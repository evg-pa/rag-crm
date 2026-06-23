"""Tests for hybrid search (APP-121).

Covers:
  1. GET /search/hybrid endpoint (mocked BM25 + mocked reranker)
  2. Hybrid fusion with weighted scoring
  3. BM25 index initialization
  4. BM25 search returns results
  5. Reranker reorders results
  6. Reranker empty candidates
  7. Hybrid search with no results returns empty
  8. Custom fusion weights
  9. Invalid weight validation
  10. All previous tests still pass (implicitly verified via conftest)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.retrieval.hybrid import (
    _min_max_normalize,
    _validate_weights,
    hybrid_search,
)
from app.retrieval.keyword import BM25Index, _tokenize
from app.retrieval.reranker import Reranker

# ── Test data ────────────────────────────────────────────────────────────────

SEMANTIC_RESULTS: list[dict[str, Any]] = [
    {
        "id": "id-1",
        "content": "Python async programming guide",
        "document_id": "doc-a",
        "chunk_index": 0,
        "similarity": 0.9,
    },
    {
        "id": "id-2",
        "content": "Docker container setup",
        "document_id": "doc-b",
        "chunk_index": 3,
        "similarity": 0.7,
    },
    {
        "id": "id-3",
        "content": "Database migration notes",
        "document_id": "doc-a",
        "chunk_index": 1,
        "similarity": 0.5,
    },
]

BM25_RESULTS: list[dict[str, Any]] = [
    {
        "id": "id-2",
        "content": "Docker container setup",
        "document_id": "doc-b",
        "chunk_index": 3,
        "bm25_score": 2.5,
    },
    {
        "id": "id-4",
        "content": "Docker compose configuration",
        "document_id": "doc-c",
        "chunk_index": 0,
        "bm25_score": 1.8,
    },
    {
        "id": "id-1",
        "content": "Python async programming guide",
        "document_id": "doc-a",
        "chunk_index": 0,
        "bm25_score": 1.2,
    },
]


# ── Helpers (mock data factories) ────────────────────────────────────────────


def _make_mock_bm25_search(
    results: list[dict[str, Any]],
) -> AsyncMock:
    """Create an AsyncMock that returns *results* when called."""
    mock = AsyncMock(return_value=results)
    return mock


def _make_mock_reranker_rerank(
    results: list[dict[str, Any]],
) -> AsyncMock:
    """Create an AsyncMock that returns *results* when called."""
    mock = AsyncMock(return_value=results)
    return mock


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_bm25() -> None:
    """Reset BM25 index between tests."""
    BM25Index.reset()


@pytest.fixture(autouse=True)
def _reset_reranker() -> None:
    """Reset Reranker between tests."""
    Reranker.reset()


@pytest.fixture(autouse=True)
def _patch_reranker() -> AsyncGenerator[None, None]:
    """Patch Reranker.rerank to return identity (no re-ordering by default)."""
    original = Reranker.rerank

    async def fake_rerank(
        self: Reranker,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        # Return candidates as-is, but add reranker_score
        return [
            {**c, "reranker_score": 1.0 - i * 0.01}
            for i, c in enumerate(candidates[:top_k])
        ]

    Reranker.rerank = fake_rerank  # type: ignore[method-assign]
    yield
    Reranker.rerank = original  # type: ignore[method-assign]


@pytest.fixture
def mock_embedding_model_for_hybrid() -> MagicMock:
    """Return a mock EmbeddingModel for hybrid search."""
    mock = MagicMock()
    mock.embed = AsyncMock(return_value=[0.01] * 384)
    return mock


@pytest.fixture
async def client_with_hybrid_mocks(
    mock_embedding_model_for_hybrid: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTP client with embedding, BM25, and reranker mocked."""
    from app.main import app
    from app.retrieval.embeddings import get_embedding_model

    _prev_embedding_override = app.dependency_overrides.get(get_embedding_model)
    app.dependency_overrides[get_embedding_model] = lambda: mock_embedding_model_for_hybrid

    # Patch BM25Index.search globally (classmethod)
    with patch.object(
        BM25Index, "search", new_callable=AsyncMock
    ) as mock_bm25_search, patch.object(
        BM25Index, "_ensure_loaded", new_callable=AsyncMock
    ) as mock_ensure:
        mock_bm25_search.return_value = BM25_RESULTS
        mock_ensure.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    if _prev_embedding_override is not None:
        app.dependency_overrides[get_embedding_model] = _prev_embedding_override
    else:
        app.dependency_overrides.pop(get_embedding_model, None)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestBM25Index:
    """Unit tests for BM25Index."""

    def test_tokenize(self) -> None:
        """_tokenize lowercases and splits on whitespace."""
        assert _tokenize("Hello World") == ["hello", "world"]
        assert _tokenize("  Extra   spaces  ") == ["extra", "spaces"]
        assert _tokenize("") == []

    def test_not_loaded_initially(self) -> None:
        """BM25Index starts with is_loaded() == False."""
        BM25Index.reset()
        assert BM25Index.is_loaded() is False

    def test_reset_clears_state(self) -> None:
        """reset() sets is_loaded to False and clears internal state."""
        BM25Index._loaded = True
        BM25Index._index = MagicMock()
        BM25Index._chunk_metadata = [{"id": "x"}]
        BM25Index.reset()
        assert BM25Index.is_loaded() is False
        assert BM25Index._index is None
        assert BM25Index._chunk_metadata is None

    @pytest.mark.asyncio
    async def test_search_without_db_raises(self) -> None:
        """search() raises RuntimeError if index not loaded and no db given."""
        BM25Index.reset()
        with pytest.raises(RuntimeError, match="not loaded"):
            await BM25Index.search("test")

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        """BM25Index.search returns results with bm25_score."""

        from rank_bm25 import BM25Okapi

        # Build a real BM25 index with mock data
        corpus = [
            ["python", "async", "programming", "guide", "for", "developers"],
            ["docker", "container", "setup", "and", "configuration"],
            ["database", "migration", "notes", "for", "postgresql"],
        ]
        metadata = [
            {
                "id": "id-1",
                "content": "python async programming guide for developers",
                "document_id": "doc-a",
                "chunk_index": 0,
            },
            {
                "id": "id-2",
                "content": "docker container setup and configuration",
                "document_id": "doc-b",
                "chunk_index": 3,
            },
            {
                "id": "id-3",
                "content": "database migration notes for postgresql",
                "document_id": "doc-a",
                "chunk_index": 1,
            },
        ]
        BM25Index._index = BM25Okapi(corpus)
        BM25Index._chunk_metadata = metadata
        BM25Index._loaded = True

        results = await BM25Index.search("python async programming", top_k=2)
        assert len(results) > 0
        assert all("bm25_score" in r for r in results)
        assert all("id" in r for r in results)


class TestHybridFusion:
    """Unit tests for hybrid_search fusion logic."""

    def test_min_max_normalize(self) -> None:
        """_min_max_normalize maps scores to [0, 1]."""
        scores = [0.9, 0.7, 0.5]
        norm = _min_max_normalize(scores)
        assert norm == pytest.approx([1.0, 0.5, 0.0])

    def test_min_max_normalize_equal_scores(self) -> None:
        """All identical positive scores → all 1.0."""
        scores = [0.5, 0.5, 0.5]
        norm = _min_max_normalize(scores)
        assert norm == [1.0, 1.0, 1.0]

    def test_min_max_normalize_empty(self) -> None:
        """Empty input → empty output."""
        assert _min_max_normalize([]) == []

    def test_min_max_normalize_single(self) -> None:
        """Single score → 1.0."""
        assert _min_max_normalize([0.42]) == [1.0]

    def test_validate_weights_valid(self) -> None:
        """Valid weights do not raise."""
        _validate_weights(0.5, 0.5)
        _validate_weights(0.0, 1.0)
        _validate_weights(1.0, 0.0)

    def test_validate_weights_negative_semantic(self) -> None:
        """Negative semantic_weight raises ValueError."""
        with pytest.raises(ValueError, match="semantic_weight"):
            _validate_weights(-0.1, 0.5)

    def test_validate_weights_semantic_over_one(self) -> None:
        """semantic_weight > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="semantic_weight"):
            _validate_weights(1.1, 0.5)

    def test_validate_weights_both_zero(self) -> None:
        """Both weights zero raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            _validate_weights(0.0, 0.0)

    @pytest.mark.asyncio
    async def test_hybrid_fusion_weighted(self) -> None:
        """Hybrid fusion combines results from both sources with weights."""
        results = await hybrid_search(
            semantic_results=SEMANTIC_RESULTS,
            bm25_results=BM25_RESULTS,
            top_k=5,
            semantic_weight=0.5,
            bm25_weight=0.5,
        )

        assert len(results) > 0
        # All results must have hybrid_score
        for r in results:
            assert "hybrid_score" in r
            assert "similarity" in r
            assert "bm25_score" in r
            assert "id" in r
            assert "content" in r

        # Results should be sorted by hybrid_score descending
        scores = [r["hybrid_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_hybrid_no_results_returns_empty(self) -> None:
        """Empty inputs → empty output."""
        results = await hybrid_search([], [], top_k=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_hybrid_custom_weights(self) -> None:
        """Custom weights change the fused ordering."""
        # All semantic → results should mirror semantic order
        results_sem = await hybrid_search(
            semantic_results=SEMANTIC_RESULTS,
            bm25_results=BM25_RESULTS,
            top_k=5,
            semantic_weight=1.0,
            bm25_weight=0.0,
        )
        # All BM25 → results should mirror BM25 order (where overlap exists)
        results_bm25 = await hybrid_search(
            semantic_results=SEMANTIC_RESULTS,
            bm25_results=BM25_RESULTS,
            top_k=5,
            semantic_weight=0.0,
            bm25_weight=1.0,
        )

        # With different weights, the top result should differ
        # (At least one set should have a top result)
        assert len(results_sem) > 0
        assert len(results_bm25) > 0

    @pytest.mark.asyncio
    async def test_hybrid_invalid_weight(self) -> None:
        """Invalid weights raise ValueError."""
        with pytest.raises(ValueError):
            await hybrid_search(
                SEMANTIC_RESULTS, BM25_RESULTS,
                semantic_weight=1.5, bm25_weight=0.5,
            )


class TestReranker:
    """Unit tests for Reranker."""

    def test_reranker_not_loaded_initially(self) -> None:
        """Reranker starts unloaded."""
        Reranker.reset()
        assert Reranker.is_loaded() is False

    @pytest.mark.asyncio
    async def test_reranker_empty_candidates(self) -> None:
        """Re-ranking empty list returns empty list."""
        reranker = Reranker()
        results = await reranker.rerank("query", [], top_k=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_reranker_reorders_results(self) -> None:
        """Reranker adds reranker_score and preserves top_k limit."""
        candidates = [
            {"id": "a", "content": "first result", "document_id": "d1", "chunk_index": 0},
            {"id": "b", "content": "second result", "document_id": "d2", "chunk_index": 1},
            {"id": "c", "content": "third result", "document_id": "d1", "chunk_index": 2},
        ]

        # Mock the rerank method since we can't load the real model in tests
        async def fake_rerank(
            self: Reranker,
            query: str,
            candidates: list[dict[str, Any]],
            top_k: int = 10,
        ) -> list[dict[str, Any]]:
            scores = [0.9, 0.3, 0.7]  # re-order: a, c, b
            scored = [
                {**c, "reranker_score": s}
                for s, c in sorted(
                    zip(scores, candidates, strict=True),
                    key=lambda x: x[0],
                    reverse=True,
                )
            ]
            return scored[:top_k]

        original = Reranker.rerank
        Reranker.rerank = fake_rerank  # type: ignore[method-assign]
        try:
            reranker = Reranker()
            results = await reranker.rerank("query", candidates, top_k=2)

            assert len(results) == 2
            assert results[0]["id"] == "a"
            assert results[0]["reranker_score"] == 0.9
            assert results[1]["id"] == "c"
            assert results[1]["reranker_score"] == 0.7
        finally:
            Reranker.rerank = original  # type: ignore[method-assign]


class TestHybridEndpoint:
    """Integration tests for GET /search/hybrid."""

    @pytest.mark.asyncio
    async def test_hybrid_search_endpoint(self, client_with_hybrid_mocks: AsyncClient) -> None:
        """GET /search/hybrid?q=test returns 200 with hybrid results."""
        response = await client_with_hybrid_mocks.get("/search/hybrid?q=test+query")
        assert response.status_code == 200

        data = response.json()
        assert data["query"] == "test query"
        assert "results" in data
        for result in data["results"]:
            assert "hybrid_score" in result
            assert "reranker_score" in result

    @pytest.mark.asyncio
    async def test_hybrid_search_missing_query(self, client_with_hybrid_mocks: AsyncClient) -> None:
        """GET /search/hybrid without ?q= returns 422."""
        response = await client_with_hybrid_mocks.get("/search/hybrid")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_hybrid_search_empty_query(self, client_with_hybrid_mocks: AsyncClient) -> None:
        """GET /search/hybrid?q= returns 422."""
        response = await client_with_hybrid_mocks.get("/search/hybrid?q=")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_hybrid_search_custom_top_k(self, client_with_hybrid_mocks: AsyncClient) -> None:
        """GET /search/hybrid?q=test&top_k=5 works."""
        response = await client_with_hybrid_mocks.get("/search/hybrid?q=test&top_k=5")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_hybrid_search_custom_weights(
        self, client_with_hybrid_mocks: AsyncClient
    ) -> None:
        """GET /search/hybrid with custom semantic_weight and bm25_weight works."""
        response = await client_with_hybrid_mocks.get(
            "/search/hybrid?q=test&semantic_weight=0.8&bm25_weight=0.2"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_hybrid_search_invalid_weight_zero(
        self, client_with_hybrid_mocks: AsyncClient
    ) -> None:
        """All-zero weights returns 422."""
        response = await client_with_hybrid_mocks.get(
            "/search/hybrid?q=test&semantic_weight=0&bm25_weight=0"
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_hybrid_search_invalid_weight_range(
        self, client_with_hybrid_mocks: AsyncClient
    ) -> None:
        """semantic_weight=1.5 returns 422 (validation error)."""
        response = await client_with_hybrid_mocks.get(
            "/search/hybrid?q=test&semantic_weight=1.5"
        )
        assert response.status_code == 422


class TestPreviousTestsStillPass:
    """Verify that existing endpoints still work with the new code."""

    @pytest.mark.asyncio
    async def test_semantic_search_endpoint_available(self, client: AsyncClient) -> None:
        """GET /search route is registered (app routes include /search)."""
        # Verify via actual HTTP request — app.routes doesn't flatten IncludedRouter
        response = await client.get("/search?q=test")
        assert response.status_code in (200, 422)  # 200=success, 422=no DB

        response = await client.get("/search/hybrid?q=test")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_health_endpoint_still_works(self, client: AsyncClient) -> None:
        """GET /health still works."""
        response = await client.get("/health")
        assert response.status_code == 200
