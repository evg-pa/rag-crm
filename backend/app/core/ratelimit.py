"""Redis-based rate limiting middleware (sliding window).

Uses Redis sorted sets to track request timestamps per IP + endpoint.
Supports per-route tiered limits and burst allowance.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from prometheus_client import Counter, Gauge
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from app.core.config import Settings

# ── Prometheus metrics for rate limiting ─────────────────────────────────────

ratelimit_hits_total = Counter(
    "ratelimit_hits_total",
    "Total rate limit rejections (429 responses)",
    labelnames=["endpoint"],
)

ratelimit_active_buckets = Gauge(
    "ratelimit_active_buckets",
    "Approximate number of active rate-limit buckets (IPs being tracked)",
)

# ── Default limits (requests per window) ─────────────────────────────────────

DEFAULT_LIMIT = 60  # requests
DEFAULT_WINDOW = 60  # seconds

# ── Per-route rate limit tiers (limit, window_seconds, burst_allowance) ──────
# Burst allowance: extra requests allowed in a short burst before throttling.
# Lower-tier routes (QA, document upload) get stricter limits than read-only
# routes (search, health).

ROUTE_TIERS: dict[str, tuple[int, int, int]] = {
    # (limit, window_sec, burst)
    # Heavy LLM endpoints — expensive, strict limit
    "/qa": (10, 60, 3),
    "/qa/stream": (10, 60, 3),
    "/qa/presets": (15, 60, 5),
    "/qa/crm/presets": (15, 60, 5),
    # Document upload — medium limit
    "/documents/upload": (20, 60, 5),
    # CRUD endpoints — moderate limit
    "/documents": (30, 60, 8),
    "/wiki": (30, 60, 8),
    "/memory": (30, 60, 8),
    "/crm": (30, 60, 8),
    "/connectors": (20, 60, 5),
    # Search — read-only, generous limit
    "/search": (60, 60, 15),
    # Pipeline status — lightweight, generous limit
    "/pipeline/status": (120, 60, 20),
}

# Prefix-based tier matching (longest-prefix wins)
ROUTE_PREFIX_TIERS: list[tuple[str, int, int, int]] = [
    ("/qa", 10, 60, 3),
    ("/documents", 30, 60, 8),
    ("/wiki", 30, 60, 8),
    ("/memory", 30, 60, 8),
    ("/crm", 30, 60, 8),
    ("/connectors", 20, 60, 5),
    ("/search", 60, 60, 15),
    ("/monitoring", 120, 60, 20),
]

# Endpoints excluded from rate limiting
SKIP_PATHS = {"/metrics", "/health", "/health/live", "/health/ready"}
SKIP_PREFIXES = ("/docs", "/openapi", "/redoc")


def _client_ip(request: Request) -> str:
    """Extract the client IP from the direct connection address.

    Only trusts X-Forwarded-For / X-Real-IP when the connecting client
    is a known proxy. Otherwise, falls back to ``request.client.host``
    to prevent IP spoofing via forged headers.
    """
    # Fall back to the raw client address (safe default)
    client = request.client
    return client.host if client else "unknown"


def _should_skip(path: str) -> bool:
    """Return True if the path should be excluded from rate limiting."""
    if path in SKIP_PATHS:
        return True
    return path.startswith(SKIP_PREFIXES)


def _get_tier(path: str) -> tuple[int, int, int]:
    """Return (limit, window_seconds, burst_allowance) for the given path.

    Exact matches take priority over prefix matches. Falls back to defaults.
    """
    if path in ROUTE_TIERS:
        return ROUTE_TIERS[path]
    for prefix, limit, window, burst in ROUTE_PREFIX_TIERS:
        if path.startswith(prefix):
            return limit, window, burst
    return DEFAULT_LIMIT, DEFAULT_WINDOW, 0


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
        self._default_limit = limit
        self._default_window = window
        self._pool: aioredis.ConnectionPool | None = None
        # Track active bucket count for metrics (approximate, updated periodically)
        self._active_bucket_count: int = 0
        self._last_bucket_count_update: float = 0.0

    async def _get_pool(self) -> aioredis.ConnectionPool:
        """Lazily create and return a shared connection pool.

        Uses ``REDIS_POOL_MAX_CONNECTIONS`` from settings to cap the
        number of concurrent connections to Redis.
        """
        if self._pool is None:
            self._pool = aioredis.ConnectionPool.from_url(
                self._settings.REDIS_URL,
                max_connections=self._settings.REDIS_POOL_MAX_CONNECTIONS,
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
        path = request.url.path
        now = time.time()

        # Determine per-route tier
        tier_limit, tier_window, burst = _get_tier(path)
        effective_limit = tier_limit + burst
        window_start = now - tier_window

        try:
            pool = await self._get_pool()
            redis_client = aioredis.Redis(connection_pool=pool)
            try:
                key = f"ratelimit:{ip}:{path}"

                # Remove old entries outside the window
                await redis_client.zremrangebyscore(key, 0, window_start)

                # Count requests in the current window
                count = await redis_client.zcard(key)

                if count >= effective_limit:
                    # Rate limit exceeded — compute Retry-After from the
                    # oldest timestamp still in the window (when it expires).
                    oldest_raw = await redis_client.zrange(key, 0, 0, withscores=True)
                    if oldest_raw:
                        oldest_ts = oldest_raw[0][1]
                        retry_after = max(1, int(oldest_ts + tier_window - now))
                    else:
                        retry_after = int(tier_window)

                    # Increment rate limit hit counter
                    ratelimit_hits_total.labels(endpoint=path).inc()

                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Rate limit exceeded. Try again later.",
                            "retry_after": retry_after,
                            "limit": tier_limit,
                            "burst": burst,
                        },
                        headers={"Retry-After": str(retry_after)},
                    )

                # Record this request
                await redis_client.zadd(key, {str(now): now})
                await redis_client.expire(key, tier_window * 2)

                # Update active bucket count gauge (throttled to every 10s)
                if now - self._last_bucket_count_update > 10:
                    # Approximate: count keys matching the ratelimit prefix
                    try:
                        cursor = 0
                        key_count = 0
                        while True:
                            cursor, keys = await redis_client.scan(
                                cursor, match="ratelimit:*", count=100
                            )
                            key_count += len(keys)
                            if cursor == 0:
                                break
                        self._active_bucket_count = key_count
                        self._last_bucket_count_update = now
                        ratelimit_active_buckets.set(key_count)
                    except Exception:
                        pass  # best-effort metric
            finally:
                await redis_client.aclose()

        except Exception:
            # If Redis is unreachable, allow the request through
            # (degraded mode — don't block traffic on Redis failure)
            pass

        return await call_next(request)
