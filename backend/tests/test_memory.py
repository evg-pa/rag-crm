"""Tests for Memory System — Working, Episodic, Semantic, Procedural (Iteration 9).

Covers: WorkingMemory, EpisodicMemory, SemanticMemory, ProceduralMemory services + API.
Runs with in-memory SQLite; no external dependencies.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

# ── Mock pgvector BEFORE app imports ──────────────────────────────────────────


class _SQLiteVector(sa.types.UserDefinedType):
    """SQLite-compatible Vector type (replaces pgvector for tests).

    Converts Python list[float] <-> bytes (float32 LE) for storage.
    """

    def __init__(self, dim: int | None = None):
        super().__init__()
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return "BLOB"

    def bind_processor(self, dialect):
        """Convert list[float] to bytes for SQLite binding."""
        def process(value):
            if value is None:
                return None
            if isinstance(value, bytes):
                return value
            # list[float] -> float32 LE bytes
            import struct
            return struct.pack(f"<{len(value)}f", *value)
        return process

    def result_processor(self, dialect, coltype):
        """Convert bytes back to list[float]."""
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            # bytes -> list[float]
            import struct
            return list(struct.unpack(f"<{len(value) // 4}f", value))
        return process


_pg_sqlalchemy_mock = Mock()
_pg_sqlalchemy_mock.Vector = _SQLiteVector
_pg_mock = Mock()
_pg_mock.sqlalchemy = _pg_sqlalchemy_mock
sys.modules["pgvector"] = _pg_mock
sys.modules["pgvector.sqlalchemy"] = _pg_sqlalchemy_mock

# Mock PostgreSQL JSONB for SQLite
from sqlalchemy import JSON as _SA_JSON

_sa_mock = Mock()
_sa_mock.JSONB = _SA_JSON
sys.modules["sqlalchemy.dialects.postgresql"] = _sa_mock

# ── Force SQLite BEFORE imports ──────────────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

from app.core.database import Base
from app.main import app
from app.memory.models import EMBEDDING_DIM
from app.memory.service import (
    EpisodicMemoryService,
    ProceduralMemoryService,
    SemanticMemoryService,
    WorkingMemoryService,
)

# Reuse conftest's in-memory engine so tables are shared
from tests.conftest import TEST_ENGINE, TEST_SESSION_FACTORY

pytestmark = pytest.mark.asyncio(loop_scope="function")


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _setup_db():
    """Create all tables."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _teardown_db():
    """Drop all tables and dispose engine."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await TEST_ENGINE.dispose()


async def _clean_tables():
    """Delete all rows across all tables."""
    async with TEST_ENGINE.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


async def _get_db():
    """Yield a fresh DB session."""
    async with TEST_SESSION_FACTORY() as session:
        yield session


# ═══════════════════════════════════════════════════════════════════════════
#  Working Memory
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkingMemory:
    async def test_add_and_retrieve(self):
        await _setup_db()
        async for db in _get_db():
            svc = WorkingMemoryService(db)
            await svc.add_message("s1", "user", "Hello")
            h = await svc.get_history("s1")
            assert len(h) == 1 and h[0]["content"] == "Hello"
        await _clean_tables()

    async def test_prune(self):
        await _setup_db()
        async for db in _get_db():
            svc = WorkingMemoryService(db)
            for i in range(13):
                await svc.add_message("s1", "user", f"msg-{i}")
            h = await svc.get_history("s1")
            assert len(h) == 10
            assert h[0]["content"] == "msg-3"
        await _clean_tables()

    async def test_clear(self):
        await _setup_db()
        async for db in _get_db():
            svc = WorkingMemoryService(db)
            await svc.add_message("s1", "user", "Q1")
            await svc.add_message("s2", "user", "Q2")
            assert await svc.clear_session("s1") == 1
            assert len(await svc.get_history("s1")) == 0
            assert len(await svc.get_history("s2")) == 1
        await _clean_tables()


# ═══════════════════════════════════════════════════════════════════════════
#  Episodic Memory
# ═══════════════════════════════════════════════════════════════════════════


class TestEpisodicMemory:
    async def test_create_and_read(self):
        await _setup_db()
        async for db in _get_db():
            svc = EpisodicMemoryService(db)
            e = await svc.create_or_update("s1", "Summary", ["a"], 3)
            assert e.summary == "Summary"
            fetched = await svc.get_by_session("s1")
            assert fetched is not None
        await _clean_tables()

    async def test_update(self):
        await _setup_db()
        async for db in _get_db():
            svc = EpisodicMemoryService(db)
            await svc.create_or_update("s1", "Old", ["a"], 3)
            e = await svc.create_or_update("s1", "New", ["a", "b"], 5)
            assert e.summary == "New" and len(e.topics) == 2
        await _clean_tables()

    async def test_not_found(self):
        await _setup_db()
        async for db in _get_db():
            svc = EpisodicMemoryService(db)
            assert await svc.get_by_session("nope") is None
        await _clean_tables()


# ═══════════════════════════════════════════════════════════════════════════
#  Semantic Memory
# ═══════════════════════════════════════════════════════════════════════════


class TestSemanticMemory:
    @patch("app.memory.service.get_embedding_model")
    async def test_add_fact(self, m):
        m.return_value = Mock(embed=AsyncMock(return_value=[0.01] * EMBEDDING_DIM))
        await _setup_db()
        async for db in _get_db():
            svc = SemanticMemoryService(db)
            e = await svc.add_fact("RAG rocks", confidence=0.9)
            assert "RAG" in e.fact
        await _clean_tables()

    @patch("app.memory.service.get_embedding_model")
    async def test_search(self, m):
        m.return_value = Mock(embed=AsyncMock(return_value=[0.01] * EMBEDDING_DIM))
        await _setup_db()
        async for db in _get_db():
            svc = SemanticMemoryService(db)
            await svc.add_fact("Fact about AI", confidence=0.9)
            r = await svc.search_similar("AI", limit=5)
            assert len(r) >= 1
        await _clean_tables()


# ═══════════════════════════════════════════════════════════════════════════
#  Procedural Memory
# ═══════════════════════════════════════════════════════════════════════════


class TestProceduralMemory:
    async def test_crud(self):
        await _setup_db()
        async for db in _get_db():
            svc = ProceduralMemoryService(db)
            e = await svc.create("test-proc", "Do X", tags=["test"])
            assert e.name == "test-proc"
            assert await svc.get_by_name("nope") is None

            await svc.increment_usage("test-proc")
            e2 = await svc.get_by_name("test-proc")
            assert e2 and e2.usage_count == 1
        await _clean_tables()

    async def test_list_ordered(self):
        await _setup_db()
        async for db in _get_db():
            svc = ProceduralMemoryService(db)
            await svc.create("a", "A")
            await svc.create("b", "B")
            await svc.create("c", "C")
            await svc.increment_usage("c")
            await svc.increment_usage("c")
            await svc.increment_usage("b")
            entries = await svc.list_all()
            assert entries[0].name == "c"
            assert entries[1].name == "b"
            assert entries[2].name == "a"
        await _clean_tables()


# ═══════════════════════════════════════════════════════════════════════════
#  HTTP API
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryAPI:
    @pytest.fixture(autouse=True)
    def _patch_app(self):
        from app.core.dependencies import get_db_session

        async def _test_db():
            async with TEST_SESSION_FACTORY() as s:
                yield s

        _prev = app.dependency_overrides.get(get_db_session)
        app.dependency_overrides[get_db_session] = _test_db
        yield
        # Restore the previous override (don't clear() — that removes conftest's override)
        if _prev is not None:
            app.dependency_overrides[get_db_session] = _prev
        else:
            app.dependency_overrides.pop(get_db_session, None)

    async def test_working_empty(self):
        await _setup_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/memory/working/x")
            assert r.status_code == 200 and r.json() == []
        await _clean_tables()

    async def test_semantic_add(self):
        await _setup_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            with patch(
                "app.memory.service.get_embedding_model",
                return_value=Mock(embed=AsyncMock(return_value=[0.01] * EMBEDDING_DIM)),
            ):
                r = await ac.post(
                    "/memory/semantic",
                    params={"fact": "PG is relational", "source": "test"},
                )
                assert r.status_code == 200
                assert r.json()["fact"] == "PG is relational"
        await _clean_tables()

    async def test_procedural_crud(self):
        await _setup_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/memory/procedural",
                params={"name": "dep", "content": "1. Test"},
            )
            assert r.status_code == 200 and r.json()["name"] == "dep"
            r2 = await ac.get("/memory/procedural/dep")
            assert r2.status_code == 200 and "Test" in r2.json()["content"]
        await _clean_tables()

    async def test_episodic_404(self):
        await _setup_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/memory/episodic/nope")
            assert r.status_code == 404
        await _clean_tables()

    async def test_teardown(self):
        """Clean up at module end."""
        await _teardown_db()
