#!/usr/bin/env python3
"""Capture real, live API examples for the required report 07.

The script never synthesizes a response. It reads the running local API, records
the actual HTTP status and selected payloads, and labels the output as a snapshot.
Synthetic demonstration records are called out explicitly and are not presented as
official government data.

Usage:
    uv run python scripts/capture_api_examples.py
    PHILFACILITIES_API_URL=http://127.0.0.1:8010 uv run python scripts/capture_api_examples.py
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_OUTPUT = Path("docs/reports/07-real-api-examples.md")


def _truncate(value: Any, *, width: int = 5000) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    if len(text) <= width:
        return text
    return text[:width].rstrip() + "\n… (truncated for this report)"


def _get(client: httpx.Client, path: str, **params: Any) -> tuple[int, Any, dict[str, str]]:
    response = client.get(path, params=params)
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    return response.status_code, payload, dict(response.headers)


def _example(
    client: httpx.Client,
    *,
    title: str,
    path: str,
    params: dict[str, Any] | None = None,
    note: str | None = None,
    width: int = 5000,
) -> list[str]:
    query = ""
    if params:
        query = "?" + "&".join(
            f"{key}={httpx.QueryParams({key: value})[key]}" for key, value in params.items()
        )
    status, payload, headers = _get(client, path, **(params or {}))
    lines = [
        f"### {title}",
        "",
        f"```http\nGET {path}{query}\n```",
        "",
        f"HTTP `{status}` · `{headers.get('content-type', 'unknown')}`",
        "",
    ]
    if note:
        lines.extend([note, ""])
    lines.extend(["```json", _truncate(payload, width=width), "```", ""])
    return lines


def build_report(base_url: str, *, timeout: float = 30.0) -> str:
    generated_at = datetime.now(UTC).isoformat()
    lines = [
        "# 07 — Real API Examples",
        "",
        f"**Captured:** {generated_at}  ",
        f"**API:** `{base_url}`  ",
        "**Source of truth:** a live response from the running PhilFacilities API.",
        "",
        "This report is a point-in-time snapshot. It does not claim nationwide coverage, "
        "completeness, or a legal review. Counts come from the response body, which only "
        "includes records that passed the publication gate.",
        "",
    ]
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        status, health, _ = _get(client, "/healthz")
        lines.extend(
            [
                "## Service health",
                "",
                f"HTTP `{status}`",
                "",
                "```json",
                _truncate(health, width=1500),
                "```",
                "",
            ]
        )

        lines.extend(
            _example(
                client,
                title="Published statistics",
                path="/v1/statistics",
                note=(
                    "Measured over public records only. Synthetic counts, if any, are "
                    "labelled by the API."
                ),
                width=4000,
            )
        )

        lines.extend(
            _example(
                client,
                title="2024 Census population observations",
                path="/v1/population",
                params={"limit": 5},
                note=(
                    "Saved PSA OpenSTAT snapshots mirrored by BetterGov.PH. Values are "
                    "statistical counts, not facility capacity; missing values remain null."
                ),
                width=6000,
            )
        )

        status, facilities, _ = _get(client, "/v1/facilities", limit=3)
        lines.extend(
            [
                "## Facility examples",
                "",
                f"`GET /v1/facilities?limit=3` returned HTTP `{status}`. The first page is "
                "shown in full; no record was selected or edited by hand.",
                "",
                "```json",
                _truncate(facilities, width=7000),
                "```",
                "",
            ]
        )
        items = facilities.get("items", []) if isinstance(facilities, dict) else []
        if items:
            facility = items[0]
            facility_id = facility.get("id")
            synthetic = facility.get("is_synthetic")
            if synthetic:
                lines.extend(
                    [
                        "> **Warning:** the first public record is marked synthetic. It is "
                        "shown only to prove the response shape and must not be cited as "
                        "government data.",
                        "",
                    ]
                )
            lines.extend(
                _example(
                    client,
                    title=f"Facility detail — {facility.get('display_name', facility_id)}",
                    path=f"/v1/facilities/{facility_id}",
                    width=9000,
                )
            )
            lines.extend(
                _example(
                    client,
                    title="Facility source evidence",
                    path=f"/v1/facilities/{facility_id}/sources",
                    note=(
                        "Evidence is filtered to rights-cleared, published releases. "
                        "Internal-only sources do not appear."
                    ),
                    width=7000,
                )
            )

        lines.extend(
            [
                "## Source and release provenance",
                "",
            ]
        )
        lines.extend(
            _example(
                client,
                title="Dataset catalogue",
                path="/v1/sources",
                note="Rights, publication state, and latest release for every registered dataset.",
                width=9000,
            )
        )
        lines.extend(
            _example(
                client,
                title="Release ledger",
                path="/v1/source-releases",
                params={"limit": 10},
                note="Newest releases first; includes retained blocked and processing releases.",
                width=7000,
            )
        )
        lines.extend(
            _example(
                client,
                title="Latest source checks",
                path="/v1/source-checks",
                params={"limit": 5},
                note="Append-only monitoring evidence, including access blockers.",
                width=5000,
            )
        )
        lines.extend(
            _example(
                client,
                title="Source monitoring summary",
                path="/v1/monitoring",
                width=5000,
            )
        )

        csv_response = client.get("/v1/downloads/facilities.csv")
        csv_lines = csv_response.text.splitlines()
        preview = "\n".join(csv_lines[:4])
        if len(csv_lines) > 4:
            preview += f"\n… ({len(csv_lines) - 1} data rows in this snapshot)"
        lines.extend(
            [
                "## Bulk export",
                "",
                "```http\nGET /v1/downloads/facilities.csv\n```",
                "",
                f"HTTP `{csv_response.status_code}` · "
                f"`{csv_response.headers.get('content-type', 'unknown')}` · "
                f"`{csv_response.headers.get('content-disposition', 'no disposition')}`",
                "",
                "```csv",
                preview,
                "```",
                "",
                "The CSV uses the same publication gate as `/v1/facilities`; it is not a "
                "separate extraction path.",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation",
            "",
            "- These are actual response samples from the local API, not fixtures written "
            "for documentation.",
            "- A record can be present in a retained release and still be absent here if "
            "its rights gate is blocked, internal-only, or quarantined.",
            "- OSM/HOT records are crowd-sourced map features with bbox-centre coordinates "
            "(`map_geocoded`) and unknown operational status; they are not official DOH or "
            "DepEd records.",
            "- Counts in this file describe the captured snapshot, not the national facility "
            "universe.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default=os.environ.get("PHILFACILITIES_API_URL", DEFAULT_API_URL),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    report = build_report(args.api_url.rstrip("/"), timeout=args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output} ({len(report)} bytes)")


if __name__ == "__main__":
    main()
