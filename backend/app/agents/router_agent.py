"""RouterAgent — classifies the user query into a search strategy.

Supported types:
  - semantic   — conceptual / meaning-based queries
  - keyword    — exact term / definition lookups
  - hybrid     — mixed or ambiguous queries (default)
  - greeting   — "hello", "thanks", small talk
  - irrelevant — gibberish, off-topic, inappropriate
"""

from __future__ import annotations

import re

from app.agents.state import AgentState

# ── Greeting patterns ────────────────────────────────────────────────────────

_GREETING_PATTERNS = [
    r"^hi\b",
    r"^hello\b",
    r"^hey\b",
    r"^good\s*(morning|afternoon|evening)",
    r"^howdy\b",
    r"^greetings\b",
    r"^yo\b",
    r"^(thanks|thank\s*you|thx|ty)\b",
    r"^(bye|goodbye|see\s*ya|cya)\b",
    r"^what('s| is) up\b",
    r"^how are you\b",
    r"^\??\s*$",  # empty or just question marks
]

# ── Irrelevant / off-topic patterns ──────────────────────────────────────────

_IRRELEVANT_PATTERNS = [
    r"^[^a-zA-Z0-9\s]{5,}$",  # mostly non-alphanumeric gibberish
    r"^(asdf|qwer|zxcv|foo|bar|baz|hjkl|tyui|bnmv)",  # keyboard mashing (prefix match)
    r"^.{1,2}$",  # one or two characters
]

# ── Keyword-heavy query indicators ───────────────────────────────────────────

_KEYWORD_INDICATORS = [
    r"\bdefine\b",
    r"\bdefinition\b",
    r"\bwhat is\b",
    r"\bmeaning of\b",
    r"\babbreviation\b",
    r"\bhow to\b",
    r"\bsteps?\b",
    r"\bprocedure\b",
]

# ── Semantic-heavy query indicators ──────────────────────────────────────────

_SEMANTIC_INDICATORS = [
    r"\brelate(d|s|tion)\b",
    r"\bsimilar\b",
    r"\bcompare\b",
    r"\bwhy\b",
    r"\bhow does\b",
    r"\bexplain\b",
    r"\boverview\b",
    r"\bsummar(y|ize)\b",
    r"\bdescribe\b",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    """Return True if *text* matches any compiled regex in *patterns*."""
    t = text.lower().strip()
    return any(re.search(pat, t) for pat in patterns)


def classify_query(query: str) -> str:
    """Classify a query string into one of the five routing categories.

    Priority order:
      1. Greeting
      2. Irrelevant
      3. Semantic
      4. Keyword
      5. Hybrid (default)
    """
    if not query or not query.strip():
        return "greeting"

    q = query.strip()

    # 1. Greeting check
    if _matches_any(q, _GREETING_PATTERNS):
        return "greeting"

    # 2. Irrelevant check
    if _matches_any(q, _IRRELEVANT_PATTERNS):
        return "irrelevant"

    # 3. Semantic indicators (check first — "why" and "compare" are strong signals)
    if _matches_any(q, _SEMANTIC_INDICATORS):
        return "semantic"

    # 4. Keyword indicators
    if _matches_any(q, _KEYWORD_INDICATORS):
        return "keyword"

    # 5. Default — hybrid
    return "hybrid"


# ── LangGraph node ───────────────────────────────────────────────────────────


async def router_agent(state: AgentState) -> dict:
    """LangGraph node: classify the query and set query_type.

    Also initialises the agent_states tracker for /pipeline/status.
    """
    query: str = state.get("query", "")
    query_type = classify_query(query)

    return {
        "query_type": query_type,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "router": "completed",
        },
    }
