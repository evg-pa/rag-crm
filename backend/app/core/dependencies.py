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


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency: yields a Redis connection."""
    redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        _settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        yield redis_client
    finally:
        await redis_client.aclose()
