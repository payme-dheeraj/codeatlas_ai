"""Data access layer for the AuditLog model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditRepository:
    """Append-only repository for audit log entries.

    Attributes:
        _session: Active async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        action: str,
        *,
        user_id: uuid.UUID | None = None,
        repo_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        request_data: dict | None = None,
        response_summary: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> AuditLog:
        """Append an audit log entry.

        Args:
            action: Action slug (e.g. scan.trigger, role.assign).
            user_id: Performing user UUID.
            repo_id: Affected repository UUID.
            resource_type: Affected resource type.
            resource_id: Affected resource UUID.
            request_data: Sanitised request payload dict.
            response_summary: Brief result description.
            ip_address: Client IP.
            user_agent: Client user-agent.
            status: success | failure | error.
            error_message: Error detail.
            duration_ms: Duration in milliseconds.

        Returns:
            Persisted AuditLog instance.
        """
        entry = AuditLog(
            action=action,
            user_id=user_id,
            repo_id=repo_id,
            resource_type=resource_type,
            resource_id=resource_id,
            request_data=request_data or {},
            response_summary=response_summary,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        action_filter: str | None = None,
    ) -> list[AuditLog]:
        """Return audit log entries for a specific user.

        Args:
            user_id: UUID of the user.
            limit: Max rows to return.
            offset: Pagination offset.
            action_filter: Optional action prefix to filter by.

        Returns:
            List of AuditLog entries, newest first.
        """
        q = select(AuditLog).where(AuditLog.user_id == user_id)
        if action_filter:
            q = q.where(AuditLog.action.startswith(action_filter))
        q = q.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def list_for_repo(
        self,
        repo_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Return audit log entries for a specific repository.

        Args:
            repo_id: UUID of the repository.
            limit: Max rows.
            offset: Pagination offset.

        Returns:
            List of AuditLog entries, newest first.
        """
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.repo_id == repo_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        action_filter: str | None = None,
    ) -> list[AuditLog]:
        """Return all audit log entries (admin use).

        Args:
            limit: Max rows.
            offset: Pagination offset.
            action_filter: Optional action prefix filter.

        Returns:
            List of AuditLog entries, newest first.
        """
        q = select(AuditLog)
        if action_filter:
            q = q.where(AuditLog.action.startswith(action_filter))
        q = q.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
        result = await self._session.execute(q)
        return list(result.scalars().all())
