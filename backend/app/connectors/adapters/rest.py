"""Generic REST adapter for real CRM APIs.

Configured via environment variables:
  CRM_REST_BASE_URL  — base URL of the CRM REST API
  CRM_REST_API_KEY   — API key / bearer token
  CRM_REST_TIMEOUT   — request timeout in seconds (default 30)
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx

from app.connectors.adapters.base import (
    ActivityData,
    BaseCRMAdapter,
    ContactData,
    DealData,
)


class RestCRMAdapter(BaseCRMAdapter):
    """REST adapter that calls a real CRM API via httpx.

    Expects the remote API to implement the same interface as the
    connector's GET endpoints (contacts, deals, activities) and a
    sync endpoint.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or os.getenv("CRM_REST_BASE_URL", "")).rstrip("/")
        self._api_key = api_key or os.getenv("CRM_REST_API_KEY", "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Adapter interface ────────────────────────────────────────────────

    async def sync(self) -> tuple[list[ContactData], list[DealData], list[ActivityData]]:
        client = await self._get_client()
        resp = await client.post("/sync")
        resp.raise_for_status()
        data = resp.json()

        contacts = [
            ContactData(
                external_id=c["external_id"],
                name=c["name"],
                email=c.get("email"),
                phone=c.get("phone"),
                company=c.get("company"),
            )
            for c in data.get("contacts", [])
        ]
        deals = [
            DealData(
                external_id=d["external_id"],
                name=d["name"],
                value=d.get("value"),
                stage=d.get("stage", "open"),
                close_date=datetime.fromisoformat(d["close_date"]) if d.get("close_date") else None,
                contact_external_id=d.get("contact_external_id"),
            )
            for d in data.get("deals", [])
        ]
        activities = [
            ActivityData(
                external_id=a["external_id"],
                type=a["type"],
                description=a.get("description", ""),
                date=datetime.fromisoformat(a["date"]),
                contact_external_id=a.get("contact_external_id"),
            )
            for a in data.get("activities", [])
        ]
        return contacts, deals, activities

    async def get_contacts(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> tuple[list[ContactData], int]:
        client = await self._get_client()
        params: dict[str, object] = {"offset": offset, "limit": limit}
        if search:
            params["q"] = search
        resp = await client.get("/contacts", params=params)
        resp.raise_for_status()
        data = resp.json()
        contacts = [
            ContactData(
                external_id=c["external_id"],
                name=c["name"],
                email=c.get("email"),
                phone=c.get("phone"),
                company=c.get("company"),
            )
            for c in data.get("items", [])
        ]
        return contacts, data.get("total", len(contacts))

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
        client = await self._get_client()
        params: dict[str, object] = {"offset": offset, "limit": limit}
        if stage:
            params["stage"] = stage
        if min_value is not None:
            params["min_value"] = min_value
        if close_date_from:
            params["close_date_from"] = close_date_from.isoformat()
        if close_date_to:
            params["close_date_to"] = close_date_to.isoformat()
        resp = await client.get("/deals", params=params)
        resp.raise_for_status()
        data = resp.json()
        deals = [
            DealData(
                external_id=d["external_id"],
                name=d["name"],
                value=d.get("value"),
                stage=d.get("stage", "open"),
                close_date=datetime.fromisoformat(d["close_date"]) if d.get("close_date") else None,
                contact_external_id=d.get("contact_external_id"),
            )
            for d in data.get("items", [])
        ]
        return deals, data.get("total", len(deals))

    async def get_activities(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        contact_external_id: str | None = None,
    ) -> tuple[list[ActivityData], int]:
        client = await self._get_client()
        params: dict[str, object] = {"offset": offset, "limit": limit}
        if contact_external_id:
            params["contact_external_id"] = contact_external_id
        resp = await client.get("/activities", params=params)
        resp.raise_for_status()
        data = resp.json()
        activities = [
            ActivityData(
                external_id=a["external_id"],
                type=a["type"],
                description=a.get("description", ""),
                date=datetime.fromisoformat(a["date"]),
                contact_external_id=a.get("contact_external_id"),
            )
            for a in data.get("items", [])
        ]
        return activities, data.get("total", len(activities))
