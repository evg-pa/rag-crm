"""Parser registry: dispatch to the correct parser by filename or content-type."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.ingestion.parsers.docx_parser import DocxParser
from app.ingestion.parsers.html_parser import HtmlParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.text_parser import TextParser

# Ordered list of parser classes checked in registration order.
# TextParser is last as it's the fallback (only .md/.txt).
_PARSER_REGISTRY: Sequence[type] = [
    PdfParser,
    DocxParser,
    HtmlParser,
    TextParser,
]


def get_parser_for(filename: str) -> type:
    """Return the parser class that supports the given filename.

    Args:
        filename: Original filename with extension (e.g. "report.pdf").

    Returns:
        Parser class (not instance) with `parse(content: bytes, filename: str) -> str`.

    Raises:
        ValueError: If no parser supports the file extension.
    """
    for parser_cls in _PARSER_REGISTRY:
        if parser_cls.supports(filename):  # type: ignore[union-attr]
            return parser_cls
    ext = Path(filename).suffix.lower()
    raise ValueError(
        f"No parser available for file extension '{ext}'. "
        f"Supported: {', '.join(_all_supported_extensions())}"
    )


def get_all_supported_extensions() -> frozenset[str]:
    """Return a frozenset of all supported file extensions across all parsers."""
    return _all_supported_extensions()


def _all_supported_extensions() -> frozenset[str]:
    exts: set[str] = set()
    for parser_cls in _PARSER_REGISTRY:
        exts.update(parser_cls.SUPPORTED_EXTENSIONS)  # type: ignore[union-attr]
    return frozenset(exts)


def get_ext_to_content_type_map() -> dict[str, str]:
    """Return a mapping of file extension → MIME content-type for all supported formats."""
    mapping: dict[str, str] = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".html": "text/html",
        ".htm": "text/html",
    }
    return mapping
