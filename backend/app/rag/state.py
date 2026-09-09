"""LangGraph RAG agent state definition.

The ``RagState`` TypedDict is the shared mutable state that flows through
every node in the LangGraph agent. Each node reads from and writes to
specific keys, enabling LangGraph to route and manage state transitions.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict


class RagState(TypedDict, total=False):
    """Shared state for the RAG agent graph.

    Attributes:
        question: Original user question string.
        repo_ids: List of repository UUID strings to scope retrieval.
        language: Optional language filter for retrieval.
        context_limit: Max number of context chunks to retrieve.
        llm_provider: LLM provider identifier (openai | anthropic | ollama).
        llm_model: Specific LLM model name to use.

        query_vector: Embedded float vector for the question.
        raw_hits: Raw retrieval results from Qdrant before reranking.
        context_chunks: Reranked and formatted context chunks for the LLM.
        graph_context: Additional context pulled from Neo4j (callers, callees).

        answer: Generated answer string from the LLM.
        model_used: Actual LLM model identifier used for generation.
        tokens_used: Dict with prompt_tokens, completion_tokens, total_tokens.
        took_ms: Total end-to-end latency in milliseconds.
        error: Error message string if any node failed.
    """

    # Input
    question: str
    repo_ids: list[str]
    language: str | None
    context_limit: int
    llm_provider: str | None
    llm_model: str | None

    # Retrieval intermediates
    query_vector: list[float]
    raw_hits: list[dict[str, Any]]
    context_chunks: list[dict[str, Any]]
    graph_context: str

    # Output
    answer: str
    model_used: str
    tokens_used: dict[str, int]
    took_ms: float
    error: str | None
