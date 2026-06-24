"""CRM Connector REST endpoints.

POST /connectors/crm/sync         — trigger a full CRM sync (202 accepted)
GET  /connectors/crm/contacts     — paginated contact list
GET  /connectors/crm/deals        — filtered deal list
GET  /connectors/crm/activities   — paginated activity list
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_db_session, get_settings
from app.core.logging import get_logger
from app.connectors.adapters.base import BaseCRMAdapter, ContactData, DealData, ActivityData
from app.connectors.crm import CRMOrchestrator, _get_adapter
from app.models.crm import CrmActivity, CrmContact, CrmDeal, CrmSyncRun

logger = get_logger(__name__)

router = APIRouter(prefix="/connectors/crm", tags=["crm"])


# ── Pydantic schemas ────────────────────────────────────────────────────────


class ContactOut(BaseModel):
    """CRM Contact in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    created_at: datetime


class DealOut(BaseModel):
    """CRM Deal in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    name: str
    value: float | None = None
    stage: str
    close_date: datetime | None = None
    contact_id: uuid.UUID | None = None
    created_at: datetime


class ActivityOut(BaseModel):
    """CRM Activity in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    type: str
    description: str
    date: datetime
    contact_id: uuid.UUID | None = None
    created_at: datetime


class PaginatedContacts(BaseModel):
    items: list[ContactOut]
    total: int
    offset: int
    limit: int


class PaginatedDeals(BaseModel):
    items: list[DealOut]
    total: int
    offset: int
    limit: int


class PaginatedActivities(BaseModel):
    items: list[ActivityOut]
    total: int
    offset: int
    limit: int


class SyncResponse(BaseModel):
    status: str = "accepted"
    message: str = "CRM sync started"


class SyncStatusOut(BaseModel):
    """Full sync status for the status widget."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    contacts_synced: int = 0
    deals_synced: int = 0
    activities_synced: int = 0
    rag_documents_created: int = 0
    rag_chunks_created: int = 0
    error_message: str | None = None
    # Live counts from current DB state
    total_contacts: int = 0
    total_deals: int = 0
    total_activities: int = 0


# ── Shared adapter getter ──────────────────────────────────────────────────

def _get_crm_adapter(settings: Settings = Depends(get_settings)) -> BaseCRMAdapter:
    return _get_adapter(settings)


# ── Background sync task ───────────────────────────────────────────────────


async def _run_sync(db: AsyncSession, settings: Settings) -> dict:
    """Run a full CRM sync using the provided DB session.

    Creates a CrmSyncRun record and updates it on completion or error.
    """
    run = CrmSyncRun(status="running", started_at=datetime.now(UTC))
    db.add(run)
    await db.commit()

    try:
        orchestrator = CRMOrchestrator(db, settings)
        stats = await orchestrator.sync()

        run.status = "success"
        run.completed_at = datetime.now(UTC)
        run.contacts_synced = stats.get("contacts_synced", 0)
        run.deals_synced = stats.get("deals_synced", 0)
        run.activities_synced = stats.get("activities_synced", 0)
        run.rag_documents_created = stats.get("rag_documents_created", 0)
        run.rag_chunks_created = stats.get("rag_chunks_created", 0)
        await db.commit()
        return stats
    except Exception as exc:
        run.status = "error"
        run.completed_at = datetime.now(UTC)
        run.error_message = str(exc)
        await db.commit()
        logger.exception("CRM sync failed")
        raise


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/sync/status", response_model=SyncStatusOut)
async def get_sync_status(
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Return the latest CRM sync run status plus current record counts."""

    # Latest sync run
    result = await db.execute(
        select(CrmSyncRun)
        .order_by(CrmSyncRun.completed_at.desc().nullslast())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    # Current counts
    contacts_total = await db.execute(select(func.count(CrmContact.id)))
    deals_total = await db.execute(select(func.count(CrmDeal.id)))
    activities_total = await db.execute(select(func.count(CrmActivity.id)))

    if latest is None:
        # Return a stub — no sync has ever run
        return SyncStatusOut(
            id=uuid.uuid4(),
            status="never",
            total_contacts=contacts_total.scalar() or 0,
            total_deals=deals_total.scalar() or 0,
            total_activities=activities_total.scalar() or 0,
        )

    return SyncStatusOut(
        id=latest.id,
        status=latest.status,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
        contacts_synced=latest.contacts_synced,
        deals_synced=latest.deals_synced,
        activities_synced=latest.activities_synced,
        rag_documents_created=latest.rag_documents_created,
        rag_chunks_created=latest.rag_chunks_created,
        error_message=latest.error_message,
        total_contacts=contacts_total.scalar() or 0,
        total_deals=deals_total.scalar() or 0,
        total_activities=activities_total.scalar() or 0,
    )


@router.post("/sync", response_model=SyncResponse, status_code=status.HTTP_202_ACCEPTED)
async def sync_crm(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Trigger a full CRM sync in the background.

    Returns 202 immediately. The sync runs as a background task.
    """
    background_tasks.add_task(_run_sync, db, settings)
    return SyncResponse()


@router.get("/contacts", response_model=PaginatedContacts)
async def list_contacts(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Search by name, email, or company"),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """List CRM contacts with pagination and optional search."""
    query = select(CrmContact)
    count_query = select(func.count(CrmContact.id))

    if search:
        pattern = f"%{search}%"
        filter_clause = (
            CrmContact.name.ilike(pattern)
            | CrmContact.email.ilike(pattern)
            | CrmContact.company.ilike(pattern)
        )
        query = query.where(filter_clause)
        count_query = count_query.where(filter_clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(CrmContact.name).offset(offset).limit(limit)
    result = await db.execute(query)
    contacts = result.scalars().all()

    return PaginatedContacts(
        items=[ContactOut.model_validate(c) for c in contacts],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/deals", response_model=PaginatedDeals)
async def list_deals(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    stage: str | None = Query(None, description="Filter by stage"),
    min_value: float | None = Query(None, ge=0, description="Minimum deal value"),
    close_date_from: datetime | None = Query(None, description="Close date range start"),
    close_date_to: datetime | None = Query(None, description="Close date range end"),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """List CRM deals with pagination and optional filters."""
    query = select(CrmDeal)
    count_query = select(func.count(CrmDeal.id))

    if stage:
        query = query.where(CrmDeal.stage == stage)
        count_query = count_query.where(CrmDeal.stage == stage)
    if min_value is not None:
        query = query.where(CrmDeal.value >= min_value)
        count_query = count_query.where(CrmDeal.value >= min_value)
    if close_date_from:
        query = query.where(CrmDeal.close_date >= close_date_from)
        count_query = count_query.where(CrmDeal.close_date >= close_date_from)
    if close_date_to:
        query = query.where(CrmDeal.close_date <= close_date_to)
        count_query = count_query.where(CrmDeal.close_date <= close_date_to)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(CrmDeal.name).offset(offset).limit(limit)
    result = await db.execute(query)
    deals = result.scalars().all()

    return PaginatedDeals(
        items=[DealOut.model_validate(d) for d in deals],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/activities", response_model=PaginatedActivities)
async def list_activities(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    contact_id: uuid.UUID | None = Query(None, description="Filter by contact ID"),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """List CRM activities with pagination and optional contact filter."""
    query = select(CrmActivity)
    count_query = select(func.count(CrmActivity.id))

    if contact_id:
        query = query.where(CrmActivity.contact_id == contact_id)
        count_query = count_query.where(CrmActivity.contact_id == contact_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(CrmActivity.date.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    activities = result.scalars().all()

    return PaginatedActivities(
        items=[ActivityOut.model_validate(a) for a in activities],
        total=total,
        offset=offset,
        limit=limit,
    )
