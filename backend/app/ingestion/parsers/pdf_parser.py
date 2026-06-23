"""Parse .pdf files into plain text with metadata extraction.

Uses pypdf to extract:
  - Full plain text from all pages
  - Document metadata: title, author, subject, keywords, creator,
    producer, creation date, modification date, and page count.
"""

import io
from pathlib import Path
from typing import Any

from pypdf import PdfReader


class PdfParser:
    """Parse .pdf files into plain text and extract document metadata."""

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf"})
    SUPPORTED_TYPES: frozenset[str] = frozenset({"application/pdf"})

    # ── Public API ───────────────────────────────────────────────────────

    @staticmethod
    def supports(filename: str) -> bool:
        """Check if this parser supports the given filename."""
        ext = Path(filename).suffix.lower()
        return ext in PdfParser.SUPPORTED_EXTENSIONS

    @staticmethod
    async def parse(content: bytes, filename: str) -> tuple[str, dict[str, Any]]:
        """Parse a PDF file, returning (plain_text, metadata_dict).

        Args:
            content: Raw PDF file bytes.
            filename: Original filename (used for extension validation).

        Returns:
            Tuple of (plain_text, metadata_dict).  metadata_dict is never
            None but may be empty if no metadata tags are present in the PDF.

        Raises:
            ValueError: If the file is not a valid PDF or cannot be parsed.
        """
        ext = Path(filename).suffix.lower()
        if ext not in PdfParser.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension '{ext}'. "
                f"Supported: {', '.join(sorted(PdfParser.SUPPORTED_EXTENSIONS))}"
            )

        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as exc:
            raise ValueError(f"Failed to read PDF: {exc}") from exc

        # Extract text from all pages
        pages_text: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text.strip())

        full_text = "\n\n".join(pages_text)

        # Extract metadata
        metadata = PdfParser._extract_metadata(reader)

        return full_text, metadata

    # ── Metadata helpers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_metadata(reader: PdfReader) -> dict[str, Any]:
        """Extract document metadata from a pypdf PdfReader.

        Returns a dict with keys that are present (never None values):
          - title (str)
          - author (str)
          - subject (str)
          - keywords (str)
          - creator (str)
          - producer (str)
          - creation_date (str, ISO 8601) — or absent if unparseable
          - modification_date (str, ISO 8601) — or absent if unparseable
          - page_count (int)
        """
        meta = reader.metadata or {}

        result: dict[str, Any] = {}

        # String metadata fields
        str_fields = {
            "title": "/Title",
            "author": "/Author",
            "subject": "/Subject",
            "keywords": "/Keywords",
            "creator": "/Creator",
            "producer": "/Producer",
        }

        for key, pdf_key in str_fields.items():
            value = PdfParser._get_meta_str(meta, pdf_key)
            if value is not None:
                result[key] = value

        # Date fields — convert to ISO 8601 strings
        for key, pdf_key in [
            ("creation_date", "/CreationDate"),
            ("modification_date", "/ModDate"),
        ]:
            date_str = PdfParser._get_meta_date(meta, pdf_key)
            if date_str is not None:
                result[key] = date_str

        # Page count
        result["page_count"] = len(reader.pages)

        return result

    @staticmethod
    def _get_meta_str(meta: dict[Any, Any], key: str) -> str | None:
        """Extract a string metadata value, stripping whitespace.

        Returns None if the key is absent, empty, or not a string.
        """
        raw = meta.get(key)
        if raw is None:
            return None
        if not isinstance(raw, str):
            raw = str(raw)
        stripped = raw.strip()
        return stripped if stripped else None

    @staticmethod
    def _get_meta_date(meta: dict[Any, Any], key: str) -> str | None:
        """Extract a date metadata value.

        pypdf may return dates as strings (e.g. "D:20230101120000+00'00'")
        or as datetime-like objects.  Returns an ISO 8601 string or None.

        We strip the "D:" prefix and try to parse common PDF date formats.
        """
        raw = meta.get(key)
        if raw is None:
            return None
        if not isinstance(raw, str):
            raw = str(raw)

        raw = raw.strip()
        if not raw:
            return None

        # Try parsing via pypdf's internal date parser (if available), or
        # fall back to returning the raw string for now.
        try:
            # If raw starts with "D:", strip it and try isoformat
            if raw.startswith("D:"):
                raw = raw[2:]
                # Attempt to parse common PDF date: YYYYMMDDHHmmSS
                # Format: 20230101120000+00'00'
                # Convert to ISO 8601: 2023-01-01T12:00:00+00:00
                date_part = raw[:14]  # YYYYMMDDHHmmSS
                if len(date_part) == 14 and date_part.isdigit():
                    iso = (
                        f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                        f"T{date_part[8:10]}:{date_part[10:12]}:{date_part[12:14]}"
                    )
                    # Append timezone if present
                    tz_part = raw[14:].strip()
                    if tz_part:
                        # Convert +00'00' → +00:00
                        tz_clean = tz_part.replace("'", ":")
                        iso += tz_clean
                    return iso
                return raw
            return raw
        except Exception:
            return raw
