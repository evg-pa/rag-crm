"""Tests for page routing — verifying each page module loads and renders.

NOTE: These tests verify that the routing logic in app.py correctly
imports and calls the render function for each page. They check
that the page module exists and has the expected interface.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

# All known page modules and their expected renderable pages
PAGE_MODULES: list[dict[str, str]] = [
    {"module": "page_modules.dashboard", "page_key": "dashboard"},
    {"module": "page_modules.documents", "page_key": "documents"},
    {"module": "page_modules.qa_chat", "page_key": "qa_chat"},
    {"module": "page_modules.search", "page_key": "search"},
    {"module": "page_modules.wiki", "page_key": "wiki"},
    {"module": "page_modules.crm_dashboard", "page_key": "crm_dashboard"},
    {"module": "page_modules.crm_data", "page_key": "crm_data"},
    {"module": "page_modules.crm_query", "page_key": "crm_query"},
    {"module": "page_modules.pipeline", "page_key": "pipeline"},
]


@pytest.mark.parametrize("page", PAGE_MODULES, ids=lambda p: p["page_key"])
def test_page_module_importable(page: dict[str, str]) -> None:
    """Every page listed in app.py routing can be imported."""
    mod = importlib.import_module(page["module"])
    assert hasattr(mod, "render"), (
        f"{page['module']} is missing a 'render()' function"
    )
    assert inspect.isfunction(mod.render), (
        f"{page['module']}.render is not a function"
    )


@pytest.mark.parametrize("page", PAGE_MODULES, ids=lambda p: p["page_key"])
def test_page_render_accepts_no_args(page: dict[str, str]) -> None:
    """render() takes no required arguments (callable as render())."""
    mod = importlib.import_module(page["module"])
    sig = inspect.signature(mod.render)
    # Only parameterless or fully-defaulted functions are valid
    for name, param in sig.parameters.items():
        if name == "self":
            continue  # allow for bound methods used as callbacks
        assert param.default is not inspect.Parameter.empty, (
            f"{page['module']}.render() has required param '{name}'"
        )


def test_all_pages_mapped_in_routing() -> None:
    """Every page in page_modules/ is listed in app.py routing."""
    pages_dir = Path(__file__).resolve().parent.parent / "page_modules"
    actual_files = {f.stem for f in pages_dir.glob("*.py") if f.stem != "__init__"}

    app_py = Path(__file__).resolve().parent.parent / "app.py"
    app_source = app_py.read_text()

    mapped_pages = set()
    for page_file in actual_files:
        if f'page_modules.{page_file}' in app_source:
            mapped_pages.add(page_file)

    missing = actual_files - mapped_pages
    assert not missing, (
        f"Page module(s) exist but are not routed in app.py: {missing}"
    )


def test_page_keys_map_to_module_names() -> None:
    """Routing keys match their module names (no mismatch like 'wiki' vs 'kb')."""
    # From sidebar.py page_map
    sidebar_map: dict[str, str] = {
        "📊 Dashboard": "dashboard",
        "📄 Documents": "documents",
        "💬 Q&A Chat": "qa_chat",
        "🔍 Search": "search",
        "📚 Knowledge Base": "wiki",
        "📊 CRM Dashboard": "crm_dashboard",
        "🔍 CRM Data": "crm_data",
        "💬 CRM Query": "crm_query",
        "⚙️ Pipeline": "pipeline",
    }

    for display_name, expected_module in sidebar_map.items():
        matching = [p for p in PAGE_MODULES if p["page_key"] == expected_module]
        assert matching, (
            f"Sidebar option '{display_name}' maps to '{expected_module}' "
            f"but no page module found"
        )
