"""Wiki generator.

Produces a comprehensive developer wiki covering all sections from the PRD:
Overview, Architecture, Modules, Data Models, API Reference, Configuration,
Development, Deployment, Security, and Runbooks.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.docs_gen._llm import call_llm

logger = get_logger(__name__)

_SYSTEM = (
    "You are an expert software architect and technical writer. Generate a comprehensive, "
    "well-structured developer wiki in Markdown. Be thorough but concise. "
    "Include concrete examples, file paths, and command snippets where relevant."
)

_PROMPT = """\
Generate a comprehensive developer wiki for the following repository.

## Repository: {repo_name}
## Description: {description}
## Tech Stack: {tech_stack}
## Languages: {languages}
## Primary Language: {primary_language}

## Module / Service Summary
{module_summaries}

## Key Data Models / Entities
{data_models}

## Infrastructure Overview
{infra_info}

## Security Context
{security_context}

---

Generate a wiki with ALL of these sections:

# {repo_name} Developer Wiki

## 1. Overview
(Repository purpose, target audience, high-level architecture)

## 2. Architecture
(System design overview, component interactions, key design decisions)

## 3. Modules
(Per-module deep-dive: purpose, key files, important functions/classes)

## 4. Data Models
(Key entities, their fields, and relationships)

## 5. API Reference
(Summary of main API endpoints, link to full reference)

## 6. Configuration
(All important environment variables and configuration options)

## 7. Development Guide
(Setup, testing, debugging, coding conventions)

## 8. Deployment
(Docker, Kubernetes, CI/CD pipeline overview)

## 9. Security
(Auth model, secrets management, known security posture)

## 10. Runbooks
(Common operational procedures: restart service, clear cache, run migrations, etc.)

Respond with ONLY the Markdown wiki content — no preamble.
"""


def generate_wiki(
    repo_name: str,
    repo_context: dict[str, Any],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate a comprehensive developer wiki.

    Args:
        repo_name: Repository display name.
        repo_context: Dict with description, tech_stack, languages,
            primary_language, module_summaries, data_models,
            infra_info, security_context.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Generated Markdown wiki string.
    """
    prompt = _PROMPT.format(
        repo_name=repo_name,
        description=repo_context.get("description", "No description available."),
        tech_stack=", ".join(repo_context.get("tech_stack", [])) or "Unknown",
        languages=", ".join(repo_context.get("languages", [])) or "Unknown",
        primary_language=repo_context.get("primary_language", "Unknown"),
        module_summaries=repo_context.get("module_summaries", "(not analyzed)"),
        data_models=repo_context.get("data_models", "(not analyzed)"),
        infra_info=repo_context.get("infra_info", "(none detected)"),
        security_context=repo_context.get("security_context", "(not analyzed)"),
    )

    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")

    logger.info("generating_wiki", repo=repo_name)
    return call_llm(provider, model, _SYSTEM, prompt, max_tokens=6000)


def generate_onboarding_guide(
    repo_name: str,
    repo_context: dict[str, Any],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate a new developer onboarding guide.

    Args:
        repo_name: Repository display name.
        repo_context: Repository context dict.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Generated Markdown onboarding guide string.
    """
    onboarding_prompt = f"""\
Generate a new developer onboarding guide for the **{repo_name}** repository.

Tech Stack: {', '.join(repo_context.get('tech_stack', [])) or 'Unknown'}
Primary Language: {repo_context.get('primary_language', 'Unknown')}
Infrastructure: {repo_context.get('infra_info', 'Docker Compose')}

Include:
1. Welcome and repository overview
2. Prerequisites and tool installation
3. Getting the code and environment setup (step-by-step)
4. Understanding the codebase structure
5. Running the development environment
6. Running tests
7. Making your first contribution (branching, PR process)
8. Key contacts and resources

Respond with ONLY Markdown — no preamble.
"""

    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")
    system = (
        "You are a senior developer creating an onboarding guide for new team members. "
        "Be welcoming, clear, and thorough. Assume the reader is a competent developer "
        "but unfamiliar with this specific codebase."
    )

    logger.info("generating_onboarding", repo=repo_name)
    return call_llm(provider, model, system, onboarding_prompt, max_tokens=3000)
