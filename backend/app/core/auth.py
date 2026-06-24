"""Authentication utilities — JWT, password hashing, and FastAPI dependency."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_db_session, get_settings
from app.models.user import User

# ── Constants ────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# ── Password hashing ─────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT tokens ───────────────────────────────────────────────────────────────


def _get_secret(settings: Settings) -> str:
    """Return the JWT secret key, with a fallback for dev."""
    secret = settings.JWT_SECRET_KEY
    if not secret:
        # Dev-only fallback — never use in production
        secret = "dev-secret-change-me-in-production"
    return secret


def create_access_token(
    user_id: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for the given user."""
    if settings is None:
        settings = Settings()
    secret = _get_secret(settings)
    to_encode: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.now(UTC)
        + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)),
    }
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: str,
    settings: Settings | None = None,
) -> str:
    """Create a JWT refresh token."""
    if settings is None:
        settings = Settings()
    secret = _get_secret(settings)
    to_encode: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def decode_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises on expiry/invalid signature."""
    if settings is None:
        settings = Settings()
    secret = _get_secret(settings)
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependency ───────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """FastAPI dependency: return the authenticated user from the Bearer token.

    Raises 401 if the token is missing, invalid, or the user doesn't exist.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    token_type = payload.get("type")
    if not user_id or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> User | None:
    """FastAPI dependency: return the authenticated user or ``None``.

    Unlike ``get_current_user``, this does NOT raise on missing tokens,
    making it suitable for endpoints that support both authenticated
    and anonymous access.
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)  # type: ignore[arg-type]
    except HTTPException:
        return None
