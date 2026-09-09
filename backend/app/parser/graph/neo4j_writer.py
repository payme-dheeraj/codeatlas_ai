"""Neo4j batch writer for the code knowledge graph.

Writes nodes and relationships in idempotent batches using ``MERGE`` so
that re-indexing a repository does not create duplicate graph elements.

Graph schema
────────────

Nodes
  (:Repository {id, name, url})
  (:File       {id, path, language, file_type, repo_id})
  (:Symbol     {id, name, qualified_name, kind, repo_id, file_path,
                start_line, end_line, signature, docstring})

Relationships
  (:Repository)-[:CONTAINS]->(:File)
  (:File)-[:DEFINES]->(:Symbol)
  (:Symbol)-[:CALLS]->(:Symbol)     — call graph edges
  (:File)-[:IMPORTS]->(:File)       — import/dependency edges
  (:Symbol)-[:MEMBER_OF]->(:Symbol) — method → enclosing class
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.parser.base import SymbolData

logger = get_logger(__name__)

# Batch sizes for bulk Neo4j writes
_NODE_BATCH = 200
_REL_BATCH = 500


class Neo4jWriter:
    """Idempotent Neo4j graph writer for code symbol data.

    Uses a synchronous Neo4j driver (bolt) since this runs inside Celery
    workers which are not async.

    Attributes:
        _driver: neo4j.Driver instance.
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        """Initialise a Neo4j driver.

        Args:
            uri: Bolt URI (e.g. ``bolt://neo4j:7687``).
            user: Neo4j username.
            password: Neo4j password.
        """
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        """Close the underlying Neo4j driver."""
        self._driver.close()

    def ensure_constraints(self) -> None:
        """Create uniqueness constraints and indexes if they do not exist.

        Safe to call multiple times — uses ``CREATE CONSTRAINT IF NOT EXISTS``.
        """
        constraints = [
            "CREATE CONSTRAINT repo_id_unique IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT file_id_unique IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE",
            "CREATE CONSTRAINT symbol_id_unique IF NOT EXISTS FOR (s:Symbol) REQUIRE s.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX file_repo_path IF NOT EXISTS FOR (f:File) ON (f.repo_id, f.path)",
            "CREATE INDEX symbol_repo IF NOT EXISTS FOR (s:Symbol) ON (s.repo_id)",
            "CREATE INDEX symbol_name IF NOT EXISTS FOR (s:Symbol) ON (s.name)",
            "CREATE INDEX symbol_kind IF NOT EXISTS FOR (s:Symbol) ON (s.kind)",
        ]
        with self._driver.session() as session:
            for stmt in constraints + indexes:
                try:
                    session.run(stmt)
                except Exception as exc:
                    logger.warning("neo4j_constraint_error", stmt=stmt, error=str(exc))

    def upsert_repository(self, repo_id: str, name: str, url: str | None) -> None:
        """Create or update the Repository node.

        Args:
            repo_id: UUID string of the repository.
            name: Repository name.
            url: Optional clone URL.
        """
        with self._driver.session() as session:
            session.run(
                """
                MERGE (r:Repository {id: $id})
                SET r.name = $name, r.url = $url
                """,
                id=repo_id,
                name=name,
                url=url or "",
            )

    def upsert_files(self, repo_id: str, files: list[dict[str, Any]]) -> None:
        """Batch upsert File nodes and :CONTAINS relationships.

        Args:
            repo_id: UUID string of the parent repository.
            files: List of dicts with keys: path, language, file_type.
        """
        batches = _chunk(files, _NODE_BATCH)
        with self._driver.session() as session:
            for batch in batches:
                session.run(
                    """
                    UNWIND $batch AS f
                    MERGE (file:File {id: f.id})
                    SET file.path      = f.path,
                        file.language  = f.language,
                        file.file_type = f.file_type,
                        file.repo_id   = f.repo_id
                    WITH file
                    MATCH (repo:Repository {id: $repo_id})
                    MERGE (repo)-[:CONTAINS]->(file)
                    """,
                    batch=[
                        {
                            "id": _file_node_id(repo_id, f["path"]),
                            "path": f["path"],
                            "language": f.get("language", "unknown"),
                            "file_type": f.get("file_type", "generic"),
                            "repo_id": repo_id,
                        }
                        for f in batch
                    ],
                    repo_id=repo_id,
                )

    def upsert_symbols(
        self, repo_id: str, file_path: str, symbols: list[SymbolData]
    ) -> dict[str, str]:
        """Batch upsert Symbol nodes and :DEFINES relationships.

        Args:
            repo_id: UUID string of the repository.
            file_path: Relative file path the symbols belong to.
            symbols: List of SymbolData instances.

        Returns:
            Dict mapping ``qualified_name`` → Neo4j node element ID.
        """
        if not symbols:
            return {}

        file_id = _file_node_id(repo_id, file_path)
        rows = [
            {
                "id": _symbol_node_id(repo_id, file_path, s.symbol_kind, s.qualified_name),
                "name": s.name,
                "qualified_name": s.qualified_name,
                "kind": s.symbol_kind,
                "repo_id": repo_id,
                "file_path": file_path,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "signature": s.signature or "",
                "docstring": s.docstring or "",
                "parent_name": s.parent_name or "",
            }
            for s in symbols
            if s.symbol_kind != "import"  # imports stored as relationships only
        ]

        name_to_node_id: dict[str, str] = {}
        batches = _chunk(rows, _NODE_BATCH)
        with self._driver.session() as session:
            for batch in batches:
                result = session.run(
                    """
                    UNWIND $batch AS s
                    MERGE (sym:Symbol {id: s.id})
                    SET sym.name           = s.name,
                        sym.qualified_name = s.qualified_name,
                        sym.kind           = s.kind,
                        sym.repo_id        = s.repo_id,
                        sym.file_path      = s.file_path,
                        sym.start_line     = s.start_line,
                        sym.end_line       = s.end_line,
                        sym.signature      = s.signature,
                        sym.docstring      = s.docstring,
                        sym.parent_name    = s.parent_name
                    WITH sym
                    MATCH (f:File {id: $file_id})
                    MERGE (f)-[:DEFINES]->(sym)
                    RETURN sym.id AS node_id, sym.qualified_name AS qname
                    """,
                    batch=batch,
                    file_id=file_id,
                )
                for record in result:
                    name_to_node_id[record["qname"]] = record["node_id"]

        return name_to_node_id

    def upsert_call_edges(
        self,
        repo_id: str,
        file_path: str,
        symbols: list[SymbolData],
    ) -> int:
        """Create :CALLS edges between symbols based on call data.

        Args:
            repo_id: UUID string of the repository.
            file_path: Source file path (for scoping caller symbols).
            symbols: SymbolData list with populated ``calls`` lists.

        Returns:
            Number of :CALLS relationships created or merged.
        """
        edges: list[dict[str, str]] = []
        for sym in symbols:
            caller_id = _symbol_node_id(
                repo_id, file_path, sym.symbol_kind, sym.qualified_name
            )
            for callee_name in sym.calls:
                edges.append(
                    {"caller_id": caller_id, "callee_name": callee_name, "repo_id": repo_id}
                )

        if not edges:
            return 0

        count = 0
        with self._driver.session() as session:
            for batch in _chunk(edges, _REL_BATCH):
                result = session.run(
                    """
                    UNWIND $batch AS e
                    MATCH (caller:Symbol {id: e.caller_id})
                    MATCH (callee:Symbol {name: e.callee_name, repo_id: e.repo_id})
                    MERGE (caller)-[r:CALLS]->(callee)
                    RETURN count(r) AS cnt
                    """,
                    batch=batch,
                )
                for record in result:
                    count += record["cnt"]
        return count

    def upsert_member_of_edges(self, repo_id: str, symbols: list[SymbolData]) -> int:
        """Create :MEMBER_OF edges from methods to their enclosing class.

        Args:
            repo_id: UUID string of the repository.
            symbols: SymbolData list; methods with ``parent_name`` set.

        Returns:
            Number of :MEMBER_OF relationships created or merged.
        """
        edges = [
            {
                "child_name": s.qualified_name,
                "parent_name": s.parent_name,
                "repo_id": repo_id,
            }
            for s in symbols
            if s.parent_name and s.symbol_kind in ("method", "function")
        ]
        if not edges:
            return 0

        count = 0
        with self._driver.session() as session:
            for batch in _chunk(edges, _REL_BATCH):
                result = session.run(
                    """
                    UNWIND $batch AS e
                    MATCH (child:Symbol  {qualified_name: e.child_name,  repo_id: e.repo_id})
                    MATCH (parent:Symbol {name: e.parent_name, repo_id: e.repo_id,
                                          kind: 'class'})
                    MERGE (child)-[r:MEMBER_OF]->(parent)
                    RETURN count(r) AS cnt
                    """,
                    batch=batch,
                )
                for record in result:
                    count += record["cnt"]
        return count

    def delete_repo_graph(self, repo_id: str) -> None:
        """Delete all graph nodes and relationships for a repository.

        Args:
            repo_id: UUID string of the repository to purge.
        """
        with self._driver.session() as session:
            session.run(
                """
                MATCH (r:Repository {id: $repo_id})
                OPTIONAL MATCH (r)-[:CONTAINS]->(f:File)
                OPTIONAL MATCH (f)-[:DEFINES]->(s:Symbol)
                DETACH DELETE r, f, s
                """,
                repo_id=repo_id,
            )
        logger.info("neo4j_repo_deleted", repo_id=repo_id)


# ── Utilities ──────────────────────────────────────────────────────────────────


def _chunk(lst: list, size: int) -> list[list]:
    """Split a list into fixed-size batches.

    Args:
        lst: The input list.
        size: Maximum batch size.

    Returns:
        List of sub-lists.
    """
    return [lst[i: i + size] for i in range(0, len(lst), size)]


def _file_node_id(repo_id: str, file_path: str) -> str:
    """Deterministic stable ID for a File node.

    Args:
        repo_id: Repository UUID string.
        file_path: Relative file path.

    Returns:
        Hex UUID string derived from repo_id + file_path.
    """
    return str(uuid.uuid5(uuid.UUID(repo_id), f"file:{file_path}"))


def _symbol_node_id(
    repo_id: str, file_path: str, kind: str, qualified_name: str
) -> str:
    """Deterministic stable ID for a Symbol node.

    Args:
        repo_id: Repository UUID string.
        file_path: Relative file path.
        kind: Symbol kind string.
        qualified_name: Fully qualified symbol name.

    Returns:
        Hex UUID string derived from composite key.
    """
    return str(
        uuid.uuid5(
            uuid.UUID(repo_id),
            f"symbol:{file_path}:{kind}:{qualified_name}",
        )
    )
