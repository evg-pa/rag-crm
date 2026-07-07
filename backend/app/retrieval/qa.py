"""AnswerAgent: single-agent Q&A backed by hybrid search + DeepSeek LLM.

Pipeline:
  1. Embed the query and run hybrid search (semantic + BM25 + reranker)
  2. Build a context prompt from the top retrieved chunks
  3. Call DeepSeek API (or Ollama fallback) to generate an answer with citations
  4. Return AnswerResult with answer_text, citations, and confidence_score
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.dependencies import get_settings
from app.core.runtime_config import resolve as resolve_runtime

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
    "does not contain enough information to answer the question, or if the context "
    "is clearly about a different topic than the question, say so clearly — respond "
    'with a JSON object that has "answer_text" set to a message like '
    '"I don\'t have enough information to answer that question." and '
    '"confidence_score": 0.0.\n\n'
    "Rules:\n"
    "- NEVER make up facts or use information not present in the chunks above.\n"
    "- If you are uncertain whether the context answers the question, say so.\n"
    "- It is better to say 'I don't know' than to guess or hallucinate.\n\n"
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


def build_context_prompt(chunks: list[dict[str, Any]], query: str | None = None) -> str:
    """Build a context string from retrieved chunks for the LLM prompt.

    If a query is provided, scans for chunks with a high BM25 score
    and prepends a focused direct-quote from the best-matching portion
    so the LLM can't miss exact keyword hits buried inside a larger chunk.
    """
    if not chunks:
        return "No relevant context chunks were found."

    parts: list[str] = []
    bm25_excerpt: str | None = None

    if query:
        # Find the chunk with the highest BM25 score
        best_bm25_chunk: dict[str, Any] | None = None
        best_bm25_score: float = 0.0
        for c in chunks:
            s = float(c.get("bm25_score", 0.0) or 0.0)
            if s > best_bm25_score:
                best_bm25_score = s
                best_bm25_chunk = c

        # If a strong BM25 match exists, extract relevant lines
        if best_bm25_chunk and best_bm25_score > 1.0:
            content = best_bm25_chunk.get("content", "")
            doc_id = best_bm25_chunk.get("document_id", "?")
            chunk_id = best_bm25_chunk.get("id", "?")
            import re as _re
            # Find lines containing any query token (length > 2)
            q_tokens = {t for t in _re.split(r"[^a-zA-Z0-9]+", query.lower()) if len(t) > 2}
            lines = content.split("\n")
            matched_lines: list[str] = []
            found_date = False
            for line in lines:
                line_lower = line.lower()
                if any(tok in line_lower for tok in q_tokens if len(tok) > 2):
                    matched_lines.append(line.strip())
                    found_date = True
                elif found_date:
                    # Keep collecting context after the first match in this chunk
                    matched_lines.append(line.strip())

            if matched_lines:
                # Only keep lines from the last date match onwards
                date_idx = -1
                for i, l in enumerate(matched_lines):
                    if _re.search(r"\d{2,4}[-./]\d{1,2}[-./]\d{2,4}", l):
                        date_idx = i
                if date_idx >= 0:
                    matched_lines = matched_lines[date_idx:]

                bm25_excerpt = (
                    f"📌 **EXACT MATCH from the knowledge base (BM25 score: {best_bm25_score:.1f})**\n"
                    f"Document: {doc_id}  Chunk: {chunk_id}\n"
                    f"```\n" + "\n".join(matched_lines) + "\n```\n"
                    f"--- The above lines are an EXACT KEYWORD MATCH for your query. "
                    f"Use them as your primary source for a direct answer. ---"
                )

    if bm25_excerpt:
        parts.append(bm25_excerpt)

    for i, chunk in enumerate(chunks, start=1):
        chunk_id = chunk.get("id", "unknown")
        document_id = chunk.get("document_id", "unknown")
        content = chunk.get("content", "")
        parts.append(
            f"[Chunk {i}] (chunk_id: {chunk_id}, document_id: {document_id})\nContent: {content}"
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
        """Return (and lazily create) the httpx async client with short timeout."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
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
                answer_text="I don't have enough information in the knowledge base to answer your question. Try uploading relevant documents first, or rephrase your query.",
                citations=[],
                confidence_score=0.0,
            )

        # Build context prompt
        context = build_context_prompt(selected, query=query)

        # Call LLM with overall timeout
        try:
            llm_response = await asyncio.wait_for(self._call_llm(query, context), timeout=45.0)
        except TimeoutError:
            llm_response = json.dumps(
                {
                    "answer_text": (
                        "The AI model took too long to respond. Please try asking again."
                    ),
                    "citations": [],
                    "confidence_score": 0.0,
                }
            )

        # Parse LLM response
        result = self._parse_llm_response(llm_response, selected)
        # Post-processing: override low-confidence / empty answers
        return self._enforce_honesty(result, chunks_present=bool(selected), chunks=selected)

    # ── Honest "not found" guard ──────────────────────────────────────
    # If reranker scores are present and the top chunk scores below
    # threshold, the context is likely irrelevant — refuse to answer.
    # Also catches empty / LLM-rejected answers with an honest refusal.
    @staticmethod
    def _enforce_honesty(result: AnswerResult, chunks_present: bool, chunks: list[dict[str, Any]] | None = None) -> AnswerResult:
        """Override poor-quality answers with an honest refusal.

        Three safety layers:
        1. If no chunks were provided → immediate refusal
        2. If the top chunk's reranker_score is very low (< 0.1) → refusal
           (the context doesn't match the question)
        3. If the answer text is empty or the LLM itself said "i don't know"
           → refusal
        """
        if not chunks_present:
            return AnswerResult(
                answer_text=(
                    "I don't have enough information in the knowledge base to "
                    "answer your question. Try uploading relevant documents first, "
                    "or rephrase your query."
                ),
                citations=[],
                confidence_score=0.0,
            )

        # Layer 2: score-based guard — if the best chunk is very low relevance,
        # don't trust anything the LLM says (it's probably hallucinating).
        if chunks:
            best_score: float = -1.0
            score_source: str = "none"
            for c in chunks:
                s = c.get("reranker_score")
                if s is None:
                    s = c.get("score")
                if s is not None:
                    try:
                        v = float(s)
                        if v > best_score:
                            best_score = v
                            score_source = "reranker_score" if "reranker_score" in c else "score"
                    except (ValueError, TypeError):
                        pass

            # Reranker score: range is roughly [-5, 5], threshold 0.1 means 'barely relevant'
            # Bypass check if any chunk has a positive BM25 keyword score (exact match)
            has_bm25_hit = any(
                float(c.get("bm25_score", 0.0) or 0.0) > 0
                for c in chunks
            )
            if not has_bm25_hit and score_source == "reranker_score" and best_score >= 0 and best_score < 0.1:
                return AnswerResult(
                    answer_text=(
                        "I don't have enough information in the knowledge base to "
                        "answer your question. Try uploading relevant documents first, "
                        "or rephrase your query."
                    ),
                    citations=[],
                    confidence_score=0.0,
                )

            # Embedding score: typically cosine similarity [0, 1], threshold 0.35
            if score_source == "score" and best_score < 0.35:
                return AnswerResult(
                    answer_text=(
                        "I don't have enough information in the knowledge base to "
                        "answer your question. Try uploading relevant documents first, "
                        "or rephrase your query."
                    ),
                    citations=[],
                    confidence_score=0.0,
                )

        answer = result.answer_text.strip().lower()

        # Layer 3: only override if the LLM itself said it can't answer
        is_explicit_refusal = answer in ("", ".", "...", "i don't know", "i don't know.")
        llm_says_no_info = any(
            answer.startswith(p)
            for p in (
                "no relevant information found",
                "the provided context does not contain",
                "the context does not contain",
                "i cannot answer",
                "there is no information",
                "i don't have enough information",
                "i don't know enough",
                "not enough information",
                "the context is about a different",
                "the chunks provided",
                "i found relevant documents",
            )
        )

        if is_explicit_refusal or llm_says_no_info:
            return AnswerResult(
                answer_text=(
                    "I don't have enough information in the knowledge base to "
                    "answer your question. Try uploading relevant documents first, "
                    "or rephrase your query."
                ),
                citations=[],
                confidence_score=0.0,
            )
        return result

    async def _call_llm(self, query: str, context: str) -> str:
        """Call the LLM API and return the raw response text.

        Tries DeepSeek first; falls back to Ollama. Returns a graceful
        fallback if neither is reachable. Uses httpx built-in timeout
        (8s total, 3s connect) so no nested wait_for needed.
        """
        user_prompt = f"Context:\n{context}\n\nQuestion: {query}"

        messages = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Try LLM (any OpenAI-compatible provider)
        api_key = self._settings.LLM_API_KEY or self._settings.DEEPSEEK_API_KEY or ""
        if api_key and api_key != "***":
            try:
                return await self._call_llm_api(messages)
            except Exception:
                pass

        # Try Ollama
        try:
            return await self._call_ollama(messages)
        except Exception:
            pass

        # Neither LLM is reachable — return honest fallback
        return json.dumps(
            {
                "answer_text": (
                    "I don't have enough information in the knowledge base to "
                    "answer your question. Try uploading relevant documents first, "
                    "or rephrase your query."
                ),
                "citations": [],
                "confidence_score": 0.0,
            }
        )

    async def _call_llm_api(self, messages: list[dict[str, str]]) -> str:
        """Call any OpenAI- or Anthropic-compatible chat API.

        Uses LLM_API_KEY / LLM_BASE_URL / LLM_MODEL when set,
        falls back to DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / "deepseek-chat".

        Auto-detects OpenModel (``api.openmodel.ai``) and uses the Anthropic
        Messages API format (``/v1/messages``, ``x-api-key`` header) instead of
        the OpenAI ``/v1/chat/completions`` format.
        """
        api_key = resolve_runtime("LLM_API_KEY") or self._settings.LLM_API_KEY or self._settings.DEEPSEEK_API_KEY
        base_url = resolve_runtime("LLM_BASE_URL") or self._settings.LLM_BASE_URL or self._settings.DEEPSEEK_BASE_URL
        model = resolve_runtime("LLM_MODEL") or self._settings.LLM_MODEL or "deepseek-chat"

        is_openmodel = "openmodel.ai" in base_url.lower()

        if is_openmodel:
            # ── Anthropic Messages API (OpenModel) ────────────────────────
            url = f"{base_url.rstrip('/')}/v1/messages"
            headers = {
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            }
            # Convert OpenAI message format → Anthropic format
            system_msgs = [m["content"] for m in messages if m["role"] == "system"]
            chat_msgs = [m for m in messages if m["role"] != "system"]
            payload: dict[str, Any] = {
                "model": model,
                "max_tokens": 1024,
                "messages": chat_msgs,
            }
            if system_msgs:
                payload["system"] = system_msgs[0]

            response = await self.http_client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Anthropic response: data["content"] is list of blocks
            content_blocks = data.get("content", [])
            texts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return texts[0] if texts else ""

        # ── OpenAI-compatible chat completions ────────────────────────────
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
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
