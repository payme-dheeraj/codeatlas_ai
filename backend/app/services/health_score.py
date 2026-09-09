"""Repository Health Score service.

Computes a composite 0-100 health score from four pillars:
  - Code Quality   (25 pts) — symbol coverage, docstring ratio
  - Security       (25 pts) — scan findings severity distribution
  - Documentation  (25 pts) — generated doc coverage
  - Activity       (25 pts) — recency of last index/scan

Each pillar is independently queryable; the composite combines them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.diagram import Diagram
from app.models.document import Document
from app.models.security_finding import SecurityFinding, SecurityScan
from app.models.symbol import ParsedSymbol

logger = get_logger(__name__)

_SEVERITY_DEDUCTIONS = {
    "critical": 10,
    "high": 5,
    "medium": 2,
    "low": 1,
    "info": 0,
}


class HealthScoreService:
    """Computes and returns repository health scores.

    Attributes:
        _session: Async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute(self, repo_id: uuid.UUID) -> dict[str, Any]:
        """Compute the full health score for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Dict with pillar scores, composite score, grade, and breakdown.
        """
        quality = await self._code_quality_score(repo_id)
        security = await self._security_score(repo_id)
        documentation = await self._documentation_score(repo_id)
        activity = await self._activity_score(repo_id)

        composite = (quality["score"] + security["score"] + documentation["score"] + activity["score"]) / 4
        composite = round(composite, 1)

        return {
            "repo_id": str(repo_id),
            "composite_score": composite,
            "grade": _grade(composite),
            "pillars": {
                "code_quality": quality,
                "security": security,
                "documentation": documentation,
                "activity": activity,
            },
            "computed_at": datetime.now(UTC).isoformat(),
        }

    async def _code_quality_score(self, repo_id: uuid.UUID) -> dict[str, Any]:
        """Score based on symbol count and docstring coverage.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Score dict with score (0-100), details.
        """
        total = await self._session.scalar(
            select(func.count(ParsedSymbol.id)).where(ParsedSymbol.repo_id == repo_id)
        ) or 0

        if total == 0:
            return {"score": 0, "details": "No symbols parsed yet."}

        with_docs = await self._session.scalar(
            select(func.count(ParsedSymbol.id)).where(
                ParsedSymbol.repo_id == repo_id,
                ParsedSymbol.docstring.isnot(None),
                ParsedSymbol.docstring != "",
            )
        ) or 0

        docstring_ratio = with_docs / total
        score = min(100.0, 40 + docstring_ratio * 60)

        return {
            "score": round(score, 1),
            "details": {
                "total_symbols": total,
                "documented_symbols": with_docs,
                "docstring_coverage_pct": round(docstring_ratio * 100, 1),
            },
        }

    async def _security_score(self, repo_id: uuid.UUID) -> dict[str, Any]:
        """Score based on open security findings severity.

        Starts at 100 and deducts for each unresolved finding by severity.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Score dict.
        """
        latest_scan = await self._session.scalar(
            select(SecurityScan.id)
            .where(SecurityScan.repo_id == repo_id, SecurityScan.status == "complete")
            .order_by(SecurityScan.created_at.desc())
            .limit(1)
        )

        if not latest_scan:
            return {"score": 50.0, "details": "No completed scan found. Score is neutral."}

        rows = await self._session.execute(
            select(SecurityFinding.severity, func.count(SecurityFinding.id))
            .where(
                SecurityFinding.scan_id == latest_scan,
                SecurityFinding.is_suppressed.is_(False),
            )
            .group_by(SecurityFinding.severity)
        )
        severity_counts = dict(rows.all())

        deduction = 0
        for sev, deduct in _SEVERITY_DEDUCTIONS.items():
            deduction += severity_counts.get(sev, 0) * deduct

        score = max(0.0, 100.0 - deduction)
        return {
            "score": round(score, 1),
            "details": {
                "finding_counts": severity_counts,
                "total_deduction": deduction,
            },
        }

    async def _documentation_score(self, repo_id: uuid.UUID) -> dict[str, Any]:
        """Score based on how many doc types have been generated.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Score dict.
        """
        _KEY_DOC_TYPES = {"readme", "api_reference", "wiki", "deployment_guide"}

        generated = await self._session.execute(
            select(Document.doc_type)
            .where(Document.repo_id == repo_id, Document.is_latest.is_(True))
        )
        generated_types = {row[0] for row in generated.all()}

        covered = len(generated_types & _KEY_DOC_TYPES)
        score = (covered / len(_KEY_DOC_TYPES)) * 100

        return {
            "score": round(score, 1),
            "details": {
                "generated_doc_types": sorted(generated_types),
                "key_types_covered": covered,
                "key_types_total": len(_KEY_DOC_TYPES),
            },
        }

    async def _activity_score(self, repo_id: uuid.UUID) -> dict[str, Any]:
        """Score based on recency of last index + scan.

        Full score (100) if indexed within 7 days.
        Decays linearly to 0 at 90 days.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Score dict.
        """
        from app.models.index_job import IndexJob

        last_index = await self._session.scalar(
            select(func.max(IndexJob.updated_at))
            .where(IndexJob.repo_id == repo_id, IndexJob.status == "complete")
        )

        if not last_index:
            return {"score": 0.0, "details": "Repository has never been indexed."}

        now = datetime.now(UTC)
        last_index = last_index.replace(tzinfo=UTC) if last_index.tzinfo is None else last_index
        age_days = (now - last_index).days
        score = max(0.0, 100.0 - (age_days / 90.0) * 100.0)

        return {
            "score": round(score, 1),
            "details": {
                "last_indexed_at": last_index.isoformat(),
                "age_days": age_days,
            },
        }


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"
