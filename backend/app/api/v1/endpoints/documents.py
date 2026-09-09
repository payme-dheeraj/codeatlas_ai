"""Documentation service endpoints.

Routes:
  POST /repos/{repo_id}/docs/generate      — trigger doc generation
  GET  /repos/{repo_id}/docs/jobs/{job_id} — get job status
  GET  /repos/{repo_id}/docs               — list latest documents
  GET  /repos/{repo_id}/docs/{doc_type}    — get latest document by type
  GET  /docs/{doc_id}                      — get document by UUID
  GET  /docs/{doc_id}/versions             — list all versions
  GET  /docs/{doc_id}/export               — export in a format
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_optional_current_user_id as get_current_user_id, get_document_service
from app.schemas.document import (
    DocumentResponse,
    DocumentSummaryResponse,
    DocumentVersionListResponse,
    ExportFormat,
    GenerateDocsRequest,
    GenerationJobResponse,
)
from app.services.document_service import DocumentService

router = APIRouter(tags=["documentation"])


@router.post(
    "/repos/{repo_id}/docs/generate",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate documentation for a repository",
    responses={
        202: {"description": "Generation job queued"},
        401: {"description": "Not authenticated"},
    },
)
async def generate_docs(
    repo_id: uuid.UUID,
    request: GenerateDocsRequest,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> GenerationJobResponse:
    """Queue documentation generation for a repository.

    Args:
        repo_id: UUID of the repository (path parameter).
        request: Generation parameters (doc_types, options).
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        GenerationJobResponse with queued job details.
    """
    request.repo_id = repo_id  # ensure path param takes precedence
    return await service.trigger_generation(request)


@router.get(
    "/repos/{repo_id}/docs/jobs/{job_id}",
    response_model=GenerationJobResponse,
    summary="Get documentation generation job status",
    responses={
        200: {"description": "Job status"},
        401: {"description": "Not authenticated"},
        404: {"description": "Job not found"},
    },
)
async def get_doc_job(
    repo_id: uuid.UUID,
    job_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> GenerationJobResponse:
    """Return the status of a documentation generation job.

    Args:
        repo_id: UUID of the repository.
        job_id: UUID of the generation job.
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        GenerationJobResponse.

    Raises:
        HTTPException 404: If the job does not exist.
    """
    result = await service.get_job(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation job '{job_id}' not found.",
        )
    return result


@router.get(
    "/repos/{repo_id}/docs",
    response_model=list[DocumentSummaryResponse],
    summary="List all generated documents for a repository",
    responses={
        200: {"description": "List of latest document summaries"},
        401: {"description": "Not authenticated"},
    },
)
async def list_documents(
    repo_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentSummaryResponse]:
    """List all latest-version documents for a repository.

    Args:
        repo_id: UUID of the repository.
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        List of DocumentSummaryResponse.
    """
    return await service.list_documents_for_repo(repo_id)


@router.get(
    "/repos/{repo_id}/docs/{doc_type}",
    response_model=DocumentResponse,
    summary="Get latest document by type",
    responses={
        200: {"description": "Document content"},
        401: {"description": "Not authenticated"},
        404: {"description": "Document not found"},
    },
)
async def get_document_by_type(
    repo_id: uuid.UUID,
    doc_type: str,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Return the latest version of a specific document type.

    Args:
        repo_id: UUID of the repository.
        doc_type: Document type slug (readme | api_reference | wiki | …).
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        DocumentResponse with full Markdown content.

    Raises:
        HTTPException 404: If no document of this type has been generated.
    """
    result = await service.get_latest_document(repo_id, doc_type)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No '{doc_type}' document found for repository '{repo_id}'. "
                   "Trigger generation first.",
        )
    return result


@router.get(
    "/docs/{doc_id}",
    response_model=DocumentResponse,
    summary="Get a document by UUID",
    responses={
        200: {"description": "Document content"},
        401: {"description": "Not authenticated"},
        404: {"description": "Document not found"},
    },
)
async def get_document(
    doc_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Return a specific document version by UUID.

    Args:
        doc_id: UUID of the document.
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        DocumentResponse.

    Raises:
        HTTPException 404: If the document does not exist.
    """
    result = await service.get_document_by_id(doc_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found.",
        )
    return result


@router.get(
    "/docs/{doc_id}/versions",
    response_model=DocumentVersionListResponse,
    summary="List all versions of a document",
    responses={
        200: {"description": "Version history"},
        401: {"description": "Not authenticated"},
        404: {"description": "Document not found"},
    },
)
async def list_document_versions(
    doc_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> DocumentVersionListResponse:
    """Return the version history for a document.

    Args:
        doc_id: UUID of any version of the document.
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        DocumentVersionListResponse with all versions.

    Raises:
        HTTPException 404: If the document does not exist.
    """
    doc = await service.get_document_by_id(doc_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found.",
        )
    return await service.list_versions(doc.repo_id, doc.doc_type)


@router.get(
    "/docs/{doc_id}/export",
    summary="Export document in a specific format",
    description=(
        "Download a document in Markdown, HTML, Confluence Storage XML, or Notion blocks JSON. "
        "HTML includes a styled standalone page. Confluence XML is compatible with the "
        "Confluence REST API ``body.storage`` field."
    ),
    responses={
        200: {"description": "Document file download"},
        401: {"description": "Not authenticated"},
        404: {"description": "Document not found"},
    },
)
async def export_document(
    doc_id: uuid.UUID,
    fmt: ExportFormat = Query(default=ExportFormat.markdown, alias="format"),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DocumentService = Depends(get_document_service),
) -> Response:
    """Download a document in the specified export format.

    Args:
        doc_id: UUID of the document.
        fmt: Export format (markdown | html | confluence | notion).
        _: Authenticated user UUID.
        service: Injected DocumentService.

    Returns:
        File download Response.

    Raises:
        HTTPException 404: If the document does not exist.
    """
    content, content_type, filename = await service.export_document(doc_id, fmt.value)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found.",
        )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
