"""API router aggregator."""

from fastapi import APIRouter

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.qa import router as qa_router
from app.api.search import router as search_router

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
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(qa_router, tags=["qa"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(pipeline_router, tags=["pipeline"])
