"""Abstract CRM adapter — defines the interface all adapters must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ContactData:
    """DTO for a CRM contact record from any adapter."""

    def __init__(
        self,
        *,
        external_id: str,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
    ) -> None:
        self.external_id = external_id
        self.name = name
        self.email = email
        self.phone = phone
        self.company = company


class DealData:
    """DTO for a CRM deal/opportunity record from any adapter."""

    def __init__(
        self,
        *,
        external_id: str,
        name: str,
        value: float | None = None,
        stage: str = "open",
        close_date: datetime | None = None,
        contact_external_id: str | None = None,
    ) -> None:
        self.external_id = external_id
        self.name = name
        self.value = value
        self.stage = stage
        self.close_date = close_date
        self.contact_external_id = contact_external_id


class ActivityData:
    """DTO for a CRM activity record from any adapter."""

    def __init__(
        self,
        *,
        external_id: str,
        type: str,
        description: str = "",
        date: datetime,
        contact_external_id: str | None = None,
    ) -> None:
        self.external_id = external_id
        self.type = type
        self.description = description
        self.date = date
        self.contact_external_id = contact_external_id


class BaseCRMAdapter(ABC):
    """Abstract CRM adapter.

    Every CRM connector (mock, REST, etc.) must implement these methods.
    """

    @abstractmethod
    async def sync(self) -> tuple[list[ContactData], list[DealData], list[ActivityData]]:
        """Fetch all records from the CRM and return them as DTOs."""
        ...

    @abstractmethod
    async def get_contacts(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> tuple[list[ContactData], int]:
        """Return a page of contacts and the total count."""
        ...

    @abstractmethod
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
        """Return a page of deals and the total count."""
        ...

    @abstractmethod
    async def get_activities(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        contact_external_id: str | None = None,
    ) -> tuple[list[ActivityData], int]:
        """Return a page of activities and the total count."""
        ...
