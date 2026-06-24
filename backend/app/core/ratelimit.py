"""Redis-based rate limiting middleware (sliding window).

Uses Redis sorted sets to track request timestamps per IP + endpoint.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from app.core.config import Settings

# Default limits (requests per window)
DEFAULT_LIMIT = 60  # requests
DEFAULT_WINDOW = 60  # seconds

# Endpoints excluded from rate limiting
SKIP_PATHS = {"/metrics", "/health", "/health/live", "/health/ready"}
SKIP_PREFIXES = ("/docs", "/openapi", "/redoc")


def _client_ip(request: Request) -> str:
    """Extract the client IP from request headers or direct address."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # Fall back to the raw client address
    client = request.client
    return client.host if client else "unknown"


def _should_skip(path: str) -> bool:
    """Return True if the path should be excluded from rate limiting."""
    if path in SKIP_PATHS:
        return True
    return path.startswith(SKIP_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis.

    Tracks request timestamps in a Redis sorted set per IP + endpoint.
    Reuses a single connection pool for all requests.

    On Redis failure the middleware passes requests through (fail-open)
    so that a Redis outage does not take down the API.
    """

    def __init__(
        self,
        app: ASGIApp,
        settings: Settings,
        limit: int = DEFAULT_LIMIT,
        window: int = DEFAULT_WINDOW,
    ) -> None:
        super().__init__(app)
        self._settings = settings
        self._limit = limit
        self._window = window
        self._pool: aioredis.ConnectionPool | None = None

    async def _get_pool(self) -> aioredis.ConnectionPool:
        """Lazily create and return a shared connection pool."""
        if self._pool is None:
            self._pool = aioredis.ConnectionPool.from_url(
                self._settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=False,
            )
        return self._pool

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip non-rate-limited paths (health, docs, metrics)
        if _should_skip(request.url.path):
            return await call_next(request)

        ip = _client_ip(request)
        now = time.time()
        window_start = now - self._window

        try:
            pool = await self._get_pool()
            redis_client = aioredis.Redis(connection_pool=pool)

            key = f"ratelimit:{ip}:{request.url.path}"

            # Remove old entries outside the window
            await redis_client.zremrangebyscore(key, 0, window_start)

            # Count requests in the current window
            count = await redis_client.zcard(key)

            if count >= self._limit:
                # Rate limit exceeded — compute Retry-After from the
                # oldest timestamp still in the window (when it expires).
                oldest_raw = await redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_raw:
                    oldest_ts = oldest_raw[0][1]
                    retry_after = max(1, int(oldest_ts + self._window - now))
                else:
                    retry_after = int(self._window)

                await redis_client.aclose()
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Try again later.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            # Record this request
            await redis_client.zadd(key, {str(now): now})
            await redis_client.expire(key, self._window * 2)
            await redis_client.aclose()

        except Exception:
            # If Redis is unreachable, allow the request through
            # (degraded mode — don't block traffic on Redis failure)
            pass

        return await call_next(request)
