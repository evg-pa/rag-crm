"""Shared fixtures for Streamlit AppTest frontend tests.

Uses st.testing.v1.AppTest to run the Streamlit app in a
headless subprocess for component-level testing.

No auth is needed — the app is fully open.
"""

from __future__ import annotations

from typing import Generator

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="function")
def app() -> Generator[AppTest, None, None]:
    """Load the Streamlit app with default (no auth) session state."""
    at = AppTest.from_file("app.py")
    at.run()
    yield at
