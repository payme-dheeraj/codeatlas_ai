"""API Reference generator.

Extracts route-like symbols from parsed symbols and generates structured
Markdown documentation for each endpoint, grouped by tag/module.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.docs_gen._llm import call_llm

logger = get_logger(__name__)

_SYSTEM = (
    "You are an expert API documentation writer. Generate clear, structured "
    "Markdown API reference documentation from the provided route and symbol information. "
    "Follow RESTful documentation conventions. Use tables for request/response fields."
)

_PROMPT = """\
Generate API Reference documentation for the following routes extracted from the codebase.

## Repository: {repo_name}
## Language / Framework: {language} / {framework}

## Routes and Symbols
{routes_block}

---

For each route, document:
1. HTTP method and path as a heading
2. One-line description
3. Authentication requirements (if detectable)
4. Request body fields table (if applicable)
5. Response schemas (200, 4xx)
6. Source file citation

Format each route as:
```
## METHOD /path

Description.

**Auth:** Bearer JWT / API Key / None

**Request Body**
| Field | Type | Required | Description |
...

**Response 200**
...json example...

*Source: `file_path:start_line-end_line`*
```

Respond with ONLY Markdown — no preamble.
"""

_FALLBACK_TEMPLATE = """\
# API Reference — {repo_name}

*Auto-generated from {count} detected route symbols.*

{routes_md}
"""


def generate_api_reference(
    repo_name: str,
    symbols: list[dict[str, Any]],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate API reference documentation from route symbols.

    Args:
        repo_name: Repository display name.
        symbols: List of symbol dicts with kind in (function, method, route).
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Generated Markdown string.
    """
    route_symbols = _extract_route_symbols(symbols)

    if not route_symbols:
        return f"# API Reference — {repo_name}\n\n*No API routes detected.*\n"

    language = _infer_language(symbols)
    framework = _infer_framework(symbols)

    routes_block = _format_routes_for_prompt(route_symbols)

    prompt = _PROMPT.format(
        repo_name=repo_name,
        language=language,
        framework=framework,
        routes_block=routes_block,
    )

    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")

    logger.info("generating_api_reference", repo=repo_name, routes=len(route_symbols))
    return call_llm(provider, model, _SYSTEM, prompt, max_tokens=4096)


def _extract_route_symbols(symbols: list[dict]) -> list[dict]:
    """Filter and rank symbols that look like API route handlers.

    Heuristic: symbols with 'route', 'endpoint', 'handler', or HTTP method
    keywords in their name, or decorated with @router/@app decorators.

    Args:
        symbols: All parsed symbol dicts for the repository.

    Returns:
        Filtered list of likely route symbols.
    """
    route_kws = frozenset({"get", "post", "put", "patch", "delete", "router", "endpoint", "handler", "route", "view"})
    decorator_kws = frozenset({"router", "app", "blueprint", "resource"})
    result = []
    for sym in symbols:
        name_lower = sym.get("name", "").lower()
        decorators = [d.lower() for d in (sym.get("extra", {}) or {}).get("decorators", [])]

        if any(kw in name_lower for kw in route_kws):
            result.append(sym)
            continue
        if any(any(dk in d for dk in decorator_kws) for d in decorators):
            result.append(sym)
    return result[:100]  # cap to avoid overly long prompt


def _format_routes_for_prompt(symbols: list[dict]) -> str:
    """Format route symbols into a structured text block for the LLM prompt.

    Args:
        symbols: List of route symbol dicts.

    Returns:
        Formatted text block string.
    """
    lines = []
    for sym in symbols:
        lines.append(
            f"### {sym.get('qualified_name', sym.get('name', 'unknown'))}"
            f"  ({sym.get('symbol_kind', 'function')})"
        )
        lines.append(f"- **File:** `{sym.get('file_path', '')}` "
                     f"(lines {sym.get('start_line', 0)}-{sym.get('end_line', 0)})")
        if sym.get("signature"):
            lines.append(f"- **Signature:** `{sym['signature']}`")
        if sym.get("docstring"):
            lines.append(f"- **Docstring:** {sym['docstring'][:300]}")
        lines.append("")
    return "\n".join(lines)


def _infer_language(symbols: list[dict]) -> str:
    langs = [s.get("language", "") for s in symbols if s.get("language")]
    if not langs:
        return "unknown"
    from collections import Counter
    return Counter(langs).most_common(1)[0][0]


def _infer_framework(symbols: list[dict]) -> str:
    all_text = " ".join(
        (s.get("file_path", "") + " " + s.get("qualified_name", "")).lower()
        for s in symbols
    )
    if "fastapi" in all_text or "router" in all_text:
        return "FastAPI"
    if "flask" in all_text:
        return "Flask"
    if "django" in all_text:
        return "Django"
    if "express" in all_text:
        return "Express.js"
    if "gin" in all_text:
        return "Gin"
    if "spring" in all_text:
        return "Spring Boot"
    return "Unknown"
