"""Admin endpoints: RBAC role management and audit log access.

Routes:
  GET  /admin/audit-logs              — list all audit logs (admin only)
  GET  /admin/audit-logs/user/{uid}   — logs for a user
  GET  /admin/audit-logs/repo/{rid}   — logs for a repository
  GET  /admin/users/{uid}/role        — get a user's role
  PUT  /admin/users/{uid}/role        — update a user's global role
  POST /repos/{repo_id}/roles         — assign per-repo role
  GET  /repos/{repo_id}/roles         — list per-repo role overrides
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.rbac import require_permission, require_role
from app.models.role import (
    PERM_AUDIT_READ,
    PERM_ROLE_ASSIGN,
    PERM_USER_MANAGE,
    VALID_ROLES,
    UserRepoRole,
)
from app.models.user import User
from app.repositories.audit_repository import AuditRepository

router = APIRouter(tags=["admin"])


# ── Pydantic schemas (inline — simple enough) ─────────────────────────────────


class RoleUpdateRequest(BaseModel):
    role: str


class RepoRoleAssignRequest(BaseModel):
    user_id: uuid.UUID
    role: str


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    repo_id: uuid.UUID | None
    action: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    status: str
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserRoleResponse(BaseModel):
    user_id: uuid.UUID
    role: str


class RepoRoleResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    repo_id: uuid.UUID
    role: str
    granted_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Audit log endpoints ───────────────────────────────────────────────────────


@router.get(
    "/admin/audit-logs",
    response_model=list[AuditLogResponse],
    summary="List all audit log entries (admin only)",
    dependencies=[Depends(require_permission(PERM_AUDIT_READ))],
)
async def list_all_audit_logs(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    repo = AuditRepository(session)
    entries = await repo.list_all(limit=limit, offset=offset, action_filter=action)
    return [AuditLogResponse.model_validate(e) for e in entries]


@router.get(
    "/admin/audit-logs/user/{user_id}",
    response_model=list[AuditLogResponse],
    summary="List audit logs for a specific user",
    dependencies=[Depends(require_permission(PERM_AUDIT_READ))],
)
async def list_user_audit_logs(
    user_id: uuid.UUID,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    repo = AuditRepository(session)
    entries = await repo.list_for_user(user_id, limit=limit, offset=offset)
    return [AuditLogResponse.model_validate(e) for e in entries]


@router.get(
    "/admin/audit-logs/repo/{repo_id}",
    response_model=list[AuditLogResponse],
    summary="List audit logs for a specific repository",
    dependencies=[Depends(require_permission(PERM_AUDIT_READ))],
)
async def list_repo_audit_logs(
    repo_id: uuid.UUID,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    repo = AuditRepository(session)
    entries = await repo.list_for_repo(repo_id, limit=limit, offset=offset)
    return [AuditLogResponse.model_validate(e) for e in entries]


# ── Role management endpoints ─────────────────────────────────────────────────


@router.get(
    "/admin/users/{user_id}/role",
    response_model=UserRoleResponse,
    summary="Get a user's global role",
    dependencies=[Depends(require_permission(PERM_USER_MANAGE))],
)
async def get_user_role(
    user_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> UserRoleResponse:
    result = await session.execute(select(User.role).where(User.id == user_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
    return UserRoleResponse(user_id=user_id, role=role)


@router.put(
    "/admin/users/{user_id}/role",
    response_model=UserRoleResponse,
    summary="Update a user's global role (admin only)",
    dependencies=[Depends(require_permission(PERM_ROLE_ASSIGN))],
)
async def update_user_role(
    user_id: uuid.UUID,
    body: RoleUpdateRequest,
    actor: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> UserRoleResponse:
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role '{body.role}'. Valid roles: {sorted(VALID_ROLES)}",
        )
    result = await session.execute(
        update(User).where(User.id == user_id).values(role=body.role).returning(User.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
    await session.commit()

    # Audit
    audit = AuditRepository(session)
    await audit.log(
        "role.assign",
        user_id=actor,
        resource_type="user",
        resource_id=user_id,
        request_data={"new_role": body.role},
        response_summary=f"Role updated to {body.role}",
    )
    return UserRoleResponse(user_id=user_id, role=body.role)


@router.post(
    "/repos/{repo_id}/roles",
    response_model=RepoRoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a per-repository role override",
    dependencies=[Depends(require_permission(PERM_ROLE_ASSIGN))],
)
async def assign_repo_role(
    repo_id: uuid.UUID,
    body: RepoRoleAssignRequest,
    actor: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> RepoRoleResponse:
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role '{body.role}'.",
        )

    # Upsert
    existing = await session.execute(
        select(UserRepoRole).where(
            UserRepoRole.user_id == body.user_id,
            UserRepoRole.repo_id == repo_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        await session.execute(
            update(UserRepoRole)
            .where(UserRepoRole.id == row.id)
            .values(role=body.role, granted_by=actor)
        )
        await session.commit()
        await session.refresh(row)
        return RepoRoleResponse.model_validate(row)

    assignment = UserRepoRole(
        user_id=body.user_id,
        repo_id=repo_id,
        role=body.role,
        granted_by=actor,
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return RepoRoleResponse.model_validate(assignment)


@router.get(
    "/repos/{repo_id}/roles",
    response_model=list[RepoRoleResponse],
    summary="List per-repository role assignments",
    dependencies=[Depends(require_permission(PERM_USER_MANAGE))],
)
async def list_repo_roles(
    repo_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[RepoRoleResponse]:
    result = await session.execute(
        select(UserRepoRole).where(UserRepoRole.repo_id == repo_id)
    )
    return [RepoRoleResponse.model_validate(r) for r in result.scalars().all()]
