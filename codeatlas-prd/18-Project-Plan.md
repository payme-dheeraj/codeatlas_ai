# 18 — Project Plan

## Team Composition

| Role | Count | Responsibility |
|------|-------|----------------|
| Backend Engineer | 3 | FastAPI microservices, DB design, Celery workers |
| AI/ML Engineer | 2 | LangGraph agents, RAG pipeline, embeddings, evaluation |
| Frontend Engineer | 1 | Next.js UI, component library, real-time features |
| DevOps Engineer | 1 | Docker, Kubernetes, CI/CD, observability |
| QA Engineer | 1 | Test strategy, E2E tests, AI evaluation suites |
| **Total** | **8** | |

---

## Project Timeline

**Total Duration:** 16 weeks (8 × 2-week sprints)

```
Week:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
       ├──────────────────────────────────────────────┤
Ph1:   ████████                                        Repo import, metadata, dashboard
Ph2:         ████████                                  Parser, embeddings, graph
Ph3:                 ████████                          AI chat with citations
Ph4:                         ████████                  Diagram generation
Ph5:                                 ████████          Security scanner
Ph6:                                         ████████  Docs + DevOps analysis
       ├──────────────────────────────────────────────┤
       Alpha                    Beta             v1.0
```

---

## Milestones

| Milestone | Week | Criteria |
|-----------|------|----------|
| **M1 — Foundation** | Week 2 | Docker Compose with all infra services running; Auth + Repo Service live |
| **M2 — Alpha** | Week 4 | Repository import, parsing, embeddings; basic search working |
| **M3 — AI Chat Beta** | Week 6 | Chat with citations working on real repos; RAG quality > 80% |
| **M4 — Diagrams Beta** | Week 8 | 3+ diagram types generated from real repos |
| **M5 — Security Beta** | Week 10 | Secrets + SAST scanning with AI remediation |
| **M6 — Docs Beta** | Week 12 | README and API docs generation working |
| **M7 — v1.0 RC** | Week 14 | All Phase 1–6 features, monitoring, E2E tests passing |
| **M8 — v1.0 GA** | Week 16 | Performance validated, security hardened, docs complete |

---

## Resource Plan

### Infrastructure Costs (Development)

| Resource | Cost/mo |
|----------|---------|
| Development server (32 GB RAM, 8 core, 500 GB SSD) | ~$200 |
| CI/CD (GitHub Actions) | ~$50 |
| OpenAI API (dev testing) | ~$50 |
| Total | ~$300/mo |

### Infrastructure Costs (Production — Medium)

| Resource | Cost/mo |
|----------|---------|
| Kubernetes cluster (16 vCPU, 32 GB) | ~$400 |
| Managed PostgreSQL (RDS or Cloud SQL) | ~$150 |
| Object storage (S3/GCS — 1 TB) | ~$25 |
| LLM API costs (if using cloud) | ~$100–500 |
| Total | ~$700–1100/mo |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LLM latency too high for local models | Medium | High | Offer cloud LLM fallback; optimize context window |
| Neo4j graph becomes too large | Low | Medium | Prune old/deleted symbols; use graph projections |
| Tree-sitter grammar gaps (new languages) | Medium | Low | Fallback to regex-based extraction |
| Qdrant vector drift after incremental updates | Low | Medium | Periodic full re-index; checksum validation |
| OpenAI API cost overrun | Medium | Medium | Aggressive caching; token budgets per user |
| Security false positives annoy users | High | Medium | Configurable rule suppression; confidence thresholds |
| Slow onboarding for large repos (>500k LOC) | Medium | High | Streaming progress; background indexing; partial results |
| Breaking change in LangGraph API | Low | High | Pin to specific version; abstraction layer over LLM clients |

---

## Dependencies

```
Phase 1 (Foundation)
└── blocks Phase 2 (Parser/Embeddings)
    └── blocks Phase 3 (AI Chat)
        └── blocks Phase 4 (Diagrams) — can start in parallel after Phase 2
        └── blocks Phase 5 (Security) — can start in parallel after Phase 1
        └── blocks Phase 6 (Docs)     — depends on Phase 2 + AI Service
```

Phases 4, 5, and 6 can be developed **in parallel** after Phase 2 is complete.

---

## Definition of Done

Each feature is considered **Done** when:
1. ✅ Unit tests written and passing (coverage target met)
2. ✅ Integration test covering the happy path exists
3. ✅ OpenAPI spec updated
4. ✅ Docker image builds cleanly
5. ✅ Feature demonstrated on a real repository
6. ✅ Performance meets SLA targets from NFR section
7. ✅ No Critical/High security findings from CI scanner
8. ✅ Feature documented in the relevant PRD file
