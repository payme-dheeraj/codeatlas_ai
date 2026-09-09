# Workers Directory

In CodeAtlas AI, the Celery worker entry point and background indexing tasks are organized within the backend application package:

- **Celery Application Configuration**: [`backend/app/workers/celery_app.py`](../backend/app/workers/celery_app.py)
- **Repository Tasks (Clone/Fetch/Stats)**: [`backend/app/workers/tasks/repo_tasks.py`](../backend/app/workers/tasks/repo_tasks.py)
- **Parser Tasks (Tree-sitter Parsing & DB Storage)**: [`backend/app/workers/tasks/parser_tasks.py`](../backend/app/workers/tasks/parser_tasks.py)
- **Embedding Tasks (Vector Generation & Qdrant Upsert)**: [`backend/app/workers/tasks/embed_tasks.py`](../backend/app/workers/tasks/embed_tasks.py)
- **Graph Tasks (Neo4j Relationship Ingestion)**: [`backend/app/workers/tasks/graph_tasks.py`](../backend/app/workers/tasks/graph_tasks.py)
- **Summary Tasks (AI Architecture Summarization)**: [`backend/app/workers/tasks/summary_tasks.py`](../backend/app/workers/tasks/summary_tasks.py)

This directory is preserved for workspace structure consistency.
