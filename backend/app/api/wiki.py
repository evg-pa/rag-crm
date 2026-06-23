"""Wiki REST API endpoints.

GET  /wiki              — list all wiki entries (paginated)
GET  /wiki/{document_id} — get a specific wiki entry
POST /wiki/refresh/{document_id} — regenerate summary for a document
GET  /wiki/search       — search wiki entries by keyword (query param `q`)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session
from app.knowledge.wiki_service import WikiService

router = APIRouter(prefix="/wiki", tags=["wiki"])


# ── Pydantic schemas ────────────────────────────────────────────────────────


class WikiEntryOut(BaseModel):
    """Wiki entry in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    summary: str
    topics: list[str] = Field(default_factory=list)
    created_at: str  # ISO 8601 string
    updated_at: str  # ISO 8601 string


class WikiEntryListOut(BaseModel):
    """Paginated list of wiki entries."""

    entries: list[WikiEntryOut]
    total: int
    page: int
    page_size: int


class WikiEntryRefreshOut(BaseModel):
    """Response after a wiki entry refresh."""

    entry: WikiEntryOut
    regenerated: bool = True


# ── Helpers ──────────────────────────────────────────────────────────────────


def _wiki_entry_to_out(entry) -> WikiEntryOut:
    """Convert a WikiEntry ORM model to a WikiEntryOut schema."""
    return WikiEntryOut(
        id=entry.id,
        document_id=entry.document_id,
        summary=entry.summary,
        topics=entry.topics,
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=WikiEntryListOut)
async def list_wiki_entries(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Entries per page"),
    db: AsyncSession = Depends(get_db_session),
) -> WikiEntryListOut:
    """List all wiki entries with pagination.

    Returns entries ordered by most recently updated first.
    """
    service = WikiService(db)
    try:
        entries, total = await service.list_entries(page=page, page_size=page_size)
        return WikiEntryListOut(
            entries=[_wiki_entry_to_out(e) for e in entries],
            total=total,
            page=page,
            page_size=page_size,
        )
    finally:
        await service.close()


@router.get("/search", response_model=list[WikiEntryOut])
async def search_wiki_entries(
    q: str = Query(..., min_length=1, description="Search query"),
    db: AsyncSession = Depends(get_db_session),
) -> list[WikiEntryOut]:
    """Search wiki entries by keyword across summary and topics."""
    service = WikiService(db)
    try:
        entries = await service.search_entries(q)
        return [_wiki_entry_to_out(e) for e in entries]
    finally:
        await service.close()


@router.get("/{document_id}", response_model=WikiEntryOut)
async def get_wiki_entry(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> WikiEntryOut:
    """Get the wiki entry for a specific document."""
    service = WikiService(db)
    try:
        entry = await service.get_entry(document_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wiki entry for document {document_id} not found.",
            )
        return _wiki_entry_to_out(entry)
    finally:
        await service.close()


@router.post(
    "/refresh/{document_id}",
    response_model=WikiEntryRefreshOut,
    status_code=status.HTTP_200_OK,
)
async def refresh_wiki_entry(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> WikiEntryRefreshOut:
    """Regenerate the wiki summary for a document.

    This calls the KnowledgeAgent to produce a fresh summary and topics.
    """
    service = WikiService(db)
    try:
        entry = await service.refresh_entry(document_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found.",
            )
        return WikiEntryRefreshOut(
            entry=_wiki_entry_to_out(entry),
            regenerated=True,
        )
    finally:
        await service.close()
