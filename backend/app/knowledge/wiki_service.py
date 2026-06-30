"""WikiService — CRUD operations for wiki entries.

Orchestrates KnowledgeAgent generation and database persistence.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.knowledge.knowledge_agent import KnowledgeAgent
from app.knowledge.models import WikiEntry
from app.models.document import Document

logger = get_logger(__name__)


class WikiService:
    """Service for creating, reading, updating, and searching wiki entries.

    Parameters
    ----------
    db:
        An async SQLAlchemy session.
    agent:
        A KnowledgeAgent instance.  Created internally if not provided.
    """

    def __init__(
        self,
        db: AsyncSession,
        agent: KnowledgeAgent | None = None,
    ) -> None:
        self._db = db
        self._agent = agent

    @property
    def agent(self) -> KnowledgeAgent:
        """Return (and lazily create) the KnowledgeAgent."""
        if self._agent is None:
            self._agent = KnowledgeAgent()
        return self._agent

    async def create_or_update_wiki(self, document_id: uuid.UUID) -> WikiEntry | None:
        """Generate and persist a wiki entry for a document.

        If a wiki entry already exists for this document, it is updated
        (regenerated).  If the document does not exist, returns None.

        Parameters
        ----------
        document_id:
            The document UUID.

        Returns
        -------
        WikiEntry | None
            The created or updated wiki entry, or None if the document
            was not found or has no chunk content.
        """
        # Fetch document with chunks (we need the full text)
        result = await self._db.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.chunks))
        )
        document = result.scalar_one_or_none()
        if document is None:
            logger.warning("Wiki generation skipped: document %s not found", document_id)
            return None

        # Reconstruct full text from chunks in order
        full_text = "\n\n".join(chunk.content for chunk in document.chunks)
        if not full_text.strip():
            logger.warning("Wiki generation skipped: document %s has no content", document_id)
            return None

        # Generate summary + topics
        try:
            result_data = await asyncio.wait_for(
                self.agent.generate_summary(full_text), timeout=45.0
            )
        except TimeoutError:
            logger.warning("Wiki generation timed out for document %s", document_id)
            result_data = {
                "summary": "Summary generation timed out.",
                "topics": [],
            }

        summary = result_data.get("summary", "")
        topics = result_data.get("topics", [])

        # Upsert: update existing or create new
        existing_result = await self._db.execute(
            select(WikiEntry).where(WikiEntry.document_id == document_id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.summary = summary
            existing.topics = topics
            # updated_at is set by server_default/onupdate
            entry = existing
            logger.info("Wiki entry updated for document %s", document_id)
        else:
            entry = WikiEntry(
                document_id=document_id,
                summary=summary,
                topics=topics,
            )
            self._db.add(entry)
            logger.info("Wiki entry created for document %s", document_id)

        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def list_entries(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WikiEntry], int]:
        """List wiki entries with pagination.

        Returns
        -------
        tuple[list[WikiEntry], int]
            (entries, total_count)
        """
        # Count total
        count_result = await self._db.execute(select(WikiEntry))
        total = len(count_result.scalars().all())

        # Fetch page
        offset = (page - 1) * page_size
        result = await self._db.execute(
            select(WikiEntry).order_by(WikiEntry.updated_at.desc()).offset(offset).limit(page_size)
        )
        entries = result.scalars().all()
        return list(entries), total

    async def get_entry(self, document_id: uuid.UUID) -> WikiEntry | None:
        """Get a wiki entry by document ID."""
        result = await self._db.execute(
            select(WikiEntry).where(WikiEntry.document_id == document_id)
        )
        return result.scalar_one_or_none()

    async def refresh_entry(self, document_id: uuid.UUID) -> WikiEntry | None:
        """Regenerate the summary for an existing wiki entry."""
        # Check the document and entry both exist
        doc_result = await self._db.execute(select(Document).where(Document.id == document_id))
        if doc_result.scalar_one_or_none() is None:
            return None

        return await self.create_or_update_wiki(document_id)

    async def search_entries(self, query: str) -> list[WikiEntry]:
        """Search wiki entries by keyword across summary and topics.

        Searches the ``summary`` column with ILIKE and the ``topics``
        JSONB array for the query substring.

        Parameters
        ----------
        query:
            Search keyword(s).

        Returns
        -------
        list[WikiEntry]
            Matching wiki entries, ordered by updated_at desc.
        """
        if not query or not query.strip():
            return []

        pattern = f"%{query.strip()}%"

        # Use JSONB containment operator for Postgres; for SQLite (tests)
        # we fall back to summary-only search since SQLite doesn't have JSONB operators.
        result = await self._db.execute(
            select(WikiEntry)
            .where(WikiEntry.summary.ilike(pattern))
            .order_by(WikiEntry.updated_at.desc())
            .limit(50)
        )
        entries = result.scalars().all()

        # Also match by topics substring (client-side filter for SQLite compat)
        # For entries not yet matched, check if the query appears in any topic
        seen_ids = {e.id for e in entries}
        all_result = await self._db.execute(
            select(WikiEntry).order_by(WikiEntry.updated_at.desc()).limit(100)
        )
        for entry in all_result.scalars().all():
            if entry.id not in seen_ids:
                if any(query.strip().lower() in topic.lower() for topic in entry.topics):
                    entries.append(entry)

        return entries

    async def backfill_all(self) -> int:
        """Generate wiki entries for all documents that don't have one yet.

        Returns
        -------
        int
            Number of wiki entries generated.
        """
        # Find all documents
        doc_result = await self._db.execute(select(Document))
        documents = doc_result.scalars().all()

        # Find which already have wiki entries
        wiki_result = await self._db.execute(select(WikiEntry.document_id))
        existing_doc_ids = {row[0] for row in wiki_result.fetchall()}

        count = 0
        for doc in documents:
            if doc.id not in existing_doc_ids:
                try:
                    entry = await self.create_or_update_wiki(doc.id)
                    if entry:
                        count += 1
                except Exception as exc:
                    logger.warning("Backfill failed for document %s: %s", doc.id, exc)

        return count

    async def close(self) -> None:
        """Close the internal KnowledgeAgent's HTTP client."""
        if self._agent is not None:
            await self._agent.close()
