"""Document ingestion pipeline: parse, chunk, store."""

from app.ingestion.chunkers.recursive import ChunkResult, RecursiveChunker
from app.ingestion.parsers.text_parser import TextParser


async def ingest_document(content: bytes, filename: str) -> tuple[str, list[ChunkResult]]:
    """Parse content and chunk it. Returns (parsed_text, chunks).

    Raises ValueError if file type is unsupported.
    """
    parsed_text = await TextParser.parse(content, filename)
    chunker = RecursiveChunker()
    chunks = chunker.chunk(parsed_text)
    return parsed_text, chunks


__all__ = ["TextParser", "RecursiveChunker", "ChunkResult", "ingest_document"]
