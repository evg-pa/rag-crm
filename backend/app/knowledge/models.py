"""WikiEntry model: auto-generated document summaries with extracted topics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.document import Document  # noqa: F401

from app.core.database import Base


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class WikiEntry(Base):
    """Auto-generated wiki entry for a document, produced by the KnowledgeAgent.

    Contains a 2-3 sentence summary and extracted keyword topics.
    Stored as JSONB (Postgres) or JSON text (SQLite — tests).
    """

    __tablename__ = "wiki_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one wiki entry per document
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # relationships
    document: Mapped[Document] = relationship("Document")

    def __repr__(self) -> str:
        return f"<WikiEntry id={self.id!r} document_id={self.document_id!r} topics={self.topics!r}>"
