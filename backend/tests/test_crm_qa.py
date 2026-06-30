"""CRM Q&A Tests — Iteration 14.

Tests cover:
- CRM entity extraction (regex + fuzzy matching)
- CRM context building
- Cross-reference with document chunks
- CRM quick-query presets
- CRM-aware routing via the LangGraph pipeline
"""

from __future__ import annotations

from datetime import UTC

import pytest

from app.agents.crm_context import (
    build_crm_context,
    build_cross_references,
    classify_crm_intent,
    extract_entity_names,
    is_crm_query,
)

# ── CRM query detection ──────────────────────────────────────────────────────


class TestIsCRMQuery:
    """Verify that is_crm_query correctly flags CRM-related queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "Show me all contacts",
            "What deals are in the pipeline?",
            "List recent activities",
            "Who is John Smith?",
            "Top deals by value",
            "CRM contacts",
            "Hot leads in negotiation stage",
            "Pipeline summary",
        ],
    )
    def test_detects_crm_queries(self, query: str) -> None:
        assert is_crm_query(query), f"Should detect CRM query: {query!r}"

    @pytest.mark.parametrize(
        "query",
        [
            "What is XDG?",
            "Hello",
            "Define backpropagation",
            "",
            "How does LangGraph work?",
            "Compare RAG and fine-tuning",
        ],
    )
    def test_ignores_non_crm_queries(self, query: str) -> None:
        assert not is_crm_query(query), f"Should NOT flag as CRM: {query!r}"


# ── CRM intent classification ────────────────────────────────────────────────


class TestClassifyCRMIntent:
    """Verify intent classification for CRM queries."""

    def test_contact_intent(self) -> None:
        assert classify_crm_intent("Who is John Doe?") == "contact"
        assert classify_crm_intent("Show me contact info") == "contact"
        assert classify_crm_intent("Find customer by email") == "contact"

    def test_deal_intent(self) -> None:
        assert classify_crm_intent("Show top deals") in ("deal", "quick_query")
        assert classify_crm_intent("Pipeline stages") == "deal"
        assert classify_crm_intent("What is the deal value?") in ("deal", "quick_query")

    def test_activity_intent(self) -> None:
        assert classify_crm_intent("Recent activities") in ("activity", "quick_query")
        assert classify_crm_intent("Show calls from yesterday") == "activity"

    def test_cross_reference_intent(self) -> None:
        result = classify_crm_intent("What deals relate to the contract document?")
        assert result == "cross_reference"

    def test_quick_query_intent(self) -> None:
        # "List all deals" mentions a specific entity → classified as deal intent
        result = classify_crm_intent("List all deals")
        assert result == "deal"

    def test_list_without_entity_is_quick_query(self) -> None:
        result = classify_crm_intent("List everything")
        assert result == "quick_query"

    def test_non_crm_query(self) -> None:
        assert classify_crm_intent("What is the meaning of life?") == "none"


# ── Entity extraction ────────────────────────────────────────────────────────


class TestExtractEntityNames:
    """Verify entity name extraction via regex and fuzzy matching."""

    def test_empty_db_names(self) -> None:
        entities = extract_entity_names("Show me contact John Doe", [])
        # Should still extract via regex even with empty DB
        assert any(e["name"] == "John Doe" for e in entities)

    def test_regex_contact_extraction(self) -> None:
        entities = extract_entity_names("contact Jane Smith", ["Jane Smith"])
        names = [e["name"] for e in entities]
        assert "Jane Smith" in names or any("Jane" in n for n in names)

    def test_regex_deal_extraction(self) -> None:
        entities = extract_entity_names("deal Acme Project 2024", ["Acme Project 2024"])
        names = [e["name"] for e in entities]
        assert any("Acme" in n for n in names)

    def test_fuzzy_matching(self) -> None:
        # Fuzzy matching should find "Jon Smit" close to "John Smith"
        entities = extract_entity_names("Jon Smit", ["John Smith"])
        fuzzy_ents = [e for e in entities if e.get("method") == "fuzzy"]
        assert any(e["confidence"] >= 0.6 for e in fuzzy_ents)

    def test_no_entities(self) -> None:
        # Generic queries that aren't CRM-related should return no entities
        entities = extract_entity_names("What is the weather?", [])
        assert entities == []
        # Also test short queries
        entities = extract_entity_names("hello", [])
        assert entities == []


# ── CRM context building ──────────────────────────────────────────────────────


class TestBuildCRMContext:
    """Verify CRM context string generation."""

    def test_contact_context(self) -> None:
        """Test building context for contact intent."""
        from app.models.crm import CrmContact

        contacts = [
            CrmContact(
                external_id="c1",
                name="Alice Wonderland",
                email="alice@example.com",
                phone="+1-555-0101",
                company="Wonderland Inc.",
            ),
        ]
        context = build_crm_context(contacts, [], [], "contact")
        assert "Alice Wonderland" in context
        assert "alice@example.com" in context
        assert "Wonderland Inc." in context
        assert "CRM Contacts" in context

    def test_deal_context(self) -> None:
        """Test building context for deal intent."""
        from app.models.crm import CrmDeal

        deals = [
            CrmDeal(
                external_id="d1",
                name="Enterprise License",
                value=50000.0,
                stage="negotiation",
            ),
        ]
        context = build_crm_context([], deals, [], "deal")
        assert "Enterprise License" in context
        assert "$50,000" in context
        assert "negotiation" in context

    def test_activity_context(self) -> None:
        """Test building context for activity intent."""
        from datetime import datetime

        from app.models.crm import CrmActivity

        activities = [
            CrmActivity(
                external_id="a1",
                type="call",
                description="Discussed contract terms",
                date=datetime.now(UTC),
            ),
        ]
        context = build_crm_context([], [], activities, "activity")
        assert "call" in context
        assert "Discussed contract terms" in context

    def test_empty_context(self) -> None:
        """Test context generation when no data matches."""
        context = build_crm_context([], [], [], "deal")
        assert "CRM Deals" not in context or context == ""
        assert not context or "CRM" not in context

    def test_summary_fallback(self) -> None:
        """Test that when intent doesn't match but data exists, a summary is shown."""
        from app.models.crm import CrmContact

        contacts = [
            CrmContact(
                external_id="c1",
                name="Bob Builder",
                email="bob@build.com",
                phone="",
                company="Build Co",
            ),
        ]
        # "quick_query" intent should fall back to summary
        context = build_crm_context(contacts, [], [], "quick_query")
        assert "Bob Builder" in context


# ── Cross-referencing ────────────────────────────────────────────────────────


class TestBuildCrossReferences:
    """Verify cross-referencing between CRM entities and document chunks."""

    def test_direct_match(self) -> None:
        entities = [{"name": "Acme Corp", "type": "company", "confidence": 0.9}]
        chunks = [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "content": "The contract with Acme Corp was signed in Q1.",
            },
        ]
        refs = build_cross_references(entities, chunks)
        assert len(refs) == 1
        assert refs[0]["entity"] == "Acme Corp"
        assert refs[0]["chunk_id"] == "chunk-1"

    def test_no_match(self) -> None:
        entities = [{"name": "Acme Corp", "type": "company", "confidence": 0.9}]
        chunks = [
            {
                "id": "chunk-2",
                "document_id": "doc-2",
                "content": "Some unrelated document content here.",
            },
        ]
        refs = build_cross_references(entities, chunks)
        assert len(refs) == 0

    def test_multiple_matches(self) -> None:
        entities = [
            {"name": "Acme Corp", "type": "company", "confidence": 0.9},
            {"name": "John Doe", "type": "contact", "confidence": 0.8},
        ]
        chunks = [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "content": "Meeting with John Doe about Acme Corp partnership.",
            },
        ]
        refs = build_cross_references(entities, chunks)
        # Both entity names appear in the chunk — expect 2 matches
        assert len(refs) == 2
        assert refs[0]["entity"] in ("Acme Corp", "John Doe")
        assert refs[1]["entity"] in ("Acme Corp", "John Doe")

    def test_empty_inputs(self) -> None:
        assert (
            build_cross_references([], [{"id": "c1", "document_id": "d1", "content": "test"}]) == []
        )
        assert build_cross_references([{"name": "test"}], []) == []


# ── CRM quick-query presets (API-level validation) ────────────────────────────


class TestCRMPresets:
    """Verify CRM quick-query preset definitions."""

    def test_presets_defined(self) -> None:
        from app.api.qa import CRM_PRESETS

        assert len(CRM_PRESETS) >= 5, "Should have at least 5 CRM presets"
        expected_keys = {"top_deals", "recent_activities", "deals_by_stage", "contacts_list"}
        assert expected_keys.issubset(set(CRM_PRESETS.keys()))

    def test_preset_shape(self) -> None:
        from app.api.qa import CRM_PRESETS

        for key, preset in CRM_PRESETS.items():
            assert "label" in preset, f"Preset {key} missing label"
            assert "description" in preset, f"Preset {key} missing description"
            assert "query" in preset, f"Preset {key} missing query"
            assert len(preset["label"]) > 0
            assert len(preset["query"]) > 0

    def test_preset_queries_are_crm_related(self) -> None:
        from app.api.qa import CRM_PRESETS

        for key, preset in CRM_PRESETS.items():
            query = preset["query"]
            assert is_crm_query(query), f"Preset {key} query is not CRM-related: {query!r}"

    def test_crm_preset_schema(self) -> None:
        from pydantic import ValidationError

        from app.api.qa import CRMPresetOut, CRMPresetsResponse

        # Valid preset
        preset = CRMPresetOut(key="test", label="Test", description="A test", query="Show contacts")
        assert preset.key == "test"

        # Missing field should fail
        with pytest.raises(ValidationError):
            CRMPresetOut(key="test")  # type: ignore[call-arg]

        # Response model
        resp = CRMPresetsResponse(presets=[preset])
        assert len(resp.presets) == 1

    def test_quick_query_schema(self) -> None:
        from pydantic import ValidationError

        from app.api.qa import CRMQuickQueryRequest, CRMQuickQueryResponse

        # Valid request with minimal fields
        req = CRMQuickQueryRequest(query="Show me deals")
        assert req.query == "Show me deals"

        # Valid request with preset
        req = CRMQuickQueryRequest(preset="top_deals", query="anything")
        assert req.preset == "top_deals"

        # Empty query should fail
        with pytest.raises(ValidationError):
            CRMQuickQueryRequest(query="")

        # Response model
        resp = CRMQuickQueryResponse(
            intent="deal",
            data={"deals": []},
            summary="Found 0 deals.",
            formatted="**Deals:** none",
        )
        assert resp.intent == "deal"


# ── Router routing (integration contract) ─────────────────────────────────────


class TestCRMRouting:
    """Verify that CRM queries are routed through the CRM context agent."""

    def test_crm_routing_after_router(self) -> None:
        """CRM queries should route to crm_context, not directly to retriever."""
        from app.agents.state_graph import _route_after_router

        # A CRM-related query_type should still come from the router
        state = {"query_type": "hybrid"}
        assert _route_after_router(state) == "crm_context"

    def test_greeting_still_routes_to_synthesizer(self) -> None:
        """Greeting queries should skip CRM and go straight to synthesizer."""
        from app.agents.state_graph import _route_after_router

        state = {"query_type": "greeting"}
        assert _route_after_router(state) == "synthesizer"

    def test_irrelevant_still_routes_to_synthesizer(self) -> None:
        from app.agents.state_graph import _route_after_router

        state = {"query_type": "irrelevant"}
        assert _route_after_router(state) == "synthesizer"

    def test_crm_routes_to_retriever(self) -> None:
        """CRM context agent, when done, routes to retriever."""
        from app.agents.state_graph import _route_after_crm

        state = {}
        assert _route_after_crm(state) == "retriever"

    def test_crm_error_routes_to_synthesizer(self) -> None:
        from app.agents.state_graph import _route_after_crm

        state = {"error": "CRM DB unavailable"}
        assert _route_after_crm(state) == "synthesizer"
