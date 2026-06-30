"""Tests for CRM API endpoints."""

import pytest


class TestCRMAPISync:
    """Tests for POST /connectors/crm/sync."""

    async def test_sync_returns_202(self, client):
        resp = await client.post("/connectors/crm/sync")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "CRM sync started" in data["message"]


class TestCRMAPIContacts:
    """Tests for GET /connectors/crm/contacts."""

    async def test_contacts_empty_when_no_sync(self, client):
        resp = await client.get("/connectors/crm/contacts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.usefixtures("_sync_crm")
    async def test_contacts_paginated(self, client):
        resp = await client.get("/connectors/crm/contacts?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 20
        assert len(data["items"]) == 5
        assert data["offset"] == 0
        assert data["limit"] == 5

    @pytest.mark.usefixtures("_sync_crm")
    async def test_contacts_search(self, client):
        resp = await client.get("/connectors/crm/contacts?search=Acme")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert (
                "Acme" in (item.get("company") or "")
                or "Acme" in (item.get("name") or "")
                or "Acme" in (item.get("email") or "")
            ), f"Expected 'Acme' in one of name/email/company, got {item}"


class TestCRMAPIDeals:
    """Tests for GET /connectors/crm/deals."""

    async def test_deals_empty_when_no_sync(self, client):
        resp = await client.get("/connectors/crm/deals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.usefixtures("_sync_crm")
    async def test_deals_paginated(self, client):
        resp = await client.get("/connectors/crm/deals?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 30
        assert len(data["items"]) == 10

    @pytest.mark.usefixtures("_sync_crm")
    async def test_deals_filter_by_stage(self, client):
        resp = await client.get("/connectors/crm/deals?stage=closed_won")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        for item in data["items"]:
            assert item["stage"] == "closed_won"

    @pytest.mark.usefixtures("_sync_crm")
    async def test_deals_filter_by_min_value(self, client):
        resp = await client.get("/connectors/crm/deals?min_value=100000")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert (item["value"] or 0) >= 100000


class TestCRMAPIActivities:
    """Tests for GET /connectors/crm/activities."""

    async def test_activities_empty_when_no_sync(self, client):
        resp = await client.get("/connectors/crm/activities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.usefixtures("_sync_crm")
    async def test_activities_paginated(self, client):
        resp = await client.get("/connectors/crm/activities?limit=15")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 50
        assert len(data["items"]) == 15


class TestCRMStandalone:
    """Verify no RAG dependency in CRM path — standalone imports."""

    def test_crm_api_imports_no_rag(self):
        """The connectors API module should not import anything from retrieval/agents."""
        import ast

        with open("app/api/connectors.py") as f:
            tree = ast.parse(f.read())

        rag_modules = {"retrieval", "agents", "reranker", "embeddings"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in rag_modules, (
                        f"connectors.py imports {alias.name} — CRM must be RAG-free"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in rag_modules, (
                    f"connectors.py imports from {node.module} — CRM must be RAG-free"
                )
