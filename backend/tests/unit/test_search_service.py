"""Unit tests for SearchService and supporting utilities.

All Qdrant and LLM calls are mocked — no external services required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.embeddings import chunk_text, content_hash
from app.rag.prompts import build_rag_prompt, format_context_chunk
from app.schemas.search import AskRequest, SearchMode, SearchRequest
from app.services.embedding_service import _rrf_fuse


# ── Embedding utilities ────────────────────────────────────────────────────────


class TestChunkText:
    def test_short_text_returns_single_chunk(self) -> None:
        text = "Hello world"
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert chunks == [text]

    def test_long_text_splits(self) -> None:
        text = "a " * 1000  # ~2000 chars
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) > 1

    def test_overlap_causes_shared_content(self) -> None:
        text = "word " * 300
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        # Adjacent chunks should share some content due to overlap
        for i in range(len(chunks) - 1):
            assert len(chunks[i]) > 0

    def test_empty_text(self) -> None:
        chunks = chunk_text("", chunk_size=512)
        assert chunks == [""]


class TestContentHash:
    def test_same_text_same_hash(self) -> None:
        assert content_hash("hello") == content_hash("hello")

    def test_different_text_different_hash(self) -> None:
        assert content_hash("hello") != content_hash("world")

    def test_hash_is_64_chars(self) -> None:
        assert len(content_hash("test")) == 64


class TestOllamaEmbeddings:
    def test_embed_ollama_batch_api_success(self) -> None:
        from app.core.embeddings import _embed_ollama

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        }

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            vectors = _embed_ollama(["hello", "world"])
            assert len(vectors) == 2
            assert vectors[0] == [0.1, 0.2, 0.3]
            mock_post.assert_called_once()

    def test_embed_ollama_fallback_to_single_api(self) -> None:
        from app.core.embeddings import _embed_ollama

        def side_effect(url, **kwargs):
            mock = MagicMock()
            if "/api/embed" in url:
                mock.status_code = 404
                return mock
            elif "/api/embeddings" in url:
                mock.status_code = 200
                mock.json.return_value = {"embedding": [0.7, 0.8, 0.9]}
                return mock
            mock.status_code = 500
            return mock

        with patch("httpx.post", side_effect=side_effect):
            vectors = _embed_ollama(["single_text"])
            assert len(vectors) == 1
            assert vectors[0] == [0.7, 0.8, 0.9]


# ── RRF fusion ────────────────────────────────────────────────────────────────


class TestRrfFuse:
    def _make_hit(self, symbol_id: str, score: float) -> dict:
        return {"symbol_id": symbol_id, "score": score, "name": symbol_id}

    def test_merges_two_lists(self) -> None:
        a = [self._make_hit("A", 0.9), self._make_hit("B", 0.7)]
        b = [self._make_hit("B", 0.8), self._make_hit("C", 0.6)]
        result = _rrf_fuse(a, b, k=60, limit=5)
        # B appears in both — should score highest via RRF
        assert result[0]["symbol_id"] == "B"

    def test_deduplicates_by_symbol_id(self) -> None:
        a = [self._make_hit("X", 0.9)]
        b = [self._make_hit("X", 0.8)]
        result = _rrf_fuse(a, b, k=60, limit=5)
        assert len(result) == 1

    def test_respects_limit(self) -> None:
        a = [self._make_hit(f"sym{i}", 1.0 / (i + 1)) for i in range(10)]
        result = _rrf_fuse(a, [], k=60, limit=3)
        assert len(result) == 3


# ── Prompts ────────────────────────────────────────────────────────────────────


class TestPrompts:
    def test_format_context_chunk_includes_name(self) -> None:
        chunk = {
            "qualified_name": "AuthService.login",
            "symbol_kind": "method",
            "file_path": "services/auth.py",
            "start_line": 10,
            "end_line": 30,
            "language": "python",
            "signature": "def login(self, email: str) -> str",
            "docstring": "Authenticate a user.",
            "chunk_text": "def login(self, email):\n    pass",
        }
        output = format_context_chunk(1, chunk)
        assert "AuthService.login" in output
        assert "services/auth.py" in output
        assert "Authenticate a user." in output

    def test_build_rag_prompt_with_chunks(self) -> None:
        chunks = [
            {
                "qualified_name": "foo",
                "symbol_kind": "function",
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 5,
                "language": "python",
                "signature": None,
                "docstring": None,
                "chunk_text": "def foo(): pass",
            }
        ]
        prompt = build_rag_prompt("What does foo do?", chunks, "No graph context.")
        assert "What does foo do?" in prompt
        assert "foo.py" in prompt

    def test_build_rag_prompt_empty_chunks(self) -> None:
        prompt = build_rag_prompt("Explain the code.", [], "")
        assert "No relevant code context" in prompt


# ── SearchService (mocked) ────────────────────────────────────────────────────


class TestSearchService:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_embedding_svc(self):
        svc = MagicMock()
        svc.hybrid_search.return_value = [
            {
                "symbol_id": str(uuid.uuid4()),
                "repo_id": str(uuid.uuid4()),
                "repo_name": "test-repo",
                "file_path": "src/auth.py",
                "language": "python",
                "symbol_kind": "function",
                "name": "login",
                "qualified_name": "login",
                "start_line": 1,
                "end_line": 10,
                "signature": "def login()",
                "docstring": "Login function",
                "chunk_text": "def login(): pass",
                "score": 0.92,
            }
        ]
        svc.search.return_value = svc.hybrid_search.return_value
        svc.search_by_text.return_value = svc.hybrid_search.return_value
        return svc

    @pytest.mark.asyncio
    async def test_search_hybrid_returns_hits(
        self, mock_session, mock_embedding_svc
    ) -> None:
        from app.services.search_service import SearchService

        svc = SearchService(mock_session)
        svc._embedding_svc = mock_embedding_svc

        result = await svc.search(
            SearchRequest(query="user authentication", mode=SearchMode.hybrid)
        )
        assert result.total == 1
        assert result.hits[0].name == "login"
        assert result.hits[0].score == pytest.approx(0.92, abs=0.01)

    @pytest.mark.asyncio
    async def test_search_semantic_mode(self, mock_session, mock_embedding_svc) -> None:
        from app.services.search_service import SearchService

        svc = SearchService(mock_session)
        svc._embedding_svc = mock_embedding_svc

        await svc.search(SearchRequest(query="auth", mode=SearchMode.semantic))
        mock_embedding_svc.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_keyword_mode(self, mock_session, mock_embedding_svc) -> None:
        from app.services.search_service import SearchService

        svc = SearchService(mock_session)
        svc._embedding_svc = mock_embedding_svc

        await svc.search(SearchRequest(query="login", mode=SearchMode.keyword))
        mock_embedding_svc.search_by_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_calls_rag_pipeline(self, mock_session, mock_embedding_svc) -> None:
        from app.services.search_service import SearchService

        mock_state = {
            "answer": "The login function authenticates users.",
            "model_used": "openai/gpt-4o-mini",
            "tokens_used": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "took_ms": 1200.0,
            "context_chunks": [],
        }

        with patch("app.services.search_service.SearchService.ask", new_callable=AsyncMock) as mock_ask:
            mock_ask.return_value = MagicMock(
                question="How does login work?",
                answer="The login function authenticates users.",
                context=[],
                model="openai/gpt-4o-mini",
                took_ms=1200.0,
                tokens_used={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            )
            svc = SearchService(mock_session)
            result = await svc.ask(AskRequest(question="How does login work?"))
            assert "login" in result.answer
