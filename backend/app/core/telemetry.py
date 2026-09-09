"""OpenTelemetry tracing setup for CodeAtlas AI.

Provides:
- ``setup_tracing(app)``   — configure OTLP exporter and instrument FastAPI.
- ``get_tracer(name)``     — return a named tracer for manual spans.
- ``traced_span(name)``    — async context manager for manual spans.

Configuration is driven by settings:
    otel_enabled                   bool   (default: False)
    otel_service_name              str    (default: "codeatlas-backend")
    otel_exporter_otlp_endpoint    str    (default: "http://jaeger:4317")
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_tracing(app) -> None:
    """Configure OpenTelemetry OTLP exporter and auto-instrument FastAPI.

    Safe to call even if otel_enabled is False — in that case this is a no-op.

    Args:
        app: FastAPI application instance.
    """
    from app.core.config import settings

    if not getattr(settings, "otel_enabled", False):
        logger.debug("otel_tracing_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = getattr(settings, "otel_exporter_otlp_endpoint", "http://jaeger:4317")
        service_name = getattr(settings, "otel_service_name", "codeatlas-backend")

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()

        logger.info(
            "otel_tracing_enabled",
            service=service_name,
            endpoint=endpoint,
        )

    except ImportError as exc:
        logger.warning("otel_packages_missing", error=str(exc))
    except Exception as exc:
        logger.error("otel_setup_failed", error=str(exc))


def get_tracer(name: str):
    """Return an OpenTelemetry tracer for a given module name.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        OpenTelemetry Tracer instance (or a no-op tracer if OTel not configured).
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


@asynccontextmanager
async def traced_span(
    name: str,
    tracer_name: str = "codeatlas",
    **attributes,
) -> AsyncGenerator[None, None]:
    """Async context manager that wraps a code block in an OTel span.

    Args:
        name: Span name.
        tracer_name: Tracer name (defaults to "codeatlas").
        **attributes: Span attributes to set at creation.

    Yields:
        Control to the wrapped block.
    """
    tracer = get_tracer(tracer_name)
    try:
        with tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
            yield
    except AttributeError:
        # No-op if tracer doesn't support start_as_current_span
        yield


class _NoopTracer:
    """Minimal no-op tracer when opentelemetry is not installed."""

    def start_as_current_span(self, name: str, **_):
        from contextlib import nullcontext
        return nullcontext()
