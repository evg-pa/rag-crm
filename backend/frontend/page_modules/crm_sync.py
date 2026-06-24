"""Page: CRM Sync — status widget and manual sync trigger.

Shows the latest sync run status, record counts, and a manual trigger button.
Uses GET /connectors/crm/sync/status and POST /connectors/crm/sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from utils import api


def _format_date(iso_str: str | None) -> str:
    """Format ISO datetime to a human-readable local-ish string."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return "just now"
        if diff < 3600:
            return f"{diff // 60}m ago"
        if diff < 86400:
            return f"{diff // 3600}h ago"
        if diff < 604800:
            return f"{diff // 86400}d ago"
        return dt.strftime("%b %d, %Y %H:%M")
    except (ValueError, TypeError):
        return iso_str[:19]


def _status_badge(status: str) -> str:
    """Return a colourful badge for the sync status."""
    badges = {
        "never":    "⚪ Never run",
        "running":  "🔄 Running…",
        "success":  "🟢 Success",
        "error":    "🔴 Error",
    }
    return badges.get(status, f"❓ {status}")


def render() -> None:
    """Render the CRM Sync page."""
    st.title("🔄 CRM Sync")

    st.markdown(
        "Monitor CRM data sync status and trigger manual syncs. "
        "Data is pulled from your connected CRM adapter into the local database."
    )

    # ── Sync action ────────────────────────────────────────────────────
    st.subheader("Trigger Sync")

    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        if st.button(
            "🔄 Sync Now",
            type="primary",
            use_container_width=True,
            help="Trigger a full sync from the CRM adapter",
        ):
            with st.spinner("Triggering sync..."):
                try:
                    result = api.trigger_sync()
                    st.success("✅ Sync triggered! It may take a minute to complete.")
                    st.session_state.sync_triggered = True
                except Exception as exc:
                    st.error(f"❌ Failed to trigger sync: {exc}")

    # ── Auto-refresh checkbox ──────────────────────────────────────────
    auto_refresh = st.checkbox(
        "Auto-refresh every 10s (useful while sync is running)",
        key="sync_auto_refresh",
        value=st.session_state.get("sync_auto_refresh", False),
    )
    if auto_refresh:
        st.caption("⏳ Refreshing automatically…")
        import time
        time.sleep(5)
        st.rerun()

    st.divider()

    # ── Load and display current status ─────────────────────────────────
    with st.spinner("Loading sync status..."):
        try:
            sync_status = api.get_sync_status()
        except Exception as exc:
            st.error(f"❌ Failed to load sync status: {exc}")
            return

    status = sync_status.get("status", "never")

    st.subheader("Status")
    st.markdown(f"**{_status_badge(status)}**")

    # ── Record counts (always visible) ─────────────────────────────────
    st.subheader("📊 Current Record Counts")
    total_contacts = sync_status.get("total_contacts", 0)
    total_deals = sync_status.get("total_deals", 0)
    total_activities = sync_status.get("total_activities", 0)

    col_c, col_d, col_a = st.columns(3)
    with col_c:
        st.metric("👤 Contacts", total_contacts)
    with col_d:
        st.metric("💰 Deals", total_deals)
    with col_a:
        st.metric("📝 Activities", total_activities)

    # ── Run details (only if a sync has ever run) ──────────────────────
    if status != "never":
        st.divider()
        st.subheader("Last Sync Details")

        started = _format_date(sync_status.get("started_at"))
        completed = _format_date(sync_status.get("completed_at"))

        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"**Started:** {started}")
            st.caption(f"**Completed:** {completed}")
        with col2:
            contacts_synced = sync_status.get("contacts_synced", 0)
            deals_synced = sync_status.get("deals_synced", 0)
            activities_synced = sync_status.get("activities_synced", 0)
            st.caption(f"**Contacts synced:** {contacts_synced}")
            st.caption(f"**Deals synced:** {deals_synced}")
            st.caption(f"**Activities synced:** {activities_synced}")

        # RAG enrichment details
        rag_docs = sync_status.get("rag_documents_created", 0)
        rag_chunks = sync_status.get("rag_chunks_created", 0)
        if rag_docs or rag_chunks:
            st.caption(f"**RAG documents created:** {rag_docs}")
            st.caption(f"**RAG chunks created:** {rag_chunks}")

        # Error message
        if status == "error":
            error_msg = sync_status.get("error_message", "Unknown error")
            st.error(f"❌ Sync error: {error_msg}")
