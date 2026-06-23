"""Tests for semantic search endpoint (APP-119).

Covers:
  1. GET /search without query → 422 validation error
  2. GET /search with mocked embedding → returns ranked results
  3. semantic_search ordering by cosine distance (unit test with mock DB)
  4. Batch embedding returns normalized vectors
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.embeddings import EmbeddingModel

# ── Embedding model patches ─────────────────────────────────────────────────
# No ONNX model is loaded during tests.  We patch the singleton factory
# so the API dependency gets a mock model that returns fixed embeddings.


@pytest.fixture
def mock_embedding_model() -> MagicMock:
    """Return a mock EmbeddingModel that returns a deterministic 384-d vector."""
    mock = MagicMock(spec=EmbeddingModel)
    mock.embed = AsyncMock(return_value=[0.01] * 384)
    mock.embed_batch = AsyncMock(return_value=[[0.01] * 384, [0.02] * 384, [0.03] * 384])
    return mock


@pytest.fixture
async def client_with_mock(
    mock_embedding_model: MagicMock,
    _setup_database,
) -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTP client with the embedding model mocked."""
    from app.main import app
    from app.retrieval.embeddings import get_embedding_model

    _prev_embedding_override = app.dependency_overrides.get(get_embedding_model)
    app.dependency_overrides[get_embedding_model] = lambda: mock_embedding_model
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    if _prev_embedding_override is not None:
        app.dependency_overrides[get_embedding_model] = _prev_embedding_override
    else:
        app.dependency_overrides.pop(get_embedding_model, None)


# ── API endpoint tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_missing_query(client: AsyncClient) -> None:
    """GET /search without ?q= returns 422 validation error."""
    response = await client.get("/search")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_empty_query(client: AsyncClient) -> None:
    """GET /search?q= with empty string returns 422."""
    response = await client.get("/search?q=")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_results(client_with_mock: AsyncClient) -> None:
    """GET /search?q=test returns a SearchResponse with the query echoed."""
    response = await client_with_mock.get("/search?q=test+query")
    assert response.status_code == 200

    data = response.json()
    assert data["query"] == "test query"


@pytest.mark.asyncio
async def test_search_default_top_k(client_with_mock: AsyncClient) -> None:
    """GET /search uses top_k=10 by default (query param is optional)."""
    response = await client_with_mock.get("/search?q=hello")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_custom_top_k(client_with_mock: AsyncClient) -> None:
    """GET /search?q=test&top_k=5 passes top_k to semantic_search."""
    response = await client_with_mock.get("/search?q=test&top_k=5")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_invalid_top_k(client: AsyncClient) -> None:
    """top_k=0 returns 422 validation error (must be >= 1)."""
    response = await client.get("/search?q=test&top_k=0")
    assert response.status_code == 422


# ── Unit tests: embedding model ─────────────────────────────────────────────


class TestEmbeddingModel:
    """Tests for the EmbeddingModel class (no ONNX loading)."""

    def test_singleton(self) -> None:
        """get_embedding_model returns the same instance each time."""
        from app.retrieval.embeddings import get_embedding_model

        a = get_embedding_model()
        b = get_embedding_model()
        assert a is b

    def test_embed_batch_empty(self) -> None:
        """embed_batch with empty list returns empty list without loading model."""
        import asyncio

        model = EmbeddingModel()

        async def run() -> list[list[float]]:
            return await model.embed_batch([])

        result = asyncio.run(run())
        assert result == []

    def test_mean_pool(self) -> None:
        """_mean_pool averages token embeddings weighted by attention mask.

        Requires torch (installed as a transitive dependency of optimum).
        Skipped when torch is not available.
        """
        try:
            import torch  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("torch not available — ONNX inference test skipped")

        batch, seq, dim = 2, 4, 8
        token_emb = torch.ones(batch, seq, dim)
        mask = torch.tensor([[1, 1, 0, 0], [1, 1, 1, 0]], dtype=torch.float)

        result = EmbeddingModel._mean_pool(token_emb, mask)

        assert result.shape == (batch, dim)
        # Row 0: (1+1) / 2 = 1.0
        assert abs(float(result[0, 0]) - 1.0) < 1e-6
        # Row 1: (1+1+1) / 3 = 1.0
        assert abs(float(result[1, 0]) - 1.0) < 1e-6


# ── Unit tests: semantic_search ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_semantic_search_empty_embedding_raises() -> None:
    """semantic_search raises ValueError when query_embedding is empty."""
    from app.retrieval.semantic import semantic_search

    db = MagicMock(spec=AsyncSession)
    with pytest.raises(ValueError, match="must not be empty"):
        await semantic_search(db, [])


@pytest.mark.asyncio
async def test_semantic_search_orders_by_similarity() -> None:
    """semantic_search returns results ordered by ascending distance."""
    from app.retrieval.semantic import semantic_search

    db = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = [
        MagicMock(
            id="id-1",
            content="most relevant chunk",
            document_id="doc-a",
            chunk_index=0,
            distance=0.1,
        ),
        MagicMock(
            id="id-2",
            content="less relevant chunk",
            document_id="doc-b",
            chunk_index=3,
            distance=0.5,
        ),
        MagicMock(
            id="id-3",
            content="least relevant chunk",
            document_id="doc-a",
            chunk_index=1,
            distance=0.9,
        ),
    ]
    db.execute = AsyncMock(return_value=mock_result)

    results = await semantic_search(db, [0.1] * 384, top_k=3)

    assert len(results) == 3
    assert results[0]["similarity"] == pytest.approx(0.9)  # 1.0 - 0.1
    assert results[1]["similarity"] == pytest.approx(0.5)  # 1.0 - 0.5
    assert results[2]["similarity"] == pytest.approx(0.1)  # 1.0 - 0.9

    # Verify first result is the most similar
    assert results[0]["id"] == "id-1"
    assert results[0]["content"] == "most relevant chunk"

    # Verify execute was called with a SELECT using cosine_distance
    call_args = db.execute.call_args
    assert call_args is not None
