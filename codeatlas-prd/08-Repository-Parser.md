# 08 — Repository Parser

## Overview

The Repository Parser Service is responsible for ingesting source code files, parsing them into Abstract Syntax Trees (ASTs) using Tree-sitter, extracting structured symbols, and populating both the relational database (PostgreSQL) and the knowledge graph (Neo4j).

---

## Supported Languages

| Language | Tree-sitter Grammar | File Extensions |
|----------|-------------------|----------------|
| Python | `tree-sitter-python` | `.py`, `.pyw` |
| TypeScript | `tree-sitter-typescript` | `.ts`, `.tsx` |
| JavaScript | `tree-sitter-javascript` | `.js`, `.jsx`, `.mjs` |
| Java | `tree-sitter-java` | `.java` |
| Kotlin | `tree-sitter-kotlin` | `.kt`, `.kts` |
| Go | `tree-sitter-go` | `.go` |
| Rust | `tree-sitter-rust` | `.rs` |
| C | `tree-sitter-c` | `.c`, `.h` |
| C++ | `tree-sitter-cpp` | `.cpp`, `.cc`, `.cxx`, `.hpp` |
| C# | `tree-sitter-c-sharp` | `.cs` |
| Ruby | `tree-sitter-ruby` | `.rb` |
| PHP | `tree-sitter-php` | `.php` |
| Swift | `tree-sitter-swift` | `.swift` |
| Scala | `tree-sitter-scala` | `.scala` |
| R | `tree-sitter-r` | `.r`, `.R` |
| Bash | `tree-sitter-bash` | `.sh`, `.bash` |
| SQL | `tree-sitter-sql` | `.sql` |
| HCL/Terraform | `tree-sitter-hcl` | `.tf`, `.tfvars` |
| YAML | `tree-sitter-yaml` | `.yaml`, `.yml` |
| Dockerfile | `tree-sitter-dockerfile` | `Dockerfile` |
| Markdown | `tree-sitter-markdown` | `.md` |
| JSON | `tree-sitter-json` | `.json` |

---

## Parser Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Parser Service                          │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Celery Worker (parse_repo task)        │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                                │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │              File Dispatcher                        │  │
│  │  - Detect language from extension/content          │  │
│  │  - Filter: exclude node_modules, .git, build/dist  │  │
│  │  - Prioritize: source files > config > docs         │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                                │
│           ┌─────────────┼──────────────┐                │
│           │             │              │                  │
│  ┌────────▼───┐  ┌──────▼─────┐  ┌───▼──────────┐     │
│  │  Language  │  │  Language  │  │   Language   │     │
│  │  Parser A  │  │  Parser B  │  │   Parser N   │     │
│  │ (Python)   │  │   (TS/JS)  │  │   (Go/Rust)  │     │
│  └────────┬───┘  └──────┬─────┘  └───┬──────────┘     │
│           └─────────────┼─────────────┘                  │
│                         │                                │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │            Symbol Normalizer                        │  │
│  │  - Normalize symbol kinds across languages         │  │
│  │  - Extract docstrings, decorators, modifiers       │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                                │
│           ┌─────────────┼──────────────┐                │
│           │                            │                  │
│  ┌────────▼───────┐          ┌─────────▼──────────┐     │
│  │  PostgreSQL    │          │   Neo4j             │     │
│  │  Persister     │          │   Graph Builder     │     │
│  │  (symbols,     │          │   (nodes, rels)     │     │
│  │   files)       │          │                     │     │
│  └────────────────┘          └─────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

---

## Symbol Extraction

### Extracted Symbol Types

| Symbol Kind | Description | Languages |
|------------|-------------|-----------|
| `function` | Top-level function | All |
| `method` | Class/struct method | All OOP languages |
| `class` | Class definition | Python, TS, Java, etc. |
| `interface` | Interface definition | TS, Java, Go, C# |
| `enum` | Enumeration | Most languages |
| `constant` | Module-level constant | All |
| `import` | Import/require statement | All |
| `export` | Export statement | JS/TS |
| `decorator` | Decorator/annotation | Python, Java, TS |
| `route` | HTTP route handler | Python (FastAPI/Flask), JS (Express) |
| `model` | ORM model class | Python (SQLAlchemy), JS (Prisma) |

### Python Example

```python
# Input source
class UserService:
    """Handles user-related business logic."""

    def authenticate(self, username: str, password: str) -> User:
        """Validate credentials and return user."""
        ...

# Extracted symbols:
[
  {
    "name": "UserService",
    "kind": "class",
    "start_line": 1, "end_line": 10,
    "docstring": "Handles user-related business logic."
  },
  {
    "name": "authenticate",
    "kind": "method",
    "parent_class": "UserService",
    "signature": "(self, username: str, password: str) -> User",
    "start_line": 4, "end_line": 7,
    "docstring": "Validate credentials and return user.",
    "parameters": [
      {"name": "username", "type": "str"},
      {"name": "password", "type": "str"}
    ],
    "return_type": "User"
  }
]
```

---

## Tech Stack Detection

The parser identifies the technology stack from:

```python
TECH_PATTERNS = {
    "frameworks": {
        "fastapi": ["requirements.txt:fastapi", "*.py:from fastapi"],
        "django": ["requirements.txt:django", "*.py:from django"],
        "nextjs": ["package.json:next", "next.config.*"],
        "react": ["package.json:react"],
        "express": ["package.json:express"],
        "spring": ["pom.xml:spring-boot"],
        "rails": ["Gemfile:rails"],
    },
    "databases": {
        "postgresql": ["requirements.txt:psycopg", "package.json:pg"],
        "mongodb": ["requirements.txt:pymongo", "package.json:mongoose"],
        "redis": ["requirements.txt:redis", "package.json:ioredis"],
    },
    "infrastructure": {
        "docker": ["Dockerfile", "docker-compose.yml"],
        "kubernetes": ["*.yaml:kind: Deployment"],
        "terraform": ["*.tf"],
        "helm": ["Chart.yaml"],
    }
}
```

---

## File Classification

Each file is classified into a category for better organization:

| Category | Detection Rules |
|----------|----------------|
| `controller` | Route decorators, HTTP method handlers |
| `service` | Class with `Service` suffix, business logic |
| `model` | ORM base classes, `Model` suffix |
| `repository` | DB query methods, `Repository`/`DAO` suffix |
| `util` / `helper` | `utils.py`, `helpers.py`, pure functions |
| `config` | `config.py`, `settings.py`, `.env.example` |
| `test` | `test_*.py`, `*.spec.ts`, `__tests__/` |
| `schema` | Pydantic models, GraphQL schemas, OpenAPI |
| `migration` | Alembic migrations, Flyway scripts |
| `script` | Standalone CLI scripts |

---

## Parser Output: Knowledge Graph

Every parsed repository produces the following Neo4j graph:

```
(Repository)-[:CONTAINS]->(File)-[:DEFINES]->(Function)
(File)-[:BELONGS_TO]->(Module)
(Function)-[:CALLS]->(Function)
(File)-[:IMPORTS]->(File)
(Class)-[:INHERITS]->(Class)
(Function)-[:USES]->(Class)
(Repository)-[:DEPENDS_ON]->(Dependency)
```

### Graph Statistics per Repository
- Average nodes: ~5,000–50,000 for medium repositories
- Average relationships: ~10,000–100,000 for medium repositories
- Build time: 30–120 seconds for 50k LOC

---

## Excluded Paths

The parser automatically excludes:

```python
EXCLUDED_PATTERNS = [
    "node_modules/", ".git/", "__pycache__/",
    "dist/", "build/", ".next/", "target/",
    "vendor/", ".venv/", "venv/", "env/",
    "*.min.js", "*.bundle.js", "*.lock",
    "*.pyc", "*.class", "*.jar",
    "coverage/", ".pytest_cache/",
]
```

---

## Performance

| Repository Size | Files | Parse Time | Graph Build |
|----------------|-------|-----------|-------------|
| Small (< 10k LOC) | < 100 | < 10s | < 5s |
| Medium (50k LOC) | ~500 | < 60s | < 30s |
| Large (200k LOC) | ~2000 | < 5min | < 2min |
| XL (1M LOC) | ~10000 | < 30min | < 15min |

Parallelism: Each file is parsed concurrently via asyncio; Neo4j writes are batched.
