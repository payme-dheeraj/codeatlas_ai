"""SQLAlchemy ORM model for the ``api_keys`` table."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents a long-lived API key credential for programmatic access.

    The raw key value is **never** stored.  Only the SHA-256 hash is persisted
    so that even a full database dump cannot recover active keys.

    Attributes:
        id: UUID primary key.
        user_id: FK to the owning user.
        name: Human-readable label (e.g. ``"CI/CD Pipeline"``).
        key_hash: SHA-256 hash of the raw key for lookup and verification.
        prefix: First 8 characters of the raw key shown in list views.
        expires_at: Expiry timestamp; None means the key never expires.
        last_used_at: Timestamp of the most recent successful authentication.
        is_active: Soft-revocation flag.
        user: Back-reference to the owning User.
    """

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    user: Mapped["User"] = relationship("User", lazy="select")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<ApiKey id={self.id} prefix={self.prefix!r} "
            f"user_id={self.user_id} active={self.is_active}>"
        )
