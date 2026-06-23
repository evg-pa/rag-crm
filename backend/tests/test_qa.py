"""Tests for Q&A service and endpoint (APP-124).

Covers:
  1. AnswerAgent._parse_llm_response parses valid JSON correctly
  2. AnswerAgent._parse_llm_response handles markdown-wrapped JSON
  3. AnswerAgent.answer with empty chunks returns graceful empty response
  4. AnswerAgent._call_llm builds correct DeepSeek request payload (mocked HTTP)
  5. POST /qa endpoint returns AnswerResult when all dependencies mocked
  6. GET /qa/history returns stub empty list
  7. POST /qa with empty query returns 422 validation error
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.retrieval.qa import (
    AnswerAgent,
    AnswerResult,
    Citation,
    build_context_prompt,
)

# ── Test data ────────────────────────────────────────────────────────────────

SAMPLE_CHUNKS: list[dict[str, Any]] = [
    {
        "id": "chunk-001",
        "content": "RAG (Retrieval-Augmented Generation) combines retrieval and generation.",
        "document_id": "doc-a",
        "chunk_index": 0,
    },
    {
        "id": "chunk-002",
        "content": "Docker is a container platform for packaging applications.",
        "document_id": "doc-b",
        "chunk_index": 1,
    },
    {
        "id": "chunk-003",
        "content": "Python is a programming language known for readability.",
        "document_id": "doc-a",
        "chunk_index": 2,
    },
]

SAMPLE_LLM_JSON_RESPONSE = {
    "answer_text": "RAG combines retrieval with text generation for accurate answers.",
    "citations": [
        {
            "chunk_id": "chunk-001",
            "document_id": "doc-a",
            "content_snippet": "RAG combines retrieval and generation",
        }
    ],
    "confidence_score": 0.85,
}


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


@pytest.fixture
def mock_embedding_model() -> MagicMock:
    """Return a mock EmbeddingModel that returns a deterministic 384-d vector."""
    from app.retrieval.embeddings import EmbeddingModel

    mock = MagicMock(spec=EmbeddingModel)
    mock.embed = AsyncMock(return_value=[0.01] * 384)
    return mock


@pytest.fixture
async def qa_client(
    mock_embedding_model: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTP client with embedding, BM25, and reranker mocked."""
    from app.main import app
    from app.retrieval.embeddings import get_embedding_model
    from app.retrieval.keyword import BM25Index
    from app.retrieval.reranker import Reranker

    # Save the existing override so we can restore it after the test
    _prev_embedding_override = app.dependency_overrides.get(get_embedding_model)
    app.dependency_overrides[get_embedding_model] = lambda: mock_embedding_model

    with (
        patch.object(BM25Index, "search", new_callable=AsyncMock) as mock_bm25,
        patch.object(BM25Index, "_ensure_loaded", new_callable=AsyncMock) as mock_ensure,
    ):
        mock_bm25.return_value = [
            {
                "id": "chunk-001",
                "content": "RAG combines retrieval and generation.",
                "document_id": "doc-a",
                "chunk_index": 0,
                "bm25_score": 2.5,
            },
        ]
        mock_ensure.return_value = None

        # Mock reranker to return identity
        original_rerank = Reranker.rerank

        async def fake_rerank(
            self: Reranker,
            query: str,
            candidates: list[dict[str, Any]],
            top_k: int = 10,
        ) -> list[dict[str, Any]]:
            return [
                {**c, "reranker_score": 1.0 - i * 0.01}
                for i, c in enumerate(candidates[:top_k])
            ]

        Reranker.rerank = fake_rerank  # type: ignore[method-assign]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        Reranker.rerank = original_rerank  # type: ignore[method-assign]

    # Restore the previous embedding model override (or remove if there was none)
    if _prev_embedding_override is not None:
        app.dependency_overrides[get_embedding_model] = _prev_embedding_override
    else:
        app.dependency_overrides.pop(get_embedding_model, None)


# ── Unit tests: build_context_prompt ─────────────────────────────────────────


class TestBuildContextPrompt:
    """Tests for build_context_prompt helper."""

    def test_builds_prompt_from_chunks(self) -> None:
        """Context prompt includes chunk IDs, document IDs, and content."""
        prompt = build_context_prompt(SAMPLE_CHUNKS)
        assert "chunk-001" in prompt
        assert "doc-a" in prompt
        assert "RAG" in prompt
        assert "[Chunk 1]" in prompt
        assert "[Chunk 2]" in prompt
        assert "[Chunk 3]" in prompt

    def test_empty_chunks_returns_placeholder(self) -> None:
        """Empty chunk list returns a 'no context' message."""
        prompt = build_context_prompt([])
        assert "No relevant context chunks" in prompt

    def test_single_chunk(self) -> None:
        """Single chunk produces a single chunk entry."""
        prompt = build_context_prompt([SAMPLE_CHUNKS[0]])
        assert "[Chunk 1]" in prompt
        assert "[Chunk 2]" not in prompt


# ── Unit tests: AnswerAgent._parse_llm_response ─────────────────────────────


class TestParseLLMResponse:
    """Tests for AnswerAgent._parse_llm_response."""

    def test_parses_valid_json(self) -> None:
        """Valid JSON response is parsed into AnswerResult with citations."""
        agent = AnswerAgent()
        raw = json.dumps(SAMPLE_LLM_JSON_RESPONSE)

        result = agent._parse_llm_response(raw, SAMPLE_CHUNKS)

        assert isinstance(result, AnswerResult)
        assert result.answer_text == SAMPLE_LLM_JSON_RESPONSE["answer_text"]
        assert len(result.citations) == 1
        assert result.citations[0].chunk_id == "chunk-001"
        assert result.citations[0].document_id == "doc-a"
        assert result.confidence_score == 0.85

    def test_parses_markdown_wrapped_json(self) -> None:
        """JSON inside markdown code fences is parsed correctly."""
        raw = f"```json\n{json.dumps(SAMPLE_LLM_JSON_RESPONSE)}\n```"

        agent = AnswerAgent()
        result = agent._parse_llm_response(raw, SAMPLE_CHUNKS)

        assert result.answer_text == SAMPLE_LLM_JSON_RESPONSE["answer_text"]
        assert len(result.citations) == 1

    def test_handles_bare_json_with_surrounding_text(self) -> None:
        """JSON with extra text before/after (no fences) still parses."""
        raw = f"Here is the answer:\n{json.dumps(SAMPLE_LLM_JSON_RESPONSE)}\nHope that helps!"

        agent = AnswerAgent()
        result = agent._parse_llm_response(raw, SAMPLE_CHUNKS)

        assert result.answer_text == SAMPLE_LLM_JSON_RESPONSE["answer_text"]
        assert len(result.citations) == 1

    def test_handles_invalid_json_fallback(self) -> None:
        """Completely invalid JSON falls back to raw text answer."""
        raw = "I'm sorry, I cannot answer that question."

        agent = AnswerAgent()
        result = agent._parse_llm_response(raw, SAMPLE_CHUNKS)

        assert result.answer_text == "I'm sorry, I cannot answer that question."
        assert result.citations == []
        assert result.confidence_score == 0.5

    def test_handles_empty_response(self) -> None:
        """Empty string falls back gracefully."""
        agent = AnswerAgent()
        result = agent._parse_llm_response("", SAMPLE_CHUNKS)

        assert result.answer_text == ""
        assert result.citations == []
        # Empty string has no braces → fallback path → score 0.5
        assert result.confidence_score == 0.5

    def test_handles_missing_keys_in_json(self) -> None:
        """JSON with missing keys uses defaults."""
        raw = json.dumps({"answer_text": "Partial response"})

        agent = AnswerAgent()
        result = agent._parse_llm_response(raw, SAMPLE_CHUNKS)

        assert result.answer_text == "Partial response"
        assert result.citations == []
        assert result.confidence_score == 0.5


# ── Unit tests: AnswerAgent.answer with empty/mocked LLM ────────────────────


class TestAnswerAgentAnswer:
    """Tests for AnswerAgent.answer method."""

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_graceful_response(self) -> None:
        """No chunks → graceful empty AnswerResult without calling LLM."""
        mock_client = MagicMock(spec=AsyncClient)
        mock_client.post = AsyncMock()  # should not be called

        agent = AnswerAgent(http_client=mock_client)

        result = await agent.answer(query="What is RAG?", chunks=[], top_k=10)

        assert result.answer_text == "No relevant information found to answer your question."
        assert result.citations == []
        assert result.confidence_score == 0.0
        # LLM should NOT have been called
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_is_called_with_context(self) -> None:
        """LLM is called with a prompt containing the chunk context."""
        mock_client = MagicMock(spec=AsyncClient)
        mock_response = _mock_httpx_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(SAMPLE_LLM_JSON_RESPONSE),
                        }
                    }
                ]
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        settings = MagicMock()
        settings.DEEPSEEK_API_KEY = "sk-test-key"
        settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
        settings.OLLAMA_BASE_URL = "http://localhost:11434"
        settings.LLM_TEMPERATURE = 0.0

        agent = AnswerAgent(settings=settings, http_client=mock_client)

        result = await agent.answer(query="What is RAG?", chunks=SAMPLE_CHUNKS, top_k=10)

        assert result.answer_text == SAMPLE_LLM_JSON_RESPONSE["answer_text"]
        assert len(result.citations) == 1

        # Verify the LLM was called with correct URL and payload
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args is not None
        url = call_args[0][0]
        assert "api.deepseek.com" in url

        payload = call_args[1]["json"]
        assert payload["model"] == "deepseek-chat"
        messages = payload["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "What is RAG?" in messages[1]["content"]
        # Context from chunks should be in the user message
        assert "chunk-001" in messages[1]["content"]
        assert "RAG" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_falls_back_to_ollama_when_no_deepseek_key(self) -> None:
        """When DEEPSEEK_API_KEY is empty, Ollama is called instead."""
        mock_client = MagicMock(spec=AsyncClient)
        mock_response = _mock_httpx_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(SAMPLE_LLM_JSON_RESPONSE),
                        }
                    }
                ]
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        settings = MagicMock()
        settings.DEEPSEEK_API_KEY = ""  # empty → fallback to Ollama
        settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
        settings.OLLAMA_BASE_URL = "http://localhost:11434"
        settings.LLM_TEMPERATURE = 0.0

        agent = AnswerAgent(settings=settings, http_client=mock_client)

        result = await agent.answer(query="What is RAG?", chunks=SAMPLE_CHUNKS, top_k=10)

        assert result.answer_text == SAMPLE_LLM_JSON_RESPONSE["answer_text"]

        # Verify Ollama was called
        call_args = mock_client.post.call_args
        assert call_args is not None
        url = call_args[0][0]
        assert "localhost:11434" in url

        payload = call_args[1]["json"]
        assert payload["model"] == "llama3.2"
        assert payload["stream"] is False

    @pytest.mark.asyncio
    async def test_deepseek_failure_falls_back_to_ollama(self) -> None:
        """When DEEPSEEK_API_KEY is set but DeepSeek fails, Ollama is called as fallback."""
        mock_client = MagicMock(spec=AsyncClient)

        # First call (DeepSeek) raises, second call (Ollama) succeeds
        deepseek_fail = _mock_httpx_response({}, status_code=500)
        deepseek_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=deepseek_fail
        )
        ollama_ok = _mock_httpx_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(SAMPLE_LLM_JSON_RESPONSE),
                        }
                    }
                ]
            }
        )
        mock_client.post = AsyncMock(side_effect=[deepseek_fail, ollama_ok])

        settings = MagicMock()
        settings.DEEPSEEK_API_KEY = "sk-test-key"  # set → try DeepSeek
        settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
        settings.OLLAMA_BASE_URL = "http://localhost:11434"
        settings.LLM_TEMPERATURE = 0.0

        agent = AnswerAgent(settings=settings, http_client=mock_client)

        result = await agent.answer(query="What is RAG?", chunks=SAMPLE_CHUNKS, top_k=10)

        # Should still get a valid answer via Ollama
        assert result.answer_text == SAMPLE_LLM_JSON_RESPONSE["answer_text"]

        # Both DeepSeek and Ollama should have been called
        assert mock_client.post.call_count == 2
        calls = mock_client.post.call_args_list
        # First call → DeepSeek
        assert "api.deepseek.com" in calls[0][0][0]
        # Second call → Ollama
        assert "localhost:11434" in calls[1][0][0]
        assert calls[1][1]["json"]["model"] == "llama3.2"

    @pytest.mark.asyncio
    async def test_top_k_limits_chunks(self) -> None:
        """Only top_k chunks are used in the prompt."""
        mock_client = MagicMock(spec=AsyncClient)
        mock_response = _mock_httpx_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(SAMPLE_LLM_JSON_RESPONSE),
                        }
                    }
                ]
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        settings = MagicMock()
        settings.DEEPSEEK_API_KEY = "sk-test-key"
        settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
        settings.OLLAMA_BASE_URL = "http://localhost:11434"
        settings.LLM_TEMPERATURE = 0.0

        agent = AnswerAgent(settings=settings, http_client=mock_client)

        # Request only top_k=2 with 3 chunks available
        await agent.answer(query="What is RAG?", chunks=SAMPLE_CHUNKS, top_k=2)

        # Verify only 2 chunks appear in the prompt
        call_args = mock_client.post.call_args
        messages = call_args[1]["json"]["messages"]
        content = messages[1]["content"]
        assert "[Chunk 1]" in content
        assert "[Chunk 2]" in content
        assert "[Chunk 3]" not in content


# ── Integration tests: POST /qa endpoint ────────────────────────────────────


class TestQAEndpoint:
    """Integration tests for POST /qa."""

    @pytest.mark.asyncio
    async def test_qa_endpoint_returns_result(
        self, qa_client: AsyncClient
    ) -> None:
        """POST /qa with a query returns an AnswerResult (LLM call mocked)."""
        from app.retrieval.qa import AnswerAgent

        async def fake_answer(
            self_agent: AnswerAgent,
            query: str,
            chunks: list[dict[str, Any]],
            top_k: int = 10,
        ) -> AnswerResult:
            return AnswerResult(
                answer_text="RAG is a technique for augmenting LLM generation.",
                citations=[
                    Citation(
                        chunk_id="chunk-001",
                        document_id="doc-a",
                        content_snippet="RAG combines retrieval and generation",
                    )
                ],
                confidence_score=0.9,
            )

        with patch.object(AnswerAgent, "answer", fake_answer):
            response = await qa_client.post(
                "/qa", json={"query": "What is RAG?", "top_k": 10}
            )

        assert response.status_code == 200

        data = response.json()
        assert data["answer_text"] == "RAG is a technique for augmenting LLM generation."
        assert len(data["citations"]) == 1
        assert data["citations"][0]["chunk_id"] == "chunk-001"
        assert data["confidence_score"] == 0.9

    @pytest.mark.asyncio
    async def test_qa_endpoint_missing_query(self, qa_client: AsyncClient) -> None:
        """POST /qa without query returns 422."""
        response = await qa_client.post("/qa", json={"top_k": 10})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_qa_endpoint_empty_query(self, qa_client: AsyncClient) -> None:
        """POST /qa with empty query returns 422."""
        response = await qa_client.post("/qa", json={"query": "", "top_k": 10})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_qa_endpoint_default_top_k(self, qa_client: AsyncClient) -> None:
        """POST /qa without top_k uses default of 10."""
        from app.retrieval.qa import AnswerAgent

        async def fake_answer(
            self_agent: AnswerAgent,
            query: str,
            chunks: list[dict[str, Any]],
            top_k: int = 10,
        ) -> AnswerResult:
            return AnswerResult(
                answer_text="OK",
                citations=[],
                confidence_score=0.5,
            )

        with patch.object(AnswerAgent, "answer", fake_answer):
            response = await qa_client.post("/qa", json={"query": "What is RAG?"})

        assert response.status_code == 200


# ── Integration tests: GET /qa/history endpoint ─────────────────────────────


class TestQAHistoryEndpoint:
    """Tests for GET /qa/history."""

    @pytest.mark.asyncio
    async def test_history_returns_empty_list(self, client: AsyncClient) -> None:
        """GET /qa/history returns stub with empty items list."""
        response = await client.get("/qa/history")
        assert response.status_code == 200

        data = response.json()
        assert data == {"items": []}


# ── Model tests ─────────────────────────────────────────────────────────────


class TestAnswerResultModel:
    """Tests for AnswerResult and Citation Pydantic models."""

    def test_answer_result_defaults(self) -> None:
        """AnswerResult has sensible defaults."""
        result = AnswerResult(answer_text="test")
        assert result.answer_text == "test"
        assert result.citations == []
        assert result.confidence_score == 0.0

    def test_answer_result_with_citations(self) -> None:
        """AnswerResult serializes with citations."""
        result = AnswerResult(
            answer_text="RAG is great.",
            citations=[
                Citation(
                    chunk_id="c1",
                    document_id="d1",
                    content_snippet="RAG is a technique",
                )
            ],
            confidence_score=0.9,
        )
        data = result.model_dump()
        assert data["answer_text"] == "RAG is great."
        assert len(data["citations"]) == 1
        assert data["citations"][0]["chunk_id"] == "c1"
        assert data["confidence_score"] == 0.9


# ── Regression: existing routes still work ──────────────────────────────────


class TestExistingRoutesStillWork:
    """Verify existing endpoints are not broken by adding QA router."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient) -> None:
        """GET /health still returns 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_endpoint_registered(self, client: AsyncClient) -> None:
        """GET /search is still registered."""
        response = await client.get("/search?q=test")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_documents_endpoint_registered(self, client: AsyncClient) -> None:
        """GET /documents is still registered (returns 405 since list is POST)."""
        response = await client.get("/documents")
        # Either 405 (method not allowed) or 200 depending on router setup
        assert response.status_code in (200, 405)
