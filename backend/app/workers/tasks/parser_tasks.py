"""Celery task for parsing a cloned repository's source files.

This task runs after ``clone_and_index_repo`` completes. It:
1. Downloads files from MinIO for the repository.
2. Classifies and language-detects each file.
3. Runs the appropriate Tree-sitter parser.
4. Bulk-upserts symbols to PostgreSQL.
5. Writes the knowledge graph (nodes + edges) to Neo4j.
6. Updates the IndexJob progress throughout.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.models.index_job import IndexJob
from app.models.repository import Repository
from app.parser.classifier import classify_file, detect_language, should_skip_file
from app.parser.graph.neo4j_writer import Neo4jWriter
from app.parser.registry import get_parser
from app.workers.celery_app import celery_app
from app.workers.tasks.repo_tasks import (
    _SyncSession,
    _update_job,
    _update_repo_status,
    get_sync_session,
)

logger = get_logger(__name__)

# Maximum file size to parse (4 MB) — larger files are skipped to avoid OOM
_MAX_FILE_BYTES = 4 * 1024 * 1024

# Batch size for PostgreSQL symbol bulk upsert
_PG_BATCH = 500


def _download_repo_files(repo_id: str, dest_dir: str) -> int:
    """Download all raw repository files from MinIO to a local temp directory.

    Args:
        repo_id: UUID string of the repository.
        dest_dir: Absolute path of the local directory to write files into.

    Returns:
        Number of files downloaded.
    """
    from minio import Minio

    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    bucket = settings.minio_bucket_repos
    prefix = f"repos/{repo_id}/raw/"
    downloaded = 0

    objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
    for obj in objects:
        relative_key = obj.object_name[len(prefix):]
        if not relative_key:
            continue
        local_path = Path(dest_dir) / relative_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(bucket, obj.object_name, str(local_path))
        downloaded += 1

    return downloaded


def _parse_file(file_path: str, absolute_path: Path) -> list[dict]:
    """Parse a single source file and return raw symbol dicts.

    Args:
        file_path: Repository-relative file path (used for classification).
        absolute_path: Absolute path of the file on disk.

    Returns:
        List of symbol dicts ready for PostgreSQL bulk upsert.
        Empty list if the file should be skipped or no parser is available.
    """
    if should_skip_file(file_path):
        return []

    language = detect_language(file_path)
    if language is None:
        return []

    try:
        size = absolute_path.stat().st_size
        if size > _MAX_FILE_BYTES:
            logger.debug("file_too_large_skipped", path=file_path, bytes=size)
            return []

        source = absolute_path.read_text(errors="replace")
        if not source.strip():
            return []

        file_type = classify_file(file_path, source)
        parser = get_parser(language)
        if parser is None:
            return []

        symbols = parser.parse(source, file_path)
        return [
            {
                "file_path": file_path,
                "file_type": file_type,
                "language": language,
                "symbol_kind": s.symbol_kind,
                "name": s.name,
                "qualified_name": s.qualified_name,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "docstring": s.docstring,
                "signature": s.signature,
                "parent_name": s.parent_name,
                "decorators": s.decorators,
                "extras": s.extras,
            }
            for s in symbols
        ]
    except Exception as exc:
        logger.warning("file_parse_error", path=file_path, error=str(exc))
        return []


@celery_app.task(
    bind=True,
    base=Task,
    name="app.workers.tasks.parser_tasks.parse_repository",
    queue="indexing",
    max_retries=1,
    default_retry_delay=120,
    soft_time_limit=1800,   # 30 min
    time_limit=2100,        # 35 min
)
def parse_repository(
    self: Task,
    *,
    repo_id: str,
    job_id: str,
    repo_name: str,
    repo_url: str | None,
) -> dict:
    """Parse all source files in a repository and build the knowledge graph.

    Pipeline stages:
    1. ``downloading``  — fetch files from MinIO.
    2. ``parsing``      — Tree-sitter AST pass per file.
    3. ``graph_write``  — write nodes + edges to Neo4j.
    4. ``complete``     — mark job and repo as parsed.

    Args:
        repo_id: UUID string of the Repository record.
        job_id: UUID string of the IndexJob record.
        repo_name: Repository name (for Neo4j node).
        repo_url: Repository URL (for Neo4j node).

    Returns:
        Summary dict with counts.
    """
    logger.info("parse_task_started", repo_id=repo_id, job_id=job_id)
    tmp_dir: str | None = None

    try:
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="running", progress=0,
                current_stage="downloading",
                started_at=datetime.now(UTC),
            )
            _update_repo_status(session, repo_id, "parsing")

        # ── Stage 1: Download from MinIO ─────────────────────────────────────
        tmp_dir = tempfile.mkdtemp(prefix=f"parse_{repo_id}_")
        downloaded = _download_repo_files(repo_id, tmp_dir)
        logger.info("files_downloaded", repo_id=repo_id, count=downloaded)

        with get_sync_session() as session:
            _update_job(session, job_id, progress=10, current_stage="parsing")

        # ── Stage 2: Parse all files ─────────────────────────────────────────
        repo_path = Path(tmp_dir)
        all_files = [
            p for p in repo_path.rglob("*")
            if p.is_file()
        ]

        total_files = len(all_files)
        all_symbols: list[dict] = []
        file_meta: list[dict] = []
        parsed_count = 0

        for idx, abs_path in enumerate(all_files):
            rel_path = str(abs_path.relative_to(repo_path))

            language = detect_language(rel_path)
            file_type = classify_file(rel_path)
            file_meta.append(
                {"path": rel_path, "language": language or "unknown", "file_type": file_type}
            )

            syms = _parse_file(rel_path, abs_path)
            if syms:
                # Inject repo_id into each symbol dict
                for s in syms:
                    s["repo_id"] = repo_id
                all_symbols.extend(syms)
                parsed_count += 1

            # Report progress every 100 files
            if (idx + 1) % 100 == 0:
                progress = 10 + int(((idx + 1) / max(total_files, 1)) * 50)
                with get_sync_session() as session:
                    _update_job(
                        session, job_id,
                        progress=progress,
                        current_stage=f"parsing ({idx+1}/{total_files})",
                    )

        logger.info(
            "parsing_complete",
            repo_id=repo_id,
            total_files=total_files,
            parsed_files=parsed_count,
            total_symbols=len(all_symbols),
        )

        with get_sync_session() as session:
            _update_job(session, job_id, progress=60, current_stage="persisting_symbols")

        from sqlalchemy import text

        insert_stmt = text(
            """
            INSERT INTO parsed_symbols (
                id, repo_id, file_path, file_type, language, symbol_kind,
                name, qualified_name, start_line, end_line,
                docstring, signature, parent_name, decorators, extras,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :repo_id, :file_path, :file_type, :language,
                :symbol_kind, :name, :qualified_name, :start_line, :end_line,
                :docstring, :signature, :parent_name,
                CAST(:decorators AS jsonb), CAST(:extras AS jsonb),
                now(), now()
            )
            ON CONFLICT (repo_id, file_path, symbol_kind, qualified_name)
            DO UPDATE SET
                start_line    = EXCLUDED.start_line,
                end_line      = EXCLUDED.end_line,
                docstring     = EXCLUDED.docstring,
                signature     = EXCLUDED.signature,
                decorators    = EXCLUDED.decorators,
                extras        = EXCLUDED.extras,
                updated_at    = now()
            """
        )

        with PGSession() as pg_session:
            # Delete stale symbols before re-inserting
            from sqlalchemy import delete as sa_delete
            from app.models.symbol import ParsedSymbol

            pg_session.execute(
                sa_delete(ParsedSymbol).where(
                    ParsedSymbol.repo_id == uuid.UUID(repo_id)
                )
            )
            pg_session.commit()

            # Bulk insert in batches
            for i in range(0, len(all_symbols), _PG_BATCH):
                batch = all_symbols[i: i + _PG_BATCH]
                rows = [
                    {
                        **s,
                        "decorators": json.dumps(s.get("decorators") or []),
                        "extras": json.dumps(s.get("extras") or {}),
                    }
                    for s in batch
                ]
                pg_session.execute(insert_stmt, rows)
            pg_session.commit()

        pg_engine.dispose()

        with get_sync_session() as session:
            _update_job(session, job_id, progress=75, current_stage="graph_write")

        # ── Stage 3b: Write knowledge graph to Neo4j ─────────────────────────
        edge_count = 0
        try:
            writer = Neo4jWriter(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
            )
            writer.ensure_constraints()
            writer.upsert_repository(repo_id, repo_name, repo_url)
            writer.upsert_files(repo_id, file_meta)

            # Group symbols by file for Neo4j writes
            from collections import defaultdict
            from app.parser.base import SymbolData

            file_symbols: dict[str, list[SymbolData]] = defaultdict(list)
            for sym_dict in all_symbols:
                sd = SymbolData(
                    name=sym_dict["name"],
                    qualified_name=sym_dict["qualified_name"],
                    symbol_kind=sym_dict["symbol_kind"],
                    start_line=sym_dict["start_line"],
                    end_line=sym_dict["end_line"],
                    docstring=sym_dict.get("docstring"),
                    signature=sym_dict.get("signature"),
                    parent_name=sym_dict.get("parent_name"),
                    decorators=sym_dict.get("decorators") or [],
                    extras=sym_dict.get("extras") or {},
                )
                file_symbols[sym_dict["file_path"]].append(sd)

            for fp, syms in file_symbols.items():
                writer.upsert_symbols(repo_id, fp, syms)

            # Write call and member-of edges for all symbols
            all_sd = [sd for syms in file_symbols.values() for sd in syms]
            for fp, syms in file_symbols.items():
                edge_count += writer.upsert_call_edges(repo_id, fp, syms)
            edge_count += writer.upsert_member_of_edges(repo_id, all_sd)
            writer.close()

            logger.info("graph_write_complete", repo_id=repo_id, edges=edge_count)
        except Exception as neo4j_exc:
            logger.warning(
                "neo4j_write_failed",
                repo_id=repo_id,
                error=str(neo4j_exc),
            )
            # Neo4j failure is non-fatal — continue to mark repo as parsed

        # ── Stage 4: Finalise ────────────────────────────────────────────────
        now = datetime.now(UTC)
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="complete",
                progress=100,
                current_stage="complete",
                finished_at=now,
            )
            _update_repo_status(session, repo_id, "complete")

        # ── Chain: trigger embedding task ────────────────────────────────────
        embed_job_id: str | None = None
        try:
            with get_sync_session() as session:
                from sqlalchemy import insert
                from app.models.index_job import IndexJob as _IndexJob
                embed_job_uuid = __import__("uuid").uuid4()
                session.execute(
                    insert(_IndexJob).values(
                        id=embed_job_uuid,
                        repo_id=__import__("uuid").UUID(repo_id),
                        job_type="embed",
                        status="queued",
                        progress=0,
                    )
                )
                session.commit()
                embed_job_id = str(embed_job_uuid)

            from app.workers.tasks.embedding_tasks import embed_repository
            embed_repository.apply_async(
                kwargs={
                    "repo_id": repo_id,
                    "job_id": embed_job_id,
                    "repo_name": repo_name,
                },
                countdown=3,
            )
            logger.info("embed_task_dispatched", repo_id=repo_id, embed_job_id=embed_job_id)
        except Exception as chain_exc:
            logger.error("embed_chain_failed", repo_id=repo_id, error=str(chain_exc))

        result = {
            "repo_id": repo_id,
            "job_id": job_id,
            "total_files": total_files,
            "parsed_files": parsed_count,
            "total_symbols": len(all_symbols),
            "graph_edges": edge_count,
            "embed_job_id": embed_job_id,
        }
        logger.info("parse_task_complete", **result)
        return result

    except SoftTimeLimitExceeded:
        error = "Parser task exceeded the 30-minute soft time limit."
        logger.error("parse_task_timeout", repo_id=repo_id)
        with get_sync_session() as session:
            _update_job(session, job_id, status="failed", error_message=error, finished_at=datetime.now(UTC))
            _update_repo_status(session, repo_id, "failed", error_message=error)
        raise

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.error("parse_task_error", repo_id=repo_id, error=error)
        with get_sync_session() as session:
            _update_job(session, job_id, status="failed", error_message=error, finished_at=datetime.now(UTC))
            _update_repo_status(session, repo_id, "failed", error_message=error)
        raise self.retry(exc=exc) from exc

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
