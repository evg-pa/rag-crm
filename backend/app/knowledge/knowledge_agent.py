"""KnowledgeAgent — generates document summaries and extracts topics via DeepSeek API.

Reuses the same httpx + DeepSeek call pattern as app.retrieval.qa.AnswerAgent.
Temperature is fixed at 0 for deterministic output.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings
from app.core.dependencies import get_settings

# ── Prompt template ──────────────────────────────────────────────────────────

KNOWLEDGE_SYSTEM_PROMPT = (
    "You are a knowledge extraction assistant. Your job is to read a document "
    "and produce a concise 2-3 sentence summary plus a list of key topics/tags.\n\n"
    "Rules:\n"
    "- Summary must be exactly 2-3 sentences.\n"
    "- Topics must be lowercase single words or 2-word phrases (e.g. 'machine learning', 'docker').\n"
    "- Extract 3-8 topics that best represent the document content.\n"
    "- Respond with ONLY a JSON object, no other text.\n\n"
    "JSON format:\n"
    '{"summary": "2-3 sentence summary here.", "topics": ["topic1", "topic two", "topic3"]}'
)


# ── KnowledgeAgent ───────────────────────────────────────────────────────────


class KnowledgeAgent:
    """Service that calls DeepSeek (or Ollama fallback) to generate document
    summaries and extract keyword topics.

    Parameters
    ----------
    settings:
        Application settings.  Defaults to ``get_settings()``.
    http_client:
        An ``httpx.AsyncClient`` for LLM API calls.  Created internally
        if not provided (useful for mocking in tests).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._http_client = http_client

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Return (and lazily create) the httpx async client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=3.0)
            )
        return self._http_client

    async def generate_summary(self, text: str) -> dict[str, Any]:
        """Generate a summary and topics for the given document text.

        Parameters
        ----------
        text:
            Full document text.

        Returns
        -------
        dict
            Keys: ``summary`` (str), ``topics`` (list[str]).
        """
        if not text or not text.strip():
            return {"summary": "Empty document — no content to summarize.", "topics": []}

        # Truncate very long documents to ~6000 chars (roughly 3000 tokens for a
        # 2:1 char-to-token ratio) to stay within LLM context limits.
        truncated = text[:6000] if len(text) > 6000 else text

        try:
            llm_response = await self._call_llm(truncated)
            return self._parse_response(llm_response)
        except Exception:
            # Graceful fallback: extract first ~200 chars as summary snippet
            snippet = text[:200].strip().replace("\n", " ")
            return {
                "summary": f"Document summary unavailable. Preview: {snippet}...",
                "topics": [],
            }

    async def _call_llm(self, text: str) -> str:
        """Call the LLM API and return the raw response text."""
        user_prompt = f"Document text:\n\n{text}"

        messages = [
            {"role": "system", "content": KNOWLEDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Try LLM (any OpenAI-compatible provider)
        api_key = self._settings.LLM_API_KEY or self._settings.DEEPSEEK_API_KEY
        if api_key and api_key != "***":
            try:
                return await self._call_llm_api(messages)
            except Exception:
                pass

        # Try Ollama fallback
        try:
            return await self._call_ollama(messages)
        except Exception:
            pass

        # Neither LLM reachable — return a static fallback
        return json.dumps({
            "summary": "Document summary unavailable. Please ensure the LLM API is reachable.",
            "topics": [],
        })

    async def _call_llm_api(self, messages: list[dict[str, str]]) -> str:
        """Call any OpenAI-compatible chat completions API.

        Uses LLM_API_KEY / LLM_BASE_URL / LLM_MODEL when set,
        falls back to DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / "deepseek-chat".
        """
        api_key = self._settings.LLM_API_KEY or self._settings.DEEPSEEK_API_KEY
        base_url = self._settings.LLM_BASE_URL or self._settings.DEEPSEEK_BASE_URL
        model = self._settings.LLM_MODEL or "deepseek-chat"

        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self._settings.LLM_TEMPERATURE,
            "max_tokens": 512,
        }

        response = await self.http_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        """Call the Ollama chat completions API (fallback)."""
        url = f"{self._settings.OLLAMA_BASE_URL}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": "llama3.2",
            "messages": messages,
            "temperature": self._settings.LLM_TEMPERATURE,
            "max_tokens": 512,
            "stream": False,
        }

        response = await self.http_client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _parse_response(self, raw_response: str) -> dict[str, Any]:
        """Parse the LLM JSON response into a summary + topics dict.

        Handles markdown-wrapped JSON and bare JSON objects.
        """
        # Try to extract JSON from markdown code fences
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_response)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Find the outermost JSON object
            brace_start = raw_response.find("{")
            brace_end = raw_response.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                json_str = raw_response[brace_start : brace_end + 1]
            else:
                return {
                    "summary": raw_response.strip()[:200],
                    "topics": [],
                }

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            return {
                "summary": raw_response.strip()[:200],
                "topics": [],
            }

        summary = str(parsed.get("summary", ""))
        raw_topics = parsed.get("topics", [])

        # Normalize topics: lowercase, strip whitespace, remove duplicates
        topics: list[str] = []
        seen: set[str] = set()
        for t in raw_topics:
            if isinstance(t, str):
                cleaned = t.strip().lower()
                if cleaned and cleaned not in seen:
                    topics.append(cleaned)
                    seen.add(cleaned)

        return {"summary": summary, "topics": topics}

    async def close(self) -> None:
        """Close the internal HTTP client if it was created by this agent."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
