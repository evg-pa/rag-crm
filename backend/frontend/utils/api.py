"""API client for the RAG-CRM backend.

Uses synchronous httpx client (Streamlit's execution model is synchronous).
Base URL is configurable via BACKEND_URL env var or defaults to localhost:8000.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

BACKEND_URL: str = os.environ.get("BACKEND_URL", "http://localhost:8000")
TIMEOUT: float = float(os.environ.get("BACKEND_TIMEOUT", "120.0"))


def _get_client() -> httpx.Client:
    """Return (or create and cache) a synchronous httpx client."""
    if "api_client" not in st.session_state:
        st.session_state.api_client = httpx.Client(
            base_url=BACKEND_URL,
            timeout=TIMEOUT,
        )
    return st.session_state.api_client


# ── Health ───────────────────────────────────────────────────────────────────


def health_check() -> dict[str, Any]:
    """GET /health — system health with database status."""
    r = _get_client().get("/health")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def pipeline_status() -> dict[str, Any]:
    """GET /pipeline/status — LangGraph agent statuses."""
    r = _get_client().get("/pipeline/status")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


# ── Documents ────────────────────────────────────────────────────────────────


def list_documents() -> list[dict[str, Any]]:
    """GET /documents — list all ingested documents."""
    r = _get_client().get("/documents")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def get_document(document_id: str) -> dict[str, Any]:
    """GET /documents/{id} — get document with chunks."""
    r = _get_client().get(f"/documents/{document_id}")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def upload_document(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """POST /documents/upload — upload a file for ingestion."""
    r = _get_client().post(
        "/documents/upload",
        files={"file": (filename, file_bytes)},
    )
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def delete_document(document_id: str) -> dict[str, Any]:
    """DELETE /documents/{id} — delete a document and its chunks."""
    r = _get_client().delete(f"/documents/{document_id}")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def scrape_url(url: str) -> dict[str, Any]:
    """POST /documents/scrape — scrape and ingest a web page."""
    r = _get_client().post(
        "/documents/scrape",
        json={"url": url},
    )
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def get_supported_extensions() -> dict[str, Any]:
    """GET /documents/supported — list supported extensions."""
    r = _get_client().get("/documents/supported")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


# ── Q&A ──────────────────────────────────────────────────────────────────────


def ask_question(query: str, top_k: int = 5, session_id: str = "default") -> dict[str, Any]:
    """POST /qa — run the LangGraph QA pipeline."""
    r = _get_client().post(
        "/qa",
        json={"query": query, "top_k": top_k, "session_id": session_id},
    )
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def get_qa_history() -> dict[str, Any]:
    """GET /qa/history — QA query history (stub)."""
    r = _get_client().get("/qa/history")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


# ── Search ────────────────────────────────────────────────────────────────────


def semantic_search(query: str, top_k: int = 10) -> dict[str, Any]:
    """GET /search — semantic search by embedding similarity."""
    r = _get_client().get("/search", params={"q": query, "top_k": top_k})
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def hybrid_search(
    query: str,
    top_k: int = 10,
    semantic_weight: float = 0.5,
    bm25_weight: float = 0.5,
) -> dict[str, Any]:
    """GET /search/hybrid — semantic + BM25 + reranker search."""
    r = _get_client().get(
        "/search/hybrid",
        params={
            "q": query,
            "top_k": top_k,
            "semantic_weight": semantic_weight,
            "bm25_weight": bm25_weight,
        },
    )
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


# ── Wiki / Knowledge Base ─────────────────────────────────────────────────────


def list_wiki_entries(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """GET /wiki — list wiki entries with pagination."""
    r = _get_client().get("/wiki", params={"page": page, "page_size": page_size})
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def get_wiki_entry(document_id: str) -> dict[str, Any]:
    """GET /wiki/{id} — get a specific wiki entry."""
    r = _get_client().get(f"/wiki/{document_id}")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def refresh_wiki_entry(document_id: str) -> dict[str, Any]:
    """POST /wiki/refresh/{id} — regenerate wiki entry for a document."""
    r = _get_client().post(f"/wiki/refresh/{document_id}")
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def search_wiki(query: str) -> list[dict[str, Any]]:
    """GET /wiki/search?q= — search wiki entries by keyword."""
    r = _get_client().get("/wiki/search", params={"q": query})
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]
