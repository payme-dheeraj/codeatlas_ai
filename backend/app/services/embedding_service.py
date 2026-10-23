"""Embedding service — indexes symbols into Qdrant and executes vector search.

Responsibilities:
- Create and configure Qdrant collections with the correct vector dimension.
- Convert ParsedSymbol records into embedded text chunks and upsert them.
- Execute semantic and hybrid search queries with optional metadata filters.
- Provide a clean async interface around the synchronous Qdrant client.
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.core.embeddings import chunk_text, content_hash, embed_single, embed_texts, get_embedding_dim
from app.core.logging import get_logger

logger = get_logger(__name__)

# Name of the Qdrant collection that holds all symbol embeddings
COLLECTION_NAME = "code_symbols"

# Payload field names stored alongside each Qdrant vector point
_F_SYMBOL_ID = "symbol_id"
_F_REPO_ID = "repo_id"
_F_REPO_NAME = "repo_name"
_F_FILE_PATH = "file_path"
_F_LANGUAGE = "language"
_F_SYMBOL_KIND = "symbol_kind"
_F_NAME = "name"
_F_QUALIFIED_NAME = "qualified_name"
_F_START_LINE = "start_line"
_F_END_LINE = "end_line"
_F_SIGNATURE = "signature"
_F_DOCSTRING = "docstring"
_F_CHUNK_TEXT = "chunk_text"
_F_CHUNK_INDEX = "chunk_index"
_F_CONTENT_HASH = "content_hash"


def _make_client() -> QdrantClient:
    """Create and return a Qdrant client configured from settings.

    Returns:
        Connected QdrantClient instance.
    """
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=getattr(settings, "qdrant_api_key", None) or None,
        prefer_grpc=False,
        timeout=30,
    )


class EmbeddingService:
    """Manages symbol embeddings in Qdrant.

    Attributes:
        _client: Qdrant client instance.
        _dim: Embedding vector dimension from config.
    """

    def __init__(self) -> None:
        """Initialise the Qdrant client and ensure the collection exists."""
        self._client = _make_client()
        self._dim = get_embedding_dim()
        self._ensure_collection()

    # ── Collection management ─────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        """Create the Qdrant collection if it does not already exist.

        Uses cosine distance and enables payload indexing for the filter
        fields used in search queries.
        """
        existing = {c.name for c in self._client.get_collections().collections}
        if COLLECTION_NAME in existing:
            try:
                info = self._client.get_collection(COLLECTION_NAME)
                current_dim = info.config.params.vectors.size
            except Exception:
                current_dim = None
            if current_dim is not None and current_dim != self._dim:
                logger.warning(
                    "qdrant_collection_dim_mismatch_recreating",
                    collection=COLLECTION_NAME,
                    existing_dim=current_dim,
                    expected_dim=self._dim,
                )
                self._client.delete_collection(COLLECTION_NAME)
                existing.discard(COLLECTION_NAME)
        if COLLECTION_NAME not in existing:
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=qmodels.VectorParams(
                    size=self._dim,
                    distance=qmodels.Distance.COSINE,
                    on_disk=False,
                ),
                hnsw_config=qmodels.HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                ),
            )
            logger.info("qdrant_collection_created", collection=COLLECTION_NAME, dim=self._dim)
        else:
            logger.debug("qdrant_collection_exists", collection=COLLECTION_NAME)

        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Ensure payload indexes required by filtering and keyword search exist.

        Runs on every start (not just on collection creation) so that
        collections created by earlier versions gain the full-text indexes that
        ``search_by_text`` depends on — without them ``MatchText`` matches
        nothing and keyword search silently returns zero results.
        """
        keyword_fields = (_F_REPO_ID, _F_LANGUAGE, _F_SYMBOL_KIND, _F_FILE_PATH)
        text_fields = (_F_NAME, _F_QUALIFIED_NAME, _F_CHUNK_TEXT)

        for field, schema in [
            *((f, qmodels.PayloadSchemaType.KEYWORD) for f in keyword_fields),
            *((f, qmodels.PayloadSchemaType.TEXT) for f in text_fields),
        ]:
            try:
                self._client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name=field,
                    field_schema=schema,
                )
            except Exception as exc:  # noqa: BLE001 - index already exists is fine
                logger.debug(
                    "qdrant_payload_index_skipped",
                    field=field,
                    schema=str(schema),
                    error=str(exc),
                )

    def delete_repo_vectors(self, repo_id: str) -> int:
        """Delete all Qdrant points for a repository.

        Args:
            repo_id: UUID string of the repository to purge.

        Returns:
            Number of points deleted.
        """
        result = self._client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key=_F_REPO_ID,
                            match=qmodels.MatchValue(value=repo_id),
                        )
                    ]
                )
            ),
        )
        logger.info("qdrant_repo_deleted", repo_id=repo_id, status=str(result.status))
        # qdrant-client returns an UpdateResult (operation_id/status) and does
        # not report a deleted-count for filter-based deletes.
        return 0

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_symbols(
        self,
        symbols: list[dict[str, Any]],
        repo_name: str,
    ) -> int:
        """Embed and upsert a batch of symbol dicts into Qdrant.

        Each symbol may produce multiple points if its combined text exceeds
        the chunk size. Points are keyed by a deterministic UUID derived from
        ``symbol_id + chunk_index`` to make upserts idempotent.

        Args:
            symbols: List of symbol dicts with keys matching ParsedSymbol columns.
            repo_name: Display name of the repository (stored in payload).

        Returns:
            Number of Qdrant points upserted.
        """
        points: list[qmodels.PointStruct] = []

        for sym in symbols:
            chunks = self._build_chunks(sym)
            if not chunks:
                continue

            texts = [c["text"] for c in chunks]
            try:
                vectors = embed_texts(texts)
            except Exception as exc:
                logger.warning(
                    "embedding_failed",
                    symbol_id=sym.get("id"),
                    error=str(exc),
                )
                continue

            for chunk, vector in zip(chunks, vectors):
                point_id = str(
                    uuid.uuid5(
                        uuid.UUID(str(sym["id"])),
                        f"chunk:{chunk['chunk_index']}",
                    )
                )
                points.append(
                    qmodels.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            _F_SYMBOL_ID: str(sym["id"]),
                            _F_REPO_ID: str(sym["repo_id"]),
                            _F_REPO_NAME: repo_name,
                            _F_FILE_PATH: sym.get("file_path", ""),
                            _F_LANGUAGE: sym.get("language", ""),
                            _F_SYMBOL_KIND: sym.get("symbol_kind", ""),
                            _F_NAME: sym.get("name", ""),
                            _F_QUALIFIED_NAME: sym.get("qualified_name", ""),
                            _F_START_LINE: sym.get("start_line", 0),
                            _F_END_LINE: sym.get("end_line", 0),
                            _F_SIGNATURE: sym.get("signature") or "",
                            _F_DOCSTRING: sym.get("docstring") or "",
                            _F_CHUNK_TEXT: chunk["text"],
                            _F_CHUNK_INDEX: chunk["chunk_index"],
                            _F_CONTENT_HASH: content_hash(chunk["text"]),
                        },
                    )
                )

        if not points:
            return 0

        # Upsert in batches of 256
        batch_size = 256
        for i in range(0, len(points), batch_size):
            self._client.upsert(
                collection_name=COLLECTION_NAME,
                points=points[i: i + batch_size],
                wait=True,
            )

        logger.info("qdrant_upserted", count=len(points), repo_name=repo_name)
        return len(points)

    @staticmethod
    def _build_chunks(sym: dict[str, Any]) -> list[dict[str, Any]]:
        """Build text chunks from a symbol dict for embedding.

        Combines signature, docstring, and qualified name into a single
        text block and splits it if necessary.

        Args:
            sym: Symbol dict with keys matching ParsedSymbol columns.

        Returns:
            List of chunk dicts with ``text`` and ``chunk_index``.
        """
        parts: list[str] = []

        # Header line: kind + qualified name + signature
        header = f"{sym.get('symbol_kind', '')} {sym.get('qualified_name', '')}"
        if sym.get("signature"):
            header += f"\n{sym['signature']}"
        parts.append(header)

        if sym.get("docstring"):
            parts.append(sym["docstring"])

        # Include file path context
        if sym.get("file_path"):
            parts.append(f"file: {sym['file_path']}")

        combined = "\n\n".join(p for p in parts if p.strip())
        if not combined.strip():
            return []

        raw_chunks = chunk_text(combined, chunk_size=256, overlap=32)
        return [{"text": c, "chunk_index": i} for i, c in enumerate(raw_chunks)]

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        repo_ids: list[str] | None = None,
        language: str | None = None,
        symbol_kind: str | None = None,
        limit: int = 10,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Execute a semantic similarity search.

        Args:
            query: Natural language or code query string.
            repo_ids: Optional list of repository UUID strings to filter.
            language: Optional language slug filter.
            symbol_kind: Optional symbol kind filter.
            limit: Maximum results to return.
            min_score: Minimum cosine similarity threshold.

        Returns:
            List of result dicts sorted by descending score.
        """
        query_vector = embed_single(query)
        qdrant_filter = self._build_filter(repo_ids, language, symbol_kind)

        results = self._client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=limit * 2,  # over-fetch for dedup
            score_threshold=min_score,
            with_payload=True,
        )

        # Deduplicate by symbol_id, keeping highest-scoring chunk per symbol
        seen: dict[str, dict[str, Any]] = {}
        for hit in results:
            sid = hit.payload.get(_F_SYMBOL_ID, "")
            if sid not in seen or hit.score > seen[sid]["score"]:
                seen[sid] = {**hit.payload, "score": hit.score}

        sorted_hits = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
        return sorted_hits[:limit]

    def search_by_text(
        self,
        query: str,
        *,
        repo_ids: list[str] | None = None,
        language: str | None = None,
        symbol_kind: str | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Execute a keyword/text search using Qdrant payload scroll + filter.

        Matches the ``chunk_text`` payload field using a substring condition.
        Lower precision than semantic search but useful for exact identifiers.

        Args:
            query: Keyword or identifier to search for.
            repo_ids: Optional repository filter.
            language: Optional language filter.
            symbol_kind: Optional kind filter.
            limit: Maximum results.
            min_score: Ignored for keyword search (kept for API consistency).

        Returns:
            List of result dicts sorted by name match quality.
        """
        must_conditions = []
        if repo_ids:
            must_conditions.append(
                qmodels.FieldCondition(
                    key=_F_REPO_ID,
                    match=qmodels.MatchAny(any=repo_ids),
                )
            )
        if language:
            must_conditions.append(
                qmodels.FieldCondition(
                    key=_F_LANGUAGE,
                    match=qmodels.MatchValue(value=language),
                )
            )
        if symbol_kind:
            must_conditions.append(
                qmodels.FieldCondition(
                    key=_F_SYMBOL_KIND,
                    match=qmodels.MatchValue(value=symbol_kind),
                )
            )

        # Full-text match against the symbol name, its qualified name, or the
        # indexed chunk text. `should` gives OR semantics so a multi-word query
        # does not require every token to appear in the symbol name alone.
        text_conditions = [
            qmodels.FieldCondition(key=field, match=qmodels.MatchText(text=query))
            for field in (_F_NAME, _F_QUALIFIED_NAME, _F_CHUNK_TEXT)
        ]

        # Qdrant semantics: must AND (should_1 OR should_2 OR ...)
        scroll_filter = qmodels.Filter(
            must=must_conditions or None,
            should=text_conditions,
        )
        records, _ = self._client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [{**r.payload, "score": 1.0} for r in records]

    def hybrid_search(
        self,
        query: str,
        *,
        repo_ids: list[str] | None = None,
        language: str | None = None,
        symbol_kind: str | None = None,
        limit: int = 10,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Fuse semantic and keyword results using Reciprocal Rank Fusion.

        Args:
            query: Search query.
            repo_ids: Optional repository filter.
            language: Optional language filter.
            symbol_kind: Optional kind filter.
            limit: Maximum results.
            min_score: Semantic score threshold.

        Returns:
            RRF-fused ranked list of result dicts.
        """
        semantic = self.search(
            query,
            repo_ids=repo_ids,
            language=language,
            symbol_kind=symbol_kind,
            limit=limit,
            min_score=min_score,
        )
        keyword = self.search_by_text(
            query,
            repo_ids=repo_ids,
            language=language,
            symbol_kind=symbol_kind,
            limit=limit,
        )
        return _rrf_fuse(semantic, keyword, k=60, limit=limit)

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_filter(
        repo_ids: list[str] | None,
        language: str | None,
        symbol_kind: str | None,
    ) -> qmodels.Filter | None:
        """Construct a Qdrant filter from optional field constraints.

        Args:
            repo_ids: Optional list of repository UUID strings.
            language: Optional language slug.
            symbol_kind: Optional symbol kind string.

        Returns:
            QdrantFilter or None if no constraints are active.
        """
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
        if symbol_kind:
            must.append(
                qmodels.FieldCondition(
                    key=_F_SYMBOL_KIND,
                    match=qmodels.MatchValue(value=symbol_kind),
                )
            )
        return qmodels.Filter(must=must) if must else None


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────


def _rrf_fuse(
    list_a: list[dict[str, Any]],
    list_b: list[dict[str, Any]],
    k: int = 60,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    RRF score = Σ 1 / (k + rank_i)

    Args:
        list_a: First ranked list (semantic results).
        list_b: Second ranked list (keyword results).
        k: RRF constant (default 60 is standard).
        limit: Maximum output items.

    Returns:
        Fused and re-ranked list.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for rank, item in enumerate(list_a, start=1):
        sid = item.get(_F_SYMBOL_ID, "")
        scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank)
        items[sid] = item

    for rank, item in enumerate(list_b, start=1):
        sid = item.get(_F_SYMBOL_ID, "")
        scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank)
        if sid not in items:
            items[sid] = item

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    for sid, rrf_score in ranked[:limit]:
        entry = {**items[sid], "score": round(rrf_score, 6)}
        result.append(entry)
    return result
