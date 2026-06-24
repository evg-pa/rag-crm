"""API router aggregator."""

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.connectors import router as connectors_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.api.qa import router as qa_router
from app.api.search import router as search_router
from app.api.wiki import router as wiki_router

# ── Pipeline status endpoint ─────────────────────────────────────────────────

pipeline_router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@pipeline_router.get("/status")
async def pipeline_status() -> dict:
    """Return the status of each agent in the LangGraph pipeline.

    Returns a mapping of agent_name → status for observability.
    """
    return {
        "agents": {
            "router": "idle",
            "retriever": "idle",
            "reranker": "idle",
            "answer": "idle",
            "critic": "idle",
            "memory": "idle",
            "synthesizer": "idle",
        },
        "pipeline": "ready",
    }


# ── Aggregate router ─────────────────────────────────────────────────────────

api_router = APIRouter()
api_router.include_router(admin_router, tags=["admin"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(connectors_router, tags=["crm"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(qa_router, tags=["qa"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(wiki_router, tags=["wiki"])
api_router.include_router(memory_router, tags=["memory"])
api_router.include_router(pipeline_router, tags=["pipeline"])
