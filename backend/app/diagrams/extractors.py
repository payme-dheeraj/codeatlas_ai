"""Data extractors for diagram generation.

Pulls structured data from Neo4j, PostgreSQL parsed symbols, and
raw repository files (docker-compose, K8s, etc.) to feed the diagram generators.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Neo4j extractors ──────────────────────────────────────────────────────────


def extract_import_graph(
    driver,
    repo_id: str,
    *,
    limit: int = 150,
) -> list[dict[str, Any]]:
    """Pull file-level import relationships from Neo4j for dependency diagrams.

    Executes the PRD Cypher query and returns edge list dicts.

    Args:
        driver: Neo4j synchronous driver instance.
        repo_id: UUID string of the repository.
        limit: Maximum number of edges to return.

    Returns:
        List of dicts with keys: source, target, weight.
    """
    cypher = """
    MATCH (f1:File)-[:IMPORTS]->(f2:File)
    WHERE f1.repo_id = $repo_id
    RETURN f1.path AS source, f2.path AS target, count(*) AS weight
    ORDER BY weight DESC
    LIMIT $limit
    """
    try:
        with driver.session() as session:
            result = session.run(cypher, repo_id=repo_id, limit=limit)
            return [{"source": r["source"], "target": r["target"], "weight": r["weight"]} for r in result]
    except Exception as exc:
        logger.warning("neo4j_import_graph_failed", error=str(exc))
        return []


def extract_call_graph(
    driver,
    repo_id: str,
    *,
    focus_symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Pull function call relationships from Neo4j for sequence diagrams.

    Args:
        driver: Neo4j synchronous driver instance.
        repo_id: UUID string.
        focus_symbol: Optional symbol name to center the graph on.
        limit: Maximum edges to return.

    Returns:
        List of dicts with keys: caller, callee, file.
    """
    if focus_symbol:
        cypher = """
        MATCH (s1:Symbol {repo_id: $repo_id, name: $focus})-[:CALLS*1..3]->(s2:Symbol)
        RETURN s1.qualified_name AS caller, s2.qualified_name AS callee,
               s1.file_path AS file
        LIMIT $limit
        """
        params = {"repo_id": repo_id, "focus": focus_symbol, "limit": limit}
    else:
        cypher = """
        MATCH (s1:Symbol {repo_id: $repo_id})-[:CALLS]->(s2:Symbol)
        RETURN s1.qualified_name AS caller, s2.qualified_name AS callee,
               s1.file_path AS file
        ORDER BY s1.file_path
        LIMIT $limit
        """
        params = {"repo_id": repo_id, "limit": limit}

    try:
        with driver.session() as session:
            result = session.run(cypher, **params)
            return [{"caller": r["caller"], "callee": r["callee"], "file": r["file"]} for r in result]
    except Exception as exc:
        logger.warning("neo4j_call_graph_failed", error=str(exc))
        return []


# ── PostgreSQL extractors ─────────────────────────────────────────────────────


def extract_orm_models(
    session,
    repo_id: str,
) -> list[dict[str, Any]]:
    """Extract class-kind symbols that look like ORM models for ER diagrams.

    Args:
        session: Synchronous SQLAlchemy session.
        repo_id: UUID string of the repository.

    Returns:
        List of symbol dicts with name, file_path, docstring, extra fields.
    """
    import uuid as _uuid
    from sqlalchemy import select
    from app.models.symbol import ParsedSymbol

    try:
        rows = session.execute(
            select(ParsedSymbol).where(
                ParsedSymbol.repo_id == _uuid.UUID(repo_id),
                ParsedSymbol.symbol_kind == "class",
            ).limit(100)
        ).scalars().all()
        return [
            {
                "name": s.name,
                "qualified_name": s.qualified_name,
                "file_path": s.file_path,
                "docstring": s.docstring or "",
                "extras": s.extras or {},
                "language": s.language,
            }
            for s in rows
        ]
    except Exception as exc:
        logger.warning("orm_model_extract_failed", error=str(exc))
        return []


def extract_symbols_by_kind(
    session,
    repo_id: str,
    kind: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Extract symbols of a specific kind from PostgreSQL.

    Args:
        session: Synchronous SQLAlchemy session.
        repo_id: UUID string.
        kind: Symbol kind (function, class, method, etc.).
        limit: Maximum rows.

    Returns:
        List of symbol attribute dicts.
    """
    import uuid as _uuid
    from sqlalchemy import select
    from app.models.symbol import ParsedSymbol

    try:
        rows = session.execute(
            select(ParsedSymbol).where(
                ParsedSymbol.repo_id == _uuid.UUID(repo_id),
                ParsedSymbol.symbol_kind == kind,
            ).limit(limit)
        ).scalars().all()
        return [
            {
                "name": s.name,
                "qualified_name": s.qualified_name,
                "file_path": s.file_path,
                "language": s.language,
                "extras": s.extras or {},
            }
            for s in rows
        ]
    except Exception as exc:
        logger.warning("symbol_extract_failed", kind=kind, error=str(exc))
        return []


# ── File-based extractors ─────────────────────────────────────────────────────


def extract_docker_compose_services(repo_path: str) -> list[dict[str, Any]]:
    """Parse docker-compose.yml to extract service definitions.

    Args:
        repo_path: Absolute path to the repository directory.

    Returns:
        List of dicts with keys: name, image, ports, depends_on, environment.
    """
    import yaml  # pyyaml

    for candidate in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        fpath = Path(repo_path) / candidate
        if fpath.exists():
            try:
                data = yaml.safe_load(fpath.read_text())
                services = data.get("services", {})
                result = []
                for name, cfg in services.items():
                    result.append({
                        "name": name,
                        "image": cfg.get("image", ""),
                        "build": bool(cfg.get("build")),
                        "ports": cfg.get("ports", []),
                        "depends_on": list(cfg.get("depends_on", {}).keys())
                        if isinstance(cfg.get("depends_on"), dict)
                        else cfg.get("depends_on", []),
                        "environment": cfg.get("environment", []),
                    })
                return result
            except Exception as exc:
                logger.warning("docker_compose_parse_failed", file=str(fpath), error=str(exc))
    return []


def extract_k8s_services(repo_path: str) -> list[dict[str, Any]]:
    """Scan for Kubernetes Service/Deployment manifests in the repo.

    Args:
        repo_path: Absolute path to the repository directory.

    Returns:
        List of dicts with keys: name, kind, namespace, containers, ports.
    """
    import yaml

    result = []
    base = Path(repo_path)
    for fpath in base.rglob("*.yaml"):
        try:
            docs = list(yaml.safe_load_all(fpath.read_text()))
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("kind", "")
                if kind not in ("Service", "Deployment", "StatefulSet", "DaemonSet"):
                    continue
                meta = doc.get("metadata", {})
                spec = doc.get("spec", {})
                containers = []
                for c in spec.get("template", {}).get("spec", {}).get("containers", []):
                    containers.append({
                        "name": c.get("name", ""),
                        "image": c.get("image", ""),
                        "ports": [p.get("containerPort") for p in c.get("ports", [])],
                    })
                result.append({
                    "name": meta.get("name", ""),
                    "kind": kind,
                    "namespace": meta.get("namespace", "default"),
                    "containers": containers,
                    "ports": spec.get("ports", []),
                })
        except Exception:
            continue
    return result


def extract_env_vars(repo_path: str) -> list[str]:
    """Extract environment variable names from .env.example or .env files.

    Args:
        repo_path: Absolute path to the repository directory.

    Returns:
        List of env var name strings.
    """
    base = Path(repo_path)
    var_names = []
    for candidate in (".env.example", ".env.sample", ".env.template", ".env"):
        fpath = base / candidate
        if fpath.exists():
            for line in fpath.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var_names.append(line.split("=")[0].strip())
            break
    return var_names
