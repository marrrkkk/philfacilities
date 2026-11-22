#!/usr/bin/env python3
"""Verify that a deployed public projection matches its manifest.

Used by `.github/workflows/publish-heroku.yml` after a restore and locally after
a deploy. The checks include a facility detail request: the previous projection
omitted source-evidence tables and every detail page returned 404 while the
directory still looked healthy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

MANIFEST_VERSION = 1
FIELDS_TIMEOUT_SECONDS = 20.0


def verify_checksum(dump_path: Path, manifest: dict) -> list[str]:
    """Return a failure message when the dump does not match the manifest."""

    digest = hashlib.sha256()
    with dump_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    expected = manifest.get("sha256", "")
    if actual != expected:
        return [f"sha256 mismatch: expected {expected}, got {actual}"]
    return []


def check_api(
    *,
    manifest: dict,
    get: Callable[[str], tuple[int, dict[str, Any], float]],
) -> list[str]:
    """Check live API responses against the manifest.

    ``get`` returns ``(status_code, json_body, elapsed_seconds)`` so this stays
    unit-testable without a live server.
    """

    failures: list[str] = []
    if manifest.get("format_version") != MANIFEST_VERSION:
        failures.append(f"unsupported manifest version: {manifest.get('format_version')}")

    status, body, _ = get("/healthz")
    if status != 200:
        failures.append(f"/healthz returned {status}")
    elif str(body.get("status", "")).lower() not in {"ok", "healthy"}:
        failures.append(f"/healthz status is {body.get('status')!r}")
    if "database" in body and body.get("database") != "ok":
        failures.append(f"/healthz database is {body.get('database')!r}")

    status, body, _ = get("/v1/statistics")
    if status != 200:
        failures.append(f"/v1/statistics returned {status}")
    else:
        expected = manifest.get("counts", {}).get("core.facilities")
        published = sum((body.get("by_category") or {}).values())
        if expected is not None and published != expected:
            failures.append(f"published facilities {published} != manifest {expected}")

    status, body, _ = get("/v1/facilities?limit=1")
    if status != 200:
        failures.append(f"facility list returned {status}")
    else:
        items = body.get("items") or []
        if not items:
            failures.append("facility list is empty")
        else:
            facility = items[0]
            identifier = facility.get("id") or facility.get("slug")
            if not identifier:
                failures.append("facility list item has no id or slug")
            else:
                detail_status, _, _ = get(f"/v1/facilities/{identifier}")
                if detail_status != 200:
                    failures.append(f"facility detail returned {detail_status}")

    status, _, elapsed = get("/v1/fields")
    if status != 200:
        failures.append(f"/v1/fields returned {status}")
    elif elapsed > FIELDS_TIMEOUT_SECONDS:
        failures.append(f"/v1/fields took {elapsed:.1f}s (limit {FIELDS_TIMEOUT_SECONDS}s)")

    status, body, _ = get("/mcp/readyz")
    if status != 200:
        failures.append(f"/mcp/readyz returned {status}")
    elif body.get("status") != "ok":
        failures.append(f"/mcp/readyz status is {body.get('status')!r}")

    return failures


def http_get(base_url: str) -> Callable[[str], tuple[int, dict[str, Any], float]]:
    """Build a GET function bound to a base URL."""

    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0)

    def get(path: str) -> tuple[int, dict[str, Any], float]:
        started = time.monotonic()
        response = client.get(path)
        elapsed = time.monotonic() - started
        try:
            body = response.json()
        except ValueError:
            body = {}
        return response.status_code, body if isinstance(body, dict) else {}, elapsed

    return get


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Base URL of the deployed API.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dump", type=Path, help="Also verify the dump checksum.")
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures: list[str] = []
    if args.dump:
        failures.extend(verify_checksum(args.dump, manifest))
    failures.extend(check_api(manifest=manifest, get=http_get(args.url)))
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print(f"OK: {manifest.get('counts', {}).get('core.facilities', 0):,} public facilities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
