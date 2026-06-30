"""CRMContextAgent — detects CRM queries, extracts entities, enriches context.

Flow:
  1. Detect if the query is CRM-related (mentions contacts, deals, activities,
     companies, or uses CRM-specific patterns like "top deals", "recent calls").
  2. Extract entity names via regex patterns + fuzzy matching against the DB.
  3. Look up matching CRM entities from the database.
  4. Cross-reference CRM entities with document chunks (e.g. "what deals
     relate to this PDF?").
  5. Return enriched context for the downstream agents.

Strategy
--------
- Regex-based extraction for common CRM patterns (name, email, company).
- Fuzzy matching (difflib.SequenceMatcher) against known CRM entity names
  from the database for partial/inexact matches.
- Cross-reference by matching CRM entity names/companies against chunk content.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.models.crm import CrmActivity, CrmContact, CrmDeal

# ── CRM query patterns ──────────────────────────────────────────────────────

# Phrases that signal a CRM-related query
_CRM_QUERY_PATTERNS = [
    r"\bcrm\b",
    r"\bcontacts?\b",
    r"\bdeals?\b",
    r"\bopportunit",
    r"\baccounts?\b",
    r"\bleads?\b",
    r"\btop\s+(deals?|opportunities?|accounts?)\b",
    r"\brecent\s+(activities?|calls?|meetings?|emails?)\b",
    r"\b(hot|warm|cold)\s+(lead|opportunity)\b",
    r"\bpipeline\b",
    r"\bstages?\b",
    r"\brevenue\b",
    r"\bforecast\b",
    r"\bclose\s+(date|rate|ratio)\b",
    r"\binteractions?\b",
    r"\bsales\s*(pipeline|funnel)\b",
    r"\bwho\s+(is|are)\b",
    r"\bshow\s+me\b",
    r"\blist\s+(all|the|my)\b",
    r"\bhow\s+many\b",
]

# Entity name extraction patterns
_ENTITY_PATTERNS = [
    # "contact John Doe"
    (r"(?:contact|person|customer|client)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", "contact"),
    # "deal Acme Project"
    (r"(?:deal|opportunity|project)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Za-z0-9]+)*)", "deal"),
    # "company Acme Corp"
    (
        r"(?:company|account|org|organisation|organization)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Za-z0-9]+)*)",
        "company",
    ),
    # "email john@example.com"
    (r"(?:email|e-mail)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", "contact"),
    # "phone +1-555-1234"
    (r"(?:phone|call|dial)\s+([+\d][\d\s\-().]{5,})", "contact"),
    # Quoted entity names
    (
        r"(?:about|regarding|related to|for)\s+['\"]?(.+?)['\"]?(?:\s*(?:document|file|PDF|agreement|contract))?",
        "generic",
    ),
]

# CRM intent classification
_CRM_INTENT_PATTERNS = {
    "cross_reference": [
        r"\brelat",
        r"\breferenc",
        r"\bconnect",
        r"\blink(?:ed|s)?\b",
        r"\bassociat",
        r"\babout\b.*\b(doc|PDF|file|contract|agreement)",
    ],
    "contact": [r"\bcontacts?\b", r"\bperson\b", r"\bwho\b", r"\bemail\b", r"\bphone\b"],
    "activity": [
        r"\bactivity",
        r"\bmeeting\b",
        r"\bcalls?\b.*\b(yesterday|today|week|recent)",
        r"\bemail\b.*\b(recent|last|sent)",
    ],
    "deal": [
        r"\bdeals?\b",
        r"\bopportunit",
        r"\bpipeline\b",
        r"\bstages?\b",
        r"\bvalue\b",
        r"\brevenue\b",
        r"\bclose\b",
    ],
    "quick_query": [
        r"\btop\b",
        r"\brecent\b",
        r"\blist\b",
        r"\bshow me\b",
        r"\bsummary\b",
        r"\bcount\b",
    ],
}


def is_crm_query(query: str) -> bool:
    """Return True if the query appears to be CRM-related."""
    q = query.lower().strip()
    return any(re.search(pat, q) for pat in _CRM_QUERY_PATTERNS)


def classify_crm_intent(query: str) -> str:
    """Classify the CRM intent: cross_reference, contact, activity, deal, quick_query, or none."""
    q = query.lower().strip()
    scores: dict[str, int] = {}
    for intent, patterns in _CRM_INTENT_PATTERNS.items():
        scores[intent] = sum(1 for p in patterns if re.search(p, q))

    if not any(scores.values()):
        return "none"

    # Priority order: specific intents beat quick_query on ties
    priority = ["cross_reference", "contact", "activity", "deal", "quick_query"]
    best = max(priority, key=lambda i: (scores.get(i, 0), -priority.index(i)))
    return best if scores.get(best, 0) > 0 else "none"


def extract_entity_names(query: str, db_names: list[str]) -> list[dict[str, Any]]:
    """Extract entity names from the query using regex + fuzzy matching.

    Returns a list of ``{"name": str, "type": str, "confidence": float}``.
    """
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    q = query.strip()

    # 1. Regex-based extraction
    for pattern, entity_type in _ENTITY_PATTERNS:
        for match in re.finditer(pattern, q, re.IGNORECASE):
            name = match.group(1).strip()
            name_clean = re.sub(r"\s+", " ", name)
            if name_clean.lower() not in seen and len(name_clean) > 2:
                entities.append(
                    {"name": name_clean, "type": entity_type, "confidence": 0.9, "method": "regex"}
                )
                seen.add(name_clean.lower())

    # 2. Fuzzy matching against known DB names
    for db_name in db_names:
        # Check if any extracted entity is a fuzzy match to a DB name
        best_ratio = 0.0
        for ent in entities:
            ratio = difflib.SequenceMatcher(None, ent["name"].lower(), db_name.lower()).ratio()
            best_ratio = max(best_ratio, ratio)

        # Check direct fuzzy match against the full query
        query_ratio = difflib.SequenceMatcher(None, q.lower(), db_name.lower()).ratio()

        if query_ratio > 0.6 and db_name.lower() not in seen:
            entities.append(
                {
                    "name": db_name,
                    "type": "fuzzy_db",
                    "confidence": round(query_ratio, 2),
                    "method": "fuzzy",
                }
            )
            seen.add(db_name.lower())

        # If we have a high fuzzy match to an existing entity, boost its confidence
        if best_ratio > 0.6:
            for ent in entities:
                r = difflib.SequenceMatcher(None, ent["name"].lower(), db_name.lower()).ratio()
                if r > 0.6:
                    ent["confidence"] = max(ent["confidence"], round(r, 2))
                    ent["db_match"] = db_name

    return entities


def build_crm_context(
    contacts: list[CrmContact],
    deals: list[CrmDeal],
    activities: list[CrmActivity],
    intent: str,
) -> str:
    """Build a formatted CRM context string from matching entities.

    The output is designed to be injected into the LLM prompt as enriched
    context, similar to how document chunks are injected.
    """
    parts: list[str] = []

    if intent == "contact" and contacts:
        parts.append("### CRM Contacts")
        for c in contacts:
            parts.append(
                f"- **{c.name}** (Email: {c.email or 'N/A'}, "
                f"Phone: {c.phone or 'N/A'}, Company: {c.company or 'N/A'})"
            )

    if intent in ("deal", "cross_reference") and deals:
        parts.append("### CRM Deals / Opportunities")
        for d in deals:
            value_str = f"${d.value:,.2f}" if d.value else "N/A"
            close_str = d.close_date.isoformat() if d.close_date else "N/A"
            parts.append(
                f"- **{d.name}** (Value: {value_str}, Stage: {d.stage}, Close: {close_str})"
            )

    if intent in ("activity", "contact", "cross_reference") and activities:
        parts.append("### CRM Activities")
        for a in activities[:10]:  # limit to 10 most recent
            parts.append(f"- **{a.type}** on {a.date.strftime('%Y-%m-%d')}: {a.description[:200]}")

    # Summary when no specific entities found
    if not parts:
        if contacts:
            parts.append(f"### CRM Contacts (all — {len(contacts)} total)")
            for c in contacts[:5]:
                parts.append(f"- {c.name} ({c.company or 'N/A'})")

        if deals:
            parts.append(f"### CRM Deals (all — {len(deals)} total)")
            for d in deals[:5]:
                parts.append(f"- {d.name} — Stage: {d.stage}")

        if activities:
            parts.append(f"### CRM Activities (recent — {len(activities)} total)")
            for a in activities[:5]:
                parts.append(f"- {a.type} on {a.date.strftime('%Y-%m-%d')}")

    return "\n".join(parts)


def build_cross_references(
    crm_entities: list[dict[str, Any]],
    document_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cross-reference CRM entity names against document chunk content.

    Returns a list of matches: ``{"entity": str, "chunk_id": str,
    "document_id": str, "content_snippet": str}``.
    """
    refs: list[dict[str, Any]] = []
    seen_refs: set[tuple[str, str]] = set()

    if not crm_entities or not document_chunks:
        return refs

    for entity in crm_entities:
        entity_name = entity.get("name", "").lower()
        if not entity_name:
            continue

        for chunk in document_chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("id", "")
            document_id = chunk.get("document_id", "")
            content = chunk.get("content", "")

            # Direct mention
            if entity_name in content.lower():
                key = (entity_name, str(chunk_id))
                if key not in seen_refs:
                    refs.append(
                        {
                            "entity": entity.get("name", entity_name),
                            "chunk_id": str(chunk_id),
                            "document_id": str(document_id),
                            "content_snippet": content[:200],
                            "match_type": "direct",
                        }
                    )
                    seen_refs.add(key)

            # Company name match
            company = entity.get("db_match", "")
            if company and company.lower() in content.lower():
                key = (company.lower(), str(chunk_id))
                if key not in seen_refs:
                    refs.append(
                        {
                            "entity": entity.get("name", entity_name),
                            "chunk_id": str(chunk_id),
                            "document_id": str(document_id),
                            "content_snippet": content[:200],
                            "match_type": "company",
                        }
                    )
                    seen_refs.add(key)

    return refs


# ── LangGraph node ───────────────────────────────────────────────────────────


async def crm_context_agent(state: AgentState) -> dict:
    """LangGraph node: detect CRM queries, extract entities, enrich context.

    Reads from state: ``query``, ``retrieved_chunks`` (if available for
    cross-reference), ``_db_session``.

    Writes to state: ``crm_query_type``, ``crm_entities``, ``crm_context``,
    ``crm_cross_refs``, ``query_type`` (overridden to ``"crm"`` if detected).
    """
    query: str = state.get("query", "")
    db: AsyncSession | None = state.get("_db_session")  # type: ignore[typeddict-item]

    # Default return — no CRM enrichment
    result: dict[str, Any] = {
        "crm_query_type": "none",
        "crm_entities": [],
        "crm_context": "",
        "crm_cross_refs": [],
    }

    # Quick check — skip if not CRM-related
    if not is_crm_query(query):
        result["agent_states"] = {
            **(state.get("agent_states") or {}),
            "crm_context": "skipped",
        }
        return result

    intent = classify_crm_intent(query)
    result["crm_query_type"] = intent

    # Extract entity names — we need DB names for fuzzy matching
    all_crm_names: list[str] = []
    contacts: list[CrmContact] = []
    deals: list[CrmDeal] = []
    activities: list[CrmActivity] = []

    if db is not None:
        try:
            # Fetch all CRM contacts
            result_c = await db.execute(select(CrmContact))
            contacts = list(result_c.scalars().all())
            all_crm_names.extend(c.name for c in contacts)

            # Fetch all CRM deals
            result_d = await db.execute(select(CrmDeal))
            deals = list(result_d.scalars().all())
            all_crm_names.extend(d.name for d in deals)
            all_crm_names.extend(d.stage for d in deals)

            # Fetch recent activities
            result_a = await db.execute(
                select(CrmActivity).order_by(CrmActivity.date.desc()).limit(20)
            )
            activities = list(result_a.scalars().all())

            # Filter entities based on intent
            if intent == "contact":
                deals = []
                activities = [
                    a for a in activities if a.type.lower() in ("call", "email", "meeting")
                ]
            elif intent == "deal":
                contacts = []
            elif intent == "activity":
                contacts = []
                deals = []
        except Exception:
            pass  # DB unavailable — return empty context gracefully

    # Extract entity names (regex + fuzzy)
    entities = extract_entity_names(query, all_crm_names)
    result["crm_entities"] = entities

    # Build CRM context
    if intent != "none":
        result["crm_context"] = build_crm_context(contacts, deals, activities, intent)

    # Cross-reference with document chunks (if retrieved)
    retrieved_chunks: list[dict[str, Any]] = state.get("retrieved_chunks", [])
    if retrieved_chunks and entities:
        result["crm_cross_refs"] = build_cross_references(entities, retrieved_chunks)

    # Override query_type so the router knows this is CRM
    result["query_type"] = "crm"

    result["agent_states"] = {
        **(state.get("agent_states") or {}),
        "crm_context": "completed",
    }

    return result
