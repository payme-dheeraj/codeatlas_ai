"""Integration tests for /api/v1/auth endpoints.

Runs against real PostgreSQL and Redis containers via testcontainers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ── Helpers ────────────────────────────────────────────────────────────────────

REGISTER_PAYLOAD = {
    "email": "integration@example.com",
    "username": "integrationuser",
    "password": "Integration1",
}


async def register_and_login(client: AsyncClient) -> dict:
    """Register a user and return the login TokenResponse dict."""
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )
    return resp.json()


# ── Registration ───────────────────────────────────────────────────────────────


class TestRegisterEndpoint:
    @pytest.mark.asyncio
    async def test_register_success_returns_201(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "Secure1234",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["username"] == "newuser"
        assert data["role"] == "viewer"
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        payload = {
            "email": "dup@example.com",
            "username": "dupuser1",
            "password": "Secure1234",
        }
        await client.post("/api/v1/auth/register", json=payload)
        payload["username"] = "dupuser2"
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_weak_password_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com",
                "username": "weakuser",
                "password": "password",  # no uppercase, no digit
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "username": "user", "password": "Password1"},
        )
        assert response.status_code == 422


# ── Login ──────────────────────────────────────────────────────────────────────


class TestLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_returns_token_pair(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "logintest@example.com",
                "username": "logintest",
                "password": "Password1",
            },
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "logintest@example.com", "password": "Password1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrongpwd@example.com",
                "username": "wrongpwduser",
                "password": "Password1",
            },
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpwd@example.com", "password": "BadPass1"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Password1"},
        )
        assert response.status_code == 401


# ── Token refresh ──────────────────────────────────────────────────────────────


class TestRefreshEndpoint:
    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json={
            "email": "refresh@example.com",
            "username": "refreshuser",
            "password": "Password1",
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": "refresh@example.com",
            "password": "Password1",
        })
        original_refresh = login.json()["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original_refresh},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["refresh_token"] != original_refresh  # rotated

    @pytest.mark.asyncio
    async def test_refresh_reuse_returns_401(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json={
            "email": "reuse@example.com",
            "username": "reuseuser",
            "password": "Password1",
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": "reuse@example.com",
            "password": "Password1",
        })
        original_refresh = login.json()["refresh_token"]

        # First use — OK
        await client.post("/api/v1/auth/refresh", json={"refresh_token": original_refresh})
        # Second use of same token — should be revoked
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original_refresh},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.jwt.token"},
        )
        assert response.status_code == 401


# ── Authenticated endpoints ────────────────────────────────────────────────────


class TestMeEndpoint:
    @pytest.mark.asyncio
    async def test_get_me_returns_profile(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json={
            "email": "metest@example.com",
            "username": "metest",
            "password": "Password1",
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": "metest@example.com",
            "password": "Password1",
        })
        token = login.json()["access_token"]

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "metest@example.com"

    @pytest.mark.asyncio
    async def test_get_me_without_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401


# ── API Keys ───────────────────────────────────────────────────────────────────


class TestApiKeyEndpoints:
    @pytest.mark.asyncio
    async def test_create_and_revoke_api_key(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json={
            "email": "apikey@example.com",
            "username": "apikeyuser",
            "password": "Password1",
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": "apikey@example.com",
            "password": "Password1",
        })
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create key
        create_resp = await client.post(
            "/api/v1/auth/api-keys",
            headers=headers,
            json={"name": "Test CI Key"},
        )
        assert create_resp.status_code == 201
        key_data = create_resp.json()
        assert key_data["key"].startswith("ca_")
        assert "key" in key_data  # raw key shown once
        key_id = key_data["id"]

        # List keys
        list_resp = await client.get("/api/v1/auth/api-keys", headers=headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert any(k["id"] == key_id for k in items)
        assert all("key" not in k for k in items)  # raw key not in list

        # Revoke key
        revoke_resp = await client.delete(
            f"/api/v1/auth/api-keys/{key_id}", headers=headers
        )
        assert revoke_resp.status_code == 204

        # Key should not appear in list anymore
        list_resp2 = await client.get("/api/v1/auth/api-keys", headers=headers)
        assert not any(k["id"] == key_id for k in list_resp2.json())

    @pytest.mark.asyncio
    async def test_create_api_key_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Orphan Key"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_authenticates_requests(self, client: AsyncClient) -> None:
        """A raw API key in X-API-Key header should authenticate a request."""
        await client.post("/api/v1/auth/register", json={
            "email": "apikeyauth@example.com",
            "username": "apikeyauth",
            "password": "Password1",
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": "apikeyauth@example.com",
            "password": "Password1",
        })
        bearer = login.json()["access_token"]

        create = await client.post(
            "/api/v1/auth/api-keys",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"name": "Repo Access Key"},
        )
        raw_key = create.json()["key"]

        # Use raw API key to call a protected endpoint
        repos_resp = await client.get(
            "/api/v1/repos",
            headers={"X-API-Key": raw_key},
        )
        assert repos_resp.status_code == 200
