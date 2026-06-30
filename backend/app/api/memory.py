"""Memory API — CRUD endpoints for working, episodic, semantic, and procedural memory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_settings
from app.memory.service import (
    EpisodicMemoryService,
    ProceduralMemoryService,
    SemanticMemoryService,
    WorkingMemoryService,
)

router = APIRouter(prefix="/memory", tags=["memory"])


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _get_db():
    """Yield an async DB session."""
    settings = get_settings()
    from app.core.database import create_engine, create_session_factory

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── Working Memory ──────────────────────────────────────────────────────────


@router.get("/working/{session_id}")
async def get_working_memory(
    session_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(_get_db),
) -> list[dict[str, Any]]:
    """Return working memory history for a session."""
    service = WorkingMemoryService(db)
    return await service.get_history(session_id=session_id, limit=limit)


@router.delete("/working/{session_id}")
async def clear_working_memory(
    session_id: str,
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    """Clear working memory for a session."""
    service = WorkingMemoryService(db)
    deleted = await service.clear_session(session_id=session_id)
    return {"deleted": deleted, "session_id": session_id}


# ── Episodic Memory ─────────────────────────────────────────────────────────


@router.get("/episodic/recent")
async def list_episodic(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(_get_db),
) -> list[dict[str, Any]]:
    """List recent episodic memories."""
    service = EpisodicMemoryService(db)
    entries = await service.list_recent(limit=limit, offset=offset)
    return [
        {
            "id": str(e.id),
            "session_id": e.session_id,
            "summary": e.summary,
            "topics": e.topics,
            "message_count": e.message_count,
            "started_at": e.started_at.isoformat(),
            "ended_at": e.ended_at.isoformat(),
            "updated_at": e.updated_at.isoformat(),
        }
        for e in entries
    ]


@router.get("/episodic/{session_id}")
async def get_episodic(
    session_id: str,
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    """Return episodic memory for a session."""
    service = EpisodicMemoryService(db)
    entry = await service.get_by_session(session_id=session_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No episodic memory for session {session_id!r}",
        )
    return {
        "id": str(entry.id),
        "session_id": entry.session_id,
        "summary": entry.summary,
        "topics": entry.topics,
        "message_count": entry.message_count,
        "started_at": entry.started_at.isoformat(),
        "ended_at": entry.ended_at.isoformat(),
    }


# ── Semantic Memory ─────────────────────────────────────────────────────────


@router.post("/semantic")
async def add_fact(
    fact: str = Query(..., min_length=1, max_length=2000),
    source: str = Query("manual"),
    source_id: str | None = Query(None),
    confidence: float = Query(1.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    """Add a new fact to semantic memory (embedding computed server-side)."""
    service = SemanticMemoryService(db)
    entry = await service.add_fact(
        fact=fact,
        source=source,
        source_id=source_id,
        confidence=confidence,
    )
    return {
        "id": str(entry.id),
        "fact": entry.fact,
        "source": entry.source,
        "confidence": entry.confidence,
    }


@router.get("/semantic/search")
async def search_facts(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    db: AsyncSession = Depends(_get_db),
) -> list[dict[str, Any]]:
    """Search semantic facts by meaning (vector similarity)."""
    service = SemanticMemoryService(db)
    return await service.search_similar(
        query=query,
        limit=limit,
        min_confidence=min_confidence,
    )


@router.get("/semantic")
async def list_facts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(_get_db),
) -> list[dict[str, Any]]:
    """List all semantic facts."""
    service = SemanticMemoryService(db)
    entries = await service.list_facts(limit=limit, offset=offset)
    return [
        {
            "id": str(e.id),
            "fact": e.fact,
            "source": e.source,
            "source_id": e.source_id,
            "confidence": e.confidence,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


@router.delete("/semantic/{fact_id}")
async def delete_fact(
    fact_id: str,
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    """Delete a semantic fact by ID."""
    service = SemanticMemoryService(db)
    deleted = await service.delete_fact(fact_id=fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Fact {fact_id!r} not found")
    return {"deleted": True, "fact_id": fact_id}


# ── Procedural Memory ───────────────────────────────────────────────────────


@router.post("/procedural")
async def create_procedure(
    name: str = Query(..., min_length=1, max_length=255),
    content: str = Query(..., min_length=1),
    description: str = Query(""),
    tags: str = Query(""),  # comma-separated
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    """Create a new procedure."""
    service = ProceduralMemoryService(db)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    entry = await service.create(
        name=name,
        content=content,
        description=description,
        tags=tag_list,
    )
    return {
        "id": str(entry.id),
        "name": entry.name,
        "description": entry.description,
        "tags": entry.tags,
    }


@router.get("/procedural/{name}")
async def get_procedure(
    name: str,
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    """Get a procedure by name."""
    service = ProceduralMemoryService(db)
    entry = await service.get_by_name(name=name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Procedure {name!r} not found")
    return {
        "id": str(entry.id),
        "name": entry.name,
        "description": entry.description,
        "content": entry.content,
        "tags": entry.tags,
        "usage_count": entry.usage_count,
    }


@router.get("/procedural")
async def list_procedures(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(_get_db),
) -> list[dict[str, Any]]:
    """List all procedures."""
    service = ProceduralMemoryService(db)
    entries = await service.list_all(limit=limit, offset=offset)
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "description": e.description,
            "tags": e.tags,
            "usage_count": e.usage_count,
            "updated_at": e.updated_at.isoformat(),
        }
        for e in entries
    ]
