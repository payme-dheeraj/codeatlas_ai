"""Celery application factory and configuration.

The Celery app is created once at module import time and shared by all
worker processes.  Beat schedule and task routing are configured here.
"""

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun
from kombu import Exchange, Queue

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Application factory ────────────────────────────────────────────────────────

celery_app = Celery(
    "codeatlas",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.repo_tasks",
        "app.workers.tasks.parser_tasks",
        "app.workers.tasks.embedding_tasks",
        "app.workers.tasks.security_tasks",
        "app.workers.tasks.document_tasks",
        "app.workers.tasks.diagram_tasks",
    ],
)

# ── Configuration ──────────────────────────────────────────────────────────────

celery_app.conf.update(
    # Serialisation
    task_serializer=settings.celery_task_serializer,
    result_serializer="json",
    accept_content=["json"],
    # Reliability
    task_acks_late=True,
    # Must stay False: with acks_late, a task whose child process is killed
    # (e.g. OOM while loading the embedding model) would otherwise be requeued
    # forever, looping indefinitely instead of surfacing the failure.
    task_reject_on_worker_lost=False,
    task_track_started=True,
    result_expires=settings.celery_result_expires,
    # Concurrency / execution
    worker_prefetch_multiplier=1,  # One task at a time per worker for long-running jobs
    # Recycle children periodically so the loaded ML model's memory is released.
    worker_max_tasks_per_child=8,
    task_soft_time_limit=600,      # 10 min soft limit → SoftTimeLimitExceeded
    task_time_limit=900,           # 15 min hard kill
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Retry defaults
    task_default_retry_delay=30,   # seconds
    task_max_retries=3,
)

# ── Named queues ───────────────────────────────────────────────────────────────

default_exchange = Exchange("codeatlas", type="direct")

celery_app.conf.task_queues = (
    Queue("indexing", default_exchange, routing_key="indexing"),
    Queue("cleanup", default_exchange, routing_key="cleanup"),
    Queue("default", default_exchange, routing_key="default"),
)

celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "codeatlas"
celery_app.conf.task_default_routing_key = "default"

celery_app.conf.task_routes = {
    "app.workers.tasks.repo_tasks.clone_and_index_repo": {"queue": "indexing"},
    "app.workers.tasks.repo_tasks.delete_repo_artifacts": {"queue": "cleanup"},
}

# ── Observability signals ──────────────────────────────────────────────────────


@task_prerun.connect
def on_task_prerun(
    task_id: str,
    task: object,
    args: tuple,
    kwargs: dict,
    **_: object,
) -> None:
    """Log task start with structured fields."""
    logger.info(
        "celery_task_started",
        task_id=task_id,
        task_name=getattr(task, "name", "unknown"),
    )


@task_postrun.connect
def on_task_postrun(
    task_id: str,
    task: object,
    state: str,
    **_: object,
) -> None:
    """Log task completion."""
    logger.info(
        "celery_task_finished",
        task_id=task_id,
        task_name=getattr(task, "name", "unknown"),
        state=state,
    )


@task_failure.connect
def on_task_failure(
    task_id: str,
    exception: Exception,
    traceback: object,
    **_: object,
) -> None:
    """Log task failure with exception details."""
    logger.error(
        "celery_task_failed",
        task_id=task_id,
        error=str(exception),
        exc_type=type(exception).__name__,
    )
