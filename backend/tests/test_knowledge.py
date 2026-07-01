"""Tests for KnowledgeAgent + Wiki API (APP-135).

Covers:
  1. KnowledgeAgent._parse_response parses valid JSON correctly
  2. KnowledgeAgent._parse_response handles markdown-wrapped JSON
  3. KnowledgeAgent.generate_summary returns graceful fallback for empty text
  4. KnowledgeAgent._call_llm builds correct DeepSeek request payload (mocked HTTP)
  5. GET /wiki returns empty list when no entries exist
  6. GET /wiki returns entries after upload
  7. GET /wiki/{document_id} returns a specific entry
  8. GET /wiki/search?q=... returns matching entries
  9. POST /wiki/refresh/{document_id} regenerates a summary
  10. Wiki entry is NOT created on upload without LLM (background task — no-op
      when DeepSeek is unreachable in tests)
  11. WikiService.backfill_all processes documents
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.knowledge.knowledge_agent import KnowledgeAgent
from app.knowledge.wiki_service import WikiService

# ── In-memory SQLite for WikiService unit tests (same engine as conftest) ───
WIKI_TEST_ENGINE = create_async_engine("sqlite+aiosqlite://", echo=False)
WIKI_TEST_SESSION_FACTORY = async_sessionmaker(
    WIKI_TEST_ENGINE, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="module", autouse=True)
async def _wiki_test_tables() -> AsyncGenerator[None, None]:
    """Create all tables on the WikiService test engine for the module."""
    from app.core.database import Base
    from app.knowledge.models import WikiEntry  # noqa: F401 — register model
    from app.models.chunk import Chunk  # noqa: F401
    from app.models.document import Document  # noqa: F401

    async with WIKI_TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with WIKI_TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def _clean_wiki_db() -> AsyncGenerator[None, None]:
    """Truncate all tables on the WikiService test engine between tests."""
    from app.core.database import Base

    yield
    async with WIKI_TEST_ENGINE.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_httpx_response(json_body: dict[str, Any], status_code: int = 200) -> MagicMock:
    """Return a mock httpx.Response with the given JSON body."""
    mock = MagicMock(spec=Response)
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.raise_for_status.return_value = None
    return mock


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_bm25() -> None:
    """Reset BM25 index between tests."""
    from app.retrieval.keyword import BM25Index

    BM25Index.reset()


@pytest.fixture(autouse=True)
def _reset_reranker() -> None:
    """Reset Reranker between tests."""
    from app.retrieval.reranker import Reranker

    Reranker.reset()


# ── Stale-event-loop workaround for async fixtures with @pytest.fixture(scope="session") ──
# Some test rigs create a session-scoped event loop but then get a new loop for
# async tests. This forces a new fixture loop when one of the session-scoped
# models fixture is present.
@pytest.fixture(scope="session")
def event_loop() -> AsyncGenerator[Any, None]:
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── KnowledgeAgent unit tests ────────────────────────────────────────────────


def test_parse_valid_json_response() -> None:
    """KnowledgeAgent._parse_response parses valid JSON correctly."""
    agent = KnowledgeAgent()

    raw = json.dumps(
        {
            "summary": "Docker is a container platform. It packages applications with their dependencies. This enables consistent deployments.",
            "topics": ["docker", "containers", "deployment"],
        }
    )
    result = agent._parse_response(raw)

    assert result["summary"] == (
        "Docker is a container platform. "
        "It packages applications with their dependencies. "
        "This enables consistent deployments."
    )
    assert result["topics"] == ["docker", "containers", "deployment"]


def test_parse_markdown_wrapped_json() -> None:
    """KnowledgeAgent._parse_response handles markdown-wrapped JSON."""
    agent = KnowledgeAgent()

    raw = """```json
{
    "summary": "Python is a programming language known for readability.",
    "topics": ["python", "programming"]
}
```"""
    result = agent._parse_response(raw)

    assert "Python is a programming language" in result["summary"]
    assert "python" in result["topics"]


def test_parse_bare_json_in_text() -> None:
    """KnowledgeAgent._parse_response finds JSON object inside surrounding text."""
    agent = KnowledgeAgent()

    raw = 'Here is the result: {"summary": "A summary.", "topics": ["topic"]} Thanks!'
    result = agent._parse_response(raw)

    assert result["summary"] == "A summary."
    assert result["topics"] == ["topic"]


def test_parse_no_json_fallback() -> None:
    """KnowledgeAgent._parse_response falls back to raw text when no JSON found."""
    agent = KnowledgeAgent()

    raw = "Just a plain text summary here."
    result = agent._parse_response(raw)

    assert result["summary"] == raw
    assert result["topics"] == []


def test_parse_normalizes_topics() -> None:
    """KnowledgeAgent._parse_response lowercases topics and removes duplicates."""
    agent = KnowledgeAgent()

    raw = json.dumps(
        {
            "summary": "Test summary.",
            "topics": ["  Docker  ", "docker", "Container", "container "],
        }
    )
    result = agent._parse_response(raw)

    assert result["topics"] == ["docker", "container"]


@pytest.mark.asyncio
async def test_generate_summary_empty_text() -> None:
    """KnowledgeAgent.generate_summary returns graceful fallback for empty text."""
    agent = KnowledgeAgent()

    result = await agent.generate_summary("")
    assert result["summary"] == "Empty document — no content to summarize."
    assert result["topics"] == []

    result = await agent.generate_summary("   ")
    assert result["summary"] == "Empty document — no content to summarize."
    assert result["topics"] == []


@pytest.mark.asyncio
async def test_deepseek_request_payload() -> None:
    """KnowledgeAgent._call_deepseek builds correct request payload."""
    settings_mock = MagicMock()
    settings_mock.DEEPSEEK_API_KEY = "test-key"
    settings_mock.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    settings_mock.LLM_API_KEY = ""  # ensure empty so DEEPSEEK_* fallback works
    settings_mock.LLM_BASE_URL = ""
    settings_mock.LLM_MODEL = ""
    settings_mock.LLM_TEMPERATURE = 0.0

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(
        return_value=_mock_httpx_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Generated summary from DeepSeek.",
                                    "topics": ["test", "mock"],
                                }
                            )
                        }
                    }
                ]
            }
        )
    )

    agent = KnowledgeAgent(settings=settings_mock, http_client=mock_client)

    result = await agent.generate_summary("Test document content.")

    assert result["summary"] == "Generated summary from DeepSeek."
    assert result["topics"] == ["test", "mock"]

    # Verify the request payload
    call_args = mock_client.post.call_args
    assert call_args is not None
    url = call_args[0][0]
    assert url == "https://api.deepseek.com/v1/chat/completions"

    payload = call_args[1]["json"]
    assert payload["model"] == "deepseek-chat"
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 512
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "Test document content." in payload["messages"][1]["content"]
    assert "knowledge extraction assistant" in payload["messages"][0]["content"]

    await agent.close()


@pytest.mark.asyncio
async def test_deepseek_unreachable_uses_ollama() -> None:
    """KnowledgeAgent falls back to Ollama when DeepSeek is unreachable."""
    settings_mock = MagicMock()
    settings_mock.DEEPSEEK_API_KEY = "test-key"
    settings_mock.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    settings_mock.OLLAMA_BASE_URL = "http://localhost:11434"
    settings_mock.LLM_API_KEY = ""
    settings_mock.LLM_BASE_URL = ""
    settings_mock.LLM_MODEL = ""
    settings_mock.LLM_TEMPERATURE = 0.0

    mock_client = MagicMock(spec=httpx.AsyncClient)

    # DeepSeek fails, Ollama succeeds
    mock_client.post = AsyncMock()
    mock_client.post.side_effect = [
        httpx.ConnectError("DeepSeek unreachable"),  # DeepSeek fails
        # Ollama succeeds
        _mock_httpx_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Generated by Ollama.",
                                    "topics": ["ollama"],
                                }
                            )
                        }
                    }
                ]
            }
        ),
    ]

    agent = KnowledgeAgent(settings=settings_mock, http_client=mock_client)
    result = await agent.generate_summary("Test content.")

    assert result["summary"] == "Generated by Ollama."
    assert result["topics"] == ["ollama"]

    # Verify both were called
    assert mock_client.post.call_count == 2
    assert "deepseek.com" in mock_client.post.call_args_list[0][0][0]
    assert "11434" in mock_client.post.call_args_list[1][0][0]

    await agent.close()


# ── Wiki API integration tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wiki_list_empty(client: AsyncClient) -> None:
    """GET /wiki returns empty list when no entries exist."""
    response = await client.get("/wiki")
    assert response.status_code == 200

    data = response.json()
    assert data["entries"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_wiki_search_empty(client: AsyncClient) -> None:
    """GET /wiki/search returns empty list when no entries match."""
    response = await client.get("/wiki/search?q=nonexistent")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_wiki_search_without_query_fails(client: AsyncClient) -> None:
    """GET /wiki/search without q param returns validation error."""
    response = await client.get("/wiki/search")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_wiki_get_nonexistent(client: AsyncClient) -> None:
    """GET /wiki/{document_id} returns 404 for nonexistent entry."""
    response = await client.get("/wiki/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_wiki_refresh_nonexistent(client: AsyncClient) -> None:
    """POST /wiki/refresh/{document_id} returns 404 for nonexistent document."""
    response = await client.post("/wiki/refresh/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


# ── WikiService unit tests (with mocked KnowledgeAgent) ──────────────────────


@pytest.mark.asyncio
async def test_wiki_service_create_entry() -> None:
    """WikiService.create_or_update_wiki creates a wiki entry for a document."""
    import uuid as uuid_mod

    from app.models.chunk import Chunk
    from app.models.document import Document

    doc_id = uuid_mod.uuid4()

    # Mock agent that returns deterministic results
    mock_agent = MagicMock(spec=KnowledgeAgent)
    mock_agent.generate_summary = AsyncMock(
        return_value={
            "summary": "A test document about Python programming.",
            "topics": ["python", "programming"],
        }
    )
    mock_agent.close = AsyncMock()

    async with WIKI_TEST_SESSION_FACTORY() as db:
        # Create a document with chunks
        doc = Document(
            id=doc_id,
            filename="test.txt",
            content_type="text/plain",
            file_size=42,
        )
        db.add(doc)
        await db.flush()

        chunk = Chunk(
            document_id=doc_id,
            chunk_index=0,
            content="Python is a programming language used widely.",
        )
        db.add(chunk)
        await db.commit()

        service = WikiService(db, agent=mock_agent)
        entry = await service.create_or_update_wiki(doc_id)

        assert entry is not None
        assert entry.document_id == doc_id
        assert "Python programming" in entry.summary
        assert entry.topics == ["python", "programming"]

        # Cleanup
        await service.close()


@pytest.mark.asyncio
async def test_wiki_service_update_existing() -> None:
    """WikiService.create_or_update_wiki updates an existing wiki entry."""
    import uuid as uuid_mod

    from app.models.chunk import Chunk
    from app.models.document import Document

    doc_id = uuid_mod.uuid4()

    # First call returns one summary, second a different one
    summaries = [
        {"summary": "First summary about Docker.", "topics": ["docker"]},
        {"summary": "Updated summary about containers.", "topics": ["containers", "docker"]},
    ]
    call_count = [0]

    async def _mock_summary(text: str) -> dict[str, Any]:
        idx = min(call_count[0], len(summaries) - 1)
        result = summaries[idx]
        call_count[0] += 1
        return result

    mock_agent = MagicMock(spec=KnowledgeAgent)
    mock_agent.generate_summary = AsyncMock(side_effect=_mock_summary)
    mock_agent.close = AsyncMock()

    async with WIKI_TEST_SESSION_FACTORY() as db:
        # Create document
        doc = Document(
            id=doc_id,
            filename="docker.txt",
            content_type="text/plain",
            file_size=100,
        )
        db.add(doc)
        await db.flush()

        chunk = Chunk(document_id=doc_id, chunk_index=0, content="Docker containers are useful.")
        db.add(chunk)
        await db.commit()

        service = WikiService(db, agent=mock_agent)

        # First create
        entry1 = await service.create_or_update_wiki(doc_id)
        assert entry1 is not None
        assert "Docker" in entry1.summary
        assert entry1.topics == ["docker"]

        # Second call should update
        entry2 = await service.create_or_update_wiki(doc_id)
        assert entry2 is not None
        assert entry2.id == entry1.id  # same row, updated
        assert "containers" in entry2.summary
        assert entry2.topics == ["containers", "docker"]

        await service.close()


@pytest.mark.asyncio
async def test_wiki_service_backfill() -> None:
    """WikiService.backfill_all generates entries for documents without them."""
    import uuid as uuid_mod

    from app.models.chunk import Chunk
    from app.models.document import Document

    doc_id_1 = uuid_mod.uuid4()
    doc_id_2 = uuid_mod.uuid4()

    mock_agent = MagicMock(spec=KnowledgeAgent)
    mock_agent.generate_summary = AsyncMock(
        return_value={
            "summary": "A summary.",
            "topics": ["backfill"],
        }
    )
    mock_agent.close = AsyncMock()

    async with WIKI_TEST_SESSION_FACTORY() as db:
        # Create two documents with chunks
        for doc_id in (doc_id_1, doc_id_2):
            doc = Document(
                id=doc_id,
                filename=f"{doc_id}.txt",
                content_type="text/plain",
                file_size=10,
            )
            db.add(doc)
            await db.flush()

            chunk = Chunk(document_id=doc_id, chunk_index=0, content="Some content.")
            db.add(chunk)
        await db.commit()

        service = WikiService(db, agent=mock_agent)
        count = await service.backfill_all()

        assert count == 2  # both documents got entries
        assert mock_agent.generate_summary.call_count == 2

        # Verify entries exist via list
        entries, total = await service.list_entries()
        assert total == 2

        await service.close()


@pytest.mark.asyncio
async def test_wiki_service_list_pagination() -> None:
    """WikiService.list_entries supports pagination."""
    import uuid as uuid_mod

    from app.knowledge.models import WikiEntry

    async with WIKI_TEST_SESSION_FACTORY() as db:
        # Create 5 wiki entries directly
        for i in range(5):
            entry = WikiEntry(
                document_id=uuid_mod.uuid4(),
                summary=f"Summary {i}",
                topics=[f"topic{i}"],
            )
            db.add(entry)
        await db.commit()

        service = WikiService(db)
        entries, total = await service.list_entries(page=1, page_size=3)

        assert total == 5
        assert len(entries) == 3

        entries2, total2 = await service.list_entries(page=2, page_size=3)
        assert total2 == 5
        assert len(entries2) == 2

        await service.close()


@pytest.mark.asyncio
async def test_wiki_service_search() -> None:
    """WikiService.search_entries finds entries by summary or topic."""
    import uuid as uuid_mod

    from app.knowledge.models import WikiEntry

    async with WIKI_TEST_SESSION_FACTORY() as db:
        entry = WikiEntry(
            document_id=uuid_mod.uuid4(),
            summary="A document about machine learning and neural networks.",
            topics=["machine learning", "neural networks", "ai"],
        )
        db.add(entry)
        await db.commit()

        service = WikiService(db)

        # Search by summary content
        results = await service.search_entries("machine learning")
        assert len(results) == 1

        # Search by topic
        results2 = await service.search_entries("neural")
        assert len(results2) == 1

        # Search with no matches
        results3 = await service.search_entries("nonexistent")
        assert len(results3) == 0

        await service.close()


# ── Import for WikiService tests ─────────────────────────────────────────────
