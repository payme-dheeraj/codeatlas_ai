"""Deployment topology diagram generator (Mermaid graph / D2)."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_deployment(
    repo_name: str,
    compose_services: list[dict[str, Any]],
    k8s_services: list[dict[str, Any]],
    *,
    output_format: str = "mermaid",
) -> str:
    """Generate a deployment topology diagram.

    Prefers Docker Compose data; falls back to Kubernetes; falls back to stub.

    Args:
        repo_name: Repository display name.
        compose_services: Docker Compose service dicts.
        k8s_services: Kubernetes resource dicts.
        output_format: "mermaid" or "d2".

    Returns:
        Diagram source string in the requested format.
    """
    if compose_services:
        if output_format == "d2":
            return _compose_to_d2(repo_name, compose_services)
        return _compose_to_mermaid(repo_name, compose_services)

    if k8s_services:
        return _k8s_to_mermaid(repo_name, k8s_services)

    return _stub(repo_name, output_format)


def _compose_to_mermaid(repo_name: str, services: list[dict]) -> str:
    """Build a Mermaid graph from Docker Compose service topology.

    Args:
        repo_name: Repository name.
        services: List of Docker Compose service dicts.

    Returns:
        Mermaid source string.
    """
    lines = ["graph LR"]
    lines.append(f"    internet([Internet])")

    # Find services with external ports — these are entry points
    entry_points = [s for s in services if s.get("ports")]
    internal = [s for s in services if not s.get("ports")]

    # Subgraph for the system
    lines.append(f"    subgraph {_safe(repo_name)}[{repo_name}]")

    for svc in services:
        name = svc["name"]
        safe = _safe(name)
        image = svc.get("image", "").split(":")[0].split("/")[-1] if svc.get("image") else ""
        label = f"{name}" + (f"<br/>{image}" if image else "")
        lines.append(f"        {safe}[{label}]")

    lines.append("    end")
    lines.append("")

    # Internet → entry points
    for svc in entry_points:
        ports = svc.get("ports", [])
        port_str = str(ports[0]).split(":")[-1] if ports else ""
        lines.append(f"    internet -->|:{port_str}| {_safe(svc['name'])}")

    # Dependency edges
    for svc in services:
        src = _safe(svc["name"])
        for dep in svc.get("depends_on", []):
            tgt = _safe(dep)
            lines.append(f"    {src} --> {tgt}")

    return "\n".join(lines)


def _compose_to_d2(repo_name: str, services: list[dict]) -> str:
    """Build a D2 deployment diagram from Docker Compose services.

    Args:
        repo_name: Repository name.
        services: Docker Compose service dicts.

    Returns:
        D2 source string.
    """
    lines = ["direction: right", ""]
    lines.append("internet -> nginx: HTTPS 443")
    lines.append("")

    for svc in services:
        for dep in svc.get("depends_on", []):
            lines.append(f"{svc['name']} -> {dep}")

    return "\n".join(lines)


def _k8s_to_mermaid(repo_name: str, services: list[dict]) -> str:
    """Build a Mermaid graph from Kubernetes services.

    Args:
        repo_name: Repository name.
        services: K8s resource dicts.

    Returns:
        Mermaid source string.
    """
    lines = ["graph TD"]
    lines.append(f"    internet([Internet])")
    lines.append(f"    subgraph k8s[Kubernetes Cluster]")

    for svc in services[:15]:
        name = svc["name"]
        kind = svc.get("kind", "Pod")
        safe = _safe(name)
        lines.append(f"        {safe}[{name}<br/>{kind}]")

    lines.append("    end")
    lines.append("    internet --> k8s")
    return "\n".join(lines)


def _stub(repo_name: str, fmt: str) -> str:
    if fmt == "d2":
        return f"# {repo_name}\n# No deployment files detected\nclient -> server"
    return (
        "graph LR\n"
        f"    internet([Internet])\n"
        f"    internet --> app[{repo_name}]\n"
        f"    app --> db[(Database)]\n"
    )


def _safe(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)
