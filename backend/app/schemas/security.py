"""Pydantic v2 schemas for the Security Scanner feature."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ScanType(str, Enum):
    secrets = "secrets"
    sast = "sast"
    iac = "iac"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class ReportFormat(str, Enum):
    json = "json"
    sarif = "sarif"
    csv = "csv"
    markdown = "markdown"


# ── Request schemas ───────────────────────────────────────────────────────────


class ScanRequest(BaseModel):
    """Payload to trigger a security scan.

    Attributes:
        repo_id: UUID of the repository to scan.
        scan_types: List of scan modules to run (defaults to all three).
        generate_remediation: Whether to run the AI remediation generator.
    """

    repo_id: uuid.UUID
    scan_types: list[ScanType] = Field(
        default_factory=lambda: [ScanType.secrets, ScanType.sast, ScanType.iac]
    )
    generate_remediation: bool = True


class SuppressFindingRequest(BaseModel):
    """Mark a finding as suppressed (false positive or accepted risk).

    Attributes:
        reason: Human-readable reason for suppression.
    """

    reason: str = Field(min_length=5, max_length=500)


# ── Response schemas ──────────────────────────────────────────────────────────


class RemediationResponse(BaseModel):
    """AI-generated remediation for a finding.

    Attributes:
        vulnerability: Explanation of the vulnerability.
        fixed_code: Corrected code snippet.
        recommendations: Additional security guidance.
    """

    vulnerability: str
    fixed_code: str
    recommendations: list[str]


class FindingResponse(BaseModel):
    """A single security finding.

    Attributes:
        id: UUID of the finding record.
        scan_id: UUID of the parent scan.
        repo_id: UUID of the repository.
        scanner: Source module slug.
        rule_id: Rule identifier.
        title: Short title.
        description: Full description.
        severity: Severity level.
        cvss_score: CVSS numeric score.
        file_path: Affected file path.
        start_line: Start line.
        end_line: End line.
        snippet: Vulnerable code snippet.
        category: Semantic category.
        language: Programming language.
        fingerprint: Dedup hash.
        remediation: AI remediation dict, if generated.
        is_false_positive: Manual FP flag.
        suppressed: Suppressed flag.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    scan_id: uuid.UUID
    repo_id: uuid.UUID
    scanner: str
    rule_id: str
    title: str
    description: str
    severity: Severity
    cvss_score: float
    file_path: str
    start_line: int
    end_line: int
    snippet: str | None
    category: str
    language: str | None
    fingerprint: str
    remediation: dict[str, Any] | None
    is_false_positive: bool
    suppressed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanSummaryResponse(BaseModel):
    """High-level scan result summary.

    Attributes:
        id: UUID of the scan.
        repo_id: UUID of the repository.
        scan_types: Modules run.
        status: Current status.
        progress: Completion percentage.
        total_findings: Total finding count.
        critical_count: Critical count.
        high_count: High count.
        medium_count: Medium count.
        low_count: Low count.
        info_count: Info count.
        started_at: When the scan started.
        finished_at: When the scan finished.
        created_at: Record creation time.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    scan_types: list[str]
    status: str
    progress: int
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanDetailResponse(ScanSummaryResponse):
    """Full scan result including paginated findings.

    Attributes:
        findings: List of FindingResponse objects.
        total_findings_returned: Count of findings in this response.
    """

    findings: list[FindingResponse] = Field(default_factory=list)
    total_findings_returned: int = 0


class FindingListResponse(BaseModel):
    """Paginated list of findings.

    Attributes:
        total: Total matching findings.
        page: Current page number.
        limit: Page size.
        has_next: Whether more pages exist.
        items: List of FindingResponse.
    """

    total: int
    page: int
    limit: int
    has_next: bool
    items: list[FindingResponse]
