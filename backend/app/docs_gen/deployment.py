"""Deployment Guide generator.

Analyses Docker Compose, Kubernetes manifests, and environment variable
files to produce a deployment guide covering all PRD sections.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.docs_gen._llm import call_llm

logger = get_logger(__name__)

_SYSTEM = (
    "You are a DevOps expert and technical writer. Generate a clear, accurate "
    "deployment guide in Markdown based on the provided infrastructure files and metadata. "
    "Be practical and include concrete commands where possible."
)

_PROMPT = """\
Generate a Deployment Guide for the following repository.

## Repository: {repo_name}

## Docker Compose Services Detected
{compose_info}

## Kubernetes Manifests Detected
{k8s_info}

## Environment Variables Detected
{env_vars}

## Ports / Endpoints Detected
{ports}

## Health Check Endpoints
{health_checks}

---

Generate a Deployment Guide with these sections:
1. Prerequisites
2. Environment Variables (table: name, description, required, example)
3. Docker Compose Deployment (step-by-step commands)
4. Kubernetes Deployment (manifests apply order + commands)
5. Health Checks
6. Scaling
7. Backup & Restore
8. Troubleshooting (common issues + fixes)

Respond with ONLY Markdown — no preamble.
"""


def generate_deployment_guide(
    repo_name: str,
    infra_context: dict[str, Any],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate a deployment guide from detected infrastructure context.

    Args:
        repo_name: Repository display name.
        infra_context: Dict with keys: compose_info, k8s_info, env_vars,
            ports, health_checks.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Generated Markdown string.
    """
    prompt = _PROMPT.format(
        repo_name=repo_name,
        compose_info=infra_context.get("compose_info", "(none detected)"),
        k8s_info=infra_context.get("k8s_info", "(none detected)"),
        env_vars=infra_context.get("env_vars", "(none detected)"),
        ports=infra_context.get("ports", "(none detected)"),
        health_checks=infra_context.get("health_checks", "(none detected)"),
    )

    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")

    logger.info("generating_deployment_guide", repo=repo_name)
    return call_llm(provider, model, _SYSTEM, prompt, max_tokens=3500)
