"""System Architecture diagram generator (C4 Container / Mermaid)."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_architecture(
    repo_name: str,
    compose_services: list[dict[str, Any]],
    k8s_services: list[dict[str, Any]],
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Generate a Mermaid C4 container diagram for the repository architecture.

    If Docker Compose services are detected, builds the diagram from their
    definitions. Falls back to an AI-assisted generation if no infra data exists.

    Args:
        repo_name: Repository display name.
        compose_services: List of Docker Compose service dicts from extractors.
        k8s_services: List of Kubernetes service dicts from extractors.
        llm_provider: Override LLM provider for AI-assisted fallback.
        llm_model: Override LLM model.

    Returns:
        Mermaid diagram source string.
    """
    if compose_services:
        return _from_compose(repo_name, compose_services)
    if k8s_services:
        return _from_k8s(repo_name, k8s_services)
    return _ai_fallback(repo_name, llm_provider, llm_model)


def _from_compose(repo_name: str, services: list[dict]) -> str:
    """Build a C4Container Mermaid diagram from Docker Compose services.

    Args:
        repo_name: Repository display name.
        services: List of service dicts with name, image, ports, depends_on.

    Returns:
        Mermaid source string.
    """
    lines = [
        "C4Container",
        f'    title System Architecture — {repo_name}',
        "",
        '    Person(user, "Developer", "Uses the application")',
        "",
        f'    System_Boundary(sys, "{repo_name}") {{',
    ]

    for svc in services:
        name = svc["name"]
        image = svc.get("image", "")
        image_label = image.split(":")[0].split("/")[-1] if image else "App"
        safe_id = name.replace("-", "_").replace(".", "_")
        lines.append(
            f'        Container({safe_id}, "{name}", "{image_label}", "{name} service")'
        )

    lines.append("    }")
    lines.append("")

    # Dependency edges
    for svc in services:
        safe_src = svc["name"].replace("-", "_").replace(".", "_")
        for dep in svc.get("depends_on", []):
            safe_dep = dep.replace("-", "_").replace(".", "_")
            lines.append(f'    Rel({safe_src}, {safe_dep}, "uses")')

    return "\n".join(lines)


def _from_k8s(repo_name: str, services: list[dict]) -> str:
    """Build a Mermaid graph from Kubernetes services.

    Args:
        repo_name: Repository display name.
        services: List of K8s resource dicts.

    Returns:
        Mermaid source string.
    """
    lines = [f"graph TD", f"    title[{repo_name} — Kubernetes Services]"]
    for svc in services[:20]:
        name = svc["name"]
        kind = svc.get("kind", "Service")
        safe = name.replace("-", "_")
        lines.append(f"    {safe}[{name}<br/>{kind}]")
    return "\n".join(lines)


def _ai_fallback(
    repo_name: str,
    llm_provider: str | None,
    llm_model: str | None,
) -> str:
    """Use LLM to infer and generate a system architecture diagram.

    Args:
        repo_name: Repository name.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Mermaid source string.
    """
    from app.docs_gen._llm import call_llm

    prompt = f"""\
Generate a Mermaid C4Container diagram for a software repository named "{repo_name}".
Infer a reasonable microservices architecture (API, database, cache, frontend if applicable).
Output ONLY valid Mermaid C4Container syntax — no explanation, no code fences.
"""
    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")
    system = "You are a software architect. Output only valid Mermaid diagram syntax."

    try:
        return call_llm(provider, model, system, prompt, max_tokens=1500)
    except Exception as exc:
        logger.warning("architecture_ai_fallback_failed", error=str(exc))
        return (
            "graph TD\n"
            f"    A[{repo_name}]\n"
            "    A --> B[API Layer]\n"
            "    A --> C[Database]\n"
        )
