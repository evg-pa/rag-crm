"""Tests for the 7-agent LangGraph QA pipeline (APP-129).

Covers:
  1. RouterAgent classification (all 5 categories)
  2. CriticAgent validation (catches missing citations, unsupported claims)
  3. CriticAgent max-retry ceiling
  4. MemoryAgent stores/retrieves history per session
  5. SynthesizerAgent produces formatted responses
  6. Pipeline status endpoint
  7. POST /qa end-to-end with mocked retrieval
  8. POST /qa handles greetings gracefully
  9. POST /qa handles empty search results
 10. POST /qa with empty query returns 422
 11. GET /health still 200 (regression)
 12. All existing routes still work
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.router_agent import classify_query
from app.agents.critic_agent import (
    MAX_CRITIC_RETRIES,
    _has_citations,
    _claims_supported,
    critic_agent,
)
from app.agents.memory_agent import (
    clear_all as memory_clear_all,
    get_history as memory_get_history,
)
from app.agents.synthesizer_agent import synthesizer_agent
from app.agents.answer_agent import answer_agent as langgraph_answer_agent


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides: Any) -> dict[str, Any]:
    """Build a minimal AgentState dict with sensible defaults."""
    state: dict[str, Any] = {
        "query": "What is RAG?",
        "session_id": "test-session",
        "query_type": "hybrid",
        "retrieved_chunks": [],
        "reranked_chunks": [],
        "answer_text": "",
        "citations": [],
        "confidence_score": 0.0,
        "critic_passed": True,
        "critic_feedback": "",
        "critic_retries": 0,
        "history": [],
        "final_response": "",
        "agent_states": {},
        "error": "",
    }
    state.update(overrides)
    return state


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_memory() -> None:
    """Reset in-memory history before each test."""
    memory_clear_all()


@pytest.fixture
async def langgraph_client() -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTP client with all LangGraph dependencies mocked."""
    from app.main import app
    from app.retrieval.embeddings import get_embedding_model
    from app.retrieval.keyword import BM25Index
    from app.retrieval.reranker import Reranker
    from app.retrieval.qa import AnswerAgent

    # Save the existing override so we can restore it after the test
    _prev_embedding_override = app.dependency_overrides.get(get_embedding_model)
    # Mock embedding model
    mock_emb = MagicMock()
    mock_emb.embed = AsyncMock(return_value=[0.01] * 384)

    app.dependency_overrides[get_embedding_model] = lambda: mock_emb

    with (
        patch.object(BM25Index, "search", new_callable=AsyncMock) as mock_bm25,
        patch.object(BM25Index, "_ensure_loaded", new_callable=AsyncMock) as mock_ensure,
        patch.object(AnswerAgent, "answer", new_callable=AsyncMock) as mock_answer,
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

        mock_answer.return_value = MagicMock(
            answer_text="RAG is a technique for augmenting LLM generation with retrieved documents.",
            citations=[
                MagicMock(
                    chunk_id="chunk-001",
                    document_id="doc-a",
                    content_snippet="RAG combines retrieval and generation",
                )
            ],
            confidence_score=0.9,
        )

        # Mock reranker to return identity with score
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


# ── RouterAgent tests ───────────────────────────────────────────────────────


class TestRouterClassification:
    """Tests for the RouterAgent query classifier."""

    def test_classifies_greetings(self) -> None:
        """Simple greetings are classified as 'greeting'."""
        assert classify_query("hi") == "greeting"
        assert classify_query("Hello") == "greeting"
        assert classify_query("thanks") == "greeting"
        assert classify_query("bye") == "greeting"
        assert classify_query("") == "greeting"

    def test_classifies_irrelevant(self) -> None:
        """Gibberish / keyboard mashing is classified as 'irrelevant'."""
        assert classify_query("asdf") == "irrelevant"
        assert classify_query("foo") == "irrelevant"
        assert classify_query("a") == "irrelevant"

    def test_classifies_semantic(self) -> None:
        """Queries with semantic indicators are classified as 'semantic'."""
        assert classify_query("Why is RAG important?") == "semantic"
        assert classify_query("compare Docker and Kubernetes") == "semantic"
        assert classify_query("explain how vector search works") == "semantic"

    def test_classifies_keyword(self) -> None:
        """Queries with keyword indicators are classified as 'keyword'."""
        assert classify_query("define: retrieval augmented generation") == "keyword"
        assert classify_query("what is the meaning of embedding?") == "keyword"

    def test_classifies_default_to_hybrid(self) -> None:
        """Ambiguous queries default to hybrid."""
        assert classify_query("Docker containers performance") == "hybrid"


# ── CriticAgent unit tests ──────────────────────────────────────────────────


class TestCriticChecks:
    """Tests for the individual critic check functions."""

    def test_has_citations_with_empty(self) -> None:
        """Empty citations list fails the check."""
        assert _has_citations([]) is False

    def test_has_citations_with_items(self) -> None:
        """Non-empty citations list passes the check."""
        assert _has_citations([{"chunk_id": "c1"}]) is True

    def test_claims_supported_empty_answer(self) -> None:
        """Empty answer fails claim support check."""
        passed, ratio = _claims_supported("", [{"content": "RAG is great"}])
        assert passed is False
        assert ratio == 0.0

    def test_claims_supported_no_chunks(self) -> None:
        """Empty chunks returns False (can't validate without context)."""
        passed, ratio = _claims_supported("RAG is great", [])
        assert passed is False
        assert ratio == 0.0

    def test_claims_supported_with_overlap(self) -> None:
        """Answer with words from chunks passes the support check."""
        passed, ratio = _claims_supported(
            "RAG combines retrieval with generation for better answers.",
            [{"content": "RAG combines retrieval and generation to improve accuracy."}],
        )
        assert passed is True
        assert ratio >= 0.3


class TestCriticAgent:
    """Tests for the CriticAgent LangGraph node."""

    @pytest.mark.asyncio
    async def test_critic_passes_valid_answer(self) -> None:
        """Critic passes an answer with citations and supported claims."""
        state = _make_state(
            answer_text="RAG combines retrieval with generation for accurate answers.",
            citations=[{"chunk_id": "c1", "document_id": "d1", "content_snippet": "RAG combines retrieval and generation"}],
            reranked_chunks=[{"id": "c1", "content": "RAG combines retrieval and generation to produce accurate responses."}],
        )
        result = await critic_agent(state)
        assert result["critic_passed"] is True
        assert result["critic_feedback"] == ""
        assert result["critic_retries"] == 0

    @pytest.mark.asyncio
    async def test_critic_fails_missing_citations(self) -> None:
        """Critic fails an answer with no citations."""
        state = _make_state(
            answer_text="RAG is a technique that improves LLM output.",
            citations=[],
            reranked_chunks=[{"id": "c1", "content": "RAG combines retrieval and generation to produce accurate responses."}],
        )
        result = await critic_agent(state)
        assert result["critic_passed"] is False
        assert "MISSING CITATIONS" in result["critic_feedback"]
        assert result["critic_retries"] == 1

    @pytest.mark.asyncio
    async def test_critic_fails_unsupported_claims(self) -> None:
        """Critic fails when answer claims aren't in the chunks."""
        state = _make_state(
            answer_text="Machine learning is a subset of artificial intelligence that uses neural networks.",
            citations=[{"chunk_id": "c1"}],
            reranked_chunks=[{"id": "c1", "content": "RAG combines retrieval and generation to produce accurate responses."}],
        )
        result = await critic_agent(state)
        assert result["critic_passed"] is False
        assert "UNSUPPORTED CLAIMS" in result["critic_feedback"]
        assert result["critic_retries"] == 1

    @pytest.mark.asyncio
    async def test_critic_forces_pass_after_max_retries(self) -> None:
        """Critic forces pass after MAX_CRITIC_RETRIES failures."""
        state = _make_state(
            answer_text="Hallucinated answer not in chunks.",
            citations=[],
            reranked_chunks=[{"id": "c1", "content": "RAG is a retrieval technique."}],
            critic_retries=MAX_CRITIC_RETRIES,
        )
        result = await critic_agent(state)
        assert result["critic_passed"] is True
        assert "Max retries reached" in result["critic_feedback"]


# ── MemoryAgent tests ────────────────────────────────────────────────────────


class TestMemoryAgent:
    """Tests for the MemoryAgent."""

    @pytest.mark.asyncio
    async def test_stores_and_retrieves_history(self) -> None:
        """Memory agent stores Q&A pairs and returns them."""
        from app.agents.memory_agent import memory_agent as mem_agent_raw

        state = _make_state(
            session_id="mem-test",
            query="What is RAG?",
            answer_text="RAG is retrieval augmented generation.",
        )
        result = await mem_agent_raw(state)

        assert len(result["history"]) == 2
        assert result["history"][0]["role"] == "user"
        assert result["history"][0]["content"] == "What is RAG?"
        assert result["history"][1]["role"] == "assistant"

        # Verify external getter
        history = memory_get_history("mem-test")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_trims_to_last_5_exchanges(self) -> None:
        """Memory trims history to last 5 exchanges (10 messages)."""
        from app.agents.memory_agent import memory_agent as mem_agent_raw

        session = "trim-test"
        for i in range(7):
            state = _make_state(
                session_id=session,
                query=f"Question {i}",
                answer_text=f"Answer {i}",
            )
            await mem_agent_raw(state)

        history = memory_get_history(session)
        assert len(history) == 10  # 5 exchanges × 2
        assert history[0]["content"] == "Question 2"  # first 2 exchanges trimmed
        assert history[-1]["content"] == "Answer 6"

    @pytest.mark.asyncio
    async def test_sessions_are_isolated(self) -> None:
        """Different session IDs have independent histories."""
        from app.agents.memory_agent import memory_agent as mem_agent_raw

        await mem_agent_raw(_make_state(session_id="s1", query="Q1", answer_text="A1"))
        await mem_agent_raw(_make_state(session_id="s2", query="Q2", answer_text="A2"))

        h1 = memory_get_history("s1")
        h2 = memory_get_history("s2")

        assert len(h1) == 2
        assert len(h2) == 2
        assert h1[0]["content"] == "Q1"
        assert h2[0]["content"] == "Q2"


# ── SynthesizerAgent tests ───────────────────────────────────────────────────


class TestSynthesizerAgent:
    """Tests for the SynthesizerAgent."""

    @pytest.mark.asyncio
    async def test_formats_answer_with_citations(self) -> None:
        """Synthesizer formats answer text with citations."""
        state = _make_state(
            query_type="hybrid",
            answer_text="RAG is a technique for augmenting LLMs.",
            citations=[
                {"chunk_id": "c1", "document_id": "d1", "content_snippet": "RAG combines retrieval"},
            ],
            confidence_score=0.9,
        )
        result = await synthesizer_agent(state)

        assert "RAG is a technique" in result["final_response"]
        assert "**Sources:**" in result["final_response"]
        assert "chunk-00" in result["final_response"] or "c1" in result["final_response"]
        assert "90%" in result["final_response"]

    @pytest.mark.asyncio
    async def test_greeting_response(self) -> None:
        """Synthesizer returns a friendly greeting."""
        state = _make_state(query_type="greeting", answer_text="")
        result = await synthesizer_agent(state)
        assert "Hello" in result["final_response"]
        assert "RAG-CRM" in result["final_response"]

    @pytest.mark.asyncio
    async def test_irrelevant_response(self) -> None:
        """Synthesizer returns a polite irrelevant message."""
        state = _make_state(query_type="irrelevant", answer_text="")
        result = await synthesizer_agent(state)
        assert "sorry" in result["final_response"].lower()

    @pytest.mark.asyncio
    async def test_includes_critic_note_when_failed(self) -> None:
        """When critic failed (but forced pass), shows quality note."""
        state = _make_state(
            query_type="hybrid",
            answer_text="Some answer.",
            critic_passed=False,
            critic_feedback="Missing citations.",
        )
        result = await synthesizer_agent(state)
        assert "Quality note" in result["final_response"]
        assert "Missing citations" in result["final_response"]


# ── Pipeline status endpoint ─────────────────────────────────────────────────


class TestPipelineStatus:
    """Tests for GET /pipeline/status."""

    @pytest.mark.asyncio
    async def test_pipeline_status_returns_agents(self, client: AsyncClient) -> None:
        """GET /pipeline/status returns all 7 agents as idle."""
        response = await client.get("/pipeline/status")
        assert response.status_code == 200

        data = response.json()
        assert "agents" in data
        agents = data["agents"]
        assert agents["router"] == "idle"
        assert agents["retriever"] == "idle"
        assert agents["reranker"] == "idle"
        assert agents["answer"] == "idle"
        assert agents["critic"] == "idle"
        assert agents["memory"] == "idle"
        assert agents["synthesizer"] == "idle"
        assert data["pipeline"] == "ready"


# ── POST /qa end-to-end tests (mocked) ──────────────────────────────────────


class TestQAEndpoint:
    """Integration tests for POST /qa via LangGraph pipeline."""

    @pytest.mark.asyncio
    async def test_qa_endpoint_returns_result(
        self, langgraph_client: AsyncClient
    ) -> None:
        """POST /qa returns a full QAResponse with citations."""
        response = await langgraph_client.post(
            "/qa",
            json={
                "query": "What is RAG?",
                "top_k": 10,
                "session_id": "test-1",
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()

        # Check all expected fields
        assert "answer_text" in data
        assert len(data["answer_text"]) > 0
        assert "citations" in data
        assert len(data["citations"]) >= 1
        assert "confidence_score" in data
        assert data["confidence_score"] > 0
        assert "final_response" in data
        assert len(data["final_response"]) > 0
        assert "query_type" in data
        assert data["query_type"] in ("semantic", "keyword", "hybrid", "greeting")

    @pytest.mark.asyncio
    async def test_qa_endpoint_greeting(self, langgraph_client: AsyncClient) -> None:
        """POST /qa with a greeting returns a friendly response."""
        response = await langgraph_client.post(
            "/qa",
            json={"query": "Hello", "top_k": 10},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_type"] == "greeting"

    @pytest.mark.asyncio
    async def test_qa_endpoint_empty_query_422(self, langgraph_client: AsyncClient) -> None:
        """POST /qa with empty query returns 422."""
        response = await langgraph_client.post(
            "/qa",
            json={"query": "", "top_k": 10},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_qa_endpoint_missing_query_422(self, langgraph_client: AsyncClient) -> None:
        """POST /qa without query returns 422."""
        response = await langgraph_client.post(
            "/qa",
            json={"top_k": 10},
        )
        assert response.status_code == 422


# ── Regression tests: existing endpoints still work ──────────────────────────


class TestExistingRoutesStillWork:
    """Verify existing endpoints are not broken by adding the pipeline."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient) -> None:
        """GET /health still returns 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_documents_endpoint_registered(self, client: AsyncClient) -> None:
        """GET /documents is still registered."""
        response = await client.get("/documents")
        assert response.status_code in (200, 405)

    @pytest.mark.asyncio
    async def test_qa_history_endpoint(self, client: AsyncClient) -> None:
        """GET /qa/history returns stub response."""
        response = await client.get("/qa/history")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


# ── Agent node isolation tests ───────────────────────────────────────────────


class TestAnswerAgentNode:
    """Tests for the LangGraph answer_agent node in isolation."""

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_graceful(self) -> None:
        """Answer agent returns a graceful message when no chunks found."""
        state = _make_state(
            query="What is RAG?",
            reranked_chunks=[],
            query_type="hybrid",
            _settings=None,
        )
        result = await langgraph_answer_agent(state)

        assert "answer_text" in result
        assert "No relevant information" in result["answer_text"]
        assert len(result["citations"]) == 0
        assert result["confidence_score"] == 0.0


class TestRetrieverAgentNode:
    """Tests for the retriever_agent in isolation."""

    @pytest.mark.asyncio
    async def test_no_db_session_returns_error(self) -> None:
        """Retriever with no DB session returns error state."""
        from app.agents.retriever_agent import retriever_agent as ret_node

        state = _make_state(
            query="What is RAG?",
            query_type="hybrid",
        )
        result = await ret_node(state)

        assert result["retrieved_chunks"] == []
        assert "error" in result
        assert "No database session" in result["error"]
        assert result["agent_states"]["retriever"] == "error"


class TestRerankerAgentNode:
    """Tests for the reranker_agent in isolation."""

    @pytest.mark.asyncio
    async def test_empty_chunks_skips_reranker(self) -> None:
        """Reranker skips when no chunks provided."""
        from app.agents.reranker_agent import reranker_agent as rerank_node

        state = _make_state(retrieved_chunks=[])
        result = await rerank_node(state)

        assert result["reranked_chunks"] == []
        assert result["agent_states"]["reranker"] == "skipped"
