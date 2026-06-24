"""CRM Dashboard — contacts, deals pipeline, and activity overview."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from components.kpi_card import kpi_row
from utils import api


# ── Colour map for deal stages ────────────────────────────────────────────

STAGE_COLOURS: dict[str, str] = {
    "lead":         "#6c757d",  # grey
    "qualified":    "#0d6efd",  # blue
    "proposal":     "#6f42c1",  # purple
    "negotiation":  "#fd7e14",  # orange
    "closed_won":   "#198754",  # green
    "closed_lost":  "#dc3545",  # red
}

STAGE_LABELS: dict[str, str] = {
    "lead":         "🟢 Lead",
    "qualified":    "🔵 Qualified",
    "proposal":     "🟣 Proposal",
    "negotiation":  "🟠 Negotiation",
    "closed_won":   "✅ Won",
    "closed_lost":  "❌ Lost",
}

ACTIVE_STAGES = {"lead", "qualified", "proposal", "negotiation"}
CLOSED_STAGES = {"closed_won", "closed_lost"}


# ── Data loading helpers ────────────────────────────────────────────────────

def _fetch_deal_stats() -> dict:
    """Fetch all deals (up to 200) and compute pipeline stats locally."""
    try:
        resp = api.list_crm_deals(limit=200)
        deals = resp.get("items", [])
        total = resp.get("total", 0)
    except Exception:
        return {
            "total": 0,
            "pipeline_value": 0.0,
            "win_rate": 0.0,
            "won_value": 0.0,
            "lost_value": 0.0,
            "by_stage": {},
            "deals": [],
        }

    pipeline_value = sum(
        d.get("value") or 0 for d in deals if d.get("stage") in ACTIVE_STAGES
    )
    won = [d for d in deals if d.get("stage") == "closed_won"]
    lost = [d for d in deals if d.get("stage") == "closed_lost"]
    won_value = sum(d.get("value") or 0 for d in won)
    lost_value = sum(d.get("value") or 0 for d in lost)

    closed_total = len(won) + len(lost)
    win_rate = (len(won) / closed_total * 100) if closed_total > 0 else 0.0

    by_stage: dict[str, list] = {}
    for d in deals:
        stage = d.get("stage", "unknown")
        by_stage.setdefault(stage, []).append(d)

    return {
        "total": total,
        "pipeline_value": pipeline_value,
        "win_rate": win_rate,
        "won_value": won_value,
        "lost_value": lost_value,
        "by_stage": by_stage,
        "deals": deals,
    }


def _fetch_contact_count() -> int:
    """Fetch total contact count."""
    try:
        resp = api.list_crm_contacts(limit=1)
        return resp.get("total", 0)
    except Exception:
        return 0


def _fetch_contacts(search: str = "", offset: int = 0, limit: int = 20) -> dict:
    """Fetch contacts with optional search."""
    try:
        return api.list_crm_contacts(search=search if search else None, offset=offset, limit=limit)
    except Exception:
        return {"items": [], "total": 0, "offset": 0, "limit": 0}


def _fetch_recent_activities(limit: int = 15) -> list:
    """Fetch most recent activities."""
    try:
        resp = api.list_crm_activities(limit=limit)
        return resp.get("items", [])
    except Exception:
        return []


# ── Render helpers ──────────────────────────────────────────────────────────

def _render_kpi_cards(contact_count: int, deal_stats: dict) -> None:
    """Render the top-level KPI row."""
    pipeline_value = deal_stats.get("pipeline_value", 0.0)
    win_rate = deal_stats.get("win_rate", 0.0)
    deal_total = deal_stats.get("total", 0)

    kpi_row([
        ("Contacts", contact_count, "👤"),
        ("Deals", deal_total, "🤝"),
        ("Pipeline", f"${pipeline_value:,.0f}", "💰"),
        ("Win Rate", f"{win_rate:.0f}%", "🏆"),
    ])


def _render_pipeline_chart(by_stage: dict) -> None:
    """Render a horizontal bar chart of deals by stage."""
    if not by_stage:
        st.info("No deals in pipeline yet.")
        return

    stage_order = ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
    rows: list[dict] = []
    for stage in stage_order:
        deals_in_stage = by_stage.get(stage, [])
        count = len(deals_in_stage)
        value = sum(d.get("value") or 0 for d in deals_in_stage)
        rows.append({
            "Stage": STAGE_LABELS.get(stage, stage),
            "Count": count,
            "Value": value,
            "colour": STAGE_COLOURS.get(stage, "#6c757d"),
        })

    df = pd.DataFrame(rows)
    df = df[df["Count"] > 0]

    if df.empty:
        st.info("No deals in pipeline yet.")
        return

    st.subheader("📈 Pipeline by Stage")

    # Render as two columns: bar chart + summary table
    col_chart, col_table = st.columns([3, 2])

    with col_chart:
        chart_data = df.set_index("Stage")["Count"]
        st.bar_chart(chart_data, use_container_width=True)

    with col_table:
        for _, row in df.iterrows():
            stage_label = row["Stage"]
            count = int(row["Count"])
            value = row["Value"]
            colour = row["colour"]
            st.markdown(
                f"<span style='color:{colour};font-weight:600;'>{stage_label}</span>: "
                f"**{count}** deals · ${value:,.0f}",
                unsafe_allow_html=True,
            )


def _render_deals_table(deals: list) -> None:
    """Render a sortable table of deals."""
    if not deals:
        st.info("No deals to display.")
        return

    rows = []
    for d in deals:
        value = d.get("value")
        rows.append({
            "Deal": d.get("name", "—"),
            "Stage": STAGE_LABELS.get(d.get("stage", ""), d.get("stage", "—")),
            "Value": f"${value:,.0f}" if value else "—",
            "Close Date": _fmt_date(d.get("close_date")),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=350)


def _render_contacts_table(contacts_data: dict) -> None:
    """Render a searchable contacts table with pagination."""
    items = contacts_data.get("items", [])
    total = contacts_data.get("total", 0)

    if not items:
        st.info("No contacts to display.")
        return

    rows = []
    for c in items:
        rows.append({
            "Name": c.get("name", "—"),
            "Email": c.get("email", "—"),
            "Phone": c.get("phone", "—"),
            "Company": c.get("company", "—"),
        })

    df = pd.DataFrame(rows)
    st.caption(f"Showing {len(items)} of {total} contacts")
    st.dataframe(df, use_container_width=True, hide_index=True, height=300)


def _render_recent_activities(activities: list) -> None:
    """Render a feed of recent activities."""
    if not activities:
        st.info("No recent activity.")
        return

    activity_icons: dict[str, str] = {
        "call": "📞",
        "email": "✉️",
        "meeting": "🤝",
        "note": "📝",
    }

    for a in activities[:15]:
        a_type = a.get("type", "note")
        icon = activity_icons.get(a_type, "📌")
        desc = a.get("description", "")
        date = _fmt_date(a.get("date"))

        st.markdown(f"{icon} **{a_type.title()}** · {date}")
        if desc:
            st.caption(f"_{desc}_")


def _fmt_date(date_str: str | None) -> str:
    """Format an ISO date string to a friendly relative or short format."""
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
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
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return date_str[:10]


# ── Main render ─────────────────────────────────────────────────────────────

def render() -> None:
    """Render the CRM Dashboard page."""
    st.title("💼 CRM Dashboard")

    # ── Load data ────────────────────────────────────────────────────────
    with st.spinner("Loading CRM data..."):
        contact_count = _fetch_contact_count()
        deal_stats = _fetch_deal_stats()
        activities = _fetch_recent_activities()

    # ── KPI cards ────────────────────────────────────────────────────────
    st.subheader("Overview")
    _render_kpi_cards(contact_count, deal_stats)

    st.divider()

    # ── Two-column: Pipeline + Activities ────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        _render_pipeline_chart(deal_stats.get("by_stage", {}))

        st.divider()
        st.subheader("📋 All Deals")
        _render_deals_table(deal_stats.get("deals", []))

    with col_right:
        # ── Contacts search ──────────────────────────────────────────────
        st.subheader("👤 Contacts")
        contact_search = st.text_input(
            "Search contacts",
            placeholder="Name, email, or company...",
            key="crm_contact_search",
        )
        contacts_data = _fetch_contacts(search=contact_search)
        _render_contacts_table(contacts_data)

        st.divider()

        # ── Recent activities ────────────────────────────────────────────
        st.subheader("📋 Recent Activity")
        _render_recent_activities(activities)

    # ── Sync action ──────────────────────────────────────────────────────
    st.divider()
    col_sync, _ = st.columns([1, 3])
    with col_sync:
        if st.button("🔄 Sync CRM Data", help="Trigger a full sync from the CRM adapter"):
            with st.spinner("Syncing..."):
                try:
                    result = api.trigger_sync()
                    st.success(f"Sync triggered — status: {result.get('status', 'unknown')}")
                except Exception as exc:
                    st.error(f"Sync failed: {exc}")
