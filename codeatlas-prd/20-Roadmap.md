# 20 — Roadmap

## Overview

CodeAtlas AI is delivered across **8 phases**, each adding a major capability layer. Phases 1–6 constitute the v1.0 release. Phases 7–8 cover post-v1.0 enterprise and advanced features.

---

## Phase Timeline

```
2026 Q3                          2026 Q4                    2027 Q1
├────────────────────────────────┼──────────────────────────┼──────────────
│  Ph1   Ph2   Ph3   Ph4         │  Ph5   Ph6   Ph7   Ph8   │
│  ████  ████  ████  ████        │  ████  ████  ████  ████  │
│                                │                          │
│    Alpha       Beta            │    v1.0     v1.1   v2.0  │
└────────────────────────────────┴──────────────────────────┴──────────────
```

---

## Phase 1: Repository Intelligence
**Duration:** Weeks 1–2 | **Target:** Alpha

### Deliverables
- [ ] Repository import via HTTPS URL (public repos)
- [ ] Repository import via SSH key (private repos)
- [ ] GitHub, GitLab, Bitbucket authentication
- [ ] Automatic metadata extraction (languages, file count, size, contributors)
- [ ] Tech stack detection (frameworks, databases, tools)
- [ ] File tree visualization in UI
- [ ] Repository dashboard with key metrics
- [ ] Indexing status with progress indicator
- [ ] Repository re-indexing (full)

### Success Criteria
- Import a 50k LOC public GitHub repo in < 2 minutes
- Accurately detect tech stack for 90%+ of popular frameworks
- All metadata displayed correctly in the UI

---

## Phase 2: Semantic Code Understanding
**Duration:** Weeks 3–4 | **Target:** Alpha+

### Deliverables
- [ ] Tree-sitter parsing for Python, TypeScript, JavaScript, Java, Go, Rust
- [ ] Symbol extraction: functions, classes, methods, imports, exports
- [ ] Call graph construction in Neo4j
- [ ] Import/dependency graph construction
- [ ] Code embeddings stored in Qdrant
- [ ] Symbol search (by name, kind, file)
- [ ] File classification (controller, service, model, test, config)
- [ ] Incremental re-indexing on file change

### Success Criteria
- Parse 10k files in < 60 seconds
- Symbol extraction accuracy > 95% on benchmark set
- Semantic search returns relevant results for 80%+ of queries

---

## Phase 3: AI Chat Over Code
**Duration:** Weeks 5–6 | **Target:** Beta

### Deliverables
- [ ] Natural language Q&A over repository content
- [ ] Streaming responses via Server-Sent Events
- [ ] Every answer cites exact file paths and line numbers
- [ ] Click-to-navigate citations in UI
- [ ] Multi-turn conversations with context retention
- [ ] Session history (save, restore, delete sessions)
- [ ] Support Ollama (local) and OpenAI/Anthropic (cloud) models
- [ ] Model switcher in settings UI
- [ ] Code snippet rendering with syntax highlighting

### Success Criteria
- RAG answer relevancy ≥ 90% (human evaluation)
- Citation accuracy ≥ 95% (correct file/line references)
- P95 response latency < 5s (local LLM), < 2s (cloud LLM)
- Hallucination rate < 5% (human evaluation)

---

## Phase 4: Diagram Generation
**Duration:** Weeks 7–8 | **Target:** Beta

### Deliverables
- [ ] System architecture diagram (C4 / Mermaid)
- [ ] Module dependency graph
- [ ] Call flow / sequence diagram for endpoints
- [ ] ER diagram from ORM models
- [ ] Deployment topology diagram (Docker Compose / K8s)
- [ ] Export as PNG, SVG, Mermaid source
- [ ] Inline diagram rendering in web UI
- [ ] Diagram regeneration on repo update
- [ ] Kroki self-hosted renderer integration

### Success Criteria
- Diagrams generated in < 10 seconds
- Architecture diagram correctly identifies 90%+ of services in Docker Compose repos
- ER diagram correctly maps 90%+ of ORM model relationships

---

## Phase 5: Security Scanning
**Duration:** Weeks 9–10 | **Target:** Beta

### Deliverables
- [ ] Secrets detection (API keys, tokens, passwords, private keys)
- [ ] SAST scanning (injection, XSS, SSRF, insecure deserialization)
- [ ] Dockerfile security analysis
- [ ] docker-compose.yml analysis
- [ ] Terraform/IaC misconfiguration detection
- [ ] Kubernetes manifest security review
- [ ] AI-generated remediation for each finding
- [ ] Severity scoring (Critical/High/Medium/Low/Info)
- [ ] SARIF export for CI/CD integration
- [ ] Finding suppression/dismissal workflow

### Success Criteria
- Zero false negatives on critical secrets benchmark dataset
- False positive rate < 10% on SAST rules
- AI remediation is actionable and correct for 80%+ of findings
- Scan completes in < 2 minutes for 50k LOC

---

## Phase 6: Documentation & DevOps Analysis
**Duration:** Weeks 11–12 | **Target:** v1.0 RC

### Deliverables
- [ ] README.md generation for any repo or module
- [ ] API reference documentation from route handlers
- [ ] Deployment guide from Docker/K8s files
- [ ] Architecture Decision Record (ADR) templates
- [ ] Document versioning and edit history
- [ ] Export to Markdown, HTML
- [ ] CI/CD pipeline analysis (GitHub Actions, GitLab CI, Jenkins)
- [ ] Dockerfile best-practice review
- [ ] Kubernetes manifest optimization recommendations
- [ ] Terraform plan analysis

### Success Criteria
- Generated README quality rated ≥ 4/5 by developers (user study)
- API docs accurate for 90%+ of detected endpoints
- DevOps recommendations are actionable and non-trivial

---

## Phase 7: Enterprise & Advanced Features
**Duration:** Weeks 13–16 | **Target:** v1.1

### Deliverables
- [ ] PR/MR analysis with AI review comments
- [ ] Branch comparison with AI diff summary
- [ ] Repository health score (composite metric: quality + security + docs coverage)
- [ ] Multi-repository semantic search
- [ ] Role-based access control (Admin / Analyst / Viewer)
- [ ] Audit log of all queries and AI outputs
- [ ] SSO integration (SAML 2.0, OIDC)
- [ ] API key management for CI/CD integrations
- [ ] Webhook support (notify on scan completion)
- [ ] Slack/Teams notification integration

---

## Phase 8: Intelligence & Ecosystem
**Duration:** 2027 Q1 | **Target:** v2.0

### Deliverables
- [ ] Architecture drift detection (compare current code vs. documented design)
- [ ] Automated onboarding guide generation per developer
- [ ] Cross-repo dependency tracking (monorepo support)
- [ ] Plugin framework for custom analyzers and diagram types
- [ ] LLM fine-tuning on organization's codebase patterns
- [ ] GitHub App / GitLab integration (native PR comments)
- [ ] VS Code and JetBrains IDE extensions
- [ ] GraphQL API support
- [ ] Self-service model hosting (bring your own LLM endpoint)
- [ ] Multi-tenant SaaS deployment option

---

## Feature Matrix by Version

| Feature | Alpha | Beta | v1.0 | v1.1 | v2.0 |
|---------|-------|------|------|------|------|
| Repository import | ✅ | ✅ | ✅ | ✅ | ✅ |
| Code parsing (10+ langs) | ✅ | ✅ | ✅ | ✅ | ✅ |
| AI Chat | — | ✅ | ✅ | ✅ | ✅ |
| Diagram generation | — | ✅ | ✅ | ✅ | ✅ |
| Security scanning | — | ✅ | ✅ | ✅ | ✅ |
| Documentation generation | — | — | ✅ | ✅ | ✅ |
| DevOps analysis | — | — | ✅ | ✅ | ✅ |
| RBAC + Audit log | — | — | — | ✅ | ✅ |
| PR/MR analysis | — | — | — | ✅ | ✅ |
| Multi-repo search | — | — | — | ✅ | ✅ |
| IDE extensions | — | — | — | — | ✅ |
| Plugin framework | — | — | — | — | ✅ |
| Architecture drift | — | — | — | — | ✅ |

---

## Versioning Policy

- **Patch** (`x.x.N`): Bug fixes, security patches — released as needed
- **Minor** (`x.N.0`): New features within a phase — released every 2 sprints
- **Major** (`N.0.0`): New phase milestone, potential breaking API changes — announced 4 weeks in advance
