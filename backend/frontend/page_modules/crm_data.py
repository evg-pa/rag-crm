"""Page: CRM Data Browser — filter, search, and browse CRM entities.

Tabs: Contacts | Deals | Activities.
Uses existing /connectors/crm/* endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from utils import api
from utils.i18n import _


def _format_date(iso_str: str | None) -> str:
    """Format ISO date string to a human-readable short form."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def _render_contacts_tab() -> None:
    """Render the Contacts tab with search and pagination."""
    st.subheader("👤 Contacts")

    # ── Filters ─────────────────────────────────────────────────────────
    col_s, col_btn, col_p = st.columns([3, 1, 1])
    with col_s:
        search = st.text_input(
            "Search by name, email, or company",
            key="crm_contacts_search",
            placeholder="e.g. Acme, john@...",
        )
    with col_btn:
        st.write("")  # spacer
        st.write("")
        search_clicked = st.button("🔍 Search", key="crm_contacts_search_btn", use_container_width=True)

    # Track last search to avoid re-fetching on every rerun
    last_search = st.session_state.get("crm_contacts_last_search", "")
    page = st.session_state.get("crm_contacts_page", 1)
    page_size = 25

    if (search != last_search) or search_clicked:
        st.session_state.crm_contacts_last_search = search
        page = 1
        st.session_state.crm_contacts_page = 1

    with st.spinner("Loading contacts..."):
        offset = (page - 1) * page_size
        try:
            data = api.list_crm_contacts(
                offset=offset,
                limit=page_size,
                search=search if search else None,
            )
        except Exception as exc:
            st.error(f"❌ Failed to load contacts: {exc}")
            return

    items = data.get("items", [])
    total = data.get("total", 0)

    st.caption(f"**{total}** contact(s) found · Page {page} of {max(1, (total + page_size - 1) // page_size)}")

    if not items:
        st.info("No contacts found. Run a CRM sync first.")
        return

    # ── Build dataframe ─────────────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for c in items:
        rows.append({
            "Name": c.get("name", ""),
            "Email": c.get("email") or "—",
            "Phone": c.get("phone") or "—",
            "Company": c.get("company") or "—",
            "Created": _format_date(c.get("created_at")),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    # ── Pagination controls ──────────────────────────────────────────────
    total_pages = max(1, (total + page_size - 1) // page_size)
    if total_pages > 1:
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Previous", disabled=(page <= 1), key="crm_contacts_prev"):
                st.session_state.crm_contacts_page = page - 1
                st.rerun()
        with col_page:
            st.write(f"Page **{page}** of {total_pages}")
        with col_next:
            if st.button("Next →", disabled=(page >= total_pages), key="crm_contacts_next"):
                st.session_state.crm_contacts_page = page + 1
                st.rerun()


def _render_deals_tab() -> None:
    """Render the Deals tab with stage/value/date filters."""
    st.subheader("💰 Deals")

    # ── Filters ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        stage = st.selectbox(
            "Stage",
            options=["", "lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"],
            format_func=lambda x: x.replace("_", " ").title() if x else "All stages",
            key="crm_deals_stage",
        )
    with col2:
        min_value = st.number_input(
            "Min value ($)",
            min_value=0,
            value=0,
            step=10000,
            key="crm_deals_min_value",
        )
    with col3:
        date_range_option = st.selectbox(
            "Close date range",
            options=["All time", "Next 30 days", "Next 90 days", "Past 30 days", "Past 90 days", "Custom"],
            key="crm_deals_date_range",
        )

    close_date_from: str | None = None
    close_date_to: str | None = None

    if date_range_option == "Custom":
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            from_date = st.date_input("From", key="crm_deals_from_date", value=None)
            if from_date:
                close_date_from = from_date.isoformat()
        with col_d2:
            to_date = st.date_input("To", key="crm_deals_to_date", value=None)
            if to_date:
                close_date_to = to_date.isoformat()
    else:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        if date_range_option == "Next 30 days":
            close_date_from = now.isoformat()
            close_date_to = (now + timedelta(days=30)).isoformat()
        elif date_range_option == "Next 90 days":
            close_date_from = now.isoformat()
            close_date_to = (now + timedelta(days=90)).isoformat()
        elif date_range_option == "Past 30 days":
            close_date_from = (now - timedelta(days=30)).isoformat()
            close_date_to = now.isoformat()
        elif date_range_option == "Past 90 days":
            close_date_from = (now - timedelta(days=90)).isoformat()
            close_date_to = now.isoformat()

    col_apply, _ = st.columns([1, 4])
    with col_apply:
        apply_clicked = st.button("Apply Filters", type="primary", key="crm_deals_apply", use_container_width=True)

    # Track filter state for cache-busting
    filter_key = f"{stage}|{min_value}|{close_date_from}|{close_date_to}"
    last_filter = st.session_state.get("crm_deals_last_filter", "")
    page = st.session_state.get("crm_deals_page", 1)
    page_size = 25

    if filter_key != last_filter or apply_clicked:
        st.session_state.crm_deals_last_filter = filter_key
        page = 1
        st.session_state.crm_deals_page = 1

    with st.spinner("Loading deals..."):
        offset = (page - 1) * page_size
        try:
            data = api.list_crm_deals(
                offset=offset,
                limit=page_size,
                stage=stage if stage else None,
                min_value=min_value if min_value > 0 else None,
                close_date_from=close_date_from,
                close_date_to=close_date_to,
            )
        except Exception as exc:
            st.error(f"❌ Failed to load deals: {exc}")
            return

    items = data.get("items", [])
    total = data.get("total", 0)

    st.caption(f"**{total}** deal(s) found · Page {page} of {max(1, (total + page_size - 1) // page_size)}")

    if not items:
        st.info("No deals found matching the current filters.")
        return

    # ── Build dataframe ─────────────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for d in items:
        value = d.get("value")
        value_str = f"${value:,.2f}" if value else "—"
        rows.append({
            "Name": d.get("name", ""),
            "Value": value_str,
            "Stage": (d.get("stage") or "").replace("_", " ").title(),
            "Close Date": _format_date(d.get("close_date")),
            "Created": _format_date(d.get("created_at")),
        })

    df = pd.DataFrame(rows)

    # Colour-code the Stage column with styled dataframe
    def _stage_color(val: str) -> str:
        colours = {
            "Closed Won": "background-color: #1b5e20; color: white",
            "Closed Lost": "background-color: #b71c1c; color: white",
            "Lead": "background-color: #1565c0; color: white",
            "Qualified": "background-color: #6a1b9a; color: white",
            "Proposal": "background-color: #e65100; color: white",
            "Negotiation": "background-color: #f9a825; color: black",
        }
        return colours.get(val, "")

    styled = df.style.applymap(_stage_color, subset=["Stage"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=400)

    # ── Pagination controls ──────────────────────────────────────────────
    total_pages = max(1, (total + page_size - 1) // page_size)
    if total_pages > 1:
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Previous", disabled=(page <= 1), key="crm_deals_prev"):
                st.session_state.crm_deals_page = page - 1
                st.rerun()
        with col_page:
            st.write(f"Page **{page}** of {total_pages}")
        with col_next:
            if st.button("Next →", disabled=(page >= total_pages), key="crm_deals_next"):
                st.session_state.crm_deals_page = page + 1
                st.rerun()


def _render_activities_tab() -> None:
    """Render the Activities tab with contact filter."""
    st.subheader("📝 Activities")

    # ── Contact filter (load contacts for dropdown) ─────────────────────
    contacts_cache = st.session_state.get("crm_contacts_cache")
    contacts_cache_time = st.session_state.get("crm_contacts_cache_time", 0)
    now = __import__("time").time()

    if contacts_cache is None or (now - contacts_cache_time) > 300:
        try:
            contacts_data = api.list_crm_contacts_all(limit=200)
            contacts_cache = contacts_data.get("items", [])
            st.session_state.crm_contacts_cache = contacts_cache
            st.session_state.crm_contacts_cache_time = now
        except Exception:
            contacts_cache = contacts_cache or []

    contact_options: list[tuple[str, str]] = [("", "All contacts")]
    contact_id_map: dict[str, str] = {}
    for c in contacts_cache or []:
        cid = str(c.get("id", ""))
        cname = c.get("name", "Unknown")
        contact_options.append((cid, cname))
        contact_id_map[cname] = cid

    col_f, col_btn = st.columns([3, 1])
    with col_f:
        selected_name = st.selectbox(
            "Filter by contact",
            options=[name for _, name in contact_options],
            key="crm_activities_contact",
        )
    contact_id: str | None = None
    if selected_name and selected_name != "All contacts":
        contact_id = contact_id_map.get(selected_name)

    with col_btn:
        st.write("")
        st.write("")
        apply_clicked = st.button("Apply", key="crm_activities_apply", use_container_width=True)

    last_contact = st.session_state.get("crm_activities_last_contact", "")
    page = st.session_state.get("crm_activities_page", 1)
    page_size = 25

    if (contact_id != last_contact) or apply_clicked:
        st.session_state.crm_activities_last_contact = contact_id
        page = 1
        st.session_state.crm_activities_page = 1

    with st.spinner("Loading activities..."):
        offset = (page - 1) * page_size
        try:
            data = api.list_crm_activities(
                offset=offset,
                limit=page_size,
                contact_id=contact_id,
            )
        except Exception as exc:
            st.error(f"❌ Failed to load activities: {exc}")
            return

    items = data.get("items", [])
    total = data.get("total", 0)

    st.caption(f"**{total}** activit(ies) found · Page {page} of {max(1, (total + page_size - 1) // page_size)}")

    if not items:
        st.info("No activities found. Run a CRM sync first.")
        return

    # ── Build dataframe ─────────────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for a in items:
        rows.append({
            "Type": (a.get("type") or "").title(),
            "Description": a.get("description", ""),
            "Date": _format_date(a.get("date")),
            "Contact ID": str(a.get("contact_id")) if a.get("contact_id") else "—",
        })

    df = pd.DataFrame(rows)

    # Colour-code activity types
    def _type_color(val: str) -> str:
        colours = {
            "Call": "background-color: #1565c0; color: white",
            "Email": "background-color: #2e7d32; color: white",
            "Meeting": "background-color: #6a1b9a; color: white",
            "Note": "background-color: #546e7a; color: white",
            "Task": "background-color: #e65100; color: white",
        }
        return colours.get(val, "")

    styled = df.style.applymap(_type_color, subset=["Type"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=400)

    # ── Pagination controls ──────────────────────────────────────────────
    total_pages = max(1, (total + page_size - 1) // page_size)
    if total_pages > 1:
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Previous", disabled=(page <= 1), key="crm_activities_prev"):
                st.session_state.crm_activities_page = page - 1
                st.rerun()
        with col_page:
            st.write(f"Page **{page}** of {total_pages}")
        with col_next:
            if st.button("Next →", disabled=(page >= total_pages), key="crm_activities_next"):
                st.session_state.crm_activities_page = page + 1
                st.rerun()


def render() -> None:
    """Render the CRM Data Browser page with tabbed entity views."""
    st.title("🔍 CRM Data Browser")

    st.markdown(
        "Browse and filter CRM entities synced from your connected CRM. "
        "Use the tabs below to switch between contacts, deals, and activities."
    )

    # ── Tabs ────────────────────────────────────────────────────────────
    tab_contacts, tab_deals, tab_activities = st.tabs([
        "👤 Contacts",
        "💰 Deals",
        "📝 Activities",
    ])

    with tab_contacts:
        _render_contacts_tab()

    with tab_deals:
        _render_deals_tab()

    with tab_activities:
        _render_activities_tab()
