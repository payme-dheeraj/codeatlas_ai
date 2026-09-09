"""FastAPI application entrypoint.

Configures:
- Structured logging
- OpenTelemetry tracing (when enabled)
- Prometheus metrics
- CORS middleware
- API routers
- Health / readiness probes
- Lifespan startup / shutdown hooks
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import check_db_health
from app.core.logging import configure_logging, get_logger
from app.core.redis import check_redis_health
from app.core.storage import storage_client

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and graceful shutdown.

    Startup:
    - Ensure MinIO bucket exists.
    - Log readiness.

    Shutdown:
    - Nothing currently required; connection pools are closed by their
      respective modules' finalizers.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the running application.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info(
        "application_starting",
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    # Ensure MinIO bucket exists (idempotent)
    await storage_client.ensure_bucket()

    logger.info("application_ready")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")


# ── Application factory ────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Fully configured FastAPI instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "CodeAtlas AI — Enterprise-grade AI Code Intelligence Platform. "
            "Repository ingestion, semantic understanding, AI chat, "
            "security scanning, and architecture diagram generation."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── OpenTelemetry ─────────────────────────────────────────────────────────
    if settings.otel_enabled:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            )
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        logger.info("otel_tracing_enabled", endpoint=settings.otel_exporter_otlp_endpoint)

    # ── Prometheus metrics ────────────────────────────────────────────────────
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/health", "/ready", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Health probes ─────────────────────────────────────────────────────────

    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        """Liveness probe — returns 200 if the process is alive."""
        return JSONResponse(
            {"status": "ok", "service": settings.otel_service_name, "version": settings.app_version}
        )

    @app.get("/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        """Readiness probe — checks all critical dependencies."""
        checks = {
            "postgres": await check_db_health(),
            "redis": await check_redis_health(),
            "storage": await storage_client.check_health(),
        }
        all_ok = all(checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={
                "status": "ready" if all_ok else "not_ready",
                "checks": checks,
            },
        )

    return app


app = create_app()
