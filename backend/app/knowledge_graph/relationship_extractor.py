"""Relationship extraction — LLM inference + co-occurrence analysis.

Extracts relationships between entities using:
1. LLM inference for high-confidence relationships
2. Co-occurrence analysis (entities appearing in same chunks)
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from app.knowledge_graph.graph_service import GraphService
from app.retrieval.qa import AnswerAgent
from app.core.runtime_config import resolve as resolve_runtime

logger = logging.getLogger(__name__)

# ── LLM prompt for relationship extraction ───────────────────────────────────

_RELATIONSHIP_EXTRACTION_PROMPT = """You are a relationship extraction system. Given a list of entities found in a document, identify relationships between them.

For each relationship, provide:
- source: The name of the source entity
- target: The name of the target entity
- type: One of: WORKS_FOR, LOCATED_IN, PART_OF, OWNS, CREATED_BY, SUBSIDIARY_OF, COMPETITOR_OF, SUPPLIES_TO, ACQUIRED, MERGED_WITH, MANAGES, REPORTS_TO, ATTENDED, HOSTED_AT, RELATED_TO
- confidence: 0.0-1.0 indicating how certain you are
- evidence: Short excerpt or reasoning for this relationship

Rules:
1. Only extract relationships between entities in the provided list
2. Only include relationships with confidence >= 0.6
3. Do NOT create self-relationships

Respond with ONLY a JSON object with key "relationships" containing an array of relationship objects."""


async def extract_relationships_llm(
    entities: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    """Use LLM to identify relationships between entities based on document text.

    Args:
        entities: List of extracted entity dicts with name, type, entity_id.
        text: The document text for context.

    Returns:
        List of relationship dicts with source_id, target_id, type, confidence.
    """
    if len(entities) < 2:
        return []

    # Build entity name map for easy lookup
    entity_by_name: dict[str, dict[str, Any]] = {}
    for ent in entities:
        name_lower = ent["name"].lower()
        entity_by_name[name_lower] = ent

    entity_list_str = "\n".join(
        f"- {e['name']} (type: {e['type']}, id: {e['entity_id']})" for e in entities[:30]
    )

    user_prompt = (
        f"Entities found in document:\n{entity_list_str}\n\nDocument text (excerpt):\n{text[:3000]}"
    )

    agent = AnswerAgent()
    try:
        messages = [
            {"role": "system", "content": _RELATIONSHIP_EXTRACTION_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        api_key = resolve_runtime("LLM_API_KEY") or agent._settings.LLM_API_KEY or agent._settings.DEEPSEEK_API_KEY or ""
        if api_key and api_key != "***":
            try:
                response_text = await agent._call_llm_api(messages)
            except Exception:
                response_text = ""
        else:
            try:
                response_text = await agent._call_ollama(messages)
            except Exception:
                response_text = ""
    finally:
        await agent.close()

    if not response_text:
        return []

    return _parse_relationship_response(response_text, entity_by_name)


def _parse_relationship_response(
    raw_response: str, entity_by_name: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Parse LLM relationship extraction response."""
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_response)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        brace_start = raw_response.find("{")
        brace_end = raw_response.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            json_str = raw_response[brace_start : brace_end + 1]
        else:
            return []

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    relationships_raw = parsed.get("relationships", [])
    if not isinstance(relationships_raw, list):
        return []

    relationships: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()

    for rel in relationships_raw:
        if not isinstance(rel, dict):
            continue

        source_name = str(rel.get("source", "")).strip().lower()
        target_name = str(rel.get("target", "")).strip().lower()
        rel_type = str(rel.get("type", "RELATED_TO")).strip().upper()
        confidence = float(rel.get("confidence", 0.5))

        if not source_name or not target_name:
            continue
        if confidence < 0.6:
            continue
        if source_name == target_name:
            continue

        source_ent = entity_by_name.get(source_name)
        target_ent = entity_by_name.get(target_name)
        if not source_ent or not target_ent:
            continue

        pair_key = (source_ent["entity_id"], target_ent["entity_id"], rel_type)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        relationships.append(
            {
                "source_id": source_ent["entity_id"],
                "target_id": target_ent["entity_id"],
                "type": rel_type,
                "confidence": confidence,
                "evidence": str(rel.get("evidence", ""))[:200],
                "method": "llm",
            }
        )

    return relationships


def extract_relationships_cooccurrence(
    entities: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract relationships via co-occurrence analysis.

    Entities that appear in the same chunks frequently are likely related.
    """
    if len(entities) < 2:
        return []

    # Build entity_id set for lookup
    {e["entity_id"] for e in entities}
    entity_map = {e["entity_id"]: e for e in entities}

    # Count co-occurrences in chunks
    cooc_counter: Counter = Counter()

    for chunk in chunks:
        chunk_content = chunk.get("content", "").lower()
        entities_in_chunk: list[str] = []

        for ent in entities:
            if ent["name"].lower() in chunk_content:
                entities_in_chunk.append(ent["entity_id"])

        # Count all pairs in this chunk
        for i in range(len(entities_in_chunk)):
            for j in range(i + 1, len(entities_in_chunk)):
                pair = tuple(sorted([entities_in_chunk[i], entities_in_chunk[j]]))
                cooc_counter[pair] += 1

    # Build relationships from co-occurrence (threshold: >=2 chunks)
    relationships: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for (eid1, eid2), count in cooc_counter.most_common(50):
        if count < 2:
            break

        pair = (eid1, eid2)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        # Normalize confidence
        confidence = min(1.0, count / 10.0)

        entity_map.get(eid1, {})
        entity_map.get(eid2, {})

        relationships.append(
            {
                "source_id": eid1,
                "target_id": eid2,
                "type": "COOCCURS_WITH",
                "confidence": round(confidence, 2),
                "weight": count,
                "method": "cooccurrence",
                "evidence": f"Co-occurs in {count} chunks",
            }
        )

    return relationships


async def process_document_relationships(
    entities: list[dict[str, Any]],
    text: str,
    document_id: str,
    chunks: list[dict[str, Any]] | None = None,
    graph_service: GraphService | None = None,
) -> dict[str, Any]:
    """Full relationship extraction pipeline for a document.

    Combines LLM inference with co-occurrence analysis to extract
    relationships between entities and store them in Neo4j.

    Returns a summary dict.
    """
    gs = graph_service or GraphService()

    all_relationships: list[dict[str, Any]] = []

    # 1. Co-occurrence analysis (always runs, no LLM needed)
    if chunks:
        cooc_rels = extract_relationships_cooccurrence(entities, chunks)
        all_relationships.extend(cooc_rels)

    # 2. LLM-based extraction for high-quality relationships
    llm_rels = await extract_relationships_llm(entities, text)
    all_relationships.extend(llm_rels)

    # Store all relationships in Neo4j
    for rel in all_relationships:
        try:
            await gs.upsert_relationship(
                source_entity_id=rel["source_id"],
                target_entity_id=rel["target_id"],
                rel_type=rel["type"],
                confidence=rel["confidence"],
                weight=rel.get("weight", 1.0),
            )
        except Exception as exc:
            logger.debug("Failed to upsert relationship: %s", exc)

    logger.info(
        "Extracted %d relationships for document %s (llm: %d, cooc: %d)",
        len(all_relationships),
        document_id,
        len(llm_rels),
        len(all_relationships) - len(llm_rels),
    )

    return {
        "relationships": len(all_relationships),
        "llm_relationships": len(llm_rels),
        "cooccurrence_relationships": len(all_relationships) - len(llm_rels),
        "document_id": document_id,
    }
