"""Qdrant-backed vector repository.

Implements the VectorRepository interface using Qdrant vector database.
Qdrant runs as a separate Docker service and communicates over its REST/gRPC API.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.retrieval.vector_repository import VectorRepository, VectorSearchResult

logger = logging.getLogger(__name__)

# Collection name — single collection for all chunk vectors.
_COLLECTION_NAME = "rag_chunks"
# Vector dimension — must match EMBEDDING_DIM (BGE-Small = 384).
_VECTOR_DIM = 384


class QdrantRepository(VectorRepository):
    """Vector storage backed by Qdrant.

    Points are stored in a single collection named ``rag_chunks``.
    Each point's id is the chunk UUID.  Content, document_id, and
    chunk_index are stored in the payload.

    The collection is created automatically on first upsert if it
    doesn't exist.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
    ) -> None:
        """Create a Qdrant-backed repository.

        Parameters
        ----------
        url:
            Qdrant server URL (default: http://localhost:6333).
        api_key:
            Optional API key for Qdrant Cloud.
        """
        self._url = url
        self._client: AsyncQdrantClient | None = None
        self._collection_initialized: bool = False

    async def _get_client(self) -> AsyncQdrantClient:
        """Return (or create) the async Qdrant client."""
        if self._client is None:
            self._client = AsyncQdrantClient(url=self._url)
        return self._client

    async def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        if self._collection_initialized:
            return

        client = await self._get_client()
        try:
            await client.get_collection(_COLLECTION_NAME)
        except Exception:
            logger.info("Creating Qdrant collection '%s' (dim=%d)", _COLLECTION_NAME, _VECTOR_DIM)
            await client.create_collection(
                collection_name=_COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=_VECTOR_DIM,
                    distance=models.Distance.COSINE,
                ),
            )

        self._collection_initialized = True

    async def upsert_embeddings(
        self,
        chunk_ids: list[str],
        embeddings: list[list[float]],
        contents: list[str],
        document_ids: list[str],
        chunk_indices: list[int],
    ) -> None:
        """Upsert chunk embeddings into Qdrant.

        Idempotent: points with existing ids are replaced.
        """
        if not chunk_ids:
            return

        await self._ensure_collection()
        client = await self._get_client()

        # Convert string UUIDs to Qdrant point ids.
        # Qdrant supports UUIDs natively.
        points = [
            models.PointStruct(
                id=cid,
                vector=emb,
                payload={
                    "content": content,
                    "document_id": did,
                    "chunk_index": idx,
                },
            )
            for cid, emb, content, did, idx in zip(
                chunk_ids, embeddings, contents, document_ids, chunk_indices, strict=True
            )
        ]

        await client.upsert(
            collection_name=_COLLECTION_NAME,
            points=points,
        )

        logger.debug("Upserted %d points into Qdrant", len(chunk_ids))

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[VectorSearchResult]:
        """Search chunks by cosine similarity in Qdrant."""
        if not query_embedding:
            raise ValueError("query_embedding must not be empty")

        await self._ensure_collection()
        client = await self._get_client()

        results = await client.search(
            collection_name=_COLLECTION_NAME,
            query_vector=query_embedding,
            limit=top_k,
            with_payload=True,
        )

        return [
            VectorSearchResult(
                id=str(scored_point.id),
                content=scored_point.payload.get("content", ""),
                document_id=scored_point.payload.get("document_id", ""),
                chunk_index=scored_point.payload.get("chunk_index", -1),
                similarity=round(float(scored_point.score), 6),
            )
            for scored_point in results
        ]

    async def delete_by_document(self, document_id: str) -> int:
        """Delete all vectors for a document.

        Qdrant doesn't return exact count on delete by filter, so we
        count points first, then delete.
        """
        await self._ensure_collection()
        client = await self._get_client()

        # Count before deletion
        count_result = await client.count(
            collection_name=_COLLECTION_NAME,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            ),
        )
        before_count = count_result.count

        if before_count == 0:
            return 0

        await client.delete(
            collection_name=_COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

        logger.debug("Deleted %d points for document %s from Qdrant", before_count, document_id)
        return before_count

    async def count(self) -> int:
        """Return total number of vectors in the Qdrant collection."""
        try:
            await self._ensure_collection()
            client = await self._get_client()
            result = await client.count(collection_name=_COLLECTION_NAME)
            return result.count
        except Exception:
            return -1

    async def list_chunk_ids(self, limit: int = 10000) -> list[str]:
        """Return chunk ids stored in Qdrant.

        Uses scroll to enumerate points without loading full vectors.
        """
        await self._ensure_collection()
        client = await self._get_client()

        ids: list[str] = []
        offset: str | int | None = None

        while len(ids) < limit:
            points, next_offset = await client.scroll(
                collection_name=_COLLECTION_NAME,
                limit=min(1000, limit - len(ids)),
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            if not points:
                break
            ids.extend(str(p.id) for p in points)
            offset = next_offset
            if offset is None:
                break

        return ids[:limit]

    async def get_chunk_data(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """Return full chunk data including embeddings from Qdrant."""
        if not chunk_ids:
            return []

        await self._ensure_collection()
        client = await self._get_client()

        # Qdrant retrieve doesn't have a batch limit, but we chunk
        # for safety with large sets.
        results: list[dict[str, Any]] = []
        for i in range(0, len(chunk_ids), 100):
            batch = chunk_ids[i : i + 100]
            points = await client.retrieve(
                collection_name=_COLLECTION_NAME,
                ids=batch,
                with_payload=True,
                with_vectors=True,
            )
            for point in points:
                results.append(
                    {
                        "id": str(point.id),
                        "content": point.payload.get("content", ""),
                        "document_id": point.payload.get("document_id", ""),
                        "chunk_index": point.payload.get("chunk_index", -1),
                        "embedding": point.vector if point.vector else None,
                    }
                )

        return results

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._collection_initialized = False
