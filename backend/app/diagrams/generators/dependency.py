"""Module dependency graph generator (Mermaid graph TD)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_dependency(
    repo_name: str,
    import_edges: list[dict[str, Any]],
    *,
    max_nodes: int = 40,
) -> str:
    """Generate a Mermaid module dependency diagram from import graph edges.

    Args:
        repo_name: Repository display name.
        import_edges: List of dicts with source, target, weight from Neo4j.
        max_nodes: Cap on total unique nodes to keep the diagram readable.

    Returns:
        Mermaid source string.
    """
    if not import_edges:
        return _empty_diagram(repo_name)

    # Collect unique nodes and trim by max_nodes
    nodes: dict[str, str] = {}  # path → safe_id
    edges: list[tuple[str, str, int]] = []

    for edge in import_edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        weight = int(edge.get("weight", 1))
        if not src or not tgt:
            continue
        if src not in nodes:
            if len(nodes) >= max_nodes:
                continue
            nodes[src] = _safe_id(src)
        if tgt not in nodes:
            if len(nodes) >= max_nodes:
                continue
            nodes[tgt] = _safe_id(tgt)
        edges.append((src, tgt, weight))

    if not edges:
        return _empty_diagram(repo_name)

    lines = ["graph TD"]
    lines.append(f"    %% {repo_name} — Module Dependency Graph")

    # Node declarations with short labels
    for path, safe in nodes.items():
        label = _short_label(path)
        lines.append(f'    {safe}["{label}"]')

    # Edges
    for src, tgt, weight in edges:
        src_id = nodes[src]
        tgt_id = nodes[tgt]
        if weight > 3:
            lines.append(f"    {src_id} ==> {tgt_id}")
        else:
            lines.append(f"    {src_id} --> {tgt_id}")

    return "\n".join(lines)


def generate_dependency_from_symbols(
    repo_name: str,
    symbols: list[dict[str, Any]],
    *,
    max_nodes: int = 35,
) -> str:
    """Fallback: build dependency graph from file paths of parsed symbols.

    Groups symbols by directory, creates directory-level nodes, and infers
    edges from symbols that reference other modules.

    Args:
        repo_name: Repository name.
        symbols: List of symbol dicts with file_path.
        max_nodes: Maximum directory nodes.

    Returns:
        Mermaid source string.
    """
    if not symbols:
        return _empty_diagram(repo_name)

    # Group files by top-level directory
    dirs: dict[str, int] = {}
    for sym in symbols:
        fp = sym.get("file_path", "")
        parts = fp.split("/")
        d = parts[0] if len(parts) > 1 else "(root)"
        dirs[d] = dirs.get(d, 0) + 1

    top_dirs = sorted(dirs.items(), key=lambda x: -x[1])[:max_nodes]

    lines = ["graph LR"]
    lines.append(f"    %% {repo_name} — Directory Overview")
    for d, count in top_dirs:
        safe = _safe_id(d)
        lines.append(f'    {safe}["{d}<br/>({count} symbols)"]')

    return "\n".join(lines)


def _safe_id(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", path)


def _short_label(path: str) -> str:
    parts = Path(path).parts
    if len(parts) <= 2:
        return path
    return f"…/{'/'.join(parts[-2:])}"


def _empty_diagram(repo_name: str) -> str:
    return f'graph TD\n    A["{repo_name}"]\n    A --> B["No import data available"]'
