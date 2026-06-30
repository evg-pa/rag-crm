"""Document ingestion pipeline: parse, chunk, store.

Supports: PDF, DOCX, HTML, Markdown, plain text, and web scraping.
"""

from typing import Any

from app.ingestion.chunkers.recursive import ChunkResult, RecursiveChunker
from app.ingestion.parsers.registry import (
    get_all_supported_extensions,
    get_parser_for,
)


async def ingest_document(
    content: bytes,
    filename: str,
) -> tuple[str, dict[str, Any], list[ChunkResult]]:
    """Parse content and chunk it. Returns (parsed_text, metadata, chunks).

    metadata is always a dict; it may be empty if the parser doesn't
    extract metadata (e.g. plain text files, markdown).

    Dispatches to the correct parser based on file extension.
    Supports: .pdf, .docx, .html, .htm, .md, .txt

    Raises ValueError if file type is unsupported.
    """
    parser_cls = get_parser_for(filename)
    result = await parser_cls.parse(content, filename)  # type: ignore[union-attr]

    # PdfParser returns (text, metadata) tuple; all other parsers return str
    if isinstance(result, tuple):
        parsed_text, metadata = result
    else:
        parsed_text = result
        metadata = {}

    chunker = RecursiveChunker()
    chunks = chunker.chunk(parsed_text)
    return parsed_text, metadata, chunks


__all__ = [
    "RecursiveChunker",
    "ChunkResult",
    "ingest_document",
    "get_parser_for",
    "get_all_supported_extensions",
]
