"""Tests for health check endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Return an async HTTP client for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    """GET /health returns status=ok, version, and database fields."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "database" in data


@pytest.mark.asyncio
async def test_health_live_endpoint(client: AsyncClient) -> None:
    """GET /health/live returns status=alive."""
    response = await client.get("/health/live")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "alive"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_ready_endpoint(client: AsyncClient) -> None:
    """GET /health/ready returns version field."""
    response = await client.get("/health/ready")
    assert response.status_code == 200

    data = response.json()
    assert "version" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_root_redirects_to_docs(client: AsyncClient) -> None:
    """GET / redirects to /docs."""
    response = await client.get("/", follow_redirects=False)
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/docs"
