"""CRM orchestrator — picks the adapter, runs sync, persists data.

The orchestrator is adapter-agnostic: it works with any BaseCRMAdapter
implementation (mock, REST, etc.).

Sync performs upserts by external_id so the same record is never
duplicated across sync runs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.adapters.base import (
    ActivityData,
    BaseCRMAdapter,
    ContactData,
    DealData,
)
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.crm import CrmActivity, CrmContact, CrmDeal

logger = get_logger(__name__)


def _get_adapter(settings: Settings) -> BaseCRMAdapter:
    """Return the configured CRM adapter instance."""
    adapter_name = settings.CRM_ADAPTER
    if adapter_name == "rest":
        from app.connectors.adapters.rest import RestCRMAdapter

        return RestCRMAdapter(base_url=settings.CRM_REST_BASE_URL)
    else:
        from app.connectors.adapters.mock import MockCRMAdapter

        return MockCRMAdapter()


class CRMOrchestrator:
    """Coordinates CRM syncs: fetch → upsert → optional RAG bridge."""

    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._adapter = _get_adapter(settings)

    @property
    def adapter(self) -> BaseCRMAdapter:
        return self._adapter

    async def sync(self) -> dict:
        """Run a full sync: fetch all records from the adapter and upsert them.

        Returns a dict with counts per entity type.
        """
        contacts, deals, activities = await self._adapter.sync()

        contact_count = await self._upsert_contacts(contacts)
        deal_count = await self._upsert_deals(deals)
        activity_count = await self._upsert_activities(activities)

        stats = {
            "contacts_synced": contact_count,
            "deals_synced": deal_count,
            "activities_synced": activity_count,
        }
        logger.info("CRM sync complete", extra=stats)

        # Optional RAG bridge
        if self._settings.CRM_RAG_BRIDGE:
            rag_stats = await self._build_rag_bridge()
            stats.update(rag_stats)

        return stats

    # ── Upsert helpers ───────────────────────────────────────────────────

    async def _upsert_contacts(self, contacts: list[ContactData]) -> int:
        count = 0
        for c in contacts:
            existing = await self._db.execute(
                select(CrmContact).where(CrmContact.external_id == c.external_id)
            )
            existing = existing.scalar_one_or_none()

            if existing:
                existing.name = c.name
                existing.email = c.email
                existing.phone = c.phone
                existing.company = c.company
            else:
                self._db.add(
                    CrmContact(
                        external_id=c.external_id,
                        name=c.name,
                        email=c.email,
                        phone=c.phone,
                        company=c.company,
                    )
                )
            count += 1
        await self._db.commit()
        return count

    async def _upsert_deals(self, deals: list[DealData]) -> int:
        # Build a mapping from contact external_id → contact DB id
        contact_map: dict[str, uuid.UUID] = {}
        if deals:
            ext_ids = list({d.contact_external_id for d in deals if d.contact_external_id})
            if ext_ids:
                result = await self._db.execute(
                    select(CrmContact.external_id, CrmContact.id).where(
                        CrmContact.external_id.in_(ext_ids)
                    )
                )
                contact_map = {row[0]: row[1] for row in result.all()}

        count = 0
        for d in deals:
            existing = await self._db.execute(
                select(CrmDeal).where(CrmDeal.external_id == d.external_id)
            )
            existing = existing.scalar_one_or_none()

            if existing:
                existing.name = d.name
                existing.value = d.value
                existing.stage = d.stage
                existing.close_date = d.close_date
                if d.contact_external_id and d.contact_external_id in contact_map:
                    existing.contact_id = contact_map[d.contact_external_id]
            else:
                contact_id = (
                    contact_map.get(d.contact_external_id) if d.contact_external_id else None
                )
                self._db.add(
                    CrmDeal(
                        external_id=d.external_id,
                        name=d.name,
                        value=d.value,
                        stage=d.stage,
                        close_date=d.close_date,
                        contact_id=contact_id,
                    )
                )
            count += 1
        await self._db.commit()
        return count

    async def _upsert_activities(self, activities: list[ActivityData]) -> int:
        # Build a mapping from contact external_id → contact DB id
        contact_map: dict[str, uuid.UUID] = {}
        if activities:
            ext_ids = list({a.contact_external_id for a in activities if a.contact_external_id})
            if ext_ids:
                result = await self._db.execute(
                    select(CrmContact.external_id, CrmContact.id).where(
                        CrmContact.external_id.in_(ext_ids)
                    )
                )
                contact_map = {row[0]: row[1] for row in result.all()}

        count = 0
        for a in activities:
            existing = await self._db.execute(
                select(CrmActivity).where(CrmActivity.external_id == a.external_id)
            )
            existing = existing.scalar_one_or_none()

            if existing:
                existing.type = a.type
                existing.description = a.description
                existing.date = a.date
                if a.contact_external_id and a.contact_external_id in contact_map:
                    existing.contact_id = contact_map[a.contact_external_id]
            else:
                contact_id = (
                    contact_map.get(a.contact_external_id) if a.contact_external_id else None
                )
                self._db.add(
                    CrmActivity(
                        external_id=a.external_id,
                        type=a.type,
                        description=a.description,
                        date=a.date,
                        contact_id=contact_id,
                    )
                )
            count += 1
        await self._db.commit()
        return count

    # ── Optional RAG bridge ──────────────────────────────────────────────

    async def _build_rag_bridge(self) -> dict:
        """Convert CRM entities to Document+Chunk records for RAG search.

        Each CRM entity becomes a Document with ``source`` metadata set to
        ``crm-contact``, ``crm-deal``, or ``crm-activity``.  A single
        Chunk is created per entity so the existing hybrid search can
        pick them up.
        """

        stats = {"rag_documents_created": 0, "rag_chunks_created": 0}

        # ── Contacts ──
        contacts_result = await self._db.execute(select(CrmContact))
        for contact in contacts_result.scalars().all():
            text = (
                f"CRM Contact: {contact.name}\n"
                f"Email: {contact.email or 'N/A'}\n"
                f"Phone: {contact.phone or 'N/A'}\n"
                f"Company: {contact.company or 'N/A'}"
            )
            await self._create_rag_document(
                source="crm-contact",
                external_id=contact.external_id,
                title=f"Contact: {contact.name}",
                text=text,
            )
            stats["rag_documents_created"] += 1
            stats["rag_chunks_created"] += 1

        # ── Deals ──
        deals_result = await self._db.execute(select(CrmDeal))
        for deal in deals_result.scalars().all():
            text = (
                f"CRM Deal: {deal.name}\nValue: ${deal.value:,.2f}"
                if deal.value
                else "Value: N/A" + "\n"
                f"Stage: {deal.stage}\n"
                f"Close Date: {deal.close_date.isoformat() if deal.close_date else 'N/A'}"
            )
            await self._create_rag_document(
                source="crm-deal",
                external_id=deal.external_id,
                title=f"Deal: {deal.name}",
                text=text,
            )
            stats["rag_documents_created"] += 1
            stats["rag_chunks_created"] += 1

        # ── Activities ──
        activities_result = await self._db.execute(select(CrmActivity))
        for activity in activities_result.scalars().all():
            text = (
                f"CRM Activity: {activity.type}\n"
                f"Date: {activity.date.isoformat()}\n"
                f"Description: {activity.description}"
            )
            await self._create_rag_document(
                source="crm-activity",
                external_id=activity.external_id,
                title=f"Activity: {activity.type} — {activity.date.date().isoformat()}",
                text=text,
            )
            stats["rag_documents_created"] += 1
            stats["rag_chunks_created"] += 1

        await self._db.commit()
        logger.info("RAG bridge built", extra=stats)
        return stats

    async def _create_rag_document(
        self,
        *,
        source: str,
        external_id: str,
        title: str,
        text: str,
    ) -> None:
        """Create a Document + Chunk for a single CRM entity.

        Uses ON CONFLICT-style dedup: if a Document with the same
        ``filename`` (derived from source+external_id) already exists, we
        skip creation — the document was already bridged in a prior sync.
        """
        from app.models.chunk import Chunk
        from app.models.document import Document

        filename = f"crm://{source}/{external_id}"

        existing = await self._db.execute(select(Document).where(Document.filename == filename))
        if existing.scalar_one_or_none() is not None:
            return  # Already bridged

        doc = Document(
            filename=filename,
            content_type="text/plain",
            file_size=len(text.encode("utf-8")),
            doc_metadata={"source": source, "crm_external_id": external_id, "title": title},
        )
        self._db.add(doc)
        await self._db.flush()

        chunk = Chunk(
            document_id=doc.id,
            chunk_index=0,
            content=text,
        )
        self._db.add(chunk)
