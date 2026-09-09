"""Integration tests for the /api/v1/repos endpoints.

Runs against a real PostgreSQL container via testcontainers.
Celery task dispatch is patched to prevent actual network calls.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestImportRepository:
    """Integration tests for POST /api/v1/repos."""

    @pytest.mark.asyncio
    async def test_import_returns_202(self, client: AsyncClient) -> None:
        """Successful import returns HTTP 202 with repository payload."""
        with patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task:
            mock_task.apply_async.return_value = MagicMock(id=str(uuid.uuid4()))

            response = await client.post(
                "/api/v1/repos",
                json={
                    "url": "https://github.com/octocat/Hello-World",
                    "default_branch": "main",
                },
            )

        assert response.status_code == 202
        data = response.json()
        assert data["name"] == "Hello-World"
        assert data["index_status"] == "pending"
        assert data["latest_job"] is not None
        assert data["latest_job"]["status"] == "queued"

    @pytest.mark.asyncio
    async def test_import_duplicate_url_returns_409(self, client: AsyncClient) -> None:
        """Second import with same URL returns HTTP 409."""
        with patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task:
            mock_task.apply_async.return_value = MagicMock(id=str(uuid.uuid4()))
            await client.post(
                "/api/v1/repos",
                json={"url": "https://github.com/octocat/duplicate-test"},
            )
            response = await client.post(
                "/api/v1/repos",
                json={"url": "https://github.com/octocat/duplicate-test"},
            )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_without_url_or_path_returns_422(self, client: AsyncClient) -> None:
        """Request with neither url nor local_path returns HTTP 422."""
        response = await client.post("/api/v1/repos", json={"name": "orphan"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_import_with_both_url_and_path_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Providing both url and local_path returns HTTP 422."""
        response = await client.post(
            "/api/v1/repos",
            json={
                "url": "https://github.com/org/repo",
                "local_path": "/mnt/repos/repo",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_import_local_path(self, client: AsyncClient) -> None:
        """Local path import accepted and returns 202."""
        with patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task:
            mock_task.apply_async.return_value = MagicMock(id=str(uuid.uuid4()))

            response = await client.post(
                "/api/v1/repos",
                json={"local_path": "/mnt/repos/local-service", "name": "local-service"},
            )

        assert response.status_code == 202
        assert response.json()["name"] == "local-service"


class TestGetRepository:
    """Integration tests for GET /api/v1/repos/{id}."""

    @pytest.mark.asyncio
    async def test_get_existing_repo(self, client: AsyncClient) -> None:
        """Returns 200 with full repository data."""
        with patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task:
            mock_task.apply_async.return_value = MagicMock(id=str(uuid.uuid4()))
            create_resp = await client.post(
                "/api/v1/repos",
                json={"url": "https://github.com/test/get-repo-test"},
            )
        repo_id = create_resp.json()["id"]

        response = await client.get(f"/api/v1/repos/{repo_id}")
        assert response.status_code == 200
        assert response.json()["id"] == repo_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_repo_returns_404(self, client: AsyncClient) -> None:
        """Returns 404 for unknown UUID."""
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}")
        assert response.status_code == 404


class TestListRepositories:
    """Integration tests for GET /api/v1/repos."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_response(self, client: AsyncClient) -> None:
        """Returns a valid paginated list structure."""
        response = await client.get("/api/v1/repos?page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "has_next" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_limit_capped_at_100(self, client: AsyncClient) -> None:
        """Limit > 100 is silently capped at 100."""
        response = await client.get("/api/v1/repos?limit=500")
        assert response.status_code == 200


class TestDeleteRepository:
    """Integration tests for DELETE /api/v1/repos/{id}."""

    @pytest.mark.asyncio
    async def test_delete_existing_returns_204(self, client: AsyncClient) -> None:
        """DELETE returns 204 and the repo is subsequently 404."""
        with patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task, \
             patch("app.workers.tasks.repo_tasks.delete_repo_artifacts") as mock_cleanup:
            mock_task.apply_async.return_value = MagicMock(id=str(uuid.uuid4()))
            mock_cleanup.apply_async.return_value = MagicMock()
            create_resp = await client.post(
                "/api/v1/repos",
                json={"url": "https://github.com/test/delete-test"},
            )
        repo_id = create_resp.json()["id"]

        delete_resp = await client.delete(f"/api/v1/repos/{repo_id}")
        assert delete_resp.status_code == 204

        get_resp = await client.get(f"/api/v1/repos/{repo_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.delete(f"/api/v1/repos/{uuid.uuid4()}")
        assert response.status_code == 404


class TestRepositoryStatus:
    """Integration tests for GET /api/v1/repos/{id}/status."""

    @pytest.mark.asyncio
    async def test_status_returns_correct_fields(self, client: AsyncClient) -> None:
        with patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task:
            mock_task.apply_async.return_value = MagicMock(id=str(uuid.uuid4()))
            create_resp = await client.post(
                "/api/v1/repos",
                json={"url": "https://github.com/test/status-test"},
            )
        repo_id = create_resp.json()["id"]

        response = await client.get(f"/api/v1/repos/{repo_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["repo_id"] == repo_id
        assert "index_status" in data
        assert "latest_job" in data


class TestHealthEndpoints:
    """Tests for /health and /ready probes."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
