"""Kroki diagram renderer — converts source code to PNG/SVG bytes.

Calls the self-hosted Kroki server (http://kroki:8000 by default).
Falls back to returning empty bytes if Kroki is unavailable, so diagram
source is still saved even if rendering fails.
"""

from __future__ import annotations

import base64
import zlib

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_KROKI_URL = "http://kroki:8000"


def _kroki_url() -> str:
    return getattr(settings, "kroki_url", _DEFAULT_KROKI_URL).rstrip("/")


# ── Format → Kroki endpoint mapping ──────────────────────────────────────────

_FORMAT_MAP = {
    "mermaid": "mermaid",
    "plantuml": "plantuml",
    "d2": "d2",
    "graphviz": "graphviz",
}


def render_diagram(
    source: str,
    diagram_format: str = "mermaid",
    output_format: str = "svg",
    *,
    timeout: float = 30.0,
) -> bytes:
    """Render diagram source to PNG or SVG bytes via Kroki.

    Args:
        source: Raw diagram source text (Mermaid, PlantUML, D2, …).
        diagram_format: Diagram language slug (mermaid | plantuml | d2).
        output_format: Desired output format (svg | png).
        timeout: HTTP request timeout in seconds.

    Returns:
        Raw rendered bytes. Returns empty bytes if Kroki is unavailable.
    """
    kroki_fmt = _FORMAT_MAP.get(diagram_format, diagram_format)
    url = f"{_kroki_url()}/{kroki_fmt}/{output_format}"

    try:
        response = httpx.post(
            url,
            content=source.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=timeout,
        )
        response.raise_for_status()
        logger.info("kroki_render_ok", fmt=diagram_format, output=output_format, bytes=len(response.content))
        return response.content

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "kroki_render_http_error",
            status=exc.response.status_code,
            fmt=diagram_format,
        )
        return b""

    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("kroki_unavailable", error=str(exc))
        return b""

    except Exception as exc:
        logger.warning("kroki_render_failed", error=str(exc))
        return b""


def render_mermaid_encoded(source: str, output_format: str = "svg") -> bytes:
    """Render Mermaid using the URL-safe encoded GET endpoint (alternative path).

    This uses the base64+zlib encoded GET variant of the Kroki API, which
    is useful if POST with text/plain is blocked.

    Args:
        source: Mermaid source text.
        output_format: svg | png.

    Returns:
        Rendered bytes.
    """
    compressed = zlib.compress(source.encode("utf-8"), level=9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
    url = f"{_kroki_url()}/mermaid/{output_format}/{encoded}"
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        return response.content
    except Exception as exc:
        logger.warning("kroki_get_render_failed", error=str(exc))
        return b""
