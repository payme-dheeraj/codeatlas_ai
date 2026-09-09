"""PR/MR analysis endpoints.

Routes:
  POST /repos/{repo_id}/pr-review   — submit a diff for AI code review
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.rbac import require_permission
from app.models.role import PERM_PR_ANALYZE
from app.services.pr_analysis import analyze_pr

router = APIRouter(tags=["pr-review"])


class PrReviewRequest(BaseModel):
    """Payload for PR/MR AI review.

    Attributes:
        diff: Unified diff string (from git diff or GitHub API).
        pr_title: Pull request title.
        pr_description: Pull request body.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.
    """

    diff: str = Field(..., description="Unified diff string")
    pr_title: str = Field(default="Untitled PR")
    pr_description: str = Field(default="")
    llm_provider: str | None = None
    llm_model: str | None = None


@router.post(
    "/repos/{repo_id}/pr-review",
    summary="Run AI code review on a pull request diff",
    description=(
        "Submits a unified diff to the AI for a structured code review. "
        "Returns a verdict (APPROVE | REQUEST_CHANGES | COMMENT), "
        "a list of issues with severity and line references, "
        "and a positive aspects summary."
    ),
    dependencies=[Depends(require_permission(PERM_PR_ANALYZE))],
)
async def review_pr(
    repo_id: uuid.UUID,
    request: PrReviewRequest,
    actor: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run AI review on a PR diff.

    Args:
        repo_id: UUID of the repository (used for context lookup).
        request: PR review request payload.
        actor: Authenticated user UUID.
        session: Async DB session.

    Returns:
        PR review result dict with verdict, issues, and raw_review.
    """
    from sqlalchemy import select
    from app.models.repository import Repository

    result = await session.execute(select(Repository.name).where(Repository.id == repo_id))
    repo_name = result.scalar_one_or_none() or str(repo_id)

    review = await analyze_pr(
        request.diff,
        repo_name=repo_name,
        pr_title=request.pr_title,
        pr_description=request.pr_description,
        llm_provider=request.llm_provider,
        llm_model=request.llm_model,
    )

    # Fire audit log (fire-and-forget)
    from app.repositories.audit_repository import AuditRepository
    audit = AuditRepository(session)
    await audit.log(
        "pr.analyze",
        user_id=actor,
        repo_id=repo_id,
        resource_type="pr_review",
        request_data={"pr_title": request.pr_title},
        response_summary=f"verdict={review['verdict']} issues={review['issues_count']}",
    )

    return review
