"""Celery task for running a full security scan against a repository.

Pipeline:
1. Download repository files from MinIO.
2. Run enabled scan modules (secrets, sast, iac) in sequence.
3. Aggregate, deduplicate, and bulk-insert findings to PostgreSQL.
4. Optionally generate AI remediation for high-priority findings.
5. Update SecurityScan record with final counts and status.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.models.security_finding import SecurityFinding, SecurityScan
from app.scanner.aggregator import normalize, severity_counts
from app.scanner.iac import scan_file_iac
from app.scanner.secrets import scan_file_for_secrets
from app.workers.celery_app import celery_app
from app.workers.tasks.repo_tasks import get_sync_session

logger = get_logger(__name__)

_MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB


def _pg_session():
    engine = create_engine(
        settings.database_url_sync,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
    )
    return sessionmaker(bind=engine)(), engine


def _update_scan(session, scan_id: str, **fields) -> None:
    session.execute(
        update(SecurityScan)
        .where(SecurityScan.id == uuid.UUID(scan_id))
        .values(**fields)
    )
    session.commit()


def _download_repo(repo_id: str, dest: str) -> int:
    from minio import Minio
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = settings.minio_bucket_repos
    prefix = f"repos/{repo_id}/raw/"
    count = 0
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        rel = obj.object_name[len(prefix):]
        if not rel:
            continue
        local = Path(dest) / rel
        local.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(bucket, obj.object_name, str(local))
        count += 1
    return count


@celery_app.task(
    bind=True,
    base=Task,
    name="app.workers.tasks.security_tasks.run_security_scan",
    queue="indexing",
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def run_security_scan(
    self: Task,
    *,
    scan_id: str,
    repo_id: str,
    scan_types: list[str],
    generate_remediation: bool = True,
) -> dict:
    """Execute a security scan for a repository.

    Args:
        scan_id: UUID string of the SecurityScan record.
        repo_id: UUID string of the Repository record.
        scan_types: List of module slugs to run.
        generate_remediation: Whether to call AI remediation generator.

    Returns:
        Summary dict with finding counts.
    """
    logger.info("scan_task_started", scan_id=scan_id, repo_id=repo_id, types=scan_types)
    tmp_dir: str | None = None

    try:
        pg_session, pg_engine = _pg_session()
        _update_scan(
            pg_session, scan_id,
            status="running",
            progress=5,
            current_stage="downloading",
            started_at=datetime.now(UTC),
        )

        # ── Stage 1: Download from MinIO ─────────────────────────────────────
        tmp_dir = tempfile.mkdtemp(prefix=f"scan_{scan_id}_")
        try:
            downloaded = _download_repo(repo_id, tmp_dir)
            logger.info("scan_files_downloaded", count=downloaded)
        except Exception as exc:
            logger.warning("minio_download_failed", error=str(exc))
            downloaded = 0

        _update_scan(pg_session, scan_id, progress=15, current_stage="scanning")

        # ── Stage 2: Run scanners ─────────────────────────────────────────────
        all_findings: list[dict] = []
        repo_path = Path(tmp_dir)

        if "secrets" in scan_types or "sast" in scan_types:
            all_findings.extend(
                _run_file_scanners(
                    repo_path, repo_id, scan_id, scan_types
                )
            )

        _update_scan(pg_session, scan_id, progress=60, current_stage="iac_scan")

        if "iac" in scan_types:
            all_findings.extend(
                _run_iac_scanner(repo_path, repo_id, scan_id)
            )

        if "sast" in scan_types and downloaded > 0:
            _update_scan(pg_session, scan_id, progress=70, current_stage="sast_scan")
            try:
                from app.scanner.sast import scan_directory_sast
                raw_sast = scan_directory_sast(tmp_dir)
                all_findings.extend(
                    normalize(
                        raw_sast,
                        uuid.UUID(scan_id),
                        uuid.UUID(repo_id),
                        scanner="sast",
                    )
                )
            except Exception as exc:
                logger.warning("sast_failed", error=str(exc))

        # ── Stage 3: Persist findings ─────────────────────────────────────────
        _update_scan(pg_session, scan_id, progress=80, current_stage="persisting")

        if all_findings:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            batch_size = 500
            inserted = 0
            for i in range(0, len(all_findings), batch_size):
                batch = all_findings[i: i + batch_size]
                stmt = pg_insert(SecurityFinding).values(batch).on_conflict_do_nothing(
                    constraint="uq_finding_scan_fingerprint"
                )
                pg_session.execute(stmt)
                pg_session.commit()
                inserted += len(batch)
            logger.info("findings_inserted", count=inserted)

        # ── Stage 4: AI remediation ───────────────────────────────────────────
        if generate_remediation and all_findings:
            _update_scan(pg_session, scan_id, progress=88, current_stage="remediation")
            try:
                from app.scanner.remediation import generate_remediations_batch
                remediations = generate_remediations_batch(all_findings, max_findings=15)
                for fp, rem in remediations.items():
                    pg_session.execute(
                        update(SecurityFinding)
                        .where(
                            SecurityFinding.scan_id == uuid.UUID(scan_id),
                            SecurityFinding.fingerprint == fp,
                        )
                        .values(remediation=rem)
                    )
                pg_session.commit()
            except Exception as exc:
                logger.warning("remediation_generation_failed", error=str(exc))

        # ── Stage 5: Finalise ─────────────────────────────────────────────────
        counts = severity_counts(all_findings)
        now = datetime.now(UTC)
        _update_scan(
            pg_session, scan_id,
            status="complete",
            progress=100,
            current_stage="complete",
            finished_at=now,
            total_findings=counts["total"],
            critical_count=counts["critical"],
            high_count=counts["high"],
            medium_count=counts["medium"],
            low_count=counts["low"],
            info_count=counts["info"],
        )

        pg_session.close()
        pg_engine.dispose()

        result = {
            "scan_id": scan_id,
            "repo_id": repo_id,
            "total_findings": counts["total"],
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
        }
        logger.info("scan_task_complete", **result)
        return result

    except SoftTimeLimitExceeded:
        error = "Security scan exceeded the 30-minute time limit."
        logger.error("scan_task_timeout", scan_id=scan_id)
        try:
            pg_session, _ = _pg_session()
            _update_scan(pg_session, scan_id, status="failed", error_message=error, finished_at=datetime.now(UTC))
        except Exception:
            pass
        raise

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.error("scan_task_error", scan_id=scan_id, error=error)
        try:
            pg_session, _ = _pg_session()
            _update_scan(pg_session, scan_id, status="failed", error_message=error, finished_at=datetime.now(UTC))
        except Exception:
            pass
        raise self.retry(exc=exc) from exc

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_file_scanners(
    repo_path: Path,
    repo_id: str,
    scan_id: str,
    scan_types: list[str],
) -> list[dict]:
    """Run secrets (and optionally per-file SAST) over all source files.

    Args:
        repo_path: Absolute path to the downloaded repo.
        repo_id: UUID string of the repository.
        scan_id: UUID string of the scan.
        scan_types: Enabled scanner slugs.

    Returns:
        List of normalized finding dicts.
    """
    from app.parser.classifier import detect_language

    findings: list[dict] = []

    for file in repo_path.rglob("*"):
        if not file.is_file():
            continue
        if file.stat().st_size > _MAX_FILE_BYTES:
            continue
        if any(
            p.startswith(".") or p in ("node_modules", "__pycache__", "dist", "build", "target")
            for p in file.parts
        ):
            continue

        try:
            rel = str(file.relative_to(repo_path))
            source = file.read_text(errors="replace")
            lang = detect_language(rel)

            if "secrets" in scan_types:
                raw = scan_file_for_secrets(rel, source)
                findings.extend(
                    normalize(raw, uuid.UUID(scan_id), uuid.UUID(repo_id), "secrets", lang)
                )
        except Exception:
            continue

    return findings


def _run_iac_scanner(repo_path: Path, repo_id: str, scan_id: str) -> list[dict]:
    """Run IaC scanner over all relevant files.

    Args:
        repo_path: Absolute path to the downloaded repo.
        repo_id: UUID string of the repository.
        scan_id: UUID string of the scan.

    Returns:
        List of normalized finding dicts.
    """
    iac_extensions = {".yaml", ".yml", ".tf", "dockerfile"}
    findings: list[dict] = []

    for file in repo_path.rglob("*"):
        if not file.is_file():
            continue
        name_lower = file.name.lower()
        ext = file.suffix.lower()
        if ext not in iac_extensions and name_lower not in {"dockerfile"}:
            continue

        try:
            rel = str(file.relative_to(repo_path))
            source = file.read_text(errors="replace")
            raw = scan_file_iac(rel, source)
            findings.extend(
                normalize(raw, uuid.UUID(scan_id), uuid.UUID(repo_id), "iac")
            )
        except Exception:
            continue

    return findings
