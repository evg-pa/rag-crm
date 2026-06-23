"""KPI card components for the dashboard."""

from __future__ import annotations

import streamlit as st


def kpi_card(label: str, value: str | int, icon: str = "") -> None:
    """Render a single KPI metric card.

    Args:
        label: The metric name (e.g. "Documents").
        value: The metric value (e.g. "42").
        icon: Optional emoji icon.
    """
    display = f"{icon} {value}" if icon else str(value)
    st.markdown(
        f"""
        <div class="rag-card rag-kpi">
            <div class="kpi-value">{display}</div>
            <div class="kpi-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: list[tuple[str, str | int, str]]) -> None:
    """Render a row of KPI cards in columns.

    Args:
        items: List of (label, value, icon) tuples.
    """
    if not items:
        return

    cols = st.columns(len(items))
    for col, (label, value, icon) in zip(cols, items, strict=True):
        with col:
            kpi_card(label, value, icon)
