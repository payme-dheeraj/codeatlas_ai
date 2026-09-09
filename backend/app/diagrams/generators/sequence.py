"""Sequence / Call Flow diagram generator (Mermaid sequenceDiagram)."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_sequence(
    repo_name: str,
    call_edges: list[dict[str, Any]],
    *,
    focus_symbol: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate a Mermaid sequence diagram from call graph edges.

    If call_edges is empty or focus_symbol is provided, falls back to
    AI-assisted generation using the symbol context.

    Args:
        repo_name: Repository display name.
        call_edges: List of dicts with caller, callee, file.
        focus_symbol: Optional symbol to center the diagram on.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Mermaid sequence diagram source string.
    """
    if call_edges:
        return _from_call_graph(repo_name, call_edges, focus_symbol)
    return _ai_generate(repo_name, focus_symbol, llm_provider, llm_model)


def _from_call_graph(
    repo_name: str,
    edges: list[dict],
    focus_symbol: str | None,
) -> str:
    """Build a sequence diagram from raw call graph edges.

    Groups callers and callees as participants and emits call arrows.

    Args:
        repo_name: Repository name.
        edges: Call graph edge list.
        focus_symbol: Optional focal symbol for title.

    Returns:
        Mermaid sequence diagram source string.
    """
    # Collect unique actors
    actors: dict[str, str] = {}  # full_name → short alias
    messages: list[str] = []

    def alias(name: str) -> str:
        if name not in actors:
            parts = name.split(".")
            short = parts[-1] if parts else name
            # Ensure uniqueness
            alias_str = short
            count = 1
            while alias_str in actors.values():
                alias_str = f"{short}{count}"
                count += 1
            actors[name] = alias_str
        return actors[name]

    for edge in edges[:30]:  # cap at 30 calls for readability
        caller = edge.get("caller", "Unknown")
        callee = edge.get("callee", "Unknown")
        c_alias = alias(caller)
        cc_alias = alias(callee)
        messages.append(f"    {c_alias}->>{cc_alias}: call")

    lines = ["sequenceDiagram"]
    if focus_symbol:
        lines.append(f"    %% Sequence for: {focus_symbol} — {repo_name}")
    else:
        lines.append(f"    %% Call flow — {repo_name}")

    for full_name, short in actors.items():
        lines.append(f"    participant {short} as {full_name.split('.')[-1]}")

    lines.extend(messages)
    return "\n".join(lines)


def _ai_generate(
    repo_name: str,
    focus_symbol: str | None,
    llm_provider: str | None,
    llm_model: str | None,
) -> str:
    """Use LLM to generate a representative sequence diagram.

    Args:
        repo_name: Repository name.
        focus_symbol: Optional function/endpoint to focus on.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Mermaid sequence diagram source string.
    """
    from app.docs_gen._llm import call_llm

    focus_hint = f" for the '{focus_symbol}' function/endpoint" if focus_symbol else ""
    prompt = f"""\
Generate a Mermaid sequenceDiagram{focus_hint} for the repository "{repo_name}".
Show the typical request-response flow through the main components (client, API, service layer, database).
Output ONLY valid Mermaid sequenceDiagram syntax — no explanation, no code fences.
"""
    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")
    system = "You are a software architect. Output only valid Mermaid sequenceDiagram syntax."

    try:
        return call_llm(provider, model, system, prompt, max_tokens=1200)
    except Exception as exc:
        logger.warning("sequence_ai_failed", error=str(exc))
        return (
            "sequenceDiagram\n"
            "    participant C as Client\n"
            "    participant API as API Layer\n"
            "    participant DB as Database\n"
            "    C->>API: request\n"
            "    API->>DB: query\n"
            "    DB-->>API: result\n"
            "    API-->>C: response\n"
        )
