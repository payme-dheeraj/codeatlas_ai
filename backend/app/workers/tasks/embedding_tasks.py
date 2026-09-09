"""Celery task for embedding a repository's parsed symbols into Qdrant.

Runs after ``parse_repository`` completes. Loads all ParsedSymbol records
for a repository from PostgreSQL, chunks and embeds them, and upserts
the resulting vectors into the Qdrant ``code_symbols`` collection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.models.symbol import ParsedSymbol
from app.services.embedding_service import EmbeddingService
from app.workers.celery_app import celery_app
from app.workers.tasks.repo_tasks import (
    _update_job,
    _update_repo_status,
    get_sync_session,
)

logger = get_logger(__name__)

# Batch size for loading symbols from PostgreSQL
_PG_BATCH = 500


@celery_app.task(
    bind=True,
    base=Task,
    name="app.workers.tasks.embedding_tasks.embed_repository",
    queue="indexing",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=3600,   # 60 min
    time_limit=3900,        # 65 min
)
def embed_repository(
    self: Task,
    *,
    repo_id: str,
    job_id: str,
    repo_name: str,
) -> dict:
    """Embed all parsed symbols for a repository and upsert to Qdrant.

    Pipeline stages:
    1. ``loading``    — fetch ParsedSymbol records from PostgreSQL.
    2. ``embedding``  — chunk text + generate embeddings in batches.
    3. ``indexing``   — upsert vectors into Qdrant.
    4. ``complete``   — mark job finished.

    Args:
        repo_id: UUID string of the Repository record.
        job_id: UUID string of the IndexJob record for this task.
        repo_name: Repository display name (stored in Qdrant payload).

    Returns:
        Summary dict with ``total_symbols`` and ``points_indexed``.
    """
    logger.info("embed_task_started", repo_id=repo_id, job_id=job_id)

    try:
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="running",
                progress=0,
                current_stage="loading",
                started_at=datetime.now(UTC),
            )

        # ── Stage 1: Load symbols from PostgreSQL ─────────────────────────────
        pg_engine = create_engine(
            settings.database_url_sync,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )
        PGSession = sessionmaker(bind=pg_engine)

        symbols_raw: list[dict] = []
        with PGSession() as pg_session:
            offset = 0
            while True:
                rows = pg_session.execute(
                    select(ParsedSymbol)
                    .where(ParsedSymbol.repo_id == uuid.UUID(repo_id))
                    .offset(offset)
                    .limit(_PG_BATCH)
                ).scalars().all()

                if not rows:
                    break

                for sym in rows:
                    symbols_raw.append(
                        {
                            "id": str(sym.id),
                            "repo_id": str(sym.repo_id),
                            "file_path": sym.file_path,
                            "language": sym.language,
                            "symbol_kind": sym.symbol_kind,
                            "name": sym.name,
                            "qualified_name": sym.qualified_name,
                            "start_line": sym.start_line,
                            "end_line": sym.end_line,
                            "docstring": sym.docstring,
                            "signature": sym.signature,
                            "parent_name": sym.parent_name,
                        }
                    )
                offset += _PG_BATCH

        pg_engine.dispose()
        total_symbols = len(symbols_raw)
        logger.info("symbols_loaded", repo_id=repo_id, count=total_symbols)

        with get_sync_session() as session:
            _update_job(
                session, job_id,
                progress=20,
                current_stage=f"embedding ({total_symbols} symbols)",
            )

        # ── Stage 2 & 3: Embed + index into Qdrant ───────────────────────────
        svc = EmbeddingService()

        # Delete stale vectors for this repo before re-indexing
        svc.delete_repo_vectors(repo_id)

        points_indexed = 0
        batch_size = 200
        for i in range(0, total_symbols, batch_size):
            batch = symbols_raw[i: i + batch_size]
            try:
                count = svc.index_symbols(batch, repo_name=repo_name)
                points_indexed += count
            except Exception as exc:
                logger.warning(
                    "batch_embed_failed",
                    batch_start=i,
                    error=str(exc),
                )

            progress = 20 + int(((i + len(batch)) / max(total_symbols, 1)) * 75)
            with get_sync_session() as session:
                _update_job(
                    session, job_id,
                    progress=min(progress, 95),
                    current_stage=f"embedding ({i + len(batch)}/{total_symbols})",
                )

        # ── Stage 4: Finalise ─────────────────────────────────────────────────
        now = datetime.now(UTC)
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="complete",
                progress=100,
                current_stage="complete",
                finished_at=now,
            )

        result = {
            "repo_id": repo_id,
            "job_id": job_id,
            "total_symbols": total_symbols,
            "points_indexed": points_indexed,
        }
        logger.info("embed_task_complete", **result)
        return result

    except SoftTimeLimitExceeded:
        error = "Embedding task exceeded the 60-minute soft time limit."
        logger.error("embed_task_timeout", repo_id=repo_id)
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="failed",
                error_message=error,
                finished_at=datetime.now(UTC),
            )
        raise

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.error("embed_task_error", repo_id=repo_id, error=error)
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="failed",
                error_message=error,
                finished_at=datetime.now(UTC),
            )
        raise self.retry(exc=exc) from exc
