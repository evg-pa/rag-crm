"""Chat message components for Q&A Chat page."""

from __future__ import annotations

import streamlit as st

from utils.i18n import _


def chat_bubble(role: str, content: str, sources: list[dict] | None = None) -> None:
    """Render a single chat message bubble.

    Args:
        role: "user" or "assistant".
        content: Markdown content of the message.
        sources: Optional list of source citations.
    """
    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    else:
        with st.chat_message("assistant"):
            st.markdown(content)
            if sources:
                _render_sources(sources)


def _render_sources(sources: list[dict]) -> None:
    """Render expandable source citations."""
    with st.expander(_('chat.sources', n=len(sources)), expanded=False):
        for i, src in enumerate(sources, 1):
            snippet = src.get("content_snippet", "")[:200]
            doc_id = src.get("document_id", "unknown")
            chunk_id = src.get("chunk_id", "")
            st.caption(f"[{i}] doc:`{doc_id[:12]}…` chunk:`{chunk_id[:12]}…`")
            st.caption(f"> {snippet}")


def render_chat_history(messages: list[dict]) -> None:
    """Render the full chat history from a list of messages.

    Args:
        messages: List of message dicts with 'role', 'content', and optional 'sources'.
    """
    for msg in messages:
        chat_bubble(
            role=msg["role"],
            content=msg["content"],
            sources=msg.get("sources"),
        )
