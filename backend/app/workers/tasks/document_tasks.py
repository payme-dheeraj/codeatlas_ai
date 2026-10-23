"""Celery task for async document generation.

Orchestrates the full documentation generation pipeline:
1. Load repository metadata and parsed symbols from PostgreSQL.
2. Build a rich context dict (file tree, tech stack, modules, infra).
3. Call each requested doc_gen module (readme, wiki, api_reference, etc.).
4. Persist each generated document with version tracking.
5. Update the generation job status.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import update

from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import DocumentGenerationJob
from app.models.symbol import ParsedSymbol
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _pg_session():
    engine = create_engine(settings.database_url_sync, pool_pre_ping=True, pool_size=2, max_overflow=2)
    return sessionmaker(bind=engine)(), engine


def _update_job(session, job_id: str, **fields) -> None:
    session.execute(
        update(DocumentGenerationJob)
        .where(DocumentGenerationJob.id == uuid.UUID(job_id))
        .values(**fields)
    )
    session.commit()


@celery_app.task(
    bind=True,
    base=Task,
    name="app.workers.tasks.document_tasks.generate_documents",
    queue="indexing",
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=3600,
    time_limit=3900,
)
def generate_documents(
    self: Task,
    *,
    job_id: str,
    repo_id: str,
    doc_types: list[str],
    force_regenerate: bool = False,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> dict:
    """Generate documentation artifacts for a repository.

    Args:
        job_id: UUID string of the DocumentGenerationJob.
        repo_id: UUID string of the Repository.
        doc_types: List of doc_type slugs to generate.
        force_regenerate: If True, regenerate even if already exists.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Summary dict with generated document counts.
    """
    logger.info("doc_task_started", job_id=job_id, repo_id=repo_id, types=doc_types)

    try:
        pg_session, pg_engine = _pg_session()
        _update_job(
            pg_session, job_id,
            status="running",
            progress=5,
            current_stage="loading_context",
            started_at=datetime.now(UTC),
        )

        # ── Stage 1: Load symbols and build context ───────────────────────────
        symbols = _load_symbols(pg_session, repo_id)
        repo_context = _build_repo_context(pg_session, repo_id, symbols)
        repo_context["llm_provider"] = llm_provider
        repo_context["llm_model"] = llm_model

        _update_job(pg_session, job_id, progress=15, current_stage="generating")

        # ── Stage 2: Generate each requested document type ────────────────────
        generated: list[dict] = []
        total = len(doc_types)

        for idx, doc_type in enumerate(doc_types):
            progress = 15 + int(((idx + 1) / total) * 75)
            _update_job(
                pg_session, job_id,
                progress=progress,
                current_stage=f"generating_{doc_type}",
            )
            try:
                content, title = _generate_one(doc_type, repo_context, symbols)
                _save_document(
                    pg_session, repo_id, doc_type, title, content,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                )
                generated.append({"doc_type": doc_type, "title": title})
                logger.info("doc_generated", doc_type=doc_type, repo_id=repo_id)
            except Exception as exc:
                logger.error("doc_generation_failed", doc_type=doc_type, error=str(exc))

        # ── Stage 3: Finalise ─────────────────────────────────────────────────
        _update_job(
            pg_session, job_id,
            status="complete",
            progress=100,
            current_stage="complete",
            finished_at=datetime.now(UTC),
        )

        pg_session.close()
        pg_engine.dispose()

        result = {
            "job_id": job_id,
            "repo_id": repo_id,
            "generated_count": len(generated),
            "documents": generated,
        }
        logger.info("doc_task_complete", **result)
        return result

    except SoftTimeLimitExceeded:
        error = "Document generation task exceeded the 60-minute time limit."
        logger.error("doc_task_timeout", job_id=job_id)
        try:
            pg_s, _ = _pg_session()
            _update_job(pg_s, job_id, status="failed", error_message=error, finished_at=datetime.now(UTC))
        except Exception:
            pass
        raise

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.error("doc_task_error", job_id=job_id, error=error)
        try:
            pg_s, _ = _pg_session()
            _update_job(pg_s, job_id, status="failed", error_message=error, finished_at=datetime.now(UTC))
        except Exception:
            pass
        raise self.retry(exc=exc) from exc


def _load_symbols(session, repo_id: str) -> list[dict]:
    """Load ParsedSymbol rows for the repository.

    Args:
        session: Synchronous SQLAlchemy session.
        repo_id: UUID string.

    Returns:
        List of symbol attribute dicts.
    """
    rows = session.execute(
        select(ParsedSymbol).where(ParsedSymbol.repo_id == uuid.UUID(repo_id)).limit(2000)
    ).scalars().all()
    return [
        {
            "name": s.name,
            "qualified_name": s.qualified_name,
            "symbol_kind": s.symbol_kind,
            "language": s.language,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "docstring": s.docstring,
            "signature": s.signature,
            "extra": s.extras or {},
        }
        for s in rows
    ]


def _build_repo_context(session, repo_id: str, symbols: list[dict]) -> dict[str, Any]:
    """Build a rich context dict from repo metadata and symbols.

    Args:
        session: Synchronous SQLAlchemy session.
        repo_id: UUID string.
        symbols: List of symbol dicts.

    Returns:
        Context dict for the doc generators.
    """
    from app.models.repository import Repository

    repo = session.execute(
        select(Repository).where(Repository.id == uuid.UUID(repo_id))
    ).scalar_one_or_none()

    if repo is None:
        return {"repo_name": "Unknown Repository"}

    # Language distribution
    langs = Counter(s["language"] for s in symbols if s.get("language"))
    primary_lang = langs.most_common(1)[0][0] if langs else "Unknown"

    # File tree (top-level directories + key files)
    files = sorted({s["file_path"] for s in symbols})
    top_level = sorted({f.split("/")[0] for f in files if "/" in f} | {f for f in files if "/" not in f})
    file_tree = "\n".join(f"  {p}" for p in top_level[:30])

    # Module summaries (top-level directories with symbol counts)
    dir_counts: Counter = Counter()
    for s in symbols:
        parts = s["file_path"].split("/")
        if len(parts) > 1:
            dir_counts[parts[0]] += 1
    module_summaries = "\n".join(
        f"- **{d}/** — {c} symbols" for d, c in dir_counts.most_common(15)
    )

    # Data models (class symbols)
    model_syms = [s for s in symbols if s.get("symbol_kind") in ("class", "interface")][:20]
    data_models = "\n".join(
        f"- `{s['qualified_name']}` ({s['language']}) — {(s.get('docstring') or '')[:80]}"
        for s in model_syms
    )

    # Tech stack from repository metadata
    tech_stack = list(repo.tech_stack or []) if hasattr(repo, "tech_stack") else []

    # Package manager file info
    pkg_files = []
    for fname in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle"):
        if any(fname in f for f in files):
            pkg_files.append(fname)
    package_files = ", ".join(pkg_files) or "(none detected)"

    return {
        "repo_name": repo.name if hasattr(repo, "name") else str(repo_id),
        "description": getattr(repo, "description", "") or "",
        "primary_language": primary_lang,
        "languages": list(langs.keys()),
        "tech_stack": tech_stack,
        "license": getattr(repo, "license_spdx", None) or "Not detected",
        "file_tree": file_tree,
        "package_files": package_files,
        "module_summaries": module_summaries,
        "data_models": data_models,
        "infra_info": _detect_infra(files),
        "security_context": "See Security Scan report for details.",
        "key_dependencies": package_files,
    }


def _detect_infra(files: list[str]) -> str:
    parts = []
    if any("docker-compose" in f.lower() for f in files):
        parts.append("Docker Compose")
    if any(f.endswith(".tf") for f in files):
        parts.append("Terraform")
    if any(f.endswith((".yaml", ".yml")) and "k8s" in f.lower() for f in files):
        parts.append("Kubernetes")
    if any("dockerfile" in f.lower() for f in files):
        parts.append("Docker")
    return ", ".join(parts) or "(none detected)"


def _generate_one(
    doc_type: str,
    repo_context: dict[str, Any],
    symbols: list[dict],
) -> tuple[str, str]:
    """Dispatch to the appropriate doc_gen module.

    Args:
        doc_type: Document type slug.
        repo_context: Repository context dict.
        symbols: List of symbol dicts.

    Returns:
        Tuple of (markdown_content, title).
    """
    repo_name = repo_context.get("repo_name", "Repository")
    provider = repo_context.get("llm_provider")
    model = repo_context.get("llm_model")

    if doc_type == "readme":
        from app.docs_gen.readme import generate_readme
        content = generate_readme(repo_context)
        return content, f"README — {repo_name}"

    elif doc_type == "api_reference":
        from app.docs_gen.api_reference import generate_api_reference
        content = generate_api_reference(repo_name, symbols, llm_provider=provider, llm_model=model)
        return content, f"API Reference — {repo_name}"

    elif doc_type == "deployment_guide":
        from app.docs_gen.deployment import generate_deployment_guide
        content = generate_deployment_guide(repo_name, repo_context, llm_provider=provider, llm_model=model)
        return content, f"Deployment Guide — {repo_name}"

    elif doc_type == "adr":
        from app.docs_gen.adr import generate_adrs
        content = generate_adrs(repo_name, repo_context, llm_provider=provider, llm_model=model)
        return content, f"Architecture Decision Records — {repo_name}"

    elif doc_type == "wiki":
        from app.docs_gen.wiki import generate_wiki
        content = generate_wiki(repo_name, repo_context, llm_provider=provider, llm_model=model)
        return content, f"Developer Wiki — {repo_name}"

    elif doc_type == "onboarding":
        from app.docs_gen.wiki import generate_onboarding_guide
        content = generate_onboarding_guide(repo_name, repo_context, llm_provider=provider, llm_model=model)
        return content, f"Onboarding Guide — {repo_name}"

    elif doc_type == "changelog":
        content = _generate_changelog(repo_name, symbols)
        return content, f"Changelog — {repo_name}"

    else:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")


def _generate_changelog(repo_name: str, symbols: list[dict]) -> str:
    """Minimal changelog stub (git history not available in indexing context).

    Args:
        repo_name: Repository display name.
        symbols: Symbol list (used to infer feature areas).

    Returns:
        Markdown changelog stub.
    """
    return (
        f"# Changelog — {repo_name}\n\n"
        "*Changelog auto-generation requires git history access. "
        "Please re-trigger after enabling git history ingestion.*\n"
    )


def _save_document(
    session,
    repo_id: str,
    doc_type: str,
    title: str,
    content: str,
    *,
    llm_provider: str | None,
    llm_model: str | None,
) -> None:
    """Persist a generated document synchronously (used inside Celery task).

    Args:
        session: Synchronous SQLAlchemy session.
        repo_id: UUID string.
        doc_type: Document type slug.
        title: Document title.
        content: Generated Markdown content.
        llm_provider: Provider used.
        llm_model: Model used.
    """
    from sqlalchemy import select as sa_select, update as sa_update
    from app.models.document import Document

    repo_uuid = uuid.UUID(repo_id)

    # Mark prior versions not latest
    session.execute(
        sa_update(Document)
        .where(Document.repo_id == repo_uuid, Document.doc_type == doc_type)
        .values(is_latest=False)
    )

    # Next version
    from sqlalchemy import func
    max_ver = session.execute(
        sa_select(func.max(Document.version)).where(
            Document.repo_id == repo_uuid, Document.doc_type == doc_type
        )
    ).scalar()
    next_ver = (max_ver or 0) + 1

    model_label = f"{llm_provider or 'unknown'}/{llm_model or 'unknown'}"

    doc = Document(
        repo_id=repo_uuid,
        doc_type=doc_type,
        title=title,
        content_md=content,
        version=next_ver,
        is_latest=True,
        generation_model=model_label,
        generation_meta={},
        content_extra={},
    )
    session.add(doc)
    session.commit()
