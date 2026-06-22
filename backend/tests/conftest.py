"""Test configuration: in-memory SQLite database and shared fixtures."""

import os
from collections.abc import AsyncGenerator, AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Force in-memory SQLite BEFORE any app imports ──────────────────────────
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

from app.core.database import Base  # noqa: E402
from app.main import app  # noqa: E402

# Ensure all models are imported so create_all sees them
from app.models.chunk import Chunk  # noqa: E402, F401
from app.models.document import Document  # noqa: E402, F401

TEST_ENGINE = create_async_engine("sqlite+aiosqlite://", echo=False)
TEST_SESSION_FACTORY = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def _setup_database() -> AsyncIterator[None]:
    """Create all tables once for the test session, then drop them."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await TEST_ENGINE.dispose()


@pytest.fixture(autouse=True)
async def _clean_db() -> AsyncGenerator[None, None]:
    """Truncate all tables between tests for isolation."""
    yield
    async with TEST_ENGINE.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency override: yield a session from the in-memory SQLite."""
    async with TEST_SESSION_FACTORY() as session:
        try:
            yield session
        finally:
            await session.close()


# Override the FastAPI dependency BEFORE any test collects
app.dependency_overrides = {}

from app.core.dependencies import get_db_session  # noqa: E402

app.dependency_overrides[get_db_session] = _override_get_db_session


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Return an async HTTP client for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
