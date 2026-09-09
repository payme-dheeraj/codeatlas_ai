"""Integration tests for /api/v1 diagram endpoints.

Uses the real FastAPI test client. Celery tasks, Neo4j, Kroki, and MinIO
are mocked to avoid external infrastructure requirements.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


async def _get_token(client: AsyncClient, suffix: str = "") -> str:
    email = f"diag{suffix}@example.com"
    username = f"diaguser{suffix}"
    await client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": "Password1",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password1",
    })
    return resp.json()["access_token"]


class TestGenerateDiagrams:
    @pytest.mark.asyncio
    async def test_generate_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            f"/api/v1/repos/{uuid.uuid4()}/diagrams/generate",
            json={"repo_id": str(uuid.uuid4()), "diagram_types": ["architecture"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_returns_202_with_job_id(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "1")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.diagram_tasks.generate_diagrams.apply_async") as mock_task:
            mock_task.return_value = MagicMock(id="celery-task-id-123")
            response = await client.post(
                f"/api/v1/repos/{repo_id}/diagrams/generate",
                json={
                    "repo_id": repo_id,
                    "diagram_types": ["architecture", "er"],
                    "diagram_format": "mermaid",
                    "force_regenerate": False,
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert set(data["diagram_types"]) == {"architecture", "er"}

    @pytest.mark.asyncio
    async def test_generate_invalid_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "2")
        repo_id = str(uuid.uuid4())
        response = await client.post(
            f"/api/v1/repos/{repo_id}/diagrams/generate",
            json={"repo_id": repo_id, "diagram_types": ["unknown_type"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_all_types(self, client: AsyncClient) -> None:
        token = await _get_token(client, "3")
        repo_id = str(uuid.uuid4())
        with patch("app.workers.tasks.diagram_tasks.generate_diagrams.apply_async") as mock_task:
            mock_task.return_value = MagicMock(id="task-all")
            response = await client.post(
                f"/api/v1/repos/{repo_id}/diagrams/generate",
                json={
                    "repo_id": repo_id,
                    "diagram_types": ["architecture", "dependency", "sequence", "er", "deployment"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 202


class TestListDiagrams:
    @pytest.mark.asyncio
    async def test_list_empty_repo_returns_empty_list(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "4")
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/diagrams",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}/diagrams")
        assert response.status_code == 401


class TestGetDiagramByType:
    @pytest.mark.asyncio
    async def test_missing_diagram_returns_404(self, client: AsyncClient) -> None:
        token = await _get_token(client, "5")
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/diagrams/architecture",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert "architecture" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/diagrams/er"
        )
        assert response.status_code == 401


class TestGetDiagramById:
    @pytest.mark.asyncio
    async def test_nonexistent_diagram_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "6")
        response = await client.get(
            f"/api/v1/diagrams/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/v1/diagrams/{uuid.uuid4()}")
        assert response.status_code == 401


class TestGetDiagramSource:
    @pytest.mark.asyncio
    async def test_source_nonexistent_diagram_returns_404(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "7")
        response = await client.get(
            f"/api/v1/diagrams/{uuid.uuid4()}/source",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_source_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/diagrams/{uuid.uuid4()}/source")
        assert response.status_code == 401


class TestDiagramFlowEndToEnd:
    @pytest.mark.asyncio
    async def test_trigger_then_list_shows_queued(
        self, client: AsyncClient
    ) -> None:
        """After triggering generation, the list endpoint still returns empty
        (job is async). Verify the round-trip doesn't error."""
        token = await _get_token(client, "8")
        repo_id = str(uuid.uuid4())

        with patch("app.workers.tasks.diagram_tasks.generate_diagrams.apply_async") as mock_task:
            mock_task.return_value = MagicMock(id="task-e2e")
            gen_resp = await client.post(
                f"/api/v1/repos/{repo_id}/diagrams/generate",
                json={"repo_id": repo_id, "diagram_types": ["dependency"]},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert gen_resp.status_code == 202
        assert gen_resp.json()["job_id"] == "task-e2e"

        # List should return empty (task hasn't run)
        list_resp = await client.get(
            f"/api/v1/repos/{repo_id}/diagrams",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        assert list_resp.json() == []

    @pytest.mark.asyncio
    async def test_d2_format_accepted(self, client: AsyncClient) -> None:
        token = await _get_token(client, "9")
        repo_id = str(uuid.uuid4())
        with patch("app.workers.tasks.diagram_tasks.generate_diagrams.apply_async") as mock_task:
            mock_task.return_value = MagicMock(id="task-d2")
            response = await client.post(
                f"/api/v1/repos/{repo_id}/diagrams/generate",
                json={
                    "repo_id": repo_id,
                    "diagram_types": ["deployment"],
                    "diagram_format": "d2",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 202
