"""GraphService — Neo4j entity/relationship CRUD and graph queries."""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver

from app.core.config import Settings
from app.knowledge_graph.driver import get_neo4j_driver

logger = logging.getLogger(__name__)


class GraphService:
    """Service for storing and querying entities and relationships in Neo4j.

    Creates a lazy Neo4j driver connection. All operations are async.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._driver: AsyncDriver | None = None

    async def _get_driver(self) -> AsyncDriver | None:
        """Lazily get or create the Neo4j driver."""
        if self._driver is None:
            self._driver = await get_neo4j_driver(self._settings)
        return self._driver

    # ── Initialization ──────────────────────────────────────────────────────

    async def initialize_schema(self) -> None:
        """Create indexes and constraints for the knowledge graph."""
        driver = await self._get_driver()
        if driver is None:
            return

        constraints = [
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
            "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX entity_label_index IF NOT EXISTS FOR (e:Entity) ON (e.label)",
            "CREATE INDEX entity_type_index IF NOT EXISTS FOR (e:Entity) ON (e.type)",
            "CREATE INDEX doc_id_index IF NOT EXISTS FOR (d:Document) ON (d.doc_id)",
            "CREATE INDEX relationship_type_index IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.type)",
        ]

        async with driver.session() as session:
            for stmt in constraints + indexes:
                try:
                    await session.run(stmt)
                except Exception as exc:
                    logger.debug("Index/constraint statement skipped: %s", exc)

    # ── Entity operations ───────────────────────────────────────────────────

    async def upsert_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Create or update an entity node in Neo4j.

        Args:
            entity_id: Unique ID for the entity (derived from name+type hash).
            name: Display name of the entity.
            entity_type: Type label (Person, Organization, Location, Concept, etc.).
            properties: Additional properties to set on the node.
        """
        driver = await self._get_driver()
        if driver is None:
            return

        props = properties or {}
        props["entity_id"] = entity_id
        props["name"] = name
        props["type"] = entity_type

        async with driver.session() as session:
            await session.run(
                """
                MERGE (e:Entity {entity_id: $entity_id})
                SET e += $props
                """,
                entity_id=entity_id,
                props=props,
            )

    async def link_entity_to_chunk(
        self, entity_id: str, chunk_id: str, confidence: float = 1.0
    ) -> None:
        """Create a MENTIONS relationship from Entity to Chunk."""
        driver = await self._get_driver()
        if driver is None:
            return

        async with driver.session() as session:
            await session.run(
                """
                MATCH (e:Entity {entity_id: $entity_id})
                MATCH (c:Chunk {chunk_id: $chunk_id})
                MERGE (c)-[r:MENTIONS]->(e)
                SET r.confidence = $confidence
                """,
                entity_id=entity_id,
                chunk_id=chunk_id,
                confidence=confidence,
            )

    async def link_entity_to_document(
        self, entity_id: str, document_id: str, confidence: float = 1.0
    ) -> None:
        """Create a CONTAINS_ENTITY relationship from Document to Entity."""
        driver = await self._get_driver()
        if driver is None:
            return

        async with driver.session() as session:
            await session.run(
                """
                MATCH (e:Entity {entity_id: $entity_id})
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (d)-[r:CONTAINS_ENTITY]->(e)
                SET r.confidence = $confidence
                """,
                entity_id=entity_id,
                doc_id=str(document_id),
                confidence=confidence,
            )

    async def ensure_document_node(self, document_id: str, filename: str = "") -> None:
        """Create a Document node if it doesn't exist."""
        driver = await self._get_driver()
        if driver is None:
            return

        async with driver.session() as session:
            await session.run(
                """
                MERGE (d:Document {doc_id: $doc_id})
                SET d.filename = $filename
                """,
                doc_id=str(document_id),
                filename=filename,
            )

    async def ensure_chunk_node(
        self, chunk_id: str, document_id: str, chunk_index: int = 0
    ) -> None:
        """Create a Chunk node linked to its Document if it doesn't exist."""
        driver = await self._get_driver()
        if driver is None:
            return

        async with driver.session() as session:
            await session.run(
                """
                MERGE (c:Chunk {chunk_id: $chunk_id})
                SET c.chunk_index = $chunk_index
                WITH c
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (d)-[r:HAS_CHUNK]->(c)
                """,
                chunk_id=str(chunk_id),
                doc_id=str(document_id),
                chunk_index=chunk_index,
            )

    # ── Relationship operations ──────────────────────────────────────────────

    async def upsert_relationship(
        self,
        source_entity_id: str,
        target_entity_id: str,
        rel_type: str,
        confidence: float = 1.0,
        weight: float = 1.0,
    ) -> None:
        """Create or update a typed relationship between two Entity nodes."""
        driver = await self._get_driver()
        if driver is None:
            return

        if source_entity_id == target_entity_id:
            return

        async with driver.session() as session:
            await session.run(
                """
                MATCH (a:Entity {entity_id: $source})
                MATCH (b:Entity {entity_id: $target})
                MERGE (a)-[r:RELATES_TO {type: $rel_type}]->(b)
                SET r.confidence = $confidence,
                    r.weight = $weight
                """,
                source=source_entity_id,
                target=target_entity_id,
                rel_type=rel_type,
                confidence=confidence,
                weight=weight,
            )

    # ── Graph queries ────────────────────────────────────────────────────────

    async def get_related_entities(
        self, entity_name: str, max_depth: int = 1, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find entities related to the given entity name (fuzzy or exact)."""
        driver = await self._get_driver()
        if driver is None:
            return []

        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($name)
                   OR toLower($name) CONTAINS toLower(e.name)
                WITH e LIMIT 5
                MATCH (e)-[r:RELATES_TO*1..%d]-(related:Entity)
                RETURN DISTINCT
                    related.name AS name,
                    related.type AS type,
                    related.entity_id AS entity_id
                LIMIT $limit
                """
                % max_depth,
                name=entity_name,
                limit=limit,
            )
            records = await result.data()
            return records

    async def expand_query_entities(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Find entities matching the query and return them with their neighbors.

        Used for query expansion in graph-enhanced search.
        """
        driver = await self._get_driver()
        if driver is None:
            return []

        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($query)
                   OR toLower($query) CONTAINS toLower(e.name)
                WITH e LIMIT 3
                OPTIONAL MATCH (e)-[r:RELATES_TO]->(neighbor:Entity)
                RETURN
                    e.name AS matched_entity,
                    e.type AS matched_type,
                    e.entity_id AS matched_id,
                    collect(DISTINCT {
                        name: neighbor.name,
                        type: neighbor.type,
                        entity_id: neighbor.entity_id,
                        relationship_type: r.type
                    }) AS related_entities
                """,
                parameters={"query": query},
            )
            records = await result.data()
            return records

    async def search_entities(
        self, search_term: str, entity_type: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search for entities by name (fuzzy match) with optional type filter."""
        driver = await self._get_driver()
        if driver is None:
            return []

        if entity_type:
            query = """
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($term)
                  AND e.type = $entity_type
                RETURN e.name AS name, e.type AS type, e.entity_id AS entity_id,
                       e.confidence AS confidence
                ORDER BY e.confidence DESC
                LIMIT $limit
            """
        else:
            query = """
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($term)
                RETURN e.name AS name, e.type AS type, e.entity_id AS entity_id,
                       e.confidence AS confidence
                ORDER BY e.confidence DESC
                LIMIT $limit
            """

        async with driver.session() as session:
            result = await session.run(
                query,
                term=search_term,
                entity_type=entity_type,
                limit=limit,
            )
            records = await result.data()
            return records

    async def get_document_entities(self, document_id: str) -> list[dict[str, Any]]:
        """Get all entities extracted from a specific document."""
        driver = await self._get_driver()
        if driver is None:
            return []

        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Document {doc_id: $doc_id})-[:CONTAINS_ENTITY]->(e:Entity)
                RETURN e.name AS name, e.type AS type, e.entity_id AS entity_id,
                       e.confidence AS confidence
                ORDER BY e.confidence DESC
                """,
                doc_id=str(document_id),
            )
            records = await result.data()
            return records

    async def get_graph_stats(self) -> dict[str, Any]:
        """Return graph statistics: entity count, relationship count, types."""
        driver = await self._get_driver()
        if driver is None:
            return {"entities": 0, "relationships": 0, "entity_types": {}, "connected": False}

        async with driver.session() as session:
            entity_count = await session.run("MATCH (e:Entity) RETURN count(e) AS cnt")
            rel_count = await session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS cnt")
            types = await session.run(
                """
                MATCH (e:Entity)
                RETURN e.type AS type, count(e) AS count
                ORDER BY count DESC
                """
            )

            entity_total = (await entity_count.single())["cnt"]
            rel_total = (await rel_count.single())["cnt"]
            type_data = await types.data()

            return {
                "entities": entity_total,
                "relationships": rel_total,
                "entity_types": {row["type"]: row["count"] for row in type_data},
                "connected": True,
            }

    async def get_entity_subgraph(
        self, entity_id: str, max_depth: int = 2, limit: int = 50
    ) -> dict[str, Any]:
        """Return a subgraph centred on an entity: nodes and edges for visualization."""
        driver = await self._get_driver()
        if driver is None:
            return {"nodes": [], "edges": []}

        async with driver.session() as session:
            # Get the central entity and its neighborhood
            result = await session.run(
                """
                MATCH (center:Entity {entity_id: $entity_id})
                WITH center
                OPTIONAL MATCH path = (center)-[r:RELATES_TO*1..%d]-(neighbor:Entity)
                WITH center, relationships(path) AS rels, nodes(path) AS nds
                UNWIND nds AS n
                WITH DISTINCT n, rels, center
                RETURN
                    collect(DISTINCT {
                        id: n.entity_id,
                        name: n.name,
                        type: n.type,
                        is_center: n.entity_id = center.entity_id
                    }) AS nodes,
                    collect(DISTINCT {
                        source: startNode(r).entity_id,
                        target: endNode(r).entity_id,
                        type: r.type,
                        confidence: r.confidence,
                        weight: r.weight
                    }) AS edges
                """
                % max_depth,
                entity_id=entity_id,
                rels_limit=limit,
            )
            record = await result.single()
            if record is None:
                return {"nodes": [], "edges": []}

            nodes = record["nodes"] or []
            edges = record["edges"] or []

            return {
                "nodes": [n for n in nodes if n is not None],
                "edges": [e for e in edges if e is not None],
            }

    async def delete_document_graph(self, document_id: str) -> None:
        """Remove all entities and relationships associated with a document."""
        driver = await self._get_driver()
        if driver is None:
            return

        async with driver.session() as session:
            # Remove orphan entities (only connected to this document)
            await session.run(
                """
                MATCH (d:Document {doc_id: $doc_id})
                OPTIONAL MATCH (d)-[:CONTAINS_ENTITY]->(e:Entity)
                OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
                DETACH DELETE d, c
                WITH e
                WHERE NOT (e)<-[:CONTAINS_ENTITY]-()
                DETACH DELETE e
                """,
                doc_id=str(document_id),
            )
