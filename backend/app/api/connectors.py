"""CRM Connector REST endpoints.

POST /connectors/crm/sync         — trigger a full CRM sync (202 accepted)
GET  /connectors/crm/contacts     — paginated contact list
GET  /connectors/crm/deals        — filtered deal list
GET  /connectors/crm/activities   — paginated activity list
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
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
from app.models.crm import CrmActivity, CrmContact, CrmDeal

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


class SyncStatusResponse(BaseModel):
    contacts_synced: int
    deals_synced: int
    activities_synced: int


# ── Shared adapter getter ──────────────────────────────────────────────────

def _get_crm_adapter(settings: Settings = Depends(get_settings)) -> BaseCRMAdapter:
    return _get_adapter(settings)


# ── Background sync task ───────────────────────────────────────────────────


async def _run_sync(db: AsyncSession, settings: Settings) -> dict:
    """Run a full CRM sync using the provided DB session."""
    orchestrator = CRMOrchestrator(db, settings)
    return await orchestrator.sync()


# ── Endpoints ───────────────────────────────────────────────────────────────


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
