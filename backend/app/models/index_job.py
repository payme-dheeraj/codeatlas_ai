"""SQLAlchemy ORM model for the ``index_jobs`` table."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IndexJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks the lifecycle of a single repository indexing run.

    Each time a repository is imported or re-indexed, one IndexJob record
    is created.  The Celery task ID is stored so callers can poll for
    progress via the Celery result backend.

    Attributes:
        id: UUID primary key.
        repo_id: FK to the parent Repository.
        job_type: The kind of indexing work requested.
        status: Current Celery task lifecycle state.
        celery_task_id: The Celery async result ID returned at dispatch.
        progress: Integer 0-100 representing percentage completion.
        current_stage: Human-readable label of the step currently running.
        error_message: Captured traceback / error string on failure.
        started_at: When the Celery worker picked up the task.
        finished_at: When the task reached a terminal state.
        repository: Back-reference to the parent Repository.
    """

    __tablename__ = "index_jobs"

    # ── Foreign key ───────────────────────────────────────────────────────────
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Job type ──────────────────────────────────────────────────────────────
    job_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # full_index | incremental | parse_only | embed_only

    # ── Celery integration ────────────────────────────────────────────────────
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # ── Progress tracking ─────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(30), default="queued", nullable=False, index=True
    )  # queued | running | complete | failed | revoked
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # e.g. "cloning", "parsing", "embedding"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timing ────────────────────────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    repository: Mapped["Repository"] = relationship(  # noqa: F821
        "Repository",
        back_populates="index_jobs",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<IndexJob id={self.id} repo_id={self.repo_id} "
            f"type={self.job_type!r} status={self.status!r}>"
        )
