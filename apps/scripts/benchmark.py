#!/usr/bin/env python3
"""RAG-CRM Query Latency Benchmark Tool.

Measures end-to-end query latency for the /qa and /search endpoints under
realistic concurrent load. Produces p50, p95, and p99 percentiles as well
as throughput (requests/sec).

Usage:
    python apps/scripts/benchmark.py              # default: 50 requests, concurrency=5
    python apps/scripts/benchmark.py --concurrency 10 --requests 100
    python apps/scripts/benchmark.py --endpoint /search --concurrency 5 --requests 30
    python apps/scripts/benchmark.py --qa-presets deep,concise  # structured QA workloads

Requires:
    - Backend running at BACKEND_URL (default http://localhost:8000)
    - httpx and numpy installed (pip install httpx numpy if needed)

Output:
    - Latency percentiles (p50, p95, p99) in milliseconds
    - Throughput in requests/second
    - Success/failure counts
    - Per-endpoint breakdowns (when multiple endpoints exercised)
"""

from __future__ import annotations

import argparse
import asyncio
import math
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("Error: numpy is required. Install with: pip install numpy")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────────────

DEFAULT_BACKEND_URL = "http://localhost:8000"
DEFAULT_REQUESTS = 50
DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT = 60.0  # seconds per request

# QA preset test queries — represent real user workloads
QA_PRESETS: dict[str, list[str]] = {
    "deep": [
        "What are the key architectural decisions in our system design documentation?",
        "Explain the tradeoffs between vector search and keyword search in detail.",
        "Summarize all documents related to database performance optimization.",
    ],
    "concise": [
        "What is RAG?",
        "List the supported file formats.",
        "What is the upload size limit?",
    ],
    "bullet": [
        "What are the main features of the CRM system?",
        "List the supported document formats for upload.",
        "What monitoring endpoints are available?",
    ],
    "comparison": [
        "Compare pgvector with other vector databases.",
        "What are the differences between chunking strategies?",
    ],
    "summary": [
        "Give me a summary of the CRM context integration.",
        "Summarize the hybrid search approach used in this platform.",
    ],
    "step_by_step": [
        "Walk me through the document ingestion pipeline step by step.",
        "How do I upload a document and search for it?",
    ],
}

# Generic question fallback (when no presets specified)
DEFAULT_QA_QUESTIONS: list[str] = [
    "What is the RAG-CRM platform?",
    "How does hybrid search work?",
    "What file formats are supported for upload?",
    "Explain the LangGraph pipeline.",
    "What is the CRM context agent?",
]

# Search queries
SEARCH_QUERIES: list[str] = [
    "performance optimization",
    "database configuration",
    "document ingestion",
    "hybrid search",
    "embedding model",
    "CRM integration",
    "API endpoints",
    "health monitoring",
    "rate limiting",
    "LangGraph pipeline",
]


# ── Data Types ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkConfig:
    """Benchmark run configuration."""

    backend_url: str
    endpoint: str  # "/qa" or "/search"
    num_requests: int
    concurrency: int
    timeout: float
    qa_presets: list[str] = field(default_factory=list)


@dataclass
class RequestResult:
    """Result of a single request."""

    endpoint: str
    status_code: int
    latency_ms: float
    payload: str = ""  # first 100 chars of request body or query param
    error: str = ""


@dataclass
class BenchmarkReport:
    """Aggregated benchmark results."""

    config: BenchmarkConfig
    total_requests: int
    successes: int
    failures: int
    latencies_ms: list[float]
    duration_sec: float
    throughput: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float
    results: list[RequestResult]

    def print(self) -> None:
        """Pretty-print the benchmark report."""
        print()
        print("=" * 68)
        print("  RAG-CRM QUERY LATENCY BENCHMARK RESULTS")
        print("=" * 68)
        print(f"  Backend:       {self.config.backend_url}")
        print(f"  Endpoint:      {self.config.endpoint}")
        print(f"  Concurrency:   {self.config.concurrency}")
        print(f"  Total sent:    {self.total_requests}")
        print(f"  Successes:     {self.successes}")
        print(f"  Failures:      {self.failures}")
        print(f"  Duration:      {self.duration_sec:.2f}s")
        print(f"  Throughput:    {self.throughput:.2f} req/s")
        print("-" * 68)
        print(f"  p50  latency:  {self.p50_ms:.1f} ms")
        print(f"  p95  latency:  {self.p95_ms:.1f} ms")
        print(f"  p99  latency:  {self.p99_ms:.1f} ms")
        print(f"  min  latency:  {self.min_ms:.1f} ms")
        print(f"  max  latency:  {self.max_ms:.1f} ms")
        print(f"  mean latency:  {self.mean_ms:.1f} ms")
        print("=" * 68)

        if self.failures > 0:
            print()
            print("  FAILURES:")
            for r in self.results:
                if r.status_code != 200:
                    print(f"    [{r.status_code}] {r.endpoint}: {r.error}")

    def json(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "backend_url": self.config.backend_url,
            "endpoint": self.config.endpoint,
            "concurrency": self.config.concurrency,
            "total_requests": self.total_requests,
            "successes": self.successes,
            "failures": self.failures,
            "duration_sec": round(self.duration_sec, 3),
            "throughput_rps": round(self.throughput, 2),
            "latency_ms": {
                "p50": round(self.p50_ms, 1),
                "p95": round(self.p95_ms, 1),
                "p99": round(self.p99_ms, 1),
                "min": round(self.min_ms, 1),
                "max": round(self.max_ms, 1),
                "mean": round(self.mean_ms, 1),
            },
        }


# ── Core Benchmark Logic ────────────────────────────────────────────────────


async def _send_qa_request(
    client: httpx.AsyncClient,
    url: str,
    question: str,
    timeout: float,
) -> RequestResult:
    """Send a single POST /qa request and measure latency."""
    start = time.monotonic()
    try:
        resp = await client.post(
            url,
            json={
                "query": question,
                "preset": "deep",  # exercises full pipeline
                "stream": False,
            },
            timeout=timeout,
        )
        latency = (time.monotonic() - start) * 1000.0
        return RequestResult(
            endpoint="/qa",
            status_code=resp.status_code,
            latency_ms=latency,
            payload=question[:100],
            error="" if resp.status_code == 200 else resp.text[:200],
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000.0
        return RequestResult(
            endpoint="/qa",
            status_code=0,
            latency_ms=latency,
            payload=question[:100],
            error=str(exc),
        )


async def _send_search_request(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    timeout: float,
) -> RequestResult:
    """Send a single GET /search request and measure latency."""
    start = time.monotonic()
    try:
        resp = await client.get(
            url,
            params={"q": query, "top_k": 5},
            timeout=timeout,
        )
        latency = (time.monotonic() - start) * 1000.0
        return RequestResult(
            endpoint="/search",
            status_code=resp.status_code,
            latency_ms=latency,
            payload=query[:100],
            error="" if resp.status_code == 200 else resp.text[:200],
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000.0
        return RequestResult(
            endpoint="/search",
            status_code=0,
            latency_ms=latency,
            payload=query[:100],
            error=str(exc),
        )


async def _health_check(url: str, timeout: float = 10.0) -> bool:
    """Verify the backend is reachable before benchmarking."""
    health_url = f"{url.rstrip('/')}/health/ready"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(health_url, timeout=timeout)
            return resp.status_code == 200
    except Exception:
        return False


async def _worker(
    client: httpx.AsyncClient,
    endpoint: str,
    url: str,
    questions: list[str],
    timeout: float,
    results: list[RequestResult],
    idx: int,
) -> None:
    """Single worker: send one request."""
    question = questions[idx % len(questions)]
    if endpoint == "/qa":
        result = await _send_qa_request(client, url, question, timeout)
    else:
        result = await _send_search_request(client, url, question, timeout)
    results.append(result)


def _compute_percentiles(
    latencies: list[float],
) -> tuple[float, float, float, float, float, float]:
    """Compute p50, p95, p99, min, max, mean from a list of latencies (ms)."""
    if not latencies:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    arr = np.array(latencies, dtype=np.float64)
    return (
        float(np.percentile(arr, 50)),
        float(np.percentile(arr, 95)),
        float(np.percentile(arr, 99)),
        float(np.min(arr)),
        float(np.max(arr)),
        float(np.mean(arr)),
    )


async def run_benchmark(config: BenchmarkConfig) -> BenchmarkReport:
    """Execute the benchmark and return a report."""
    url = f"{config.backend_url.rstrip('/')}{config.endpoint}"

    # Determine questions
    if config.endpoint == "/qa" and config.qa_presets:
        questions: list[str] = []
        for preset in config.qa_presets:
            questions.extend(QA_PRESETS.get(preset, []))
        if not questions:
            questions = DEFAULT_QA_QUESTIONS
    elif config.endpoint == "/qa":
        questions = DEFAULT_QA_QUESTIONS
    else:
        questions = SEARCH_QUERIES

    print(f"Benchmarking {config.endpoint} against {url}")
    print(f"  Requests: {config.num_requests}, Concurrency: {config.concurrency}")
    print(f"  Question pool: {len(questions)} unique queries")
    print()

    results: list[RequestResult] = []
    start_time = time.monotonic()

    # Process requests with bounded concurrency
    sem = asyncio.Semaphore(config.concurrency)

    async def bounded_worker(idx: int) -> None:
        async with sem:
            async with httpx.AsyncClient() as client:
                await _worker(
                    client,
                    config.endpoint,
                    url,
                    questions,
                    config.timeout,
                    results,
                    idx,
                )
            # Progress indicator
            done = len(results)
            if done % max(1, config.num_requests // 10) == 0 or done == config.num_requests:
                elapsed = time.monotonic() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  [{done}/{config.num_requests}] {rate:.1f} req/s", flush=True)

    # Launch all workers
    tasks = [asyncio.create_task(bounded_worker(i)) for i in range(config.num_requests)]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print("\n  Benchmark cancelled by user.")
    except KeyboardInterrupt:
        print("\n  Benchmark interrupted by user.")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    duration = time.monotonic() - start_time

    # Categorize results
    successes = sum(1 for r in results if r.status_code == 200)
    failures = sum(1 for r in results if r.status_code != 200)

    # Compute percentiles from successful request latencies
    latencies = [r.latency_ms for r in results if r.status_code == 200]
    p50, p95, p99, mn, mx, mean = _compute_percentiles(latencies)

    throughput = successes / duration if duration > 0 else 0.0

    return BenchmarkReport(
        config=config,
        total_requests=len(results),
        successes=successes,
        failures=failures,
        latencies_ms=latencies,
        duration_sec=duration,
        throughput=throughput,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        min_ms=mn,
        max_ms=mx,
        mean_ms=mean,
        results=results,
    )


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> BenchmarkConfig:
    """Parse command-line arguments into a BenchmarkConfig."""
    parser = argparse.ArgumentParser(
        description="RAG-CRM Query Latency Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python apps/scripts/benchmark.py\n"
            "  python apps/scripts/benchmark.py --endpoint /search --concurrency 10\n"
            "  python apps/scripts/benchmark.py --qa-presets deep,concise,bullet\n"
        ),
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help=f"Backend base URL (default: {DEFAULT_BACKEND_URL})",
    )
    parser.add_argument(
        "--endpoint",
        default="/qa",
        choices=["/qa", "/search"],
        help="Endpoint to benchmark (default: /qa)",
    )
    parser.add_argument(
        "--requests", "-n",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"Total number of requests to send (default: {DEFAULT_REQUESTS})",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Maximum concurrent requests (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--qa-presets",
        default="",
        help=(
            "Comma-separated QA presets to exercise: "
            "deep,concise,bullet,comparison,summary,step_by_step"
        ),
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON instead of pretty-printed",
    )

    args = parser.parse_args(argv)

    presets: list[str] = []
    if args.qa_presets:
        presets = [p.strip() for p in args.qa_presets.split(",") if p.strip()]

    return BenchmarkConfig(
        backend_url=args.backend_url,
        endpoint=args.endpoint,
        num_requests=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
        qa_presets=presets,
    )


async def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, health-check, run benchmark, print results."""
    config = parse_args(argv)

    # Health check
    print("Checking backend health...", end=" ")
    if not await _health_check(config.backend_url):
        print("FAILED")
        print(f"  Could not reach {config.backend_url}/health/ready")
        print("  Make sure the backend is running: docker compose up -d backend")
        return 1
    print("OK")

    report = await run_benchmark(config)

    if "--json" in (argv or []) or "-j" in (argv or []):
        import json as _json
        print(_json.dumps(report.json(), indent=2))
    else:
        report.print()

    # Exit code: non-zero if any failures
    return 1 if report.failures > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
