#!/usr/bin/env python3
"""Migration script: copy existing pgvector embeddings to Qdrant.

Usage:
    python -m app.scripts.migrate_to_qdrant          # migrate all
    python -m app.scripts.migrate_to_qdrant --dry-run # preview only
    python -m app.scripts.migrate_to_qdrant --verify   # verify after migration

Environment:
    VECTOR_STORE=pgvector  (source backend, default)
    QDRANT_URL=http://localhost:6333  (target Qdrant instance)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import time

from app.core.dependencies import _session_factory, get_settings
from app.retrieval.pgvector_repository import PgVectorRepository
from app.retrieval.qdrant_repository import QdrantRepository

logger = logging.getLogger(__name__)


async def migrate(dry_run: bool = False, batch_size: int = 100) -> dict:
    """Copy all vectors from pgvector to Qdrant.

    Returns a summary dict with counts and timing.
    """
    settings = get_settings()

    source = PgVectorRepository(session_factory=_session_factory)
    target = QdrantRepository(url=settings.QDRANT_URL)

    # Count source vectors
    source_count = await source.count()
    if source_count <= 0:
        logger.warning("No vectors found in pgvector — nothing to migrate")
        return {
            "source_count": source_count,
            "migrated": 0,
            "errors": 0,
            "dry_run": dry_run,
        }

    if dry_run:
        target_count = -1
        with contextlib.suppress(Exception):
            target_count = await target.count()
        logger.info(
            "DRY RUN: would migrate %d vectors from pgvector to Qdrant "
            "(target currently has %d vectors)",
            source_count,
            target_count,
        )
        return {
            "source_count": source_count,
            "target_count_before": target_count,
            "migrated": 0,
            "errors": 0,
            "dry_run": True,
        }

    # Enumerate all chunk ids
    chunk_ids = await source.list_chunk_ids(limit=source_count)
    logger.info("Found %d chunks in pgvector", len(chunk_ids))

    migrated = 0
    errors = 0
    t_start = time.monotonic()

    # Process in batches
    for i in range(0, len(chunk_ids), batch_size):
        batch = chunk_ids[i : i + batch_size]
        try:
            chunks = await source.get_chunk_data(batch)

            ids = []
            embeddings = []
            contents = []
            doc_ids = []
            indices = []

            for chunk in chunks:
                emb = chunk.get("embedding")
                if emb is None:
                    continue
                ids.append(chunk["id"])
                embeddings.append(emb)
                contents.append(chunk["content"])
                doc_ids.append(chunk["document_id"])
                indices.append(chunk.get("chunk_index", -1))

            if ids:
                await target.upsert_embeddings(
                    chunk_ids=ids,
                    embeddings=embeddings,
                    contents=contents,
                    document_ids=doc_ids,
                    chunk_indices=indices,
                )
                migrated += len(ids)

            if (i // batch_size + 1) % 10 == 0:
                logger.info("Migrated %d/%d chunks...", migrated, len(chunk_ids))

        except Exception as exc:
            logger.error("Failed to migrate batch starting at index %d: %s", i, exc)
            errors += len(batch)

    elapsed = time.monotonic() - t_start
    logger.info(
        "Migration complete: %d vectors migrated, %d errors in %.1fs",
        migrated,
        errors,
        elapsed,
    )

    target_count = await target.count()
    return {
        "source_count": source_count,
        "migrated": migrated,
        "errors": errors,
        "target_count_after": target_count,
        "elapsed_seconds": round(elapsed, 1),
        "dry_run": False,
    }


async def verify() -> dict:
    """Verify that Qdrant contains the same vectors as pgvector."""
    settings = get_settings()

    source = PgVectorRepository(session_factory=_session_factory)
    target = QdrantRepository(url=settings.QDRANT_URL)

    source_count = await source.count()
    target_count = await target.count()

    logger.info("Source (pgvector): %d vectors", source_count)
    logger.info("Target (Qdrant):  %d vectors", target_count)

    if source_count != target_count:
        logger.warning(
            "Count mismatch: source=%d, target=%d (diff=%d)",
            source_count,
            target_count,
            abs(source_count - target_count),
        )

    # Spot-check: compare search results for a simple query
    test_embedding = [0.0] * 384  # zero vector — will return some results
    source_results = await source.search(test_embedding, top_k=5)
    target_results = await target.search(test_embedding, top_k=5)

    source_ids = {r.id for r in source_results}
    target_ids = {r.id for r in target_results}
    overlap = source_ids & target_ids

    logger.info(
        "Top-5 search overlap: %d/%d ids match",
        len(overlap),
        len(source_ids),
    )

    return {
        "source_count": source_count,
        "target_count": target_count,
        "match": source_count == target_count,
        "top5_overlap": len(overlap),
        "top5_total": len(source_ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate pgvector embeddings to Qdrant"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without writing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify Qdrant contains same data as pgvector",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of vectors per batch (default: 100)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async def run() -> None:
        if args.verify:
            result = await verify()
        else:
            result = await migrate(dry_run=args.dry_run, batch_size=args.batch_size)

        import json
        print(json.dumps(result, indent=2))

        if result.get("errors", 0) > 0:
            sys.exit(1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
