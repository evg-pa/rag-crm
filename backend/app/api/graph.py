"""Knowledge Graph REST endpoints.

GET  /graph/entities        — search entities
GET  /graph/entities/{id}   — get entity subgraph for visualization
GET  /graph/stats           — graph statistics (entity count, relationship count)
GET  /graph/expand          — expand query with related entities
DELETE /graph/documents/{id} — delete graph data for a document
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, status

from app.knowledge_graph.graph_service import GraphService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["knowledge-graph"])


@router.get("/entities")
async def search_entities(
    q: str = Query(..., min_length=1, description="Search term for entity names"),
    type: str | None = Query(
        None, description="Filter by entity type (PERSON, ORGANIZATION, etc.)"
    ),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Search for entities by name (fuzzy match)."""
    try:
        gs = GraphService()
        results = await gs.search_entities(q, entity_type=type, limit=limit)
        return {"entities": results, "total": len(results)}
    except Exception as exc:
        logger.warning("Graph entities search failed: %s", exc)
        return {"entities": [], "total": 0}


@router.get("/entities/{entity_id}")
async def get_entity_subgraph(
    entity_id: str,
    depth: int = Query(2, ge=1, le=3, description="Max traversal depth"),
) -> dict[str, Any]:
    """Get the subgraph centred on an entity (nodes + edges for visualization)."""
    try:
        gs = GraphService()
        subgraph = await gs.get_entity_subgraph(entity_id, max_depth=depth)
        return subgraph
    except Exception as exc:
        logger.warning("Entity subgraph fetch failed: %s", exc)
        return {"nodes": [], "edges": []}


@router.get("/stats")
async def get_graph_stats() -> dict[str, Any]:
    """Return knowledge graph statistics."""
    try:
        gs = GraphService()
        return await gs.get_graph_stats()
    except Exception as exc:
        logger.warning("Graph stats fetch failed: %s", exc)
        return {"entities": 0, "relationships": 0, "entity_types": {}, "connected": False}


@router.get("/expand")
async def expand_query(
    q: str = Query(..., min_length=1, description="Query to expand with related entities"),
) -> dict[str, Any]:
    """Expand a query with related entities from the knowledge graph."""
    try:
        gs = GraphService()
        expanded = await gs.expand_query_entities(q, top_k=10)
        return {"query": q, "expanded_entities": expanded, "total": len(expanded)}
    except Exception as exc:
        logger.warning("Query expansion failed: %s", exc)
        return {"query": q, "expanded_entities": [], "total": 0}


@router.get("/documents/{document_id}/entities")
async def get_document_entities(
    document_id: str,
) -> dict[str, Any]:
    """Get all entities extracted from a specific document."""
    try:
        gs = GraphService()
        entities = await gs.get_document_entities(document_id)
        return {"document_id": document_id, "entities": entities, "total": len(entities)}
    except Exception as exc:
        logger.warning("Document entities fetch failed: %s", exc)
        return {"document_id": document_id, "entities": [], "total": 0}


@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document_graph(
    document_id: str,
) -> dict[str, str]:
    """Delete all graph data (entities, relationships) for a document."""
    try:
        gs = GraphService()
        await gs.delete_document_graph(document_id)
        return {"status": "deleted", "document_id": document_id}
    except Exception as exc:
        logger.warning("Document graph deletion failed: %s", exc)
        return {"status": "error", "document_id": document_id, "detail": str(exc)}
