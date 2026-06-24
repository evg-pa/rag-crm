"""Prometheus metrics middleware for FastAPI.

Exposes:
- ``http_requests_total`` — counter by method, endpoint, status
- ``http_request_duration_seconds`` — histogram of request latency
- ``db_query_duration_seconds`` — histogram of DB query latency (instrumented in DB layer)

Served at ``/metrics`` endpoint registered as a separate route.
"""

import time
from collections.abc import Awaitable, Callable

from prometheus_client import Counter, Histogram
from prometheus_client import generate_latest as _generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── Metrics ───────────────────────────────────────────────────────────────────

requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

db_query_duration = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    labelnames=["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware that records request count and latency for Prometheus."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()
        request_duration.labels(method=method, endpoint=endpoint).observe(duration)

        return response


def metrics_endpoint() -> Response:
    """Return Prometheus-formatted metrics."""
    from prometheus_client import generate_latest

    return Response(
        content=generate_latest().decode("utf-8"),
        media_type="text/plain; charset=utf-8",
    )
