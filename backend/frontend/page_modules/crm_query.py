"""Page: CRM Quick Query — run preset or free-form CRM queries against the backend."""

from __future__ import annotations

import streamlit as st

from utils import api


def _load_presets() -> list[dict]:
    """Load available CRM quick-query presets from the backend."""
    try:
        data = api.get_crm_presets()
        return data.get("presets", [])
    except Exception:
        return []


def _render_preset_buttons(presets: list[dict]) -> str | None:
    """Render preset buttons in a grid layout.

    Returns the selected preset key, or None if no preset was clicked.
    """
    if not presets:
        st.info("No CRM presets available. Check backend connectivity.")
        return None

    selected: str | None = None
    # Render in rows of 2
    cols_per_row = 2
    for i in range(0, len(presets), cols_per_row):
        row_presets = presets[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, preset in enumerate(row_presets):
            with cols[j]:
                key = preset.get("key", "")
                label = preset.get("label", key)
                description = preset.get("description", "")

                # Use a container with border styling for each preset card
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    st.caption(description)
                    if st.button(
                        f"🚀 Run \"{label}\"",
                        key=f"crm_preset_{key}",
                        use_container_width=True,
                    ):
                        selected = key

    return selected


def _render_results(response: dict) -> None:
    """Render the CRM quick-query results."""
    intent = response.get("intent", "")
    summary = response.get("summary", "")
    formatted = response.get("formatted", "")
    data = response.get("data", {})

    if intent:
        st.caption(f"**Intent:** `{intent}`")

    # Summary
    if summary:
        st.markdown("### Summary")
        st.markdown(f"> {summary}")

    # Data
    if data:
        st.markdown("### Results")

        # Deal lists
        if "deals" in data:
            import pandas as pd

            deals = data["deals"]
            if deals:
                rows = []
                for d in deals:
                    value = d.get("value")
                    rows.append({
                        "Name": d.get("name", "—"),
                        "Value": f"${value:,.0f}" if value else "—",
                        "Stage": (d.get("stage") or "").replace("_", " ").title(),
                        "Contact": d.get("contact", "—"),
                        "Close Date": d.get("close_date", "—")[:10] if d.get("close_date") else "—",
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Contact lists
        if "contacts" in data:
            import pandas as pd

            contacts = data["contacts"]
            if contacts:
                rows = []
                for c in contacts:
                    rows.append({
                        "Name": c.get("name", "—"),
                        "Email": c.get("email") or "—",
                        "Phone": c.get("phone") or "—",
                        "Company": c.get("company") or "—",
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Activities
        if "activities" in data:
            import pandas as pd

            activities = data["activities"]
            if activities:
                rows = []
                for a in activities:
                    rows.append({
                        "Type": (a.get("type") or "").title(),
                        "Description": a.get("description", "—"),
                        "Date": a.get("date", "—")[:10] if a.get("date") else "—",
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Pipeline summary
        if "stages" in data:
            stages = data["stages"]
            if stages:
                st.markdown("**Deals by Stage**")
                for stage_name, count in stages.items():
                    st.metric(
                        stage_name.replace("_", " ").title(),
                        count,
                    )

        # Fallback: render any other structured data as JSON
        if not any(k in data for k in ("deals", "contacts", "activities", "stages")):
            st.json(data)

    # Formatted text (full markdown answer)
    if formatted:
        st.markdown("### Full Answer")
        st.markdown(formatted)


def render() -> None:
    """Render the CRM Quick Query page."""
    st.title("💬 CRM Quick Query")

    st.markdown(
        "Ask natural-language questions about your CRM data. "
        "Use preset queries below or type a free-form question."
    )

    # ── Presets ──────────────────────────────────────────────────────────
    st.subheader("📋 Preset Queries")

    presets = _load_presets()
    selected_preset = _render_preset_buttons(presets)

    # ── Free-form query ──────────────────────────────────────────────────
    st.subheader("✏️ Free-Form Query")
    st.caption("Ask anything about your CRM: \"Show top 5 deals by value\", \"Which contacts are in Acme Corp?\", etc.")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        query = st.text_input(
            "Your CRM question",
            key="crm_query_input",
            placeholder="e.g. Show deals closing this month",
            label_visibility="collapsed",
        )
    with col_btn:
        send_clicked = st.button("🔍 Query", type="primary", use_container_width=True, key="crm_query_send")

    # ── Determine what to send ───────────────────────────────────────────
    effective_query: str | None = None
    effective_preset: str | None = None

    if selected_preset:
        # Find preset details
        for p in presets:
            if p.get("key") == selected_preset:
                effective_preset = selected_preset
                effective_query = p.get("query", selected_preset)
                break

    if send_clicked and query.strip():
        effective_query = query.strip()
        effective_preset = None

    # ── Execute query ────────────────────────────────────────────────────
    if effective_query:
        with st.spinner("Running CRM query..."):
            try:
                response = api.crm_quick_query(
                    query=effective_query,
                    preset=effective_preset,
                    limit=st.session_state.get("crm_query_limit", 10),
                )
                # Store in session for reuse across reruns
                st.session_state.crm_query_response = response
            except Exception as exc:
                st.error(f"❌ Query failed: {exc}")
                st.session_state.crm_query_response = None

    # ── Display results ──────────────────────────────────────────────────
    response = st.session_state.get("crm_query_response")
    if response:
        st.divider()
        _render_results(response)

    # ── Limit slider ─────────────────────────────────────────────────────
    with st.sidebar:
        st.divider()
        st.caption("⚙️ CRM Query Settings")
        limit = st.slider(
            "Result limit",
            min_value=1,
            max_value=100,
            value=st.session_state.get("crm_query_limit", 10),
            step=1,
            key="crm_query_limit_slider",
        )
        st.session_state.crm_query_limit = limit
