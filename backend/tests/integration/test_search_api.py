"""Integration tests for /api/v1/search and /api/v1/ask endpoints.

Uses the real FastAPI test client with DB/Redis container overrides.
Qdrant and LLM calls are mocked to avoid external infrastructure.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


async def _get_token(client: AsyncClient, suffix: str = "") -> str:
    """Register a user and return a valid JWT bearer token."""
    email = f"search{suffix}@example.com"
    username = f"searchuser{suffix}"
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "username": username,
        "password": "Password1",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password1",
    })
    return resp.json()["access_token"]


class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/search",
            json={"query": "authentication"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_returns_200_with_mocked_qdrant(
        self, client: AsyncClient
    ) -> None:
        token = await _get_token(client, "1")
        mock_hits = [
            {
                "symbol_id": str(uuid.uuid4()),
                "repo_id": str(uuid.uuid4()),
                "repo_name": "test-repo",
                "file_path": "src/auth.py",
                "language": "python",
                "symbol_kind": "function",
                "name": "authenticate",
                "qualified_name": "authenticate",
                "start_line": 10,
                "end_line": 25,
                "signature": "def authenticate(email, password)",
                "docstring": "Authenticate a user.",
                "chunk_text": "def authenticate(email, password): ...",
                "score": 0.88,
            }
        ]
        with patch(
            "app.services.embedding_service.EmbeddingService.hybrid_search",
            return_value=mock_hits,
        ):
            response = await client.post(
                "/api/v1/search",
                json={"query": "user authentication", "mode": "hybrid"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["hits"][0]["name"] == "authenticate"
        assert data["hits"][0]["score"] == pytest.approx(0.88, abs=0.01)
        assert "took_ms" in data

    @pytest.mark.asyncio
    async def test_search_semantic_mode(self, client: AsyncClient) -> None:
        token = await _get_token(client, "2")
        with patch(
            "app.services.embedding_service.EmbeddingService.search",
            return_value=[],
        ):
            response = await client.post(
                "/api/v1/search",
                json={"query": "login function", "mode": "semantic"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        assert response.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_search_keyword_mode(self, client: AsyncClient) -> None:
        token = await _get_token(client, "3")
        with patch(
            "app.services.embedding_service.EmbeddingService.search_by_text",
            return_value=[],
        ):
            response = await client.post(
                "/api/v1/search",
                json={"query": "UserRepository", "mode": "keyword"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_422(self, client: AsyncClient) -> None:
        token = await _get_token(client, "4")
        response = await client.post(
            "/api/v1/search",
            json={"query": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_with_repo_filter(self, client: AsyncClient) -> None:
        token = await _get_token(client, "5")
        repo_id = str(uuid.uuid4())
        with patch(
            "app.services.embedding_service.EmbeddingService.hybrid_search",
            return_value=[],
        ):
            response = await client.post(
                "/api/v1/search",
                json={"query": "database", "repo_ids": [repo_id]},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_limit_above_max_returns_422(self, client: AsyncClient) -> None:
        token = await _get_token(client, "6")
        response = await client.post(
            "/api/v1/search",
            json={"query": "test", "limit": 999},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422


class TestAskEndpoint:
    @pytest.mark.asyncio
    async def test_ask_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/ask",
            json={"question": "How does login work?"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_ask_returns_200_with_mocked_rag(self, client: AsyncClient) -> None:
        token = await _get_token(client, "7")

        mock_response = MagicMock()
        mock_response.question = "How does login work?"
        mock_response.answer = "The login function validates credentials and issues JWT tokens."
        mock_response.context = []
        mock_response.model = "openai/gpt-4o-mini"
        mock_response.took_ms = 1500.0
        mock_response.tokens_used = {
            "prompt_tokens": 200,
            "completion_tokens": 80,
            "total_tokens": 280,
        }

        with patch(
            "app.services.search_service.SearchService.ask",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.post(
                "/api/v1/ask",
                json={"question": "How does login work?"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "JWT" in data["answer"]
        assert "model" in data
        assert data["tokens_used"]["total_tokens"] == 280

    @pytest.mark.asyncio
    async def test_ask_short_question_returns_422(self, client: AsyncClient) -> None:
        token = await _get_token(client, "8")
        response = await client.post(
            "/api/v1/ask",
            json={"question": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_ask_with_language_filter(self, client: AsyncClient) -> None:
        token = await _get_token(client, "9")
        mock_response = MagicMock()
        mock_response.question = "What is the user model?"
        mock_response.answer = "The user model defines user entity."
        mock_response.context = []
        mock_response.model = "openai/gpt-4o-mini"
        mock_response.took_ms = 900.0
        mock_response.tokens_used = {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}

        with patch(
            "app.services.search_service.SearchService.ask",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.post(
                "/api/v1/ask",
                json={"question": "What is the user model?", "language": "python"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
