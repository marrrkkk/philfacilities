#!/usr/bin/env python3
"""Local read-API latency baseline for PhilFacilities.

This is a local smoke benchmark against the configured database, not a capacity or
load test. It measures serial request latency against a locally running API so
regressions in query plans or response building are visible before a deployment.
The working database is real and publication-gated, but this is still one client
over loopback, not a representative production load test.

Usage:
    uv run python scripts/api_benchmark.py
    uv run python scripts/api_benchmark.py --samples 20 --json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = os.environ.get("PHILFACILITIES_API_BASE_URL", "http://127.0.0.1:8010")

ENDPOINTS = [
    ("health", "/healthz"),
    ("statistics", "/v1/statistics"),
    ("facilities", "/v1/facilities?limit=20"),
    ("bbox query", "/v1/facilities/within?bbox=120.9,14.4,121.1,14.7&limit=500"),
    ("sources", "/v1/sources"),
]


@dataclass(frozen=True)
class Result:
    name: str
    path: str
    samples: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    mean_bytes: int


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile; adequate for small deterministic sample sets."""
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def fetch(url: str, timeout: float) -> tuple[int, int]:
    request = Request(url, headers={"Accept": "application/json, text/csv;q=0.9"})
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            size = len(response.read())
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"{url} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"{url} is unreachable: {exc.reason}") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    return round(elapsed_ms), size


def _first_facility_detail_path(base_url: str, timeout: float) -> str:
    url = base_url.rstrip("/") + "/v1/facilities?limit=1"
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Could not discover a public facility for the detail sample: {url}"
        ) from exc
    items = payload.get("items") or []
    if not items or not items[0].get("slug"):
        raise RuntimeError("The API returned no public facility to benchmark.")
    return f"/v1/facilities/{items[0]['slug']}"


def run(base_url: str, samples: int, warmup: int, timeout: float) -> list[Result]:
    endpoints = list(ENDPOINTS)
    endpoints.insert(3, ("facility detail", _first_facility_detail_path(base_url, timeout)))
    results: list[Result] = []
    for name, path in endpoints:
        url = base_url.rstrip("/") + path
        for _ in range(warmup):
            fetch(url, timeout)
        durations: list[int] = []
        sizes: list[int] = []
        for _ in range(samples):
            elapsed_ms, size = fetch(url, timeout)
            durations.append(elapsed_ms)
            sizes.append(size)
        results.append(
            Result(
                name=name,
                path=path,
                samples=samples,
                p50_ms=percentile(durations, 0.50),
                p95_ms=percentile(durations, 0.95),
                max_ms=max(durations),
                mean_bytes=round(statistics.fmean(sizes)),
            )
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--samples", type=int, default=10, help="measured requests per endpoint")
    parser.add_argument("--warmup", type=int, default=2, help="unmeasured requests per endpoint")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per request")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    if args.samples < 1 or args.warmup < 0:
        parser.error("--samples must be at least 1 and --warmup cannot be negative")

    try:
        results = run(args.base_url, args.samples, args.warmup, args.timeout)
    except RuntimeError as exc:
        print(f"BENCHMARK FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
        return 0

    print(f"PhilFacilities API latency baseline ({args.base_url})")
    print("Publication-approved real data; serial requests over loopback. Not a load test.")
    print()
    print(f"{'endpoint':<16} {'p50 ms':>7} {'p95 ms':>7} {'max ms':>7} {'bytes':>7}  path")
    for result in results:
        print(
            f"{result.name:<16} {result.p50_ms:>7.0f} {result.p95_ms:>7.0f} "
            f"{result.max_ms:>7.0f} {result.mean_bytes:>7d}  {result.path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
