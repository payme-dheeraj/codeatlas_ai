"""SQLAlchemy ORM model for the ``repositories`` table."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Repository(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents an imported software repository.

    A repository is the root entity of the system.  All parsed symbols,
    embeddings, graph nodes, security findings, and generated documents
    are associated with a repository record.

    Attributes:
        id: UUID primary key.
        owner_id: FK to the ``users`` table (nullable until auth is wired).
        name: Human-readable display name (slug-safe).
        url: Remote clone URL (HTTPS or SSH).  Null for local imports.
        local_path: Absolute path inside the container (MinIO key prefix).
        provider: Hosting provider identifier.
        default_branch: The branch that was cloned and indexed.
        description: Short description inferred from README or provided by user.
        tech_stack: JSON blob with detected languages, frameworks, and tools.
        stats: JSON blob with file count, LOC, contributor count, etc.
        index_status: Current indexing lifecycle state.
        last_indexed_at: Timestamp of the most recent successful full index.
        is_private: Whether the repository requires authentication to clone.
        index_jobs: Back-reference to all associated IndexJob records.
    """

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_repositories_owner_name"),
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # ── Source ────────────────────────────────────────────────────────────────
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # github | gitlab | bitbucket | local
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    is_private: Mapped[bool] = mapped_column(default=False, nullable=False)

    # ── Metadata ──────────────────────────────────────────────────────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    clone_path: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # MinIO key prefix for raw files

    # ── Status ────────────────────────────────────────────────────────────────
    index_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )  # pending | cloning | cloned | parsing | embedding | complete | failed
    last_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    index_jobs: Mapped[list["IndexJob"]] = relationship(  # noqa: F821
        "IndexJob",
        back_populates="repository",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id} name={self.name!r} status={self.index_status!r}>"
