"""Structured prompt templates for the RAG agent.

All prompts are defined as plain strings with ``{placeholder}`` style
format fields. They are rendered by the ``generate_answer`` node before
being sent to the LLM.
"""

from __future__ import annotations

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are CodeAtlas AI, an expert software engineering assistant with deep knowledge \
of code architecture, design patterns, and best practices.

Your role is to answer questions about codebases by analysing the provided source \
code context. You have access to extracted code symbols (functions, classes, methods) \
from real repositories.

Guidelines:
- Base your answers ONLY on the provided code context. Do not hallucinate APIs, \
  functions, or behaviours that are not shown in the context.
- Cite specific file paths and line numbers when referencing code.
- When explaining code, be precise and technical.
- If the context is insufficient to answer confidently, say so explicitly.
- Format code snippets with appropriate markdown code fences and language tags.
- Keep answers focused and actionable.
"""

# ── RAG answer prompt ─────────────────────────────────────────────────────────

RAG_PROMPT = """\
## Question
{question}

## Code Context
The following code symbols were retrieved from the codebase as relevant context:

{context}

## Graph Context
{graph_context}

## Instructions
Using the code context above, provide a thorough and technically precise answer \
to the question. Cite file paths and line numbers where relevant. If the context \
does not contain enough information to answer fully, state what is known and what \
is uncertain.
"""

# ── Context chunk formatter ───────────────────────────────────────────────────

CONTEXT_CHUNK_TEMPLATE = """\
### [{index}] `{qualified_name}` ({symbol_kind})
**File:** `{file_path}` (lines {start_line}–{end_line})
**Language:** {language}
{signature_block}
{docstring_block}
```{language}
{chunk_text}
```
"""

# ── Graph context formatter ───────────────────────────────────────────────────

GRAPH_CONTEXT_TEMPLATE = """\
### Call Graph Context
The following relationships were found in the code knowledge graph:

{relationships}
"""

GRAPH_CONTEXT_EMPTY = "No additional graph relationships were found for this query."

# ── Fallback answer ───────────────────────────────────────────────────────────

INSUFFICIENT_CONTEXT_ANSWER = (
    "I could not find sufficient context in the indexed codebase to answer "
    "this question confidently. Please ensure the relevant repository has been "
    "indexed, or try rephrasing the question with more specific symbol names."
)


def format_context_chunk(index: int, chunk: dict) -> str:
    """Render a single context chunk into the prompt template.

    Args:
        index: 1-indexed position in the context list.
        chunk: Dict with keys matching Qdrant payload fields.

    Returns:
        Formatted markdown string for this chunk.
    """
    sig = chunk.get("signature") or ""
    doc = chunk.get("docstring") or ""
    language = chunk.get("language", "text")

    signature_block = f"**Signature:** `{sig}`\n" if sig else ""
    docstring_block = f"**Docstring:** {doc}\n" if doc else ""

    return CONTEXT_CHUNK_TEMPLATE.format(
        index=index,
        qualified_name=chunk.get("qualified_name", chunk.get("name", "unknown")),
        symbol_kind=chunk.get("symbol_kind", "symbol"),
        file_path=chunk.get("file_path", ""),
        start_line=chunk.get("start_line", 0),
        end_line=chunk.get("end_line", 0),
        language=language,
        signature_block=signature_block,
        docstring_block=docstring_block,
        chunk_text=chunk.get("chunk_text", ""),
    )


def build_rag_prompt(question: str, chunks: list[dict], graph_context: str) -> str:
    """Assemble the full RAG user prompt from retrieved context.

    Args:
        question: The user's question.
        chunks: List of retrieved and reranked context chunk dicts.
        graph_context: Graph relationship string from Neo4j.

    Returns:
        Fully rendered RAG prompt string.
    """
    if not chunks:
        context_str = "_No relevant code context was found._"
    else:
        context_str = "\n\n".join(
            format_context_chunk(i + 1, c) for i, c in enumerate(chunks)
        )

    graph_str = graph_context if graph_context.strip() else GRAPH_CONTEXT_EMPTY

    return RAG_PROMPT.format(
        question=question,
        context=context_str,
        graph_context=graph_str,
    )
