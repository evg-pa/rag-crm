"""Vector repository abstract interface.

Defines the contract for vector storage backends (pgvector, Qdrant, etc.).
All operations that touch vector embeddings go through this interface so the
storage backend can be swapped at runtime via configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorSearchResult:
    """A single result from a vector search."""

    id: str
    content: str
    document_id: str
    chunk_index: int
    similarity: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorRepository(ABC):
    """Abstract interface for vector storage and retrieval.

    Implementations must be safe to call concurrently (thread-safe for
    search, upsert, and delete).  Upsert is idempotent: re-upserting an
    existing vector with the same id replaces it.

    All async methods are designed to run under a FastAPI event loop.
    """

    @abstractmethod
    async def upsert_embeddings(
        self,
        chunk_ids: list[str],
        embeddings: list[list[float]],
        contents: list[str],
        document_ids: list[str],
        chunk_indices: list[int],
    ) -> None:
        """Store or update embeddings for chunks.

        Idempotent: re-upserting a chunk with the same id replaces its
        embedding, content, and metadata atomically.

        Parameters
        ----------
        chunk_ids:
            Unique identifiers for each chunk (UUID strings).
        embeddings:
            L2-normalized embedding vectors, one per chunk.
        contents:
            Raw text content for each chunk.
        document_ids:
            Parent document identifiers (UUID strings).
        chunk_indices:
            Ordinal position of each chunk within its document.
        """
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[VectorSearchResult]:
        """Return the top-k most similar chunks by cosine similarity.

        Parameters
        ----------
        query_embedding:
            L2-normalized query vector (same dimension as stored vectors).
        top_k:
            Number of results to return.

        Returns
        -------
        list[VectorSearchResult]
            Results ordered by descending similarity (most similar first).
        """
        ...

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> int:
        """Delete all vectors belonging to a document.

        Parameters
        ----------
        document_id:
            The document whose vectors should be removed.

        Returns
        -------
        int
            Number of vectors deleted.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of vectors in the store.

        Returns
        -------
        int
            Total vector count.  Returns -1 if the backend cannot determine
            the count (e.g. connection error).
        """
        ...

    @abstractmethod
    async def list_chunk_ids(self, limit: int = 10000) -> list[str]:
        """Return chunk ids stored in this repository.

        Used by the migration script to enumerate existing vectors.

        Parameters
        ----------
        limit:
            Maximum number of ids to return.

        Returns
        -------
        list[str]
            Chunk UUID strings.
        """
        ...

    @abstractmethod
    async def get_chunk_data(
        self, chunk_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Return full chunk data (content, document_id, chunk_index, embedding).

        Used by the migration script to copy data between backends.

        Parameters
        ----------
        chunk_ids:
            Chunk UUID strings to fetch.

        Returns
        -------
        list[dict]
            Each dict has keys: id, content, document_id, chunk_index, embedding.
        """
        ...
