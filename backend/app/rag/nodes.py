"""LangGraph node functions for the RAG agent.

Each function accepts and returns a ``RagState`` dict. LangGraph calls
these as individual graph nodes, passing state between them.

Node pipeline:
  embed_query → retrieve_context → fetch_graph_context → rerank_context
              → generate_answer
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.embeddings import embed_single
from app.core.logging import get_logger
from app.rag.prompts import (
    GRAPH_CONTEXT_EMPTY,
    GRAPH_CONTEXT_TEMPLATE,
    INSUFFICIENT_CONTEXT_ANSWER,
    SYSTEM_PROMPT,
    build_rag_prompt,
)
from app.rag.state import RagState
from app.services.embedding_service import (
    COLLECTION_NAME,
    EmbeddingService,
    _F_LANGUAGE,
    _F_REPO_ID,
    _F_SYMBOL_KIND,
)

logger = get_logger(__name__)


# ── Node 1: embed_query ───────────────────────────────────────────────────────


def embed_query(state: RagState) -> RagState:
    """Embed the user question into a vector for Qdrant search.

    Args:
        state: Current agent state with ``question`` populated.

    Returns:
        Updated state with ``query_vector`` set.
    """
    question = state["question"]
    logger.debug("embedding_query", question=question[:80])
    try:
        vector = embed_single(question)
        return {**state, "query_vector": vector}
    except Exception as exc:
        logger.error("embed_query_failed", error=str(exc))
        return {**state, "error": f"Embedding failed: {exc}"}


# ── Node 2: retrieve_context ──────────────────────────────────────────────────


def retrieve_context(state: RagState) -> RagState:
    """Search Qdrant with the embedded query vector and retrieve top-K chunks.

    Uses the pre-computed ``query_vector`` from ``embed_query`` to avoid a
    second embedding API call.

    Args:
        state: Current agent state with ``query_vector`` populated.

    Returns:
        Updated state with ``raw_hits`` populated.
    """
    if state.get("error"):
        return state

    vector = state.get("query_vector")
    if not vector:
        return {**state, "error": "query_vector is missing."}

    repo_ids: list[str] = state.get("repo_ids") or []
    language: str | None = state.get("language")
    limit: int = state.get("context_limit", 8)

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels

        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=20,
        )

        must: list[qmodels.Condition] = []
        if repo_ids:
            must.append(
                qmodels.FieldCondition(
                    key=_F_REPO_ID,
                    match=qmodels.MatchAny(any=repo_ids),
                )
            )
        if language:
            must.append(
                qmodels.FieldCondition(
                    key=_F_LANGUAGE,
                    match=qmodels.MatchValue(value=language),
                )
            )

        qdrant_filter = qmodels.Filter(must=must) if must else None

        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=qdrant_filter,
            limit=min(limit * 3, 30),  # over-fetch for reranking
            score_threshold=0.2,
            with_payload=True,
        )

        raw_hits = [
            {**hit.payload, "score": hit.score}
            for hit in results
        ]
        logger.debug("retrieved_hits", count=len(raw_hits))
        return {**state, "raw_hits": raw_hits}

    except Exception as exc:
        logger.error("retrieve_context_failed", error=str(exc))
        return {**state, "raw_hits": [], "error": f"Retrieval failed: {exc}"}


# ── Node 3: fetch_graph_context ───────────────────────────────────────────────


def fetch_graph_context(state: RagState) -> RagState:
    """Query Neo4j for call graph relationships of retrieved symbols.

    For the top-5 retrieved symbols, fetches their direct callers and
    callees to provide structural context to the LLM.

    Args:
        state: Current agent state with ``raw_hits`` populated.

    Returns:
        Updated state with ``graph_context`` string set.
    """
    if state.get("error"):
        return {**state, "graph_context": GRAPH_CONTEXT_EMPTY}

    hits = state.get("raw_hits") or []
    if not hits:
        return {**state, "graph_context": GRAPH_CONTEXT_EMPTY}

    # Only query graph for the top 5 unique symbols
    top_names = list({h.get("qualified_name", "") for h in hits[:5] if h.get("qualified_name")})
    if not top_names:
        return {**state, "graph_context": GRAPH_CONTEXT_EMPTY}

    repo_ids: list[str] = state.get("repo_ids") or []

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

        lines: list[str] = []
        with driver.session() as session:
            for qname in top_names:
                # Find callers and callees for this symbol
                result = session.run(
                    """
                    MATCH (s:Symbol {qualified_name: $qname})
                    WHERE ($repo_ids = [] OR s.repo_id IN $repo_ids)
                    OPTIONAL MATCH (caller:Symbol)-[:CALLS]->(s)
                    OPTIONAL MATCH (s)-[:CALLS]->(callee:Symbol)
                    RETURN
                        s.qualified_name AS sym,
                        collect(DISTINCT caller.qualified_name)[..5] AS callers,
                        collect(DISTINCT callee.qualified_name)[..5] AS callees
                    LIMIT 1
                    """,
                    qname=qname,
                    repo_ids=repo_ids,
                )
                record = result.single()
                if record:
                    callers = [c for c in (record["callers"] or []) if c]
                    callees = [c for c in (record["callees"] or []) if c]
                    if callers:
                        lines.append(f"- `{qname}` is called by: " + ", ".join(f"`{c}`" for c in callers))
                    if callees:
                        lines.append(f"- `{qname}` calls: " + ", ".join(f"`{c}`" for c in callees))

        driver.close()

        if not lines:
            return {**state, "graph_context": GRAPH_CONTEXT_EMPTY}

        graph_context = GRAPH_CONTEXT_TEMPLATE.format(relationships="\n".join(lines))
        return {**state, "graph_context": graph_context}

    except Exception as exc:
        logger.warning("graph_context_failed", error=str(exc))
        return {**state, "graph_context": GRAPH_CONTEXT_EMPTY}


# ── Node 4: rerank_context ────────────────────────────────────────────────────


def rerank_context(state: RagState) -> RagState:
    """Rerank retrieved hits and select the final context window.

    If a cross-encoder reranker is available (``BAAI/bge-reranker-base``),
    uses it to score (question, chunk) pairs. Falls back to the original
    Qdrant scores when the reranker is not installed.

    Args:
        state: Current agent state with ``raw_hits`` populated.

    Returns:
        Updated state with ``context_chunks`` set to the top-K reranked items.
    """
    if state.get("error"):
        return {**state, "context_chunks": []}

    hits = state.get("raw_hits") or []
    limit = state.get("context_limit", 8)
    question = state.get("question", "")

    if not hits:
        return {**state, "context_chunks": []}

    # Deduplicate by symbol_id, keeping best score
    seen: dict[str, dict] = {}
    for hit in hits:
        sid = hit.get("symbol_id", "")
        if sid not in seen or hit["score"] > seen[sid]["score"]:
            seen[sid] = hit
    deduped = list(seen.values())

    # Attempt cross-encoder reranking
    try:
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)
        pairs = [(question, h.get("chunk_text", "")) for h in deduped]
        scores = reranker.predict(pairs)
        for hit, score in zip(deduped, scores):
            hit["score"] = float(score)
        logger.debug("reranker_applied", count=len(deduped))
    except Exception:
        pass  # Use original Qdrant scores

    ranked = sorted(deduped, key=lambda x: x["score"], reverse=True)
    return {**state, "context_chunks": ranked[:limit]}


# ── Node 5: generate_answer ───────────────────────────────────────────────────


def generate_answer(state: RagState) -> RagState:
    """Generate the final answer using an LLM with the retrieved context.

    Supports OpenAI, Anthropic, and Ollama backends. The provider is
    selected via ``state["llm_provider"]``, defaulting to
    ``settings.llm_provider``.

    Args:
        state: Current agent state with ``context_chunks`` and ``graph_context``.

    Returns:
        Updated state with ``answer``, ``model_used``, and ``tokens_used``.
    """
    if state.get("error"):
        return {
            **state,
            "answer": INSUFFICIENT_CONTEXT_ANSWER,
            "model_used": "none",
            "tokens_used": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    chunks = state.get("context_chunks") or []
    graph_context = state.get("graph_context") or GRAPH_CONTEXT_EMPTY
    question = state.get("question", "")

    if not chunks:
        return {
            **state,
            "answer": INSUFFICIENT_CONTEXT_ANSWER,
            "model_used": "none",
            "tokens_used": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    user_prompt = build_rag_prompt(question, chunks, graph_context)

    provider = (state.get("llm_provider") or getattr(settings, "llm_provider", "openai")).lower()
    model = state.get("llm_model") or getattr(settings, "llm_model", "gpt-4o-mini")

    t0 = time.perf_counter()
    answer, tokens, model_used = _call_llm(provider, model, user_prompt)
    took_ms = (time.perf_counter() - t0) * 1000

    return {
        **state,
        "answer": answer,
        "model_used": model_used,
        "tokens_used": tokens,
        "took_ms": took_ms,
    }


# ── LLM dispatch ──────────────────────────────────────────────────────────────


def _call_llm(
    provider: str,
    model: str,
    user_prompt: str,
) -> tuple[str, dict[str, int], str]:
    """Dispatch to the appropriate LLM provider.

    Args:
        provider: Provider slug (openai | anthropic | ollama).
        model: Model identifier string.
        user_prompt: The fully rendered user prompt.

    Returns:
        Tuple of (answer_text, tokens_dict, model_used_string).
    """
    if provider == "openai":
        return _call_openai(model, user_prompt)
    elif provider == "anthropic":
        return _call_anthropic(model, user_prompt)
    elif provider in ("ollama", "local"):
        return _call_ollama(model, user_prompt)
    else:
        logger.warning("unknown_llm_provider", provider=provider)
        return _call_openai(model, user_prompt)


def _call_openai(model: str, user_prompt: str) -> tuple[str, dict[str, int], str]:
    """Call OpenAI Chat Completions API.

    Args:
        model: OpenAI model name (e.g. ``"gpt-4o-mini"``).
        user_prompt: Rendered user prompt string.

    Returns:
        Tuple of (answer, tokens_dict, model_used).
    """
    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    answer = response.choices[0].message.content or ""
    usage = response.usage
    tokens = {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }
    return answer, tokens, f"openai/{model}"


def _call_anthropic(model: str, user_prompt: str) -> tuple[str, dict[str, int], str]:
    """Call Anthropic Messages API.

    Args:
        model: Anthropic model name (e.g. ``"claude-3-5-sonnet-20241022"``).
        user_prompt: Rendered user prompt string.

    Returns:
        Tuple of (answer, tokens_dict, model_used).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=2048,
        temperature=0.1,
    )
    answer = response.content[0].text if response.content else ""
    tokens = {
        "prompt_tokens": response.usage.input_tokens,
        "completion_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
    }
    return answer, tokens, f"anthropic/{model}"


def _call_ollama(model: str, user_prompt: str) -> tuple[str, dict[str, int], str]:
    """Call a local Ollama model via its HTTP API.

    Args:
        model: Ollama model tag (e.g. ``"llama3.1:8b"``).
        user_prompt: Rendered user prompt string.

    Returns:
        Tuple of (answer, tokens_dict, model_used).
    """
    import httpx

    ollama_base = getattr(settings, "ollama_base_url", "http://localhost:11434")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    response = httpx.post(
        f"{ollama_base}/api/chat",
        json=payload,
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    answer = data.get("message", {}).get("content", "")
    tokens = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
        "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
    }
    return answer, tokens, f"ollama/{model}"
