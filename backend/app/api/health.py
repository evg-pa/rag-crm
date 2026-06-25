"""Health check endpoints — liveness, readiness, and dependency probes."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_db_session, get_settings

router = APIRouter()


@router.get("/health")
async def health_check(
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Health check with database connectivity verification."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "database": db_status,
    }


@router.get("/health/ready")
async def health_ready(
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Readiness probe: application is ready to serve traffic.

    Checks:
    - Database is reachable
    - Redis is reachable (if configured)
    - Qdrant is reachable (if configured as vector store)
    - Embedding model is loaded and producing embeddings
    """
    db_ready = "ready"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ready = "not ready"

    redis_ready = "ready"
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_ready = "not ready"

    qdrant_ready = "disabled"
    if settings.VECTOR_STORE.lower() == "qdrant":
        try:
            from app.retrieval.vector_store import get_vector_store
            store = get_vector_store()
            count = await store.count()
            qdrant_ready = "ready" if count >= 0 else "not ready"
        except Exception:
            qdrant_ready = "not ready"

    embedding_ready = "ready"
    try:
        from app.retrieval.embeddings import get_embedding_model

        model = get_embedding_model()
        emb = await model.embed("health check warmup")
        if not emb or len(emb) == 0:
            embedding_ready = "not ready"
    except Exception:
        embedding_ready = "not ready"

    all_ready = (
        db_ready == "ready"
        and redis_ready == "ready"
        and embedding_ready == "ready"
        and (qdrant_ready in ("ready", "disabled"))
    )
    overall = "ready" if all_ready else "degraded"

    return {
        "status": overall,
        "version": settings.APP_VERSION,
        "database": db_ready,
        "redis": redis_ready,
        "embedding_model": embedding_ready,
        "vector_store": qdrant_ready,
    }


@router.get("/health/live")
async def health_live(
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Liveness probe: application process is alive."""
    return {
        "status": "alive",
        "version": settings.APP_VERSION,
    }
