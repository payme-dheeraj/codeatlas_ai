# 03 — System Architecture

## Overview

CodeAtlas AI follows a **microservices architecture** with an event-driven backbone. All services communicate via REST (synchronous) and a Redis-backed Celery task queue (asynchronous). The system is designed to be fully self-contained via Docker Compose, with Kubernetes manifests provided for production scale-out.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                               │
│  ┌─────────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │  Next.js Web UI │    │  REST Client │    │  CLI / SDK     │  │
│  └────────┬────────┘    └──────┬───────┘    └───────┬────────┘  │
└───────────┼─────────────────────┼────────────────────┼──────────┘
            │                     │                    │
            ▼                     ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                    GATEWAY & AUTH LAYER                           │
│  ┌──────────────────┐        ┌─────────────────────────────┐    │
│  │   NGINX Reverse  │        │   Auth Service (JWT/OAuth2)  │    │
│  │   Proxy (TLS)    │───────▶│   + RBAC Middleware          │    │
│  └──────────────────┘        └─────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ Internal HTTP (service mesh)
┌────────────────────────────────▼─────────────────────────────────┐
│                      MICROSERVICES LAYER                          │
│                                                                   │
│  ┌───────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
│  │   Repo    │  │  Parser   │  │    AI    │  │   Diagram    │  │
│  │  Service  │  │  Service  │  │  Service │  │   Service    │  │
│  └─────┬─────┘  └─────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│        │              │              │                │           │
│  ┌─────┴──────────────┴──────────────┴────────────────┴───────┐  │
│  │              Celery Task Queue (Redis broker)               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────┐  ┌───────────┐  ┌──────────────────────────────┐ │
│  │ Security  │  │   Docs    │  │       Search Service          │ │
│  │ Scanner   │  │  Service  │  │   (hybrid: vector + graph)    │ │
│  └───────────┘  └───────────┘  └──────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                       DATA LAYER                                  │
│                                                                   │
│  ┌──────────────┐  ┌──────────┐  ┌────────┐  ┌──────────────┐  │
│  │  PostgreSQL  │  │  Qdrant  │  │ Neo4j  │  │    MinIO     │  │
│  │  (metadata,  │  │ (vector  │  │(graph  │  │  (raw files, │  │
│  │   users,     │  │ search)  │  │  DB)   │  │  artifacts)  │  │
│  │   results)   │  └──────────┘  └────────┘  └──────────────┘  │
│  └──────────────┘                                                 │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │         Redis (cache, session, Celery broker/backend)       │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                    LLM / AI LAYER                                 │
│                                                                   │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────┐ │
│  │    Ollama    │  │  OpenAI API    │  │  Anthropic Claude    │ │
│  │  (local LLM) │  │  (cloud LLM)   │  │    (cloud LLM)       │ │
│  └──────────────┘  └────────────────┘  └──────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Frontend | Next.js | 14.x | Web UI, SSR, API routes |
| Styling | TailwindCSS + shadcn/ui | latest | Design system |
| API Gateway | NGINX | 1.25 | Reverse proxy, TLS termination |
| Auth | FastAPI + PyJWT | — | JWT auth, OAuth2, RBAC |
| Repo Service | FastAPI | 0.111 | Repository management |
| Parser Service | FastAPI | 0.111 | Code parsing, AST extraction |
| AI Service | FastAPI + LangGraph | 0.1.x | LLM orchestration, RAG |
| Diagram Service | FastAPI | 0.111 | Diagram generation |
| Security Service | FastAPI | 0.111 | Security scanning |
| Docs Service | FastAPI | 0.111 | Documentation generation |
| Search Service | FastAPI | 0.111 | Hybrid search |
| Task Queue | Celery + Redis | 5.3 | Async job processing |
| Relational DB | PostgreSQL | 16 | Metadata, users, results |
| Vector DB | Qdrant | 1.9 | Embedding storage & retrieval |
| Graph DB | Neo4j | 5.x | Code knowledge graph |
| Object Store | MinIO | latest | File storage |
| Cache | Redis | 7.2 | Caching, sessions, queues |
| Local LLM | Ollama | 0.1.x | Self-hosted LLM runtime |
| Tracing | OpenTelemetry | — | Distributed tracing |
| Metrics | Prometheus + Grafana | — | Observability |

---

## Data Flow: Repository Ingestion

```
1. User submits repo URL via UI
       │
2. Repo Service: clone/fetch → store raw files in MinIO
       │
3. Repo Service: publish task → Celery queue (parse_repo)
       │
4. Parser Service worker:
   ├── Tree-sitter: parse files → extract symbols
   ├── Store symbols in PostgreSQL
   ├── Build call graph → store in Neo4j
   └── Generate embeddings → store in Qdrant
       │
5. AI Service: post-process → generate summaries per module
       │
6. Status updated in PostgreSQL → frontend notified via polling/WebSocket
```

## Data Flow: AI Chat Query

```
1. User sends question via chat UI
       │
2. AI Service receives query
       │
3. Query expansion + embedding generation
       │
4. Hybrid retrieval:
   ├── Qdrant: top-k semantic chunk retrieval
   └── Neo4j: graph context (callers, dependencies)
       │
5. LangGraph agent: rerank → select relevant context → build prompt
       │
6. LLM (Ollama/OpenAI): generate answer with citations
       │
7. Response streamed back to UI with source references
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sync vs Async processing | Async via Celery | Repo ingestion is long-running; must not block HTTP |
| Graph DB | Neo4j | Native graph traversal for call graphs, import chains |
| Vector DB | Qdrant | Production-grade, self-hosted, supports hybrid search |
| LLM runtime | Ollama | Privacy-first; cloud LLMs as fallback |
| API style | REST + OpenAPI | Broad tooling support, easy to generate SDKs |
| Frontend framework | Next.js 14 | App Router, SSR, edge functions |
| Container orchestration | Docker Compose + K8s | Simple local dev, production-scale K8s |
