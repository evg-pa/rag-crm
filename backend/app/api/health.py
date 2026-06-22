"""Health check endpoints."""

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
    """Readiness probe: application is ready to serve traffic."""
    db_ready = "ready"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ready = "not ready"

    return {
        "status": db_ready,
        "version": settings.APP_VERSION,
    }


@router.get("/health/live")
async def health_live(
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Liveness probe: application is alive."""
    return {
        "status": "alive",
        "version": settings.APP_VERSION,
    }
