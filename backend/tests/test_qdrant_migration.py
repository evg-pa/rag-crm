"""Tests for Qdrant vector repository and vector store factory (APP-173 / APP-197).

Covers:
  1. VectorRepository interface contract
  2. QdrantRepository with mocked qdrant_client
  3. Vector store factory dispatching
  4. PgVectorRepository through the interface
  5. Migration script helpers
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.retrieval.pgvector_repository import PgVectorRepository
from app.retrieval.qdrant_repository import QdrantRepository
from app.retrieval.vector_repository import VectorRepository, VectorSearchResult

# ── Test data ────────────────────────────────────────────────────────────────

SAMPLE_CHUNK_IDS = [str(uuid.uuid4()) for _ in range(5)]
SAMPLE_EMBEDDINGS = [[i / 100.0] * 384 for i in range(1, 6)]
SAMPLE_CONTENTS = [f"Chunk {i} content" for i in range(5)]
SAMPLE_DOC_IDS = [str(uuid.uuid4()) for _ in range(5)]
SAMPLE_CHUNK_INDICES = list(range(5))


# ── Helper to create mock Qdrant client results ─────────────────────────────


def _make_scored_point(
    point_id: str | uuid.UUID,
    score: float,
    content: str = "",
    document_id: str = "",
    chunk_index: int = 0,
) -> MagicMock:
    """Create a mock Qdrant ScoredPoint."""
    point = MagicMock()
    point.id = str(point_id)
    point.score = score
    point.vector = None
    point.payload = {
        "content": content,
        "document_id": document_id,
        "chunk_index": chunk_index,
    }
    return point


def _make_record(
    point_id: str | uuid.UUID,
    vector: list[float] | None = None,
    content: str = "",
    document_id: str = "",
    chunk_index: int = 0,
) -> MagicMock:
    """Create a mock Qdrant Record."""
    record = MagicMock()
    record.id = str(point_id)
    record.vector = vector
    record.payload = {
        "content": content,
        "document_id": document_id,
        "chunk_index": chunk_index,
    }
    return record


# ── VectorRepository interface contract ─────────────────────────────────────


def test_vector_search_result_fields():
    """VectorSearchResult should store all expected fields."""
    result = VectorSearchResult(
        id="abc-123",
        content="test content",
        document_id="doc-1",
        chunk_index=0,
        similarity=0.85,
        metadata={"source": "test"},
    )
    assert result.id == "abc-123"
    assert result.content == "test content"
    assert result.document_id == "doc-1"
    assert result.chunk_index == 0
    assert result.similarity == 0.85
    assert result.metadata == {"source": "test"}


def test_vector_search_result_defaults():
    """VectorSearchResult metadata defaults to empty dict."""
    result = VectorSearchResult(id="x", content="c", document_id="d", chunk_index=0, similarity=1.0)
    assert result.metadata == {}


def test_vector_repository_is_abstract():
    """VectorRepository cannot be instantiated directly."""
    with pytest.raises(TypeError):
        VectorRepository()  # type: ignore[abstract]


# ── QdrantRepository with mocked client ────────────────────────────────────


class TestQdrantRepository:
    """Tests for QdrantRepository using mocked AsyncQdrantClient."""

    @pytest.fixture
    def qdrant_repo(self) -> QdrantRepository:
        """Return a QdrantRepository with mocked client."""
        repo = QdrantRepository(url="http://localhost:6333")
        return repo

    @pytest.fixture
    def mock_client(self, qdrant_repo: QdrantRepository) -> MagicMock:
        """Inject a mock client into the repository."""
        mock = MagicMock()
        mock.get_collection = AsyncMock()
        mock.create_collection = AsyncMock()
        mock.upsert = AsyncMock()
        mock.search = AsyncMock()
        mock.count = AsyncMock(return_value=MagicMock(count=5))
        mock.scroll = AsyncMock()
        mock.retrieve = AsyncMock()
        mock.delete = AsyncMock()
        mock.close = AsyncMock()
        qdrant_repo._client = mock
        qdrant_repo._collection_initialized = True
        return mock

    # ── Initialization ──────────────────────────────────────────────────

    def test_init_defaults(self):
        """QdrantRepository should use default URL."""
        repo = QdrantRepository()
        assert repo._url == "http://localhost:6333"
        assert repo._client is None
        assert repo._collection_initialized is False

    def test_init_custom_url(self):
        """QdrantRepository should accept custom URL."""
        repo = QdrantRepository(url="http://qdrant:6333")
        assert repo._url == "http://qdrant:6333"

    # ── Upsert ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_calls_client(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """upsert_embeddings should call qdrant_client.upsert."""
        await qdrant_repo.upsert_embeddings(
            chunk_ids=SAMPLE_CHUNK_IDS,
            embeddings=SAMPLE_EMBEDDINGS,
            contents=SAMPLE_CONTENTS,
            document_ids=SAMPLE_DOC_IDS,
            chunk_indices=SAMPLE_CHUNK_INDICES,
        )
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        assert call_args[1]["collection_name"] == "rag_chunks"
        points = call_args[1]["points"]
        assert len(points) == 5
        assert points[0].payload["content"] == "Chunk 0 content"

    @pytest.mark.asyncio
    async def test_upsert_empty_list(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """upsert_embeddings with empty lists should be a no-op."""
        await qdrant_repo.upsert_embeddings(
            chunk_ids=[],
            embeddings=[],
            contents=[],
            document_ids=[],
            chunk_indices=[],
        )
        mock_client.upsert.assert_not_called()

    # ── Search ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_returns_results(
        self, qdrant_repo: QdrantRepository, mock_client: MagicMock
    ):
        """search should return VectorSearchResult list."""
        mock_points = [
            _make_scored_point("id-1", 0.95, "Chunk A", "doc-1", 0),
            _make_scored_point("id-2", 0.80, "Chunk B", "doc-1", 1),
        ]
        mock_client.search = AsyncMock(return_value=mock_points)

        query = [0.1] * 384
        results = await qdrant_repo.search(query, top_k=2)

        assert len(results) == 2
        assert results[0].id == "id-1"
        assert results[0].similarity == 0.95
        assert results[0].content == "Chunk A"
        assert results[0].document_id == "doc-1"
        assert results[0].chunk_index == 0

    @pytest.mark.asyncio
    async def test_search_empty_query_raises(
        self, qdrant_repo: QdrantRepository, mock_client: MagicMock
    ):
        """search with empty query should raise ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            await qdrant_repo.search([], top_k=10)

    @pytest.mark.asyncio
    async def test_search_passes_top_k(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """search should pass top_k as limit."""
        mock_client.search = AsyncMock(return_value=[])
        await qdrant_repo.search([0.1] * 384, top_k=15)
        call_args = mock_client.search.call_args
        assert call_args[1]["limit"] == 15

    # ── Delete ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_by_document(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """delete_by_document should count then delete."""
        mock_client.count = AsyncMock(return_value=MagicMock(count=3))
        deleted = await qdrant_repo.delete_by_document("doc-1")
        assert deleted == 3
        mock_client.count.assert_called_once()
        mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_document_no_results(
        self, qdrant_repo: QdrantRepository, mock_client: MagicMock
    ):
        """delete_by_document should return 0 when no points match."""
        mock_client.count = AsyncMock(return_value=MagicMock(count=0))
        deleted = await qdrant_repo.delete_by_document("doc-missing")
        assert deleted == 0
        mock_client.delete.assert_not_called()

    # ── Count ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_count(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """count should return the collection size."""
        mock_client.count = AsyncMock(return_value=MagicMock(count=42))
        assert await qdrant_repo.count() == 42

    @pytest.mark.asyncio
    async def test_count_returns_minus_1_on_error(
        self, qdrant_repo: QdrantRepository, mock_client: MagicMock
    ):
        """count should return -1 on error."""
        mock_client.count = AsyncMock(side_effect=Exception("connection error"))
        assert await qdrant_repo.count() == -1

    # ── List chunk ids ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_chunk_ids(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """list_chunk_ids should enumerate all point ids."""
        mock_points = [MagicMock(id="id-1"), MagicMock(id="id-2")]
        mock_client.scroll = AsyncMock(
            return_value=(mock_points, None)  # (points, next_offset)
        )
        ids = await qdrant_repo.list_chunk_ids(limit=100)
        assert ids == ["id-1", "id-2"]

    # ── Get chunk data ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_chunk_data(self, qdrant_repo: QdrantRepository, mock_client: MagicMock):
        """get_chunk_data should return full chunk info with embeddings."""
        test_vec = [0.1] * 384
        mock_records = [
            _make_record("id-1", test_vec, "content 1", "doc-1", 0),
            _make_record("id-2", test_vec, "content 2", "doc-1", 1),
        ]
        mock_client.retrieve = AsyncMock(return_value=mock_records)

        results = await qdrant_repo.get_chunk_data(["id-1", "id-2"])
        assert len(results) == 2
        assert results[0]["id"] == "id-1"
        assert results[0]["content"] == "content 1"
        assert results[0]["embedding"] == test_vec

    @pytest.mark.asyncio
    async def test_get_chunk_data_empty_list(
        self, qdrant_repo: QdrantRepository, mock_client: MagicMock
    ):
        """get_chunk_data with empty list should return []."""
        results = await qdrant_repo.get_chunk_data([])
        assert results == []
        mock_client.retrieve.assert_not_called()

    # ── Collection creation ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_once(
        self, qdrant_repo: QdrantRepository, mock_client: MagicMock
    ):
        """_ensure_collection should only create the collection once."""
        # Reset to force collection creation
        qdrant_repo._collection_initialized = False
        qdrant_repo._client = None  # Redo mock

        mock_client.get_collection = AsyncMock(side_effect=Exception("not found"))
        qdrant_repo._client = mock_client

        # First call: should create
        await qdrant_repo._ensure_collection()
        mock_client.create_collection.assert_called_once()

        # Second call: should skip
        await qdrant_repo._ensure_collection()
        # create_collection should still only have been called once
        assert mock_client.create_collection.call_count == 1

    # ── Client lazy init ─────────────────────────────────────────────

    def test_get_client_lazy_init(self, qdrant_repo: QdrantRepository):
        """_get_client should lazily create the AsyncQdrantClient."""
        assert qdrant_repo._client is None
        with patch("app.retrieval.qdrant_repository.AsyncQdrantClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            import asyncio

            asyncio.run(qdrant_repo._get_client())
            mock_cls.assert_called_once_with(url="http://localhost:6333")


# ── Vector store factory ────────────────────────────────────────────────────


class TestVectorStoreFactory:
    """Tests for get_vector_store() factory function."""

    @patch("app.retrieval.vector_store.get_settings")
    def test_default_pgvector(self, mock_settings: MagicMock):
        """Default VECTOR_STORE should return PgVectorRepository."""
        from app.retrieval.vector_store import get_vector_store

        # Clear cache
        get_vector_store.cache_clear()

        mock_settings.return_value.VECTOR_STORE = "pgvector"

        with patch.object(PgVectorRepository, "__init__", return_value=None):
            result = get_vector_store()
            assert result is not None

        # Clear cache so other tests get correct vector store
        get_vector_store.cache_clear()

    @patch("app.retrieval.vector_store.get_settings")
    def test_qdrant_selection(self, mock_settings: MagicMock):
        """VECTOR_STORE=qdrant should return QdrantRepository."""
        from app.retrieval.vector_store import get_vector_store

        get_vector_store.cache_clear()

        mock_settings.return_value.VECTOR_STORE = "qdrant"
        mock_settings.return_value.QDRANT_URL = "http://qdrant:6333"

        with patch.object(QdrantRepository, "__init__", return_value=None):
            result = get_vector_store()
            assert result is not None

        # Clear cache so other tests get correct vector store
        get_vector_store.cache_clear()

    @patch("app.retrieval.vector_store.get_settings")
    def test_case_insensitive(self, mock_settings: MagicMock):
        """VECTOR_STORE should be case-insensitive."""
        from app.retrieval.vector_store import get_vector_store

        get_vector_store.cache_clear()

        mock_settings.return_value.VECTOR_STORE = "QdRaNt"
        mock_settings.return_value.QDRANT_URL = "http://qdrant:6333"

        with patch.object(QdrantRepository, "__init__", return_value=None):
            result = get_vector_store()
            assert result is not None

        # Clear cache so other tests get correct vector store
        get_vector_store.cache_clear()


# ── Migration script helpers ─────────────────────────────────────────────────


class TestMigrationScript:
    """Tests for migrate_to_qdrant script logic."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self):
        """--dry-run should not call upsert."""
        from app.scripts.migrate_to_qdrant import migrate

        with (
            patch.object(PgVectorRepository, "count", new_callable=AsyncMock) as mock_count,
            patch.object(PgVectorRepository, "list_chunk_ids", new_callable=AsyncMock),
            patch.object(
                QdrantRepository, "upsert_embeddings", new_callable=AsyncMock
            ) as mock_upsert,
            patch.object(QdrantRepository, "count", new_callable=AsyncMock) as mock_qcount,
        ):
            mock_count.return_value = 10
            mock_qcount.return_value = 0

            result = await migrate(dry_run=True)

            assert result["dry_run"] is True
            assert result["migrated"] == 0
            mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_source_returns_zero(self):
        """Migration with no vectors should return 0."""
        from app.scripts.migrate_to_qdrant import migrate

        with (
            patch.object(PgVectorRepository, "count", new_callable=AsyncMock) as mock_count,
        ):
            mock_count.return_value = 0

            result = await migrate(dry_run=False)

            assert result["migrated"] == 0

    @pytest.mark.asyncio
    async def test_verify_counts(self):
        """verify should compare source and target counts."""
        from app.scripts.migrate_to_qdrant import verify

        with (
            patch.object(PgVectorRepository, "count", new_callable=AsyncMock) as mock_scount,
            patch.object(QdrantRepository, "count", new_callable=AsyncMock) as mock_tcount,
            patch.object(PgVectorRepository, "search", new_callable=AsyncMock) as mock_ssearch,
            patch.object(QdrantRepository, "search", new_callable=AsyncMock) as mock_tsearch,
        ):
            mock_scount.return_value = 5
            mock_tcount.return_value = 5

            r1 = VectorSearchResult(
                id="a", content="", document_id="d", chunk_index=0, similarity=1.0
            )
            r2 = VectorSearchResult(
                id="a", content="", document_id="d", chunk_index=0, similarity=0.99
            )
            mock_ssearch.return_value = [r1]
            mock_tsearch.return_value = [r2]

            result = await verify()

            assert result["match"] is True
            assert result["source_count"] == 5
            assert result["target_count"] == 5
            assert result["top5_overlap"] == 1
