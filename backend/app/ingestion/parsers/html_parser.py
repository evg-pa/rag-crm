"""Parse HTML files into plain text using BeautifulSoup.

Strips tags, scripts, styles, and extracts visible text content
preserving paragraph/section structure. Also provides metadata
extraction (title, description, publish date).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HtmlMetadata:
    """Metadata extracted from an HTML document."""

    title: str | None = None
    description: str | None = None
    publish_date: str | None = None  # ISO 8601 or raw string
    encoding: str = "utf-8"
    extra: dict[str, str] = field(default_factory=dict)


class HtmlParser:
    """Extract plain text from HTML files and HTML strings."""

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".html", ".htm"})
    SUPPORTED_TYPES: frozenset[str] = frozenset({"text/html", "application/xhtml+xml"})

    # Tags whose text content we skip entirely
    _SKIP_TAGS: frozenset[str] = frozenset(
        {
            "script",
            "style",
            "noscript",
            "svg",
            "canvas",
            "nav",
            "footer",
            "header",
            "aside",
        }
    )

    # Block-level tags that get a newline before/after
    _BLOCK_TAGS: frozenset[str] = frozenset(
        {
            "p",
            "div",
            "section",
            "article",
            "main",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "br",
            "hr",
            "tr",
            "blockquote",
            "pre",
        }
    )

    @staticmethod
    def supports(filename: str) -> bool:
        """Check if this parser supports the given filename."""
        ext = Path(filename).suffix.lower()
        return ext in HtmlParser.SUPPORTED_EXTENSIONS

    @staticmethod
    async def parse(content: bytes, filename: str) -> str:
        """Extract text from HTML bytes.

        Args:
            content: Raw HTML bytes (typically UTF-8).
            filename: Original filename (used only for error messages).

        Returns:
            Plain text with HTML tags removed, preserving paragraph breaks.

        Raises:
            ValueError: If content is not valid HTML or has no text.
        """
        ext = Path(filename).suffix.lower()
        if ext not in HtmlParser.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension '{ext}'. "
                f"Supported: {', '.join(sorted(HtmlParser.SUPPORTED_EXTENSIONS))}"
            )

        if not content:
            raise ValueError("Empty HTML: nothing to extract.")

        return HtmlParser._parse_html_bytes(content)

    @classmethod
    def extract_metadata(cls, content: bytes) -> HtmlMetadata:
        """Extract metadata from HTML bytes without a full parse.

        Returns title, meta description, publish date, and detected encoding.
        Public so the scraper can obtain metadata independently.
        """
        from bs4 import BeautifulSoup

        encoding, html_str = cls._detect_encoding(content)
        soup = BeautifulSoup(html_str, "lxml")
        meta = HtmlMetadata(encoding=encoding)

        # Title
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            meta.title = title_tag.get_text(strip=True)

        # Meta description
        desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.IGNORECASE)})
        if desc_tag and desc_tag.get("content", "").strip():
            meta.description = desc_tag["content"].strip()

        # If no description meta, try og:description
        if not meta.description:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content", "").strip():
                meta.description = og_desc["content"].strip()

        # Publish date: check article:published_time, meta date, etc.
        for prop in ("article:published_time", "og:article:published_time"):
            date_tag = soup.find("meta", property=prop)
            if date_tag and date_tag.get("content", "").strip():
                meta.publish_date = date_tag["content"].strip()
                break

        if not meta.publish_date:
            date_re = re.compile(r"date|pubdate|publish", re.IGNORECASE)
            date_tag = soup.find("meta", attrs={"name": date_re})
            if date_tag and date_tag.get("content", "").strip():
                meta.publish_date = date_tag["content"].strip()

        return meta

    @classmethod
    def _detect_encoding(cls, content: bytes) -> tuple[str, str]:
        """Detect character encoding from meta charset tag or BOM.

        Returns (encoding_name, decoded_html_string).
        """
        # Try charset detection from meta tag first (scan first 4096 bytes)
        head_bytes = content[:4096]
        charset_pattern = re.compile(
            rb'<meta[^>]+charset=["\']?([a-zA-Z0-9_\-]+)',
            re.IGNORECASE,
        )
        match = charset_pattern.search(head_bytes)
        if match:
            declared = match.group(1).decode("ascii", errors="replace").lower()
            try:
                return declared, content.decode(declared)
            except (UnicodeDecodeError, LookupError):
                pass  # Declared encoding failed, fall through

        # Try UTF-8 with BOM
        if content[:3] == b"\xef\xbb\xbf":
            return "utf-8-sig", content.decode("utf-8-sig")

        # Try UTF-8
        try:
            return "utf-8", content.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # Try latin-1 (ISO-8859-1)
        try:
            return "latin-1", content.decode("latin-1")
        except UnicodeDecodeError:
            pass

        # Final fallback: replace errors
        return "utf-8", content.decode("utf-8", errors="replace")

    @classmethod
    def _parse_html_bytes(cls, content: bytes) -> str:
        """Parse HTML bytes into plain text.

        Package-private so the scraper can reuse the logic without
        duplicating the tag-stripping pipeline.
        """
        from bs4 import BeautifulSoup

        _encoding, html_str = cls._detect_encoding(content)

        soup = BeautifulSoup(html_str, "lxml")

        # Remove skipped tags entirely
        for tag_name in cls._SKIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Add newlines around block-level elements so the text splitter
        # gets natural paragraph breaks.
        texts: list[str] = []
        _extract_with_newlines(soup, texts, cls._BLOCK_TAGS)

        result = " ".join(texts)
        # Collapse multiple spaces
        import re

        result = re.sub(r"[ \t]+", " ", result)
        # Collapse multiple blank lines into double newline
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = result.strip()

        if not result:
            raise ValueError("HTML contains no extractable text content.")

        return result


def _extract_with_newlines(
    element,
    texts: list[str],
    block_tags: frozenset[str],
) -> None:
    """Walk the BeautifulSoup tree and extract text with newlines around block tags."""
    from bs4 import NavigableString, Tag

    if isinstance(element, NavigableString):
        text = element.strip()
        if text:
            texts.append(text)
        return

    if not isinstance(element, Tag):
        return

    tag_name = element.name.lower() if element.name else ""

    if tag_name in block_tags:
        texts.append("\n")

    for child in element.children:
        _extract_with_newlines(child, texts, block_tags)

    if tag_name in block_tags:
        texts.append("\n")
