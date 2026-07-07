"""FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import RedirectResponse, Response

from app.api import api_router
from app.core.config import Settings
from app.core.database import init_db
from app.core.dependencies import get_settings
from app.core.logging import get_logger, log_unhandled
from app.core.metrics import PrometheusMiddleware, metrics_endpoint
from app.core.middleware import RequestIDMiddleware
from app.core.ratelimit import RateLimitMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler: startup and shutdown events."""
    settings: Settings = get_settings()
    log_unhandled(settings.APP_NAME, settings.APP_VERSION)
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
            logger.info(
                "BM25 index built on startup (metadata: %d entries)",
                len(BM25Index._chunk_metadata or []),
            )
        except Exception as exc:
            logger.warning("BM25 index build failed on startup: %s", exc)

    # Backfill wiki entries for existing documents (fire and forget)
    async def _backfill_wiki() -> None:
        """Background task: generate wiki entries for all documents that lack them."""
        from app.knowledge.wiki_service import WikiService

        async with _session_factory() as wiki_db:
            service = WikiService(wiki_db)
            try:
                count = await service.backfill_all()
                if count > 0:
                    logger.info("Wiki backfill complete: %d entries generated", count)
                else:
                    logger.info("Wiki backfill: all documents already have entries")
            except Exception as exc:
                logger.warning("Wiki backfill failed: %s", exc)
            finally:
                await service.close()

    asyncio.create_task(_backfill_wiki())

    # Pre-load embedding model and reranker in background (don't block startup)
    async def _preload_models() -> None:
        try:
            from app.retrieval.embeddings import get_embedding_model

            m = get_embedding_model()
            await m.embed("warmup")
            logger.info("Embedding model loaded on startup")
        except Exception as exc:
            logger.warning("Embedding model preload failed: %s", exc)

        try:
            from app.retrieval.reranker import Reranker

            r = Reranker()
            await r.rerank("warmup", [{"id": "1", "content": "warmup"}], top_k=1)
            logger.info("Reranker model loaded on startup")
        except Exception as exc:
            logger.warning("Reranker preload failed: %s", exc)

    asyncio.create_task(_preload_models())

    # Initialize Neo4j knowledge graph schema (fire and forget)
    async def _init_neo4j() -> None:
        try:
            from app.knowledge_graph.graph_service import GraphService

            gs = GraphService(settings)
            await gs.initialize_schema()
            logger.info("Neo4j knowledge graph schema initialized")
        except Exception as exc:
            logger.warning("Neo4j schema init failed: %s", exc)

    asyncio.create_task(_init_neo4j())

    yield

    # Cleanup Neo4j driver on shutdown
    try:
        from app.knowledge_graph.driver import close_neo4j_driver

        await close_neo4j_driver()
    except Exception as exc:
        logger.warning("Neo4j driver cleanup failed: %s", exc)

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

    # Request ID middleware — adds X-Request-ID header and structlog context
    app.add_middleware(RequestIDMiddleware)

    # Prometheus metrics middleware — records request count & latency
    app.add_middleware(PrometheusMiddleware)

    # Rate limiting middleware — sliding window via Redis (60 req/min per IP)
    app.add_middleware(RateLimitMiddleware, settings=settings, limit=60, window=60)

    # Include API routers
    app.include_router(api_router)

    # Prometheus /metrics endpoint (registered after middleware to avoid recursion)
    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:  # type: ignore[misc]
        return metrics_endpoint()

    # Error rate monitoring endpoint — returns aggregated error counts by status range
    @app.get("/monitoring/errors", include_in_schema=False)
    async def error_rates() -> JSONResponse:
        """Return current error counts grouped by endpoint and status range.

        Aggregates the Prometheus ``http_requests_total`` counter to show
        client errors (4xx) and server errors (5xx) per endpoint.
        """
        from prometheus_client import REGISTRY

        errors: dict[str, dict[str, int]] = {}

        # Collect samples from the counter metric
        for metric in REGISTRY.collect():
            if metric.name == "http_requests_total":
                for sample in metric.samples:
                    labels = sample.labels
                    endpoint = labels.get("endpoint", "unknown")
                    status_code = labels.get("status", "000")
                    value = int(sample.value)

                    if endpoint not in errors:
                        errors[endpoint] = {
                            "2xx": 0,
                            "3xx": 0,
                            "4xx": 0,
                            "5xx": 0,
                            "total": 0,
                        }

                    status_int = int(status_code)
                    if 200 <= status_int < 300:
                        errors[endpoint]["2xx"] += value
                    elif 300 <= status_int < 400:
                        errors[endpoint]["3xx"] += value
                    elif 400 <= status_int < 500:
                        errors[endpoint]["4xx"] += value
                    elif 500 <= status_int < 600:
                        errors[endpoint]["5xx"] += value
                    errors[endpoint]["total"] += value

        # Calculate error rate per endpoint
        summary: list[dict] = []
        for endpoint, counts in sorted(errors.items()):
            total = counts["total"]
            error_count = counts["4xx"] + counts["5xx"]
            error_rate = round(error_count / total * 100, 2) if total > 0 else 0.0
            summary.append(
                {
                    "endpoint": endpoint,
                    "total_requests": total,
                    "client_errors_4xx": counts["4xx"],
                    "server_errors_5xx": counts["5xx"],
                    "error_rate_percent": error_rate,
                }
            )

        return JSONResponse(
            content={
                "summary": summary,
                "overall": {
                    "total_requests": sum(c["total"] for c in errors.values()),
                    "total_errors": sum(c["4xx"] + c["5xx"] for c in errors.values()),
                },
            }
        )

    # Register global exception handlers for structured error logging
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Log all unhandled exceptions with request ID context, then return 500."""
        logger.error(
            "unhandled exception",
            exc_info=True,
            method=request.method,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Redirect root to docs
    @app.get("/", include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
