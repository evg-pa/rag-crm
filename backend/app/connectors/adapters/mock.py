"""Mock CRM adapter — generates fake CRM data in-memory (no external API)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

from app.connectors.adapters.base import (
    ActivityData,
    BaseCRMAdapter,
    ContactData,
    DealData,
)

# Deterministic seed for reproducible test data
random.seed(42)

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona",
    "George", "Hannah", "Ivan", "Julia", "Kevin", "Laura",
]
LAST_NAMES = [
    "Anderson", "Brown", "Clark", "Davis", "Evans", "Foster",
    "Garcia", "Harris", "Ito", "Johnson", "Kim", "Lee",
]
COMPANIES = [
    "Acme Corp", "Globex Inc", "Initech", "Umbrella Co",
    "Stark Industries", "Wayne Enterprises", "Wonka Industries",
    "Cyberdyne Systems", "Massive Dynamic", "Soylent Corp",
]
STAGES = [
    "lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost",
]
ACTIVITY_TYPES = ["call", "email", "meeting", "note"]


def _rand_date(days_back: int = 365) -> datetime:
    """Return a random datetime within the last *days_back* days."""
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now(UTC) - delta


class MockCRMAdapter(BaseCRMAdapter):
    """Generates fake CRM contacts, deals, and activities in-memory.

    Data is regenerated on every call — suitable for development and
    testing without an external CRM dependency.
    """

    def __init__(self, *, seed: int | None = 42) -> None:
        self._seed = seed
        if seed is not None:
            random.seed(seed)

    # ── Internal generators ──────────────────────────────────────────────

    @staticmethod
    def _gen_contacts(count: int = 20) -> list[ContactData]:
        return [
            ContactData(
                external_id=f"mock-contact-{i}",
                name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                email=f"contact-{i}@example.com",
                phone=f"+1-555-{random.randint(1000, 9999)}",
                company=random.choice(COMPANIES),
            )
            for i in range(count)
        ]

    @staticmethod
    def _gen_deals(
        contacts: list[ContactData], *, count: int = 30,
    ) -> list[DealData]:
        deals: list[DealData] = []
        for i in range(count):
            contact = random.choice(contacts)
            stage = random.choice(STAGES)
            close_date = _rand_date(180) if stage in ("closed_won", "closed_lost") else None
            deals.append(
                DealData(
                    external_id=f"mock-deal-{i}",
                    name=f"Deal #{i:04d} — {contact.company or 'Unknown'}",
                    value=round(random.uniform(500, 500_000), 2),
                    stage=stage,
                    close_date=close_date,
                    contact_external_id=contact.external_id,
                )
            )
        return deals

    @staticmethod
    def _gen_activities(
        contacts: list[ContactData], *, count: int = 50,
    ) -> list[ActivityData]:
        return [
            ActivityData(
                external_id=f"mock-activity-{i}",
                type=random.choice(ACTIVITY_TYPES),
                description=f"Mock activity #{i} — {random.choice(ACTIVITY_TYPES)} with {random.choice(contacts).name}",
                date=_rand_date(90),
                contact_external_id=random.choice(contacts).external_id,
            )
            for i in range(count)
        ]

    # ── Adapter interface ────────────────────────────────────────────────

    async def sync(self) -> tuple[list[ContactData], list[DealData], list[ActivityData]]:
        contacts = self._gen_contacts()
        deals = self._gen_deals(contacts)
        activities = self._gen_activities(contacts)
        return contacts, deals, activities

    async def get_contacts(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> tuple[list[ContactData], int]:
        contacts = self._gen_contacts(50)
        if search:
            q = search.lower()
            contacts = [
                c for c in contacts
                if q in c.name.lower()
                or (c.email and q in c.email.lower())
                or (c.company and q in c.company.lower())
            ]
        total = len(contacts)
        return contacts[offset : offset + limit], total

    async def get_deals(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        stage: str | None = None,
        min_value: float | None = None,
        close_date_from: datetime | None = None,
        close_date_to: datetime | None = None,
    ) -> tuple[list[DealData], int]:
        contacts = self._gen_contacts(10)
        deals = self._gen_deals(contacts, count=50)
        if stage:
            deals = [d for d in deals if d.stage == stage]
        if min_value is not None:
            deals = [d for d in deals if d.value is not None and d.value >= min_value]
        if close_date_from:
            deals = [d for d in deals if d.close_date and d.close_date >= close_date_from]
        if close_date_to:
            deals = [d for d in deals if d.close_date and d.close_date <= close_date_to]
        total = len(deals)
        return deals[offset : offset + limit], total

    async def get_activities(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        contact_external_id: str | None = None,
    ) -> tuple[list[ActivityData], int]:
        contacts = self._gen_contacts(10)
        activities = self._gen_activities(contacts, count=50)
        if contact_external_id:
            activities = [
                a for a in activities
                if a.contact_external_id == contact_external_id
            ]
        total = len(activities)
        return activities[offset : offset + limit], total
