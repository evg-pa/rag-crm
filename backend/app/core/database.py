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
    """Create an async SQLAlchemy engine with connection pooling."""
    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=15,
        pool_pre_ping=True,
        echo=False,
    )


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
