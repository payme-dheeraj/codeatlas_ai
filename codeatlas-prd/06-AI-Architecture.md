# 06 — AI Architecture

## Overview

CodeAtlas AI uses a **multi-agent LangGraph architecture** built on top of a **LlamaIndex RAG pipeline**. The system is LLM-agnostic, supporting local models via Ollama, OpenAI, Anthropic, and any OpenAI-compatible endpoint.

---

## LLM Provider Stack

```
┌─────────────────────────────────────────────────────┐
│              AI Service (FastAPI)                    │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │           LLM Router / Provider Manager       │   │
│  └──────────┬────────────────┬──────────────────┘   │
│             │                │                        │
│    ┌────────▼──────┐  ┌──────▼──────────────────┐   │
│    │  Ollama       │  │  Cloud LLM Adapter       │   │
│    │  (local)      │  │  OpenAI / Anthropic /    │   │
│    │               │  │  Azure OpenAI / Together │   │
│    │  Models:      │  └──────────────────────────┘   │
│    │  - llama3.2   │                                  │
│    │  - codellama  │  Embedding Models:               │
│    │  - deepseek-  │  - text-embedding-3-small        │
│    │    coder      │  - nomic-embed-text (Ollama)     │
│    │  - phi3       │  - sentence-transformers          │
│    └───────────────┘                                  │
└─────────────────────────────────────────────────────┘
```

### Provider Configuration

```python
class LLMConfig(BaseSettings):
    provider: str = "ollama"           # ollama | openai | anthropic | azure
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"
    embedding_model: str = "nomic-embed-text"  # or text-embedding-3-small
    embedding_dimensions: int = 1536
    max_context_tokens: int = 8192
    temperature: float = 0.1
```

---

## LangGraph Agent Architecture

### Agent Graph Structure

```
                ┌──────────────────┐
                │   User Query      │
                └────────┬─────────┘
                         │
                ┌────────▼─────────┐
                │  Query Analyzer   │  Classify: chat / explain / diagram / docs / security
                └────────┬─────────┘
                         │
          ┌──────────────┼──────────────────┐
          │              │                  │
  ┌───────▼──────┐ ┌─────▼──────┐  ┌───────▼──────┐
  │  Chat Agent  │ │  Explain   │  │  Generator   │
  │  (RAG-based) │ │  Agent     │  │  Agent       │
  └───────┬──────┘ └─────┬──────┘  └───────┬──────┘
          │              │                  │
  ┌───────▼──────────────▼──────────────────▼──────┐
  │              Retriever Node                     │
  │  ┌─────────────────┐  ┌───────────────────┐    │
  │  │  Vector Retriever│  │  Graph Retriever  │    │
  │  │  (Qdrant)        │  │  (Neo4j)          │    │
  │  └─────────────────┘  └───────────────────┘    │
  └──────────────────────────┬─────────────────────┘
                             │
                   ┌─────────▼─────────┐
                   │   Reranker Node    │  Cross-encoder reranking
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │  Context Builder   │  Assemble prompt with citations
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │    LLM Node        │  Generate response (streaming)
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │  Citation Extractor│  Extract file/line refs
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │   Final Response   │
                   └───────────────────┘
```

### Agent State

```python
from langgraph.graph import StateGraph
from typing import TypedDict, List, Optional

class AgentState(TypedDict):
    query: str
    repo_id: str
    session_id: str
    query_type: str                    # chat | explain | generate
    retrieved_chunks: List[dict]       # from Qdrant
    graph_context: List[dict]          # from Neo4j
    reranked_chunks: List[dict]
    prompt: str
    response: str
    citations: List[dict]              # file, start_line, end_line, snippet
    conversation_history: List[dict]
    error: Optional[str]
```

---

## Embedding Pipeline

### Chunking Strategy

```python
class CodeChunker:
    """
    Hierarchical chunking:
    1. Function-level chunks (preferred — preserves semantic boundaries)
    2. Class-level chunks for small classes
    3. Fixed-size chunks with overlap for long functions
    """
    chunk_size: int = 512        # tokens
    chunk_overlap: int = 50      # tokens
    min_chunk_size: int = 50     # tokens

    def chunk(self, file_content: str, language: str) -> List[Chunk]:
        # Use Tree-sitter to find function/class boundaries
        # Prefer semantic boundaries over fixed-size splits
        ...
```

### Embedding Models

| Use Case | Model | Dimensions | Provider |
|----------|-------|-----------|---------|
| Code chunks | `nomic-embed-text` | 768 | Ollama (local) |
| Code chunks | `text-embedding-3-small` | 1536 | OpenAI |
| Query embedding | Same as code | — | Matched to index |
| Doc chunks | `nomic-embed-text` | 768 | Ollama |

### Metadata per Embedding

```python
{
    "repo_id": "uuid",
    "file_path": "src/auth/service.py",
    "language": "python",
    "chunk_type": "function",      # function | class | comment | docstring | code
    "symbol_name": "authenticate_user",
    "start_line": 42,
    "end_line": 78,
    "content": "def authenticate_user(...):\n    ...",
}
```

---

## RAG Retrieval Strategy

### Hybrid Retrieval

```python
async def hybrid_retrieve(query: str, repo_id: str, top_k: int = 20):
    # 1. Dense retrieval from Qdrant
    vector_results = await qdrant.search(
        collection="code_chunks",
        query_vector=await embed(query),
        filter={"repo_id": repo_id},
        limit=top_k
    )

    # 2. Graph-based context expansion from Neo4j
    # For each retrieved function, fetch callers + callees
    graph_context = await neo4j.query("""
        MATCH (f:Function {name: $name})-[:CALLS|CALLED_BY*1..2]-(related)
        RETURN related
    """, name=extracted_symbol)

    # 3. Keyword fallback (PostgreSQL FTS)
    keyword_results = await pg.query(
        "SELECT * FROM symbols WHERE to_tsvector(content) @@ plainto_tsquery($1)",
        query
    )

    return merge_and_deduplicate(vector_results, graph_context, keyword_results)
```

### Reranking

```python
# Cross-encoder reranking using sentence-transformers
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank(query: str, chunks: List[dict]) -> List[dict]:
    pairs = [(query, chunk["content"]) for chunk in chunks]
    scores = reranker.predict(pairs)
    return sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:10]
```

---

## Prompt Templates

### Repository Chat Prompt

```
You are CodeAtlas AI, an expert code analyst. You have been given context from the repository "{repo_name}".

CONTEXT (from source code):
{context_with_citations}

CONVERSATION HISTORY:
{conversation_history}

USER QUESTION:
{user_query}

INSTRUCTIONS:
- Answer based ONLY on the provided context.
- ALWAYS cite the exact file path and line numbers for every claim.
- Format citations as: [file_path:line_start-line_end]
- If you cannot find the answer in the context, say "I couldn't find information about this in the codebase."
- Use markdown for code snippets.

ANSWER:
```

### Code Explanation Prompt

```
You are a senior software engineer. Explain the following {language} code clearly and concisely.

FILE: {file_path} (lines {start_line}-{end_line})
```{language}
{code_snippet}
```

Explain:
1. What this code does (1-2 sentences)
2. Key logic and algorithms
3. Parameters and return values
4. Any potential issues or edge cases

EXPLANATION:
```

---

## Agent Tools

The LangGraph chat agent has access to the following tools:

| Tool | Description |
|------|-------------|
| `search_code` | Semantic search over code chunks |
| `get_file_content` | Retrieve full file content from MinIO |
| `get_function_definition` | Look up a specific function by name |
| `get_callers` | Find all callers of a function (Neo4j) |
| `get_callees` | Find all functions called by a function (Neo4j) |
| `get_file_tree` | Get repository file structure |
| `get_module_summary` | Get AI-generated module summary |
| `search_symbols` | Search for symbols by name/type |
