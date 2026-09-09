# 02 — Product Requirements

## Personas

| Persona | Role | Primary Goals |
|---------|------|---------------|
| **Developer** | IC Engineer | Understand unfamiliar code, navigate large repos, get instant answers |
| **Tech Lead** | Senior Engineer / EM | Architecture visibility, code quality, onboarding new team members |
| **Security Engineer** | AppSec / PSIRT | Find secrets, vulnerabilities, misconfigurations at scale |
| **DevOps Engineer** | Platform / SRE | Infrastructure analysis, CI/CD health, deployment config review |
| **Architect** | Principal / Staff Eng | Design integrity, dependency tracking, diagram generation |
| **Engineering Manager** | EM / Director | Health scores, productivity metrics, codebase overview |

---

## Functional Requirements

### FR-01: Repository Management
- FR-01.1: Import public Git repositories via HTTPS URL
- FR-01.2: Import private Git repositories with SSH key or PAT authentication
- FR-01.3: Import local file system paths via volume mount
- FR-01.4: Support GitHub, GitLab, Bitbucket, Azure DevOps, Gitea
- FR-01.5: Display repository metadata (size, languages, contributors, last commit)
- FR-01.6: Support repository re-indexing (full and incremental)
- FR-01.7: Track indexing status with progress indicators

### FR-02: Code Parsing & Analysis
- FR-02.1: Parse 20+ languages using Tree-sitter
- FR-02.2: Extract functions, classes, interfaces, enums, constants
- FR-02.3: Extract import/dependency relationships between files
- FR-02.4: Build call graphs (function A calls function B)
- FR-02.5: Detect tech stack (frameworks, libraries, versions)
- FR-02.6: Classify files by type (controller, model, service, test, config)

### FR-03: AI Chat
- FR-03.1: Natural language Q&A over repository content
- FR-03.2: Every answer must cite specific file paths and line numbers
- FR-03.3: Multi-turn conversation with context retention
- FR-03.4: Switch between repositories within a chat session
- FR-03.5: Support follow-up questions ("show me where this is called")
- FR-03.6: Code snippet rendering with syntax highlighting

### FR-04: Diagram Generation
- FR-04.1: System architecture diagram (services, databases, external integrations)
- FR-04.2: Module dependency diagram
- FR-04.3: Sequence/flow diagram for specific functions or endpoints
- FR-04.4: ER diagram from ORM models or SQL schema
- FR-04.5: Deployment topology diagram (Docker/K8s)
- FR-04.6: Export diagrams as PNG, SVG, and source (Mermaid/PlantUML/D2)

### FR-05: Security Scanning
- FR-05.1: Detect hardcoded secrets (API keys, passwords, tokens, private keys)
- FR-05.2: Run SAST rules (injection, XSS, SSRF, insecure deserialization)
- FR-05.3: Scan IaC files (Terraform, Helm, Dockerfile, docker-compose.yml)
- FR-05.4: Display findings with severity (Critical/High/Medium/Low/Info)
- FR-05.5: Generate AI-assisted remediation code for each finding
- FR-05.6: Export security report as PDF/JSON/SARIF

### FR-06: Documentation Generation
- FR-06.1: Generate README.md for any repository or module
- FR-06.2: Generate API reference documentation from code/OpenAPI specs
- FR-06.3: Generate deployment documentation
- FR-06.4: Generate architecture decision record (ADR) templates
- FR-06.5: Produce wiki pages exportable to Confluence/Notion format
- FR-06.6: All generated docs must be editable and versionable

### FR-07: DevOps Analysis
- FR-07.1: Analyze CI/CD pipeline files (GitHub Actions, GitLab CI, Jenkins)
- FR-07.2: Review Dockerfile best practices
- FR-07.3: Analyze Kubernetes manifests for security and efficiency
- FR-07.4: Review Terraform/Pulumi IaC for best practices
- FR-07.5: Provide optimization recommendations with explanations

### FR-08: Enterprise Features (Phase 8)
- FR-08.1: PR/MR analysis with AI review comments
- FR-08.2: Branch comparison (diff analysis with AI summary)
- FR-08.3: Repository health score (composite metric)
- FR-08.4: Multi-repository semantic search
- FR-08.5: Team-level access control (RBAC)
- FR-08.6: Audit log of all queries and AI-generated outputs

---

## Non-Functional Requirements

### NFR-01: Performance
- Initial analysis: < 5 minutes for a 50k LOC repository
- Chat response latency: < 3 seconds (local LLM), < 1.5 seconds (cloud LLM)
- Diagram generation: < 10 seconds
- Security scan: < 2 minutes for 50k LOC

### NFR-02: Scalability
- Horizontal scaling of all stateless services
- Support repositories up to 1M LOC
- Support 100+ concurrent users (enterprise tier)
- Qdrant collections scalable to 10M+ vectors

### NFR-03: Security
- All API endpoints require JWT authentication
- Role-based access control (Admin, Analyst, Viewer)
- mTLS between internal services (production)
- Secrets encrypted at rest (AES-256)
- No repository content transmitted to external services without explicit consent

### NFR-04: Reliability
- 99.5% uptime SLA (enterprise)
- Graceful degradation when LLM is unavailable (fallback to keyword search)
- All background jobs are idempotent and retryable
- Data backed up daily with point-in-time recovery

### NFR-05: Maintainability
- All services independently deployable
- OpenAPI specs auto-generated for all REST endpoints
- Test coverage ≥ 80% for critical paths
- All configuration via environment variables

### NFR-06: Observability
- Distributed tracing via OpenTelemetry
- Prometheus metrics for all services
- Structured JSON logging
- Grafana dashboards pre-built for all services

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Initial analysis time (50k LOC) | < 5 minutes |
| Chat answer relevance (human eval) | ≥ 90% |
| Language support | 20+ languages |
| Secret detection recall | 100% on benchmark dataset |
| User onboarding time (new repo) | < 10 minutes |
| Documentation generation accuracy | ≥ 85% (human eval) |
| Security finding false positive rate | < 10% |
