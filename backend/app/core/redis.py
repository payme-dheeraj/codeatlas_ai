"""Redis connection pool and helper utilities."""

from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    """Return (or lazily create) the module-level Redis connection pool.

    Returns:
        A shared ConnectionPool instance.
    """
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
        )
        logger.info("redis_pool_created", max_connections=settings.redis_max_connections)
    return _pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency that yields a Redis client per request.

    Yields:
        A Redis client backed by the shared connection pool.
    """
    client: Redis = aioredis.Redis(connection_pool=get_redis_pool())
    try:
        yield client
    finally:
        await client.aclose()


async def check_redis_health() -> bool:
    """Probe Redis connectivity for the /ready health-check endpoint.

    Returns:
        True if Redis responds to PING, False otherwise.
    """
    try:
        client: Redis = aioredis.Redis(connection_pool=get_redis_pool())
        await client.ping()
        await client.aclose()
        return True
    except Exception as exc:
        logger.error("redis_health_check_failed", error=str(exc))
        return False


class RedisCache:
    """Thin wrapper around Redis providing typed get/set/delete helpers.

    Attributes:
        client: The underlying async Redis client.
        default_ttl: Default TTL in seconds applied when no TTL is specified.
    """

    def __init__(self, client: Redis, default_ttl: int = 300) -> None:
        """Initialise the cache wrapper.

        Args:
            client: An async Redis client instance.
            default_ttl: Default time-to-live in seconds (default: 300).
        """
        self.client = client
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        """Retrieve and return a value by key, or None if absent.

        Args:
            key: Redis key to look up.

        Returns:
            The stored value, or None.
        """
        import json

        raw = await self.client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Serialise ``value`` to JSON and store it in Redis.

        Args:
            key: Redis key.
            value: JSON-serialisable value.
            ttl: Time-to-live in seconds; falls back to ``default_ttl``.
        """
        import json

        await self.client.setex(
            key,
            ttl if ttl is not None else self.default_ttl,
            json.dumps(value, default=str),
        )

    async def delete(self, key: str) -> None:
        """Remove a key from Redis.

        Args:
            key: Redis key to delete.
        """
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in Redis.

        Args:
            key: Redis key to test.

        Returns:
            True if the key exists, False otherwise.
        """
        return bool(await self.client.exists(key))
