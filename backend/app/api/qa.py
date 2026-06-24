"""Q&A REST endpoints — powered by the 7-agent LangGraph pipeline.

POST /qa              — answer a question using the full LangGraph pipeline
GET  /qa/history      — stub for QA history (not yet implemented)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.agents.state_graph import build_qa_graph
from app.core.config import Settings
from app.core.dependencies import get_db_session, get_settings
from app.retrieval.embeddings import EmbeddingModel, get_embedding_model
from app.retrieval.qa import AnswerResult, Citation

router = APIRouter(prefix="/qa", tags=["qa"])
crm_router = APIRouter(prefix="/qa/crm", tags=["qa"])

# ── Compiled graph (lazy, built once) ────────────────────────────────────────
_qa_graph: Any = None  # compiled LangGraph StateGraph


def _get_graph() -> Any:
    """Return (or lazily build) the compiled LangGraph QA pipeline."""
    global _qa_graph
    if _qa_graph is None:
        _qa_graph = build_qa_graph()
    return _qa_graph


# ── Pydantic schemas ────────────────────────────────────────────────────────


class QARequest(BaseModel):
    """Request body for POST /qa."""

    query: str = Field(..., description="The question to answer", min_length=1)
    top_k: int = Field(10, ge=1, le=100, description="Number of chunks to retrieve")
    session_id: str = Field("default", description="Session identifier for conversation memory")


class QAResponse(BaseModel):
    """Response body for POST /qa (LangGraph pipeline output)."""

    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence_score: float = 0.0
    final_response: str = ""
    query_type: str = ""


class QAHistoryResponse(BaseModel):
    """Stub response for GET /qa/history."""

    items: list[dict[str, Any]] = Field(default_factory=list)


# ── CRM Quick-Query Presets ──────────────────────────────────────────────────


CRM_PRESETS: dict[str, dict[str, str]] = {
    "top_deals": {
        "label": "🏆 Top Deals by Value",
        "description": "Show me the highest-value deals currently in the pipeline",
        "query": "List all deals sorted by value from highest to lowest, with contact names.",
    },
    "recent_activities": {
        "label": "📅 Recent Activities",
        "description": "Show the most recent calls, meetings, and emails",
        "query": "What are the most recent CRM activities?",
    },
    "deals_by_stage": {
        "label": "📊 Deals by Stage",
        "description": "Show how many deals are in each pipeline stage",
        "query": "Summarize deals grouped by pipeline stage.",
    },
    "contacts_list": {
        "label": "👥 All Contacts",
        "description": "List all CRM contacts",
        "query": "List all CRM contacts.",
    },
    "hot_leads": {
        "label": "🔥 Hot Leads",
        "description": "Show deals in late stages (negotiation / closed won)",
        "query": "Show deals in late stages like negotiation or closed won.",
    },
    "pipeline_summary": {
        "label": "📈 Pipeline Summary",
        "description": "Total pipeline value, deal count, and average deal size",
        "query": "What is the total pipeline value and how many deals are open?",
    },
}


class CRMPresetOut(BaseModel):
    """A single CRM preset definition."""

    key: str = Field(..., description="Preset identifier")
    label: str = Field(..., description="Human-readable button label")
    description: str = Field(..., description="Short description of what the preset does")
    query: str = Field(..., description="Suggested query text to send to the Q&A endpoint")


class CRMPresetsResponse(BaseModel):
    """Response body for GET /qa/crm/presets."""

    presets: list[CRMPresetOut] = Field(default_factory=list)


class CRMQuickQueryRequest(BaseModel):
    """Request body for POST /qa/crm/quick-query (bypasses LangGraph)."""

    preset: str | None = Field(None, description="Preset key from /qa/crm/presets")
    query: str = Field(..., description="Free-form CRM question", min_length=1)
    limit: int = Field(10, ge=1, le=100, description="Max results to return")


class CRMQuickQueryResponse(BaseModel):
    """Response body for POST /qa/crm/quick-query."""

    intent: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    formatted: str = ""


@crm_router.get("/presets", response_model=CRMPresetsResponse)
async def list_crm_presets() -> CRMPresetsResponse:
    """Return the list of available CRM quick-query presets.

    Each preset has a ``key``, ``label``, ``description``, and the
    ``query`` string that can be sent to ``POST /qa`` for a full
    LangGraph pipeline answer.
    """
    return CRMPresetsResponse(
        presets=[
            CRMPresetOut(
                key=k,
                label=v["label"],
                description=v["description"],
                query=v["query"],
            )
            for k, v in CRM_PRESETS.items()
        ]
    )


@crm_router.post("/quick-query", response_model=CRMQuickQueryResponse)
async def crm_quick_query(
    body: CRMQuickQueryRequest,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CRMQuickQueryResponse:
    """Run a CRM quick-query that bypasses the full LangGraph pipeline.

    Executes a direct CRM database lookup and returns structured CRM data.
    Use this for quick, well-known CRM queries instead of the full QA pipeline.

    Supports:
    - ``top_deals`` — highest-value deals with contact names
    - ``recent_activities`` — recent calls, meetings, emails
    - ``deals_by_stage`` — deal counts grouped by stage
    - ``contacts_list`` — all CRM contacts
    - ``hot_leads`` — deals in late stages
    - ``pipeline_summary`` — aggregate pipeline stats
    - Free-form CRM queries (intent-detected)
    """
    from app.models.crm import CrmActivity, CrmContact, CrmDeal

    query = body.preset or body.query

    # Detect intent from preset or free-form query
    from app.agents.crm_context import classify_crm_intent
    intent = classify_crm_intent(query)

    # Default empty response
    response = CRMQuickQueryResponse(
        intent=intent,
        data={},
        summary="",
        formatted="No CRM data found.",
    )

    try:
        if body.preset == "top_deals" or intent == "deal" or "top" in query.lower():
            result = await db.execute(
                select(CrmDeal).order_by(CrmDeal.value.desc().nullslast()).limit(body.limit)
            )
            deals = list(result.scalars().all())

            # Enrich with contact names
            deal_list: list[dict[str, Any]] = []
            for d in deals:
                contact_name = "N/A"
                if d.contact_id:
                    c_result = await db.execute(
                        select(CrmContact).where(CrmContact.id == d.contact_id)
                    )
                    contact = c_result.scalar_one_or_none()
                    contact_name = contact.name if contact else "N/A"

                deal_list.append({
                    "id": str(d.id),
                    "name": d.name,
                    "value": d.value,
                    "stage": d.stage,
                    "close_date": d.close_date.isoformat() if d.close_date else None,
                    "contact": contact_name,
                })

            total_value = sum(d.value or 0 for d in deals)
            response.data = {
                "deals": deal_list,
                "total_count": len(deal_list),
                "total_value": total_value,
            }
            response.summary = f"Found {len(deal_list)} deals totaling ${total_value:,.2f}."

        elif body.preset == "recent_activities" or intent == "activity":
            result = await db.execute(
                select(CrmActivity).order_by(CrmActivity.date.desc()).limit(body.limit)
            )
            activities = list(result.scalars().all())

            activity_list: list[dict[str, Any]] = []
            for a in activities:
                contact_name = "N/A"
                if a.contact_id:
                    c_result = await db.execute(
                        select(CrmContact).where(CrmContact.id == a.contact_id)
                    )
                    contact = c_result.scalar_one_or_none()
                    contact_name = contact.name if contact else "N/A"

                activity_list.append({
                    "id": str(a.id),
                    "type": a.type,
                    "description": a.description[:200],
                    "date": a.date.isoformat(),
                    "contact": contact_name,
                })

            response.data = {"activities": activity_list, "total_count": len(activity_list)}
            response.summary = f"Found {len(activity_list)} recent activities."

        elif body.preset == "deals_by_stage":
            result = await db.execute(select(CrmDeal))
            deals = list(result.scalars().all())

            stage_counts: dict[str, int] = {}
            stage_values: dict[str, float] = {}
            for d in deals:
                stage = d.stage or "unknown"
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
                stage_values[stage] = stage_values.get(stage, 0) + (d.value or 0)

            stage_data = [
                {"stage": stage, "count": count, "value": stage_values[stage]}
                for stage, count in sorted(stage_counts.items())
            ]
            response.data = {"stages": stage_data, "total_deals": len(deals)}
            response.summary = f"{len(deals)} deals across {len(stage_data)} stages."

        elif body.preset == "contacts_list" or intent == "contact":
            result = await db.execute(
                select(CrmContact).order_by(CrmContact.name).limit(body.limit)
            )
            contacts = list(result.scalars().all())

            contact_list: list[dict[str, Any]] = [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "company": c.company,
                }
                for c in contacts
            ]
            response.data = {"contacts": contact_list, "total_count": len(contact_list)}
            response.summary = f"Found {len(contact_list)} contacts."

        elif body.preset == "hot_leads":
            late_stages = ("negotiation", "closed won", "closed_won")
            result = await db.execute(
                select(CrmDeal).where(CrmDeal.stage.in_(late_stages))
                .order_by(CrmDeal.value.desc().nullslast())
            )
            deals = list(result.scalars().all())

            hot_list: list[dict[str, Any]] = []
            for d in deals:
                contact_name = "N/A"
                if d.contact_id:
                    c_result = await db.execute(
                        select(CrmContact).where(CrmContact.id == d.contact_id)
                    )
                    contact = c_result.scalar_one_or_none()
                    contact_name = contact.name if contact else "N/A"

                hot_list.append({
                    "id": str(d.id),
                    "name": d.name,
                    "value": d.value,
                    "stage": d.stage,
                    "contact": contact_name,
                })

            response.data = {"hot_leads": hot_list, "total_count": len(hot_list)}
            response.summary = f"Found {len(hot_list)} hot leads in late stages."

        elif body.preset == "pipeline_summary":
            result = await db.execute(select(CrmDeal))
            deals = list(result.scalars().all())

            open_deals = [d for d in deals if d.stage not in ("closed lost", "closed_won", "cancelled")]
            total_value = sum(d.value or 0 for d in deals)
            open_value = sum(d.value or 0 for d in open_deals)
            avg_value = (total_value / len(deals)) if deals else 0

            response.data = {
                "total_deals": len(deals),
                "open_deals": len(open_deals),
                "total_pipeline_value": total_value,
                "open_pipeline_value": open_value,
                "average_deal_value": round(avg_value, 2),
            }
            response.summary = (
                f"{len(open_deals)} open deals of {len(deals)} total, "
                f"pipeline value ${open_value:,.2f}, "
                f"avg ${avg_value:,.2f}/deal."
            )

        # Format nicely for display
        if response.data:
            lines: list[str] = []
            for key, value in response.data.items():
                if isinstance(value, list):
                    lines.append(f"\n**{key.replace('_', ' ').title()}:**")
                    for item in value[:5]:
                        if isinstance(item, dict):
                            parts = [f"{k}: {v}" for k, v in item.items() if v is not None]
                            lines.append(f"- {', '.join(parts[:4])}")
                elif isinstance(value, (int, float)):
                    lines.append(f"\n**{key.replace('_', ' ').title()}:** {value:,.2f}" if isinstance(value, float) else f"\n**{key.replace('_', ' ').title()}:** {value}")
                else:
                    lines.append(f"\n**{key.replace('_', ' ').title()}:** {value}")
            response.formatted = "\n".join(lines)

    except Exception:
        pass  # Return empty gracefully

    return response


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    db: AsyncSession = Depends(get_db_session),
    model: EmbeddingModel = Depends(get_embedding_model),
    settings: Settings = Depends(get_settings),
) -> QAResponse:
    """Answer a question using the 7-agent LangGraph pipeline.

    Pipeline:
    1. RouterAgent — classifies the query type
    2. RetrieverAgent — runs the appropriate search strategy
    3. RerankerAgent — re-ranks top results
    4. AnswerAgent — generates an answer via DeepSeek / Ollama
    5. CriticAgent — validates the answer (up to 2 retries)
    6. MemoryAgent — stores the exchange in session history
    7. SynthesizerAgent — produces the final polished response
    """
    # Build initial state with injected dependencies
    initial_state: AgentState = {
        "query": body.query,
        "session_id": body.session_id,
        "top_k": body.top_k,
        "_db_session": db,           # type: ignore[typeddict-item]
        "_embedding_model": model,   # type: ignore[typeddict-item]
        "_settings": settings,       # type: ignore[typeddict-item]
    }

    graph = _get_graph()

    # FIX 6: wrap graph.ainvoke() in try/except for meaningful error responses
    try:
        raw_state: dict[str, Any] = await graph.ainvoke(initial_state)  # type: ignore[assignment]
    except Exception as exc:
        return QAResponse(
            answer_text=f"Pipeline error: {exc}",
            citations=[],
            confidence_score=0.0,
            final_response=f"An error occurred while processing your question: {exc}",
            query_type="",
        )

    # FIX 4: strip DI-injected private fields before any serialization
    raw_state.pop("_db_session", None)
    raw_state.pop("_embedding_model", None)
    raw_state.pop("_settings", None)

    result_state: AgentState = raw_state  # type: ignore[assignment]

    # Extract fields from the final state
    answer_text: str = result_state.get("answer_text", "")
    citations_raw: list[dict[str, Any]] = result_state.get("citations", [])
    confidence_score: float = float(result_state.get("confidence_score", 0.0))
    final_response: str = result_state.get("final_response", answer_text)
    query_type: str = result_state.get("query_type", "")

    # Convert citation dicts to Citation models
    citations: list[Citation] = []
    for cit in citations_raw:
        citations.append(
            Citation(
                chunk_id=str(cit.get("chunk_id", "")),
                document_id=str(cit.get("document_id", "")),
                content_snippet=str(cit.get("content_snippet", "")),
            )
        )

    return QAResponse(
        answer_text=answer_text,
        citations=citations,
        confidence_score=confidence_score,
        final_response=final_response,
        query_type=query_type,
    )


@router.get("/history", response_model=QAHistoryResponse)
async def qa_history(
    settings: Settings = Depends(get_settings),
) -> QAHistoryResponse:
    """Return QA query history (stub — not yet implemented)."""
    return QAHistoryResponse(items=[])
