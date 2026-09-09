"""SQLAlchemy ORM models for generated documentation and version history."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Valid document type slugs (matches PRD Document Types table)
DOC_TYPES = frozenset({
    "readme",
    "api_reference",
    "deployment_guide",
    "adr",
    "wiki",
    "changelog",
    "onboarding",
})


class Document(Base):
    """A generated documentation artifact for a repository.

    Each document type is scoped to a repository and supports versioning.
    The ``content_md`` column stores the canonical Markdown representation;
    optional HTML / Confluence XML are stored in ``content_extra``.

    Attributes:
        id: UUID primary key.
        repo_id: FK to repositories.id.
        doc_type: Slug identifying the document type.
        title: Human-readable document title.
        content_md: Full Markdown content.
        content_extra: Dict of alternative format strings (html, confluence, notion).
        version: Monotonically increasing version number per (repo_id, doc_type).
        is_latest: True only for the most recent version.
        generation_model: LLM model used to generate the document.
        generation_meta: Additional generation metadata (tokens, latency, …).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest: Mapped[bool] = mapped_column(nullable=False, default=True)
    generation_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_documents_repo_type", "repo_id", "doc_type"),
        Index("ix_documents_repo_latest", "repo_id", "doc_type", "is_latest"),
    )


class DocumentGenerationJob(Base):
    """Tracks async document generation tasks.

    Attributes:
        id: UUID primary key.
        repo_id: FK to repositories.id.
        doc_types: List of doc_type slugs requested.
        status: queued | running | complete | failed.
        progress: 0-100 completion percentage.
        current_stage: Human-readable stage label.
        error_message: Failure reason, if any.
        started_at: When the task began.
        finished_at: When the task completed.
        created_at: Creation timestamp.
    """

    __tablename__ = "document_generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
