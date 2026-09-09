"""SQLAlchemy ORM model for the ``users`` table.

A minimal user model sufficient for auth and ownership tracking.
Full auth endpoints are implemented in a later sprint.
"""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Platform user record.

    Attributes:
        id: UUID primary key.
        email: Unique email address used for login.
        username: Unique display name / slug.
        password_hash: bcrypt hash of the user's password.  Null for OAuth users.
        role: RBAC role: admin | analyst | viewer.
        oauth_provider: OAuth2 provider name (github, google, etc.) or None.
        oauth_id: Provider-scoped user identifier for OAuth logins.
        is_active: Soft-delete / account suspension flag.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
