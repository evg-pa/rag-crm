"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse

from app.api import api_router
from app.core.config import Settings
from app.core.database import init_db
from app.core.dependencies import get_settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler: startup and shutdown events."""
    settings: Settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info(
        "starting application",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
    )
    # Auto-create tables on startup (dev mode)
    await init_db(settings)

    # Pre-build BM25 index from existing chunks
    from app.core.dependencies import _session_factory
    from app.retrieval.keyword import BM25Index

    async with _session_factory() as session:
        try:
            await BM25Index._ensure_loaded(session)
            logger.info("BM25 index built on startup")
        except Exception as exc:
            logger.warning("BM25 index build failed on startup: %s", exc)

    yield
    logger.info("shutting down application")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # CORS: allow localhost:3000 (frontend dev server)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(api_router)

    # Redirect root to docs
    @app.get("/", include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
