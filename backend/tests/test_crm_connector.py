"""Tests for CRM connector: adapters, orchestrator, upsert logic."""

import pytest
from sqlalchemy import select

from app.connectors.adapters.mock import MockCRMAdapter
from app.connectors.crm import CRMOrchestrator, _get_adapter
from app.core.config import Settings
from app.models.crm import CrmActivity, CrmContact, CrmDeal


class TestMockCRMAdapter:
    """Unit tests for the mock adapter (no DB needed)."""

    async def test_sync_returns_triple(self):
        adapter = MockCRMAdapter(seed=42)
        contacts, deals, activities = await adapter.sync()
        assert len(contacts) == 20
        assert len(deals) == 30
        assert len(activities) == 50
        assert all(c.name for c in contacts)
        assert all(d.stage for d in deals)
        assert all(a.type for a in activities)

    async def test_get_contacts_pagination(self):
        adapter = MockCRMAdapter(seed=42)
        items, total = await adapter.get_contacts(offset=0, limit=5)
        assert len(items) == 5
        assert total == 50

    async def test_get_contacts_search(self):
        adapter = MockCRMAdapter(seed=42)
        items, total = await adapter.get_contacts(offset=0, limit=50, search="Alice")
        # Alice is in FIRST_NAMES, should match some
        assert any("Alice" in c.name for c in items)

    async def test_get_deals_filter_by_stage(self):
        adapter = MockCRMAdapter(seed=42)
        items, total = await adapter.get_deals(offset=0, limit=50, stage="closed_won")
        assert all(d.stage == "closed_won" for d in items)
        assert total == len(items)

    async def test_get_deals_filter_by_min_value(self):
        adapter = MockCRMAdapter(seed=42)
        items, total = await adapter.get_deals(offset=0, limit=50, min_value=100_000)
        assert all((d.value or 0) >= 100_000 for d in items)

    async def test_get_activities_filter_by_contact(self):
        adapter = MockCRMAdapter(seed=42)
        items, total = await adapter.get_activities(
            offset=0, limit=50, contact_external_id="mock-contact-0",
        )
        assert all(a.contact_external_id == "mock-contact-0" for a in items)


class TestCRMOrchestrator:
    """Integration tests: orchestrator with in-memory SQLite."""

    async def test_sync_persists_contacts(self, _setup_database, _clean_db, client):
        """Run a full sync via the orchestrator and verify DB records."""
        from tests.conftest import TEST_SESSION_FACTORY

        settings = Settings(CRM_ADAPTER="mock", CRM_RAG_BRIDGE=False)
        async with TEST_SESSION_FACTORY() as db:
            orchestrator = CRMOrchestrator(db, settings)
            stats = await orchestrator.sync()

            assert stats["contacts_synced"] == 20
            assert stats["deals_synced"] == 30
            assert stats["activities_synced"] == 50

        # Verify via the API
        resp = await client.get("/connectors/crm/contacts?limit=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 20
        assert len(data["items"]) == 20

    async def test_sync_upserts_not_duplicates(self, _setup_database, _clean_db, client):
        """Running sync twice should upsert, not duplicate."""
        from tests.conftest import TEST_SESSION_FACTORY

        settings = Settings(CRM_ADAPTER="mock", CRM_RAG_BRIDGE=False)
        async with TEST_SESSION_FACTORY() as db:
            orchestrator = CRMOrchestrator(db, settings)
            await orchestrator.sync()  # First sync
            stats = await orchestrator.sync()  # Second sync — should be all updates

            # Counts should be the same (upserts, not inserts)
            assert stats["contacts_synced"] == 20

            # DB should still have exactly 20 contacts
            result = await db.execute(select(CrmContact))
            contacts = result.scalars().all()
            assert len(contacts) == 20

    async def test_rag_bridge_enabled(self, _setup_database, _clean_db, client):
        """When CRM_RAG_BRIDGE=true, Document+Chunk rows are created."""
        from tests.conftest import TEST_SESSION_FACTORY
        from app.models.chunk import Chunk
        from app.models.document import Document

        settings = Settings(CRM_ADAPTER="mock", CRM_RAG_BRIDGE=True)
        async with TEST_SESSION_FACTORY() as db:
            orchestrator = CRMOrchestrator(db, settings)
            stats = await orchestrator.sync()

            assert "rag_documents_created" in stats
            assert stats["rag_documents_created"] > 0
            assert stats["rag_chunks_created"] > 0

            # Verify Document records exist with correct source metadata
            docs_result = await db.execute(
                select(Document).where(Document.doc_metadata["source"].as_string() == "crm-contact")
            )
            docs = docs_result.scalars().all()
            assert len(docs) > 0

            # Verify Chunks exist
            chunks_result = await db.execute(select(Chunk))
            chunks = chunks_result.scalars().all()
            assert len(chunks) > 0


class TestCRMAdapterSelection:
    """Tests for adapter selection logic."""

    def test_default_adapter_is_mock(self):
        settings = Settings(CRM_ADAPTER="mock")
        adapter = _get_adapter(settings)
        assert isinstance(adapter, MockCRMAdapter)

    def test_unknown_adapter_falls_back_to_mock(self):
        settings = Settings(CRM_ADAPTER="salesforce")
        adapter = _get_adapter(settings)
        assert isinstance(adapter, MockCRMAdapter)
