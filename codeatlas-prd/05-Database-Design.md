# 05 — Database Design

## Storage Systems Overview

| Store | System | Purpose |
|-------|--------|---------|
| Relational | PostgreSQL 16 | Users, repositories, jobs, findings, documents |
| Vector | Qdrant 1.9 | Code chunk embeddings for semantic search |
| Graph | Neo4j 5.x | Code knowledge graph (call graphs, imports) |
| Object | MinIO | Raw files, generated artifacts, exports |
| Cache | Redis 7.2 | Sessions, job results, response cache |

---

## PostgreSQL Schema

### `users`
```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    username    TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    role        TEXT NOT NULL DEFAULT 'viewer',  -- admin, analyst, viewer
    oauth_provider TEXT,
    oauth_id    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### `repositories`
```sql
CREATE TABLE repositories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID REFERENCES users(id),
    name        TEXT NOT NULL,
    url         TEXT,
    local_path  TEXT,
    provider    TEXT,          -- github, gitlab, bitbucket, local
    default_branch TEXT DEFAULT 'main',
    description TEXT,
    tech_stack  JSONB,         -- {languages: [], frameworks: [], tools: []}
    stats       JSONB,         -- {files: 0, loc: 0, contributors: 0}
    index_status TEXT DEFAULT 'pending',  -- pending, running, complete, failed
    last_indexed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### `index_jobs`
```sql
CREATE TABLE index_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID REFERENCES repositories(id),
    job_type    TEXT NOT NULL,  -- full_index, incremental, parse_only, embed_only
    status      TEXT DEFAULT 'queued',  -- queued, running, complete, failed
    celery_task_id TEXT,
    progress    INT DEFAULT 0,  -- 0-100
    error_msg   TEXT,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### `files`
```sql
CREATE TABLE files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID REFERENCES repositories(id),
    path        TEXT NOT NULL,
    language    TEXT,
    size_bytes  INT,
    loc         INT,
    checksum    TEXT,
    minio_key   TEXT,          -- path in MinIO bucket
    parsed_at   TIMESTAMPTZ,
    UNIQUE(repo_id, path)
);
```

### `symbols`
```sql
CREATE TABLE symbols (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID REFERENCES repositories(id),
    file_id     UUID REFERENCES files(id),
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,  -- function, class, method, variable, import, export
    signature   TEXT,
    docstring   TEXT,
    start_line  INT,
    end_line    INT,
    language    TEXT,
    metadata    JSONB          -- decorators, modifiers, etc.
);
CREATE INDEX idx_symbols_repo ON symbols(repo_id);
CREATE INDEX idx_symbols_name ON symbols(name);
```

### `security_findings`
```sql
CREATE TABLE security_findings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID REFERENCES repositories(id),
    scan_id     UUID,
    file_path   TEXT NOT NULL,
    line_number INT,
    kind        TEXT NOT NULL,  -- secret, sast, iac
    rule_id     TEXT,
    title       TEXT NOT NULL,
    description TEXT,
    severity    TEXT NOT NULL,  -- critical, high, medium, low, info
    confidence  TEXT,
    snippet     TEXT,
    remediation TEXT,           -- AI-generated fix
    status      TEXT DEFAULT 'open',  -- open, fixed, suppressed
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_findings_repo ON security_findings(repo_id);
CREATE INDEX idx_findings_severity ON security_findings(severity);
```

### `documents`
```sql
CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID REFERENCES repositories(id),
    doc_type    TEXT NOT NULL,  -- readme, api_reference, deployment, adr, wiki
    title       TEXT,
    content_md  TEXT,
    minio_key   TEXT,
    version     INT DEFAULT 1,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `chat_sessions`
```sql
CREATE TABLE chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    repo_id     UUID REFERENCES repositories(id),
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID REFERENCES chat_sessions(id),
    role        TEXT NOT NULL,  -- user, assistant
    content     TEXT NOT NULL,
    citations   JSONB,          -- [{file, line_start, line_end, snippet}]
    tokens_used INT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### `diagrams`
```sql
CREATE TABLE diagrams (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID REFERENCES repositories(id),
    diagram_type TEXT NOT NULL, -- architecture, dependency, sequence, er, deployment
    title       TEXT,
    source_code TEXT,           -- Mermaid/PlantUML/D2 source
    minio_key_png TEXT,
    minio_key_svg TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Qdrant Collections

### `code_chunks`
Stores embeddings for code file chunks used in RAG retrieval.

```python
CollectionConfig(
    name="code_chunks",
    vectors_config=VectorsConfig(
        size=1536,          # text-embedding-3-small / nomic-embed-text
        distance=Distance.COSINE
    ),
    payload_schema={
        "repo_id": "keyword",
        "file_path": "keyword",
        "language": "keyword",
        "chunk_type": "keyword",   # code, docstring, comment
        "start_line": "integer",
        "end_line": "integer",
        "symbol_name": "keyword",
        "content": "text"
    }
)
```

### `doc_chunks`
Stores embeddings for generated documentation chunks.

```python
CollectionConfig(
    name="doc_chunks",
    vectors_config=VectorsConfig(
        size=1536,
        distance=Distance.COSINE
    )
)
```

---

## Neo4j Graph Model

### Node Types

| Label | Properties | Description |
|-------|-----------|-------------|
| `Repository` | id, name, url | Repository root node |
| `File` | id, path, language, loc | Source file |
| `Module` | id, name, path | Logical module/package |
| `Function` | id, name, signature, start_line, end_line | Function/method |
| `Class` | id, name, bases, start_line, end_line | Class definition |
| `Variable` | id, name, type | Module-level variable |
| `Dependency` | name, version, ecosystem | External package |

### Relationship Types

| Type | From | To | Description |
|------|------|----|-------------|
| `CONTAINS` | Repository | File | Repo contains file |
| `BELONGS_TO` | File | Module | File in module |
| `DEFINES` | File | Function/Class | File defines symbol |
| `CALLS` | Function | Function | Function calls function |
| `IMPORTS` | File/Module | File/Module | Import relationship |
| `INHERITS` | Class | Class | Class inheritance |
| `USES` | Function | Variable/Class | Function uses symbol |
| `DEPENDS_ON` | Repository | Dependency | External dependency |

### Example Cypher Queries

```cypher
-- Find all callers of a function
MATCH (caller:Function)-[:CALLS]->(target:Function {name: "process_payment"})
RETURN caller.name, caller.file_path, caller.start_line

-- Find transitive dependencies of a module
MATCH path = (m:Module {name: "auth"})-[:IMPORTS*1..5]->(dep:Module)
RETURN path

-- Find orphan functions (never called)
MATCH (f:Function)
WHERE NOT ()-[:CALLS]->(f)
AND NOT f.name STARTS WITH "test_"
RETURN f.name, f.file_path
```

---

## MinIO Bucket Structure

```
codeatlas-repos/
├── {repo_id}/
│   ├── raw/                    # Raw cloned repository files
│   │   └── {file_path}
│   ├── artifacts/              # Generated artifacts
│   │   ├── diagrams/
│   │   │   ├── architecture.png
│   │   │   └── dependencies.svg
│   │   └── docs/
│   │       ├── README.md
│   │       └── api-reference.html
│   └── reports/                # Security scan reports
│       └── security-{scan_id}.pdf
```

---

## Redis Key Patterns

| Pattern | Type | TTL | Purpose |
|---------|------|-----|---------|
| `session:{user_id}` | Hash | 24h | User session data |
| `repo:status:{repo_id}` | String | 1h | Indexing status |
| `chat:context:{session_id}` | List | 2h | Conversation history |
| `embed:cache:{content_hash}` | String | 7d | Embedding cache |
| `rate:limit:{user_id}:{endpoint}` | Counter | 1m | Rate limiting |
