# 04 — Microservices

## Service Catalog

| Service | Container Name | Port | Responsibility |
|---------|---------------|------|----------------|
| Frontend | `frontend` | 3000 | Next.js web application |
| Gateway | `gateway` | 8000 | NGINX reverse proxy + routing |
| Auth Service | `auth` | 8001 | JWT issuance, OAuth2, RBAC |
| Repo Service | `repo-service` | 8002 | Repository CRUD, cloning, metadata |
| Parser Service | `parser` | 8003 | Tree-sitter parsing, symbol extraction |
| AI Service | `ai` | 8004 | LLM orchestration, RAG, chat |
| Diagram Service | `diagram` | 8005 | Diagram generation and export |
| Docs Service | `docs` | 8006 | Documentation generation |
| Security Service | `security` | 8007 | Security scanning (SAST, secrets, IaC) |
| Search Service | `search` | 8008 | Hybrid vector + graph search |
| Worker | `worker` | — | Celery background task worker |

---

## Service Descriptions

### Auth Service (`auth` — port 8001)

**Responsibilities:**
- User registration, login, logout
- JWT access token + refresh token issuance
- OAuth2 integration (GitHub, GitLab, Google)
- Role-Based Access Control (Admin, Analyst, Viewer)
- API key management for programmatic access

**Key Endpoints:**
```
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
POST /auth/api-keys
```

**Dependencies:** PostgreSQL, Redis (session cache)

---

### Repo Service (`repo-service` — port 8002)

**Responsibilities:**
- Accept repository import requests (URL, SSH, local path)
- Clone/fetch repositories using GitPython
- Store raw files in MinIO
- Extract and persist repository metadata (languages, file tree, contributors)
- Trigger parsing jobs via Celery
- Expose repository CRUD and status APIs

**Key Endpoints:**
```
POST   /repos                    # Import repository
GET    /repos                    # List repositories
GET    /repos/{id}               # Repository details
DELETE /repos/{id}               # Remove repository
POST   /repos/{id}/reindex       # Trigger re-indexing
GET    /repos/{id}/status        # Indexing status
GET    /repos/{id}/files         # File tree
GET    /repos/{id}/languages     # Language breakdown
```

**Dependencies:** PostgreSQL, MinIO, Redis (Celery), Parser Service

---

### Parser Service (`parser` — port 8003)

**Responsibilities:**
- Consume parse tasks from Celery queue
- Parse files using Tree-sitter (20+ languages)
- Extract: functions, classes, methods, imports, exports, decorators
- Build call graphs and import graphs
- Persist parsed symbols to PostgreSQL
- Build knowledge graph in Neo4j (nodes: File, Function, Class, Module)
- Generate embeddings for code chunks via AI Service
- Store embeddings in Qdrant

**Key Endpoints:**
```
POST /parse/file                 # Parse a single file
POST /parse/repo                 # Parse entire repository
GET  /parse/status/{job_id}      # Job status
GET  /parse/symbols/{repo_id}    # List symbols
GET  /parse/graph/{repo_id}      # Graph statistics
```

**Dependencies:** PostgreSQL, Qdrant, Neo4j, MinIO, AI Service (for embeddings)

---

### AI Service (`ai` — port 8004)

**Responsibilities:**
- Manage LLM provider configuration (Ollama, OpenAI, Anthropic)
- Generate text embeddings (sentence-transformers / OpenAI)
- Orchestrate LangGraph agents for chat, summarization, and generation tasks
- Implement RAG pipeline (retrieve → augment → generate)
- Manage conversation history and context windows
- Stream LLM responses via Server-Sent Events (SSE)

**Key Endpoints:**
```
POST /ai/chat                    # Send chat message (streaming)
POST /ai/embed                   # Generate embeddings
POST /ai/summarize               # Summarize code/file/module
POST /ai/explain                 # Explain a code snippet
GET  /ai/models                  # List available LLM models
POST /ai/models/switch           # Switch active model
```

**Dependencies:** Qdrant, Neo4j, Redis (conversation cache), Ollama/OpenAI/Anthropic

---

### Diagram Service (`diagram` — port 8005)

**Responsibilities:**
- Query Neo4j and PostgreSQL for structural data
- Generate Mermaid, PlantUML, and D2 diagram source code
- Render diagrams to PNG/SVG using Kroki or local renderer
- Store generated diagrams in MinIO
- Support diagram types: architecture, dependency, sequence, ER, deployment

**Key Endpoints:**
```
POST /diagrams/architecture      # System architecture diagram
POST /diagrams/dependencies      # Module dependency diagram
POST /diagrams/sequence          # Sequence diagram for an endpoint
POST /diagrams/er                # Entity-relationship diagram
POST /diagrams/deployment        # Deployment topology
GET  /diagrams/{id}              # Retrieve diagram
GET  /diagrams/{id}/source       # Get diagram source code
```

**Dependencies:** PostgreSQL, Neo4j, MinIO, AI Service

---

### Docs Service (`docs` — port 8006)

**Responsibilities:**
- Generate README.md for repositories and modules
- Generate API reference from OpenAPI specs or code docstrings
- Generate deployment guides
- Generate Architecture Decision Records (ADR)
- Export to Markdown, HTML, Confluence format

**Key Endpoints:**
```
POST /docs/readme                # Generate README
POST /docs/api-reference         # Generate API docs
POST /docs/deployment-guide      # Generate deployment guide
POST /docs/adr                   # Generate ADR template
GET  /docs/{repo_id}             # List all generated docs
GET  /docs/{doc_id}/export       # Export document
```

**Dependencies:** PostgreSQL, MinIO, AI Service

---

### Security Service (`security` — port 8007)

**Responsibilities:**
- Detect hardcoded secrets using pattern matching + ML (detect-secrets, truffleHog rules)
- Run SAST analysis using semgrep rules
- Scan IaC files (Terraform, Helm, Dockerfile, docker-compose)
- Generate AI-assisted remediation for each finding
- Persist findings to PostgreSQL
- Export reports in JSON, SARIF, PDF

**Key Endpoints:**
```
POST /security/scan              # Trigger full security scan
POST /security/scan/secrets      # Secrets-only scan
POST /security/scan/sast         # SAST-only scan
POST /security/scan/iac          # IaC-only scan
GET  /security/findings/{repo_id} # List findings
GET  /security/findings/{id}/remediation # AI remediation
GET  /security/report/{repo_id}  # Export full report
```

**Dependencies:** PostgreSQL, MinIO, AI Service

---

### Search Service (`search` — port 8008)

**Responsibilities:**
- Hybrid search: combine Qdrant vector search + Neo4j graph traversal + PostgreSQL full-text
- Symbol search (find all usages of a function/class)
- Cross-repository semantic search (Phase 8)
- Provide ranked, deduplicated results with source citations

**Key Endpoints:**
```
GET /search?q={query}&repo={id}  # Semantic search
GET /search/symbol?name={name}   # Symbol search
GET /search/global?q={query}     # Cross-repo search
```

**Dependencies:** Qdrant, Neo4j, PostgreSQL

---

## Inter-Service Communication

```
                    ┌─────────────────────────────────┐
                    │         Redis Pub/Sub             │
                    │    (event notifications)          │
                    └──────────────┬──────────────────┘
                                   │
┌──────────┐  REST   ┌────────────▼──────────┐  REST  ┌───────────┐
│  Repo    │────────▶│   Celery Task Queue   │───────▶│  Parser   │
│ Service  │         │   (Redis broker)      │        │  Service  │
└──────────┘         └───────────────────────┘        └───────────┘
                              │                              │
                         Celery tasks               REST to AI Svc
                              │                              │
                    ┌─────────▼────────┐           ┌────────▼──────┐
                    │  Worker Process  │           │  AI Service   │
                    │  (parser tasks,  │           │  (embeddings) │
                    │  scan tasks)     │           └───────────────┘
                    └──────────────────┘
```

**Communication Patterns:**
- **Sync REST**: Auth, low-latency queries (search, diagram retrieval)
- **Async Celery**: Repo ingestion, full parse, security scan, diagram generation
- **SSE Streaming**: AI chat responses
- **Polling**: Indexing status (frontend polls `/repos/{id}/status`)
