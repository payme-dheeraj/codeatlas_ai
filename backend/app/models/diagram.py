"""SQLAlchemy ORM model for generated diagrams."""

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

DIAGRAM_TYPES = frozenset({
    "architecture",
    "dependency",
    "sequence",
    "er",
    "deployment",
    "component_map",
    "data_flow",
})

DIAGRAM_FORMATS = frozenset({"mermaid", "plantuml", "d2"})
RENDER_FORMATS = frozenset({"svg", "png"})


class Diagram(Base):
    """A generated diagram artifact for a repository.

    Attributes:
        id: UUID primary key.
        repo_id: FK to repositories.id.
        diagram_type: One of the DIAGRAM_TYPES slugs.
        diagram_format: Source format (mermaid | plantuml | d2).
        title: Human-readable diagram title.
        source_code: Raw diagram source (Mermaid/PlantUML/D2 text).
        render_url_svg: MinIO presigned URL for SVG render.
        render_url_png: MinIO presigned URL for PNG render.
        minio_key_svg: Raw MinIO object key for SVG.
        minio_key_png: Raw MinIO object key for PNG.
        source_checksum: SHA-256 of source_code for cache invalidation.
        generation_meta: Additional metadata (model used, options, etc.).
        version: Monotonic version per (repo_id, diagram_type).
        is_latest: True for the most recent version.
        options: JSON options passed at generation time (e.g. focus_symbol).
        created_at: Creation timestamp.
    """

    __tablename__ = "diagrams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    diagram_type: Mapped[str] = mapped_column(String(30), nullable=False)
    diagram_format: Mapped[str] = mapped_column(
        String(15), nullable=False, default="mermaid"
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    render_url_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_url_png: Mapped[str | None] = mapped_column(Text, nullable=True)
    minio_key_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    minio_key_png: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest: Mapped[bool] = mapped_column(nullable=False, default=True)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_diagrams_repo_type", "repo_id", "diagram_type"),
        Index("ix_diagrams_repo_latest", "repo_id", "diagram_type", "is_latest"),
    )
