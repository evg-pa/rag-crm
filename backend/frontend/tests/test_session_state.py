"""Tests for session state initialization.

Verifies all expected session state keys exist with correct
defaults after the Streamlit app loads.
"""

from __future__ import annotations


class TestInitSessionState:
    """init_session_state() should populate all expected keys."""

    def _get_app_state(self):
        """Helper: run AppTest and return session state proxy.

        Pre-populates health cache so the dashboard doesn't block on API calls.
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py")
        at.session_state["health_cache_time"] = 100  # far in the past — fresh call
        at.session_state["health_cache"] = {
            "status": "ok", "database": "connected",
        }
        at.session_state["health_status"] = {
            "status": "ok", "database": "connected",
        }
        at.run()
        return at.session_state

    def test_all_defaults_set(self) -> None:
        """All session state defaults exist after init."""
        ss = self._get_app_state()

        expected_keys: set[str] = {
            # Chat
            "messages",
            "history_loaded",
            "theme",
            # Data caches
            "documents_cache",
            "documents_cache_time",
            "wiki_cache",
            "wiki_cache_time",
            # Pipeline
            "pipeline_status",
            "pipeline_status_time",
            # Health
            "health_cache",
            "health_cache_time",
            "health_status",
            # Search
            "last_search_query",
            "search_results",
            "search_page",
            # Navigation
            "current_page",
            # Documents / Upload
            "scrape_url",
            "upload_success",
            "delete_confirm_id",
            # Q&A
            "qa_top_k",
            "qa_session_id",
            # Misc
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
        """health_cache_time is set to a valid timestamp (or stays at 0 before first check)."""
        val = self._get_app_state()["health_cache_time"]
        assert isinstance(val, (int, float)), (
            f"Expected health_cache_time to be int/float, got {type(val)}"
        )
        assert val >= 0, f"Expected non-negative timestamp, got {val}"

    def test_search_page_defaults_to_one(self) -> None:
        """Search page starts at 1."""
        assert self._get_app_state()["search_page"] == 1

    def test_top_k_defaults_to_five(self) -> None:
        """QA top-k defaults to 5."""
        assert self._get_app_state()["qa_top_k"] == 5

    def test_no_auth_keys_in_defaults(self) -> None:
        """Auth keys (auth_token, auth_user) are NOT in session state defaults."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py")
        at.session_state["health_cache_time"] = 100
        at.session_state["health_cache"] = {
            "status": "ok", "database": "connected",
        }
        at.session_state["health_status"] = {
            "status": "ok", "database": "connected",
        }
        at.run()
        assert "auth_token" not in at.session_state
        assert "auth_user" not in at.session_state
        assert "auth_page" not in at.session_state
