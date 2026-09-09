"""Repository pattern implementation for the Repository model."""

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.repository import Repository
from app.repositories.base import BaseRepository


class RepoRepository(BaseRepository[Repository]):
    """Data access layer for the ``repositories`` table.

    Extends BaseRepository with repository-specific query methods.

    Attributes:
        model: Bound to the Repository ORM model.
    """

    model = Repository

    async def get_with_latest_job(self, repo_id: uuid.UUID) -> Repository | None:
        """Fetch a repository eagerly loading its most recent IndexJob.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Repository instance with ``index_jobs`` populated, or None.
        """
        result = await self._session.execute(
            select(Repository)
            .options(selectinload(Repository.index_jobs))
            .where(Repository.id == repo_id)
        )
        return result.scalar_one_or_none()

    async def get_by_url(self, url: str) -> Repository | None:
        """Look up a repository by its remote clone URL.

        Args:
            url: Exact clone URL to match.

        Returns:
            Matching Repository, or None if not found.
        """
        result = await self._session.execute(
            select(Repository).where(Repository.url == url)
        )
        return result.scalar_one_or_none()

    async def get_by_name_and_owner(
        self,
        name: str,
        owner_id: uuid.UUID | None,
    ) -> Repository | None:
        """Look up a repository by display name and optional owner.

        Args:
            name: Display name to match.
            owner_id: Owner UUID, or None for anonymous imports.

        Returns:
            Matching Repository, or None.
        """
        stmt = select(Repository).where(Repository.name == name)
        if owner_id is not None:
            stmt = stmt.where(Repository.owner_id == owner_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 20,
        status_filter: str | None = None,
    ) -> tuple[list[Repository], int]:
        """Return paginated repositories owned by a specific user.

        Args:
            owner_id: UUID of the owning user.
            offset: Number of records to skip.
            limit: Maximum records to return.
            status_filter: Optional index_status to filter on.

        Returns:
            Tuple of (repositories, total_count).
        """
        filters: list[Any] = [Repository.owner_id == owner_id]
        if status_filter:
            filters.append(Repository.index_status == status_filter)
        return await self.list(
            offset=offset,
            limit=limit,
            filters=filters,
            order_by=desc(Repository.created_at),
        )

    async def update_status(
        self,
        repo_id: uuid.UUID,
        status: str,
        error_message: str | None = None,
    ) -> Repository | None:
        """Update the ``index_status`` of a repository in one call.

        Args:
            repo_id: Target repository UUID.
            status: New status string (e.g. ``"complete"`` or ``"failed"``).
            error_message: Optional error detail to persist on failure.

        Returns:
            Updated Repository instance, or None if not found.
        """
        repo = await self.get_by_id(repo_id)
        if repo is None:
            return None
        updates: dict[str, Any] = {"index_status": status}
        if error_message is not None:
            updates["error_message"] = error_message
        return await self.update(repo, **updates)
