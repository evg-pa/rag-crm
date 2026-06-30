"""Memory models: Working, Episodic, Semantic, and Procedural memory stores.

WorkingMemory  — per-session Q&A history (replaces in-memory store)
EpisodicMemory — cross-session conversation summaries with metadata
SemanticMemory — extracted facts with pgvector embeddings (384d, BGE-Small)
ProceduralMemory — reusable patterns and templates
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from app.models.document import Document  # noqa: F401

from app.core.database import Base

# BGE-Small embedding dimension
EMBEDDING_DIM: int = 384


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


# ── Working Memory ──────────────────────────────────────────────────────────


class WorkingMemory(Base):
    """Per-session Q&A history stored in PostgreSQL.

    Each row is a single message (user query or assistant response).
    Messages are ordered by ``created_at`` within a ``session_id``.
    Retained up to ``MAX_EXCHANGES * 2`` entries per session; older
    entries are pruned automatically.
    """

    __tablename__ = "working_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, default="default"
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,  # "user" | "assistant"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    def __repr__(self) -> str:
        return f"<WorkingMemory id={self.id!r} session={self.session_id!r} role={self.role!r}>"


# ── Episodic Memory ─────────────────────────────────────────────────────────


class EpisodicMemory(Base):
    """Cross-session conversation summaries with metadata.

    Created after each QA session completes. Contains the session's
    key topics, message count, and a short summary.
    """

    __tablename__ = "episodic_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return f"<EpisodicMemory session={self.session_id!r} topics={self.topics!r}>"


# ── Semantic Memory ─────────────────────────────────────────────────────────


class SemanticMemory(Base):
    """Extracted facts stored with pgvector embeddings for semantic retrieval.

    Each fact is a short, self-contained statement extracted from
    conversations or documents.  The embedding enables finding related
    facts by meaning, not just keywords.
    """

    __tablename__ = "semantic_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIM),
        nullable=True,  # type: ignore[arg-type]
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="conversation",
        # "conversation" | "document" | "manual"
    )
    source_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,  # document_id or session_id
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<SemanticMemory id={self.id!r} fact={self.fact[:60]!r} "
            f"confidence={self.confidence!r}>"
        )


# ── Procedural Memory ───────────────────────────────────────────────────────


class ProceduralMemory(Base):
    """Reusable patterns, templates, and workflows.

    Stores named procedures that can be applied across sessions.
    Content is typically structured markdown with steps, inputs, outputs.
    """

    __tablename__ = "procedural_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,  # markdown procedure
    )
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return f"<ProceduralMemory name={self.name!r} tags={self.tags!r}>"
