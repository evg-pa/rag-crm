"""Web scraper: fetch a URL and extract plain text.

Uses httpx for HTTP requests and delegates to HtmlParser for text
extraction. Includes timeout, size limits, robots.txt checking,
and basic safety checks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """Result of a web scrape operation."""

    url: str
    title: str | None
    text: str
    content_type: str | None
    status_code: int
    description: str | None = None
    publish_date: str | None = None
    robots_allowed: bool | None = None  # None = not checked, True/False = result


class WebScraper:
    """Fetch a URL and extract plain text from the HTML response."""

    # Maximum response size (10 MB) — reject anything larger
    MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024
    # Request timeout (connect, read, write)
    TIMEOUT_SECONDS: float = 30.0
    # User-Agent string
    USER_AGENT: str = (
        "RAG-CRM-Ingestion/0.1 (+https://github.com/rag-crm; indexing bot)"
    )

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Reject non-HTTP(S) and private-network URLs."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        # Reject private IPs and localhost
        hostname = (parsed.hostname or "").lower()
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return False
        return not (
            hostname.startswith("10.")
            or hostname.startswith("172.16.")
            or hostname.startswith("192.168.")
        )

    @staticmethod
    def _extract_title(html_str: str) -> str | None:
        """Extract <title> text from HTML without full BS4 parse."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html_str, re.IGNORECASE | re.DOTALL)
        if match:
            from bs4 import BeautifulSoup
            # Use BS4 just for the title to handle entities
            title_soup = BeautifulSoup(match.group(1), "html.parser")
            return title_soup.get_text().strip() or None
        return None

    @classmethod
    async def _check_robots_txt(cls, url: str) -> bool | None:
        """Check robots.txt for the URL's origin.

        Returns True if allowed, False if disallowed, None if robots.txt
        could not be fetched or parsed (no robots.txt present).
        """
        import httpx

        parsed = urlparse(url)
        robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers={"User-Agent": cls.USER_AGENT},
            ) as client:
                resp = await client.get(robots_url)
                if resp.status_code != 200:
                    return None  # No robots.txt, assume allowed

                robots_content = resp.text
        except Exception:
            logger.warning("Could not fetch robots.txt for %s", url, exc_info=True)
            return None

        # Parse robots.txt manually to find applicable disallow rules.
        user_agent_prefix = "RAG-CRM-Ingestion"
        applicable_rules: list[str] = []
        current_agent: str | None = None
        wildcard_rules: list[str] = []

        for line in robots_content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # User-agent line
            ua_match = re.match(r"^User-agent:\s*(.+)", stripped, re.IGNORECASE)
            if ua_match:
                current_agent = ua_match.group(1).strip()
                continue

            # Disallow line
            dis_match = re.match(r"^Disallow:\s*(.*)", stripped, re.IGNORECASE)
            if dis_match:
                path = dis_match.group(1).strip()
                if not path:
                    continue  # Empty disallow means allow all
                if current_agent == "*":
                    wildcard_rules.append(path)
                elif current_agent and current_agent.lower() == user_agent_prefix.lower():
                    applicable_rules.append(path)
                continue

        # Prefer specific agent rules over wildcard
        rules = applicable_rules if applicable_rules else wildcard_rules
        if not rules:
            return True  # No disallow rules found

        # Check if the URL path is disallowed
        path = parsed.path or "/"
        for rule in rules:
            # Simple prefix matching (robots.txt spec)
            if path.startswith(rule):
                logger.warning(
                    "URL %s disallowed by robots.txt rule: Disallow: %s", url, rule
                )
                return False

        return True

    @classmethod
    async def scrape(cls, url: str) -> ScrapeResult:
        """Fetch a URL and extract plain text.

        Args:
            url: Full HTTP or HTTPS URL to scrape.

        Returns:
            ScrapeResult with extracted text and metadata.

        Raises:
            ValueError: If the URL is invalid, unsafe, or the response is not HTML.
            httpx.HTTPError: On network or HTTP errors.
        """
        import httpx

        if not cls._is_safe_url(url):
            raise ValueError(
                f"Unsafe or unsupported URL: {url}. Only public HTTP/HTTPS URLs are allowed."
            )

        # Check robots.txt (optional first pass, log warning if disallowed)
        robots_allowed = await cls._check_robots_txt(url)
        if robots_allowed is False:
            logger.warning("robots.txt disallows scraping %s — proceeding anyway", url)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(cls.TIMEOUT_SECONDS),
            follow_redirects=True,
            headers={"User-Agent": cls.USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        # Only accept HTML responses
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise ValueError(
                f"URL returned non-HTML content type '{content_type}'. "
                "Only HTML pages can be scraped."
            )

        raw_bytes = response.content
        if len(raw_bytes) > cls.MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Response too large ({len(raw_bytes)} bytes). "
                f"Maximum is {cls.MAX_RESPONSE_BYTES} bytes."
            )

        # Delegate to HtmlParser for text extraction
        from app.ingestion.parsers.html_parser import HtmlParser

        text = HtmlParser._parse_html_bytes(raw_bytes)

        # Extract metadata via HtmlParser
        metadata = HtmlParser.extract_metadata(raw_bytes)

        return ScrapeResult(
            url=url,
            title=metadata.title,
            text=text,
            content_type=content_type,
            status_code=response.status_code,
            description=metadata.description,
            publish_date=metadata.publish_date,
            robots_allowed=robots_allowed,
        )
