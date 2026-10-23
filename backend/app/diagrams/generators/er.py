"""ER Diagram generator — infers entity-relationship structure from ORM models."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_er(
    repo_name: str,
    orm_models: list[dict[str, Any]],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate a Mermaid ER diagram from ORM class symbols.

    Heuristically extracts field names from docstrings and extras, then
    uses the LLM to infer cardinality relationships between models.

    Args:
        repo_name: Repository display name.
        orm_models: List of class symbol dicts from extractors.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Mermaid erDiagram source string.
    """
    if not orm_models:
        return _empty_er(repo_name)

    # Try heuristic-first, fall back to AI for relationships
    entity_blocks = _build_entity_blocks(orm_models)
    relationships = _ai_infer_relationships(repo_name, orm_models, llm_provider, llm_model)

    lines = ["erDiagram"]
    lines.append(f"    %% ER Diagram — {repo_name}")
    lines.append("")

    for block in entity_blocks:
        lines.extend(block)
        lines.append("")

    if relationships:
        lines.append("    %% Relationships")
        lines.extend(relationships)

    return "\n".join(lines)


def _build_entity_blocks(orm_models: list[dict]) -> list[list[str]]:
    """Build Mermaid entity definition blocks from ORM class symbols.

    Args:
        orm_models: Class symbol dicts.

    Returns:
        List of line-groups, one per entity.
    """
    blocks = []
    for model in orm_models[:20]:  # cap at 20 entities
        name = _mermaid_name(model.get("name", "Entity"))
        docstring = model.get("docstring", "")

        # Extract attribute hints from docstring (Attributes: ... section)
        attrs = _extract_attrs_from_docstring(docstring)

        block = [f"    {name} {{"]
        if attrs:
            for field_name, field_type in attrs[:10]:
                block.append(f"        {field_type} {field_name}")
        else:
            block.append("        string id PK")
        block.append("    }")
        blocks.append(block)

    return blocks


def _extract_attrs_from_docstring(docstring: str) -> list[tuple[str, str]]:
    """Parse field info from a Google-style docstring Attributes section.

    Args:
        docstring: Full docstring string.

    Returns:
        List of (field_name, type_hint) tuples.
    """
    result = []
    in_attrs = False
    attr_re = re.compile(r"^\s{4,}(\w+)\s*[:(]")

    for line in docstring.splitlines():
        if "Attributes:" in line:
            in_attrs = True
            continue
        if in_attrs:
            if line.strip() == "" and result:
                break
            m = attr_re.match(line)
            if m:
                field = m.group(1)
                # Infer a basic type
                lower = line.lower()
                if "uuid" in lower or " id" in lower:
                    ftype = "uuid"
                elif "str" in lower or "string" in lower or "text" in lower:
                    ftype = "string"
                elif "int" in lower or "integer" in lower:
                    ftype = "int"
                elif "float" in lower or "decimal" in lower:
                    ftype = "float"
                elif "bool" in lower:
                    ftype = "boolean"
                elif "datetime" in lower or "timestamp" in lower:
                    ftype = "timestamp"
                elif "dict" in lower or "json" in lower:
                    ftype = "jsonb"
                elif "list" in lower:
                    ftype = "array"
                else:
                    ftype = "string"
                result.append((field, ftype))
    return result


def _ai_infer_relationships(
    repo_name: str,
    orm_models: list[dict],
    llm_provider: str | None,
    llm_model: str | None,
) -> list[str]:
    """Use LLM to infer ER relationships between models.

    Args:
        repo_name: Repository name.
        orm_models: List of ORM class symbol dicts.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        List of Mermaid relationship lines (e.g. ``User ||--o{ Repository : "owns"``).
    """
    from app.docs_gen._llm import call_llm

    model_names = [m.get("name", "?") for m in orm_models[:15]]
    prompt = f"""\
Given these database entity names: {', '.join(model_names)}

Output ONLY the Mermaid erDiagram relationship lines (no entity blocks, no fences).
Example format:
    users ||--o{{ repositories : "owns"
    repositories ||--o{{ parsed_symbols : "contains"

Output ONLY relationship lines, nothing else.
"""
    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model_name = llm_model or getattr(settings, "llm_model", "llama3.2")
    system = "You are a database architect. Output only valid Mermaid erDiagram relationship lines."

    try:
        raw = call_llm(provider, model_name, system, prompt, max_tokens=600)
        lines = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped and ("||" in stripped or "|{" in stripped or "}|" in stripped):
                lines.append(f"    {stripped}")
        return lines
    except Exception as exc:
        logger.warning("er_relationship_ai_failed", error=str(exc))
        return []


def _mermaid_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _empty_er(repo_name: str) -> str:
    return (
        "erDiagram\n"
        f"    %% ER Diagram — {repo_name}\n"
        "    Entity {\n"
        "        uuid id PK\n"
        "    }\n"
    )
