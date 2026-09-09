"""Data access layer for SecurityScan and SecurityFinding models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_finding import SecurityFinding, SecurityScan


class SecurityRepository:
    """Repository for security scan and finding records.

    Attributes:
        _session: Active async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Scans ─────────────────────────────────────────────────────────────────

    async def create_scan(
        self,
        repo_id: uuid.UUID,
        scan_types: list[str],
    ) -> SecurityScan:
        """Create a new SecurityScan record in queued state.

        Args:
            repo_id: UUID of the repository.
            scan_types: List of scan module slugs to run.

        Returns:
            Persisted SecurityScan instance.
        """
        scan = SecurityScan(
            repo_id=repo_id,
            scan_types=scan_types,
            status="queued",
            progress=0,
        )
        self._session.add(scan)
        await self._session.commit()
        await self._session.refresh(scan)
        return scan

    async def get_scan(self, scan_id: uuid.UUID) -> SecurityScan | None:
        """Fetch a SecurityScan by primary key.

        Args:
            scan_id: UUID of the scan.

        Returns:
            SecurityScan or None.
        """
        result = await self._session.execute(
            select(SecurityScan).where(SecurityScan.id == scan_id)
        )
        return result.scalar_one_or_none()

    async def list_scans_for_repo(
        self, repo_id: uuid.UUID, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[SecurityScan], int]:
        """Return paginated scans for a repository, newest first.

        Args:
            repo_id: UUID of the repository.
            limit: Page size.
            offset: Row offset.

        Returns:
            Tuple of (scans_list, total_count).
        """
        base = select(SecurityScan).where(SecurityScan.repo_id == repo_id)
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self._session.execute(
            base.order_by(SecurityScan.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total or 0

    async def update_scan(self, scan_id: uuid.UUID, **fields: Any) -> None:
        """Partially update a SecurityScan record.

        Args:
            scan_id: UUID of the scan to update.
            **fields: Column names and new values.
        """
        await self._session.execute(
            update(SecurityScan)
            .where(SecurityScan.id == scan_id)
            .values(**fields)
        )
        await self._session.commit()

    # ── Findings ──────────────────────────────────────────────────────────────

    async def bulk_insert_findings(
        self, findings: list[dict[str, Any]]
    ) -> int:
        """Bulk insert security findings, ignoring duplicates by fingerprint.

        Args:
            findings: List of finding attribute dicts.

        Returns:
            Number of rows inserted.
        """
        if not findings:
            return 0

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(SecurityFinding).values(findings)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_finding_scan_fingerprint"
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount or 0

    async def list_findings(
        self,
        scan_id: uuid.UUID,
        *,
        severity: str | None = None,
        scanner: str | None = None,
        file_path: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SecurityFinding], int]:
        """Return paginated findings for a scan with optional filters.

        Args:
            scan_id: UUID of the parent scan.
            severity: Optional severity filter.
            scanner: Optional scanner slug filter.
            file_path: Optional file path filter.
            limit: Page size.
            offset: Row offset.

        Returns:
            Tuple of (findings_list, total_count).
        """
        base = select(SecurityFinding).where(SecurityFinding.scan_id == scan_id)
        if severity:
            base = base.where(SecurityFinding.severity == severity)
        if scanner:
            base = base.where(SecurityFinding.scanner == scanner)
        if file_path:
            base = base.where(SecurityFinding.file_path == file_path)

        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self._session.execute(
            base.order_by(SecurityFinding.cvss_score.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total or 0

    async def list_findings_for_repo(
        self,
        repo_id: uuid.UUID,
        *,
        severity: str | None = None,
        scanner: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SecurityFinding], int]:
        """Return paginated findings across all scans of a repository.

        Args:
            repo_id: UUID of the repository.
            severity: Optional severity filter.
            scanner: Optional scanner filter.
            limit: Page size.
            offset: Row offset.

        Returns:
            Tuple of (findings_list, total_count).
        """
        base = select(SecurityFinding).where(SecurityFinding.repo_id == repo_id)
        if severity:
            base = base.where(SecurityFinding.severity == severity)
        if scanner:
            base = base.where(SecurityFinding.scanner == scanner)

        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self._session.execute(
            base.order_by(SecurityFinding.cvss_score.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total or 0

    async def get_finding(self, finding_id: uuid.UUID) -> SecurityFinding | None:
        """Fetch a single SecurityFinding by primary key.

        Args:
            finding_id: UUID of the finding.

        Returns:
            SecurityFinding or None.
        """
        result = await self._session.execute(
            select(SecurityFinding).where(SecurityFinding.id == finding_id)
        )
        return result.scalar_one_or_none()

    async def suppress_finding(
        self, finding_id: uuid.UUID, *, is_false_positive: bool = False
    ) -> None:
        """Mark a finding as suppressed or false positive.

        Args:
            finding_id: UUID of the finding.
            is_false_positive: If True, marks as FP; otherwise plain suppressed.
        """
        await self._session.execute(
            update(SecurityFinding)
            .where(SecurityFinding.id == finding_id)
            .values(suppressed=True, is_false_positive=is_false_positive)
        )
        await self._session.commit()

    async def set_remediation(
        self, finding_id: uuid.UUID, remediation: dict[str, Any]
    ) -> None:
        """Attach AI-generated remediation to a finding.

        Args:
            finding_id: UUID of the finding.
            remediation: Dict with vulnerability, fixed_code, recommendations.
        """
        await self._session.execute(
            update(SecurityFinding)
            .where(SecurityFinding.id == finding_id)
            .values(remediation=remediation)
        )
        await self._session.commit()
