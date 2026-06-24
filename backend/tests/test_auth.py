"""Tests for JWT authentication — register, login, refresh, me, and admin endpoints.

Covers:
  1. Register a new user — 201 + tokens
  2. Login with valid credentials — 200 + tokens
  3. Login with invalid password — 401
  4. Login with non-existent email — 401
  5. Token refresh — 200 + new tokens
  6. Refresh with access token — 401 (wrong token type)
  7. Get current user (me) — 200 + user profile
  8. Register duplicate email — 409
  9. Register weak password — 422
 10. Admin list users — 200 (admin-only)
 11. Admin get user — 200 (admin-only)
 12. Admin update user — 200 (admin-only)
 13. Admin delete user — 200 (admin-only)
 14. Admin self-deletion guard — 422
 15. Admin self-demotion guard — 422
 16. Non-admin access to admin endpoints — 403
"""

import pytest
from httpx import AsyncClient

from tests.conftest import get_auth_headers


# ── Registration ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_new_user(unauth_client: AsyncClient) -> None:
    """POST /auth/register with valid data returns 201 + access + refresh tokens."""
    response = await unauth_client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "securepass123",
            "display_name": "New User",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_default_display_name(unauth_client: AsyncClient) -> None:
    """POST /auth/register without display_name uses the email prefix."""
    response = await unauth_client.post(
        "/auth/register",
        json={"email": "jane@example.com", "password": "securepass123"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert "access_token" in data

    # Verify the display name via /me
    headers = get_auth_headers(data["access_token"])
    me_resp = await unauth_client.get("/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["display_name"] == "jane"


@pytest.mark.asyncio
async def test_register_duplicate_email(unauth_client: AsyncClient) -> None:
    """POST /auth/register with an already-registered email returns 409."""
    await unauth_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "securepass123"},
    )
    response = await unauth_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "anotherpass123"},
    )
    assert response.status_code == 409, response.text
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_weak_password(unauth_client: AsyncClient) -> None:
    """POST /auth/register with a password < 8 characters returns 422."""
    response = await unauth_client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_register_invalid_email(unauth_client: AsyncClient) -> None:
    """POST /auth/register with an invalid email returns 422."""
    response = await unauth_client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "securepass123"},
    )
    assert response.status_code == 422, response.text


# ── Login ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_valid(unauth_client: AsyncClient) -> None:
    """POST /auth/login with valid credentials returns 200 + tokens."""
    # Register first
    await unauth_client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "securepass123"},
    )

    response = await unauth_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "securepass123"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(unauth_client: AsyncClient) -> None:
    """POST /auth/login with wrong password returns 401."""
    await unauth_client.post(
        "/auth/register",
        json={"email": "badpw@example.com", "password": "securepass123"},
    )

    response = await unauth_client.post(
        "/auth/login",
        json={"email": "badpw@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_login_nonexistent_email(unauth_client: AsyncClient) -> None:
    """POST /auth/login with an email that doesn't exist returns 401."""
    response = await unauth_client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "securepass123"},
    )
    assert response.status_code == 401, response.text


# ── Token Refresh ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_refresh(unauth_client: AsyncClient) -> None:
    """POST /auth/refresh with a valid refresh token returns new tokens."""
    register_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "refresh@example.com", "password": "securepass123"},
    )
    refresh_token = register_resp.json()["refresh_token"]

    response = await unauth_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Verify tokens are usable (the /me endpoint works with new access token)
    me_resp = await unauth_client.get("/auth/me", headers=get_auth_headers(data["access_token"]))
    assert me_resp.status_code == 200


@pytest.mark.asyncio
async def test_token_refresh_with_access_token(unauth_client: AsyncClient) -> None:
    """POST /auth/refresh with an access token (instead of refresh) returns 401."""
    register_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "access@example.com", "password": "securepass123"},
    )
    access_token = register_resp.json()["access_token"]

    response = await unauth_client.post(
        "/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401, response.text


# ── Get Current User ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_me(unauth_client: AsyncClient) -> None:
    """GET /auth/me returns the current user's profile."""
    register_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "me@example.com", "password": "securepass123"},
    )
    token = register_resp.json()["access_token"]
    headers = get_auth_headers(token)

    response = await unauth_client.get("/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == "me@example.com"
    assert "id" in data
    assert data["is_admin"] is False


@pytest.mark.asyncio
async def test_get_me_without_token(unauth_client: AsyncClient) -> None:
    """GET /auth/me without a token returns 401."""
    response = await unauth_client.get("/auth/me")
    assert response.status_code == 401, response.text


# ── Admin Endpoints ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_users(
    unauth_client: AsyncClient, admin_user
) -> None:
    """GET /admin/users as admin returns user list."""
    register_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "someuser@example.com", "password": "securepass123"},
    )
    # Login as admin
    admin_tokens = register_resp  # won't work, admin was created by fixture
    # We need to register + login admin from fixture, or login the fixture user

    # Actually, the admin_user fixture creates a user with a known password
    login_resp = await unauth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
    admin_token = login_resp.json()["access_token"]
    headers = get_auth_headers(admin_token)

    response = await unauth_client.get("/admin/users", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "users" in data
    assert "total" in data
    assert data["total"] >= 1  # at least admin user
    emails = [u["email"] for u in data["users"]]
    assert "admin@example.com" in emails


@pytest.mark.asyncio
async def test_admin_get_user(
    unauth_client: AsyncClient, admin_user
) -> None:
    """GET /admin/users/{id} as admin returns a single user."""
    # Register a user to look up
    reg_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "target@example.com", "password": "securepass123"},
    )
    # Login as that user to get their id via /me
    user_token = reg_resp.json()["access_token"]
    me_resp = await unauth_client.get("/auth/me", headers=get_auth_headers(user_token))
    target_id = me_resp.json()["id"]

    # Login as admin
    login_resp = await unauth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = get_auth_headers(admin_token)

    response = await unauth_client.get(f"/admin/users/{target_id}", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == "target@example.com"
    assert data["id"] == target_id


@pytest.mark.asyncio
async def test_admin_update_user(
    unauth_client: AsyncClient, admin_user
) -> None:
    """PATCH /admin/users/{id} as admin updates a user's fields."""
    # Register a regular user
    reg_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "update-target@example.com", "password": "securepass123"},
    )
    user_token = reg_resp.json()["access_token"]
    me_resp = await unauth_client.get("/auth/me", headers=get_auth_headers(user_token))
    target_id = me_resp.json()["id"]

    # Login as admin
    login_resp = await unauth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = get_auth_headers(admin_token)

    # Deactivate the user
    response = await unauth_client.patch(
        f"/admin/users/{target_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["is_active"] is False

    # Verify: the deactivated user cannot login
    login_fail = await unauth_client.post(
        "/auth/login",
        json={"email": "update-target@example.com", "password": "securepass123"},
    )
    assert login_fail.status_code == 403, login_fail.text


@pytest.mark.asyncio
async def test_admin_delete_user(
    unauth_client: AsyncClient, admin_user
) -> None:
    """DELETE /admin/users/{id} as admin removes a user."""
    reg_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "delete-me@example.com", "password": "securepass123"},
    )
    user_token = reg_resp.json()["access_token"]
    me_resp = await unauth_client.get("/auth/me", headers=get_auth_headers(user_token))
    target_id = me_resp.json()["id"]

    # Login as admin
    login_resp = await unauth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = get_auth_headers(admin_token)

    response = await unauth_client.delete(
        f"/admin/users/{target_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"

    # Verify user no longer exists (login fails)
    login_fail = await unauth_client.post(
        "/auth/login",
        json={"email": "delete-me@example.com", "password": "securepass123"},
    )
    assert login_fail.status_code == 401


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(
    unauth_client: AsyncClient, admin_user
) -> None:
    """DELETE /admin/users/{self_id} as admin returns 422."""
    login_resp = await unauth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = get_auth_headers(admin_token)

    me_resp = await unauth_client.get("/auth/me", headers=headers)
    admin_id = me_resp.json()["id"]

    response = await unauth_client.delete(
        f"/admin/users/{admin_id}", headers=headers
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_admin_cannot_demote_self(
    unauth_client: AsyncClient, admin_user
) -> None:
    """PATCH /admin/users/{self_id} with is_admin=false returns 422."""
    login_resp = await unauth_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = get_auth_headers(admin_token)

    me_resp = await unauth_client.get("/auth/me", headers=headers)
    admin_id = me_resp.json()["id"]

    response = await unauth_client.patch(
        f"/admin/users/{admin_id}",
        json={"is_admin": False},
        headers=headers,
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin_endpoints(
    unauth_client: AsyncClient
) -> None:
    """Non-admin users get 403 on /admin/* endpoints."""
    reg_resp = await unauth_client.post(
        "/auth/register",
        json={"email": "regular@example.com", "password": "securepass123"},
    )
    token = reg_resp.json()["access_token"]
    headers = get_auth_headers(token)

    response = await unauth_client.get("/admin/users", headers=headers)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_admin_access_without_auth(unauth_client: AsyncClient) -> None:
    """GET /admin/users without auth returns 401."""
    response = await unauth_client.get("/admin/users")
    assert response.status_code == 401, response.text
