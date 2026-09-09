"""Shared pytest fixtures for all test modules.

Uses testcontainers to spin up real PostgreSQL and Redis instances so tests
run against actual DB behaviour rather than mocks.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base


# ── Test containers ────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Start a PostgreSQL 16 container for the entire test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Start a Redis 7 container for the entire test session."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


# ── Async engine + session ─────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Use a single event loop for the session scope."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine(postgres_container: PostgresContainer):
    """Create async engine pointing at the test PostgreSQL container."""
    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_redis(redis_container: RedisContainer) -> AsyncGenerator[Redis, None]:
    """Yield a Redis client pointing at the test Redis container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client: Redis = aioredis.Redis(host=host, port=int(port), decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async session per test, rolled back after each test."""
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ── HTTP client ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    test_redis: Redis,
) -> AsyncGenerator[AsyncClient, None]:
    """Yield an AsyncClient with DB and Redis overridden to use test containers."""

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_redis() -> AsyncGenerator[Redis, None]:
        yield test_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
