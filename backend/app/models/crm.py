"""CRM ORM models: Contact, Deal, Activity.

Separate tables (not Document/Chunk) — independent of the RAG pipeline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class CrmContact(Base):
    """CRM Contact — person or organisation from an external CRM."""

    __tablename__ = "crm_contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    external_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow,
    )

    def __repr__(self) -> str:
        return f"<CrmContact id={self.id!r} name={self.name!r}>"


class CrmDeal(Base):
    """CRM Deal / Opportunity — associated with a contact."""

    __tablename__ = "crm_deals"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    external_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    stage: Mapped[str] = mapped_column(String(100), nullable=False, default="open")
    close_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow,
    )

    def __repr__(self) -> str:
        return f"<CrmDeal id={self.id!r} name={self.name!r} stage={self.stage!r}>"


class CrmSyncRun(Base):
    """CRM Sync Run — tracks each sync execution for the status widget."""

    __tablename__ = "crm_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )  # pending | running | success | error
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    contacts_synced: Mapped[int] = mapped_column(default=0)
    deals_synced: Mapped[int] = mapped_column(default=0)
    activities_synced: Mapped[int] = mapped_column(default=0)
    rag_documents_created: Mapped[int] = mapped_column(default=0)
    rag_chunks_created: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    def __repr__(self) -> str:
        return f"<CrmSyncRun id={self.id!r} status={self.status!r}>"


class CrmActivity(Base):
    """CRM Activity — call, email, meeting, note associated with a contact."""

    __tablename__ = "crm_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    external_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow,
    )

    def __repr__(self) -> str:
        return f"<CrmActivity id={self.id!r} type={self.type!r}>"
