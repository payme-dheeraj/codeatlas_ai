"""Prometheus business metrics for CodeAtlas AI.

All counters, histograms, and gauges are registered once at import time.
Import and update them from any module that needs instrumentation.

Usage:
    from app.core.metrics import llm_requests_total, parse_duration_seconds
    llm_requests_total.labels(provider="openai", model="gpt-4o", status="success").inc()
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── LLM / AI Service ──────────────────────────────────────────────────────────

llm_requests_total = Counter(
    "codeatlas_llm_requests_total",
    "Total LLM API calls",
    ["provider", "model", "status"],
)

llm_tokens_used_total = Counter(
    "codeatlas_llm_tokens_total",
    "Total tokens consumed",
    ["provider", "model", "type"],  # type: prompt | completion
)

llm_request_duration_seconds = Histogram(
    "codeatlas_llm_duration_seconds",
    "LLM request duration in seconds",
    ["provider", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

rag_retrieval_duration_seconds = Histogram(
    "codeatlas_rag_retrieval_seconds",
    "RAG retrieval pipeline duration in seconds",
    ["retriever"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
)

chat_sessions_active = Gauge(
    "codeatlas_chat_sessions_active",
    "Currently active chat sessions",
)

# ── Parser Service ────────────────────────────────────────────────────────────

files_parsed_total = Counter(
    "codeatlas_files_parsed_total",
    "Total files parsed",
    ["language", "status"],
)

symbols_extracted_total = Counter(
    "codeatlas_symbols_extracted_total",
    "Total symbols extracted",
    ["kind", "language"],
)

parse_duration_seconds = Histogram(
    "codeatlas_parse_duration_seconds",
    "File parse duration in seconds",
    ["language"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5],
)

# ── Celery / Worker ───────────────────────────────────────────────────────────

celery_tasks_total = Counter(
    "codeatlas_celery_tasks_total",
    "Celery task count by name and status",
    ["task_name", "status"],  # status: received | started | succeeded | failed | retried
)

celery_queue_length = Gauge(
    "codeatlas_celery_queue_length",
    "Number of tasks waiting in each queue",
    ["queue_name"],
)

celery_task_duration_seconds = Histogram(
    "codeatlas_celery_task_seconds",
    "Celery task execution duration in seconds",
    ["task_name"],
    buckets=[1, 5, 15, 30, 60, 180, 600, 1800],
)

# ── Security Scanner ──────────────────────────────────────────────────────────

security_scans_total = Counter(
    "codeatlas_security_scans_total",
    "Total security scans",
    ["status"],
)

security_findings_total = Counter(
    "codeatlas_security_findings_total",
    "Total security findings",
    ["severity", "category"],
)

scan_duration_seconds = Histogram(
    "codeatlas_scan_duration_seconds",
    "Security scan duration in seconds",
    buckets=[5, 15, 30, 60, 120, 300, 600],
)

# ── Documentation & Diagrams ──────────────────────────────────────────────────

docs_generated_total = Counter(
    "codeatlas_docs_generated_total",
    "Total documentation artifacts generated",
    ["doc_type"],
)

diagrams_generated_total = Counter(
    "codeatlas_diagrams_generated_total",
    "Total diagrams generated",
    ["diagram_type", "format"],
)

diagram_render_duration_seconds = Histogram(
    "codeatlas_diagram_render_seconds",
    "Diagram render duration (Kroki) in seconds",
    ["diagram_format", "output_format"],
    buckets=[0.5, 1, 2, 5, 10, 30],
)

# ── Repository Operations ─────────────────────────────────────────────────────

repo_index_duration_seconds = Histogram(
    "codeatlas_repo_index_seconds",
    "Repository indexing duration in seconds",
    buckets=[10, 30, 60, 120, 300, 600, 1800],
)

repo_size_files = Gauge(
    "codeatlas_repo_size_files",
    "Number of files in the indexed repository",
)

# ── Webhooks ──────────────────────────────────────────────────────────────────

webhook_deliveries_total = Counter(
    "codeatlas_webhook_deliveries_total",
    "Total webhook delivery attempts",
    ["event", "status"],  # status: success | failure
)
