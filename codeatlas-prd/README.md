# CodeAtlas AI — Product Requirements Documentation

> **An AI-powered, Docker-first platform that imports software repositories, understands code, generates architecture diagrams, detects vulnerabilities, produces documentation, and enables AI chat over your entire codebase.**

---

## Document Index

| # | Document | Description |
|---|----------|-------------|
| 00 | [Vision](./00-Vision.md) | Product vision, mission, and north-star goals |
| 01 | [Executive Summary](./01-Executive-Summary.md) | High-level overview for stakeholders |
| 02 | [Product Requirements](./02-Product-Requirements.md) | Functional & non-functional requirements, personas, success metrics |
| 03 | [System Architecture](./03-System-Architecture.md) | Overall system design, technology choices, data flow |
| 04 | [Microservices](./04-Microservices.md) | Service catalog, responsibilities, inter-service communication |
| 05 | [Database Design](./05-Database-Design.md) | PostgreSQL schema, Neo4j graph model, Qdrant collections |
| 06 | [AI Architecture](./06-AI-Architecture.md) | LLM stack, LangGraph agents, LlamaIndex pipeline |
| 07 | [RAG Pipeline](./07-RAG-Pipeline.md) | Retrieval-Augmented Generation design, chunking, embedding, retrieval |
| 08 | [Repository Parser](./08-Repository-Parser.md) | Tree-sitter parsing, language support, symbol extraction |
| 09 | [Security Scanner](./09-Security-Scanner.md) | Secrets detection, SAST, IaC scanning, AI remediation |
| 10 | [Documentation Service](./10-Documentation-Service.md) | README, API docs, wiki auto-generation |
| 11 | [Diagram Generator](./11-Diagram-Generator.md) | Architecture, ER, sequence, and deployment diagram generation |
| 12 | [Frontend Design](./12-Frontend-Design.md) | Next.js UI, component library, UX flows |
| 13 | [API Specification](./13-API-Specification.md) | REST API contracts, authentication, rate limiting |
| 14 | [Docker Deployment](./14-Docker-Deployment.md) | Docker Compose services, networking, volumes |
| 15 | [Kubernetes Deployment](./15-Kubernetes-Deployment.md) | Helm charts, manifests, scaling strategy |
| 16 | [Observability](./16-Observability.md) | Prometheus metrics, Grafana dashboards, tracing, alerting |
| 17 | [Testing](./17-Testing.md) | Unit, integration, E2E, AI evaluation strategy |
| 18 | [Project Plan](./18-Project-Plan.md) | Milestones, resource plan, risk register |
| 19 | [Sprint Backlog](./19-Sprint-Backlog.md) | Sprint-by-sprint user stories and acceptance criteria |
| 20 | [Roadmap](./20-Roadmap.md) | Phase-by-phase feature roadmap (8 phases) |

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/codeatlas-ai.git
cd codeatlas-ai

# Start all services
docker compose up -d

# Access the platform
open http://localhost:3000
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TailwindCSS, shadcn/ui |
| API Gateway | NGINX + FastAPI Gateway |
| Backend Services | FastAPI (Python 3.12) |
| AI Orchestration | LangGraph, LlamaIndex |
| Vector Database | Qdrant |
| Graph Database | Neo4j |
| Relational Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Object Storage | MinIO |
| Task Queue | Celery + Redis |
| LLM Runtime | Ollama (local) + OpenAI/Anthropic (cloud) |
| Observability | Prometheus, Grafana, OpenTelemetry |
| Container Runtime | Docker + Kubernetes |

---

*Last updated: July 2026*
