"""Security service — async orchestrator for scan lifecycle and reporting."""

from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.security_repository import SecurityRepository
from app.schemas.security import (
    FindingListResponse,
    FindingResponse,
    ScanDetailResponse,
    ScanRequest,
    ScanSummaryResponse,
)

logger = get_logger(__name__)


class SecurityService:
    """Async service for security scan management and report generation.

    Attributes:
        _repo: Data access layer for security records.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SecurityRepository(session)

    # ── Scan lifecycle ─────────────────────────────────────────────────────────

    async def trigger_scan(self, request: ScanRequest) -> ScanSummaryResponse:
        """Create a SecurityScan record and dispatch the Celery task.

        Args:
            request: ScanRequest payload with repo_id, types, options.

        Returns:
            ScanSummaryResponse with the new scan's details.
        """
        scan_types = [t.value for t in request.scan_types]
        scan = await self._repo.create_scan(request.repo_id, scan_types)

        from app.workers.tasks.security_tasks import run_security_scan
        run_security_scan.apply_async(
            kwargs={
                "scan_id": str(scan.id),
                "repo_id": str(request.repo_id),
                "scan_types": scan_types,
                "generate_remediation": request.generate_remediation,
            }
        )
        logger.info("scan_dispatched", scan_id=str(scan.id), repo_id=str(request.repo_id))
        return ScanSummaryResponse.model_validate(scan)

    async def get_scan(self, scan_id: uuid.UUID) -> ScanSummaryResponse | None:
        """Return the scan summary for a given scan UUID.

        Args:
            scan_id: UUID of the scan.

        Returns:
            ScanSummaryResponse or None if not found.
        """
        scan = await self._repo.get_scan(scan_id)
        if scan is None:
            return None
        return ScanSummaryResponse.model_validate(scan)

    async def list_scans(
        self,
        repo_id: uuid.UUID,
        *,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[ScanSummaryResponse], int]:
        """Return paginated scans for a repository.

        Args:
            repo_id: UUID of the repository.
            page: Page number (1-indexed).
            limit: Page size.

        Returns:
            Tuple of (scans_list, total_count).
        """
        offset = (page - 1) * limit
        scans, total = await self._repo.list_scans_for_repo(repo_id, limit=limit, offset=offset)
        return [ScanSummaryResponse.model_validate(s) for s in scans], total

    # ── Findings ───────────────────────────────────────────────────────────────

    async def list_findings(
        self,
        scan_id: uuid.UUID,
        *,
        severity: str | None = None,
        scanner: str | None = None,
        file_path: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> FindingListResponse:
        """Return paginated, filtered findings for a scan.

        Args:
            scan_id: UUID of the scan.
            severity: Optional severity filter.
            scanner: Optional scanner module filter.
            file_path: Optional file path filter.
            page: Page number.
            limit: Page size.

        Returns:
            FindingListResponse with paginated items.
        """
        offset = (page - 1) * limit
        findings, total = await self._repo.list_findings(
            scan_id,
            severity=severity,
            scanner=scanner,
            file_path=file_path,
            limit=limit,
            offset=offset,
        )
        return FindingListResponse(
            total=total,
            page=page,
            limit=limit,
            has_next=(offset + len(findings)) < total,
            items=[FindingResponse.model_validate(f) for f in findings],
        )

    async def suppress_finding(
        self,
        finding_id: uuid.UUID,
        *,
        is_false_positive: bool = False,
    ) -> bool:
        """Suppress or mark a finding as false positive.

        Args:
            finding_id: UUID of the finding.
            is_false_positive: If True, marks as FP.

        Returns:
            True if the finding was found and updated.
        """
        finding = await self._repo.get_finding(finding_id)
        if finding is None:
            return False
        await self._repo.suppress_finding(finding_id, is_false_positive=is_false_positive)
        return True

    # ── Report export ──────────────────────────────────────────────────────────

    async def export_report(
        self,
        scan_id: uuid.UUID,
        fmt: str = "json",
    ) -> tuple[str, str, str]:
        """Generate a security report in the requested format.

        Args:
            scan_id: UUID of the scan.
            fmt: Output format (json | sarif | csv | markdown).

        Returns:
            Tuple of (content_string, content_type, filename).
        """
        scan = await self._repo.get_scan(scan_id)
        if scan is None:
            return "", "application/json", "report.json"

        findings, _ = await self._repo.list_findings(scan_id, limit=5000, offset=0)

        if fmt == "sarif":
            content = self._to_sarif(scan, findings)
            return content, "application/json", f"scan_{scan_id}.sarif.json"
        elif fmt == "csv":
            content = self._to_csv(findings)
            return content, "text/csv", f"scan_{scan_id}.csv"
        elif fmt == "markdown":
            content = self._to_markdown(scan, findings)
            return content, "text/markdown", f"scan_{scan_id}.md"
        else:  # json
            content = self._to_json(scan, findings)
            return content, "application/json", f"scan_{scan_id}.json"

    # ── Private formatters ─────────────────────────────────────────────────────

    @staticmethod
    def _to_json(scan: Any, findings: list[Any]) -> str:
        data = {
            "scan_id": str(scan.id),
            "repo_id": str(scan.repo_id),
            "status": scan.status,
            "summary": {
                "total": scan.total_findings,
                "critical": scan.critical_count,
                "high": scan.high_count,
                "medium": scan.medium_count,
                "low": scan.low_count,
                "info": scan.info_count,
            },
            "findings": [
                {
                    "id": str(f.id),
                    "rule_id": f.rule_id,
                    "title": f.title,
                    "severity": f.severity,
                    "cvss_score": f.cvss_score,
                    "file_path": f.file_path,
                    "start_line": f.start_line,
                    "end_line": f.end_line,
                    "category": f.category,
                    "scanner": f.scanner,
                    "description": f.description,
                    "snippet": f.snippet,
                    "remediation": f.remediation,
                }
                for f in findings
                if not f.suppressed
            ],
        }
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def _to_sarif(scan: Any, findings: list[Any]) -> str:
        """Generate SARIF 2.1.0 format output.

        Args:
            scan: SecurityScan ORM instance.
            findings: List of SecurityFinding ORM instances.

        Returns:
            SARIF JSON string.
        """
        rules: dict[str, dict] = {}
        results: list[dict] = []

        for f in findings:
            if f.suppressed:
                continue
            if f.rule_id not in rules:
                rules[f.rule_id] = {
                    "id": f.rule_id,
                    "name": f.title,
                    "shortDescription": {"text": f.title},
                    "fullDescription": {"text": f.description},
                    "properties": {
                        "severity": f.severity,
                        "cvss_score": f.cvss_score,
                    },
                }
            sev_map = {
                "critical": "error",
                "high": "error",
                "medium": "warning",
                "low": "note",
                "info": "none",
            }
            results.append(
                {
                    "ruleId": f.rule_id,
                    "level": sev_map.get(f.severity, "warning"),
                    "message": {"text": f.description},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": f.file_path},
                                "region": {
                                    "startLine": f.start_line,
                                    "endLine": f.end_line,
                                },
                            }
                        }
                    ],
                }
            )

        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "CodeAtlas Security Scanner",
                            "version": "1.0.0",
                            "rules": list(rules.values()),
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(sarif, indent=2, default=str)

    @staticmethod
    def _to_csv(findings: list[Any]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "rule_id", "title", "severity", "cvss_score",
            "file_path", "start_line", "end_line", "category", "scanner",
        ])
        for f in findings:
            if not f.suppressed:
                writer.writerow([
                    str(f.id), f.rule_id, f.title, f.severity, f.cvss_score,
                    f.file_path, f.start_line, f.end_line, f.category, f.scanner,
                ])
        return buf.getvalue()

    @staticmethod
    def _to_markdown(scan: Any, findings: list[Any]) -> str:
        lines = [
            f"# Security Scan Report",
            f"",
            f"**Scan ID:** `{scan.id}`  ",
            f"**Repository:** `{scan.repo_id}`  ",
            f"**Status:** {scan.status}  ",
            f"",
            f"## Summary",
            f"",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| 🔴 Critical | {scan.critical_count} |",
            f"| 🟠 High | {scan.high_count} |",
            f"| 🟡 Medium | {scan.medium_count} |",
            f"| 🔵 Low | {scan.low_count} |",
            f"| ⚪ Info | {scan.info_count} |",
            f"| **Total** | **{scan.total_findings}** |",
            f"",
            f"## Findings",
            f"",
        ]
        for f in sorted(findings, key=lambda x: -x.cvss_score):
            if f.suppressed:
                continue
            lines += [
                f"### [{f.severity.upper()}] {f.title}",
                f"",
                f"- **Rule:** `{f.rule_id}`",
                f"- **File:** `{f.file_path}` (lines {f.start_line}–{f.end_line})",
                f"- **CVSS:** {f.cvss_score}",
                f"- **Scanner:** {f.scanner}",
                f"",
                f"{f.description}",
                f"",
            ]
            if f.snippet:
                lines += [f"```\n{f.snippet}\n```", ""]
        return "\n".join(lines)
