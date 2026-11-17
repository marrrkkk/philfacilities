"""PAGASA automated-weather-station (AWS) network adapter.

The public PAGASA AWS page is a server-rendered table of station identifiers,
station names, current readings and a per-station "Last Updated" value. It is a
live operational page, not a dated downloadable station inventory. This adapter
therefore preserves the page as a dated acquisition artifact and publishes only
the factual station identity (site ID, site name and the source last-updated
value). The readings remain in the private artifact as acquisition evidence and
are not presented as a real-time weather service or as a facility attribute.

The page supplies no coordinates, PSGC codes, station ownership, operator,
commissioning date or access rules. PAGASA is a national government agency, so
the station is classified as a national-government environmental monitoring
facility. Presence on the page is not treated as proof that a station is
currently operational or publicly accessible.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from ..acquisition import AcquisitionError, HttpAcquirer
from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    RoleData,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text, normalise_code

AWS_URL = "https://bagong.pagasa.dost.gov.ph/automated-weather-station"
PUBLIC_FIELDS = ("site_id", "site_name", "last_updated")
READING_COLUMNS = (
    "Temperature",
    "Humidity",
    "Wind Speed",
    "Wind Direction",
    "Precipitation",
    "Pressure",
    "Solar Radiation",
)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_table = False
        self._tables = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._tables += 1
            self._in_table = self._tables == 1
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(clean_text(" ".join(self._cell)) or "")
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._in_table:
            self._in_table = False


def parse_aws_html(html: str) -> tuple[list[str], list[dict[str, str]]]:
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return [], []
    header = [clean_text(cell) or "" for cell in parser.rows[0]]
    if "Site ID" not in header or "Site Name" not in header:
        raise ValueError(
            "PAGASA AWS page did not contain the expected Site ID/Site Name table header; "
            "the page structure or access state changed."
        )
    records: list[dict[str, str]] = []
    for cells in parser.rows[1:]:
        if len(cells) < len(header):
            continue
        records.append({header[i]: cells[i] for i in range(len(header))})
    return header, records


def fetch_pagasa_aws(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    result = acquirer.fetch(AWS_URL, max_bytes=10 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"PAGASA AWS page returned HTTP {result.status_code}.", result=result
        )
    header, source_rows = parse_aws_html(result.content.decode("utf-8", errors="replace"))
    if not source_rows:
        raise AcquisitionError("PAGASA AWS page returned no station rows.", result=result)

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(source_rows, start=1):
        site_id = normalise_code(row.get("Site ID"))
        site_name = clean_text(row.get("Site Name"))
        if not site_id or not site_name or site_id in seen:
            continue
        seen.add(site_id)
        readings = {
            column: clean_text(row.get(column))
            for column in READING_COLUMNS
            if clean_text(row.get(column))
        }
        records.append(
            {
                "site_id": site_id,
                "site_name": site_name,
                "readings": readings,
                "last_updated": clean_text(row.get("Last Updated")),
                "row_reference": f"pagasa-aws-html:{index}",
            }
        )

    if not records:
        raise AcquisitionError("PAGASA AWS page returned no usable station records.")

    artifact = {
        "source_url": AWS_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_columns": header,
        "record_count": len(records),
        "note": (
            "Dated acquisition artifact of the live PAGASA automated-weather-station "
            "page. Readings are retained as evidence but are not republished as current "
            "weather or as facility attributes. The page supplies no coordinates, "
            "PSGC codes, station ownership, commissioning date or access rules."
        ),
        "records": records,
    }
    metadata = {
        "retrieved_at": artifact["retrieved_at"],
        "records": len(records),
        "source_url": AWS_URL,
        "source_columns": header,
    }
    return json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8"), metadata


class PagasaAwsAdapter:
    source_code = "pagasa"
    parser_version = "pagasa-aws-html-1.0.0"
    schema_version = "pagasa-aws-html-v1"
    expected_columns = {"required": {"Site ID", "Site Name", "Last Updated"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content)
        except json.JSONDecodeError as exc:
            raise ValueError("PAGASA AWS release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("PAGASA AWS artifact contains no records.")
        rows: list[ParsedRow] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            site_id = normalise_code(record.get("site_id"))
            site_name = clean_text(record.get("site_name"))
            if not site_id or not site_name:
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            rows.append(
                ParsedRow(
                    source_record_key=f"PAGASA-AWS:{site_id}",
                    row_reference=str(record.get("row_reference") or f"pagasa-aws:{site_id}"),
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("PAGASA AWS artifact contained no usable station records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "no_coordinates",
                    "message": (
                        "The PAGASA AWS table supplies station identifiers and names but "
                        "no coordinates or PSGC codes. Stations remain unmapped until an "
                        "authorized coordinate source is used."
                    ),
                },
                {
                    "code": "readings_not_republished",
                    "message": (
                        "Temperature, humidity, wind, precipitation, pressure and solar "
                        "radiation readings are retained in the private acquisition "
                        "artifact only; they are not treated as current weather or as "
                        "facility attributes."
                    ),
                },
                {
                    "code": "directory_not_operational_status",
                    "message": (
                        "Page presence and a source last-updated value are not proof that "
                        "a station is currently operational or publicly accessible."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("site_name"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_site_name",
                        "fatal",
                        "A PAGASA AWS row has no site name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_site_id",
                        "error",
                        f"PAGASA AWS station key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if not clean_text(payload.get("last_updated")):
                issues.append(
                    ValidationIssue(
                        "missing_last_updated",
                        "warning",
                        f"PAGASA AWS station {name} has no source last-updated value.",
                        row_reference=row.row_reference,
                    )
                )
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            site_id = normalise_code(payload.get("site_id"))
            site_name = clean_text(payload.get("site_name"))
            if not site_id or not site_name:
                continue
            last_updated = clean_text(payload.get("last_updated"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=site_name[:300],
                    facility_type="environmental_monitoring",
                    facility_subtype="WEATHER_STATION",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    access_conditions=(
                        "PAGASA automated weather station. The public page does not state "
                        "whether the site permits visitor access."
                    ),
                    record_status="unknown",
                    location=LocationData(address_text=None, precision="unknown"),
                    functions=[
                        FunctionData(
                            function_code="ENVIRONMENTAL_MONITORING",
                            source_value="Automated weather station",
                            designation_status="unknown",
                            evidence={
                                "source": "PAGASA automated-weather-station page",
                                "site_id": site_id,
                                "source_last_updated": last_updated,
                            },
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OPERATOR",
                            entity_name=(
                                "Philippine Atmospheric, Geophysical and Astronomical "
                                "Services Administration (PAGASA)"
                            ),
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "Official PAGASA AWS page"},
                        )
                    ],
                )
            )
        return candidates
