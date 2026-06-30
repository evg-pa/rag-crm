"""Page 3: Q&A Chat — ask questions and get answers with citations."""

from __future__ import annotations

import streamlit as st

from components.chat_message import render_chat_history
from utils import api, state
from utils.i18n import _


def _run_qa(prompt: str) -> None:
    """Execute the QA pipeline for a given prompt and append the response."""
    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "sources": None,
    })

    with st.spinner(_("qa.searching")):
        try:
            top_k = st.session_state.get("qa_top_k", 5)
            session_id = st.session_state.get("qa_session_id", "default")
            response = api.ask_question(prompt, top_k=top_k, session_id=session_id)

            answer_text = response.get("answer_text") or response.get(
                "final_response", "No answer generated."
            )
            citations = response.get("citations", [])
            confidence = response.get("confidence_score", 0.0)
            query_type = response.get("query_type", "")

            # Check if this is a "not found" / empty answer
            is_no_answer = False
            if confidence < 0.15 or not answer_text.strip():
                is_no_answer = True
            no_info_phrases = (
                "i don't have enough information",
                "no relevant information",
                "the provided context does not contain",
                "i cannot answer",
                "there is no information",
            )
            if any(phrase in answer_text.lower() for phrase in no_info_phrases):
                is_no_answer = True

            content_parts = []
            if is_no_answer:
                content_parts.append(
                    _("qa.no_answer")
                )
            else:
                content_parts.append(answer_text)
                if confidence > 0:
                    content_parts.append(f"\n\n{_('qa.confidence', pct=confidence * 100)}")
                if query_type:
                    content_parts.append(_("qa.query_type", type=query_type))

            st.session_state.messages.append({
                "role": "assistant",
                "content": " ".join(content_parts),
                "sources": citations,
            })
        except Exception as exc:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"❌ Error: {exc}",
                "sources": None,
            })


def render() -> None:
    """Render the Q&A Chat page."""
    st.title(_("qa.title"))
    st.caption(_("qa.caption"))

    # ── Settings (collapsible) ──────────────────────────────────────────
    with st.expander(_("qa.settings"), expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            top_k = st.slider(
                _("qa.top_k"),
                min_value=1,
                max_value=50,
                value=st.session_state.get("qa_top_k", 5),
                step=1,
                key="qa_top_k_slider",
                help=_("qa.top_k_help"),
            )
            st.session_state.qa_top_k = top_k
        with col2:
            session_id = st.text_input(
                _("qa.session_id"),
                value=st.session_state.get("qa_session_id", "default"),
                key="qa_session_id_input",
                help=_("qa.session_help"),
            )
            st.session_state.qa_session_id = session_id

    # ── Chat History ────────────────────────────────────────────────────
    render_chat_history(st.session_state.messages)

    # ── Suggested Questions ─────────────────────────────────────────────
    if not st.session_state.messages:
        st.divider()
        st.caption(_("qa.try_asking"))
        suggestions = [
            _("qa.suggest_about"),
            _("qa.suggest_tech"),
            _("qa.suggest_features"),
            _("qa.suggest_arch"),
        ]
        cols = st.columns(len(suggestions))
        for col, suggestion in zip(cols, suggestions, strict=True):
            with col:
                if st.button(
                    suggestion,
                    key=f"suggest_{suggestion[:20]}",
                    use_container_width=True,
                ):
                    st.session_state.pending_question = suggestion
                    st.rerun()

    # ── Chat Input ──────────────────────────────────────────────────────
    if prompt := st.chat_input(_("qa.chat_input")):
        _run_qa(prompt)
        st.rerun()

    # Handle pending question from suggestion button
    if "pending_question" in st.session_state:
        prompt = st.session_state.pending_question
        del st.session_state.pending_question
        _run_qa(prompt)
        st.rerun()

    # ── Utility Buttons ─────────────────────────────────────────────────
    if st.session_state.messages:
        st.divider()
        col_clear, _ = st.columns(2)
        with col_clear:
            if st.button(_("qa.clear_btn"), use_container_width=True):
                state.clear_chat()
                st.rerun()
