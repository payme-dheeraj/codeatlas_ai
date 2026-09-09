"""Business logic for repository ingestion and management.

This service orchestrates:
1. Validation and deduplication of import requests.
2. Kicking off the async clone + index Celery task.
3. Providing status queries and re-index triggers.

It never touches SQLAlchemy directly; all persistence goes through
RepoRepository and JobRepository.
"""

import os
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.index_job import IndexJob
from app.models.repository import Repository
from app.repositories.job_repository import JobRepository
from app.repositories.repo_repository import RepoRepository
from app.schemas.repository import (
    IndexJobResponse,
    ReindexRequest,
    RepositoryCreate,
    RepositoryListResponse,
    RepositoryResponse,
    RepositoryStatusResponse,
    RepositoryUpdate,
)

logger = get_logger(__name__)


def _derive_name_from_url(url: str) -> str:
    """Infer a repository display name from its clone URL.

    Args:
        url: HTTPS or SSH git URL.

    Returns:
        A cleaned-up name string (e.g. ``"my-service"`` from
        ``"https://github.com/org/my-service.git"``).
    """
    # Strip .git suffix, take the last path segment
    path = url.rstrip("/").rstrip(".git")
    name = path.split("/")[-1].split(":")[-1]
    # Replace non-alphanumeric characters with hyphens
    name = re.sub(r"[^a-zA-Z0-9._-]", "-", name)
    return name or "repository"


def _detect_provider(url: str) -> str | None:
    """Guess the hosting provider from a clone URL.

    Args:
        url: Remote clone URL.

    Returns:
        Provider slug (github | gitlab | bitbucket) or None.
    """
    lower = url.lower()
    if "github.com" in lower:
        return "github"
    if "gitlab.com" in lower or "gitlab." in lower:
        return "gitlab"
    if "bitbucket.org" in lower:
        return "bitbucket"
    if "azure.com" in lower or "visualstudio.com" in lower:
        return "azure"
    return None


def _job_to_response(job: IndexJob | None) -> IndexJobResponse | None:
    """Convert an IndexJob ORM instance to its response schema.

    Args:
        job: ORM instance or None.

    Returns:
        Serialised IndexJobResponse, or None.
    """
    if job is None:
        return None
    return IndexJobResponse.model_validate(job)


def _repo_to_response(
    repo: Repository,
    latest_job: IndexJob | None = None,
) -> RepositoryResponse:
    """Convert a Repository ORM instance to its response schema.

    Args:
        repo: Repository ORM instance.
        latest_job: Most recent IndexJob for this repository, if any.

    Returns:
        Serialised RepositoryResponse.
    """
    data = RepositoryResponse.model_validate(repo)
    data.latest_job = _job_to_response(latest_job)
    return data


class RepoService:
    """Orchestrates repository lifecycle: import, status, re-index, deletion.

    Attributes:
        _repo_repo: Data access layer for Repository records.
        _job_repo: Data access layer for IndexJob records.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session.

        Args:
            session: Active SQLAlchemy async session (injected by FastAPI).
        """
        self._repo_repo = RepoRepository(session)
        self._job_repo = JobRepository(session)

    async def import_repository(
        self,
        payload: RepositoryCreate,
        owner_id: uuid.UUID | None = None,
    ) -> RepositoryResponse:
        """Validate and register a new repository import request.

        Steps:
        1. Derive display name and provider from the URL if not provided.
        2. Check for duplicate URL / name+owner combinations.
        3. Persist the Repository record (status=``pending``).
        4. Create an IndexJob record (status=``queued``).
        5. Dispatch the ``clone_and_index_repo`` Celery task.

        Args:
            payload: Validated RepositoryCreate request body.
            owner_id: UUID of the authenticated user, or None for anon imports.

        Returns:
            Serialised RepositoryResponse with the new job attached.

        Raises:
            ValueError: If a repository with the same URL or name already exists.
        """
        # ── 1. Derive name / provider ────────────────────────────────────────
        name = payload.name
        if not name:
            if payload.url:
                name = _derive_name_from_url(payload.url)
            else:
                name = os.path.basename(payload.local_path or "repository")

        provider = payload.provider
        if not provider and payload.url:
            provider = _detect_provider(payload.url)

        # ── 2. Deduplication checks ──────────────────────────────────────────
        if payload.url:
            existing = await self._repo_repo.get_by_url(payload.url)
            if existing:
                raise ValueError(
                    f"Repository with URL '{payload.url}' already exists "
                    f"(id={existing.id})."
                )

        existing_name = await self._repo_repo.get_by_name_and_owner(name, owner_id)
        if existing_name:
            raise ValueError(
                f"Repository named '{name}' already exists for this owner."
            )

        # ── 3. Persist repository record ─────────────────────────────────────
        repo = await self._repo_repo.create(
            name=name,
            url=payload.url,
            provider=provider,
            default_branch=payload.default_branch,
            is_private=payload.is_private,
            index_status="pending",
            owner_id=owner_id,
        )
        logger.info("repository_created", repo_id=str(repo.id), name=name, url=payload.url)

        # ── 4. Create index job record ───────────────────────────────────────
        job = await self._job_repo.create(
            repo_id=repo.id,
            job_type="full_index",
            status="queued",
        )

        # ── 5. Dispatch Celery task ──────────────────────────────────────────
        try:
            from app.workers.tasks.repo_tasks import clone_and_index_repo

            task = clone_and_index_repo.apply_async(
                kwargs={
                    "repo_id": str(repo.id),
                    "job_id": str(job.id),
                    "url": payload.url,
                    "local_path": payload.local_path,
                    "zip_minio_key": getattr(payload, "zip_minio_key", None),
                    "branch": payload.default_branch,
                    "auth_token": payload.auth_token,
                    "is_private": payload.is_private,
                },
                task_id=str(job.id),  # Use job UUID as Celery task ID for easy correlation
            )
            await self._job_repo.update(job, celery_task_id=task.id)
            logger.info(
                "celery_task_dispatched",
                task_id=task.id,
                repo_id=str(repo.id),
                job_id=str(job.id),
            )
        except Exception as exc:
            # If task dispatch fails, mark job as failed but keep repo record
            await self._job_repo.update(
                job,
                status="failed",
                error_message=f"Failed to dispatch task: {exc}",
            )
            await self._repo_repo.update_status(
                repo.id, "failed", error_message=str(exc)
            )
            logger.error(
                "celery_task_dispatch_failed",
                error=str(exc),
                repo_id=str(repo.id),
            )

        return _repo_to_response(repo, job)

    async def get_repository(self, repo_id: uuid.UUID) -> RepositoryResponse | None:
        """Retrieve a single repository with its latest job.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Serialised RepositoryResponse, or None if not found.
        """
        repo = await self._repo_repo.get_by_id(repo_id)
        if repo is None:
            return None
        latest_job = await self._job_repo.get_latest_for_repo(repo_id)
        return _repo_to_response(repo, latest_job)

    async def list_repositories(
        self,
        owner_id: uuid.UUID | None = None,
        *,
        page: int = 1,
        limit: int = 20,
        status_filter: str | None = None,
    ) -> RepositoryListResponse:
        """Return a paginated list of repositories.

        Args:
            owner_id: Filter to repositories owned by this user (optional).
            page: Page number (1-indexed).
            limit: Items per page (max 100).
            status_filter: Optional ``index_status`` filter.

        Returns:
            Paginated RepositoryListResponse.
        """
        limit = min(limit, 100)
        offset = (page - 1) * limit

        if owner_id:
            repos, total = await self._repo_repo.list_by_owner(
                owner_id,
                offset=offset,
                limit=limit,
                status_filter=status_filter,
            )
        else:
            repos, total = await self._repo_repo.list(
                offset=offset,
                limit=limit,
                order_by=None,
            )

        items = []
        for repo in repos:
            latest_job = await self._job_repo.get_latest_for_repo(repo.id)
            items.append(_repo_to_response(repo, latest_job))

        return RepositoryListResponse(
            total=total,
            page=page,
            limit=limit,
            has_next=(offset + limit) < total,
            items=items,
        )

    async def get_status(self, repo_id: uuid.UUID) -> RepositoryStatusResponse | None:
        """Return detailed indexing status for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            RepositoryStatusResponse, or None if not found.
        """
        repo = await self._repo_repo.get_by_id(repo_id)
        if repo is None:
            return None
        latest_job = await self._job_repo.get_latest_for_repo(repo_id)
        return RepositoryStatusResponse(
            repo_id=repo.id,
            index_status=repo.index_status,
            latest_job=_job_to_response(latest_job),
        )

    async def trigger_reindex(
        self,
        repo_id: uuid.UUID,
        payload: ReindexRequest,
    ) -> RepositoryResponse | None:
        """Trigger a re-indexing run for an existing repository.

        Blocks if a job is already active unless ``force_full`` is set.

        Args:
            repo_id: UUID of the repository to re-index.
            payload: Re-index options (job_type, force_full).

        Returns:
            Updated RepositoryResponse, or None if the repo does not exist.

        Raises:
            ValueError: If a job is already running and force_full is False.
        """
        repo = await self._repo_repo.get_by_id(repo_id)
        if repo is None:
            return None

        # Block duplicate runs
        active = await self._job_repo.get_active_job_for_repo(repo_id)
        if active and not payload.force_full:
            raise ValueError(
                f"Repository is already being indexed (job_id={active.id}). "
                "Pass force_full=true to override."
            )

        job = await self._job_repo.create(
            repo_id=repo.id,
            job_type=payload.job_type,
            status="queued",
        )

        try:
            from app.workers.tasks.repo_tasks import clone_and_index_repo

            task = clone_and_index_repo.apply_async(
                kwargs={
                    "repo_id": str(repo.id),
                    "job_id": str(job.id),
                    "url": repo.url,
                    "local_path": None,
                    "branch": repo.default_branch,
                    "auth_token": None,
                    "is_private": repo.is_private,
                },
                task_id=str(job.id),
            )
            await self._job_repo.update(job, celery_task_id=task.id)
            await self._repo_repo.update_status(repo.id, "pending")
            logger.info(
                "reindex_dispatched",
                repo_id=str(repo_id),
                job_id=str(job.id),
                job_type=payload.job_type,
            )
        except Exception as exc:
            await self._job_repo.update(job, status="failed", error_message=str(exc))
            logger.error("reindex_dispatch_failed", error=str(exc), repo_id=str(repo_id))

        return await self.get_repository(repo_id)

    async def update_repository(
        self,
        repo_id: uuid.UUID,
        payload: RepositoryUpdate,
    ) -> RepositoryResponse | None:
        """Apply a partial update to a repository's mutable metadata.

        Args:
            repo_id: UUID of the repository.
            payload: Fields to update (all optional).

        Returns:
            Updated RepositoryResponse, or None if not found.
        """
        repo = await self._repo_repo.get_by_id(repo_id)
        if repo is None:
            return None
        updates = payload.model_dump(exclude_none=True)
        if updates:
            repo = await self._repo_repo.update(repo, **updates)
        latest_job = await self._job_repo.get_latest_for_repo(repo_id)
        return _repo_to_response(repo, latest_job)

    async def delete_repository(self, repo_id: uuid.UUID) -> bool:
        """Delete a repository record and schedule its stored artifacts for removal.

        Args:
            repo_id: UUID of the repository to delete.

        Returns:
            True if the repository was found and deleted, False otherwise.
        """
        repo = await self._repo_repo.get_by_id(repo_id)
        if repo is None:
            return False

        # Schedule MinIO cleanup asynchronously (non-blocking)
        try:
            from app.workers.tasks.repo_tasks import delete_repo_artifacts

            delete_repo_artifacts.apply_async(kwargs={"repo_id": str(repo_id)})
        except Exception as exc:
            logger.warning(
                "artifact_cleanup_dispatch_failed",
                repo_id=str(repo_id),
                error=str(exc),
            )

        await self._repo_repo.delete(repo)
        logger.info("repository_deleted", repo_id=str(repo_id))
        return True
