"""Parse .md and .txt files into plain text."""

import re
from pathlib import Path


class TextParser:
    """Parse .md and .txt files into plain text."""

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt"})
    SUPPORTED_TYPES: frozenset[str] = frozenset({"text/markdown", "text/plain", "text/x-markdown"})

    # Regex patterns for stripping markdown syntax (applied in order).
    # Each tuple: (pattern, replacement).
    _MD_STRIP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        # Code blocks first (greedy, strip entire block)
        (re.compile(r"```[\s\S]*?```"), ""),
        # Inline code
        (re.compile(r"`{1,3}[^`]+`{1,3}"), ""),
        # Images: ![alt](url) → alt
        (re.compile(r"!\[([^\]]*)\]\([^)]+\)"), r"\1"),
        # Links: [text](url) → text
        (re.compile(r"\[([^\]]*)\]\([^)]+\)"), r"\1"),
        # Bold: **text**
        (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
        # Italic: *text*
        (re.compile(r"\*(.+?)\*"), r"\1"),
        # Strikethrough: ~~text~~
        (re.compile(r"~~(.+?)~~"), r"\1"),
        # Headings: # prefix
        (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),
        # Blockquotes: > prefix
        (re.compile(r"^>\s+", re.MULTILINE), ""),
        # Unordered list markers: - / * / +
        (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),
        # Ordered list markers: 1. 2. etc.
        (re.compile(r"^\s*\d+\.\s+", re.MULTILINE), ""),
        # Horizontal rules (3+ dashes/asterisks/underscores on their own line)
        (re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE), ""),
    ]

    @staticmethod
    def supports(filename: str) -> bool:
        """Check if this parser supports the given filename."""
        ext = Path(filename).suffix.lower()
        return ext in TextParser.SUPPORTED_EXTENSIONS

    @staticmethod
    async def parse(content: bytes, filename: str) -> str:
        """Parse file content into plain text.

        - .txt: decode as UTF-8
        - .md: decode as UTF-8, strip markdown formatting (basic: remove
          image/link syntax, headings markers, bold/italic, code blocks, etc.)

        Args:
            content: Raw file bytes.
            filename: Original filename (used to determine file type).

        Returns:
            Plain text with markdown formatting stripped.

        Raises:
            ValueError: If content is not valid UTF-8 or file type is unsupported.
        """
        ext = Path(filename).suffix.lower()
        if ext not in TextParser.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension '{ext}'. "
                f"Supported: {', '.join(sorted(TextParser.SUPPORTED_EXTENSIONS))}"
            )

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("File is not valid UTF-8 text.") from exc

        if not text:
            return ""

        if ext == ".md":
            text = TextParser._strip_markdown(text)

        return text.strip()

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Strip basic markdown formatting from text, preserving content."""
        for pattern, replacement in TextParser._MD_STRIP_PATTERNS:
            text = pattern.sub(replacement, text)
        # Collapse multiple blank lines into a single blank line
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
