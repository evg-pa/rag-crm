"""Recursive character text splitter — pure Python, no LLM calls.

Splits text recursively on a hierarchy of separators: section breaks,
newlines, sentences, words, and finally characters until each chunk fits
within chunk_size. Adjacent chunks overlap by chunk_overlap characters.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class ChunkResult:
    """A single text chunk with its position in the sequence."""

    index: int
    content: str


class RecursiveChunker:
    """Recursive character text splitter.

    Splits text recursively on section breaks (\\n\\n), then newlines,
    then sentences, then characters until each chunk fits within
    chunk_size with chunk_overlap.

    No LLM calls — pure deterministic splitting.
    """

    DEFAULT_SEPARATORS: Sequence[str] = ("\n\n", "\n", ". ", " ", "")

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[ChunkResult]:
        """Split text into ordered chunks.

        Args:
            text: The input plain text.

        Returns:
            Ordered list of ChunkResult.  Empty string produces empty list.
            Text shorter than chunk_size produces a single chunk.
        """
        if not text:
            return []

        splits = self._split(text, self.DEFAULT_SEPARATORS)
        merged = self._merge_with_overlap(splits)
        return [ChunkResult(index=i, content=chunk) for i, chunk in enumerate(merged)]

    def _split(self, text: str, separators: Sequence[str]) -> list[str]:
        """Recursively split text by the first separator that produces
        sub-strings <= chunk_size."""
        if not separators:
            # Character-level: every character is a unit.
            # Merge them into chunks later.
            return [text]

        sep = separators[0]
        remaining = separators[1:]

        pieces = list(text) if not sep else self._split_by_separator(text, sep)

        result: list[str] = []
        current: list[str] = []
        current_len = 0

        for piece in pieces:
            piece_len = len(piece)
            if piece_len > self.chunk_size:
                # Flush any accumulated pieces first
                if current:
                    result.append("".join(current))
                    current = []
                    current_len = 0
                # Recurse with next separator for this oversized piece
                result.extend(self._split(piece, remaining))
            elif current_len + piece_len > self.chunk_size:
                # Piece would overflow — flush current, start new
                result.append("".join(current))
                current = [piece]
                current_len = piece_len
            else:
                current.append(piece)
                current_len += piece_len

        if current:
            result.append("".join(current))

        return result

    @staticmethod
    def _split_by_separator(text: str, separator: str) -> list[str]:
        """Split text by separator, keeping the separator attached to the
        preceding fragment for more natural chunk boundaries."""
        if not separator:
            return list(text)

        parts: list[str] = []
        idx = 0
        sep_len = len(separator)

        while idx < len(text):
            pos = text.find(separator, idx)
            if pos == -1:
                parts.append(text[idx:])
                break
            # Include the separator with the preceding text
            parts.append(text[idx : pos + sep_len])
            idx = pos + sep_len

        return parts

    def _merge_with_overlap(self, splits: list[str]) -> list[str]:
        """Merge splits into final chunks with chunk_overlap between
        consecutive chunks."""
        if not splits:
            return []

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for split in splits:
            split_len = len(split)

            if current_len + split_len > self.chunk_size and current:
                # Finalize current chunk
                full_text = "".join(current)
                chunks.append(full_text)
                # Start overlap from the end of the previous chunk
                overlap_start = max(0, len(full_text) - self.chunk_overlap)
                current = [full_text[overlap_start:]]
                current_len = len(current[0])

            # Handle splits that are individually larger than chunk_size
            # (shouldn't happen after recursive split, but be safe)
            if split_len > self.chunk_size:
                # Flush current if any
                if current:
                    full_text = "".join(current)
                    chunks.append(full_text)
                    current = []
                    current_len = 0
                # Split the oversized piece at chunk_size boundaries
                for start in range(0, split_len, self.chunk_size - self.chunk_overlap):
                    end = min(start + self.chunk_size, split_len)
                    chunks.append(split[start:end])
                continue

            current.append(split)
            current_len += split_len

        if current:
            chunks.append("".join(current))

        # Remove empty chunks
        return [c for c in chunks if c.strip()]
