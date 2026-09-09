"""ADR (Architecture Decision Record) generator.

Detects major technology choices from the parsed symbol graph and
repository metadata, then uses the LLM to generate templated ADRs.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.docs_gen._llm import call_llm

logger = get_logger(__name__)

_SYSTEM = (
    "You are a software architect. Generate Architecture Decision Records (ADRs) "
    "in the MADR/Nygard template format. Each ADR should explain why a technology "
    "choice was made based on the evidence in the codebase."
)

_PROMPT = """\
Generate Architecture Decision Records for the following technology choices detected in the codebase.

## Repository: {repo_name}
## Detected Tech Stack: {tech_stack}
## Key Dependencies: {dependencies}
## Infrastructure: {infrastructure}

---

Generate one ADR for each significant technology decision (up to 5 ADRs). Follow this template exactly:

```
# ADR-{{number}}: {{Title}}

**Date:** {{YYYY-MM-DD}}
**Status:** Accepted

## Context
{{Why was this decision needed? What problem does it solve?}}

## Decision
{{What was decided? What technology/pattern was chosen?}}

## Consequences

### Positive
- {{benefit 1}}
- {{benefit 2}}

### Negative
- {{trade-off 1}}

## Alternatives Considered
- {{alternative 1}}: {{why rejected}}

*Source files: {{file citations}}*
```

Respond with ONLY the Markdown ADR content — no preamble.
"""


def generate_adrs(
    repo_name: str,
    repo_context: dict[str, Any],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate ADR documents for major technology choices.

    Args:
        repo_name: Repository display name.
        repo_context: Dict with tech_stack, dependencies, infrastructure.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Generated Markdown string containing multiple ADR sections.
    """
    prompt = _PROMPT.format(
        repo_name=repo_name,
        tech_stack=", ".join(repo_context.get("tech_stack", [])) or "Unknown",
        dependencies=repo_context.get("key_dependencies", "(not analyzed)"),
        infrastructure=repo_context.get("infra_info", "(none detected)"),
    )

    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")

    logger.info("generating_adrs", repo=repo_name)
    return call_llm(provider, model, _SYSTEM, prompt, max_tokens=4096)


def _detect_tech_decisions(symbols: list[dict[str, Any]], tech_stack: list[str]) -> list[str]:
    """Identify significant technology decisions from symbols and tech stack.

    Args:
        symbols: Parsed symbol dicts.
        tech_stack: Detected tech stack list from repository metadata.

    Returns:
        List of technology decision strings.
    """
    decisions = []
    all_files = " ".join(s.get("file_path", "") for s in symbols).lower()

    checks = [
        ("postgresql", "PostgreSQL as relational database"),
        ("redis", "Redis for caching and session storage"),
        ("celery", "Celery for asynchronous task processing"),
        ("fastapi", "FastAPI as the web framework"),
        ("sqlalchemy", "SQLAlchemy as the ORM"),
        ("docker", "Docker for containerization"),
        ("kubernetes", "Kubernetes for container orchestration"),
        ("neo4j", "Neo4j as a graph database"),
        ("qdrant", "Qdrant as a vector database"),
        ("langgraph", "LangGraph for AI agent orchestration"),
    ]

    for keyword, description in checks:
        if keyword in all_files or any(keyword in t.lower() for t in tech_stack):
            decisions.append(description)

    return decisions
