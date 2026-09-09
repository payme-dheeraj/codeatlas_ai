"""Search service — orchestrates symbol search and RAG queries.

This is the primary service consumed by the API layer. It delegates:
- Semantic/keyword/hybrid search to EmbeddingService (Qdrant).
- RAG answer generation to the LangGraph agent (rag.graph).
- Repository name resolution to SymbolRepository.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.symbol_repository import SymbolRepository
from app.schemas.search import (
    AskRequest,
    AskResponse,
    ContextChunk,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


class SearchService:
    """Async service for code search and RAG question answering.

    Attributes:
        _session: Active async SQLAlchemy session.
        _symbol_repo: Data access for symbol metadata.
        _embedding_svc: Qdrant vector search client.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with a database session.

        Args:
            session: Active async SQLAlchemy session.
        """
        self._session = session
        self._symbol_repo = SymbolRepository(session)
        self._embedding_svc = EmbeddingService()

    # ── Symbol Search ─────────────────────────────────────────────────────────

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a symbol search and return ranked results.

        Args:
            request: Validated SearchRequest payload.

        Returns:
            SearchResponse with ranked SearchHit items.
        """
        t0 = time.perf_counter()

        repo_ids = [str(r) for r in request.repo_ids] if request.repo_ids else None

        if request.mode.value == "semantic":
            raw_hits = self._embedding_svc.search(
                request.query,
                repo_ids=repo_ids,
                language=request.language,
                symbol_kind=request.symbol_kind,
                limit=request.limit,
                min_score=request.min_score,
            )
        elif request.mode.value == "keyword":
            raw_hits = self._embedding_svc.search_by_text(
                request.query,
                repo_ids=repo_ids,
                language=request.language,
                symbol_kind=request.symbol_kind,
                limit=request.limit,
            )
        else:  # hybrid
            raw_hits = self._embedding_svc.hybrid_search(
                request.query,
                repo_ids=repo_ids,
                language=request.language,
                symbol_kind=request.symbol_kind,
                limit=request.limit,
                min_score=request.min_score,
            )

        hits = [self._hit_to_schema(h) for h in raw_hits]
        took_ms = (time.perf_counter() - t0) * 1000

        return SearchResponse(
            query=request.query,
            mode=request.mode,
            total=len(hits),
            hits=hits,
            took_ms=round(took_ms, 2),
        )

    # ── RAG Answer ────────────────────────────────────────────────────────────

    async def ask(self, request: AskRequest) -> AskResponse:
        """Generate a RAG answer for a natural language question.

        Runs the LangGraph pipeline synchronously in a thread pool executor
        to avoid blocking the async event loop during LLM calls.

        Args:
            request: Validated AskRequest payload.

        Returns:
            AskResponse with generated answer and context citations.
        """
        import asyncio
        from functools import partial

        from app.rag.graph import run_rag

        repo_ids = [str(r) for r in request.repo_ids] if request.repo_ids else None

        # Run CPU/IO-bound RAG pipeline in a thread pool
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(
            None,
            partial(
                run_rag,
                request.question,
                repo_ids=repo_ids,
                language=request.language,
                context_limit=request.context_limit,
                llm_provider=request.llm_provider,
                llm_model=request.llm_model,
            ),
        )

        answer = final_state.get("answer", "")
        model_used = final_state.get("model_used", "unknown")
        tokens_used = final_state.get("tokens_used") or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        took_ms = final_state.get("took_ms", 0.0)
        context_chunks = final_state.get("context_chunks") or []

        logger.info(
            "rag_completed",
            question=request.question[:80],
            model=model_used,
            context_count=len(context_chunks),
            tokens=tokens_used.get("total_tokens", 0),
        )

        return AskResponse(
            question=request.question,
            answer=answer,
            context=[self._chunk_to_schema(c) for c in context_chunks],
            model=model_used,
            took_ms=round(took_ms, 2),
            tokens_used=tokens_used,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _hit_to_schema(hit: dict[str, Any]) -> SearchHit:
        """Convert a raw Qdrant payload dict to a SearchHit schema.

        Args:
            hit: Qdrant payload dict with score.

        Returns:
            SearchHit instance.
        """
        return SearchHit(
            symbol_id=uuid.UUID(hit.get("symbol_id", str(uuid.uuid4()))),
            repo_id=uuid.UUID(hit.get("repo_id", str(uuid.uuid4()))),
            repo_name=hit.get("repo_name", ""),
            file_path=hit.get("file_path", ""),
            language=hit.get("language", ""),
            symbol_kind=hit.get("symbol_kind", ""),
            name=hit.get("name", ""),
            qualified_name=hit.get("qualified_name", ""),
            start_line=hit.get("start_line", 0),
            end_line=hit.get("end_line", 0),
            signature=hit.get("signature") or None,
            docstring=hit.get("docstring") or None,
            score=round(float(hit.get("score", 0.0)), 4),
            chunk_text=hit.get("chunk_text", ""),
        )

    @staticmethod
    def _chunk_to_schema(chunk: dict[str, Any]) -> ContextChunk:
        """Convert a context chunk dict to the ContextChunk response schema.

        Args:
            chunk: Dict from Qdrant payload with score.

        Returns:
            ContextChunk instance.
        """
        return ContextChunk(
            symbol_id=uuid.UUID(chunk.get("symbol_id", str(uuid.uuid4()))),
            repo_name=chunk.get("repo_name", ""),
            file_path=chunk.get("file_path", ""),
            start_line=chunk.get("start_line", 0),
            end_line=chunk.get("end_line", 0),
            language=chunk.get("language", ""),
            symbol_kind=chunk.get("symbol_kind", ""),
            qualified_name=chunk.get("qualified_name", ""),
            text=chunk.get("chunk_text", ""),
            score=round(float(chunk.get("score", 0.0)), 4),
        )
