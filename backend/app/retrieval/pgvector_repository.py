"""PgVector-backed vector repository.

Implements the VectorRepository interface using pgvector (PostgreSQL
extension) with SQLAlchemy async sessions.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, text

from app.models.chunk import Chunk
from app.retrieval.vector_repository import VectorRepository, VectorSearchResult

logger = logging.getLogger(__name__)


class PgVectorRepository(VectorRepository):
    """Vector storage backed by pgvector in PostgreSQL.

    Uses the existing ``chunks`` table and its ``embedding`` column
    (pgvector Vector(384)).  The repository requires a database session
    factory and creates fresh sessions for each operation to avoid
    session lifecycle conflicts in FastAPI's dependency injection.
    """

    def __init__(self, session_factory: Any) -> None:
        """Create a PgVector-backed repository.

        Parameters
        ----------
        session_factory:
            An async session factory (callable returning an
            ``AsyncSession`` context manager or directly an
            ``AsyncSession``).  Typically the SQLAlchemy
            ``async_sessionmaker`` instance.
        """
        self._session_factory = session_factory

    async def upsert_embeddings(
        self,
        chunk_ids: list[str],
        embeddings: list[list[float]],
        contents: list[str],
        document_ids: list[str],
        chunk_indices: list[int],
    ) -> None:
        """Update embeddings on existing chunks.

        Chunks must already exist in the database (created by the
        ingestion pipeline before embeddings are generated).  This
        method updates only the ``embedding`` column.
        """
        if not chunk_ids:
            return

        async with self._session_factory() as db:
            for chunk_id, embedding in zip(chunk_ids, embeddings, strict=True):
                # Use raw SQL for efficient, targeted update without
                # loading the full object into the session.
                await db.execute(
                    text("UPDATE chunks SET embedding = :emb WHERE id = :cid"),
                    {"emb": embedding, "cid": chunk_id},
                )
            await db.commit()

        logger.debug("Upserted %d embeddings via pgvector", len(chunk_ids))

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[VectorSearchResult]:
        """Search chunks by cosine similarity via pgvector."""
        if not query_embedding:
            raise ValueError("query_embedding must not be empty")

        async with self._session_factory() as db:
            distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")

            stmt = (
                select(
                    Chunk.id,
                    Chunk.content,
                    Chunk.document_id,
                    Chunk.chunk_index,
                    distance,
                )
                .where(Chunk.embedding.isnot(None))
                .order_by(distance)
                .limit(top_k)
            )

            result = await db.execute(stmt)
            rows = result.all()

            return [
                VectorSearchResult(
                    id=str(row.id),
                    content=row.content,
                    document_id=str(row.document_id),
                    chunk_index=row.chunk_index,
                    similarity=round(float(1.0 - row.distance), 6),
                )
                for row in rows
            ]

    async def delete_by_document(self, document_id: str) -> int:
        """Delete all chunk embeddings for a document (set to NULL).

        Returns the number of chunks affected.
        """
        async with self._session_factory() as db:
            result = await db.execute(
                text("UPDATE chunks SET embedding = NULL WHERE document_id = :did"),
                {"did": document_id},
            )
            await db.commit()
            return result.rowcount or 0

    async def count(self) -> int:
        """Return the number of chunks with non-NULL embeddings."""
        async with self._session_factory() as db:
            result = await db.execute(
                text("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
            )
            row = result.scalar()
            return int(row) if row is not None else 0

    async def list_chunk_ids(self, limit: int = 10000) -> list[str]:
        """Return chunk UUIDs that have embeddings."""
        async with self._session_factory() as db:
            result = await db.execute(
                select(Chunk.id)
                .where(Chunk.embedding.isnot(None))
                .order_by(Chunk.chunk_index)
                .limit(limit)
            )
            return [str(row[0]) for row in result.all()]

    async def get_chunk_data(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """Return full chunk data for the given ids."""
        if not chunk_ids:
            return []

        async with self._session_factory() as db:
            result = await db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
            chunks = result.scalars().all()

            return [
                {
                    "id": str(chunk.id),
                    "content": chunk.content,
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "embedding": chunk.embedding,
                }
                for chunk in chunks
            ]
