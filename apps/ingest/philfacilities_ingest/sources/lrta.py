"""LRTA Line 1 and Line 2 station distances.

The Light Rail Transit Authority publishes a public page with interval
distances for Line 1 and Line 2. The page lists station *pairs*, not a station
inventory and not coordinates. This adapter derives the unique station names
from the interval table, keeps the adjacent interval distances as evidence and
labels the name derivation explicitly. No coordinates, opening status or
building-level location is inferred.

The page's own modified date is preserved as the release date basis when it can
be read from the embedded schema metadata; otherwise the retrieval date is used.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
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

DISTANCE_URL = "https://www.lrta.gov.ph/distance-between-stations/"
TABLE_RE = re.compile(r"<table\b(?P<attrs>[^>]*)>(?P<body>.*?)</table>", re.S | re.I)
ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh]\b[^>]*>(?P<body>.*?)</t[dh]>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
TOTAL_RE = re.compile(r"^TOTAL\s+DISTANCE$", re.I)


def _clean(value: str) -> str:
    text = TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _line_name(attrs: str) -> str | None:
    lowered = attrs.lower()
    if "distance-stn-l1" in lowered:
        return "Line 1"
    if "distance-stn" in lowered:
        return "Line 2"
    return None


def parse_distance_page(document: str) -> list[dict[str, Any]]:
    """Return one record per unique station with adjacent interval evidence."""

    stations: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for table in TABLE_RE.finditer(document):
        line = _line_name(table.group("attrs"))
        if line is None:
            continue
        previous_station: str | None = None
        for row in ROW_RE.finditer(table.group("body")):
            cells = [_clean(cell.group("body")) for cell in CELL_RE.finditer(row.group("body"))]
            if len(cells) < 2 or TOTAL_RE.match(cells[0]) or not cells[0]:
                continue
            label = cells[0].replace("*", "").strip()
            if " - " not in label:
                continue
            left, right = (part.strip() for part in label.split(" - ", 1))
            if not left or not right:
                continue
            try:
                meters = int(cells[1].replace(",", ""))
            except ValueError:
                meters = None
            for name in (left, right):
                key = (line, name.casefold())
                if key not in stations:
                    stations[key] = {
                        "line": line,
                        "station_name": name,
                        "intervals": [],
                        "derived_from": "adjacent station-pair distance table",
                    }
                    order.append(key)
                stations[key]["intervals"].append(
                    {
                        "from": left,
                        "to": right,
                        "meters": meters,
                        "kilometers": cells[2] if len(cells) > 2 else None,
                    }
                )
            previous_station = right
        if previous_station:
            # Retain the last name only to make the loop observable in debugging.
            stations[(line, previous_station.casefold())]["terminal"] = True
    return [stations[key] for key in order]


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper() or "UNNAMED"


def _record_key(line: str, station: str) -> str:
    return f"LRTA:{line.upper().replace(' ', '-')}:{_slug(station)}"


def fetch_distance_page(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    result = acquirer.fetch(DISTANCE_URL)
    if result.status_code >= 400 or result.error:
        raise ValueError(f"LRTA distance page request failed: HTTP {result.status_code}")
    published = None
    match = re.search(r'"dateModified":"([^"]+)"', result.content.decode("utf-8", "replace"))
    if match:
        try:
            published = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
        except ValueError:
            published = None
    return result.content, {
        "url": DISTANCE_URL,
        "status_code": result.status_code,
        "sha256": result.sha256,
        "content_type": result.content_type,
        "date_modified": published.isoformat() if published else None,
    }


class LrtaStationAdapter:
    source_code = "lrta"
    parser_version = "lrta-distance-html-1.0.0"
    schema_version = "lrta-distance-html-v1"
    expected_columns = {"required": {"station_name", "line"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            document = spec.content.decode("utf-8", "replace")
        except UnicodeDecodeError as exc:
            raise ValueError("LRTA distance page is not decodable text.") from exc
        records = parse_distance_page(document)
        if not records:
            raise ValueError("LRTA page contained no station-pair distance rows.")
        rows = [
            ParsedRow(
                source_record_key=_record_key(record["line"], record["station_name"]),
                row_reference=f"lrta-distance:{record['line']}:{record['station_name']}",
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
                    "code": "station_names_derived_from_intervals",
                    "message": (
                        "The source publishes station-pair distances, not a station list. "
                        "Unique station names were derived from the interval labels; the "
                        "raw intervals are retained in each record."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The page supplies no coordinates, addresses, opening dates or "
                        "operating status. Stations remain unmapped and their operational "
                        "state is unknown."
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
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_station_name",
                        "fatal",
                        "LRTA station row has no station name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_station",
                        "error",
                        f"LRTA station {key} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            intervals = row.normalized_payload.get("intervals") or []
            if not intervals:
                issues.append(
                    ValidationIssue(
                        "no_interval_evidence",
                        "warning",
                        f"{name} has no adjacent interval evidence.",
                        row_reference=row.row_reference,
                    )
                )
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
            line = clean_text(payload.get("line"))
            if not name:
                continue
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=f"{name} LRT Station",
                    facility_type="transport_facility",
                    facility_subtype="LRT_STATION",
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
                        address_text=f"{line}, Metro Manila",
                    ),
                    functions=[
                        FunctionData(
                            function_code="RAIL_TRANSPORT",
                            source_value=f"{line} station",
                            designation_status="source_listed",
                            evidence={
                                "source": "LRTA Distance Between Stations — Line 1 and 2",
                                "line": line,
                                "intervals": payload.get("intervals"),
                                "name_derivation": payload.get("derived_from"),
                            },
                        )
                    ],
                )
            )
        return candidates
