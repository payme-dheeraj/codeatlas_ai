"""Document service — async orchestrator for documentation generation and export."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    DocumentResponse,
    DocumentSummaryResponse,
    DocumentVersionListResponse,
    GenerateDocsRequest,
    GenerationJobResponse,
)

logger = get_logger(__name__)


class DocumentService:
    """Async service for document generation, retrieval, and export.

    Attributes:
        _repo: Data access layer for document records.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = DocumentRepository(session)

    # ── Generation ─────────────────────────────────────────────────────────────

    async def trigger_generation(
        self, request: GenerateDocsRequest
    ) -> GenerationJobResponse:
        """Create a generation job and dispatch the Celery task.

        Args:
            request: GenerateDocsRequest with repo_id, doc_types, options.

        Returns:
            GenerationJobResponse with job status.
        """
        doc_types = [t.value for t in request.doc_types]
        job = await self._repo.create_job(request.repo_id, doc_types)

        from app.workers.tasks.document_tasks import generate_documents
        generate_documents.apply_async(
            kwargs={
                "job_id": str(job.id),
                "repo_id": str(request.repo_id),
                "doc_types": doc_types,
                "force_regenerate": request.force_regenerate,
                "llm_provider": request.llm_provider,
                "llm_model": request.llm_model,
            }
        )
        logger.info("doc_job_dispatched", job_id=str(job.id), repo_id=str(request.repo_id))
        return GenerationJobResponse.model_validate(job)

    async def get_job(self, job_id: uuid.UUID) -> GenerationJobResponse | None:
        """Return generation job status.

        Args:
            job_id: UUID of the job.

        Returns:
            GenerationJobResponse or None.
        """
        job = await self._repo.get_job(job_id)
        if job is None:
            return None
        return GenerationJobResponse.model_validate(job)

    # ── Document retrieval ─────────────────────────────────────────────────────

    async def get_latest_document(
        self,
        repo_id: uuid.UUID,
        doc_type: str,
    ) -> DocumentResponse | None:
        """Return the latest version of a document.

        Args:
            repo_id: UUID of the repository.
            doc_type: Document type slug.

        Returns:
            DocumentResponse or None if not generated yet.
        """
        doc = await self._repo.get_latest(repo_id, doc_type)
        if doc is None:
            return None
        return DocumentResponse.model_validate(doc)

    async def get_document_by_id(self, doc_id: uuid.UUID) -> DocumentResponse | None:
        """Return a specific document version by UUID.

        Args:
            doc_id: UUID of the document.

        Returns:
            DocumentResponse or None.
        """
        doc = await self._repo.get_by_id(doc_id)
        if doc is None:
            return None
        return DocumentResponse.model_validate(doc)

    async def list_documents_for_repo(
        self, repo_id: uuid.UUID
    ) -> list[DocumentSummaryResponse]:
        """Return all latest-version document summaries for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            List of DocumentSummaryResponse.
        """
        docs = await self._repo.list_latest_for_repo(repo_id)
        return [DocumentSummaryResponse.model_validate(d) for d in docs]

    async def list_versions(
        self, repo_id: uuid.UUID, doc_type: str
    ) -> DocumentVersionListResponse:
        """Return all versions of a document type.

        Args:
            repo_id: UUID of the repository.
            doc_type: Document type slug.

        Returns:
            DocumentVersionListResponse with version history.
        """
        versions = await self._repo.list_versions(repo_id, doc_type)
        return DocumentVersionListResponse(
            doc_type=doc_type,
            total=len(versions),
            versions=[DocumentSummaryResponse.model_validate(v) for v in versions],
        )

    # ── Export ─────────────────────────────────────────────────────────────────

    async def export_document(
        self,
        doc_id: uuid.UUID,
        fmt: str = "markdown",
    ) -> tuple[str, str, str]:
        """Export a document in the requested format.

        Args:
            doc_id: UUID of the document to export.
            fmt: Target format (markdown | html | confluence | notion).

        Returns:
            Tuple of (content_string, content_type, filename).
        """
        doc = await self._repo.get_by_id(doc_id)
        if doc is None:
            return "", "text/plain", "document.md"

        if fmt == "html":
            from app.docs_gen.exporters import to_html
            content = to_html(doc.content_md, title=doc.title)
            return content, "text/html", f"{doc.doc_type}_v{doc.version}.html"

        elif fmt == "confluence":
            from app.docs_gen.exporters import to_confluence_xml
            content = to_confluence_xml(doc.content_md, title=doc.title)
            return content, "application/xml", f"{doc.doc_type}_v{doc.version}.xml"

        elif fmt == "notion":
            import json
            from app.docs_gen.exporters import to_notion_blocks
            blocks = to_notion_blocks(doc.content_md)
            content = json.dumps({"blocks": blocks}, indent=2)
            return content, "application/json", f"{doc.doc_type}_v{doc.version}.json"

        else:  # markdown (default)
            return doc.content_md, "text/markdown", f"{doc.doc_type}_v{doc.version}.md"
