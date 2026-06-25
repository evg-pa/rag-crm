"""KnowledgeGraphAgent — graph-enhanced query expansion for the LangGraph pipeline.

Augments search results by:
1. Extracting entity names from the user query
2. Looking up related entities from the knowledge graph
3. Expanding search terms with related entity names
4. Augmenting search results with graph-connected documents
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.agents.state import AgentState
from app.knowledge_graph.driver import get_neo4j_driver
from app.knowledge_graph.entity_extractor import extract_entities_from_text
from app.knowledge_graph.graph_service import GraphService

logger = logging.getLogger(__name__)


async def knowledge_graph_agent(state: AgentState) -> dict:
    """LangGraph node: expand query with related entities from the knowledge graph.

    Reads from state: ``query``, ``retrieved_chunks``.
    Writes to state: ``graph_entities``, ``graph_augmented_chunks``.

    The agent:
    1. Extracts entity names from the user query
    2. Looks up related entities in Neo4j
    3. Augments retrieved chunks with graph-connected documents
    """
    query: str = state.get("query", "")
    retrieved_chunks: list[dict[str, Any]] = state.get("retrieved_chunks", [])

    result: dict[str, Any] = {
        "graph_entities": [],
        "graph_augmented_chunks": [],
    }

    if not query or len(query.strip()) < 3:
        result["agent_states"] = {
            **(state.get("agent_states") or {}),
            "knowledge_graph": "skipped",
        }
        return result

    try:
        gs = GraphService()

        # Step 1: Extract entities from the query
        query_entities = await extract_entities_from_text(query)

        if not query_entities:
            result["graph_augmented_chunks"] = retrieved_chunks
            result["agent_states"] = {
                **(state.get("agent_states") or {}),
                "knowledge_graph": "skipped",
            }
            return result

        # Step 2: Look up related entities in the knowledge graph
        expanded_entities: list[dict[str, Any]] = []
        for ent in query_entities[:3]:  # limit to top 3 query entities
            related = await gs.get_related_entities(ent["name"], max_depth=1, limit=10)
            expanded_entities.extend(related)

        # Deduplicate expanded entities
        seen_entity_ids: set[str] = set()
        unique_expanded: list[dict[str, Any]] = []
        for ent in expanded_entities:
            eid = ent.get("entity_id", "")
            if eid and eid not in seen_entity_ids:
                seen_entity_ids.add(eid)
                unique_expanded.append(ent)

        result["graph_entities"] = [
            {
                "entity_id": e.get("entity_id", ""),
                "name": e.get("name", ""),
                "type": e.get("type", ""),
            }
            for e in unique_expanded
        ]

        # Step 3: Augment chunks with graph-connected documents
        # For each retrieved chunk, check if its document has entity matches
        augmented_chunks: list[dict[str, Any]] = []
        existing_chunk_ids: set[str] = set()

        # Keep existing chunks
        for chunk in retrieved_chunks:
            chunk_id = str(chunk.get("id", ""))
            if chunk_id:
                existing_chunk_ids.add(chunk_id)
            augmented_chunks.append(chunk)

        # Step 4: For each expanded entity, find its connected chunks
        # by searching chunk content for entity names
        chunk_entity_scores: dict[str, float] = {}

        for chunk in retrieved_chunks:
            chunk_id = str(chunk.get("id", ""))
            content = str(chunk.get("content", "")).lower()

            score = 0.0
            for ent in unique_expanded:
                ent_name = str(ent.get("name", "")).lower()
                if ent_name and ent_name in content:
                    score += 0.3

            if score > 0:
                chunk_entity_scores[chunk_id] = score

        # Annotate augmented chunks with graph scores
        for chunk in augmented_chunks:
            chunk_id = str(chunk.get("id", ""))
            if chunk_id in chunk_entity_scores:
                chunk["graph_score"] = chunk_entity_scores[chunk_id]
                chunk["_graph_augmented"] = True

        result["graph_augmented_chunks"] = augmented_chunks

        result["agent_states"] = {
            **(state.get("agent_states") or {}),
            "knowledge_graph": "completed",
        }

    except Exception as exc:
        logger.warning("Knowledge graph agent error: %s", exc)
        result["agent_states"] = {
            **(state.get("agent_states") or {}),
            "knowledge_graph": "error",
        }
        result["error"] = f"Knowledge graph agent failed: {exc}"

    return result
