"""Findings aggregator — dedup, normalize, severity scoring, fingerprinting."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from typing import Any

from app.scanner.secrets import RawFinding


def fingerprint(finding: RawFinding) -> str:
    """Generate a deterministic SHA-256 fingerprint for deduplication.

    Two findings with the same rule, file, and line range produce the
    same fingerprint so re-scans don't create duplicate records.

    Args:
        finding: RawFinding instance.

    Returns:
        64-character hex SHA-256 digest.
    """
    key = f"{finding.rule_id}|{finding.file_path}|{finding.start_line}|{finding.end_line}"
    return hashlib.sha256(key.encode()).hexdigest()


def normalize(
    findings: list[RawFinding],
    scan_id: uuid.UUID,
    repo_id: uuid.UUID,
    scanner: str,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Convert raw findings to database-ready dicts with fingerprints.

    Deduplicates by fingerprint within the batch.

    Args:
        findings: List of RawFinding instances from a scanner module.
        scan_id: UUID of the parent SecurityScan.
        repo_id: UUID of the repository.
        scanner: Source scanner slug (secrets | sast | iac).
        language: Optional language label for all findings in this batch.

    Returns:
        Deduplicated list of finding dicts ready for bulk insert.
    """
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    for f in findings:
        fp = fingerprint(f)
        if fp in seen:
            continue
        seen.add(fp)

        rows.append(
            {
                "id": uuid.uuid4(),
                "scan_id": scan_id,
                "repo_id": repo_id,
                "scanner": scanner,
                "rule_id": f.rule_id,
                "title": f.title[:500],
                "description": f.description,
                "severity": f.severity,
                "cvss_score": f.cvss_score,
                "file_path": f.file_path,
                "start_line": f.start_line,
                "end_line": f.end_line,
                "snippet": f.snippet[:2000] if f.snippet else None,
                "category": f.category,
                "language": language,
                "fingerprint": fp,
                "remediation": None,
                "is_false_positive": False,
                "suppressed": False,
                "extra": f.extra,
            }
        )

    return rows


def severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Count findings by severity level.

    Args:
        findings: List of normalized finding dicts.

    Returns:
        Dict with keys: critical, high, medium, low, info, total.
    """
    counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }
    for f in findings:
        sev = f.get("severity", "info").lower()
        if sev in counts:
            counts[sev] += 1
    counts["total"] = sum(counts.values())
    return counts
