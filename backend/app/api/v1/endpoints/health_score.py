"""Repository health score endpoints.

Routes:
  GET /repos/{repo_id}/health    — compute and return health score
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_optional_current_user_id as get_current_user_id, get_db
from app.services.health_score import HealthScoreService

router = APIRouter(tags=["health"])


@router.get(
    "/repos/{repo_id}/health",
    summary="Compute repository health score",
    description=(
        "Returns a composite 0-100 health score with four pillars: "
        "Code Quality, Security, Documentation, and Activity. "
        "Each pillar contributes 25 points to the composite."
    ),
)
async def get_health_score(
    repo_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Compute the health score for a repository.

    Args:
        repo_id: UUID of the repository.
        _: Authenticated user UUID.
        session: Async DB session.

    Returns:
        Health score dict with composite, grade, and pillar breakdown.
    """
    service = HealthScoreService(session)
    return await service.compute(repo_id)
