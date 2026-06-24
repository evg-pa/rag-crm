"""E2E tests for Pipeline page — agent flow diagram."""

from __future__ import annotations

from playwright.sync_api import Page, expect


class TestPipelinePage:
    """Pipeline page renders the LangGraph agent diagram."""

    def test_pipeline_page_loads(self, page: Page, base_url: str) -> None:
        """Navigating to Pipeline page loads without errors."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Click the Pipeline nav option
        pipeline_radio = page.locator("label:has-text('⚙️ Pipeline')")
        pipeline_radio.click()
        page.wait_for_timeout(1500)

        # Verify Pipeline page content loaded
        body = page.locator("body")
        expect(body).to_contain_text("Pipeline")

    def test_pipeline_has_auto_refresh(self, page: Page, base_url: str) -> None:
        """Pipeline page has the auto-refresh toggle."""
        page.goto(f"{base_url}/pipeline")
        page.wait_for_load_state("networkidle")

        # The checkbox input itself is visually hidden (Streamlit renders
        # it as hidden + styled label). Check it exists in the DOM.
        checkboxes = page.locator("input[type='checkbox']")
        expect(checkboxes.first).to_be_hidden()
        # Also check the visible toggle element exists
        toggle_area = page.locator("text=Auto-refresh")
        expect(toggle_area).to_be_visible()

    def test_pipeline_shows_agent_status(self, page: Page, base_url: str) -> None:
        """Pipeline page shows agent status indicators."""
        page.goto(f"{base_url}/pipeline")
        page.wait_for_load_state("networkidle")

        # The page should reference at least some agents by name
        body = page.locator("body")
        agent_indicators = ["Router", "Retriever", "Reranker", "Answer", "Critic", "Memory", "Synthesizer"]
        text = body.text_content() or ""
        found = [a for a in agent_indicators if a in text]
        assert len(found) >= 3, (
            f"Expected at least 3 agent references on Pipeline page, "
            f"found {len(found)}: {found}"
        )
