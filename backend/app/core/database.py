"""Async SQLAlchemy engine, session factory, and dependency injection helpers."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _build_engine(*, test_mode: bool = False) -> AsyncEngine:
    """Create and return the async SQLAlchemy engine.

    Args:
        test_mode: When True, uses NullPool to prevent connection sharing
                   between test cases (required by testcontainers).

    Returns:
        Configured AsyncEngine instance.
    """
    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "future": True,
    }

    if test_mode:
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 3600

    engine = create_async_engine(settings.database_url, **kwargs)
    logger.info("database_engine_created", url=settings.database_url.split("@")[-1])
    return engine


# Module-level engine — shared across the application lifetime
engine: AsyncEngine = _build_engine()

# Session factory — produces AsyncSession instances on demand
AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request.

    The session is automatically committed on success and rolled back on
    any unhandled exception, then closed in the finally block.

    Yields:
        An async SQLAlchemy session bound to the current request.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """Probe the database connection for the /ready health check endpoint.

    Returns:
        True if the database is reachable, False otherwise.
    """
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))
        return False
