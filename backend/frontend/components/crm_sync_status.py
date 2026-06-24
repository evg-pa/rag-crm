"""CRM Sync Status widget — last sync time, record counts, manual trigger."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from utils import api


def _format_time_ago(iso_str: str | None) -> str:
    """Convert ISO timestamp to human-readable relative time."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 0:
            return "just now"
        if diff < 60:
            return "just now"
        if diff < 3600:
            m = diff // 60
            return f"{m}m ago"
        if diff < 86400:
            h = diff // 3600
            return f"{h}h ago"
        d = diff // 86400
        return f"{d}d ago"
    except (ValueError, TypeError):
        return "—"


def _status_icon(status: str) -> str:
    """Return an emoji + label for sync status."""
    icons = {
        "success": "✅",
        "running": "🔄",
        "pending": "⏳",
        "error": "❌",
        "never": "⏸️",
    }
    labels = {
        "success": "Synced",
        "running": "Syncing…",
        "pending": "Queued",
        "error": "Failed",
        "never": "No syncs",
    }
    return f"{icons.get(status, '❓')} {labels.get(status, status)}"


def _render_sync_card() -> None:
    """Render the sync status card — status, last sync, record counts, trigger."""
    try:
        status_data = api.get_sync_status()
    except Exception:
        st.warning("⚠️ Unable to fetch sync status from backend.")
        return

    status = status_data.get("status", "never")
    completed_at = status_data.get("completed_at")
    contacts = status_data.get("total_contacts", 0)
    deals = status_data.get("total_deals", 0)
    activities = status_data.get("total_activities", 0)
    error_msg = status_data.get("error_message")

    # ── Status header ──────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="rag-card" style="margin-bottom: 16px;">
            <div style="display:flex; align-items:center; justify-content:space-between;">
                <div>
                    <span style="font-size:1.1rem; font-weight:600; color:var(--text-primary);">
                        🔗 CRM Sync
                    </span>
                    <span style="margin-left:10px; font-size:0.9rem; color:var(--text-secondary);">
                        {_status_icon(status)}
                    </span>
                </div>
                <span style="font-size:0.8rem; color:var(--text-secondary);">
                    Last sync: {_format_time_ago(completed_at)}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Record counts (KPI-style row) ──────────────────────────────────
    cols = st.columns(3)
    with cols[0]:
        st.metric("👤 Contacts", contacts)
    with cols[1]:
        st.metric("💰 Deals", deals)
    with cols[2]:
        st.metric("📋 Activities", activities)

    # ── Synced counts (if a sync has run) ──────────────────────────────
    if status not in ("never",) and status_data.get("contacts_synced", 0) > 0:
        st.caption(
            f"Last sync ingested: "
            f"{status_data.get('contacts_synced', 0)} contacts, "
            f"{status_data.get('deals_synced', 0)} deals, "
            f"{status_data.get('activities_synced', 0)} activities"
        )

    # ── Error display ──────────────────────────────────────────────────
    if status == "error" and error_msg:
        st.error(f"**Sync error:** {error_msg}")

    # ── Manual trigger button ──────────────────────────────────────────
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button(
            "🔄 Sync Now",
            key="crm_sync_trigger",
            type="primary",
            disabled=(status == "running"),
            use_container_width=True,
        ):
            try:
                api.trigger_sync()
                st.toast("✅ Sync triggered! Refresh to see progress.", icon="🔄")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to trigger sync: {exc}")


def crm_sync_status() -> None:
    """Render the CRM sync status widget.

    Shows last sync time, record counts, errors, and a manual trigger button.
    Follows the kpi_card.py component pattern — uses rag-card CSS class
    for the status header and st.metric for KPI-style counts.
    """
    _render_sync_card()
