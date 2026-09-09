"""LangGraph RAG agent graph definition.

Compiles the stateful agent graph from individual node functions.
The graph is compiled once at module import time and reused across
all requests to avoid repeated compilation overhead.

Pipeline:
  embed_query
      │
      ▼
  retrieve_context
      │
      ▼
  fetch_graph_context
      │
      ▼
  rerank_context
      │
      ▼
  generate_answer
      │
      ▼
   END
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.rag.nodes import (
    embed_query,
    fetch_graph_context,
    generate_answer,
    rerank_context,
    retrieve_context,
)
from app.rag.state import RagState

# ── Graph construction ────────────────────────────────────────────────────────

_builder = StateGraph(RagState)

_builder.add_node("embed_query", embed_query)
_builder.add_node("retrieve_context", retrieve_context)
_builder.add_node("fetch_graph_context", fetch_graph_context)
_builder.add_node("rerank_context", rerank_context)
_builder.add_node("generate_answer", generate_answer)

_builder.set_entry_point("embed_query")

_builder.add_edge("embed_query", "retrieve_context")
_builder.add_edge("retrieve_context", "fetch_graph_context")
_builder.add_edge("fetch_graph_context", "rerank_context")
_builder.add_edge("rerank_context", "generate_answer")
_builder.add_edge("generate_answer", END)

# Compiled graph — module-level singleton; thread-safe for concurrent use
rag_graph = _builder.compile()


def run_rag(
    question: str,
    *,
    repo_ids: list[str] | None = None,
    language: str | None = None,
    context_limit: int = 8,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> RagState:
    """Execute the full RAG pipeline and return the final state.

    Args:
        question: User's natural language question.
        repo_ids: Optional list of repository UUID strings to scope search.
        language: Optional language filter for retrieval.
        context_limit: Max context chunks to pass to the LLM (1-20).
        llm_provider: Override LLM provider (openai | anthropic | ollama).
        llm_model: Override specific LLM model name.

    Returns:
        Final ``RagState`` with ``answer``, ``context_chunks``,
        ``model_used``, and ``tokens_used`` populated.
    """
    import time

    t0 = time.perf_counter()

    initial_state: RagState = {
        "question": question,
        "repo_ids": [str(r) for r in (repo_ids or [])],
        "language": language,
        "context_limit": context_limit,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }

    final_state: RagState = rag_graph.invoke(initial_state)
    final_state["took_ms"] = (time.perf_counter() - t0) * 1000

    return final_state
