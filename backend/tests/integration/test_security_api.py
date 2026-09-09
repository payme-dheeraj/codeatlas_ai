"""Integration tests for /api/v1/security endpoints.

Uses the real FastAPI test client with DB/Redis container overrides.
Celery tasks are mocked to avoid external infrastructure.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


async def _get_token(client: AsyncClient, suffix: str = "") -> str:
    email = f"security{suffix}@example.com"
    username = f"securityuser{suffix}"
    await client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": "Password1",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password1",
    })
    return resp.json()["access_token"]


class TestTriggerScan:
    @pytest.mark.asyncio
    async def test_trigger_scan_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/security/scans",
            json={"repo_id": str(uuid.uuid4()), "scan_types": ["secrets"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_trigger_scan_returns_202(self, client: AsyncClient) -> None:
        token = await _get_token(client, "1")
        repo_id = str(uuid.uuid4())

        with patch(
            "app.workers.tasks.security_tasks.run_security_scan.apply_async"
        ):
            response = await client.post(
                "/api/v1/security/scans",
                json={
                    "repo_id": repo_id,
                    "scan_types": ["secrets", "sast", "iac"],
                    "generate_remediation": False,
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["status"] == "queued"
        assert data["repo_id"] == repo_id

    @pytest.mark.asyncio
    async def test_trigger_scan_invalid_scan_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "2")
        response = await client.post(
            "/api/v1/security/scans",
            json={"repo_id": str(uuid.uuid4()), "scan_types": ["invalid_type"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422


class TestGetScan:
    @pytest.mark.asyncio
    async def test_get_nonexistent_scan_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "3")
        response = await client.get(
            f"/api/v1/security/scans/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_scan_returns_correct_data(self, client: AsyncClient) -> None:
        token = await _get_token(client, "4")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.security_tasks.run_security_scan.apply_async"):
            create_resp = await client.post(
                "/api/v1/security/scans",
                json={"repo_id": repo_id, "scan_types": ["secrets"], "generate_remediation": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        scan_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/security/scans/{scan_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == scan_id
        assert data["repo_id"] == repo_id
        assert data["status"] == "queued"


class TestListScans:
    @pytest.mark.asyncio
    async def test_list_scans_empty_repo(self, client: AsyncClient) -> None:
        token = await _get_token(client, "5")
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/scans",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_scans_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}/scans")
        assert response.status_code == 401


class TestListFindings:
    @pytest.mark.asyncio
    async def test_list_findings_for_scan(self, client: AsyncClient) -> None:
        token = await _get_token(client, "6")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.security_tasks.run_security_scan.apply_async"):
            create_resp = await client.post(
                "/api/v1/security/scans",
                json={"repo_id": repo_id, "scan_types": ["secrets"], "generate_remediation": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        scan_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/security/scans/{scan_id}/findings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_findings_with_severity_filter(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "7")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.security_tasks.run_security_scan.apply_async"):
            create_resp = await client.post(
                "/api/v1/security/scans",
                json={"repo_id": repo_id, "scan_types": ["sast"], "generate_remediation": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        scan_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/security/scans/{scan_id}/findings?severity=critical",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestSuppressFinding:
    @pytest.mark.asyncio
    async def test_suppress_nonexistent_finding_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "8")
        response = await client.post(
            f"/api/v1/security/findings/{uuid.uuid4()}/suppress",
            json={"reason": "Known false positive from test fixture"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_suppress_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            f"/api/v1/security/findings/{uuid.uuid4()}/suppress",
            json={"reason": "False positive"},
        )
        assert response.status_code == 401


class TestExportReport:
    @pytest.mark.asyncio
    async def test_export_nonexistent_scan_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "9")
        response = await client.get(
            f"/api/v1/security/scans/{uuid.uuid4()}/report?format=json",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_sarif_format(self, client: AsyncClient) -> None:
        token = await _get_token(client, "10")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.security_tasks.run_security_scan.apply_async"):
            create_resp = await client.post(
                "/api/v1/security/scans",
                json={"repo_id": repo_id, "scan_types": ["secrets"], "generate_remediation": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        scan_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/security/scans/{scan_id}/report?format=sarif",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert data["version"] == "2.1.0"
        assert "runs" in data

    @pytest.mark.asyncio
    async def test_export_csv_format(self, client: AsyncClient) -> None:
        token = await _get_token(client, "11")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.security_tasks.run_security_scan.apply_async"):
            create_resp = await client.post(
                "/api/v1/security/scans",
                json={"repo_id": repo_id, "scan_types": ["iac"], "generate_remediation": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        scan_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/security/scans/{scan_id}/report?format=csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_markdown_format(self, client: AsyncClient) -> None:
        token = await _get_token(client, "12")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.security_tasks.run_security_scan.apply_async"):
            create_resp = await client.post(
                "/api/v1/security/scans",
                json={"repo_id": repo_id, "scan_types": ["secrets"], "generate_remediation": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        scan_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/security/scans/{scan_id}/report?format=markdown",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "# Security Scan Report" in response.text
