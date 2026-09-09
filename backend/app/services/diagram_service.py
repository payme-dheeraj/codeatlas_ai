"""Diagram service — async orchestrator for diagram generation and retrieval."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.diagram_repository import DiagramRepository
from app.schemas.diagram import (
    DiagramGenerationJobResponse,
    DiagramResponse,
    DiagramSummaryResponse,
    GenerateDiagramRequest,
)

logger = get_logger(__name__)


class DiagramService:
    """Async service for diagram generation, retrieval, and URL refresh.

    Attributes:
        _repo: Data access layer for diagram records.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = DiagramRepository(session)

    async def trigger_generation(
        self, request: GenerateDiagramRequest
    ) -> DiagramGenerationJobResponse:
        """Dispatch a Celery diagram generation task.

        Args:
            request: GenerateDiagramRequest with repo_id, types, options.

        Returns:
            DiagramGenerationJobResponse with task ID.
        """
        diagram_types = [t.value for t in request.diagram_types]

        from app.workers.tasks.diagram_tasks import generate_diagrams
        task = generate_diagrams.apply_async(
            kwargs={
                "repo_id": str(request.repo_id),
                "diagram_types": diagram_types,
                "diagram_format": request.diagram_format.value,
                "force_regenerate": request.force_regenerate,
                "options": request.options,
            }
        )

        logger.info("diagram_task_dispatched", task_id=task.id, repo_id=str(request.repo_id))
        return DiagramGenerationJobResponse(
            job_id=task.id,
            repo_id=request.repo_id,
            diagram_types=diagram_types,
            status="queued",
        )

    async def list_diagrams(self, repo_id: uuid.UUID) -> list[DiagramSummaryResponse]:
        """Return all latest-version diagram summaries for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            List of DiagramSummaryResponse.
        """
        diagrams = await self._repo.list_latest_for_repo(repo_id)
        return [DiagramSummaryResponse.model_validate(d) for d in diagrams]

    async def get_diagram(
        self, repo_id: uuid.UUID, diagram_type: str
    ) -> DiagramResponse | None:
        """Return the latest diagram of a given type for a repository.

        Args:
            repo_id: UUID of the repository.
            diagram_type: Diagram type slug.

        Returns:
            DiagramResponse or None.
        """
        diagram = await self._repo.get_latest(repo_id, diagram_type)
        if diagram is None:
            return None
        return DiagramResponse.model_validate(diagram)

    async def get_diagram_by_id(self, diagram_id: uuid.UUID) -> DiagramResponse | None:
        """Return a diagram by its UUID.

        Args:
            diagram_id: UUID of the diagram.

        Returns:
            DiagramResponse or None.
        """
        diagram = await self._repo.get_by_id(diagram_id)
        if diagram is None:
            return None
        return DiagramResponse.model_validate(diagram)

    async def get_source(
        self, repo_id: uuid.UUID, diagram_type: str
    ) -> tuple[str, str] | None:
        """Return the raw source code and diagram format for a diagram.

        Args:
            repo_id: UUID of the repository.
            diagram_type: Diagram type slug.

        Returns:
            Tuple of (source_code, diagram_format) or None.
        """
        diagram = await self._repo.get_latest(repo_id, diagram_type)
        if diagram is None:
            return None
        return diagram.source_code, diagram.diagram_format
