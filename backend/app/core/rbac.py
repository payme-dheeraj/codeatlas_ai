"""RBAC enforcement helpers and FastAPI dependencies.

Provides:
- ``require_permission(perm)``  — FastAPI Depends factory that raises 403
  if the current user's role lacks the requested permission.
- ``require_role(role)``        — Role-level guard.
- ``get_current_user_role``     — Async dep that resolves the effective role.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.logging import get_logger
from app.models.role import ROLE_VIEWER, VALID_ROLES, has_permission

logger = get_logger(__name__)


async def get_current_user_role(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> str:
    """Resolve the current user's global role from the User model.

    Args:
        user_id: Current authenticated user UUID.
        session: Async DB session.

    Returns:
        Role string (admin | analyst | viewer). Defaults to viewer.
    """
    from app.models.user import User

    result = await session.execute(select(User.role).where(User.id == user_id))
    role = result.scalar_one_or_none()
    if role not in VALID_ROLES:
        return ROLE_VIEWER
    return role


def require_permission(permission: str):
    """FastAPI dependency factory that enforces a permission gate.

    Args:
        permission: Permission constant string from app.models.role.

    Returns:
        Async dependency callable.

    Raises:
        HTTPException 403: If the user's role lacks the permission.
    """
    async def _dep(
        role: str = Depends(get_current_user_role),
    ) -> str:
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role '{role}' does not have '{permission}' permission.",
            )
        return role

    return _dep


def require_role(required_role: str):
    """FastAPI dependency that enforces a minimum role level.

    Role hierarchy: admin > analyst > viewer.

    Args:
        required_role: Minimum role required.

    Returns:
        Async dependency callable.

    Raises:
        HTTPException 403: If the user's role is below the required level.
    """
    _hierarchy = {ROLE_VIEWER: 0, "analyst": 1, "admin": 2}

    async def _dep(role: str = Depends(get_current_user_role)) -> str:
        if _hierarchy.get(role, 0) < _hierarchy.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' or higher required. Your role: '{role}'.",
            )
        return role

    return _dep
