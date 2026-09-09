# CodeAtlas AI

**Enterprise-grade AI Code Intelligence Platform** — repository ingestion, semantic understanding, AI chat, security scanning, diagram generation, and documentation automation.

---

## Quick Start

### Prerequisites

- Docker ≥ 24 + Docker Compose v2
- 8 GB RAM minimum (16 GB recommended for Ollama)
- macOS, Linux, or WSL2

### 1. Clone and configure

```bash
git clone https://github.com/your-org/codeatlas-ai.git
cd codeatlas-ai
make env          # copies .env.example → .env
```

Edit `.env` and set at minimum:
```bash
SECRET_KEY=<32-char random string>
DB_PASSWORD=<secure password>
NEO4J_PASSWORD=<secure password>
```

### 2. Start core services

```bash
make up
```

Services started: PostgreSQL, Redis, Qdrant, Neo4j, MinIO, Kroki, backend API, Celery worker, nginx gateway.

### 3. Run migrations

```bash
make migrate
```

### 4. Access the API

| URL | Description |
|-----|-------------|
| `http://localhost/docs` | Swagger UI |
| `http://localhost/redoc` | ReDoc |
| `http://localhost/health` | Liveness probe |
| `http://localhost/ready` | Readiness probe |
| `http://localhost:9001` | MinIO console |
| `http://localhost:7474` | Neo4j browser |

---

## Profiles

```bash
# Include Ollama (local LLM — GPU optional)
make up-ai

# Include Prometheus + Grafana monitoring
make up-monitoring

# Start everything
make up-all

# Pull Ollama models after startup
make pull-models
```

---

## Architecture

```
nginx (:80)
  └── backend FastAPI (:8000)
        ├── PostgreSQL (:5432)  — relational data
        ├── Redis (:6379)        — cache + Celery broker
        ├── Qdrant (:6333)       — vector embeddings
        ├── Neo4j (:7687)        — code knowledge graph
        └── MinIO (:9000)        — object storage (repos, diagrams)

Celery Worker
  └── indexing | cleanup | default queues

Kroki (:8009) — Mermaid / PlantUML / D2 renderer
Ollama (:11434) — local LLM (optional, ai profile)
Prometheus (:9090) + Grafana (:3001) — monitoring (monitoring profile)
```

---

## Features

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Repository Intelligence (import, metadata, tech stack) | ✅ |
| 2 | Semantic Code Understanding (tree-sitter, symbols, Neo4j) | ✅ |
| 3 | AI Chat Over Code (RAG, streaming, citations) | ✅ |
| 4 | Diagram Generation (architecture, ER, sequence, dependency) | ✅ |
| 5 | Security Scanning (secrets, SAST, IaC, SARIF export) | ✅ |
| 6 | Documentation Service (README, API ref, ADR, wiki) | ✅ |
| 7 | Enterprise (RBAC, audit log, PR review, webhooks, health score) | ✅ |

---

## Development

```bash
# Install dependencies locally
make install

# Run with hot-reload
make dev

# Tests
make test           # all tests
make test-unit      # unit only
make test-integration  # integration only

# Code quality
make lint
make format
make typecheck

# Database
make migration MSG="add_new_table"   # create migration
make migrate-local                   # apply locally
```

---

## API Overview

All endpoints are under `/api/v1`. Authentication uses JWT Bearer tokens.

### Auth
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`

### Repositories
- `POST /api/v1/repos/` — import repository
- `GET /api/v1/repos/{id}` — get repository details
- `POST /api/v1/repos/{id}/reindex` — trigger re-indexing

### Search & Chat
- `POST /api/v1/search/` — semantic code search
- `POST /api/v1/chat/sessions` — create chat session
- `GET /api/v1/chat/sessions/{id}/stream` — streaming AI response (SSE)

### Security
- `POST /api/v1/repos/{id}/scans` — trigger security scan
- `GET /api/v1/repos/{id}/scans/{scan_id}/findings` — list findings

### Diagrams
- `POST /api/v1/repos/{id}/diagrams/generate` — generate diagrams
- `GET /api/v1/repos/{id}/diagrams/{type}` — get diagram by type

### Documentation
- `POST /api/v1/repos/{id}/docs/generate` — generate docs
- `GET /api/v1/repos/{id}/docs/{type}` — get latest document

### Enterprise
- `GET /api/v1/repos/{id}/health` — repository health score
- `POST /api/v1/repos/{id}/pr-review` — AI PR/MR review
- `POST /api/v1/repos/{id}/webhooks` — create webhook
- `GET /api/v1/admin/audit-logs` — audit log (admin)
- `PUT /api/v1/admin/users/{id}/role` — update role (admin)

---

## LLM Configuration

| Provider | `LLM_PROVIDER` | Additional Vars |
|----------|---------------|-----------------|
| Ollama (local) | `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| OpenAI | `openai` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |

---

## Observability

- **Metrics** — Prometheus scrapes `/metrics` every 15s. Grafana dashboard at `:3001`.
- **Logs** — Structured JSON via `structlog`. Set `LOG_FORMAT=json` in production.
- **Traces** — OpenTelemetry OTLP. Set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT`.

---

## License

MIT — see [LICENSE](LICENSE).
