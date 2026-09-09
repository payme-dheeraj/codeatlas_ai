"""Repository pattern implementation for the IndexJob model."""

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.index_job import IndexJob
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[IndexJob]):
    """Data access layer for the ``index_jobs`` table.

    Extends BaseRepository with job-specific query helpers.

    Attributes:
        model: Bound to the IndexJob ORM model.
    """

    model = IndexJob

    async def get_latest_for_repo(self, repo_id: uuid.UUID) -> IndexJob | None:
        """Return the most recently created job for a given repository.

        Args:
            repo_id: UUID of the parent repository.

        Returns:
            The most recent IndexJob, or None if no jobs exist.
        """
        result = await self._session.execute(
            select(IndexJob)
            .where(IndexJob.repo_id == repo_id)
            .order_by(desc(IndexJob.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_job_for_repo(self, repo_id: uuid.UUID) -> IndexJob | None:
        """Return a running or queued job for a repository, if one exists.

        Used to prevent duplicate indexing runs from being dispatched.

        Args:
            repo_id: UUID of the parent repository.

        Returns:
            An active IndexJob, or None if the repo is idle.
        """
        result = await self._session.execute(
            select(IndexJob)
            .where(
                IndexJob.repo_id == repo_id,
                IndexJob.status.in_(["queued", "running"]),
            )
            .order_by(desc(IndexJob.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_repo(
        self,
        repo_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> tuple[list[IndexJob], int]:
        """Return paginated job history for a repository.

        Args:
            repo_id: UUID of the parent repository.
            offset: Records to skip.
            limit: Maximum records to return.

        Returns:
            Tuple of (jobs, total_count).
        """
        return await self.list(
            offset=offset,
            limit=limit,
            filters=[IndexJob.repo_id == repo_id],
            order_by=desc(IndexJob.created_at),
        )

    async def update_progress(
        self,
        job_id: uuid.UUID,
        *,
        progress: int,
        current_stage: str | None = None,
        status: str | None = None,
    ) -> IndexJob | None:
        """Update progress fields on a running job.

        Args:
            job_id: UUID of the job to update.
            progress: New progress value (0-100).
            current_stage: Optional human-readable stage label.
            status: Optional new status value.

        Returns:
            Updated IndexJob, or None if not found.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return None
        updates: dict = {"progress": progress}
        if current_stage is not None:
            updates["current_stage"] = current_stage
        if status is not None:
            updates["status"] = status
        return await self.update(job, **updates)
