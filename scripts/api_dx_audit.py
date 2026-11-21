#!/usr/bin/env python3
"""Read-only API developer-experience audit for PhilFacilities.

Counts every declared public field against the canonical database using the
same publication gate as the API, and optionally measures list/detail payload
sizes against a running API. Output goes to ``var/reports/`` only: generated
evidence never belongs in ``docs/``.

Usage:
    uv run python scripts/api_dx_audit.py
    uv run python scripts/api_dx_audit.py --api http://127.0.0.1:8010 \
        --samples 5
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from philfacilities_api.db import SessionLocal
from philfacilities_api.services.field_coverage import (
    COVERAGE_CAVEATS,
    FIELD_COVERAGE_VERSION,
    collect_field_coverage,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "var" / "reports"

GATE_DEFINITION = (
    "public_facility_index_filter() from services/filters.py: "
    "core.facilities.publication_status == 'public'"
)


def _fetch_json(url: str, timeout: float) -> tuple[dict, int, int]:
    request = Request(url, headers={"Accept": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return json.loads(body), elapsed_ms, len(body)


def measure_api(base_url: str, samples: int, timeout: float) -> dict:
    """Measure representative JSON payloads; never mutates the API or database."""

    base_url = base_url.rstrip("/")
    probes = {
        "facilities_limit_20": "/v1/facilities?limit=20",
        "facilities_limit_100": "/v1/facilities?limit=100",
        "facilities_limit_100_compact": "/v1/facilities?limit=100&view=compact",
        "facilities_type_school_limit_100": "/v1/facilities?type=school&limit=100",
        "map_bbox_zoom_10": "/v1/facilities/map?bbox=120,14,121,15&zoom=10",
        "taxonomy": "/v1/taxonomy",
        "fields": "/v1/fields?by_category=true",
    }
    first, _, _ = _fetch_json(base_url + "/v1/facilities?limit=1", timeout)
    items = first.get("items") or []
    if items:
        slug = items[0].get("slug") or items[0]["id"]
        probes["facility_detail_full"] = f"/v1/facilities/{slug}"
        probes["facility_detail_compact"] = f"/v1/facilities/{slug}?view=compact"

    measured = {}
    for name, path in probes.items():
        try:
            durations: list[int] = []
            sizes: list[int] = []
            top_level_keys: int | None = None
            for _ in range(samples):
                payload, elapsed_ms, size = _fetch_json(base_url + path, timeout)
                durations.append(elapsed_ms)
                sizes.append(size)
                if top_level_keys is None and isinstance(payload, dict):
                    top_level_keys = len(payload)
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            # An older deployment may not expose every probe. The audit stays
            # read-only and records the gap instead of aborting the whole run.
            measured[name] = {"path": path, "unavailable": str(exc)}
            continue
        measured[name] = {
            "path": path,
            "samples": samples,
            "p50_ms": statistics.median(durations),
            "min_ms": min(durations),
            "max_ms": max(durations),
            "mean_bytes": round(statistics.fmean(sizes), 1),
            "top_level_keys": top_level_keys,
        }
    return measured


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", help="base URL of a running API to measure (optional)")
    parser.add_argument("--samples", type=int, default=3, help="requests per measured endpoint")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds per request")
    parser.add_argument(
        "--no-by-category",
        action="store_true",
        help="skip per-category field denominators (included by default)",
    )
    parser.add_argument(
        "--output", help="explicit output path (default: var/reports/api-dx-audit-<UTC>.json)"
    )
    args = parser.parse_args()

    if args.samples < 1:
        parser.error("--samples must be at least 1")
    database_url = os.environ.get("PHILFACILITIES_DATABASE_URL", "")
    if not database_url:
        print("PHILFACILITIES_DATABASE_URL is required", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        coverage = collect_field_coverage(session, by_category=not args.no_by_category)
    coverage.pop("as_of", None)  # replaced with the report timestamp below
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database_url_host": database_url.split("@")[-1].split("/")[0],
        "gate_definition": GATE_DEFINITION,
        "coverage_version": FIELD_COVERAGE_VERSION,
        "caveats": COVERAGE_CAVEATS,
        "fields": coverage["fields"],
        "by_category": coverage.get("by_category"),
        "api": measure_api(args.api, args.samples, args.timeout) if args.api else None,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = Path(args.output) if args.output else REPORT_DIR / f"api-dx-audit-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {path}")
    for entry in report["fields"]:
        if entry["field"] in {
            "relationships[]",
            "school.resources[]",
            "public_access_class",
            "contacts[]",
            "location.postal_code",
        }:
            print(
                f"  {entry['field']:<26} {entry['populated']:>8} / {entry['total']:<8} "
                f"({entry['fill_ratio']:.4f})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
