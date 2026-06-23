"""Test configuration: in-memory SQLite database and shared fixtures."""

import os
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── SQLite-compatible Vector replacement ────────────────────────────────────
# pgvector.sqlalchemy.Vector generates ``vector(384)`` DDL that SQLite
# rejects.  Replace it with a LargeBinary-based type BEFORE any app model
# imports the real module, so create_all succeeds on the in-memory DB.


class _SQLiteVector(sa.types.UserDefinedType):
    """Drop-in for pgvector.sqlalchemy.Vector that stores embeddings as
    raw bytes (float32 little-endian) in a BLOB column.

    SQLite-only; real Postgres deployments use the actual pgvector type.

    Exposes the same comparator methods (cosine_distance, l2_distance, etc.)
    so that ORM queries using those operators work in tests.
    """

    def __init__(self, dim: int | None = None):
        super().__init__()
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return "BLOB"

    class comparator_factory(sa.types.UserDefinedType.Comparator):  # noqa: N801
        """Comparators that mirror pgvector's Vector.Comparator."""

        def cosine_distance(self, other: object) -> sa.ColumnElement[float]:
            return sa.literal(0.0)

        def l2_distance(self, other: object) -> sa.ColumnElement[float]:
            return sa.literal(0.0)

        def inner_product(self, other: object) -> sa.ColumnElement[float]:
            return sa.literal(0.0)

        def max_inner_product(self, other: object) -> sa.ColumnElement[float]:
            return sa.literal(0.0)


_pg_sqlalchemy_mock = Mock()
_pg_sqlalchemy_mock.Vector = _SQLiteVector
_pg_mock = Mock()
_pg_mock.sqlalchemy = _pg_sqlalchemy_mock
sys.modules["pgvector"] = _pg_mock
sys.modules["pgvector.sqlalchemy"] = _pg_sqlalchemy_mock

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
from app.retrieval.embeddings import EmbeddingModel, get_embedding_model  # noqa: E402

app.dependency_overrides[get_db_session] = _override_get_db_session


def _get_mock_embedding_model() -> EmbeddingModel:
    """Return a mock EmbeddingModel that returns deterministic vectors without ONNX."""
    mock = Mock(spec=EmbeddingModel)
    mock.embed = AsyncMock(return_value=[0.01] * 384)
    return mock


app.dependency_overrides[get_embedding_model] = _get_mock_embedding_model


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Return an async HTTP client for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
