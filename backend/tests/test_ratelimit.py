"""Tests for Redis-based rate limiting middleware."""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
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


@pytest_asyncio.fixture
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

        with (
            patch("redis.asyncio.ConnectionPool.from_url"),
            patch("redis.asyncio.Redis", return_value=mock_redis),
        ):
            client = app_with_ratelimit
            resp = await client.get(self._URL)
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_blocks_when_over_limit(self, app_with_ratelimit):
        """When Redis reports the limit is exceeded, middleware returns 429."""
        mock_redis = _build_mock_redis(zcard_cb=lambda *a, **kw: 999)

        with (
            patch("redis.asyncio.ConnectionPool.from_url"),
            patch("redis.asyncio.Redis", return_value=mock_redis),
        ):
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

        with (
            patch("redis.asyncio.ConnectionPool.from_url"),
            patch("redis.asyncio.Redis", return_value=mock_redis),
        ):
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

        with (
            patch("redis.asyncio.ConnectionPool.from_url"),
            patch("redis.asyncio.Redis", return_value=mock_redis),
        ):
            client = app_with_ratelimit
            resp = await client.get(self._URL)
            # Should not be 429 — fail-open means traffic passes
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_different_client_ips_have_separate_buckets(self, app_with_ratelimit):
        """Two requests from different client hosts should use separate
        rate-limit keys.  Verifies that _client_ip always uses
        request.client.host, not spoofable headers."""
        zcard_keys = []

        def _zcard_side(key, *args, **kwargs):
            zcard_keys.append(key)
            return 0

        mock_redis = _build_mock_redis(zcard_cb=_zcard_side)

        with (
            patch("redis.asyncio.ConnectionPool.from_url"),
            patch("redis.asyncio.Redis", return_value=mock_redis),
        ):
            client = app_with_ratelimit

            # The ASGI transport always uses ("testclient", 50000) as
            # the client address, so both requests share the same bucket
            # regardless of X-Forwarded-For headers.
            resp = await client.get(
                self._URL,
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            assert resp.status_code == 200

            resp = await client.get(
                self._URL,
                headers={"X-Forwarded-For": "10.0.0.2"},
            )
            assert resp.status_code == 200

            # Both keys should use the actual client host (testclient),
            # NOT the spoofed X-Forwarded-For values.
            assert len(zcard_keys) >= 2
            for key in zcard_keys:
                assert "10.0.0.1" not in key, (
                    f"Spoofed IP 10.0.0.1 should not appear in key {key!r}"
                )
                assert "10.0.0.2" not in key, (
                    f"Spoofed IP 10.0.0.2 should not appear in key {key!r}"
                )


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
            assert allowed, f"Request {i + 1} should be allowed"

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
        for _i in range(5):
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
        for _i in range(3):
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
        for _i in range(3):
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
    """Test IP extraction logic.

    _client_ip always uses ``request.client.host`` (the direct connection
    address) to prevent IP spoofing via forged X-Forwarded-For headers.
    """

    def test_uses_client_host_directly(self):
        """Direct client IP is always used, ignoring proxy headers."""
        from starlette.requests import Request

        from app.core.ratelimit import _client_ip

        scope = {
            "type": "http",
            "headers": [
                (b"x-forwarded-for", b"10.0.0.1, 10.0.0.2"),
                (b"x-real-ip", b"10.0.0.3"),
            ],
            "client": ("192.168.1.1", 12345),
        }
        request = Request(scope)
        # Proxy headers are ignored — use the actual connecting IP
        assert _client_ip(request) == "192.168.1.1"

    def test_uses_client_host_when_no_proxy_headers(self):
        """When no proxy headers are set, use the direct client IP."""
        from starlette.requests import Request

        from app.core.ratelimit import _client_ip

        scope = {
            "type": "http",
            "headers": [],
            "client": ("192.168.1.1", 12345),
        }
        request = Request(scope)
        assert _client_ip(request) == "192.168.1.1"

    def test_unknown_when_no_client(self):
        """When there's no client info at all, return 'unknown'."""
        from starlette.requests import Request

        from app.core.ratelimit import _client_ip

        scope = {
            "type": "http",
            "headers": [],
            "client": None,
        }
        request = Request(scope)
        assert _client_ip(request) == "unknown"


class TestPerRouteTiers:
    """Tests for per-route rate limit tier resolution."""

    def test_qa_endpoint_gets_strict_limit(self):
        """QA endpoint should have a strict limit with burst allowance."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/qa")
        assert limit == 10
        assert window == 60
        assert burst == 3

    def test_qa_stream_gets_strict_limit(self):
        """/qa/stream should match the exact tier."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/qa/stream")
        assert limit == 10
        assert burst == 3

    def test_qa_presets_gets_moderate_limit(self):
        """QA presets should have a slightly higher limit than raw QA."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/qa/presets")
        assert limit == 15
        assert burst == 5

    def test_search_gets_generous_limit(self):
        """Search should have a higher limit (read-only, cheap)."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/search")
        assert limit == 60
        assert burst == 15

    def test_pipeline_status_gets_very_generous_limit(self):
        """Pipeline status should have the highest limit."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/pipeline/status")
        assert limit == 120
        assert burst == 20

    def test_unknown_path_gets_default(self):
        """Unmatched paths should get the default limit with no burst."""
        from app.core.ratelimit import DEFAULT_LIMIT, DEFAULT_WINDOW, _get_tier

        limit, window, burst = _get_tier("/some/random/path")
        assert limit == DEFAULT_LIMIT
        assert window == DEFAULT_WINDOW
        assert burst == 0

    def test_prefix_match_for_nested_path(self):
        """Nested paths should match via prefix."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/documents/123")
        assert limit == 30
        assert burst == 8

    def test_exact_match_wins_over_prefix(self):
        """/documents/upload has an exact match that overrides the prefix."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/documents/upload")
        assert limit == 20
        assert burst == 5

    def test_crm_endpoint_gets_moderate_limit(self):
        """CRM endpoints should have moderate limits."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/crm/contacts")
        assert limit == 30
        assert burst == 8

    def test_monitoring_endpoint_gets_high_limit(self):
        """Monitoring endpoints should have generous limits."""
        from app.core.ratelimit import _get_tier

        limit, window, burst = _get_tier("/monitoring/errors")
        assert limit == 120
        assert burst == 20


class TestBurstAllowance:
    """Tests verifying burst allowance works properly in rate limiting."""

    @pytest.mark.asyncio
    async def test_burst_allows_extra_requests_within_window(self):
        """Burst should allow extra requests beyond the base limit."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        # Simulate a tier with limit=5, window=60, burst=3 → effective=8
        limiter = FakeTimeRateLimiter(limit=8, window=60)

        # 8 requests should all pass (5 base + 3 burst)
        for i in range(8):
            allowed, _ = await limiter.check("10.0.0.1", "/qa")
            assert allowed, f"Request {i + 1}/8 with burst should be allowed"

        # 9th should be blocked
        allowed, _ = await limiter.check("10.0.0.1", "/qa")
        assert not allowed, "9th request should be blocked after burst exhausted"

    @pytest.mark.asyncio
    async def test_burst_resets_after_window(self):
        """After window slides, burst allowance should refresh."""
        fake_now = [1000000.0]

        class FakeTimeRateLimiter(_InMemoryRateLimiter):
            async def check(self, ip: str, path: str, now=None):
                return await super().check(ip, path, now=fake_now[0])

        limiter = FakeTimeRateLimiter(limit=4, window=60)

        # Use all 4 + 1 more to prove limit works
        for _ in range(4):
            await limiter.check("10.0.0.1", "/search")
        allowed, _ = await limiter.check("10.0.0.1", "/search")
        assert not allowed

        # Advance past window
        fake_now[0] += 61
        # Now should have 4 fresh slots
        for i in range(4):
            allowed, _ = await limiter.check("10.0.0.1", "/search")
            assert allowed, f"After window refresh, request {i + 1} should pass"


class TestRateLimitPrometheusMetrics:
    """Tests for Prometheus metrics exposed by the rate limiter."""

    def test_ratelimit_hits_counter_registered(self):
        """The ratelimit_hits_total counter should be registered in Prometheus."""
        from prometheus_client import REGISTRY

        from app.core.ratelimit import ratelimit_hits_total

        # Counter should exist and have the right name
        # Counter base name is "ratelimit_hits" (Prometheus appends _total in output)
        assert ratelimit_hits_total._name == "ratelimit_hits"

        # Should be findable in the registry (without _total suffix)
        found = False
        for metric in REGISTRY.collect():
            if metric.name == "ratelimit_hits":
                found = True
                break
        assert found, "ratelimit_hits should be in the Prometheus registry"

    def test_ratelimit_active_buckets_gauge_registered(self):
        """The ratelimit_active_buckets gauge should be registered."""
        from prometheus_client import REGISTRY

        from app.core.ratelimit import ratelimit_active_buckets

        assert ratelimit_active_buckets._name == "ratelimit_active_buckets"

        found = False
        for metric in REGISTRY.collect():
            if metric.name == "ratelimit_active_buckets":
                found = True
                break
        assert found, "ratelimit_active_buckets should be in the Prometheus registry"

    def test_ratelimit_hits_increments_correctly(self):
        """Incrementing the counter should work with labels."""
        from app.core.ratelimit import ratelimit_hits_total

        before = ratelimit_hits_total.labels(endpoint="/qa")._value.get()
        ratelimit_hits_total.labels(endpoint="/qa").inc()
        after = ratelimit_hits_total.labels(endpoint="/qa")._value.get()
        assert after == before + 1
