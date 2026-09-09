"""Webhook model — outbound HTTP notifications for scan/doc completion events."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

WEBHOOK_EVENTS = frozenset({
    "scan.complete",
    "scan.failed",
    "docs.complete",
    "docs.failed",
    "diagram.complete",
    "diagram.failed",
    "repo.indexed",
    "repo.reindex_failed",
})


class Webhook(Base):
    """An outbound webhook subscription for repository events.

    Attributes:
        id: UUID primary key.
        repo_id: FK to repositories.id (scoped per repository).
        user_id: FK to users.id (owner of this webhook).
        url: Target HTTPS URL to POST events to.
        secret: HMAC signing secret (SHA-256 HMAC of payload).
        events: List of event slugs to subscribe to.
        is_active: Whether the webhook is enabled.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str | None] = mapped_column(String(200), nullable=True)
    events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_webhooks_repo", "repo_id"),)


class WebhookDelivery(Base):
    """Record of a webhook delivery attempt.

    Attributes:
        id: UUID primary key.
        webhook_id: FK to webhooks.id.
        event: Event slug that triggered this delivery.
        payload: JSON payload sent.
        response_status: HTTP status code received.
        response_body: First 2000 chars of response body.
        duration_ms: Round-trip duration.
        success: Whether delivery was successful (2xx).
        attempt: Attempt number (1-based).
        delivered_at: Delivery timestamp.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_webhook_deliveries_webhook", "webhook_id"),)
