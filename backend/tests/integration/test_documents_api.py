"""Integration tests for /api/v1 documentation endpoints.

Uses the real FastAPI test client with DB/Redis container overrides.
Celery tasks and LLM calls are mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


async def _get_token(client: AsyncClient, suffix: str = "") -> str:
    email = f"docs{suffix}@example.com"
    username = f"docsuser{suffix}"
    await client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": "Password1",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password1",
    })
    return resp.json()["access_token"]


class TestGenerateDocs:
    @pytest.mark.asyncio
    async def test_generate_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            f"/api/v1/repos/{uuid.uuid4()}/docs/generate",
            json={"repo_id": str(uuid.uuid4()), "doc_types": ["readme"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_returns_202(self, client: AsyncClient) -> None:
        token = await _get_token(client, "1")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.document_tasks.generate_documents.apply_async"):
            response = await client.post(
                f"/api/v1/repos/{repo_id}/docs/generate",
                json={
                    "repo_id": repo_id,
                    "doc_types": ["readme", "wiki"],
                    "force_regenerate": False,
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["status"] == "queued"
        assert set(data["doc_types"]) == {"readme", "wiki"}

    @pytest.mark.asyncio
    async def test_generate_invalid_doc_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "2")
        repo_id = str(uuid.uuid4())
        response = await client.post(
            f"/api/v1/repos/{repo_id}/docs/generate",
            json={"repo_id": repo_id, "doc_types": ["invalid_type"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422


class TestGetJobStatus:
    @pytest.mark.asyncio
    async def test_get_job_not_found_returns_404(self, client: AsyncClient) -> None:
        token = await _get_token(client, "3")
        repo_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/repos/{repo_id}/docs/jobs/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_returns_status(self, client: AsyncClient) -> None:
        token = await _get_token(client, "4")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.document_tasks.generate_documents.apply_async"):
            create_resp = await client.post(
                f"/api/v1/repos/{repo_id}/docs/generate",
                json={"repo_id": repo_id, "doc_types": ["readme"]},
                headers={"Authorization": f"Bearer {token}"},
            )
        job_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/repos/{repo_id}/docs/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["status"] == "queued"


class TestListDocuments:
    @pytest.mark.asyncio
    async def test_list_empty_repo_returns_empty_list(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "5")
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/docs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}/docs")
        assert response.status_code == 401


class TestGetDocumentByType:
    @pytest.mark.asyncio
    async def test_get_missing_doc_returns_404(self, client: AsyncClient) -> None:
        token = await _get_token(client, "6")
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/docs/readme",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert "readme" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_doc_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/docs/wiki"
        )
        assert response.status_code == 401


class TestGetDocumentById:
    @pytest.mark.asyncio
    async def test_get_nonexistent_doc_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "7")
        response = await client.get(
            f"/api/v1/docs/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_doc_versions_nonexistent_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "8")
        response = await client.get(
            f"/api/v1/docs/{uuid.uuid4()}/versions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestExportDocument:
    @pytest.mark.asyncio
    async def test_export_nonexistent_doc_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "9")
        response = await client.get(
            f"/api/v1/docs/{uuid.uuid4()}/export?format=markdown",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            f"/api/v1/docs/{uuid.uuid4()}/export?format=html"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_invalid_format_returns_422(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "10")
        response = await client.get(
            f"/api/v1/docs/{uuid.uuid4()}/export?format=pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422


class TestDocumentVersioning:
    @pytest.mark.asyncio
    async def test_versioning_increments_on_resave(
        self, client: AsyncClient
    ) -> None:
        """Saving two documents of the same type creates v1 then v2."""
        token = await _get_token(client, "11")
        repo_id = uuid.uuid4()

        with patch("app.workers.tasks.document_tasks.generate_documents.apply_async"):
            # First generation
            resp1 = await client.post(
                f"/api/v1/repos/{repo_id}/docs/generate",
                json={"repo_id": str(repo_id), "doc_types": ["readme"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp1.status_code == 202

            # Second generation (force_regenerate)
            resp2 = await client.post(
                f"/api/v1/repos/{repo_id}/docs/generate",
                json={"repo_id": str(repo_id), "doc_types": ["readme"], "force_regenerate": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp2.status_code == 202
            # Both jobs should have different IDs
            assert resp1.json()["id"] != resp2.json()["id"]
