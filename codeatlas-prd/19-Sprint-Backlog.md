# 19 — Sprint Backlog

## Sprint 1 (Week 1–2): Foundation & Infrastructure

**Goal:** All Docker services running; Auth + Repo Service operational.

### User Stories

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S1-01 | As a developer, I can run `docker compose up` and have all services start | 5 | 🔴 Must |
| S1-02 | As a user, I can register an account and receive a JWT token | 3 | 🔴 Must |
| S1-03 | As a user, I can log in with email/password | 2 | 🔴 Must |
| S1-04 | As a user, I can import a public GitHub repository by URL | 5 | 🔴 Must |
| S1-05 | As a user, I can see the list of my imported repositories | 2 | 🔴 Must |
| S1-06 | As a developer, PostgreSQL schema migrations run automatically on startup | 3 | 🔴 Must |
| S1-07 | As a user, I can see repository metadata (name, language, file count) | 2 | 🟡 Should |
| S1-08 | As a DevOps engineer, all services expose `/health` and `/metrics` | 3 | 🟡 Should |

**Acceptance Criteria (S1-04):**
- User submits a GitHub URL via POST `/repos`
- Repository is cloned into MinIO
- Basic metadata (language breakdown, file count, size) is extracted
- Status shows `complete` after successful import
- Response time for metadata extraction < 30 seconds for repos < 10k LOC

---

## Sprint 2 (Week 3–4): Parser & Knowledge Graph

**Goal:** Tree-sitter parsing, symbol extraction, Neo4j graph built for imported repos.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S2-01 | As a user, my repo is automatically parsed after import | 5 | 🔴 Must |
| S2-02 | As a user, I can browse extracted symbols (functions, classes) for my repo | 3 | 🔴 Must |
| S2-03 | As a developer, Python, TypeScript, and JavaScript are parsed correctly | 5 | 🔴 Must |
| S2-04 | As a user, I can see a file tree view of my repository | 2 | 🔴 Must |
| S2-05 | As a developer, call graph is built in Neo4j for parsed repos | 5 | 🔴 Must |
| S2-06 | As a user, I can see the tech stack detected for my repository | 2 | 🟡 Should |
| S2-07 | As a developer, code chunks are embedded and stored in Qdrant | 5 | 🔴 Must |
| S2-08 | As a user, I can search for symbols by name | 3 | 🟡 Should |
| S2-09 | As a developer, 10+ languages are supported in the parser | 5 | 🟡 Should |

---

## Sprint 3 (Week 5–6): AI Chat

**Goal:** Natural language Q&A over repo with source citations.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S3-01 | As a user, I can open a chat window for any indexed repository | 3 | 🔴 Must |
| S3-02 | As a user, I can ask a question and receive a streamed answer | 8 | 🔴 Must |
| S3-03 | As a user, every AI answer includes citations with file path and line numbers | 5 | 🔴 Must |
| S3-04 | As a user, I can click a citation and see the relevant code snippet | 3 | 🔴 Must |
| S3-05 | As a user, the chat retains conversation history within a session | 3 | 🔴 Must |
| S3-06 | As a user, I can start a new chat session | 2 | 🔴 Must |
| S3-07 | As a user, I can switch the LLM model (Ollama vs OpenAI) in settings | 3 | 🟡 Should |
| S3-08 | As a user, I can ask follow-up questions that reference earlier context | 3 | 🟡 Should |
| S3-09 | As a developer, RAG answer relevancy ≥ 85% on eval set | 5 | 🔴 Must |

---

## Sprint 4 (Week 7–8): Diagram Generation

**Goal:** Auto-generate 4 diagram types from repo data.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S4-01 | As a user, I can generate a system architecture diagram for my repo | 5 | 🔴 Must |
| S4-02 | As a user, I can generate a module dependency diagram | 5 | 🔴 Must |
| S4-03 | As a user, I can generate an ER diagram from ORM models | 5 | 🟡 Should |
| S4-04 | As a user, I can generate a sequence diagram for a specific endpoint | 5 | 🟡 Should |
| S4-05 | As a user, I can download diagrams as PNG or SVG | 2 | 🔴 Must |
| S4-06 | As a user, I can view the Mermaid source code for any diagram | 2 | 🟡 Should |
| S4-07 | As a user, diagrams render inline in the web UI | 3 | 🔴 Must |
| S4-08 | As a user, I can regenerate a diagram if the repo changes | 2 | 🟡 Should |

---

## Sprint 5 (Week 9–10): Security Scanner

**Goal:** Secrets detection, SAST, and IaC scanning with AI remediation.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S5-01 | As a security engineer, I can trigger a full security scan on any repo | 3 | 🔴 Must |
| S5-02 | As a user, hardcoded secrets (API keys, tokens, passwords) are detected | 8 | 🔴 Must |
| S5-03 | As a security engineer, SAST findings are shown with file/line references | 5 | 🔴 Must |
| S5-04 | As a user, Dockerfile and docker-compose.yml are scanned for issues | 5 | 🟡 Should |
| S5-05 | As a user, Terraform files are scanned for misconfigurations | 5 | 🟡 Should |
| S5-06 | As a user, each finding has an AI-generated remediation suggestion | 5 | 🔴 Must |
| S5-07 | As a security engineer, I can export findings as SARIF | 3 | 🟡 Should |
| S5-08 | As a user, I can suppress/dismiss a finding with a reason | 2 | 🟡 Should |
| S5-09 | As a user, findings are categorized by severity with counts | 2 | 🔴 Must |

---

## Sprint 6 (Week 11–12): Documentation Generation

**Goal:** README, API docs, and wiki generation.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S6-01 | As a user, I can generate a README.md for any repository | 5 | 🔴 Must |
| S6-02 | As a developer, API reference docs are generated from route handlers | 5 | 🔴 Must |
| S6-03 | As a user, I can view and edit generated documentation in the UI | 3 | 🔴 Must |
| S6-04 | As a user, I can download generated docs as Markdown | 2 | 🔴 Must |
| S6-05 | As a DevOps engineer, deployment guide is generated from Docker/K8s files | 5 | 🟡 Should |
| S6-06 | As a user, CI/CD pipeline files are analyzed for best practices | 5 | 🟡 Should |
| S6-07 | As a DevOps engineer, Kubernetes manifests are analyzed for security | 5 | 🟡 Should |
| S6-08 | As a user, I can regenerate a document to get an updated version | 2 | 🟡 Should |

---

## Sprint 7 (Week 13–14): Polish, Performance & Monitoring

**Goal:** Production-ready: monitoring dashboards, performance optimization, E2E tests.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S7-01 | As a DevOps engineer, Grafana dashboards are pre-built for all services | 5 | 🔴 Must |
| S7-02 | As a developer, all critical alert rules are configured in Prometheus | 3 | 🔴 Must |
| S7-03 | As a developer, E2E Playwright tests cover all critical user flows | 8 | 🔴 Must |
| S7-04 | As a user, initial analysis for a 50k LOC repo completes in < 5 minutes | 5 | 🔴 Must |
| S7-05 | As a user, the UI is fully responsive on mobile and tablet | 3 | 🟡 Should |
| S7-06 | As a developer, Kubernetes Helm chart deploys successfully | 5 | 🟡 Should |
| S7-07 | As a user, indexing progress is shown in real-time | 3 | 🔴 Must |
| S7-08 | As a DevOps engineer, distributed tracing is visible in Jaeger/Tempo | 3 | 🟡 Should |

---

## Sprint 8 (Week 15–16): Hardening & v1.0 Release

**Goal:** Security hardening, documentation, v1.0 GA release.

| ID | Story | Points | Priority |
|----|-------|--------|---------|
| S8-01 | As an admin, RBAC (Admin/Analyst/Viewer) is enforced on all endpoints | 5 | 🔴 Must |
| S8-02 | As a user, all sensitive config is in environment variables (no hardcoded secrets) | 3 | 🔴 Must |
| S8-03 | As a developer, CI pipeline runs all tests and blocks on failure | 3 | 🔴 Must |
| S8-04 | As a developer, Docker images are published to GHCR with version tags | 2 | 🔴 Must |
| S8-05 | As a user, rate limiting is enforced on all API endpoints | 3 | 🟡 Should |
| S8-06 | As a user, audit log records all AI queries and generated outputs | 3 | 🟡 Should |
| S8-07 | As a user, all PRD documentation is complete and up to date | 3 | 🔴 Must |
| S8-08 | As a developer, load tests confirm 100 concurrent users without degradation | 5 | 🔴 Must |
