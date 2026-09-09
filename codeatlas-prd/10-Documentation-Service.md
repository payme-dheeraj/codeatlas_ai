# 10 — Documentation Service

## Overview

The Documentation Service auto-generates living documentation from the indexed codebase. It leverages the AI Service and parsed symbols to produce README files, API references, deployment guides, Architecture Decision Records, and wiki pages — all traceable to source code.

---

## Document Types

| Type | Description | Output Format |
|------|-------------|--------------|
| `readme` | Repository/module README | Markdown |
| `api_reference` | REST/GraphQL API documentation | Markdown, HTML |
| `deployment_guide` | Docker/K8s deployment instructions | Markdown |
| `adr` | Architecture Decision Record templates | Markdown |
| `wiki` | Comprehensive module/service wiki | Markdown, HTML, Confluence XML |
| `changelog` | AI-generated changelog from git history | Markdown |
| `onboarding` | New developer onboarding guide | Markdown |

---

## README Generator

### Input Sources
- Repository metadata (languages, frameworks, detected tools)
- Top-level file structure
- Existing partial README (if any)
- Package manager files (`package.json`, `pyproject.toml`, `Cargo.toml`)
- AI-generated module summaries
- Docker Compose / Kubernetes manifests

### Generated README Structure

```markdown
# {Repository Name}

> {One-line AI-generated description}

## Features
{AI-inferred feature list from code}

## Tech Stack
{Detected frameworks and libraries with badges}

## Getting Started

### Prerequisites
{Detected runtime/tooling requirements}

### Installation
{Steps inferred from package manager + Docker files}

### Running Locally
{Docker Compose or direct commands}

## Project Structure
{File tree with AI-generated descriptions}

## API Reference
{Link to generated API docs}

## Configuration
{Environment variables from .env.example or config files}

## Contributing
{Standard contributing guidelines}

## License
{Detected from LICENSE file}
```

---

## API Reference Generator

### Input Sources
- OpenAPI/Swagger specs (if present)
- FastAPI/Flask/Express route handlers (parsed by Parser Service)
- Pydantic models / TypeScript interfaces
- Docstrings and JSDoc comments

### Generation Strategy

```python
async def generate_api_reference(repo_id: str) -> str:
    # 1. Check for existing OpenAPI spec
    openapi_spec = await find_openapi_spec(repo_id)

    if openapi_spec:
        # Convert existing spec to docs
        return await render_openapi_to_markdown(openapi_spec)
    else:
        # Extract routes from parsed symbols
        routes = await get_route_symbols(repo_id)
        # Generate documentation from code + docstrings
        return await ai_generate_api_docs(routes)
```

### Generated API Doc Example

```markdown
## POST /auth/login

Authenticate a user and return JWT tokens.

**Request Body**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| username | string | ✅ | User's email or username |
| password | string | ✅ | User's password |

**Response 200**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 3600
}
```

**Response 401**
```json
{ "detail": "Invalid credentials" }
```

*Source: `src/api/routes/auth.py:15-42`*
```

---

## Deployment Guide Generator

### Detects and Documents
- Docker Compose services and their environment variables
- Kubernetes resource requirements and scaling configuration
- Required secrets and how to create them
- Network ports and ingress configuration
- Health check endpoints
- Backup and restore procedures

### Generated Structure

```markdown
# Deployment Guide — {Service Name}

## Prerequisites
## Environment Variables
## Docker Compose Deployment
## Kubernetes Deployment
## Health Checks
## Scaling
## Backup & Restore
## Troubleshooting
```

---

## Architecture Decision Record (ADR) Generator

ADRs are created from:
- Major technology choices detected in the codebase
- AI inference of the "why" from code comments and commit messages

### ADR Template

```markdown
# ADR-{number}: {Title}

**Date:** {date}
**Status:** {proposed | accepted | deprecated | superseded}

## Context
{AI-inferred context and problem being solved}

## Decision
{What was decided and implemented}

## Consequences
### Positive
- ...

### Negative
- ...

## Alternatives Considered
- ...

*Source files: {relevant file citations}*
```

---

## Wiki Generator

Generates a comprehensive developer wiki covering:

| Section | Content |
|---------|---------|
| Overview | Repository summary, purpose, team |
| Architecture | System design (links to diagrams) |
| Modules | Per-module deep-dive with AI summaries |
| Data Models | Entities and their relationships |
| API Reference | All endpoints |
| Configuration | All config options |
| Development | Setup, testing, debugging |
| Deployment | All deployment modes |
| Security | Security posture, known issues |
| Runbooks | Common operational procedures |

---

## Export Formats

### Confluence Export

```python
def to_confluence_xml(markdown_content: str) -> str:
    """Convert markdown to Confluence Storage Format XML."""
    ...
```

### Notion Export

```python
def to_notion_blocks(markdown_content: str) -> List[dict]:
    """Convert markdown to Notion block API format."""
    ...
```

---

## Versioning

Every generated document is versioned:

```sql
-- documents table includes version tracking
INSERT INTO documents (repo_id, doc_type, title, content_md, version)
VALUES ($1, 'readme', 'README.md', $content, 
        (SELECT COALESCE(MAX(version), 0) + 1 
         FROM documents WHERE repo_id = $1 AND doc_type = 'readme'));
```

Users can compare versions and restore previous generations.

---

## Regeneration Triggers

| Trigger | Action |
|---------|--------|
| Repository re-indexed | Regenerate all docs |
| Specific file changed | Regenerate affected module docs |
| Manual request via UI | Regenerate selected document |
| Scheduled (weekly) | Refresh README and wiki |
