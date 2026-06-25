"""Semantic search via the configured vector store (pgvector or Qdrant).

When a ``VectorRepository`` is provided it is used directly; otherwise
falls back to pgvector via SQLAlchemy for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.retrieval.vector_repository import VectorRepository


async def semantic_search(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int = 10,
    vector_store: VectorRepository | None = None,
) -> list[dict[str, Any]]:
    """Return the *top_k* chunks most similar to *query_embedding* by cosine distance.

    If *vector_store* is provided, delegates to it for the search.
    Otherwise uses pgvector directly (existing behaviour, for backward compat).

    Items are ordered by ascending distance (most similar first).  Each
    result dict contains ``id``, ``content``, ``document_id``,
    ``chunk_index``, and ``similarity``.
    """
    if not query_embedding:
        raise ValueError("query_embedding must not be empty")

    if vector_store is not None:
        results = await vector_store.search(query_embedding, top_k=top_k)
        return [
            {
                "id": r.id,
                "content": r.content,
                "document_id": r.document_id,
                "chunk_index": r.chunk_index,
                "similarity": r.similarity,
            }
            for r in results
        ]

    # pgvector direct path (backward compatible)
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
        {
            "id": str(row.id),
            "content": row.content,
            "document_id": str(row.document_id),
            "chunk_index": row.chunk_index,
            "similarity": round(float(1.0 - row.distance), 6),
        }
        for row in rows
    ]
