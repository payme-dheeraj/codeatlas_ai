"""Audit log model — records every significant user action and AI output."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Immutable audit log entry.

    Every significant action (queries, scans, doc generation, role changes,
    API key use, etc.) is recorded here for compliance and debugging.

    Attributes:
        id: UUID primary key.
        user_id: FK to users.id (nullable for anonymous/API key actions).
        repo_id: FK to repositories.id (nullable if not repo-scoped).
        action: Action slug (e.g. scan.trigger, chat.query, role.assign).
        resource_type: Resource type string (scan | document | diagram | user).
        resource_id: UUID of the affected resource (nullable).
        request_data: Sanitised request payload (no secrets).
        response_summary: Brief summary of the result.
        ip_address: Client IP address.
        user_agent: Client user-agent string.
        status: success | failure | error.
        error_message: Error detail if status != success.
        duration_ms: Request/task duration in milliseconds.
        created_at: Event timestamp.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    request_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_audit_action", "action"),
        Index("ix_audit_user_created", "user_id", "created_at"),
        Index("ix_audit_repo_created", "repo_id", "created_at"),
    )
