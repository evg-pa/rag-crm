"""Document model: uploaded files with metadata."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.chunk import Chunk  # noqa: F401
    from app.models.user import User  # noqa: F401

from app.core.database import Base


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class Document(Base):
    """Uploaded document with metadata."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, default=None
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. "text/markdown", "text/plain", "application/pdf"
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, index=True
    )  # sha256 hex digest of parsed text; used for duplicate detection
    doc_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "doc_metadata", JSON, nullable=True, default=None
    )  # e.g. {title, author, page_count} from PDF parsing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # relationships
    owner: Mapped[User | None] = relationship(
        "User", back_populates="documents", foreign_keys=[user_id]
    )
    chunks: Mapped[list[Chunk]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id!r} filename={self.filename!r} "
            f"content_type={self.content_type!r}>"
        )
