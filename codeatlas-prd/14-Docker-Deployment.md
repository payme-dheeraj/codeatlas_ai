# 14 — Docker Deployment

## Overview

CodeAtlas AI is Docker-first. A single `docker compose up -d` command starts all 18 services. The Compose file is organized into profiles: `core`, `ai`, `monitoring`, and `dev`.

---

## Service Matrix

| Service | Image | Ports | Profile |
|---------|-------|-------|---------|
| `frontend` | `codeatlas/frontend:latest` | 3000 | core |
| `gateway` | `nginx:1.25-alpine` | 80, 443 | core |
| `auth` | `codeatlas/auth:latest` | 8001 | core |
| `repo-service` | `codeatlas/repo-service:latest` | 8002 | core |
| `parser` | `codeatlas/parser:latest` | 8003 | core |
| `ai` | `codeatlas/ai-service:latest` | 8004 | core |
| `diagram` | `codeatlas/diagram:latest` | 8005 | core |
| `docs` | `codeatlas/docs:latest` | 8006 | core |
| `security` | `codeatlas/security:latest` | 8007 | core |
| `search` | `codeatlas/search:latest` | 8008 | core |
| `worker` | `codeatlas/worker:latest` | — | core |
| `postgres` | `postgres:16-alpine` | 5432 | core |
| `redis` | `redis:7-alpine` | 6379 | core |
| `qdrant` | `qdrant/qdrant:v1.9.0` | 6333, 6334 | core |
| `neo4j` | `neo4j:5.18-community` | 7474, 7687 | core |
| `minio` | `minio/minio:latest` | 9000, 9001 | core |
| `ollama` | `ollama/ollama:latest` | 11434 | ai |
| `kroki` | `yuzutech/kroki:latest` | 8000 | core |
| `prometheus` | `prom/prometheus:latest` | 9090 | monitoring |
| `grafana` | `grafana/grafana:latest` | 3001 | monitoring |

---

## docker-compose.yml

```yaml
version: "3.9"

x-common-env: &common-env
  POSTGRES_URL: postgresql://codeatlas:password@postgres:5432/codeatlas
  REDIS_URL: redis://redis:6379/0
  QDRANT_URL: http://qdrant:6333
  NEO4J_URL: bolt://neo4j:7687
  NEO4J_AUTH: neo4j/password
  MINIO_ENDPOINT: minio:9000
  MINIO_ACCESS_KEY: minioadmin
  MINIO_SECRET_KEY: minioadmin
  SECRET_KEY: ${SECRET_KEY:-change-me-in-production}
  ENVIRONMENT: ${ENVIRONMENT:-development}

services:

  # ──────────────────────────────────────────
  # INFRASTRUCTURE
  # ──────────────────────────────────────────

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: codeatlas
      POSTGRES_USER: codeatlas
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U codeatlas"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  qdrant:
    image: qdrant/qdrant:v1.9.0
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      QDRANT__SERVICE__HTTP_PORT: 6333
      QDRANT__SERVICE__GRPC_PORT: 6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 15s
      timeout: 5s
      retries: 5

  neo4j:
    image: neo4j:5.18-community
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_memory_heap_max__size: 2G
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "password", "RETURN 1"]
      interval: 20s
      timeout: 10s
      retries: 10

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ──────────────────────────────────────────
  # AI RUNTIME
  # ──────────────────────────────────────────

  ollama:
    image: ollama/ollama:latest
    profiles: ["ai"]
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  # ──────────────────────────────────────────
  # DIAGRAM RENDERER
  # ──────────────────────────────────────────

  kroki:
    image: yuzutech/kroki:latest
    environment:
      KROKI_MERMAID_HOST: mermaid
      KROKI_PLANTUML_HOST: plantuml

  # ──────────────────────────────────────────
  # APPLICATION SERVICES
  # ──────────────────────────────────────────

  auth:
    image: codeatlas/auth:latest
    build: ./services/auth
    environment:
      <<: *common-env
      JWT_SECRET: ${JWT_SECRET:-change-me}
      JWT_EXPIRE_MINUTES: 60
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}

  repo-service:
    image: codeatlas/repo-service:latest
    build: ./services/repo-service
    environment:
      <<: *common-env
    volumes:
      - repo_cache:/tmp/repos
    depends_on:
      postgres: {condition: service_healthy}
      minio: {condition: service_healthy}
      redis: {condition: service_healthy}

  parser:
    image: codeatlas/parser:latest
    build: ./services/parser
    environment:
      <<: *common-env
      AI_SERVICE_URL: http://ai:8004
    depends_on:
      postgres: {condition: service_healthy}
      qdrant: {condition: service_healthy}
      neo4j: {condition: service_healthy}

  ai:
    image: codeatlas/ai-service:latest
    build: ./services/ai-service
    environment:
      <<: *common-env
      LLM_PROVIDER: ${LLM_PROVIDER:-ollama}
      OLLAMA_BASE_URL: http://ollama:11434
      OLLAMA_MODEL: ${OLLAMA_MODEL:-llama3.2}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
    depends_on:
      qdrant: {condition: service_healthy}
      neo4j: {condition: service_healthy}
      redis: {condition: service_healthy}

  diagram:
    image: codeatlas/diagram:latest
    build: ./services/diagram
    environment:
      <<: *common-env
      KROKI_URL: http://kroki:8000
      AI_SERVICE_URL: http://ai:8004
    depends_on:
      postgres: {condition: service_healthy}
      neo4j: {condition: service_healthy}

  docs:
    image: codeatlas/docs:latest
    build: ./services/docs
    environment:
      <<: *common-env
      AI_SERVICE_URL: http://ai:8004
    depends_on:
      postgres: {condition: service_healthy}
      minio: {condition: service_healthy}

  security:
    image: codeatlas/security:latest
    build: ./services/security
    environment:
      <<: *common-env
      AI_SERVICE_URL: http://ai:8004
    depends_on:
      postgres: {condition: service_healthy}
      minio: {condition: service_healthy}

  search:
    image: codeatlas/search:latest
    build: ./services/search
    environment:
      <<: *common-env
    depends_on:
      postgres: {condition: service_healthy}
      qdrant: {condition: service_healthy}
      neo4j: {condition: service_healthy}

  worker:
    image: codeatlas/worker:latest
    build: ./services/worker
    command: celery -A worker.app worker --loglevel=info --concurrency=4
    environment:
      <<: *common-env
      AI_SERVICE_URL: http://ai:8004
    depends_on:
      redis: {condition: service_healthy}
      postgres: {condition: service_healthy}

  frontend:
    image: codeatlas/frontend:latest
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://gateway:8000/api/v1
    depends_on:
      - gateway

  gateway:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./infra/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./infra/nginx/certs:/etc/nginx/certs:ro
    depends_on:
      - auth
      - repo-service
      - ai
      - diagram
      - docs
      - security
      - search
      - frontend

  # ──────────────────────────────────────────
  # MONITORING
  # ──────────────────────────────────────────

  prometheus:
    image: prom/prometheus:latest
    profiles: ["monitoring"]
    volumes:
      - ./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    profiles: ["monitoring"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./infra/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    ports:
      - "3001:3000"

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  neo4j_data:
  minio_data:
  ollama_data:
  repo_cache:
  prometheus_data:
  grafana_data:
```

---

## Quick Start Commands

```bash
# Start core services
docker compose up -d

# Start with AI runtime (requires Ollama/GPU)
docker compose --profile ai up -d

# Start with monitoring
docker compose --profile monitoring up -d

# Start everything
docker compose --profile ai --profile monitoring up -d

# Pull Ollama model after startup
docker exec -it codeatlas-ollama ollama pull llama3.2
docker exec -it codeatlas-ollama ollama pull nomic-embed-text

# View logs
docker compose logs -f ai parser

# Scale worker instances
docker compose up -d --scale worker=4
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-in-production` | JWT signing key |
| `JWT_SECRET` | `change-me` | JWT secret |
| `LLM_PROVIDER` | `ollama` | `ollama\|openai\|anthropic` |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `GRAFANA_PASSWORD` | `admin` | Grafana admin password |
| `ENVIRONMENT` | `development` | `development\|production` |
