"""Admin endpoints — LLM config (unauthenticated, local dev) and user management.

The LLM config endpoint lets any user change the active LLM provider/model/key
at runtime via the frontend sidebar. Authentication is intentionally omitted
since this runs in a local dev/self-hosted context.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.dependencies import get_db_session
from app.core.runtime_config import get_llm_config, set_llm_config
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class AdminUserOut(BaseModel):
    """User in admin list responses."""

    id: str
    email: str
    display_name: str
    is_active: bool
    is_admin: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_user(cls, user: User) -> AdminUserOut:
        return cls(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )


class UserUpdateRequest(BaseModel):
    """Fields allowed to update on a user (admin-only)."""

    is_active: bool | None = None
    is_admin: bool | None = None
    display_name: str | None = None


class AdminUserListResponse(BaseModel):
    """Paginated user list."""

    users: list[AdminUserOut]
    total: int


# ── LLM Config schemas ───────────────────────────────────────────────────


class LLMConfigRequest(BaseModel):
    """Request body for updating LLM config."""

    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


class LLMConfigResponse(BaseModel):
    """Current LLM config."""

    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_configured: bool


class LLMTestRequest(BaseModel):
    """Request body for testing an LLM connection."""

    api_key: str = ""
    base_url: str = ""
    model: str = ""


# ── LLM Config endpoints ────────────────────────────────────────────────


@router.get("/llm-config", response_model=LLMConfigResponse)
async def get_llm_config_endpoint() -> LLMConfigResponse:
    """Get the current runtime LLM configuration."""
    cfg = get_llm_config()
    from app.core.dependencies import get_settings

    settings = get_settings()
    key = cfg.get("LLM_API_KEY") or settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""
    url = cfg.get("LLM_BASE_URL") or settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL or ""
    model = cfg.get("LLM_MODEL") or settings.LLM_MODEL or "deepseek-chat"
    return LLMConfigResponse(
        llm_api_key=key[:8] + "..." if len(key) > 10 else ("set" if key else ""),
        llm_base_url=url,
        llm_model=model,
        llm_configured=bool(key),
    )


@router.put("/llm-config", response_model=LLMConfigResponse)
async def update_llm_config(body: LLMConfigRequest) -> LLMConfigResponse:
    """Update the runtime LLM configuration (in-memory, immediate).

    Set fields to empty string to clear the override and fall back to env.
    """
    set_llm_config(
        LLM_API_KEY=body.llm_api_key,
        LLM_BASE_URL=body.llm_base_url,
        LLM_MODEL=body.llm_model,
    )
    return await get_llm_config_endpoint()


@router.post("/llm-config/test")
async def test_llm_connection(body: LLMTestRequest) -> dict[str, object]:
    """Test an LLM connection by making a simple chat request."""
    url = f"{body.base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if body.api_key:
        headers["Authorization"] = f"Bearer {body.api_key}"
    payload = {
        "model": body.model or "deepseek-chat",
        "messages": [{"role": "user", "content": "Reply with just the word OK"}],
        "max_tokens": 10,
    }
    try:
        async with AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return {"status": "ok", "message": "Connection successful"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Admin guard ──────────────────────────────────────────────────────────────


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency: ensure the current user is an admin.

    Raises 403 if the user is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_admin_user),
) -> AdminUserListResponse:
    """List all registered users (admin-only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar_one()

    return AdminUserListResponse(
        users=[AdminUserOut.from_user(u) for u in users],
        total=total,
    )


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_admin_user),
) -> AdminUserOut:
    """Get a single user by ID (admin-only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return AdminUserOut.from_user(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_admin_user),
) -> AdminUserOut:
    """Update a user's active status, admin flag, or display name (admin-only).

    Admins cannot update their own admin flag (self-demotion guard).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Guard: an admin cannot demote themselves
    if user.id == admin.id and body.is_admin is False:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot remove your own admin privileges",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return AdminUserOut.from_user(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    admin: User = Depends(get_admin_user),
) -> dict[str, str]:
    """Delete a user and all their documents (admin-only).

    Admins cannot delete themselves.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Guard: an admin cannot delete themselves
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot delete your own account",
        )

    await db.delete(user)
    await db.commit()

    return {"status": "deleted", "user_id": str(user_id)}
