"""Pydantic v2 schemas for search and RAG request/response payloads."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    """Supported search modes.

    Attributes:
        semantic: Pure vector similarity search.
        keyword: Full-text BM25-style search via Qdrant payload filters.
        hybrid: Combine semantic + keyword with RRF fusion.
    """

    semantic = "semantic"
    keyword = "keyword"
    hybrid = "hybrid"


class SearchRequest(BaseModel):
    """Payload for the /search endpoint.

    Attributes:
        query: Natural language or code query string.
        repo_ids: Optional list of repository UUIDs to scope the search.
                  If empty, searches across all repositories.
        language: Optional programming language filter.
        symbol_kind: Optional symbol kind filter (function, class, …).
        mode: Search strategy (semantic | keyword | hybrid).
        limit: Maximum number of results to return (1-50).
        min_score: Minimum similarity score threshold (0.0-1.0).
    """

    query: str = Field(min_length=1, max_length=2000)
    repo_ids: list[uuid.UUID] = Field(default_factory=list)
    language: str | None = None
    symbol_kind: str | None = None
    mode: SearchMode = SearchMode.hybrid
    limit: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)


class SearchHit(BaseModel):
    """A single search result item.

    Attributes:
        symbol_id: UUID of the matching ParsedSymbol.
        repo_id: UUID of the containing repository.
        repo_name: Display name of the repository.
        file_path: Relative file path within the repository.
        language: Programming language.
        symbol_kind: Type of symbol.
        name: Unqualified symbol name.
        qualified_name: Fully scoped symbol name.
        start_line: Definition start line.
        end_line: Definition end line.
        signature: Function/method signature, if available.
        docstring: Extracted documentation string.
        score: Similarity score (0.0-1.0).
        chunk_text: The embedded text chunk that matched.
    """

    symbol_id: uuid.UUID
    repo_id: uuid.UUID
    repo_name: str
    file_path: str
    language: str
    symbol_kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    score: float
    chunk_text: str


class SearchResponse(BaseModel):
    """Response from /search endpoint.

    Attributes:
        query: The original query string.
        mode: Search mode used.
        total: Number of hits returned.
        hits: Ranked list of SearchHit items.
        took_ms: Server-side search latency in milliseconds.
    """

    query: str
    mode: SearchMode
    total: int
    hits: list[SearchHit]
    took_ms: float


class AskRequest(BaseModel):
    """Payload for the /ask (RAG) endpoint.

    Attributes:
        question: Natural language question about the codebase.
        repo_ids: Optional repository scope.
        language: Optional language filter for retrieval.
        context_limit: Maximum number of context chunks to retrieve.
        stream: Whether to stream the answer as Server-Sent Events.
        llm_provider: LLM provider override (openai | anthropic | ollama).
        llm_model: Specific model name override.
    """

    question: str = Field(min_length=5, max_length=4000)
    repo_ids: list[uuid.UUID] = Field(default_factory=list)
    language: str | None = None
    context_limit: int = Field(default=8, ge=1, le=20)
    stream: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None


class ContextChunk(BaseModel):
    """A piece of retrieved context used as input to the LLM.

    Attributes:
        symbol_id: UUID of the source symbol.
        repo_name: Repository display name.
        file_path: Source file path.
        start_line: Start line of the symbol.
        end_line: End line of the symbol.
        language: Programming language.
        symbol_kind: Kind of symbol.
        qualified_name: Fully qualified name.
        text: The text content fed to the LLM.
        score: Retrieval relevance score.
    """

    symbol_id: uuid.UUID
    repo_name: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    symbol_kind: str
    qualified_name: str
    text: str
    score: float


class AskResponse(BaseModel):
    """Response from /ask (RAG) endpoint.

    Attributes:
        question: The original question.
        answer: Generated LLM answer.
        context: Retrieved context chunks used for generation.
        model: LLM model identifier used.
        took_ms: Total latency in milliseconds.
        tokens_used: Token consumption dict (prompt, completion, total).
    """

    question: str
    answer: str
    context: list[ContextChunk]
    model: str
    took_ms: float
    tokens_used: dict[str, int]
