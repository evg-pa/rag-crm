"""SQLAlchemy 2.0 async engine, session factory, and Base."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


def create_engine(settings: Settings) -> Any:
    """Create an async SQLAlchemy engine with connection pooling.

    Pool arguments are omitted for SQLite backends because aiosqlite
    does not support them.
    """
    kwargs: dict[str, Any] = {"echo": False}
    if not settings.DATABASE_URL.startswith("sqlite"):
        kwargs.update({"pool_size": 5, "max_overflow": 15, "pool_pre_ping": True})
    return create_async_engine(settings.DATABASE_URL, **kwargs)


def create_session_factory(engine: Any) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db(settings: Settings) -> None:
    """Create all tables (dev/auto-migrate mode)."""
    engine = create_engine(settings)
    async with engine.begin() as conn:
        from app.models.chunk import Chunk  # noqa: F401
        from app.models.document import Document  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
