"""Memory service: CRUD and lifecycle operations for all four memory types.

WorkingMemory  — per-session Q&A history (PostgreSQL)
EpisodicMemory — cross-session conversation summaries
SemanticMemory — extracted facts with pgvector embeddings
ProceduralMemory — reusable patterns and templates
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.memory.models import (
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    WorkingMemory,
)
from app.retrieval.embeddings import get_embedding_model

logger = get_logger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

# Max working memory entries per session (5 exchanges = 10 entries)
MAX_WORKING_ENTRIES: int = 10
# Max days to retain episodic/semantic memory before archival
DEFAULT_TTL_DAYS: int = 90

# ── Working Memory ─────────────────────────────────────────────────────────


class WorkingMemoryService:
    """Per-session Q&A history management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        conversation_id: str = "default",
    ) -> WorkingMemory:
        """Append a message to a session's working memory."""
        entry = WorkingMemory(
            session_id=session_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        # Prune old entries after insert
        await self._prune(session_id, conversation_id)
        return entry

    async def get_history(
        self,
        session_id: str,
        conversation_id: str = "default",
        limit: int = MAX_WORKING_ENTRIES,
    ) -> list[dict[str, str]]:
        """Return the last *limit* messages for a session, oldest first."""
        stmt = (
            select(WorkingMemory)
            .where(
                WorkingMemory.session_id == session_id,
                WorkingMemory.conversation_id == conversation_id,
            )
            .order_by(WorkingMemory.created_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [{"role": r.role, "content": r.content, "id": str(r.id)} for r in rows]

    async def clear_session(self, session_id: str, conversation_id: str = "default") -> int:
        """Delete all working memory for a session/conversation."""
        stmt = delete(WorkingMemory).where(
            WorkingMemory.session_id == session_id,
            WorkingMemory.conversation_id == conversation_id,
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount  # type: ignore[return-value]

    async def clear_all(self) -> int:
        """Delete ALL working memory (destructive — test use only)."""
        stmt = delete(WorkingMemory)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount  # type: ignore[return-value]

    async def _prune(self, session_id: str, conversation_id: str) -> None:
        """Keep only the last MAX_WORKING_ENTRIES for the session."""
        # Count current entries
        count_stmt = (
            select(WorkingMemory)
            .where(
                WorkingMemory.session_id == session_id,
                WorkingMemory.conversation_id == conversation_id,
            )
            .order_by(WorkingMemory.created_at)
        )
        result = await self.db.execute(count_stmt)
        rows = result.scalars().all()

        if len(rows) > MAX_WORKING_ENTRIES:
            # Delete oldest entries beyond the limit
            ids_to_remove = [r.id for r in rows[:-MAX_WORKING_ENTRIES]]
            del_stmt = delete(WorkingMemory).where(
                WorkingMemory.id.in_(ids_to_remove)  # type: ignore[arg-type]
            )
            await self.db.execute(del_stmt)
            await self.db.commit()


# ── Episodic Memory ─────────────────────────────────────────────────────────


class EpisodicMemoryService:
    """Cross-session conversation summary management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_or_update(
        self,
        session_id: str,
        summary: str,
        topics: list[str],
        message_count: int,
    ) -> EpisodicMemory:
        """Create or update an episodic memory entry for a session."""
        stmt = select(EpisodicMemory).where(EpisodicMemory.session_id == session_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.summary = summary
            existing.topics = topics
            existing.message_count = message_count
            existing.ended_at = datetime.now(UTC)
            entry = existing
        else:
            entry = EpisodicMemory(
                session_id=session_id,
                summary=summary,
                topics=topics,
                message_count=message_count,
            )
            self.db.add(entry)

        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_by_session(self, session_id: str) -> EpisodicMemory | None:
        """Return the episodic memory for a session, if any."""
        stmt = select(EpisodicMemory).where(EpisodicMemory.session_id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 20, offset: int = 0) -> list[EpisodicMemory]:
        """Return the most recent episodic memories."""
        stmt = (
            select(EpisodicMemory)
            .order_by(EpisodicMemory.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_by_topics(self, topics: list[str], limit: int = 10) -> list[EpisodicMemory]:
        """Find episodic memories matching any of the given topics."""
        stmt = (
            select(EpisodicMemory)
            .where(EpisodicMemory.topics.has_any(topics))  # type: ignore[arg-type]
            .order_by(EpisodicMemory.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def prune_old(self, days: int = DEFAULT_TTL_DAYS) -> int:
        """Delete episodic memories older than *days*."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = delete(EpisodicMemory).where(EpisodicMemory.updated_at < cutoff)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount  # type: ignore[return-value]


# ── Semantic Memory ─────────────────────────────────────────────────────────


class SemanticMemoryService:
    """Extracted fact management with vector search."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_fact(
        self,
        fact: str,
        source: str = "conversation",
        source_id: str | None = None,
        confidence: float = 1.0,
    ) -> SemanticMemory:
        """Store a new fact with its embedding."""
        embedding = await self._compute_embedding(fact)
        entry = SemanticMemory(
            fact=fact,
            embedding=embedding,
            source=source,
            source_id=source_id,
            confidence=confidence,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def search_similar(
        self, query: str, limit: int = 10, min_confidence: float = 0.5
    ) -> list[dict[str, Any]]:
        """Find facts semantically similar to *query*."""
        embedding = await self._compute_embedding(query)
        if embedding is None:
            return []

        # Cosine distance via pgvector <=> operator
        # Use ORM-level query to let SQLAlchemy handle vector type casting
        from sqlalchemy import select as sa_select

        stmt = (
            sa_select(
                SemanticMemory.id,
                SemanticMemory.fact,
                SemanticMemory.source,
                SemanticMemory.source_id,
                SemanticMemory.confidence,
                (1 - SemanticMemory.embedding.cosine_distance(embedding)).label("similarity"),
            )
            .where(
                SemanticMemory.confidence >= min_confidence,
                SemanticMemory.embedding.isnot(None),
            )
            .order_by(SemanticMemory.embedding.cosine_distance(embedding))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        rows = result.fetchall()
        return [
            {
                "id": str(r[0]),
                "fact": r[1],
                "source": r[2],
                "source_id": r[3],
                "confidence": float(r[4]),
                "similarity": float(r[5]),
            }
            for r in rows
        ]

    async def list_facts(self, limit: int = 50, offset: int = 0) -> list[SemanticMemory]:
        """Return recent facts."""
        stmt = (
            select(SemanticMemory)
            .order_by(SemanticMemory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact by ID. Returns True if found and deleted."""
        stmt = select(SemanticMemory).where(SemanticMemory.id == fact_id)
        result = await self.db.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await self.db.delete(entry)
        await self.db.commit()
        return True

    async def prune_low_confidence(self, threshold: float = 0.3) -> int:
        """Delete facts below a confidence threshold."""
        stmt = delete(SemanticMemory).where(SemanticMemory.confidence < threshold)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount  # type: ignore[return-value]

    async def _compute_embedding(self, text: str) -> list[float] | None:
        """Compute an embedding vector for the given text."""
        try:
            model = get_embedding_model()
            return await model.embed(text)
        except Exception:
            logger.warning("Failed to compute embedding for semantic fact", exc_info=True)
            return None


# ── Procedural Memory ──────────────────────────────────────────────────────


class ProceduralMemoryService:
    """Reusable pattern/template management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        name: str,
        content: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> ProceduralMemory:
        """Create a new procedure."""
        entry = ProceduralMemory(
            name=name,
            description=description,
            content=content,
            tags=tags or [],
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_by_name(self, name: str) -> ProceduralMemory | None:
        """Look up a procedure by name."""
        stmt = select(ProceduralMemory).where(ProceduralMemory.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def search_by_tags(self, tags: list[str], limit: int = 10) -> list[ProceduralMemory]:
        """Find procedures matching any tag."""
        stmt = (
            select(ProceduralMemory)
            .where(ProceduralMemory.tags.has_any(tags))  # type: ignore[arg-type]
            .order_by(ProceduralMemory.usage_count.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def increment_usage(self, name: str) -> None:
        """Increment the usage counter for a procedure."""
        stmt = select(ProceduralMemory).where(ProceduralMemory.name == name)
        result = await self.db.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry:
            entry.usage_count = (entry.usage_count or 0) + 1
            await self.db.commit()

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[ProceduralMemory]:
        """List all procedures, most used first."""
        stmt = (
            select(ProceduralMemory)
            .order_by(ProceduralMemory.usage_count.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
