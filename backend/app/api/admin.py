"""Admin endpoints — user management (admin-only)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.dependencies import get_db_session
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
