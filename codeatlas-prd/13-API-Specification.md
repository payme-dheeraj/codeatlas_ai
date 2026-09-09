# 13 — API Specification

## Overview

All CodeAtlas AI services expose REST APIs with OpenAPI 3.1 specifications. Authentication uses JWT Bearer tokens. All endpoints return `application/json`. Streaming endpoints use Server-Sent Events (SSE).

**Base URL:** `https://your-instance/api/v1`

---

## Authentication

### Headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Auth Endpoints

```
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
POST /auth/api-keys          # Create API key
DELETE /auth/api-keys/{id}   # Revoke API key
```

#### POST /auth/login

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secret"
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe",
    "role": "analyst"
  }
}
```

**Response 401:**
```json
{ "detail": "Invalid credentials" }
```

---

## Repositories API

### Endpoints

```
POST   /repos                     Import repository
GET    /repos                     List repositories (paginated)
GET    /repos/{id}                Get repository details
DELETE /repos/{id}                Delete repository
POST   /repos/{id}/reindex        Trigger re-indexing
GET    /repos/{id}/status         Get indexing status
GET    /repos/{id}/files          Get file tree
GET    /repos/{id}/languages      Get language breakdown
GET    /repos/{id}/symbols        List symbols
GET    /repos/{id}/health         Get health score
```

#### POST /repos

**Request:**
```json
{
  "url": "https://github.com/org/repo",
  "name": "my-service",
  "auth_token": "ghp_...",         // optional, for private repos
  "ssh_key_id": "uuid",            // optional, for SSH auth
  "branch": "main"                 // optional, default: default branch
}
```

**Response 202:**
```json
{
  "id": "uuid",
  "name": "my-service",
  "status": "queued",
  "job_id": "uuid",
  "created_at": "2026-07-17T12:00:00Z"
}
```

#### GET /repos/{id}/status

**Response 200:**
```json
{
  "repo_id": "uuid",
  "status": "running",
  "progress": 65,
  "stage": "embedding",
  "stages_completed": ["clone", "parse", "graph"],
  "stages_remaining": ["embedding", "summary"],
  "started_at": "2026-07-17T12:00:00Z",
  "estimated_completion": "2026-07-17T12:04:00Z"
}
```

---

## AI Chat API

### Endpoints

```
POST /ai/chat                     Send message (streaming SSE)
GET  /ai/sessions                 List chat sessions
GET  /ai/sessions/{id}            Get session with messages
DELETE /ai/sessions/{id}          Delete session
POST /ai/explain                  Explain a code snippet
POST /ai/summarize                Summarize a file/module
GET  /ai/models                   List available LLM models
POST /ai/models/switch            Switch active model
```

#### POST /ai/chat

**Request:**
```json
{
  "repo_id": "uuid",
  "session_id": "uuid",            // optional, creates new if omitted
  "message": "How does the payment processing work?",
  "stream": true
}
```

**Response (streaming SSE):**
```
data: {"type":"start","session_id":"uuid","message_id":"uuid"}

data: {"type":"delta","content":"The payment processing "}

data: {"type":"delta","content":"starts in `src/services/"}

data: {"type":"delta","content":"payment.py:42`..."}

data: {"type":"citations","citations":[{"file_path":"src/services/payment.py","start_line":42,"end_line":78,"symbol_name":"process_payment","snippet":"def process_payment(order_id: str):"}]}

data: {"type":"done","tokens_used":847}
```

**Response (non-streaming, `stream: false`):**
```json
{
  "message_id": "uuid",
  "session_id": "uuid",
  "content": "The payment processing starts in `process_payment()` at [src/services/payment.py:42-78]...",
  "citations": [
    {
      "file_path": "src/services/payment.py",
      "start_line": 42,
      "end_line": 78,
      "symbol_name": "process_payment",
      "snippet": "def process_payment(order_id: str):"
    }
  ],
  "tokens_used": 847
}
```

---

## Diagrams API

### Endpoints

```
POST /diagrams/generate           Generate a diagram
GET  /diagrams/{id}               Get diagram metadata
GET  /diagrams/{id}/source        Get diagram source code
GET  /diagrams/{id}/image         Get diagram image (PNG/SVG)
GET  /diagrams/repo/{repo_id}     List all diagrams for a repo
DELETE /diagrams/{id}             Delete diagram
```

#### POST /diagrams/generate

**Request:**
```json
{
  "repo_id": "uuid",
  "diagram_type": "architecture",  // architecture|dependency|sequence|er|deployment
  "format": "mermaid",             // mermaid|plantuml|d2
  "options": {
    "max_nodes": 50,
    "focus_module": "src/auth"     // optional
  }
}
```

**Response 202:**
```json
{
  "diagram_id": "uuid",
  "status": "generating",
  "job_id": "uuid"
}
```

---

## Security API

### Endpoints

```
POST /security/scan               Trigger security scan
GET  /security/scans/{repo_id}    List scans for repo
GET  /security/scan/{id}/status   Scan job status
GET  /security/findings/{repo_id} List all findings
GET  /security/finding/{id}       Single finding detail
GET  /security/finding/{id}/remediation  AI remediation
PATCH /security/finding/{id}      Update finding status
GET  /security/report/{repo_id}   Export report
```

#### GET /security/findings/{repo_id}

**Query Parameters:**
- `severity`: `critical|high|medium|low|info`
- `kind`: `secret|sast|iac`
- `status`: `open|fixed|suppressed`
- `page`: integer (default: 1)
- `limit`: integer (default: 20, max: 100)

**Response 200:**
```json
{
  "total": 47,
  "page": 1,
  "limit": 20,
  "findings": [
    {
      "id": "uuid",
      "file_path": "src/config/settings.py",
      "line_number": 14,
      "kind": "secret",
      "rule_id": "aws-access-key",
      "title": "Hardcoded AWS Access Key",
      "severity": "critical",
      "status": "open",
      "snippet": "AWS_SECRET_KEY = \"wJalrX...\"",
      "created_at": "2026-07-17T12:00:00Z"
    }
  ]
}
```

---

## Search API

### Endpoints

```
GET /search                       Semantic search
GET /search/symbols               Symbol search
GET /search/global                Cross-repo search (Phase 8)
```

#### GET /search

**Query Parameters:**
- `q`: search query (required)
- `repo_id`: filter by repository
- `language`: filter by language
- `kind`: filter by symbol kind
- `limit`: max results (default: 10)

**Response 200:**
```json
{
  "query": "user authentication",
  "results": [
    {
      "score": 0.92,
      "file_path": "src/auth/service.py",
      "start_line": 42,
      "end_line": 78,
      "symbol_name": "authenticate_user",
      "language": "python",
      "snippet": "def authenticate_user(username: str, password: str) -> User:",
      "summary": "Validates user credentials against hashed password in PostgreSQL"
    }
  ]
}
```

---

## Error Format

All errors follow RFC 7807 Problem Details:

```json
{
  "type": "https://codeatlas.ai/errors/not-found",
  "title": "Repository Not Found",
  "status": 404,
  "detail": "Repository with id 'abc123' does not exist",
  "instance": "/api/v1/repos/abc123"
}
```

---

## Rate Limiting

| Tier | Requests/min | Chat messages/day |
|------|-------------|-------------------|
| Free | 60 | 50 |
| Team | 300 | 500 |
| Enterprise | Unlimited | Unlimited |

Rate limit headers returned on every response:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1721210460
```

---

## Pagination

All list endpoints support cursor-based pagination:

```json
{
  "data": [...],
  "pagination": {
    "total": 150,
    "page": 1,
    "limit": 20,
    "has_next": true,
    "next_cursor": "eyJpZCI6..."
  }
}
```
