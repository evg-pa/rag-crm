"""Text chunkers: split text into overlapping or disjoint segments."""

from app.ingestion.chunkers.recursive import ChunkResult, RecursiveChunker

__all__ = ["ChunkResult", "RecursiveChunker"]
