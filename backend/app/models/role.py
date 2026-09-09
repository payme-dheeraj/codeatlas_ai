"""RBAC role and permission models.

Roles: admin | analyst | viewer
Each user has one role (stored on the User model as a string column).
This module provides the canonical role constants, permission maps,
and the UserRoleAssignment model for per-repository overrides.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# ── Role constants ────────────────────────────────────────────────────────────

ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
ROLE_VIEWER = "viewer"

VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER})

# ── Permission constants ──────────────────────────────────────────────────────

PERM_REPO_CREATE = "repo:create"
PERM_REPO_READ = "repo:read"
PERM_REPO_DELETE = "repo:delete"
PERM_REPO_REINDEX = "repo:reindex"

PERM_SCAN_TRIGGER = "scan:trigger"
PERM_SCAN_READ = "scan:read"
PERM_SCAN_SUPPRESS = "scan:suppress"

PERM_DOCS_GENERATE = "docs:generate"
PERM_DOCS_READ = "docs:read"

PERM_DIAGRAMS_GENERATE = "diagrams:generate"
PERM_DIAGRAMS_READ = "diagrams:read"

PERM_CHAT_CREATE = "chat:create"
PERM_CHAT_READ = "chat:read"

PERM_USER_MANAGE = "user:manage"
PERM_ROLE_ASSIGN = "role:assign"

PERM_AUDIT_READ = "audit:read"
PERM_WEBHOOK_MANAGE = "webhook:manage"
PERM_HEALTH_READ = "health:read"
PERM_PR_ANALYZE = "pr:analyze"

# ── Role → permissions mapping ────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_ADMIN: frozenset({
        PERM_REPO_CREATE, PERM_REPO_READ, PERM_REPO_DELETE, PERM_REPO_REINDEX,
        PERM_SCAN_TRIGGER, PERM_SCAN_READ, PERM_SCAN_SUPPRESS,
        PERM_DOCS_GENERATE, PERM_DOCS_READ,
        PERM_DIAGRAMS_GENERATE, PERM_DIAGRAMS_READ,
        PERM_CHAT_CREATE, PERM_CHAT_READ,
        PERM_USER_MANAGE, PERM_ROLE_ASSIGN,
        PERM_AUDIT_READ, PERM_WEBHOOK_MANAGE,
        PERM_HEALTH_READ, PERM_PR_ANALYZE,
    }),
    ROLE_ANALYST: frozenset({
        PERM_REPO_READ, PERM_REPO_REINDEX,
        PERM_SCAN_TRIGGER, PERM_SCAN_READ, PERM_SCAN_SUPPRESS,
        PERM_DOCS_GENERATE, PERM_DOCS_READ,
        PERM_DIAGRAMS_GENERATE, PERM_DIAGRAMS_READ,
        PERM_CHAT_CREATE, PERM_CHAT_READ,
        PERM_HEALTH_READ, PERM_PR_ANALYZE,
    }),
    ROLE_VIEWER: frozenset({
        PERM_REPO_READ,
        PERM_SCAN_READ,
        PERM_DOCS_READ,
        PERM_DIAGRAMS_READ,
        PERM_CHAT_CREATE, PERM_CHAT_READ,
        PERM_HEALTH_READ,
    }),
}


def has_permission(role: str, permission: str) -> bool:
    """Check whether a role has a specific permission.

    Args:
        role: Role string (admin | analyst | viewer).
        permission: Permission constant string.

    Returns:
        True if the role includes the permission.
    """
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


# ── Per-repository role override model ────────────────────────────────────────


class UserRepoRole(Base):
    """Per-repository role override for a user.

    Allows granting a specific role on a single repository,
    overriding the user's global role for that repository context.

    Attributes:
        id: UUID primary key.
        user_id: FK to users.id.
        repo_id: FK to repositories.id.
        role: Role string (admin | analyst | viewer).
        granted_by: UUID of the admin user who granted this role.
        created_at: Grant timestamp.
    """

    __tablename__ = "user_repo_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "repo_id", name="uq_user_repo_role"),
        Index("ix_user_repo_roles_user", "user_id"),
        Index("ix_user_repo_roles_repo", "repo_id"),
    )
