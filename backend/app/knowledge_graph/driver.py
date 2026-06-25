"""Neo4j async driver singleton — lazy initialization with connection verification."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.core.config import Settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None
_driver_lock = asyncio.Lock()


def _build_neo4j_uri(settings: Settings) -> str:
    """Construct a Neo4j URI from settings, stripping the bolt:// prefix if duplicated."""
    raw = settings.NEO4J_URI
    # Handle cases where env var already has bolt:// prefix
    if "://" in raw:
        return raw
    return f"bolt://{raw}"


async def get_neo4j_driver(settings: Settings | None = None) -> AsyncDriver | None:
    """Return (lazily create) the shared Neo4j async driver.

    Returns None if the driver cannot be created (Neo4j not available).
    Thread-safe via asyncio.Lock.
    """
    global _driver

    if _driver is not None:
        return _driver

    async with _driver_lock:
        if _driver is not None:
            return _driver

        cfg = settings or Settings()
        try:
            from neo4j import AsyncGraphDatabase

            uri = _build_neo4j_uri(cfg)
            _driver = AsyncGraphDatabase.driver(
                uri,
                auth=(cfg.NEO4J_USER, cfg.NEO4J_PASSWORD),
                max_connection_lifetime=3600,
                max_connection_pool_size=10,
                connection_acquisition_timeout=10,
            )
            # Verify connectivity
            await _driver.verify_connectivity()
            logger.info("Neo4j driver created and connected to %s", uri)
            return _driver
        except Exception as exc:
            logger.warning("Neo4j driver creation failed: %s", exc)
            if _driver is not None:
                await _driver.close()
            _driver = None
            return None


async def check_neo4j_connection(settings: Settings | None = None) -> bool:
    """Return True if Neo4j is reachable and healthy."""
    driver = await get_neo4j_driver(settings)
    if driver is None:
        return False
    try:
        await driver.verify_connectivity()
        return True
    except Exception:
        return False


async def close_neo4j_driver() -> None:
    """Close the global Neo4j driver cleanly (for shutdown)."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")
