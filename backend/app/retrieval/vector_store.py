"""Vector store factory.

Provides a single entry point for obtaining the active VectorRepository
implementation based on the VECTOR_STORE configuration setting.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.dependencies import _session_factory, get_settings
from app.retrieval.pgvector_repository import PgVectorRepository
from app.retrieval.qdrant_repository import QdrantRepository
from app.retrieval.vector_repository import VectorRepository

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_vector_store() -> VectorRepository:
    """Return the active vector store implementation.

    The choice is controlled by the ``VECTOR_STORE`` environment variable:
    - ``pgvector`` (default) — PostgreSQL pgvector backend
    - ``qdrant`` — Qdrant vector database backend

    The result is cached at the process level (lru_cache) so only one
    client is created per backend.
    """
    settings = get_settings()
    store_type = settings.VECTOR_STORE.lower()

    if store_type == "qdrant":
        logger.info("Using Qdrant vector store at %s", settings.QDRANT_URL)
        return QdrantRepository(
            url=settings.QDRANT_URL,
        )
    else:
        logger.info("Using pgvector vector store (PostgreSQL)")
        return PgVectorRepository(session_factory=_session_factory)
