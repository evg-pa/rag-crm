"""Dependency injection container for FastAPI."""

from collections.abc import AsyncGenerator
from functools import lru_cache

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import create_engine, create_session_factory, get_db


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()


# Module-level engine + session factory (created once per process)
_settings = get_settings()
_engine = create_engine(_settings)
_session_factory = create_session_factory(_engine)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async for session in get_db(_session_factory):
        yield session


# Shared Redis connection pool (lazy singleton, same pattern as RateLimitMiddleware)
_redis_pool: aioredis.ConnectionPool | None = None


async def _get_redis_pool() -> aioredis.ConnectionPool:
    """Lazily create and return a shared Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            _settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=_settings.REDIS_POOL_MAX_CONNECTIONS,
        )
    return _redis_pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency: yields a Redis connection from the shared pool.

    Uses a process-wide ConnectionPool so connections are reused across
    requests instead of creating a new TCP connection every time.
    """
    pool = await _get_redis_pool()
    redis_client: aioredis.Redis = aioredis.Redis(connection_pool=pool)  # type: ignore[no-untyped-call]
    try:
        yield redis_client
    finally:
        await redis_client.aclose()
