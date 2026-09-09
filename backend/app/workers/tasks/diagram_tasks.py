"""Celery task for async diagram generation.

Pipeline for each requested diagram type:
1. Download repository files from MinIO (for file-based extractors).
2. Extract data from Neo4j (call/import graphs) and PostgreSQL (symbols).
3. Call the appropriate diagram generator module.
4. Compute source checksum; skip if unchanged (unless force_regenerate).
5. Render SVG + PNG via Kroki.
6. Upload renders to MinIO.
7. Persist diagram record to PostgreSQL.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func

from app.core.config import settings
from app.core.logging import get_logger
from app.models.diagram import Diagram
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

_MAX_FILE_BYTES = 5 * 1024 * 1024


def _pg_session():
    engine = create_engine(settings.database_url_sync, pool_pre_ping=True, pool_size=2, max_overflow=2)
    return sessionmaker(bind=engine)(), engine


def _neo4j_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def _download_repo(repo_id: str, dest: str) -> None:
    try:
        from minio import Minio
        client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        bucket = settings.minio_bucket_repos
        prefix = f"repos/{repo_id}/raw/"
        for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
            rel = obj.object_name[len(prefix):]
            if not rel:
                continue
            local = Path(dest) / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            client.fget_object(bucket, obj.object_name, str(local))
    except Exception as exc:
        logger.warning("diagram_minio_download_failed", error=str(exc))


def _checksum(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


def _save_diagram_sync(
    session,
    repo_id: str,
    diagram_type: str,
    diagram_format: str,
    title: str,
    source: str,
    checksum: str,
    *,
    options: dict,
    svg_key: str,
    png_key: str,
    svg_url: str,
    png_url: str,
) -> str:
    """Persist a diagram synchronously, returning the new diagram UUID string."""
    repo_uuid = uuid.UUID(repo_id)

    # Mark prior versions not latest
    session.execute(
        update(Diagram)
        .where(Diagram.repo_id == repo_uuid, Diagram.diagram_type == diagram_type)
        .values(is_latest=False)
    )

    max_ver = session.execute(
        select(func.max(Diagram.version)).where(
            Diagram.repo_id == repo_uuid, Diagram.diagram_type == diagram_type
        )
    ).scalar()
    next_ver = (max_ver or 0) + 1

    d = Diagram(
        repo_id=repo_uuid,
        diagram_type=diagram_type,
        diagram_format=diagram_format,
        title=title,
        source_code=source,
        source_checksum=checksum,
        version=next_ver,
        is_latest=True,
        options=options,
        minio_key_svg=svg_key or None,
        minio_key_png=png_key or None,
        render_url_svg=svg_url or None,
        render_url_png=png_url or None,
    )
    session.add(d)
    session.commit()
    return str(d.id)


@celery_app.task(
    bind=True,
    base=Task,
    name="app.workers.tasks.diagram_tasks.generate_diagrams",
    queue="indexing",
    max_retries=1,
    default_retry_delay=30,
    soft_time_limit=1200,
    time_limit=1500,
)
def generate_diagrams(
    self: Task,
    *,
    repo_id: str,
    diagram_types: list[str],
    diagram_format: str = "mermaid",
    force_regenerate: bool = False,
    options: dict | None = None,
) -> dict:
    """Generate one or more diagram types for a repository.

    Args:
        repo_id: UUID string of the repository.
        diagram_types: List of diagram type slugs.
        diagram_format: Source format (mermaid | plantuml | d2).
        force_regenerate: Skip checksum cache if True.
        options: Generator-specific options dict.

    Returns:
        Summary dict with generated diagram IDs.
    """
    logger.info("diagram_task_started", repo_id=repo_id, types=diagram_types)
    options = options or {}
    tmp_dir: str | None = None

    try:
        pg_session, pg_engine = _pg_session()

        # ── Stage 1: Download repo files ──────────────────────────────────────
        tmp_dir = tempfile.mkdtemp(prefix=f"diagrams_{repo_id}_")
        _download_repo(repo_id, tmp_dir)

        # ── Stage 2: Extract shared data ──────────────────────────────────────
        from app.diagrams.extractors import (
            extract_docker_compose_services,
            extract_import_graph,
            extract_k8s_services,
            extract_orm_models,
        )

        compose_services = extract_docker_compose_services(tmp_dir)
        k8s_services = extract_k8s_services(tmp_dir)
        orm_models = extract_orm_models(pg_session, repo_id)

        try:
            neo4j_driver = _neo4j_driver()
        except Exception:
            neo4j_driver = None
            logger.warning("neo4j_unavailable_for_diagrams")

        import_edges: list[dict] = []
        call_edges: list[dict] = []
        if neo4j_driver:
            from app.diagrams.extractors import extract_call_graph
            import_edges = extract_import_graph(neo4j_driver, repo_id)
            call_edges = extract_call_graph(
                neo4j_driver, repo_id,
                focus_symbol=options.get("focus_symbol"),
            )

        # ── Stage 3: Generate each diagram ────────────────────────────────────
        from app.diagrams.renderer import render_diagram
        from app.diagrams.storage import upload_render

        generated: list[dict] = []

        for dtype in diagram_types:
            try:
                source = _generate_source(
                    dtype, repo_id, pg_session, tmp_dir,
                    compose_services, k8s_services, orm_models,
                    import_edges, call_edges, diagram_format, options,
                )
                if not source.strip():
                    logger.warning("empty_diagram_source", dtype=dtype)
                    continue

                new_checksum = _checksum(source)

                # Check cache
                if not force_regenerate:
                    existing = pg_session.execute(
                        select(Diagram.source_checksum).where(
                            Diagram.repo_id == uuid.UUID(repo_id),
                            Diagram.diagram_type == dtype,
                            Diagram.is_latest.is_(True),
                        )
                    ).scalar()
                    if existing == new_checksum:
                        logger.info("diagram_cache_hit", dtype=dtype)
                        continue

                # Render
                svg_bytes = render_diagram(source, diagram_format, "svg")
                png_bytes = render_diagram(source, diagram_format, "png")

                # Store placeholder id for upload keys
                placeholder_id = str(uuid.uuid4())
                svg_key, svg_url = upload_render(repo_id, placeholder_id, dtype, svg_bytes, "svg")
                png_key, png_url = upload_render(repo_id, placeholder_id, dtype, png_bytes, "png")

                diagram_id = _save_diagram_sync(
                    pg_session, repo_id, dtype, diagram_format,
                    _default_title(dtype, repo_id),
                    source, new_checksum,
                    options=options,
                    svg_key=svg_key, png_key=png_key,
                    svg_url=svg_url, png_url=png_url,
                )
                generated.append({"diagram_type": dtype, "diagram_id": diagram_id})
                logger.info("diagram_generated", dtype=dtype, diagram_id=diagram_id)

            except Exception as exc:
                logger.error("diagram_generation_error", dtype=dtype, error=str(exc))

        pg_session.close()
        pg_engine.dispose()
        if neo4j_driver:
            neo4j_driver.close()

        result = {"repo_id": repo_id, "generated": generated, "count": len(generated)}
        logger.info("diagram_task_complete", **result)
        return result

    except SoftTimeLimitExceeded:
        logger.error("diagram_task_timeout", repo_id=repo_id)
        raise

    except Exception as exc:
        logger.error("diagram_task_error", repo_id=repo_id, error=str(exc))
        raise self.retry(exc=exc) from exc

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _generate_source(
    dtype: str,
    repo_id: str,
    pg_session,
    tmp_dir: str,
    compose_services: list[dict],
    k8s_services: list[dict],
    orm_models: list[dict],
    import_edges: list[dict],
    call_edges: list[dict],
    diagram_format: str,
    options: dict,
) -> str:
    """Dispatch to the correct generator module.

    Args:
        dtype: Diagram type slug.
        repo_id: UUID string of the repository.
        pg_session: Sync PG session.
        tmp_dir: Local repo checkout directory.
        compose_services: Docker Compose service list.
        k8s_services: Kubernetes service list.
        orm_models: ORM class symbol list.
        import_edges: Neo4j import edge list.
        call_edges: Neo4j call edge list.
        diagram_format: Source format slug.
        options: Generator options dict.

    Returns:
        Diagram source string.
    """
    from app.models.repository import Repository
    repo = pg_session.execute(
        select(Repository).where(Repository.id == uuid.UUID(repo_id))
    ).scalar_one_or_none()
    repo_name = getattr(repo, "name", repo_id) if repo else repo_id

    if dtype == "architecture":
        from app.diagrams.generators.architecture import generate_architecture
        return generate_architecture(repo_name, compose_services, k8s_services)

    elif dtype == "dependency":
        from app.diagrams.generators.dependency import (
            generate_dependency,
            generate_dependency_from_symbols,
        )
        from app.diagrams.extractors import extract_symbols_by_kind
        if import_edges:
            return generate_dependency(repo_name, import_edges, max_nodes=options.get("max_nodes", 40))
        symbols = extract_symbols_by_kind(pg_session, repo_id, "function", limit=500)
        return generate_dependency_from_symbols(repo_name, symbols)

    elif dtype == "sequence":
        from app.diagrams.generators.sequence import generate_sequence
        return generate_sequence(
            repo_name, call_edges,
            focus_symbol=options.get("focus_symbol"),
        )

    elif dtype == "er":
        from app.diagrams.generators.er import generate_er
        return generate_er(repo_name, orm_models)

    elif dtype == "deployment":
        from app.diagrams.generators.deployment import generate_deployment
        return generate_deployment(
            repo_name, compose_services, k8s_services,
            output_format=diagram_format if diagram_format in ("mermaid", "d2") else "mermaid",
        )

    else:
        raise ValueError(f"Unknown diagram_type: {dtype!r}")


def _default_title(dtype: str, repo_id: str) -> str:
    titles = {
        "architecture": "System Architecture",
        "dependency": "Module Dependency Graph",
        "sequence": "Call Flow / Sequence",
        "er": "Entity-Relationship Diagram",
        "deployment": "Deployment Topology",
        "component_map": "Component Map",
        "data_flow": "Data Flow Diagram",
    }
    return titles.get(dtype, dtype.replace("_", " ").title())
