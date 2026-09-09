# 07 — RAG Pipeline

## Overview

The RAG (Retrieval-Augmented Generation) pipeline in CodeAtlas AI is purpose-built for source code. It uses hierarchical chunking at semantic boundaries (functions, classes), multi-source retrieval (vector + graph + keyword), cross-encoder reranking, and citation extraction to produce accurate, traceable answers.

---

## Pipeline Stages

```
┌──────────────────────────────────────────────────────────────────┐
│                     INDEXING PIPELINE                             │
│                                                                   │
│  Raw Files (MinIO)                                                │
│       │                                                           │
│       ▼                                                           │
│  ┌──────────────┐                                                │
│  │ File Chunker │  Tree-sitter semantic boundaries               │
│  └──────┬───────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────┐                                                │
│  │  Embedding   │  nomic-embed-text / text-embedding-3-small     │
│  │  Generator   │                                                │
│  └──────┬───────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────┐                                                │
│  │   Qdrant     │  Store vectors + metadata payload              │
│  │   Upsert     │                                                │
│  └──────────────┘                                                │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     RETRIEVAL PIPELINE                            │
│                                                                   │
│  User Query                                                       │
│       │                                                           │
│       ▼                                                           │
│  ┌──────────────┐                                                │
│  │Query Embedder│  Embed query with same model as index          │
│  └──────┬───────┘                                                │
│         │                                                         │
│    ┌────▼──────────────────────────────────────┐                │
│    │               Multi-Source Retrieval        │                │
│    │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │                │
│    │  │  Qdrant  │  │  Neo4j  │  │  PG FTS  │ │                │
│    │  │ (top-20) │  │ (graph) │  │(keyword) │ │                │
│    │  └──────────┘  └──────────┘  └──────────┘ │                │
│    └────────────────────┬──────────────────────┘                │
│                         │                                         │
│  ┌──────────────────────▼──────────────────┐                    │
│  │         Merge & Deduplicate              │                    │
│  └──────────────────────┬──────────────────┘                    │
│                         │                                         │
│  ┌──────────────────────▼──────────────────┐                    │
│  │         Cross-Encoder Reranker           │  top-10 kept       │
│  └──────────────────────┬──────────────────┘                    │
│                         │                                         │
│  ┌──────────────────────▼──────────────────┐                    │
│  │         Context Window Builder           │  max 6k tokens     │
│  └──────────────────────┬──────────────────┘                    │
│                         │                                         │
│  ┌──────────────────────▼──────────────────┐                    │
│  │           LLM Generation                 │  streaming         │
│  └──────────────────────┬──────────────────┘                    │
│                         │                                         │
│  ┌──────────────────────▼──────────────────┐                    │
│  │         Citation Extractor               │                    │
│  └──────────────────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Chunking Strategy

### Priority Order
1. **Function-level chunks** — preferred; preserves complete function context
2. **Class-level chunks** — for small classes (< 100 lines)
3. **Fixed-size chunks with overlap** — fallback for large files without clear boundaries

### Chunk Metadata
Each chunk stored in Qdrant carries:
```json
{
  "id": "uuid",
  "repo_id": "uuid",
  "file_path": "src/services/auth.py",
  "language": "python",
  "chunk_type": "function",
  "symbol_name": "authenticate_user",
  "start_line": 42,
  "end_line": 78,
  "content": "def authenticate_user(username: str, password: str) -> User:\n    ...",
  "summary": "Validates user credentials and returns a User object or raises AuthError"
}
```

### Chunk Size Guidelines

| Language | Target Chunk Size | Strategy |
|----------|-----------------|---------|
| Python | 100–300 lines | Function/method boundaries |
| TypeScript/JS | 50–200 lines | Function/class boundaries |
| Java/Kotlin | 50–200 lines | Method boundaries |
| Go | 50–150 lines | Function boundaries |
| Rust | 50–200 lines | Function/impl boundaries |
| SQL | 20–100 lines | Statement level |
| Markdown/Docs | 200–500 tokens | Paragraph level |

---

## Retrieval Details

### Vector Retrieval (Qdrant)

```python
search_params = SearchParams(hnsw_ef=128, exact=False)

results = qdrant_client.search(
    collection_name="code_chunks",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
    ),
    limit=20,
    with_payload=True,
    score_threshold=0.65,   # minimum cosine similarity
    search_params=search_params
)
```

### Graph Context Retrieval (Neo4j)

For each symbol found in vector results, expand with Neo4j:

```cypher
-- Get function with its callers and callees
MATCH (f:Function {name: $func_name, repo_id: $repo_id})
OPTIONAL MATCH (caller:Function)-[:CALLS]->(f)
OPTIONAL MATCH (f)-[:CALLS]->(callee:Function)
RETURN f, collect(caller) as callers, collect(callee) as callees
LIMIT 10
```

### Keyword Fallback (PostgreSQL FTS)

```sql
SELECT s.*, f.path as file_path
FROM symbols s
JOIN files f ON s.file_id = f.id
WHERE s.repo_id = $1
AND to_tsvector('english', s.name || ' ' || COALESCE(s.docstring, ''))
    @@ plainto_tsquery('english', $2)
ORDER BY ts_rank(
    to_tsvector('english', s.name || ' ' || COALESCE(s.docstring, '')),
    plainto_tsquery('english', $2)
) DESC
LIMIT 10;
```

---

## Context Window Assembly

```python
def build_context(chunks: List[Chunk], max_tokens: int = 6000) -> str:
    context_parts = []
    token_count = 0

    for chunk in chunks:
        chunk_header = f"### File: {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line})\n"
        chunk_content = f"```{chunk.language}\n{chunk.content}\n```\n"
        chunk_tokens = count_tokens(chunk_header + chunk_content)

        if token_count + chunk_tokens > max_tokens:
            break

        context_parts.append(chunk_header + chunk_content)
        token_count += chunk_tokens

    return "\n".join(context_parts)
```

---

## Citation Format

Every AI response includes structured citations:

```json
{
  "answer": "The `authenticate_user` function validates credentials by hashing the password and comparing with the stored hash. [src/auth/service.py:42-78]\n\nIt is called from the login endpoint in [src/api/routes/auth.py:15-30].",
  "citations": [
    {
      "file_path": "src/auth/service.py",
      "start_line": 42,
      "end_line": 78,
      "symbol_name": "authenticate_user",
      "snippet": "def authenticate_user(username: str, password: str) -> User:"
    },
    {
      "file_path": "src/api/routes/auth.py",
      "start_line": 15,
      "end_line": 30,
      "symbol_name": "login_endpoint",
      "snippet": "@router.post('/login')\nasync def login(credentials: LoginRequest):"
    }
  ]
}
```

---

## Incremental Indexing

On repository update (push/pull):
1. Compute file checksums: identify added, modified, deleted files
2. Delete Qdrant vectors for modified/deleted files (`filter by file_path`)
3. Delete Neo4j nodes for modified/deleted files
4. Re-parse and re-embed only changed files
5. Update PostgreSQL records

```python
async def incremental_reindex(repo_id: str, changed_files: List[str]):
    for file_path in changed_files:
        # Remove old vectors
        qdrant.delete(filter={"repo_id": repo_id, "file_path": file_path})
        # Remove old graph nodes
        neo4j.run("MATCH (f:File {path: $path, repo_id: $repo_id}) DETACH DELETE f",
                  path=file_path, repo_id=repo_id)
        # Re-parse and re-index
        await parse_and_embed_file(repo_id, file_path)
```

---

## Quality Evaluation

| Metric | Tool | Target |
|--------|------|--------|
| Retrieval Recall@10 | Custom eval dataset | ≥ 85% |
| Answer Relevance | LLM-as-judge | ≥ 90% |
| Citation Accuracy | Line number verification | ≥ 95% |
| Hallucination Rate | Human eval | < 5% |
| Latency (local LLM) | P95 end-to-end | < 5s |
| Latency (cloud LLM) | P95 end-to-end | < 2s |
