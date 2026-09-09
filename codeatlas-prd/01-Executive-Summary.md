# 01 — Executive Summary

## What is CodeAtlas AI?

CodeAtlas AI is a self-hosted, AI-powered developer intelligence platform. It connects to any Git repository (public or private), ingests the codebase, builds a multi-modal knowledge base (vector embeddings + knowledge graph), and exposes that intelligence through a web UI, REST API, and AI chat interface.

---

## Key Capabilities

### 1. Repository Intelligence
Import any Git repository via URL or local path. The platform extracts metadata, detects tech stacks, maps file structures, and classifies components automatically.

### 2. Semantic Code Understanding
Tree-sitter parses 20+ languages into ASTs. Symbols, functions, classes, imports, and call graphs are extracted and stored in both a PostgreSQL relational store and a Neo4j knowledge graph.

### 3. AI Chat Over Code
LangGraph-orchestrated agents answer natural-language questions about the codebase with citations to exact source lines. Powered by local Ollama models or cloud LLMs.

### 4. Architecture Diagram Generation
Auto-generates Mermaid/PlantUML/D2 diagrams for: system architecture, module dependencies, call flows, database ER diagrams, and deployment topology.

### 5. Security Scanning
Detects secrets (API keys, tokens), runs SAST rules (semgrep-based), scans IaC (Terraform, Helm, Dockerfile), and generates AI-assisted remediation suggestions.

### 6. Documentation Generation
Produces README files, API reference documentation, deployment guides, and wiki pages directly from code, comments, and inferred context.

### 7. DevOps Insights
Analyzes CI/CD pipelines, Docker configurations, Kubernetes manifests, and Terraform plans for best-practice violations and optimization opportunities.

---

## Technical Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js Frontend                      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────┐
│              NGINX API Gateway + Auth Service            │
└──┬──────────┬─────────┬────────┬────────┬───────────────┘
   │          │         │        │        │
   ▼          ▼         ▼        ▼        ▼
Repo      Parser     AI Svc   Diagram   Security
Service   Service    (LLM)    Service   Scanner
   │          │         │        │        │
   └──────────┴─────────┴────────┴────────┘
                       │
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
     PostgreSQL      Qdrant         Neo4j
     (metadata)    (vectors)       (graph)
         │
    Redis + MinIO + Celery Workers
```

---

## Deployment Model

| Mode | Description |
|------|-------------|
| **Local** | `docker compose up` — all services on one machine |
| **Team** | Docker Compose on a server, shared over LAN/VPN |
| **Enterprise** | Kubernetes (Helm) with horizontal pod autoscaling |
| **Cloud-hybrid** | Local services + cloud LLM endpoints |

---

## Phased Delivery

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Repository import, metadata, dashboard | ✅ Planned |
| 2 | Tree-sitter parsing, embeddings, knowledge graph | ✅ Planned |
| 3 | AI chat with citations | ✅ Planned |
| 4 | Diagram generation | ✅ Planned |
| 5 | Security scanning | ✅ Planned |
| 6 | Documentation generation | ✅ Planned |
| 7 | DevOps analysis | ✅ Planned |
| 8 | Enterprise features, multi-repo, PR reviews | ✅ Planned |

---

## Investment Summary

- **Team**: 6–8 engineers (3 backend, 2 AI/ML, 1 frontend, 1 DevOps, 1 QA)
- **Timeline**: 8 phases × ~2 weeks = ~16 weeks to full feature parity
- **Infrastructure**: Runs on a single 32GB RAM, 8-core machine for small/medium repos
- **LLM Cost**: $0 for local Ollama; ~$0.01–0.05 per complex query with cloud LLMs
