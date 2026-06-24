"""E2E tests for Pipeline page — agent flow diagram.

NOTE: The ``page`` fixture already logs in.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


class TestPipelinePage:
    """Pipeline page renders the LangGraph agent diagram."""

    def test_pipeline_page_loads(self, page: Page) -> None:
        """Navigating to Pipeline page loads without errors."""
        page.wait_for_load_state("networkidle")

        pipeline_radio = page.locator("label:has-text('⚙️ Pipeline')")
        pipeline_radio.click()
        page.wait_for_timeout(1500)

        body = page.locator("body")
        expect(body).to_contain_text("Pipeline")

    def test_pipeline_has_auto_refresh(self, page: Page) -> None:
        """Pipeline page has the auto-refresh toggle."""
        # Navigate to pipeline via sidebar
        pipeline_radio = page.locator("label:has-text('⚙️ Pipeline')")
        pipeline_radio.click()
        page.wait_for_timeout(1500)

        checkboxes = page.locator("input[type='checkbox']")
        expect(checkboxes.first).to_be_hidden()
        toggle_area = page.locator("text=Auto-refresh")
        expect(toggle_area).to_be_visible()

    def test_pipeline_shows_agent_status(self, page: Page) -> None:
        """Pipeline page shows agent status indicators."""
        pipeline_radio = page.locator("label:has-text('⚙️ Pipeline')")
        pipeline_radio.click()
        page.wait_for_timeout(1500)

        body = page.locator("body")
        agent_indicators = [
            "Router", "Retriever", "Reranker",
            "Answer", "Critic", "Memory", "Synthesizer",
        ]
        text = body.text_content() or ""
        found = [a for a in agent_indicators if a in text]
        assert len(found) >= 3, (
            f"Expected at least 3 agent references on Pipeline page, "
            f"found {len(found)}: {found}"
        )
