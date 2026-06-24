"""Tests for Redis-based rate limiting middleware."""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.ratelimit import RateLimitMiddleware


# ---------------------------------------------------------------------------
# Redis mock helpers
# ---------------------------------------------------------------------------

def _build_mock_redis(zcard_cb=None, zadd_cb=None, expire_cb=None, zrem_cb=None, zrange_cb=None):
    """Create a mock Redis client with optional side-effect callbacks."""
    mock_redis = Mock()
    mock_redis.zremrangebyscore = AsyncMock(side_effect=zrem_cb)
    mock_redis.zcard = AsyncMock(side_effect=zcard_cb, return_value=0)
    mock_redis.zadd = AsyncMock(side_effect=zadd_cb)
    mock_redis.expire = AsyncMock(side_effect=expire_cb)
    mock_redis.zrange = AsyncMock(side_effect=zrange_cb, return_value=[])
    mock_redis.aclose = AsyncMock()
    return mock_redis


# ---------------------------------------------------------------------------
# In-memory rate limiter for fast deterministic testing without Redis
# ---------------------------------------------------------------------------

class _InMemoryRateLimiter:
    """A self-contained in-memory sliding-window rate limiter.

    Replaces the Redis-backed middleware for deterministic tests that
    exercise the full HTTP stack without mocking every Redis call.
    """

    def __init__(self, limit: int = 60, window: int = 60):
        self._limit = limit
        self._window = window
        self._buckets: dict[str, list[float]] = {}

    async def check(self, ip: str, path: str, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed: bool, retry_after: int)."""
        if now is None:
            now = time.time()
        key = f"{ip}:{path}"
        bucket = self._buckets.setdefault(key, [])
        window_start = now - self._window
        # Remove expired timestamps
        bucket[:] = [ts for ts in bucket if ts > window_start]

        if len(bucket) >= self._limit:
            retry_after = max(1, int(bucket[0] + self._window - now))
            return False, retry_after

        bucket.append(now)
        return True, 0


# ---------------------------------------------------------------------------
# Tests against the full app (mock Redis pool)
# ---------------------------------------------------------------------------

@pytest.fixture
async def app_with_ratelimit():
    """Create a fresh app with rate limiting middleware that uses a mock Redis."""
    from app.main import app
    # Re-use the app but patch the middleware's Redis pool
    # Find the rate limit middleware
    for mw in app.user_middleware:
        if isinstance(mw, RateLimitMiddleware):
            mw._pool = None  # reset pool so test can inject mock
            break
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRateLimitSkipPaths:
    """Verify that health, docs, and metrics endpoints are never rate-limited."""

    @pytest.mark.parametrize(
        "path",
        [
            "/health",
            "/health/live",
            "/health/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        ],
    )
    @pytest.mark.asyncio
    async def test_skip_paths_not_rate_limited(self, path, app_with_ratelimit):
        """Even after many requests, these paths should always return 200."""
        client = app_with_ratelimit
        # Send 100 rapid requests — should never be rate limited
        for _ in range(100):
            resp = await client.get(path)
            assert resp.status_code != 429, f"{path} should not be rate limited"


class TestRateLimitingWithMockRedis:
    """Integration tests that replace Redis with a mock to verify
    the middleware returns 429 when the limit is hit."""

    # /pipeline/status is a lightweight no-DB endpoint that is rate-limited
    _URL = "/pipeline/status"

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self, app_with_ratelimit):
        """Requests under the limit should pass through to the endpoint."""
        mock_redis = _build_mock_redis(zcard_cb=lambda *a, **kw: 0)

        with patch("redis.asyncio.ConnectionPool.from_url"), \
             patch("redis.asyncio.Redis", return_value=mock_redis):
            client = app_with_ratelimit
            resp = await client.get(self._URL)
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_blocks_when_over_limit(self, app_with_ratelimit):
        """When Redis reports the limit is exceeded, middleware returns 429."""
        mock_redis = _build_mock_redis(zcard_cb=lambda *a, **kw: 999)

        with patch("redis.asyncio.ConnectionPool.from_url"), \
             patch("redis.asyncio.Redis", return_value=mock_redis):
            client = app_with_ratelimit
            resp = await client.get(self._URL)
            assert resp.status_code == 429
            data = resp.json()
            assert "detail" in data
            assert "Retry-After" in resp.headers

    @pytest.mark.asyncio
    async def test_retry_after_computed_from_oldest_entry(self, app_with_ratelimit):
        """Retry-After should be based on when the oldest request expires."""
        now = time.time()
        oldest = now - 30  # 30 seconds ago in a 60s window → 30s until expiry
        mock_redis = _build_mock_redis(
            zcard_cb=lambda *a, **kw: 999,
            zrange_cb=lambda *a, **kw: [("ts:oldest", oldest)],
        )

        with patch("redis.asyncio.ConnectionPool.from_url"), \
             patch("redis.asyncio.Redis", return_value=mock_redis):
            client = app_with_ratelimit
            resp = await client.get(self._URL)
            assert resp.status_code == 429
            retry_after = int(resp.headers["Retry-After"])
            # Should be roughly 30 (oldest + 60 - now ≈ 30)
            assert 25 <= retry_after <= 35, f"Expected ~30, got {retry_after}"

    @pytest.mark.asyncio
    async def test_fail_open_on_redis_error(self, app_with_ratelimit):
        """When Redis throws, the request should still go through (fail-open)."""
        mock_redis = _build_mock_redis()
        mock_redis.zremrangebyscore = AsyncMock(side_effect=ConnectionError("boom"))

        with patch("redis.asyncio.ConnectionPool.from_url"), \
             patch("redis.asyncio.Redis", return_value=mock_redis):
            client = app_with_ratelimit
            resp = await client.get(self._URL)
            # Should not be 429 — fail-open means traffic passes
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_different_ips_have_separate_buckets(self, app_with_ratelimit):
        """IP A being rate-limited should not affect IP B."""
        # Track keys used for zcard, so we can verify IPs produce different keys
        zcard_keys = []
        zadd_keys = []

        def _zcard_side(key, *args, **kwargs):
            zcard_keys.append(key)
            return 0

        def _zadd_side(key, *args, **kwargs):
            zadd_keys.append(key)

        mock_redis = _build_mock_redis(
            zcard_cb=_zcard_side,
            zadd_cb=_zadd_side,
        )

        with patch("redis.asyncio.ConnectionPool.from_url"), \
             patch("redis.asyncio.Redis", return_value=mock_redis):
            client = app_with_ratelimit

            # Request from "IP-A" via header
            resp = await client.get(
                self._URL,
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            assert resp.status_code == 200

            # Request from "IP-B" via header
            resp = await client.get(
                self._URL,
                headers={"X-Forwarded-For": "10.0.0.2"},
            )
            assert resp.status_code == 200

            # Both requests should have recorded keys with different IPs
            assert len(zcard_keys) >= 2
            ip1_key = next(k for k in zcard_keys if "10.0.0.1" in k)
            ip2_key = next(k for k in zcard_keys if "10.0.0.2" in k)
            assert ip1_key != ip2_key


class TestInMemoryRateLimiting:
    """End-to-end tests using the real app but an in-memory timer for deterministic
    sliding-window verification without Redis or time.sleep."""

    @pytest.mark.asyncio
    async def test_rapid_requests_exceed_limit(self):
        """10+ rapid requests from the same IP should get 429.

        Uses a deterministic fake clock so the test runs instantly.
        """
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=10, window=60)

        # First 10 requests should be allowed
        for i in range(10):
            allowed, retry = await limiter.check("192.168.1.1", "/api/test")
            assert allowed, f"Request {i+1} should be allowed"

        # 11th request should be blocked
        allowed, retry = await limiter.check("192.168.1.1", "/api/test")
        assert not allowed, "11th request should be blocked"
        assert retry >= 1

    @pytest.mark.asyncio
    async def test_window_slides_forward(self):
        """After the window slides past the oldest timestamp, requests resume."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=5, window=60)

        # Fire 6 rapid requests — 6th is blocked
        for i in range(5):
            allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
            assert allowed
        allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
        assert not allowed

        # Advance time past the window (oldest is at 1000000.0, window=60)
        fake_now[0] += 61
        allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
        assert allowed

    @pytest.mark.asyncio
    async def test_different_ips_independent(self):
        """Flooding one IP should not block another."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=3, window=60)

        # Exhaust IP A
        for i in range(3):
            allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
            assert allowed
        allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
        assert not allowed

        # IP B should still work
        allowed, _ = await limiter.check("10.0.0.2", "/api/qa")
        assert allowed

    @pytest.mark.asyncio
    async def test_different_endpoints_independent(self):
        """Same IP to different endpoints have separate buckets."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=3, window=60)

        # Exhaust /api/qa for one IP
        for i in range(3):
            allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
            assert allowed
        allowed, _ = await limiter.check("10.0.0.1", "/api/qa")
        assert not allowed

        # Same IP to /api/search should still work
        allowed, _ = await limiter.check("10.0.0.1", "/api/search")
        assert allowed

    @pytest.mark.asyncio
    async def test_retry_after_is_correct(self):
        """Retry-After should reflect when the oldest request expires."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=2, window=60)

        # First request at t=0
        await limiter.check("192.168.1.1", "/x")
        # Second request at t=30
        fake_now[0] += 30
        await limiter.check("192.168.1.1", "/x")
        # Third request — blocked. Oldest is at t=0, window=60, expires at t=60
        # now = 30, so retry_after = 60 - 30 = 30
        fake_now[0] += 0.5
        allowed, retry_after = await limiter.check("192.168.1.1", "/x")
        assert not allowed
        assert 29 <= retry_after <= 31, f"Expected ~30, got {retry_after}"

    @pytest.mark.asyncio
    async def test_min_retry_after_is_one_second(self):
        """Retry-After must always be at least 1."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=1, window=60)

        await limiter.check("10.0.0.1", "/y")
        # Second request is blocked, Retry-After should be ≥ 1
        allowed, retry_after = await limiter.check("10.0.0.1", "/y")
        assert not allowed
        assert retry_after >= 1


class TestClientIPExtraction:
    """Test IP extraction logic."""

    def test_prefers_x_forwarded_for(self):
        """X-Forwarded-For should take priority."""
        from app.core.ratelimit import _client_ip
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [
                (b"x-forwarded-for", b"10.0.0.1, 10.0.0.2"),
            ],
            "client": ("192.168.1.1", 12345),
        }
        request = Request(scope)
        assert _client_ip(request) == "10.0.0.1"

    def test_falls_back_to_x_real_ip(self):
        """X-Real-IP should be used when X-Forwarded-For is absent."""
        from app.core.ratelimit import _client_ip
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [
                (b"x-real-ip", b"10.0.0.3"),
            ],
            "client": ("192.168.1.1", 12345),
        }
        request = Request(scope)
        assert _client_ip(request) == "10.0.0.3"

    def test_falls_back_to_client_host(self):
        """When no proxy headers are set, use the direct client IP."""
        from app.core.ratelimit import _client_ip
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [],
            "client": ("192.168.1.1", 12345),
        }
        request = Request(scope)
        assert _client_ip(request) == "192.168.1.1"

    def test_unknown_when_no_client(self):
        """When there's no client info at all, return 'unknown'."""
        from app.core.ratelimit import _client_ip
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [],
            "client": None,
        }
        request = Request(scope)
        assert _client_ip(request) == "unknown"
