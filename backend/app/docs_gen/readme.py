"""README generator.

Builds a structured README prompt from repository metadata and parsed
symbols, then calls the configured LLM to produce the Markdown content.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.docs_gen._llm import call_llm

logger = get_logger(__name__)

# ── README prompt template (based on PRD structure) ───────────────────────────

_SYSTEM = (
    "You are an expert technical writer. Generate a professional, well-structured "
    "README in Markdown for the described software repository. Be accurate and concise. "
    "Use only information provided — do not invent features or APIs."
)

_PROMPT = """\
Generate a README.md for the following repository.

## Repository Metadata
- **Name:** {repo_name}
- **Description:** {description}
- **Primary Language:** {primary_language}
- **Detected Languages:** {languages}
- **Tech Stack:** {tech_stack}
- **License:** {license}

## Top-Level File Structure
```
{file_tree}
```

## Detected Package Manager Files
{package_files}

## Key Modules / Services
{module_summaries}

## Docker / Kubernetes Information
{infra_info}

---

Generate a README with the following sections (skip any section where no data is available):
1. Title and one-line description
2. Features (inferred from code/modules)
3. Tech Stack (with markdown badge links if possible)
4. Getting Started: Prerequisites, Installation, Running Locally
5. Project Structure (annotated file tree)
6. API Reference (brief, link to generated docs)
7. Configuration (key environment variables)
8. Contributing
9. License

Respond with ONLY the Markdown content — no preamble.
"""


def generate_readme(repo_context: dict[str, Any]) -> str:
    """Generate a README document for a repository.

    Args:
        repo_context: Dict with keys: repo_name, description, primary_language,
            languages, tech_stack, license, file_tree, package_files,
            module_summaries, infra_info, llm_provider, llm_model.

    Returns:
        Generated Markdown string.
    """
    prompt = _PROMPT.format(
        repo_name=repo_context.get("repo_name", "Unknown Repository"),
        description=repo_context.get("description", "No description available."),
        primary_language=repo_context.get("primary_language", "Unknown"),
        languages=", ".join(repo_context.get("languages", [])) or "Unknown",
        tech_stack=", ".join(repo_context.get("tech_stack", [])) or "Unknown",
        license=repo_context.get("license", "Not detected"),
        file_tree=repo_context.get("file_tree", "(not available)"),
        package_files=repo_context.get("package_files", "(none detected)"),
        module_summaries=repo_context.get("module_summaries", "(not available)"),
        infra_info=repo_context.get("infra_info", "(none detected)"),
    )

    provider = repo_context.get("llm_provider") or getattr(settings, "llm_provider", "ollama")
    model = repo_context.get("llm_model") or getattr(settings, "llm_model", "llama3.2")

    logger.info("generating_readme", repo=repo_context.get("repo_name"))
    return call_llm(provider, model, _SYSTEM, prompt, max_tokens=3000)
