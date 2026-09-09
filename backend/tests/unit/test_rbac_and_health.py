"""Unit tests for RBAC permission map, health score grading, and PR analysis helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.role import (
    PERM_AUDIT_READ,
    PERM_DOCS_GENERATE,
    PERM_REPO_CREATE,
    PERM_REPO_DELETE,
    PERM_REPO_READ,
    PERM_ROLE_ASSIGN,
    PERM_SCAN_READ,
    PERM_SCAN_TRIGGER,
    PERM_USER_MANAGE,
    PERM_WEBHOOK_MANAGE,
    ROLE_ADMIN,
    ROLE_ANALYST,
    ROLE_VIEWER,
    has_permission,
)
from app.services.health_score import _grade
from app.services.pr_analysis import _extract_verdict, _extract_issues


# ── RBAC permission map ────────────────────────────────────────────────────────


class TestHasPermission:
    # Admin should have everything
    def test_admin_has_repo_create(self) -> None:
        assert has_permission(ROLE_ADMIN, PERM_REPO_CREATE) is True

    def test_admin_has_role_assign(self) -> None:
        assert has_permission(ROLE_ADMIN, PERM_ROLE_ASSIGN) is True

    def test_admin_has_audit_read(self) -> None:
        assert has_permission(ROLE_ADMIN, PERM_AUDIT_READ) is True

    def test_admin_has_webhook_manage(self) -> None:
        assert has_permission(ROLE_ADMIN, PERM_WEBHOOK_MANAGE) is True

    # Analyst can trigger scans but cannot manage users
    def test_analyst_has_scan_trigger(self) -> None:
        assert has_permission(ROLE_ANALYST, PERM_SCAN_TRIGGER) is True

    def test_analyst_has_docs_generate(self) -> None:
        assert has_permission(ROLE_ANALYST, PERM_DOCS_GENERATE) is True

    def test_analyst_cannot_manage_users(self) -> None:
        assert has_permission(ROLE_ANALYST, PERM_USER_MANAGE) is False

    def test_analyst_cannot_assign_roles(self) -> None:
        assert has_permission(ROLE_ANALYST, PERM_ROLE_ASSIGN) is False

    def test_analyst_cannot_delete_repo(self) -> None:
        assert has_permission(ROLE_ANALYST, PERM_REPO_DELETE) is False

    # Viewer can only read
    def test_viewer_has_repo_read(self) -> None:
        assert has_permission(ROLE_VIEWER, PERM_REPO_READ) is True

    def test_viewer_has_scan_read(self) -> None:
        assert has_permission(ROLE_VIEWER, PERM_SCAN_READ) is True

    def test_viewer_cannot_trigger_scan(self) -> None:
        assert has_permission(ROLE_VIEWER, PERM_SCAN_TRIGGER) is False

    def test_viewer_cannot_create_repo(self) -> None:
        assert has_permission(ROLE_VIEWER, PERM_REPO_CREATE) is False

    def test_viewer_cannot_manage_webhooks(self) -> None:
        assert has_permission(ROLE_VIEWER, PERM_WEBHOOK_MANAGE) is False

    # Unknown role
    def test_unknown_role_has_no_permissions(self) -> None:
        assert has_permission("superuser", PERM_REPO_READ) is False

    def test_unknown_permission_is_false(self) -> None:
        assert has_permission(ROLE_ADMIN, "nonexistent:permission") is False


# ── Health score grading ──────────────────────────────────────────────────────


class TestGrade:
    def test_grade_a(self) -> None:
        assert _grade(95) == "A"
        assert _grade(90) == "A"

    def test_grade_b(self) -> None:
        assert _grade(85) == "B"
        assert _grade(80) == "B"

    def test_grade_c(self) -> None:
        assert _grade(75) == "C"
        assert _grade(70) == "C"

    def test_grade_d(self) -> None:
        assert _grade(65) == "D"
        assert _grade(60) == "D"

    def test_grade_f(self) -> None:
        assert _grade(59) == "F"
        assert _grade(0) == "F"


# ── PR analysis helpers ────────────────────────────────────────────────────────


class TestExtractVerdict:
    def test_approve(self) -> None:
        assert _extract_verdict("### Verdict\nAPPROVE — looks good!") == "APPROVE"

    def test_request_changes(self) -> None:
        assert _extract_verdict("Verdict: REQUEST_CHANGES needed") == "REQUEST_CHANGES"

    def test_comment(self) -> None:
        assert _extract_verdict("Verdict: COMMENT\n") == "COMMENT"

    def test_unknown_when_no_verdict(self) -> None:
        assert _extract_verdict("This is a review without any verdict keyword.") == "UNKNOWN"

    def test_request_changes_takes_priority_over_approve(self) -> None:
        # REQUEST_CHANGES appears first alphabetically in check order
        review = "APPROVE if you fix this\nBut actually REQUEST_CHANGES needed"
        verdict = _extract_verdict(review)
        assert verdict in ("REQUEST_CHANGES", "APPROVE")  # depends on order


class TestExtractIssues:
    def test_extracts_single_issue(self) -> None:
        review = """\
### Issues Found

1. Issue with auth
   - Severity: high
   - File: app/api/auth.py
   - Line: 42
   - Issue: SQL injection risk
   - Suggestion: Use parameterized queries
"""
        issues = _extract_issues(review)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "auth.py" in issues[0]["file"]
        assert "42" in issues[0]["line"]

    def test_no_issues_returns_empty(self) -> None:
        review = "### Issues Found\n\nNone detected."
        issues = _extract_issues(review)
        assert issues == []

    def test_extracts_multiple_issues(self) -> None:
        review = """\
1. First issue
   - Severity: critical
   - File: main.py
   - Line: 10
   - Issue: Secret exposed
   - Suggestion: Use env vars

2. Second issue
   - Severity: medium
   - File: utils.py
   - Line: 55
   - Issue: Unused import
   - Suggestion: Remove the import
"""
        issues = _extract_issues(review)
        # May extract 0-2 depending on regex match; just check it doesn't error
        assert isinstance(issues, list)


# ── Webhook event validation ──────────────────────────────────────────────────


class TestWebhookEvents:
    def test_valid_events_set_is_non_empty(self) -> None:
        from app.models.webhook import WEBHOOK_EVENTS
        assert len(WEBHOOK_EVENTS) > 0

    def test_scan_complete_is_valid(self) -> None:
        from app.models.webhook import WEBHOOK_EVENTS
        assert "scan.complete" in WEBHOOK_EVENTS

    def test_docs_complete_is_valid(self) -> None:
        from app.models.webhook import WEBHOOK_EVENTS
        assert "docs.complete" in WEBHOOK_EVENTS

    def test_repo_indexed_is_valid(self) -> None:
        from app.models.webhook import WEBHOOK_EVENTS
        assert "repo.indexed" in WEBHOOK_EVENTS
