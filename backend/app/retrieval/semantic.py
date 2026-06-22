"""Semantic search via pgvector cosine distance.

Uses the pgvector `<=>` operator for cosine distance, which is equivalent
to ``1 - cosine_similarity``.  Results are ordered by ascending distance
(= descending similarity).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


async def semantic_search(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Return the *top_k* chunks most similar to *query_embedding* by cosine distance.

    Items are ordered by ascending distance (most similar first).  Each
    result dict contains ``id``, ``content``, ``document_id``,
    ``chunk_index``, and ``similarity`` (1 − distance).

    Notes
    -----
    - Requires the pgvector extension to be enabled in the target database.
    - Runs a sequential scan over all chunks — for production workloads with
      many chunks, add an IVFFlat index on ``embedding``.
    """
    if not query_embedding:
        raise ValueError("query_embedding must not be empty")

    # pgvector <=> is cosine distance: 1 − cosine_similarity
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.document_id,
            Chunk.chunk_index,
            distance,
        )
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
