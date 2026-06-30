"""Page: CRM Sync — status widget and manual sync trigger.

Shows the latest sync run status, record counts, and a manual trigger button.
Uses GET /connectors/crm/sync/status and POST /connectors/crm/sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from utils import api
from utils.i18n import _


def _format_date(iso_str: str | None) -> str:
    """Format ISO datetime to a human-readable local-ish string."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return _("dashboard.just_now")
        if diff < 3600:
            return f"{diff // 60}{_('dashboard.min_ago')}"
        if diff < 86400:
            return f"{diff // 3600}{_('dashboard.hr_ago')}"
        if diff < 604800:
            return f"{diff // 86400}{_('dashboard.day_ago')}"
        return dt.strftime("%b %d, %Y %H:%M")
    except (ValueError, TypeError):
        return iso_str[:19]


def _status_badge(status: str) -> str:
    """Return a colourful badge for the sync status."""
    badges = {
        "never":    _("⚪ Never run"),
        "running":  _("🔄 Running…"),
        "success":  _("🟢 Success"),
        "error":    _("🔴 Error"),
    }
    return badges.get(status, _(f"❓ {status}"))


def render() -> None:
    """Render the CRM Sync page."""
    st.title(_("crm_sync.title"))

    st.markdown(_("crm_sync.description"))

    # ── Sync action ────────────────────────────────────────────────────
    st.subheader(_("crm_sync.trigger"))

    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        if st.button(
            _("crm_sync.sync_now"),
            type="primary",
            use_container_width=True,
            help=_("crm_sync.sync_help"),
        ):
            with st.spinner(_("crm_sync.syncing")):
                try:
                    result = api.trigger_sync()
                    st.success(_("crm_sync.synced_ok"))
                    st.session_state.sync_triggered = True
                except Exception as exc:
                    st.error(_("crm_sync.sync_failed", err=exc))

    # ── Auto-refresh checkbox ──────────────────────────────────────────
    auto_refresh = st.checkbox(
        _("crm_sync.auto_refresh"),
        key="sync_auto_refresh",
        value=st.session_state.get("sync_auto_refresh", False),
    )
    if auto_refresh:
        st.caption(_("crm_sync.refreshing"))
        import time
        time.sleep(5)
        st.rerun()

    st.divider()

    # ── Load and display current status ─────────────────────────────────
    with st.spinner(_("crm_sync.spinner")):
        try:
            sync_status = api.get_sync_status()
        except Exception as exc:
            st.error(_("❌ Failed to load sync status: {err}", err=exc))
            return

    status = sync_status.get("status", "never")

    st.subheader(_("crm_sync.status"))
    st.markdown(f"**{_status_badge(status)}**")

    # ── Record counts (always visible) ─────────────────────────────────
    st.subheader(_("crm_sync.records"))
    total_contacts = sync_status.get("total_contacts", 0)
    total_deals = sync_status.get("total_deals", 0)
    total_activities = sync_status.get("total_activities", 0)

    col_c, col_d, col_a = st.columns(3)
    with col_c:
        st.metric(_("👤 Contacts"), total_contacts)
    with col_d:
        st.metric(_("💰 Deals"), total_deals)
    with col_a:
        st.metric(_("📝 Activities"), total_activities)

    # ── Run details (only if a sync has ever run) ──────────────────────
    if status != "never":
        st.divider()
        st.subheader(_("crm_sync.last_details"))

        started = _format_date(sync_status.get("started_at"))
        completed = _format_date(sync_status.get("completed_at"))

        col1, col2 = st.columns(2)
        with col1:
            st.caption(_("crm_sync.started", d=started))
            st.caption(_("crm_sync.completed", d=completed))
        with col2:
            contacts_synced = sync_status.get("contacts_synced", 0)
            deals_synced = sync_status.get("deals_synced", 0)
            activities_synced = sync_status.get("activities_synced", 0)
            st.caption(_("crm_sync.contacts_synced", n=contacts_synced))
            st.caption(_("crm_sync.deals_synced", n=deals_synced))
            st.caption(_("crm_sync.activities_synced", n=activities_synced))

        # RAG enrichment details
        rag_docs = sync_status.get("rag_documents_created", 0)
        rag_chunks = sync_status.get("rag_chunks_created", 0)
        if rag_docs or rag_chunks:
            st.caption(_("crm_sync.rag_docs", n=rag_docs))
            st.caption(_("crm_sync.rag_chunks", n=rag_chunks))

        # Error message
        if status == "error":
            error_msg = sync_status.get("error_message", "Unknown error")
            st.error(_("crm_sync.error", msg=error_msg))
