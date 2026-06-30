"""Tests for the Knowledge Graph module (Neo4j)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Entity Extractor tests ────────────────────────────────────────────────────


class TestEntityExtraction:
    """Tests for entity extraction (LLM path is mocked, regex fallback is real)."""

    def test_regex_extracts_person(self):
        """Regex fallback should extract person names with honorifics."""
        from app.knowledge_graph.entity_extractor import _regex_entity_extraction

        text = "Dr. Jane Smith presented at the conference organized by Acme Corp Inc."
        entities = _regex_entity_extraction(text)

        names = [e["name"] for e in entities]
        assert "Jane Smith" in names

    def test_regex_extracts_organization(self):
        """Regex fallback should extract organization names ending with Inc/Corp/LLC."""
        from app.knowledge_graph.entity_extractor import _regex_entity_extraction

        text = "Techno Solutions LLC and Global Dynamics Corp are partners."
        entities = _regex_entity_extraction(text)

        org_names = [e["name"] for e in entities if e["type"] == "ORGANIZATION"]
        assert any("Techno Solutions" in name for name in org_names)
        assert any("Global Dynamics" in name for name in org_names)

    def test_regex_extracts_date(self):
        """Regex fallback should extract dates in Month Day, Year format."""
        from app.knowledge_graph.entity_extractor import _regex_entity_extraction

        text = "The event was held on January 15, 2025 in Paris."
        entities = _regex_entity_extraction(text)

        dates = [e["name"] for e in entities if e["type"] == "DATE"]
        assert len(dates) >= 1
        assert "January 15, 2025" in dates

    def test_regex_extracts_email(self):
        """Regex fallback should extract email addresses."""
        from app.knowledge_graph.entity_extractor import _regex_entity_extraction

        text = "Contact john.doe@example.com or jane@acme.com for details."
        entities = _regex_entity_extraction(text)

        emails = [e["name"] for e in entities if e["type"] == "PERSON"]
        assert any("john.doe@example.com" in e for e in emails)

    def test_regex_skips_short_text(self):
        """Regex fallback should skip names < 2 chars."""
        from app.knowledge_graph.entity_extractor import _regex_entity_extraction

        entities = _regex_entity_extraction("A B C")
        # No match should produce < 2 char names
        for e in entities:
            assert len(e["name"]) >= 2

    def test_parse_entity_response_valid_json(self):
        """Should parse valid JSON with entities array."""
        from app.knowledge_graph.entity_extractor import _parse_entity_response

        response = '{"entities": [{"name": "Alice", "type": "PERSON", "confidence": 0.9, "context": "Alice is a researcher"}]}'
        entities = _parse_entity_response(response)

        assert len(entities) == 1
        assert entities[0]["name"] == "Alice"
        assert entities[0]["type"] == "PERSON"
        assert entities[0]["confidence"] == 0.9
        assert "entity_id" in entities[0]

    def test_parse_entity_response_json_in_fence(self):
        """Should extract JSON from markdown code fences."""
        from app.knowledge_graph.entity_extractor import _parse_entity_response

        response = '```json\n{"entities": [{"name": "Bob", "type": "ORGANIZATION", "confidence": 0.8}]}\n```'
        entities = _parse_entity_response(response)

        assert len(entities) == 1
        assert entities[0]["name"] == "Bob"

    def test_parse_entity_response_invalid_json(self):
        """Should return empty list for invalid JSON."""
        from app.knowledge_graph.entity_extractor import _parse_entity_response

        entities = _parse_entity_response("not json at all")
        assert entities == []

    def test_parse_entity_response_filters_low_confidence(self):
        """Should filter out entities with confidence < 0.5."""
        from app.knowledge_graph.entity_extractor import _parse_entity_response

        response = '{"entities": [{"name": "Low", "type": "OTHER", "confidence": 0.3}, {"name": "High", "type": "OTHER", "confidence": 0.9}]}'
        entities = _parse_entity_response(response)

        assert len(entities) == 1
        assert entities[0]["name"] == "High"

    def test_parse_entity_response_dedup(self):
        """Should deduplicate entities by entity_id."""
        from app.knowledge_graph.entity_extractor import _parse_entity_response

        response = '{"entities": [{"name": "Alice", "type": "PERSON", "confidence": 0.9}, {"name": "alice", "type": "PERSON", "confidence": 0.8}]}'
        entities = _parse_entity_response(response)

        # Both should have same entity_id (case-insensitive name+type hash)
        assert len(entities) <= 1  # at most 1 unique entity_id

    @pytest.mark.asyncio
    async def test_extract_entities_short_text(self):
        """Should return empty list for very short text (< 20 chars)."""
        from app.knowledge_graph.entity_extractor import extract_entities_from_text

        entities = await extract_entities_from_text("Short.")
        assert entities == []

    @pytest.mark.asyncio
    async def test_extract_entities_no_api_key(self):
        """When no API key, should fall back to regex extraction."""
        from app.knowledge_graph.entity_extractor import extract_entities_from_text

        entities = await extract_entities_from_text(
            "Dr. John Smith works at Acme Corp Inc located in New York. "
            "Contact john.smith@acme-corp.com for details from January 2025."
        )

        # Regex fallback should find at least one entity
        assert len(entities) >= 1
        # All entities must have required fields
        for e in entities:
            assert "name" in e
            assert "type" in e
            assert "entity_id" in e


# ── Relationship Extractor tests ──────────────────────────────────────────────


class TestRelationshipExtraction:
    """Tests for relationship extraction."""

    def test_cooccurrence_basic(self):
        """Should extract relationships based on entity co-occurrence in chunks."""
        from app.knowledge_graph.relationship_extractor import extract_relationships_cooccurrence

        entities = [
            {"entity_id": "a1", "name": "Alice", "type": "PERSON"},
            {"entity_id": "b2", "name": "Bob", "type": "PERSON"},
            {"entity_id": "c3", "name": "Acme Corp", "type": "ORGANIZATION"},
        ]
        chunks = [
            {"content": "Alice and Bob work at Acme Corp.", "id": "chunk1"},
            {"content": "Alice and Bob discussed the project.", "id": "chunk2"},
            {"content": "Alice presented to Acme Corp executives.", "id": "chunk3"},
        ]

        relationships = extract_relationships_cooccurrence(entities, chunks)

        # Alice-Bob should co-occur in 2 chunks (threshold: >=2)
        # Alice-Acme should co-occur in 2 chunks
        assert len(relationships) >= 1
        for rel in relationships:
            assert "source_id" in rel
            assert "target_id" in rel
            assert "confidence" in rel
            assert rel["method"] == "cooccurrence"

    def test_cooccurrence_none_pairs(self):
        """Co-occurrence needs at least 2 entities in a chunk to create a relationship."""
        from app.knowledge_graph.relationship_extractor import extract_relationships_cooccurrence

        entities = [
            {"entity_id": "a1", "name": "Alice", "type": "PERSON"},
            {"entity_id": "b2", "name": "Bob", "type": "PERSON"},
        ]
        # Alice and Bob never appear in the same chunk
        chunks = [
            {"content": "Alice works alone.", "id": "chunk1"},
            {"content": "Bob works elsewhere.", "id": "chunk2"},
        ]

        relationships = extract_relationships_cooccurrence(entities, chunks)
        # None should cross the >= 2 co-occurrence threshold
        assert all(rel.get("weight", 0) < 2 for rel in relationships) if relationships else True

    def test_cooccurrence_single_entity(self):
        """A single entity cannot produce relationships."""
        from app.knowledge_graph.relationship_extractor import extract_relationships_cooccurrence

        entities = [{"entity_id": "a1", "name": "Alice", "type": "PERSON"}]
        chunks = [{"content": "Alice works here.", "id": "chunk1"}]

        relationships = extract_relationships_cooccurrence(entities, chunks)
        assert relationships == []

    def test_parse_relationship_response(self):
        """Should parse valid relationship JSON."""
        from app.knowledge_graph.relationship_extractor import _parse_relationship_response

        entity_by_name = {
            "alice": {"entity_id": "a1", "name": "Alice", "type": "PERSON"},
            "bob": {"entity_id": "b2", "name": "Bob", "type": "PERSON"},
        }
        response = '{"relationships": [{"source": "Alice", "target": "Bob", "type": "WORKS_FOR", "confidence": 0.8, "evidence": "Alice works for Bob"}]}'

        relationships = _parse_relationship_response(response, entity_by_name)
        assert len(relationships) == 1
        assert relationships[0]["source_id"] == "a1"
        assert relationships[0]["target_id"] == "b2"
        assert relationships[0]["type"] == "WORKS_FOR"

    def test_parse_relationship_low_confidence_filtered(self):
        """Relationships below 0.6 confidence should be filtered."""
        from app.knowledge_graph.relationship_extractor import _parse_relationship_response

        entity_by_name = {
            "alice": {"entity_id": "a1", "name": "Alice", "type": "PERSON"},
            "bob": {"entity_id": "b2", "name": "Bob", "type": "PERSON"},
        }
        response = '{"relationships": [{"source": "Alice", "target": "Bob", "type": "KNOWS", "confidence": 0.4}]}'

        relationships = _parse_relationship_response(response, entity_by_name)
        assert relationships == []


# ── Graph Agent tests ─────────────────────────────────────────────────────────


class TestGraphAgent:
    """Tests for the knowledge graph LangGraph agent."""

    @pytest.mark.asyncio
    async def test_agent_skips_empty_query(self):
        """Agent should skip processing for empty/short queries."""
        from app.knowledge_graph.graph_agent import knowledge_graph_agent

        state = {"query": "", "retrieved_chunks": []}
        result = await knowledge_graph_agent(state)

        assert result["graph_entities"] == []
        assert result["graph_augmented_chunks"] == []

    @pytest.mark.asyncio
    async def test_agent_skips_short_query(self):
        """Agent should skip for queries shorter than 3 chars."""
        from app.knowledge_graph.graph_agent import knowledge_graph_agent

        state = {"query": "ab", "retrieved_chunks": []}
        result = await knowledge_graph_agent(state)

        assert result["agent_states"]["knowledge_graph"] == "skipped"

    @pytest.mark.asyncio
    async def test_agent_preserves_existing_chunks(self):
        """Agent should keep existing retrieved chunks in its output."""
        from app.knowledge_graph.graph_agent import knowledge_graph_agent

        state = {
            "query": "What does Alice work on?",
            "retrieved_chunks": [
                {
                    "id": "chunk1",
                    "content": "Alice works on project X.",
                    "document_id": "doc1",
                    "similarity": 0.9,
                },
            ],
        }

        # Neo4j won't be available, so agent will fallback gracefully
        result = await knowledge_graph_agent(state)

        # Should still include the original chunks
        augmented = result.get("graph_augmented_chunks", [])
        assert len(augmented) >= 1
        assert augmented[0]["id"] == "chunk1"

    @pytest.mark.asyncio
    async def test_agent_graceful_neo4j_unavailable(self):
        """Agent should gracefully handle missing Neo4j."""
        from app.knowledge_graph.graph_agent import knowledge_graph_agent

        state = {
            "query": "test query about artificial intelligence",
            "retrieved_chunks": [
                {
                    "id": "chunk1",
                    "content": "AI is transforming industries.",
                    "document_id": "doc1",
                    "similarity": 0.9,
                },
            ],
        }

        result = await knowledge_graph_agent(state)

        # Should not crash, should return augmented chunks (at least originals)
        assert "graph_augmented_chunks" in result
        assert "agent_states" in result


# ── API endpoint tests ────────────────────────────────────────────────────────


class TestKnowledgeGraphAPI:
    """Tests for the knowledge graph API endpoints."""

    @pytest.mark.asyncio
    async def test_stats_endpoint_graceful(self, client):
        """Stats endpoint should return gracefully when Neo4j unavailable."""
        import logging

        logger = logging.getLogger("app.knowledge_graph.graph_service")
        logger.setLevel(logging.CRITICAL)

        resp = await client.get("/graph/stats")
        # Should return 200 with empty/false stats, or 503 if error propagated
        assert resp.status_code in (200, 503)

        if resp.status_code == 200:
            data = resp.json()
            # When disconnected, entities should be 0 and connected=False
            assert "entities" in data
            assert "relationships" in data

    @pytest.mark.asyncio
    async def test_entities_search_graceful(self, client):
        """Entity search endpoint should handle Neo4j unavailability."""
        resp = await client.get("/graph/entities?q=test")
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_subgraph_graceful(self, client):
        """Subgraph endpoint should handle Neo4j unavailability."""
        resp = await client.get("/graph/entities/test123?depth=2")
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_document_entities_graceful(self, client):
        """Document entities endpoint should handle Neo4j unavailability."""
        resp = await client.get("/graph/documents/nonexistent/entities")
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_expand_query_graceful(self, client):
        """Query expansion should handle Neo4j unavailability."""
        resp = await client.get("/graph/expand?q=test")
        assert resp.status_code in (200, 503)


# ── Graph Service unit tests ──────────────────────────────────────────────────


class TestGraphService:
    """Tests for GraphService (mocked Neo4j driver)."""

    def _make_graph_service_with_mock_driver(self):
        """Create a GraphService with a mocked Neo4j driver."""
        from app.knowledge_graph.graph_service import GraphService

        gs = GraphService()

        mock_session = AsyncMock()
        mock_driver = MagicMock()

        # driver.session() returns an async context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_driver.session.return_value = mock_ctx

        async def _get_driver():
            return mock_driver

        gs._get_driver = _get_driver  # type: ignore[method-assign]
        gs._driver = None
        return gs, mock_driver, mock_session

    @pytest.mark.asyncio
    async def test_upsert_entity(self):
        """Upsert entity should call MERGE in Neo4j."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        await gs.upsert_entity(
            entity_id="e1",
            name="Test Entity",
            entity_type="ORGANIZATION",
            properties={"source": "test"},
        )

        # Should have called session.run with a MERGE query
        mock_session.run.assert_called()
        call_args = mock_session.run.call_args[0]
        assert "MERGE" in str(call_args)

    @pytest.mark.asyncio
    async def test_upsert_relationship(self):
        """Upsert relationship should call MERGE with RELATES_TO."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        await gs.upsert_relationship(
            source_entity_id="e1",
            target_entity_id="e2",
            rel_type="WORKS_FOR",
            confidence=0.9,
        )

        mock_session.run.assert_called()
        call_args_str = str(mock_session.run.call_args)
        assert "RELATES_TO" in call_args_str

    @pytest.mark.asyncio
    async def test_upsert_relationship_self_reference_skipped(self):
        """Self-referencing relationships should be skipped."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        await gs.upsert_relationship(
            source_entity_id="same",
            target_entity_id="same",
            rel_type="KNOWS",
        )

        # Should not call session.run for self-references
        mock_session.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_document_node(self):
        """Should create a Document node via MERGE."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        await gs.ensure_document_node("doc-1", "test.pdf")

        mock_session.run.assert_called()
        call_args_str = str(mock_session.run.call_args)
        assert "MERGE" in call_args_str
        assert "Document" in call_args_str

    @pytest.mark.asyncio
    async def test_search_entities_with_type(self):
        """Entity search should apply type filter."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        run_result = AsyncMock()
        run_result.data.return_value = [
            {"name": "Acme Corp", "type": "ORGANIZATION", "entity_id": "e1", "confidence": 0.9},
        ]
        mock_session.run.return_value = run_result

        results = await gs.search_entities("Acme", entity_type="ORGANIZATION")
        assert len(results) >= 1
        assert results[0]["type"] == "ORGANIZATION"

    @pytest.mark.asyncio
    async def test_get_graph_stats(self):
        """Graph stats should return counts from Neo4j."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            str(args[0]) if args else ""
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Entity count query
                single_mock = AsyncMock(return_value={"cnt": 42})
                result.single = single_mock
                return result
            elif call_count == 2:
                # Relationship count query
                single_mock = AsyncMock(return_value={"cnt": 10})
                result.single = single_mock
                return result
            else:
                # Type breakdown
                data_mock = AsyncMock(
                    return_value=[
                        {"type": "PERSON", "count": 30},
                        {"type": "ORGANIZATION", "count": 12},
                    ]
                )
                result.data = data_mock
                return result

        mock_session.run.side_effect = _side_effect

        stats = await gs.get_graph_stats()
        assert stats["entities"] == 42
        assert stats["relationships"] == 10
        assert stats["entity_types"] == {"PERSON": 30, "ORGANIZATION": 12}
        assert stats["connected"] is True

    @pytest.mark.asyncio
    async def test_delete_document_graph(self):
        """Should delete document and orphan entities."""
        gs, mock_driver, mock_session = self._make_graph_service_with_mock_driver()

        await gs.delete_document_graph("doc-1")

        mock_session.run.assert_called()
        call_args_str = str(mock_session.run.call_args)
        assert "DETACH DELETE" in call_args_str or "DELETE" in call_args_str


# ── Health check test ─────────────────────────────────────────────────────────


class TestHealthCheckKG:
    """Test that Neo4j appears in health check."""

    @pytest.mark.asyncio
    async def test_health_ready_includes_neo4j(self, client):
        """Readiness endpoint should include neo4j field."""
        resp = await client.get("/health/ready")
        assert resp.status_code in (200, 503)  # 503 if degraded

        data = resp.json()
        assert "neo4j" in data
        assert data["neo4j"] in ("ready", "not ready")
