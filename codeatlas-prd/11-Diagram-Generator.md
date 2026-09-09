# 11 — Diagram Generator

## Overview

The Diagram Generator service produces architecture, dependency, sequence, ER, and deployment diagrams from the indexed knowledge graph and relational data. Diagrams are generated as source code (Mermaid, PlantUML, or D2), rendered to PNG/SVG, and stored in MinIO.

---

## Diagram Types

| Type | Source Data | Output Format |
|------|------------|---------------|
| System Architecture | Repo metadata, Docker Compose/K8s | Mermaid/C4 |
| Module Dependency | Neo4j import graph | Mermaid graph |
| Call Flow / Sequence | Neo4j call graph + AI | Mermaid sequence |
| ER Diagram | ORM models, SQL schema | Mermaid ER / PlantUML |
| Deployment Topology | Docker Compose / K8s manifests | Mermaid / D2 |
| Component Map | File classification data | Mermaid |
| Data Flow | AI inference from code | Mermaid |

---

## Generation Pipeline

```
┌──────────────────────────────────────────────────────────┐
│                  Diagram Service                          │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │            Diagram Request Handler                │    │
│  │  Input: {repo_id, diagram_type, options}          │    │
│  └─────────────────────┬────────────────────────────┘    │
│                        │                                  │
│         ┌──────────────┼───────────────────┐             │
│         │              │                   │              │
│  ┌──────▼──────┐ ┌─────▼──────┐  ┌────────▼────────┐   │
│  │  Data       │ │  Data      │  │  Data           │   │
│  │  Extractor  │ │  Extractor │  │  Extractor      │   │
│  │  (Neo4j)    │ │  (PG)      │  │  (MinIO/Files)  │   │
│  └──────┬──────┘ └─────┬──────┘  └────────┬────────┘   │
│         └──────────────┼───────────────────┘             │
│                        │                                  │
│  ┌─────────────────────▼────────────────────────────┐    │
│  │              Diagram Source Generator             │    │
│  │  (AI-assisted Mermaid/PlantUML/D2 synthesis)     │    │
│  └─────────────────────┬────────────────────────────┘    │
│                        │                                  │
│  ┌─────────────────────▼────────────────────────────┐    │
│  │              Renderer (Kroki API)                 │    │
│  │  Mermaid → PNG/SVG                                │    │
│  │  PlantUML → PNG/SVG                               │    │
│  │  D2 → PNG/SVG                                     │    │
│  └─────────────────────┬────────────────────────────┘    │
│                        │                                  │
│  ┌─────────────────────▼────────────────────────────┐    │
│  │              MinIO Storage                        │    │
│  │  repos/{repo_id}/artifacts/diagrams/              │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## Diagram 1: System Architecture

### Data Sources
- `docker-compose.yml` service definitions
- Kubernetes manifests
- Environment variables referencing external services
- AI inference for undocumented services

### Generated Mermaid (C4 Container Diagram)

```mermaid
C4Container
    title System Architecture — CodeAtlas AI

    Person(user, "Developer", "Uses web UI")

    System_Boundary(codeatlas, "CodeAtlas AI") {
        Container(frontend, "Frontend", "Next.js 14", "Web application")
        Container(gateway, "API Gateway", "NGINX", "Routing & TLS")
        Container(auth, "Auth Service", "FastAPI", "Authentication")
        Container(repo_svc, "Repo Service", "FastAPI", "Repository management")
        Container(ai_svc, "AI Service", "FastAPI + LangGraph", "LLM orchestration")
        ContainerDb(pg, "PostgreSQL", "PostgreSQL 16", "Relational data")
        ContainerDb(qdrant, "Qdrant", "Qdrant 1.9", "Vector embeddings")
        ContainerDb(neo4j, "Neo4j", "Neo4j 5", "Knowledge graph")
    }

    Rel(user, frontend, "Uses", "HTTPS")
    Rel(frontend, gateway, "API calls", "HTTPS")
    Rel(gateway, auth, "Auth check", "HTTP")
    Rel(gateway, repo_svc, "Routes", "HTTP")
    Rel(gateway, ai_svc, "Routes", "HTTP/SSE")
    Rel(repo_svc, pg, "Reads/Writes")
    Rel(ai_svc, qdrant, "Vector search")
    Rel(ai_svc, neo4j, "Graph queries")
```

---

## Diagram 2: Module Dependency

### Neo4j Query
```cypher
MATCH (f1:File)-[:IMPORTS]->(f2:File)
WHERE f1.repo_id = $repo_id
RETURN f1.path as source, f2.path as target, count(*) as weight
ORDER BY weight DESC
LIMIT 100
```

### Generated Mermaid

```mermaid
graph TD
    A[src/main.py] --> B[src/api/routes.py]
    A --> C[src/core/config.py]
    B --> D[src/services/auth.py]
    B --> E[src/services/user.py]
    D --> F[src/models/user.py]
    D --> G[src/core/security.py]
    E --> F
```

---

## Diagram 3: Sequence Diagram

### Input: Endpoint or function name
### Process: AI traces the call graph and generates sequence diagram

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI Router
    participant Auth as Auth Service
    participant DB as PostgreSQL
    participant Cache as Redis

    C->>API: POST /auth/login {username, password}
    API->>Auth: validate_credentials(username, password)
    Auth->>Cache: get(session:username)
    Cache-->>Auth: null (not cached)
    Auth->>DB: SELECT * FROM users WHERE email = ?
    DB-->>Auth: User record
    Auth->>Auth: verify_password(password, hash)
    Auth->>Cache: set(session:username, user_data, TTL=3600)
    Auth-->>API: User object
    API->>API: generate_jwt(user.id, role)
    API-->>C: {access_token, refresh_token}
```

---

## Diagram 4: ER Diagram

### Data Sources
- SQLAlchemy/Tortoise/Prisma ORM model classes
- SQL migration files
- Pydantic models with relational hints

### Generated Mermaid ER

```mermaid
erDiagram
    users {
        uuid id PK
        string email UK
        string username UK
        string role
        timestamp created_at
    }
    repositories {
        uuid id PK
        uuid owner_id FK
        string name
        string url
        jsonb tech_stack
        string index_status
    }
    chat_sessions {
        uuid id PK
        uuid user_id FK
        uuid repo_id FK
        string title
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        string role
        text content
        jsonb citations
    }

    users ||--o{ repositories : "owns"
    users ||--o{ chat_sessions : "creates"
    repositories ||--o{ chat_sessions : "associated with"
    chat_sessions ||--o{ chat_messages : "contains"
```

---

## Diagram 5: Deployment Topology

### Input: `docker-compose.yml` or Kubernetes manifests

### Generated D2

```d2
direction: right

internet -> nginx: HTTPS 443

nginx -> frontend: :3000
nginx -> gateway: :8000

gateway -> auth: :8001
gateway -> repo_service: :8002
gateway -> ai_service: :8004

repo_service -> postgres: :5432
repo_service -> redis: :6379
repo_service -> minio: :9000

ai_service -> qdrant: :6333
ai_service -> neo4j: :7687
ai_service -> ollama: :11434
```

---

## Renderer: Kroki

CodeAtlas uses [Kroki](https://kroki.io) (self-hosted) to render all diagram formats:

```python
async def render_diagram(source: str, format: str = "mermaid") -> bytes:
    response = await httpx.post(
        f"http://kroki:8000/{format}/png",
        content=source.encode(),
        headers={"Content-Type": "text/plain"}
    )
    return response.content
```

Supported via Kroki: Mermaid, PlantUML, D2, Graphviz, BPMN, C4, and more.

---

## Caching

Diagrams are cached and only regenerated when:
1. The repository is re-indexed
2. User explicitly requests regeneration
3. The source diagram data has changed (checksum comparison)
