"""Integration tests for /api/v1/repos/{repo_id}/symbols endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


async def _create_authed_client(client: AsyncClient) -> tuple[AsyncClient, str]:
    """Register a user, login, and return (client, bearer_token)."""
    await client.post("/api/v1/auth/register", json={
        "email": "parser@example.com",
        "username": "parseruser",
        "password": "Password1",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "parser@example.com",
        "password": "Password1",
    })
    token = resp.json()["access_token"]
    return client, token


class TestParseStatusEndpoint:
    @pytest.mark.asyncio
    async def test_parse_status_returns_200(self, client: AsyncClient) -> None:
        _, token = await _create_authed_client(client)
        repo_id = uuid.uuid4()

        response = await client.get(
            f"/api/v1/repos/{repo_id}/parse-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "parse_status" in data
        assert "total_symbols" in data
        assert "languages" in data

    @pytest.mark.asyncio
    async def test_parse_status_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}/parse-status")
        assert response.status_code == 401


class TestListSymbolsEndpoint:
    @pytest.mark.asyncio
    async def test_list_symbols_empty_repo(self, client: AsyncClient) -> None:
        _, token = await _create_authed_client(client)
        repo_id = uuid.uuid4()

        response = await client.get(
            f"/api/v1/repos/{repo_id}/symbols",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["has_next"] is False

    @pytest.mark.asyncio
    async def test_list_symbols_pagination_params(self, client: AsyncClient) -> None:
        _, token = await _create_authed_client(client)
        repo_id = uuid.uuid4()

        response = await client.get(
            f"/api/v1/repos/{repo_id}/symbols?page=1&limit=10",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["limit"] == 10

    @pytest.mark.asyncio
    async def test_list_symbols_limit_above_max_returns_422(
        self, client: AsyncClient
    ) -> None:
        _, token = await _create_authed_client(client)
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/symbols?limit=999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_symbols_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/repos/{uuid.uuid4()}/symbols")
        assert response.status_code == 401


class TestFileSymbolsEndpoint:
    @pytest.mark.asyncio
    async def test_file_symbols_not_found_returns_404(
        self, client: AsyncClient
    ) -> None:
        _, token = await _create_authed_client(client)
        repo_id = uuid.uuid4()

        response = await client.get(
            f"/api/v1/repos/{repo_id}/symbols/file",
            params={"path": "src/main.py"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_file_symbols_missing_path_param_returns_422(
        self, client: AsyncClient
    ) -> None:
        _, token = await _create_authed_client(client)
        response = await client.get(
            f"/api/v1/repos/{uuid.uuid4()}/symbols/file",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422


class TestGetSymbolEndpoint:
    @pytest.mark.asyncio
    async def test_get_nonexistent_symbol_returns_404(
        self, client: AsyncClient
    ) -> None:
        _, token = await _create_authed_client(client)
        response = await client.get(
            f"/api/v1/symbols/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_symbol_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(f"/api/v1/symbols/{uuid.uuid4()}")
        assert response.status_code == 401
