"""MRT-3 station directory connector.

The official MRT-3 site publishes a station carousel with 13 station names and
short landmark descriptions. The page is not a current operations feed and its
labels may be stale, so this adapter preserves the source names verbatim and
does not infer coordinates, addresses, opening dates or operating status.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any

from ..acquisition import HttpAcquirer
from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text

MRT3_STATIONS_URL = "https://www.mrt3.com/index.php/menu-stations"
STATION_RE = re.compile(
    r'<li\b[^>]*class=["\'][^"\']*\bstation\b[^"\']*["\'][^>]*>(?P<name>.*?)</li>',
    re.S | re.I,
)
TAG_RE = re.compile(r"<[^>]+>")
DESCRIPTION_RE = re.compile(
    r'<div\s+class=["\']carousel-caption station-caption["\']>\s*<h2>(?P<body>.*?)</h2>',
    re.S | re.I,
)
DATE_MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def parse_station_page(document: str) -> list[dict[str, Any]]:
    names = [clean_text(_clean(match.group("name"))) for match in STATION_RE.finditer(document)]
    descriptions = [
        clean_text(_clean(match.group("body"))) for match in DESCRIPTION_RE.finditer(document)
    ]
    records = []
    for index, name in enumerate(names):
        if not name:
            continue
        records.append(
            {
                "station_name": name,
                "landmark_description": descriptions[index] if index < len(descriptions) else None,
                "source_position": index + 1,
                "derived_from": "official MRT-3 station carousel",
            }
        )
    return records


def _fetch_published_date(document: str) -> datetime | None:
    match = DATE_MODIFIED_RE.search(document)
    if not match:
        return None
    try:
        value = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def fetch_mrt3_stations(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    result = acquirer.fetch(MRT3_STATIONS_URL)
    if result.status_code >= 400 or result.error:
        raise ValueError(f"MRT-3 station page request failed: HTTP {result.status_code}")
    document = result.content.decode("utf-8", "replace")
    published = _fetch_published_date(document)
    return result.content, {
        "url": MRT3_STATIONS_URL,
        "status_code": result.status_code,
        "sha256": result.sha256,
        "content_type": result.content_type,
        "date_modified": published.isoformat() if published else None,
    }


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper() or "UNNAMED"


class Mrt3StationAdapter:
    source_code = "dotr"
    parser_version = "mrt3-station-html-1.0.0"
    schema_version = "mrt3-station-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        document = spec.content.decode("utf-8", "replace")
        records = parse_station_page(document)
        if not records:
            raise ValueError("MRT-3 station page contained no station names.")
        rows = [
            ParsedRow(
                source_record_key=f"MRT3:{_slug(record['station_name'])}",
                row_reference=f"mrt3-station:{record['source_position']}",
                raw_payload=record,
                normalized_payload=record,
            )
            for record in records
        ]
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "station_names_verbatim_may_be_stale",
                    "message": (
                        "Station names are preserved exactly as published by the MRT-3 site; "
                        "some labels predate later renamings. No current-name mapping is inferred."
                    ),
                },
                {
                    "code": "no_coordinates_or_operating_status",
                    "message": (
                        "The station page supplies landmark descriptions but no coordinates, "
                        "addresses, opening dates or operating status. Stations remain unmapped "
                        "and their operational state is unknown."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            name = clean_text(row.normalized_payload.get("station_name"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_station_name",
                        "fatal",
                        "MRT-3 station row has no station name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_station",
                        "error",
                        f"MRT-3 station {name} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(row.source_record_key)
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("station_name"))
            if not name:
                continue
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=f"MRT3:{_slug(name)}",
                    row_reference=row.row_reference,
                    display_name=f"{name} MRT Station",
                    facility_type="transport_facility",
                    facility_subtype="MRT_STATION",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOVERNMENT_UNSPECIFIED",
                    operator_type="GOVERNMENT_UNSPECIFIED",
                    public_access_class="PUBLIC_PAID_OR_CONDITIONAL",
                    record_status="unknown",
                    location=LocationData(
                        precision="unknown",
                        method=None,
                        address_text="EDSA, Metro Manila",
                    ),
                    functions=[
                        FunctionData(
                            function_code="RAIL_TRANSPORT",
                            source_value="MRT-3 station",
                            designation_status="source_listed",
                            evidence={
                                "source": "MRT-3 official station page",
                                "landmark_description": payload.get("landmark_description"),
                                "source_position": payload.get("source_position"),
                                "name_derivation": payload.get("derived_from"),
                            },
                        )
                    ],
                )
            )
        return candidates
