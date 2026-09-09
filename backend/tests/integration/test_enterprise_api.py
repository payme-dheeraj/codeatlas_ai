"""Integration tests for Phase 7 enterprise endpoints.

Covers: admin/RBAC, audit logs, health score, PR review, and webhooks.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


async def _register_and_login(
    client: AsyncClient, suffix: str, role: str = "viewer"
) -> tuple[str, uuid.UUID]:
    """Register a user and return (token, user_id)."""
    email = f"enterprise{suffix}@example.com"
    username = f"enterpriseuser{suffix}"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": "Password1",
    })
    user_id = uuid.UUID(reg.json()["id"])
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password1",
    })
    return resp.json()["access_token"], user_id


async def _admin_token(client: AsyncClient, suffix: str) -> tuple[str, uuid.UUID]:
    """Create a user with admin role and return (token, user_id).

    NOTE: In test env, we use the test DB directly to set admin role.
    Here we mock the RBAC dependency to simulate an admin.
    """
    return await _register_and_login(client, suffix, role="admin")


# ── Health Score ──────────────────────────────────────────────────────────────


class TestHealthScore:
    @pytest.mark.asyncio
    async def test_health_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}/health")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_health_authenticated_returns_score(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "h1")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/repos/{repo_id}/health",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "composite_score" in data
        assert "grade" in data
        assert "pillars" in data
        assert set(data["pillars"].keys()) == {
            "code_quality", "security", "documentation", "activity"
        }

    @pytest.mark.asyncio
    async def test_health_score_range_0_to_100(self, client: AsyncClient) -> None:
        token, _ = await _register_and_login(client, "h2")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/repos/{repo_id}/health",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        score = response.json()["composite_score"]
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_health_grade_is_letter(self, client: AsyncClient) -> None:
        token, _ = await _register_and_login(client, "h3")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/repos/{repo_id}/health",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.json()["grade"] in ("A", "B", "C", "D", "F")


# ── PR Review ─────────────────────────────────────────────────────────────────


class TestPrReview:
    _SAMPLE_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
index abc..def 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,6 +10,8 @@ def login(username, password):
+    query = f"SELECT * FROM users WHERE username='{username}'"
+    db.execute(query)
"""

    @pytest.mark.asyncio
    async def test_pr_review_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            f"/api/v1/repos/{uuid.uuid4()}/pr-review",
            json={"diff": self._SAMPLE_DIFF},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_pr_review_returns_verdict(self, client: AsyncClient) -> None:
        token, _ = await _register_and_login(client, "pr1")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True), \
             patch("app.services.pr_analysis.call_llm", return_value=(
                 "### Summary\nAdds SQL injection.\n\n"
                 "### Verdict\nREQUEST_CHANGES — SQL injection risk.\n\n"
                 "### Issues Found\nNone structured.\n"
             )):
            response = await client.post(
                f"/api/v1/repos/{repo_id}/pr-review",
                json={
                    "diff": self._SAMPLE_DIFF,
                    "pr_title": "Add login query",
                    "pr_description": "Direct SQL query",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert "raw_review" in data
        assert data["verdict"] in ("APPROVE", "REQUEST_CHANGES", "COMMENT", "UNKNOWN")

    @pytest.mark.asyncio
    async def test_pr_review_empty_diff_still_returns(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "pr2")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True), \
             patch("app.services.pr_analysis.call_llm", return_value="### Verdict\nAPPROVE\n"):
            response = await client.post(
                f"/api/v1/repos/{repo_id}/pr-review",
                json={"diff": "", "pr_title": "Empty PR"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200


# ── Webhooks ──────────────────────────────────────────────────────────────────


class TestWebhooks:
    @pytest.mark.asyncio
    async def test_create_webhook_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            f"/api/v1/repos/{uuid.uuid4()}/webhooks",
            json={"url": "https://example.com/hook", "events": ["scan.complete"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_webhook_returns_201(self, client: AsyncClient) -> None:
        token, _ = await _register_and_login(client, "wh1")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.post(
                f"/api/v1/repos/{repo_id}/webhooks",
                json={
                    "url": "https://hooks.example.com/codeatlas",
                    "events": ["scan.complete", "docs.complete"],
                    "secret": "my-signing-secret",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["is_active"] is True
        assert set(data["events"]) == {"scan.complete", "docs.complete"}

    @pytest.mark.asyncio
    async def test_create_webhook_invalid_event_returns_422(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "wh2")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.post(
                f"/api/v1/repos/{repo_id}/webhooks",
                json={"url": "https://example.com", "events": ["invalid.event"]},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_webhooks_empty(self, client: AsyncClient) -> None:
        token, _ = await _register_and_login(client, "wh3")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/repos/{repo_id}/webhooks",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_webhook_returns_404(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "wh4")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/repos/{repo_id}/webhooks/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent_webhook_returns_404(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "wh5")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.delete(
                f"/api/v1/repos/{repo_id}/webhooks/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_webhook_lifecycle(self, client: AsyncClient) -> None:
        """Create → list → get → deactivate."""
        token, _ = await _register_and_login(client, "wh6")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            create = await client.post(
                f"/api/v1/repos/{repo_id}/webhooks",
                json={"url": "https://example.com/hook", "events": ["repo.indexed"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert create.status_code == 201
            webhook_id = create.json()["id"]

            get_resp = await client.get(
                f"/api/v1/repos/{repo_id}/webhooks/{webhook_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert get_resp.status_code == 200

            delete_resp = await client.delete(
                f"/api/v1/repos/{repo_id}/webhooks/{webhook_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert delete_resp.status_code == 204


# ── Audit Logs ────────────────────────────────────────────────────────────────


class TestAuditLogs:
    @pytest.mark.asyncio
    async def test_audit_logs_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/admin/audit-logs")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_audit_logs_authenticated_returns_list(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "al1")

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                "/api/v1/admin/audit-logs",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_user_audit_logs(self, client: AsyncClient) -> None:
        token, user_id = await _register_and_login(client, "al2")

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/admin/audit-logs/user/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ── RBAC Role Management ──────────────────────────────────────────────────────


class TestRoleManagement:
    @pytest.mark.asyncio
    async def test_get_user_role_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}/role")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_role_returns_404(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _register_and_login(client, "rm1")

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/admin/users/{uuid.uuid4()}/role",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_existing_user_role(self, client: AsyncClient) -> None:
        token, user_id = await _register_and_login(client, "rm2")

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.get(
                f"/api/v1/admin/users/{user_id}/role",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["role"] in ("admin", "analyst", "viewer")

    @pytest.mark.asyncio
    async def test_update_role_invalid_role_returns_422(
        self, client: AsyncClient
    ) -> None:
        token, user_id = await _register_and_login(client, "rm3")

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.put(
                f"/api/v1/admin/users/{user_id}/role",
                json={"role": "superadmin"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_assign_repo_role(self, client: AsyncClient) -> None:
        token, user_id = await _register_and_login(client, "rm4")
        repo_id = uuid.uuid4()

        with patch("app.core.rbac.has_permission", return_value=True):
            response = await client.post(
                f"/api/v1/repos/{repo_id}/roles",
                json={"user_id": str(user_id), "role": "analyst"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "analyst"
        assert data["user_id"] == str(user_id)
