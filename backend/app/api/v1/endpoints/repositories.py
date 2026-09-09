"""REST endpoints for repository management.

All endpoints are OpenAPI-documented and return consistent JSON error bodies
following RFC 7807 Problem Details (via FastAPI's HTTPException).

Route prefix: /api/v1/repos
"""

import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import (
    get_optional_current_user_id,
    get_repo_service,
)
from app.core.logging import get_logger
from app.schemas.repository import (
    ReindexRequest,
    RepositoryCreate,
    RepositoryListResponse,
    RepositoryResponse,
    RepositoryStatusResponse,
    RepositoryUpdate,
)
from app.services.repo_service import RepoService

router = APIRouter(prefix="/repos", tags=["repositories"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import a repository",
    description=(
        "Register a new repository for ingestion. "
        "The clone and index pipeline is dispatched asynchronously. "
        "Poll `GET /repos/{id}/status` for progress."
    ),
    responses={
        202: {"description": "Repository accepted for indexing"},
        409: {"description": "Repository with this URL or name already exists"},
        422: {"description": "Validation error in request body"},
    },
)
async def import_repository(
    payload: RepositoryCreate,
    service: RepoService = Depends(get_repo_service),
    owner_id: uuid.UUID | None = Depends(get_optional_current_user_id),
) -> RepositoryResponse:
    """Import a new repository by URL or local path.

    The endpoint returns immediately with HTTP 202. Cloning and indexing
    happen in a background Celery worker. Use the returned ``latest_job.id``
    or ``GET /repos/{id}/status`` to track progress.

    Args:
        payload: Repository import request body.
        service: Injected RepoService.
        owner_id: UUID of the authenticated user (optional).

    Returns:
        Newly created RepositoryResponse with queued IndexJob attached.

    Raises:
        HTTPException 409: If a repository with the same URL or name exists.
    """
    try:
        return await service.import_repository(payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=RepositoryListResponse,
    summary="List repositories",
    description="Return a paginated list of repositories, optionally filtered by status.",
)
async def list_repositories(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by index_status: pending | cloning | complete | failed",
    ),
    service: RepoService = Depends(get_repo_service),
    owner_id: uuid.UUID | None = Depends(get_optional_current_user_id),
) -> RepositoryListResponse:
    """Return all repositories visible to the caller.

    Args:
        page: 1-indexed page number.
        limit: Items per page (max 100).
        status_filter: Optional index_status filter.
        service: Injected RepoService.
        owner_id: Authenticated user UUID (optional — returns all repos if None).

    Returns:
        Paginated RepositoryListResponse.
    """
    return await service.list_repositories(
        owner_id=owner_id,
        page=page,
        limit=limit,
        status_filter=status_filter,
    )


@router.get(
    "/{repo_id}",
    response_model=RepositoryResponse,
    summary="Get repository details",
    responses={
        200: {"description": "Repository details"},
        404: {"description": "Repository not found"},
    },
)
async def get_repository(
    repo_id: uuid.UUID,
    service: RepoService = Depends(get_repo_service),
) -> RepositoryResponse:
    """Retrieve full details for a single repository.

    Args:
        repo_id: UUID of the target repository.
        service: Injected RepoService.

    Returns:
        RepositoryResponse including the latest IndexJob.

    Raises:
        HTTPException 404: If the repository does not exist.
    """
    result = await service.get_repository(repo_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found.",
        )
    return result


@router.patch(
    "/{repo_id}",
    response_model=RepositoryResponse,
    summary="Update repository metadata",
    responses={
        200: {"description": "Updated repository"},
        404: {"description": "Repository not found"},
    },
)
async def update_repository(
    repo_id: uuid.UUID,
    payload: RepositoryUpdate,
    service: RepoService = Depends(get_repo_service),
) -> RepositoryResponse:
    """Partially update a repository's mutable metadata fields.

    Args:
        repo_id: UUID of the repository to update.
        payload: Fields to update (all optional).
        service: Injected RepoService.

    Returns:
        Updated RepositoryResponse.

    Raises:
        HTTPException 404: If the repository does not exist.
    """
    result = await service.update_repository(repo_id, payload)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found.",
        )
    return result


@router.delete(
    "/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a repository",
    responses={
        204: {"description": "Repository deleted"},
        404: {"description": "Repository not found"},
    },
)
async def delete_repository(
    repo_id: uuid.UUID,
    service: RepoService = Depends(get_repo_service),
) -> None:
    """Delete a repository record and schedule artifact cleanup.

    MinIO objects are deleted asynchronously in a background task.

    Args:
        repo_id: UUID of the repository to delete.
        service: Injected RepoService.

    Raises:
        HTTPException 404: If the repository does not exist.
    """
    deleted = await service.delete_repository(repo_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found.",
        )


@router.get(
    "/{repo_id}/status",
    response_model=RepositoryStatusResponse,
    summary="Get indexing status",
    description=(
        "Returns the current indexing lifecycle status and the latest job details. "
        "Poll this endpoint every 5–10 seconds while index_status is not "
        "'complete' or 'failed'."
    ),
    responses={
        200: {"description": "Status response"},
        404: {"description": "Repository not found"},
    },
)
async def get_repository_status(
    repo_id: uuid.UUID,
    service: RepoService = Depends(get_repo_service),
) -> RepositoryStatusResponse:
    """Return the current indexing status and latest job progress.

    Args:
        repo_id: UUID of the repository.
        service: Injected RepoService.

    Returns:
        RepositoryStatusResponse with index_status and latest_job fields.

    Raises:
        HTTPException 404: If the repository does not exist.
    """
    result = await service.get_status(repo_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found.",
        )
    return result


@router.get(
    "/{repo_id}/status/stream",
    summary="Stream indexing status updates via SSE",
    description=(
        "Streams Server-Sent Events with the current index status and progress percentage. "
        "Terminates with [DONE] when indexing completes or fails."
    ),
    responses={
        200: {"description": "SSE stream of progress events"},
        404: {"description": "Repository not found"},
    },
)
async def stream_repository_status(
    repo_id: uuid.UUID,
    service: RepoService = Depends(get_repo_service),
) -> StreamingResponse:
    """Stream real-time indexing status and job progress via Server-Sent Events.

    Args:
        repo_id: UUID of the repository.
        service: Injected RepoService.

    Returns:
        StreamingResponse with text/event-stream content.
    """
    import asyncio
    import json

    initial = await service.get_status(repo_id)
    if initial is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found.",
        )

    async def event_generator():
        while True:
            result = await service.get_status(repo_id)
            if result is None:
                break

            cur_status = result.index_status
            progress = (
                result.latest_job.progress
                if result.latest_job
                else (100 if cur_status in ("complete", "cloned") else 0)
            )
            stage = result.latest_job.current_stage if result.latest_job else None

            payload = {
                "status": cur_status,
                "progress": progress,
                "current_stage": stage,
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if cur_status in ("complete", "failed", "cloned"):
                break

            await asyncio.sleep(1.5)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{repo_id}/reindex",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger re-indexing",
    description=(
        "Dispatch a new indexing job for an already-imported repository. "
        "Will reject the request if a job is already running unless force_full=true."
    ),
    responses={
        202: {"description": "Re-index job accepted"},
        404: {"description": "Repository not found"},
        409: {"description": "An indexing job is already running"},
    },
)
async def reindex_repository(
    repo_id: uuid.UUID,
    payload: ReindexRequest = ReindexRequest(),
    service: RepoService = Depends(get_repo_service),
) -> RepositoryResponse:
    """Trigger a re-indexing run for an existing repository.

    Args:
        repo_id: UUID of the repository to re-index.
        payload: Re-index options.
        service: Injected RepoService.

    Returns:
        Updated RepositoryResponse with the new queued job.

    Raises:
        HTTPException 404: Repository not found.
        HTTPException 409: Active job exists and force_full is False.
    """
    try:
        result = await service.trigger_reindex(repo_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found.",
        )
    return result


@router.post(
    "/upload",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import a repository from a ZIP archive",
    description=(
        "Upload a ZIP file containing a repository. "
        "The archive is extracted to a temp directory and indexed asynchronously."
    ),
    responses={
        202: {"description": "Repository accepted for indexing"},
        400: {"description": "Invalid ZIP file"},
        409: {"description": "Repository with this name already exists"},
    },
)
async def upload_repository(
    file: UploadFile = File(..., description="ZIP archive of the repository"),
    name: str | None = Query(default=None, description="Display name (defaults to ZIP filename)"),
    service: RepoService = Depends(get_repo_service),
    owner_id: uuid.UUID | None = Depends(get_optional_current_user_id),
) -> RepositoryResponse:
    """Import a repository by uploading a ZIP archive.

    Args:
        file: Uploaded ZIP file.
        name: Optional display name (derived from filename if omitted).
        service: Injected RepoService.
        owner_id: Authenticated user UUID (optional).

    Returns:
        Newly created RepositoryResponse with queued IndexJob.

    Raises:
        HTTPException 400: If the uploaded file is not a valid ZIP.
        HTTPException 409: If a repository with the same name already exists.
    """
    import io as _io

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a .zip archive.",
        )

    repo_name = name or Path(file.filename).stem
    contents = await file.read()

    if not zipfile.is_zipfile(_io.BytesIO(contents)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid ZIP archive.",
        )

    # Upload the ZIP to MinIO so the worker (in a separate container) can access it.
    try:
        from minio import Minio as _Minio
        from app.core.config import settings as _settings

        _client = _Minio(
            endpoint=_settings.minio_endpoint,
            access_key=_settings.minio_access_key,
            secret_key=_settings.minio_secret_key,
            secure=_settings.minio_secure,
        )
        bucket = _settings.minio_bucket_repos
        if not _client.bucket_exists(bucket):
            _client.make_bucket(bucket)

        zip_key = f"uploads/{repo_name}/{file.filename}"
        _client.put_object(
            bucket_name=bucket,
            object_name=zip_key,
            data=_io.BytesIO(contents),
            length=len(contents),
            content_type="application/zip",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store ZIP in object storage: {exc}",
        ) from exc

    payload = RepositoryCreate(
        zip_minio_key=zip_key,
        name=repo_name,
        provider="local",
    )
    try:
        return await service.import_repository(payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{repo_id}/files",
    summary="List files/directories in a repository path",
)
async def list_repo_files(
    repo_id: uuid.UUID,
    path: str = Query(default="", description="Relative path inside the repo (empty = root)"),
) -> list[dict]:
    """Return immediate children of a path in the repository stored in MinIO."""
    try:
        from minio import Minio as _Minio
        from app.core.config import settings as _settings

        client = _Minio(
            endpoint=_settings.minio_endpoint,
            access_key=_settings.minio_access_key,
            secret_key=_settings.minio_secret_key,
            secure=_settings.minio_secure,
        )
        bucket = _settings.minio_bucket_repos
        prefix = f"repos/{repo_id}/raw/"
        query_prefix = prefix + (path.lstrip("/") + "/" if path else "")

        seen: dict[str, dict] = {}
        for obj in client.list_objects(bucket, prefix=query_prefix, recursive=False):
            rel = obj.object_name[len(query_prefix):]
            if not rel:
                continue
            parts = rel.split("/")
            name = parts[0]
            if name in seen:
                continue
            is_dir = obj.is_dir or len(parts) > 1
            entry_path = (path.rstrip("/") + "/" + name).lstrip("/") if path else name
            seen[name] = {
                "name": name,
                "path": entry_path,
                "type": "directory" if is_dir else "file",
                "size": obj.size if not is_dir else None,
            }
        return sorted(seen.values(), key=lambda x: (x["type"] == "file", x["name"]))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {exc}",
        ) from exc


@router.get(
    "/{repo_id}/file",
    summary="Get file content from repository",
)
async def get_repo_file(
    repo_id: uuid.UUID,
    path: str = Query(..., description="Relative file path inside the repo"),
) -> dict:
    """Return the text content of a single file stored in MinIO."""
    import io as _io
    try:
        from minio import Minio as _Minio
        from app.core.config import settings as _settings

        client = _Minio(
            endpoint=_settings.minio_endpoint,
            access_key=_settings.minio_access_key,
            secret_key=_settings.minio_secret_key,
            secure=_settings.minio_secure,
        )
        bucket = _settings.minio_bucket_repos
        obj_key = f"repos/{repo_id}/raw/{path.lstrip('/')}"
        response = client.get_object(bucket, obj_key)
        raw = response.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = f"(binary file, {len(raw)} bytes)"
        return {"path": path, "content": content, "size": len(raw)}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path} ({exc})",
        ) from exc
