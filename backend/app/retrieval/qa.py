"""AnswerAgent: single-agent Q&A backed by hybrid search + DeepSeek LLM.

Pipeline:
  1. Embed the query and run hybrid search (semantic + BM25 + reranker)
  2. Build a context prompt from the top retrieved chunks
  3. Call DeepSeek API (or Ollama fallback) to generate an answer with citations
  4. Return AnswerResult with answer_text, citations, and confidence_score
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.dependencies import get_settings

# ── Pydantic models ─────────────────────────────────────────────────────────


class Citation(BaseModel):
    """A citation linking a statement to a source chunk."""

    chunk_id: str
    document_id: str
    content_snippet: str


class AnswerResult(BaseModel):
    """The result of a single-agent Q&A call."""

    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence_score: float = 0.0


# ── Prompt template ──────────────────────────────────────────────────────────

QA_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based ONLY on the "
    "provided context chunks. Do not use any outside knowledge. If the context "
    "does not contain enough information to answer the question, say so clearly.\n\n"
    "For every factual statement in your answer, cite the relevant chunk IDs "
    "from the context.\n\n"
    "You MUST respond in valid JSON format with these exact keys:\n"
    '- "answer_text": your answer as a string\n'
    '- "citations": a list of objects, each with "chunk_id", "document_id", '
    'and "content_snippet" (a short excerpt from the chunk that supports the answer)\n'
    '- "confidence_score": a float from 0.0 to 1.0 indicating how confident '
    "you are in the answer given the context\n\n"
    "Respond with ONLY the JSON object, no other text."
)


def build_context_prompt(chunks: list[dict[str, Any]]) -> str:
    """Build a context string from retrieved chunks for the LLM prompt."""
    if not chunks:
        return "No relevant context chunks were found."

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        chunk_id = chunk.get("id", "unknown")
        document_id = chunk.get("document_id", "unknown")
        content = chunk.get("content", "")
        parts.append(
            f"[Chunk {i}] (chunk_id: {chunk_id}, document_id: {document_id})\n"
            f"Content: {content}"
        )
    return "\n\n".join(parts)


# ── AnswerAgent ──────────────────────────────────────────────────────────────


class AnswerAgent:
    """Service that answers questions using hybrid search + LLM generation.

    Uses the full hybrid search pipeline (semantic + BM25 + reranker) to
    retrieve relevant chunks, then calls a remote LLM (DeepSeek API by
    default, with Ollama as a structured fallback path) to generate a
    cited answer.

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
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def answer(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_k: int = 10,
    ) -> AnswerResult:
        """Answer a query using the provided chunks as context.

        Parameters
        ----------
        query:
            The user's question.
        chunks:
            Pre-retrieved chunks from hybrid search.  Each chunk is a dict
            with at least ``id``, ``content``, and ``document_id``.
        top_k:
            How many top chunks to include in the prompt (default 10).

        Returns
        -------
        AnswerResult
            Contains ``answer_text``, ``citations``, and ``confidence_score``.
        """
        # Limit to top_k chunks
        selected = chunks[:top_k]

        if not selected:
            return AnswerResult(
                answer_text="No relevant information found to answer your question.",
                citations=[],
                confidence_score=0.0,
            )

        # Build context prompt
        context = build_context_prompt(selected)

        # Call LLM
        llm_response = await self._call_llm(query, context)

        # Parse LLM response
        return self._parse_llm_response(llm_response, selected)

    async def _call_llm(self, query: str, context: str) -> str:
        """Call the LLM API and return the raw response text.

        Tries DeepSeek first; falls back to Ollama if DeepSeek is not
        configured.
        """
        user_prompt = f"Context:\n{context}\n\nQuestion: {query}"

        messages = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Try DeepSeek API if configured
        if self._settings.DEEPSEEK_API_KEY:
            return await self._call_deepseek(messages)

        # Fall back to Ollama
        return await self._call_ollama(messages)

    async def _call_deepseek(self, messages: list[dict[str, str]]) -> str:
        """Call the DeepSeek chat completions API."""
        url = f"{self._settings.DEEPSEEK_BASE_URL}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": self._settings.LLM_TEMPERATURE,
            "max_tokens": 1024,
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
            "max_tokens": 1024,
            "stream": False,
        }

        response = await self.http_client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _parse_llm_response(
        self,
        raw_response: str,
        chunks: list[dict[str, Any]],
    ) -> AnswerResult:
        """Parse the LLM JSON response into an AnswerResult.

        Handles cases where the LLM wraps the JSON in markdown fences
        or adds extra text.
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
                # Fallback: treat entire response as answer text
                return AnswerResult(
                    answer_text=raw_response.strip(),
                    citations=[],
                    confidence_score=0.5,
                )

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            return AnswerResult(
                answer_text=raw_response.strip(),
                citations=[],
                confidence_score=0.5,
            )

        answer_text = parsed.get("answer_text", "")
        confidence_score = float(parsed.get("confidence_score", 0.5))
        raw_citations = parsed.get("citations", [])

        # Build Citation objects
        citations: list[Citation] = []
        for cit in raw_citations:
            if isinstance(cit, dict):
                citations.append(
                    Citation(
                        chunk_id=str(cit.get("chunk_id", "")),
                        document_id=str(cit.get("document_id", "")),
                        content_snippet=str(cit.get("content_snippet", "")),
                    )
                )

        return AnswerResult(
            answer_text=answer_text,
            citations=citations,
            confidence_score=confidence_score,
        )

    async def close(self) -> None:
        """Close the internal HTTP client if it was created by this agent."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
