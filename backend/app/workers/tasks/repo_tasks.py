"""Celery tasks for repository cloning, indexing, and artifact cleanup.

Tasks use a synchronous SQLAlchemy session (psycopg2) because Celery workers
are not async.  A new session is created per task via a context manager to
ensure proper cleanup.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.git_remote import normalize_clone_url, resolve_branch
from app.core.logging import get_logger
from app.models.index_job import IndexJob
from app.models.repository import Repository
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# ── Synchronous DB session for worker processes ────────────────────────────────

_sync_engine = create_engine(
    settings.database_url_sync,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
)
_SyncSession = sessionmaker(bind=_sync_engine, autocommit=False, autoflush=False)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Yield a synchronous SQLAlchemy session with auto-commit/rollback.

    Yields:
        An active SQLAlchemy Session.
    """
    session: Session = _SyncSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _update_job(
    session: Session,
    job_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    current_stage: str | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    """Apply partial updates to an IndexJob row without loading the ORM object.

    Args:
        session: Active synchronous SQLAlchemy session.
        job_id: UUID string of the IndexJob to update.
        status: New status value.
        progress: Progress percentage 0-100.
        current_stage: Human-readable pipeline stage label.
        error_message: Error detail for failed states.
        started_at: Timestamp when the worker started processing.
        finished_at: Timestamp when the task reached a terminal state.
    """
    values: dict = {}
    if status is not None:
        values["status"] = status
    if progress is not None:
        values["progress"] = progress
    if current_stage is not None:
        values["current_stage"] = current_stage
    if error_message is not None:
        values["error_message"] = error_message
    if started_at is not None:
        values["started_at"] = started_at
    if finished_at is not None:
        values["finished_at"] = finished_at
    if values:
        session.execute(
            update(IndexJob).where(IndexJob.id == uuid.UUID(job_id)).values(**values)
        )
        session.commit()


def _update_repo_status(
    session: Session,
    repo_id: str,
    status: str,
    error_message: str | None = None,
    tech_stack: dict | None = None,
    stats: dict | None = None,
    clone_path: str | None = None,
    last_indexed_at: datetime | None = None,
) -> None:
    """Update Repository status columns directly without loading the full ORM object.

    Args:
        session: Active synchronous SQLAlchemy session.
        repo_id: UUID string of the Repository to update.
        status: New index_status value.
        error_message: Error detail on failure.
        tech_stack: Detected tech stack JSON blob.
        stats: Repository statistics JSON blob.
        clone_path: MinIO key prefix where raw files are stored.
        last_indexed_at: Timestamp of successful completion.
    """
    values: dict = {"index_status": status}
    if error_message is not None:
        values["error_message"] = error_message
    if tech_stack is not None:
        values["tech_stack"] = tech_stack
    if stats is not None:
        values["stats"] = stats
    if clone_path is not None:
        values["clone_path"] = clone_path
    if last_indexed_at is not None:
        values["last_indexed_at"] = last_indexed_at
    session.execute(
        update(Repository).where(Repository.id == uuid.UUID(repo_id)).values(**values)
    )
    session.commit()


def _detect_tech_stack(repo_path: Path) -> dict:  # noqa: C901
    """Scan the repository for known indicator files and return a rich tech-stack dict.

    Args:
        repo_path: Absolute path to the cloned repository on disk.

    Returns:
        Dict with ``languages``, ``frameworks``, ``databases``, ``infrastructure``,
        ``package_managers``, and ``tools`` lists, plus ``readme_summary``.
    """
    import json as _json

    languages: set[str] = set()
    frameworks: set[str] = set()
    databases: set[str] = set()
    infrastructure: set[str] = set()
    package_managers: set[str] = set()
    tools: set[str] = set()

    # ── Language detection by file extension (first 8000 files) ──────────────
    LANG_MAP: dict[str, str] = {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
        ".js": "JavaScript", ".jsx": "JavaScript", ".java": "Java",
        ".go": "Go", ".rs": "Rust", ".kt": "Kotlin", ".cs": "C#",
        ".cpp": "C++", ".c": "C", ".rb": "Ruby", ".php": "PHP",
        ".swift": "Swift", ".scala": "Scala", ".dart": "Dart",
        ".ex": "Elixir", ".exs": "Elixir", ".hs": "Haskell",
        ".lua": "Lua", ".r": "R", ".jl": "Julia",
    }
    lang_counts: dict[str, int] = {}
    count = 0
    for path in repo_path.rglob("*"):
        if count > 8000:
            break
        parts = path.relative_to(repo_path).parts if path.is_relative_to(repo_path) else ()
        if any(p in ("node_modules", "__pycache__", ".git", "dist", "build", "target", ".venv", "venv") for p in parts):
            continue
        if path.is_file() and path.suffix in LANG_MAP:
            lang = LANG_MAP[path.suffix]
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            languages.add(lang)
            count += 1

    # Primary language = most files
    primary_language = max(lang_counts, key=lang_counts.get) if lang_counts else None

    # ── Package manager detection ─────────────────────────────────────────────
    PM_INDICATORS: list[tuple[str, str]] = [
        ("package.json", "npm/yarn"),
        ("yarn.lock", "Yarn"),
        ("pnpm-lock.yaml", "pnpm"),
        ("bun.lockb", "Bun"),
        ("pyproject.toml", "Poetry/pip"),
        ("requirements.txt", "pip"),
        ("Pipfile", "Pipenv"),
        ("Cargo.toml", "Cargo"),
        ("go.mod", "Go Modules"),
        ("pom.xml", "Maven"),
        ("build.gradle", "Gradle"),
        ("build.gradle.kts", "Gradle"),
        ("Gemfile", "Bundler"),
        ("composer.json", "Composer"),
        ("pubspec.yaml", "pub"),
        ("mix.exs", "Mix"),
    ]
    for indicator, pm in PM_INDICATORS:
        if (repo_path / indicator).exists():
            package_managers.add(pm)

    # ── Infrastructure detection ──────────────────────────────────────────────
    if (repo_path / "Dockerfile").exists() or list(repo_path.rglob("Dockerfile")):
        infrastructure.add("Docker")
    for dc in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        if (repo_path / dc).exists():
            infrastructure.add("Docker Compose")
            break
    # Kubernetes: look for YAML files with apiVersion/kind fields
    k8s_found = False
    for yaml_file in list(repo_path.rglob("*.yaml"))[:200] + list(repo_path.rglob("*.yml"))[:200]:
        if k8s_found:
            break
        try:
            txt = yaml_file.read_text(errors="ignore")
            if "apiVersion:" in txt and "kind:" in txt and ("Deployment" in txt or "Service" in txt or "Pod" in txt):
                infrastructure.add("Kubernetes")
                k8s_found = True
        except OSError:
            pass
    # Helm
    if (repo_path / "Chart.yaml").exists() or list(repo_path.rglob("Chart.yaml")):
        infrastructure.add("Helm")
    # Terraform
    if list(repo_path.rglob("*.tf")):
        infrastructure.add("Terraform")
    # Pulumi
    if (repo_path / "Pulumi.yaml").exists() or (repo_path / "Pulumi.yml").exists():
        infrastructure.add("Pulumi")
    # GitHub Actions
    if (repo_path / ".github" / "workflows").exists():
        tools.add("GitHub Actions")
    # GitLab CI
    if (repo_path / ".gitlab-ci.yml").exists():
        tools.add("GitLab CI")
    # CircleCI
    if (repo_path / ".circleci").exists():
        tools.add("CircleCI")
    # Make / Just
    if (repo_path / "Makefile").exists():
        tools.add("Make")
    if (repo_path / "justfile").exists() or (repo_path / "Justfile").exists():
        tools.add("Just")

    # ── Framework detection from package.json ─────────────────────────────────
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = _json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            JS_FRAMEWORKS: dict[str, str] = {
                "next": "Next.js", "react": "React", "vue": "Vue.js",
                "@angular/core": "Angular", "svelte": "Svelte",
                "nuxt": "Nuxt.js", "gatsby": "Gatsby",
                "express": "Express", "fastify": "Fastify",
                "@nestjs/core": "NestJS", "koa": "Koa",
                "hono": "Hono", "remix": "Remix",
            }
            for dep_key, fname in JS_FRAMEWORKS.items():
                if dep_key in deps:
                    frameworks.add(fname)
            # Database hints from JS deps
            DB_HINTS: dict[str, str] = {
                "pg": "PostgreSQL", "mysql2": "MySQL", "mongodb": "MongoDB",
                "redis": "Redis", "ioredis": "Redis", "sqlite3": "SQLite",
                "@prisma/client": "Prisma (ORM)", "typeorm": "TypeORM",
                "mongoose": "MongoDB", "sequelize": "Sequelize",
                "drizzle-orm": "Drizzle ORM",
            }
            for dep_key, dbname in DB_HINTS.items():
                if dep_key in deps:
                    databases.add(dbname)
        except Exception:
            pass

    # ── Framework detection from Python files ─────────────────────────────────
    py_dep_files = [
        repo_path / "requirements.txt",
        repo_path / "requirements-dev.txt",
        repo_path / "pyproject.toml",
    ]
    py_content = ""
    for f in py_dep_files:
        if f.exists():
            try:
                py_content += f.read_text(errors="ignore").lower() + "\n"
            except OSError:
                pass
    if py_content:
        PYTHON_FRAMEWORKS: dict[str, str] = {
            "fastapi": "FastAPI", "django": "Django",
            "flask": "Flask", "starlette": "Starlette",
            "litestar": "Litestar", "tornado": "Tornado",
            "sqlalchemy": "SQLAlchemy", "celery": "Celery",
            "pydantic": "Pydantic", "alembic": "Alembic",
        }
        for key, name in PYTHON_FRAMEWORKS.items():
            if key in py_content:
                frameworks.add(name)
        PYTHON_DBS: dict[str, str] = {
            "psycopg2": "PostgreSQL", "asyncpg": "PostgreSQL",
            "pymysql": "MySQL", "aiomysql": "MySQL",
            "pymongo": "MongoDB", "motor": "MongoDB",
            "redis": "Redis", "aioredis": "Redis",
            "sqlite": "SQLite", "qdrant": "Qdrant",
            "neo4j": "Neo4j", "elasticsearch": "Elasticsearch",
        }
        for key, dbname in PYTHON_DBS.items():
            if key in py_content:
                databases.add(dbname)

    # ── README summary ────────────────────────────────────────────────────────
    readme_summary: str | None = None
    for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
        readme_file = repo_path / readme_name
        if readme_file.exists():
            try:
                text = readme_file.read_text(errors="ignore")
                # Extract first non-empty, non-heading paragraph (≤400 chars)
                lines = [ln.strip() for ln in text.splitlines()]
                para_lines: list[str] = []
                for ln in lines:
                    if ln.startswith("#") or ln.startswith("=") or ln.startswith("-"):
                        if para_lines:
                            break
                        continue
                    if ln:
                        para_lines.append(ln)
                    elif para_lines:
                        break
                if para_lines:
                    readme_summary = " ".join(para_lines)[:400]
            except OSError:
                pass
            break

    return {
        "languages": sorted(languages),
        "primary_language": primary_language,
        "frameworks": sorted(frameworks),
        "databases": sorted(databases),
        "infrastructure": sorted(infrastructure),
        "package_managers": sorted(package_managers),
        "tools": sorted(tools),
        "readme_summary": readme_summary,
    }


def _collect_stats(repo_path: Path) -> dict:
    """Compute aggregate repository statistics including git metrics.

    Args:
        repo_path: Absolute path to the cloned repository on disk.

    Returns:
        Dict with ``total_files``, ``total_lines``, ``total_size_bytes``,
        ``modules``, ``commits``, ``contributors``, ``dependencies``.
    """
    total_files = 0
    total_lines = 0
    total_bytes = 0
    modules: set[str] = set()

    TEXT_EXTENSIONS = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs",
        ".kt", ".cs", ".cpp", ".c", ".rb", ".php", ".swift", ".scala",
        ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".tf", ".sql",
    }
    SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build", "target", ".git", ".venv", "venv"}

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(repo_path).parts
        if any(p.startswith(".") or p in SKIP_DIRS for p in parts):
            continue
        total_files += 1
        total_bytes += path.stat().st_size
        if path.suffix in TEXT_EXTENSIONS:
            try:
                total_lines += path.read_text(errors="ignore").count("\n")
            except OSError:
                pass
        # Top-level dirs are treated as modules
        if len(parts) > 1:
            modules.add(parts[0])

    # ── Git metrics ───────────────────────────────────────────────────────────
    commits = 0
    contributors = 0
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "--oneline"],
            capture_output=True, text=True, cwd=str(repo_path), timeout=10
        )
        if result.returncode == 0:
            commits = len(result.stdout.strip().splitlines())
        result2 = subprocess.run(
            ["git", "log", "--format=%ae"],
            capture_output=True, text=True, cwd=str(repo_path), timeout=10
        )
        if result2.returncode == 0:
            contributors = len(set(result2.stdout.strip().splitlines()))
    except Exception:
        pass

    # ── Dependencies count (rough) ────────────────────────────────────────────
    dependencies = 0
    try:
        import json as _json
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            pkg = _json.loads(pkg_json.read_text())
            dependencies += len(pkg.get("dependencies", {}))
            dependencies += len(pkg.get("devDependencies", {}))
        req_txt = repo_path / "requirements.txt"
        if req_txt.exists():
            lines = [ln.strip() for ln in req_txt.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
            dependencies += len(lines)
        cargo = repo_path / "Cargo.toml"
        if cargo.exists():
            txt = cargo.read_text()
            dependencies += txt.count("\n") - txt.count("[")
        go_mod = repo_path / "go.mod"
        if go_mod.exists():
            lines = [ln for ln in go_mod.read_text().splitlines() if ln.strip().startswith("require") or (ln.startswith("\t") and "/" in ln)]
            dependencies += len(lines)
    except Exception:
        pass

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "total_size_bytes": total_bytes,
        "modules": sorted(modules),
        "module_count": len(modules),
        "commits": commits,
        "contributors": contributors,
        "dependencies": dependencies,
    }


def _store_files_in_minio(repo_id: str, repo_path: Path) -> int:
    """Upload all repository files to MinIO under the repo's key prefix.

    Uses the synchronous MinIO SDK directly (suitable for Celery workers).

    Args:
        repo_id: UUID string of the repository.
        repo_path: Absolute path to the cloned directory.

    Returns:
        Number of files uploaded.
    """
    from minio import Minio

    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    bucket = settings.minio_bucket_repos
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    uploaded = 0
    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(repo_path)
        parts = relative.parts
        # Skip noise directories
        if any(p.startswith(".") or p in ("node_modules", "__pycache__", "dist", "build", "target") for p in parts):
            continue
        object_key = f"repos/{repo_id}/raw/{relative.as_posix()}"
        try:
            client.fput_object(
                bucket_name=bucket,
                object_name=object_key,
                file_path=str(file_path),
            )
            uploaded += 1
        except Exception as exc:
            logger.warning("minio_upload_failed", key=object_key, error=str(exc))

    return uploaded


# ── Celery tasks ───────────────────────────────────────────────────────────────


class BaseTask(Task):
    """Base Celery task class with automatic failure handling.

    On unhandled exceptions, marks the associated IndexJob and Repository
    as ``failed`` with the error detail persisted to the database.
    """

    abstract = True

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: object,
    ) -> None:
        """Persist failure state to the database on unhandled task exception."""
        repo_id: str | None = kwargs.get("repo_id")
        job_id: str | None = kwargs.get("job_id")
        error = f"{type(exc).__name__}: {exc}"
        logger.error(
            "task_unhandled_failure",
            task_id=task_id,
            repo_id=repo_id,
            error=error,
        )
        try:
            with get_sync_session() as session:
                if job_id:
                    _update_job(
                        session,
                        job_id,
                        status="failed",
                        error_message=error,
                        finished_at=datetime.now(UTC),
                    )
                if repo_id:
                    _update_repo_status(session, repo_id, "failed", error_message=error)
        except Exception as db_exc:
            logger.error("failure_handler_db_error", error=str(db_exc))


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.tasks.repo_tasks.clone_and_index_repo",
    queue="indexing",
    max_retries=2,
    default_retry_delay=60,
)
def clone_and_index_repo(
    self: Task,
    *,
    repo_id: str,
    job_id: str,
    url: str | None,
    local_path: str | None,
    zip_minio_key: str | None = None,
    branch: str | None,
    auth_token: str | None,
    is_private: bool,
) -> dict:
    """Clone a remote repository (or accept a local path) and store raw files in MinIO.

    Pipeline stages:
    1. ``cloning``  — git clone / validate local path.
    2. ``uploading`` — stream all files to MinIO.
    3. ``analysing`` — detect tech stack and collect statistics.
    4. ``complete``  — mark job and repository as done.

    Args:
        repo_id: UUID string of the Repository record.
        job_id: UUID string of the IndexJob record.
        url: Remote HTTPS/SSH clone URL, or None for local imports.
        local_path: Absolute container path for local imports, or None.
        branch: Git branch to check out, or None to auto-detect the remote's
            default branch.
        auth_token: PAT for private HTTPS repos (not persisted).
        is_private: Whether the repository is private.

    Returns:
        Dict summarising the completed job.
    """
    import git

    logger.info("clone_task_started", repo_id=repo_id, job_id=job_id, url=url)
    tmp_dir: str | None = None

    try:
        with get_sync_session() as session:
            _update_job(
                session,
                job_id,
                status="running",
                progress=0,
                current_stage="cloning",
                started_at=datetime.now(UTC),
            )
            _update_repo_status(session, repo_id, "cloning")

        # ── Stage 1: Clone ───────────────────────────────────────────────────
        if url:
            tmp_dir = tempfile.mkdtemp(prefix=f"codeatlas_{repo_id}_")
            clone_url = normalize_clone_url(url, auth_token)

            # Resolve the branch against the remote. Repositories differ on
            # whether the default is `main` or `master`, so never assume.
            resolved_branch = resolve_branch(url, branch or None, auth_token)
            if resolved_branch != branch:
                logger.info(
                    "branch_resolved",
                    repo_id=repo_id,
                    requested=branch,
                    resolved=resolved_branch,
                )
                with get_sync_session() as session:
                    session.execute(
                        update(Repository)
                        .where(Repository.id == uuid.UUID(repo_id))
                        .values(default_branch=resolved_branch)
                    )
                    session.commit()
            branch = resolved_branch

            logger.info("git_clone_started", url=url, branch=branch, dest=tmp_dir)
            git.Repo.clone_from(
                clone_url,
                tmp_dir,
                branch=branch,
                depth=1,             # shallow clone for speed
                no_single_branch=False,
            )
            repo_path = Path(tmp_dir)
        elif zip_minio_key:
            # Download ZIP from MinIO (shared object store) and extract locally.
            from minio import Minio as _Minio

            _mc = _Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            tmp_zip_path = os.path.join(tempfile.gettempdir(), f"codeatlas_zip_{repo_id}.zip")
            _mc.fget_object(settings.minio_bucket_repos, zip_minio_key, tmp_zip_path)
            logger.info("zip_downloaded_from_minio", key=zip_minio_key, dest=tmp_zip_path)

            extract_dir = tempfile.mkdtemp(prefix=f"codeatlas_{repo_id}_")
            with zipfile.ZipFile(tmp_zip_path, "r") as zf:
                zf.extractall(extract_dir)
            os.unlink(tmp_zip_path)

            # If ZIP contains a single top-level dir, use that as root
            extracted = list(Path(extract_dir).iterdir())
            repo_path = (
                extracted[0]
                if len(extracted) == 1 and extracted[0].is_dir()
                else Path(extract_dir)
            )
            tmp_dir = str(repo_path)  # track for cleanup
        elif local_path:
            repo_path = Path(local_path)
            if not repo_path.exists():
                raise FileNotFoundError(f"Local path not found: {local_path}")
        else:
            raise ValueError("One of url, local_path, or zip_minio_key must be provided.")

        with get_sync_session() as session:
            _update_job(session, job_id, progress=25, current_stage="uploading")
            _update_repo_status(session, repo_id, "uploading")

        # ── Stage 2: Upload to MinIO ─────────────────────────────────────────
        uploaded = _store_files_in_minio(repo_id, repo_path)
        logger.info("minio_upload_complete", repo_id=repo_id, files=uploaded)

        with get_sync_session() as session:
            _update_job(session, job_id, progress=60, current_stage="analysing")
            _update_repo_status(session, repo_id, "analysing")

        # ── Stage 3: Tech stack + stats ──────────────────────────────────────
        tech_stack = _detect_tech_stack(repo_path)
        stats = _collect_stats(repo_path)
        stats["files_stored"] = uploaded
        logger.info("analysis_complete", repo_id=repo_id, stats=stats)

        # ── Stage 4: Finalise ────────────────────────────────────────────────
        now = datetime.now(UTC)
        readme_summary = tech_stack.pop("readme_summary", None)
        with get_sync_session() as session:
            _update_job(
                session,
                job_id,
                status="complete",
                progress=100,
                current_stage="complete",
                finished_at=now,
            )
            values: dict = {
                "index_status": "cloned",
                "tech_stack": tech_stack,
                "stats": stats,
                "clone_path": f"repos/{repo_id}/raw",
                "last_indexed_at": now,
            }
            if readme_summary:
                values["description"] = readme_summary
            session.execute(
                update(Repository).where(Repository.id == uuid.UUID(repo_id)).values(**values)
            )
            session.commit()

        logger.info(
            "clone_task_complete",
            repo_id=repo_id,
            job_id=job_id,
            files=uploaded,
            languages=tech_stack.get("languages"),
        )

        # ── Chain: trigger parse task ────────────────────────────────────────
        # Create a new IndexJob for the parse stage and dispatch it.
        parse_job_id: str | None = None
        try:
            with get_sync_session() as session:
                from sqlalchemy import insert
                from app.models.index_job import IndexJob as _IndexJob
                parse_job_uuid = __import__("uuid").uuid4()
                session.execute(
                    insert(_IndexJob).values(
                        id=parse_job_uuid,
                        repo_id=__import__("uuid").UUID(repo_id),
                        job_type="parse",
                        status="queued",
                        progress=0,
                    )
                )
                session.commit()
                parse_job_id = str(parse_job_uuid)

            from app.workers.tasks.parser_tasks import parse_repository
            parse_repository.apply_async(
                kwargs={
                    "repo_id": repo_id,
                    "job_id": parse_job_id,
                    "repo_name": (url or "").rsplit("/", 1)[-1].replace(".git", "") if url else repo_id,
                    "repo_url": url,
                },
                countdown=2,  # brief delay to let DB writes settle
            )
            logger.info("parse_task_dispatched", repo_id=repo_id, parse_job_id=parse_job_id)
        except Exception as chain_exc:
            logger.error("parse_chain_failed", repo_id=repo_id, error=str(chain_exc))

        return {
            "repo_id": repo_id,
            "job_id": job_id,
            "files_stored": uploaded,
            "tech_stack": tech_stack,
            "stats": stats,
            "parse_job_id": parse_job_id,
        }

    except SoftTimeLimitExceeded:
        error = "Task exceeded the 10-minute soft time limit."
        logger.error("clone_task_timeout", repo_id=repo_id)
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="failed", error_message=error,
                finished_at=datetime.now(UTC),
            )
            _update_repo_status(session, repo_id, "failed", error_message=error)
        raise

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.error("clone_task_error", repo_id=repo_id, error=error)
        with get_sync_session() as session:
            _update_job(
                session, job_id,
                status="failed", error_message=error,
                finished_at=datetime.now(UTC),
            )
            _update_repo_status(session, repo_id, "failed", error_message=error)
        raise self.retry(exc=exc) from exc

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.tasks.repo_tasks.delete_repo_artifacts",
    queue="cleanup",
)
def delete_repo_artifacts(self: Task, *, repo_id: str) -> dict:
    """Remove all MinIO objects stored under a repository's key prefix.

    Called asynchronously when a repository is deleted via the API so that
    the HTTP response does not block on potentially slow storage deletion.

    Args:
        repo_id: UUID string of the deleted repository.

    Returns:
        Dict with ``deleted_count``.
    """
    from minio import Minio
    from minio.deleteobjects import DeleteObject

    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    bucket = settings.minio_bucket_repos
    prefix = f"repos/{repo_id}/"

    try:
        objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
        delete_list = [DeleteObject(obj.object_name) for obj in objects]
        if delete_list:
            errors = list(client.remove_objects(bucket, iter(delete_list)))
            if errors:
                logger.warning(
                    "minio_delete_errors",
                    repo_id=repo_id,
                    count=len(errors),
                )
        logger.info(
            "artifact_cleanup_complete",
            repo_id=repo_id,
            deleted=len(delete_list),
        )
        return {"repo_id": repo_id, "deleted_count": len(delete_list)}
    except Exception as exc:
        logger.error("artifact_cleanup_failed", repo_id=repo_id, error=str(exc))
        raise
