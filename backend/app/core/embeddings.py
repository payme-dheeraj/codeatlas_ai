"""Embedding model abstraction.

Provides a unified interface for generating text embeddings that works
with both local sentence-transformers models and the OpenAI API.

The active backend is selected via the ``EMBEDDING_BACKEND`` environment
variable:
  - ``local``  — sentence-transformers (default; runs on CPU or GPU)
  - ``openai`` — OpenAI text-embedding-3-small via the official SDK

Models are loaded once per process and cached as module-level singletons
to avoid the high cost of repeated model initialisation.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Module-level model caches ─────────────────────────────────────────────────

_local_model: Any = None
_openai_client: Any = None


# ── Embedding dimension map ───────────────────────────────────────────────────

EMBEDDING_DIM: dict[str, int] = {
    # Local sentence-transformers
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-large-en-v1.5": 1024,
    # Ollama
    "nomic-embed-text": 768,
    "all-minilm": 384,
    "mxbai-embed-large": 1024,
    "snowflake-arctic-embed": 1024,
    "bge-m3": 1024,
    "bge-large": 1024,
    # OpenAI
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def get_embedding_dim() -> int:
    """Return the vector dimension for the currently configured model.

    Returns:
        Integer dimension of the embedding vectors.
    """
    backend = getattr(settings, "embedding_backend", "local").lower()
    if backend == "ollama":
        model_name = getattr(settings, "ollama_embed_model", "nomic-embed-text")
        return EMBEDDING_DIM.get(model_name, 768)
    return EMBEDDING_DIM.get(settings.embedding_model_name, 384)


# ── Local backend ─────────────────────────────────────────────────────────────


def _get_local_model() -> Any:
    """Load (or return cached) sentence-transformers model.

    Returns:
        Loaded SentenceTransformer instance.
    """
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        logger.info(
            "loading_embedding_model",
            model=settings.embedding_model_name,
            backend="local",
        )
        _local_model = SentenceTransformer(settings.embedding_model_name)
    return _local_model


def _embed_local(texts: list[str]) -> list[list[float]]:
    """Generate embeddings with a local sentence-transformers model.

    Args:
        texts: List of input strings.

    Returns:
        List of float vectors, one per input text.
    """
    model = _get_local_model()
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return [v.tolist() for v in vectors]


# ── Ollama backend ────────────────────────────────────────────────────────────


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    """Generate embeddings via local Ollama API.

    Supports batch /api/embed (Ollama >= 0.1.30) with fallback to /api/embeddings.

    Args:
        texts: List of input strings.

    Returns:
        List of float vectors.
    """
    import httpx

    base = getattr(settings, "ollama_base_url", "http://localhost:11434")
    model = getattr(settings, "ollama_embed_model", "nomic-embed-text")

    try:
        resp = httpx.post(
            f"{base}/api/embed",
            json={"model": model, "input": texts},
            timeout=60.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if "embeddings" in data:
                return data["embeddings"]
    except Exception:
        pass

    results = []
    with httpx.Client(timeout=60.0) as client:
        for text in texts:
            resp = client.post(
                f"{base}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            results.append(resp.json()["embedding"])
    return results


# ── OpenAI backend ────────────────────────────────────────────────────────────


def _get_openai_client() -> Any:
    """Return cached OpenAI client.

    Returns:
        openai.OpenAI instance.
    """
    global _openai_client
    if _openai_client is None:
        import openai

        _openai_client = openai.OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _embed_openai(texts: list[str]) -> list[list[float]]:
    """Generate embeddings via the OpenAI Embeddings API.

    Handles the 2048-token-per-item limit by truncating text to 8000
    characters before sending to the API.

    Args:
        texts: List of input strings.

    Returns:
        List of float vectors.
    """
    client = _get_openai_client()
    # OpenAI recommends replacing newlines for embedding quality
    cleaned = [t.replace("\n", " ")[:8000] for t in texts]
    response = client.embeddings.create(
        input=cleaned,
        model=settings.embedding_model_name,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


# ── Public API ────────────────────────────────────────────────────────────────


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using the configured backend.

    Automatically selects local, ollama, or OpenAI backend based on
    ``settings.embedding_backend``.

    Args:
        texts: Non-empty list of input strings to embed.

    Returns:
        List of float embedding vectors in the same order as inputs.

    Raises:
        ValueError: If ``texts`` is empty.
        RuntimeError: If the configured backend is unknown.
    """
    if not texts:
        raise ValueError("embed_texts requires at least one text input.")

    backend = getattr(settings, "embedding_backend", "local").lower()
    if backend == "openai":
        return _embed_openai(texts)
    elif backend == "ollama":
        return _embed_ollama(texts)
    elif backend == "local":
        return _embed_local(texts)
    else:
        raise RuntimeError(f"Unknown embedding backend: '{backend}'")


def embed_single(text: str) -> list[float]:
    """Embed a single text string.

    Args:
        text: Input string to embed.

    Returns:
        Float embedding vector.
    """
    return embed_texts([text])[0]


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """Split text into overlapping token-approximate chunks for embedding.

    Uses a character-based approximation (1 token ≈ 4 chars) to keep
    chunks within model context windows without requiring a tokenizer.

    Args:
        text: Full source text to split.
        chunk_size: Target chunk size in approximate tokens.
        overlap: Overlap between consecutive chunks in approximate tokens.

    Returns:
        List of text chunk strings.
    """
    # Convert token targets to character counts
    char_size = max(1, chunk_size * 4)
    # Overlap must stay strictly smaller than the window, otherwise the
    # start cursor cannot advance.
    char_overlap = max(0, min(overlap * 4, char_size - 1))

    if len(text) <= char_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + char_size, len(text))
        # Try to break at a newline boundary
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos > start + char_size // 2:
                end = newline_pos + 1
        chunks.append(text[start:end])

        # Stop once the tail has been emitted. Without this the next start
        # (end - char_overlap) would rewind behind `end`, re-emit the same
        # tail chunk forever and grow `chunks` without bound.
        if end >= len(text):
            break

        # Guarantee forward progress even if the newline break produced a
        # window smaller than the overlap.
        start = max(start + 1, end - char_overlap)

    return chunks


def content_hash(text: str) -> str:
    """Return a stable SHA-256 hex digest of the text for dedup checks.

    Args:
        text: Input string.

    Returns:
        64-character hex string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
