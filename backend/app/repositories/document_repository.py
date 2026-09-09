"""Data access layer for Document and DocumentGenerationJob models."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentGenerationJob


class DocumentRepository:
    """Repository for document and generation job records.

    Attributes:
        _session: Active async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Generation Jobs ───────────────────────────────────────────────────────

    async def create_job(
        self, repo_id: uuid.UUID, doc_types: list[str]
    ) -> DocumentGenerationJob:
        """Create a new generation job in queued state.

        Args:
            repo_id: UUID of the repository.
            doc_types: List of doc_type slugs to generate.

        Returns:
            Persisted DocumentGenerationJob.
        """
        job = DocumentGenerationJob(
            repo_id=repo_id,
            doc_types=doc_types,
            status="queued",
        )
        self._session.add(job)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def get_job(self, job_id: uuid.UUID) -> DocumentGenerationJob | None:
        """Fetch a generation job by primary key.

        Args:
            job_id: UUID of the job.

        Returns:
            DocumentGenerationJob or None.
        """
        result = await self._session.execute(
            select(DocumentGenerationJob).where(DocumentGenerationJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def update_job(self, job_id: uuid.UUID, **fields: Any) -> None:
        """Partially update a generation job.

        Args:
            job_id: UUID of the job.
            **fields: Column names and values to update.
        """
        await self._session.execute(
            update(DocumentGenerationJob)
            .where(DocumentGenerationJob.id == job_id)
            .values(**fields)
        )
        await self._session.commit()

    # ── Documents ─────────────────────────────────────────────────────────────

    async def save_document(
        self,
        repo_id: uuid.UUID,
        doc_type: str,
        title: str,
        content_md: str,
        *,
        generation_model: str | None = None,
        generation_meta: dict | None = None,
        content_extra: dict | None = None,
    ) -> Document:
        """Save a new document version, marking all prior versions as not latest.

        Args:
            repo_id: UUID of the repository.
            doc_type: Document type slug.
            title: Document title.
            content_md: Markdown content string.
            generation_model: LLM model identifier.
            generation_meta: Additional generation metadata.
            content_extra: Alternative format content dict.

        Returns:
            Newly created Document record.
        """
        # Mark all existing versions as not latest
        await self._session.execute(
            update(Document)
            .where(Document.repo_id == repo_id, Document.doc_type == doc_type)
            .values(is_latest=False)
        )

        # Determine next version number
        max_version = await self._session.scalar(
            select(func.max(Document.version)).where(
                Document.repo_id == repo_id, Document.doc_type == doc_type
            )
        )
        next_version = (max_version or 0) + 1

        doc = Document(
            repo_id=repo_id,
            doc_type=doc_type,
            title=title,
            content_md=content_md,
            version=next_version,
            is_latest=True,
            generation_model=generation_model,
            generation_meta=generation_meta or {},
            content_extra=content_extra or {},
        )
        self._session.add(doc)
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def get_latest(
        self, repo_id: uuid.UUID, doc_type: str
    ) -> Document | None:
        """Return the latest version of a document type for a repository.

        Args:
            repo_id: UUID of the repository.
            doc_type: Document type slug.

        Returns:
            Latest Document or None.
        """
        result = await self._session.execute(
            select(Document).where(
                Document.repo_id == repo_id,
                Document.doc_type == doc_type,
                Document.is_latest.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """Fetch a document by primary key.

        Args:
            doc_id: UUID of the document.

        Returns:
            Document or None.
        """
        result = await self._session.execute(
            select(Document).where(Document.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def list_latest_for_repo(
        self, repo_id: uuid.UUID
    ) -> list[Document]:
        """Return all latest-version documents for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            List of latest Document records sorted by doc_type.
        """
        result = await self._session.execute(
            select(Document)
            .where(Document.repo_id == repo_id, Document.is_latest.is_(True))
            .order_by(Document.doc_type)
        )
        return list(result.scalars().all())

    async def list_versions(
        self, repo_id: uuid.UUID, doc_type: str
    ) -> list[Document]:
        """Return all versions of a document type, newest first.

        Args:
            repo_id: UUID of the repository.
            doc_type: Document type slug.

        Returns:
            List of Document records ordered by descending version.
        """
        result = await self._session.execute(
            select(Document)
            .where(Document.repo_id == repo_id, Document.doc_type == doc_type)
            .order_by(Document.version.desc())
        )
        return list(result.scalars().all())

    async def delete_all_for_repo(self, repo_id: uuid.UUID) -> int:
        """Delete all documents for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Number of rows deleted.
        """
        from sqlalchemy import delete
        result = await self._session.execute(
            delete(Document).where(Document.repo_id == repo_id)
        )
        await self._session.commit()
        return result.rowcount or 0
