"""Entity extraction pipeline — LLM-based NER that runs during document ingestion.

Extracts named entities (people, organizations, locations, concepts, etc.)
from document text and stores them as Neo4j nodes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from app.knowledge_graph.graph_service import GraphService
from app.retrieval.qa import AnswerAgent
from app.core.runtime_config import resolve as resolve_runtime

logger = logging.getLogger(__name__)

# ── LLM prompt for entity extraction ─────────────────────────────────────────

_ENTITY_EXTRACTION_PROMPT = """You are an entity extraction system. Extract named entities from the provided text.

Entity types to extract:
- PERSON: Individual people (full names, titles)
- ORGANIZATION: Companies, institutions, agencies
- LOCATION: Cities, countries, regions, landmarks
- CONCEPT: Key concepts, technologies, methodologies, frameworks
- PRODUCT: Products, services, brands
- EVENT: Named events, conferences, historical events
- DATE: Specific dates or time periods mentioned
- OTHER: Any other notable named entity

For each entity, extract:
- name: The canonical name of the entity
- type: One of the above types
- confidence: A float 0.0-1.0 indicating extraction confidence
- context: A short excerpt from the text that mentions this entity

Rules:
1. Extract ONLY entities that are explicitly mentioned in the text
2. Use canonical names (e.g., "New York City" not "NYC", "Google LLC" not "google")
3. Only include entities where confidence >= 0.5
4. Merge duplicates (same entity mentioned multiple times)

Respond with ONLY a JSON object with key "entities" containing an array of entity objects."""


async def extract_entities_from_text(
    text: str,
    chunk_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract entities from text using LLM with clean JSON output.

    Args:
        text: The document text to extract entities from.
        chunk_id: Optional chunk ID for reference.

    Returns:
        List of entity dicts with keys: name, type, confidence, context, entity_id.
    """
    if not text or len(text.strip()) < 20:
        return []

    # Limit input length to avoid huge API calls
    truncated = text[:4000]

    user_prompt = f"Text to analyze:\n\n{truncated}"

    agent = AnswerAgent()
    try:
        # Build message for entity extraction (reuse existing LLM infrastructure)
        messages = [
            {"role": "system", "content": _ENTITY_EXTRACTION_PROMPT},
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
        # Fallback: regex-based extraction when LLM unavailable
        return _regex_entity_extraction(text, chunk_id)

    return _parse_entity_response(response_text, chunk_id)


def _parse_entity_response(raw_response: str, chunk_id: str | None = None) -> list[dict[str, Any]]:
    """Parse the LLM JSON response into entity dicts."""
    # Try to extract JSON from markdown code fences
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
        logger.debug("Failed to parse entity extraction JSON response")
        return []

    entities_raw = parsed.get("entities", [])
    if not isinstance(entities_raw, list):
        return []

    entities: list[dict[str, Any]] = []
    seen_entity_ids: set[str] = set()

    for ent in entities_raw:
        if not isinstance(ent, dict):
            continue

        name = str(ent.get("name", "")).strip()
        entity_type = str(ent.get("type", "OTHER")).strip().upper()
        confidence = float(ent.get("confidence", 0.5))
        context = str(ent.get("context", ""))[:300]

        if not name or len(name) < 2:
            continue
        if confidence < 0.5:
            continue

        # Generate deterministic entity_id from name+type
        entity_id = hashlib.md5(f"{name.lower()}|{entity_type.lower()}".encode()).hexdigest()[:16]

        if entity_id in seen_entity_ids:
            continue
        seen_entity_ids.add(entity_id)

        entities.append(
            {
                "entity_id": entity_id,
                "name": name,
                "type": entity_type,
                "confidence": confidence,
                "context": context,
            }
        )

    return entities


def _regex_entity_extraction(text: str, chunk_id: str | None = None) -> list[dict[str, Any]]:
    """Fallback: regex-based entity extraction when LLM unavailable.

    Uses simple patterns for people, organizations, locations, dates.
    """
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    patterns: list[tuple[str, str, float]] = [
        # Person names (Mr./Ms./Dr. + capitalized words)
        (r"(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", "PERSON", 0.7),
        # Organizations (capitalized, ends with Inc, Corp, LLC, etc.)
        (
            r"([A-Z][a-zA-Z0-9&]*(?:\s+[A-Z][a-zA-Z0-9&]*)*)\s+(?:Inc\.?|Corp\.?|LLC|Ltd\.?|GmbH|S\.A\.|AG)",
            "ORGANIZATION",
            0.8,
        ),
        # Locations (capitalized places)
        (r"(?:in|at|from|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", "LOCATION", 0.5),
        # Email addresses
        (r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", "PERSON", 0.6),
        # Dates
        (
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
            "DATE",
            0.9,
        ),
        # Technical concepts (all-caps acronyms)
        (r"\b([A-Z]{2,6})\b", "CONCEPT", 0.4),
    ]

    for pattern, entity_type, confidence in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1).strip()
            if len(name) < 2:
                continue
            entity_id = hashlib.md5(f"{name.lower()}|{entity_type.lower()}".encode()).hexdigest()[
                :16
            ]
            if entity_id in seen:
                continue
            seen.add(entity_id)
            entities.append(
                {
                    "entity_id": entity_id,
                    "name": name,
                    "type": entity_type,
                    "confidence": confidence,
                    "context": text[max(0, match.start() - 40) : match.end() + 40],
                    "source": "regex_fallback",
                }
            )

    return entities


async def process_document_entities(
    text: str,
    document_id: str,
    filename: str,
    chunks: list[dict[str, Any]] | None = None,
    graph_service: GraphService | None = None,
) -> dict[str, Any]:
    """Full entity extraction pipeline for a document.

    Extracts entities from the full text, then stores them and their
    relationships in Neo4j.

    Returns a summary dict with entity/relationship counts.
    """
    gs = graph_service or GraphService()

    # Ensure document node exists
    await gs.ensure_document_node(document_id, filename)

    # Extract entities from full document text
    entities = await extract_entities_from_text(text)

    if not entities:
        logger.info("No entities extracted from document %s", document_id)
        return {"entities": 0, "relationships": 0, "document_id": document_id}

    # Store entities as Neo4j nodes
    for ent in entities:
        await gs.upsert_entity(
            entity_id=ent["entity_id"],
            name=ent["name"],
            entity_type=ent["type"],
            properties={
                "confidence": ent.get("confidence", 0.5),
                "context": ent.get("context", ""),
                "source_document": filename,
            },
        )
        # Link entity to document
        await gs.link_entity_to_document(
            entity_id=ent["entity_id"],
            document_id=document_id,
            confidence=ent.get("confidence", 0.5),
        )

        # Link entity to chunks if chunk info available
        if chunks:
            for chunk in chunks:
                chunk_content = chunk.get("content", "")
                chunk_id = str(chunk.get("id", ""))
                if ent["name"].lower() in chunk_content.lower():
                    await gs.ensure_chunk_node(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        chunk_index=chunk.get("chunk_index", chunk.get("index", 0)),
                    )
                    await gs.link_entity_to_chunk(
                        entity_id=ent["entity_id"],
                        chunk_id=chunk_id,
                        confidence=ent.get("confidence", 0.5),
                    )

    logger.info("Extracted %d entities from document %s", len(entities), document_id)

    return {
        "entities": len(entities),
        "relationships": 0,
        "document_id": document_id,
    }
