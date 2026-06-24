"""Tests for session state initialization.

Verifies all expected session state keys exist with correct
defaults after the Streamlit app loads.
"""

from __future__ import annotations


class TestInitSessionState:
    """init_session_state() should populate all expected keys."""

    def _get_app_state(self):
        """Helper: run AppTest and return session state proxy."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py")
        at.run()
        return at.session_state

    def test_all_defaults_set(self) -> None:
        """All session state defaults exist after init."""
        ss = self._get_app_state()

        expected_keys: set[str] = {
            "messages",
            "history_loaded",
            "theme",
            "documents_cache",
            "documents_cache_time",
            "wiki_cache",
            "wiki_cache_time",
            "pipeline_status",
            "pipeline_status_time",
            "health_cache",
            "health_cache_time",
            "health_status",
            "last_search_query",
            "search_results",
            "search_page",
            "current_page",
            "scrape_url",
            "upload_success",
            "delete_confirm_id",
            "qa_top_k",
            "qa_session_id",
            "app_version",
        }
        for key in expected_keys:
            assert key in ss, f"Missing session state key: {key}"

    def test_theme_defaults_to_dark(self) -> None:
        """Theme defaults to 'dark'."""
        assert self._get_app_state()["theme"] == "dark"

    def test_current_page_defaults_to_dashboard(self) -> None:
        """Default page is dashboard."""
        assert self._get_app_state()["current_page"] == "dashboard"

    def test_messages_empty_on_init(self) -> None:
        """Chat messages start empty."""
        assert self._get_app_state()["messages"] == []

    def test_health_cache_is_timestamp(self) -> None:
        """health_cache_time is set to a valid timestamp after app init."""
        val = self._get_app_state()["health_cache_time"]
        assert isinstance(val, (int, float)), (
            f"Expected health_cache_time to be int/float, got {type(val)}"
        )
        assert val > 0, f"Expected positive timestamp, got {val}"

    def test_search_page_defaults_to_one(self) -> None:
        """Search page starts at 1."""
        assert self._get_app_state()["search_page"] == 1

    def test_top_k_defaults_to_ten(self) -> None:
        """QA top-k defaults to 5."""
        assert self._get_app_state()["qa_top_k"] == 5
