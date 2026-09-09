# 16 — Observability

## Overview

CodeAtlas AI implements the **three pillars of observability**: metrics (Prometheus + Grafana), logs (structured JSON), and traces (OpenTelemetry). All FastAPI services expose `/metrics` and `/health` endpoints.

---

## Metrics: Prometheus

### Service Metrics Exposed

Every FastAPI service exposes these metrics at `/metrics`:

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# HTTP request metrics (auto-instrumented via prometheus-fastapi-instrumentator)
http_requests_total          # Counter: total HTTP requests by method, endpoint, status
http_request_duration_seconds # Histogram: request duration
http_requests_in_progress    # Gauge: concurrent requests

# Business metrics (per service)
```

### AI Service Metrics

```python
llm_requests_total = Counter(
    "codeatlas_llm_requests_total",
    "Total LLM API calls",
    ["provider", "model", "status"]
)

llm_tokens_used_total = Counter(
    "codeatlas_llm_tokens_total",
    "Total tokens consumed",
    ["provider", "model", "type"]  # type: prompt|completion
)

llm_request_duration_seconds = Histogram(
    "codeatlas_llm_duration_seconds",
    "LLM request duration",
    ["provider", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)

rag_retrieval_duration_seconds = Histogram(
    "codeatlas_rag_retrieval_seconds",
    "RAG retrieval pipeline duration",
    ["retriever"]
)

chat_sessions_active = Gauge(
    "codeatlas_chat_sessions_active",
    "Active chat sessions"
)
```

### Parser Service Metrics

```python
files_parsed_total = Counter(
    "codeatlas_files_parsed_total",
    "Files parsed",
    ["language", "status"]
)

symbols_extracted_total = Counter(
    "codeatlas_symbols_extracted_total",
    "Symbols extracted",
    ["kind", "language"]
)

parse_duration_seconds = Histogram(
    "codeatlas_parse_duration_seconds",
    "File parse duration",
    ["language"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5]
)
```

### Worker/Queue Metrics

```python
celery_tasks_total = Counter(
    "codeatlas_celery_tasks_total",
    "Celery task count",
    ["task_name", "status"]  # status: received|started|succeeded|failed|retried
)

celery_queue_length = Gauge(
    "codeatlas_celery_queue_length",
    "Tasks waiting in queue",
    ["queue_name"]
)

celery_task_duration_seconds = Histogram(
    "codeatlas_celery_task_seconds",
    "Task execution duration",
    ["task_name"]
)
```

---

## prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "codeatlas-services"
    static_configs:
      - targets:
          - "auth:8001"
          - "repo-service:8002"
          - "parser:8003"
          - "ai:8004"
          - "diagram:8005"
          - "docs:8006"
          - "security:8007"
          - "search:8008"
    metrics_path: /metrics

  - job_name: "postgres"
    static_configs:
      - targets: ["postgres-exporter:9187"]

  - job_name: "redis"
    static_configs:
      - targets: ["redis-exporter:9121"]

  - job_name: "qdrant"
    static_configs:
      - targets: ["qdrant:6333"]
    metrics_path: /metrics

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

rule_files:
  - /etc/prometheus/rules/*.yml
```

---

## Grafana Dashboards

### Pre-built Dashboards

| Dashboard | Purpose |
|-----------|---------|
| **Overview** | System health at a glance; all service UP/DOWN, error rates |
| **AI Service** | LLM requests/min, token usage, latency percentiles, model distribution |
| **Parser** | Files/sec, language breakdown, parse error rate, queue depth |
| **RAG Performance** | Retrieval latency, chunk hit rate, reranker stats |
| **Security Scanner** | Findings by severity over time, scan duration, false positive rate |
| **Infrastructure** | PostgreSQL connections, Redis memory, Qdrant vector count, Neo4j queries |
| **Celery Queue** | Queue depth, task throughput, failed task rate, worker utilization |
| **User Activity** | Active users, chat sessions, API usage by endpoint |

---

## Alerting Rules

```yaml
# /infra/prometheus/rules/codeatlas.yml
groups:
  - name: codeatlas-critical
    rules:
      - alert: ServiceDown
        expr: up{job="codeatlas-services"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is DOWN"

      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m])
          / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "Error rate > 5% on {{ $labels.instance }}"

      - alert: LLMHighLatency
        expr: |
          histogram_quantile(0.95, codeatlas_llm_duration_seconds_bucket) > 30
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM P95 latency > 30s"

      - alert: CeleryQueueBacklog
        expr: codeatlas_celery_queue_length > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Celery queue backlog > 100 tasks"

      - alert: PostgresDiskFull
        expr: |
          pg_database_size_bytes / pg_tablespace_size_bytes > 0.85
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "PostgreSQL disk usage > 85%"
```

---

## Logging: Structured JSON

All services output structured JSON logs:

```python
import structlog

logger = structlog.get_logger()

# Example log entry
logger.info(
    "chat_request_completed",
    user_id=user_id,
    repo_id=repo_id,
    session_id=session_id,
    tokens_used=tokens,
    duration_ms=duration,
    model=model_name,
    citations_count=len(citations)
)
```

**Log format:**
```json
{
  "timestamp": "2026-07-17T12:00:00.123Z",
  "level": "info",
  "service": "ai-service",
  "event": "chat_request_completed",
  "user_id": "uuid",
  "repo_id": "uuid",
  "tokens_used": 847,
  "duration_ms": 2340,
  "model": "llama3.2",
  "citations_count": 3,
  "trace_id": "abc123",
  "span_id": "def456"
}
```

---

## Tracing: OpenTelemetry

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Auto-instrument FastAPI and HTTP clients
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

# Manual spans for key operations
with trace.get_tracer(__name__).start_as_current_span("rag_pipeline") as span:
    span.set_attribute("repo_id", repo_id)
    span.set_attribute("query_length", len(query))
    results = await retrieve_chunks(query, repo_id)
    span.set_attribute("chunks_retrieved", len(results))
```

Traces exported to: **Jaeger** (local) or **OpenTelemetry Collector** → Tempo/Datadog/New Relic (cloud).

---

## Health Check Endpoints

Every service implements:

```
GET /health    # Liveness: returns 200 if process is alive
GET /ready     # Readiness: returns 200 if dependencies (DB, etc.) are reachable
GET /metrics   # Prometheus metrics
```

```python
@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service", "version": VERSION}

@app.get("/ready")
async def ready():
    checks = {
        "postgres": await check_postgres(),
        "qdrant": await check_qdrant(),
        "neo4j": await check_neo4j(),
        "redis": await check_redis(),
    }
    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks}
    )
```
