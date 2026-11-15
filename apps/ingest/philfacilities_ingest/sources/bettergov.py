"""Connectors for BetterGov.PH's public open-data and classification services.

Two distinct source families are represented here:

* Open Data Portal facility extracts. Dataset 35 is the HOT/OpenStreetMap health
  facility extract (ODbL); dataset 36 is the HOT/OpenStreetMap education extract
  (ODbL). They are crowd-sourced map features, not official government registries.
* The PSGC classification snapshot. It is a BetterGov mirror of a PSA PSGC
  release, not the latest official PSA workbook. It is loaded as a clearly
  labelled supplementary geography release.
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from typing import Any

import pyarrow.parquet as pq

from ..contracts import (
    FacilityCandidate,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    SchoolData,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text, parse_float
from .psgc import ParsedUnit


def _centre(bbox: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not bbox:
        return None, None
    try:
        return (
            (float(bbox["ymin"]) + float(bbox["ymax"])) / 2,
            (float(bbox["xmin"]) + float(bbox["xmax"])) / 2,
        )
    except (KeyError, TypeError, ValueError):
        return None, None


def _psgc_from_osm(row: dict[str, Any]) -> tuple[str | None, str]:
    """Map OSM administrative codes to a PSGC-shaped code where possible.

    HOT uses P-codes (``PH1705304001``). Stripping the country prefix yields
    the 10-digit PSGC-shaped barangay code for most rows. This is a
    supplementary crosswalk, not proof that the OSM feature is inside the
    official PSGC boundary.
    """

    for field in ("adm4_pcode", "adm3_pcode", "adm2_pcode"):
        value = row.get(field)
        if not value:
            continue
        digits = re.sub(r"\D", "", str(value))
        if field == "adm4_pcode" and len(digits) >= 10:
            return digits[-10:], "osm_admin_code_adm4"
        if field == "adm3_pcode" and len(digits) >= 7:
            return digits[-7:] + "000", "osm_admin_code_adm3"
        if field == "adm2_pcode" and len(digits) >= 5:
            return digits[-5:] + "00000", "osm_admin_code_adm2"
    return None, "no_osm_admin_code"


def _osm_ownership(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"government", "public", "state"}:
        return "government"
    if normalized in {"private", "ngo", "religious", "business"}:
        return "private"
    return "unknown"


def _primary_value(value: Any, *, limit: int = 80) -> str | None:
    """Return the first source value and fit the normalized subtype column.

    OSM commonly stores several ``healthcare`` values in one semicolon-separated
    string. The raw payload keeps the full value; the canonical subtype uses the
    first value so a display label never exceeds the normalized column.
    """

    text = clean_text(value)
    if not text:
        return None
    primary = re.split(r"[;,]", text)[0].strip()
    return primary[:limit] or None


class OSMParquetAdapter:
    """Parse one HOT/OSM GeoParquet extract into canonical facility rows."""

    source_code = "osm"
    parser_version = "osm-geoparquet-1.0.0"
    schema_version = "hotosm-phl-geoparquet-v1"
    expected_columns = {"required": {"id", "name", "bbox"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec, *, facility_domain: str) -> None:
        self.spec = spec
        self.facility_domain = facility_domain
        self._rows: list[dict[str, Any]] = []

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        table = pq.read_table(io.BytesIO(spec.content))
        columns = set(table.column_names)
        missing = self.expected_columns["required"] - columns
        if missing:
            raise ValueError(
                f"OSM GeoParquet schema changed: missing columns {sorted(missing)}; "
                f"observed {sorted(columns)}"
            )
        rows: list[ParsedRow] = []
        for index, record in enumerate(table.to_pylist(), start=1):
            name = clean_text(
                record.get("name") or record.get("name_en") or record.get("name_latin")
            )
            # An unnamed map feature cannot be presented as a named facility.
            # The raw Parquet file is preserved; only named features become
            # publication candidates.
            if not name:
                continue
            payload = {key: value for key, value in record.items() if key != "geom"}
            lat, lon = _centre(record.get("bbox"))
            payload["_bbox_center_latitude"] = lat
            payload["_bbox_center_longitude"] = lon
            payload["_source_row"] = index
            rows.append(
                ParsedRow(
                    source_record_key=str(record["id"]),
                    row_reference=f"parquet_row:{index}",
                    raw_payload=payload,
                    normalized_payload=payload,
                )
            )
        if not rows:
            raise ValueError("OSM GeoParquet contained no named facility features.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "unnamed_features_skipped",
                    "message": (
                        "Unnamed OSM features are retained in the preserved raw file but are "
                        "not turned into named facility records."
                    ),
                }
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            lat = parse_float(payload.get("_bbox_center_latitude"))
            lon = parse_float(payload.get("_bbox_center_longitude"))
            if not clean_text(payload.get("name")):
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "OSM feature has no usable name",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_osm_id",
                        "error",
                        f"Duplicate OSM feature id {row.source_record_key}",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(row.source_record_key)
            if lat is None or lon is None:
                issues.append(
                    ValidationIssue(
                        "missing_coordinate",
                        "error",
                        "OSM feature has no usable point or bounding box",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not (4.0 <= lat <= 21.6 and 115.5 <= lon <= 127.5):
                issues.append(
                    ValidationIssue(
                        "coordinate_outside_philippines_bbox",
                        "error",
                        "OSM coordinate lies outside the Philippines plausibility box",
                        {"latitude": lat, "longitude": lon},
                        row.row_reference,
                    )
                )
                rejected += 1
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            lat = parse_float(payload.get("_bbox_center_latitude"))
            lon = parse_float(payload.get("_bbox_center_longitude"))
            if lat is None or lon is None:
                continue
            name = clean_text(payload.get("name") or payload.get("name_en"))
            if not name:
                continue
            if self.facility_domain == "health":
                subtype = _primary_value(payload.get("healthcare")) or _primary_value(
                    payload.get("amenity")
                )
                school = None
                facility_type = "health_facility"
            else:
                subtype = _primary_value(payload.get("amenity")) or _primary_value(
                    payload.get("building")
                )
                school = SchoolData()
                facility_type = "school"
            psgc_code, psgc_method = _psgc_from_osm(payload)
            address = clean_text(payload.get("addr_full"))
            if not address and payload.get("addr_city"):
                address = clean_text(payload.get("addr_city"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=f"osm:{row.source_record_key}",
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type=facility_type,
                    facility_subtype=subtype,
                    ownership=_osm_ownership(payload.get("operator_type")),
                    # A mapped feature is not evidence that a facility is open,
                    # licensed, or operating. Never infer operational status.
                    record_status="unknown",
                    location=LocationData(
                        latitude=lat,
                        longitude=lon,
                        precision="map_geocoded",
                        method="openstreetmap_bbox_center",
                        address_text=address,
                        psgc_code=psgc_code,
                        review_status="source_supplied",
                    ),
                    school=school,
                    health=None,
                )
            )
            if psgc_code:
                payload["_psgc_crosswalk_method"] = psgc_method
        return candidates


def parse_psgc_api_payload(
    payload: dict[str, list[dict[str, Any]]],
) -> tuple[list[ParsedUnit], list[str]]:
    """Turn the BetterGov PSGC API collections into release-scoped units."""

    warnings: list[str] = []
    units: list[ParsedUnit] = []
    level_map = {
        "Reg": "region",
        "Prov": "province",
        # BetterGov returns highly urbanised and independent cities in the
        # provinces collection with geographic_level "City". They sit at the
        # city/municipality level in the PSGC hierarchy.
        "City": "municipality",
        "Mun": "municipality",
        "SubMun": "municipality",
        "Bgy": "barangay",
    }
    by_code: dict[str, ParsedUnit] = {}
    for collection in ("regions", "provinces", "municipalities", "barangays"):
        for row in payload.get(collection, []):
            raw_code = str(row.get("code") or "")
            code = re.sub(r"\D", "", raw_code).zfill(10)[-10:]
            if not code:
                continue
            level = level_map.get(str(row.get("geographic_level") or ""))
            if level is None:
                warnings.append(f"unknown PSGC level {row.get('geographic_level')!r}; skipped")
                continue
            unit = ParsedUnit(
                psgc_code=code,
                name=clean_text(row.get("area_name")) or code,
                geographic_level=level,
                parent_psgc_code=None,
                correspondence_code=clean_text(row.get("correspondence_code")),
                old_name=clean_text(row.get("old_name")),
                city_class=clean_text(row.get("city_class")),
                income_classification=clean_text(row.get("income_classification")),
                urban_rural=clean_text(row.get("urban_rural")),
                island_region=clean_text(row.get("island_region")),
                raw_payload={key: value for key, value in row.items() if key != "populations"},
                sheet="bettergov-psgc-api",
                row=len(units) + 1,
            )
            units.append(unit)
            by_code[code] = unit

    for unit in units:
        code = unit.psgc_code
        if unit.geographic_level == "region":
            unit.parent_psgc_code = None
            continue
        if unit.geographic_level == "province":
            parent = code[:2] + "00000000"
        elif unit.geographic_level == "municipality":
            # Highly urbanised and independent cities are not under a province.
            if (unit.city_class or "").upper() in {"HUC", "ICC"}:
                parent = code[:2] + "00000000"
            else:
                parent = code[:5] + "00000"
                if parent not in by_code:
                    parent = code[:2] + "00000000"
        else:
            parent = code[:7] + "000"
            if parent not in by_code:
                parent = code[:5] + "00000"
        unit.parent_psgc_code = parent if parent in by_code else None
        if unit.parent_psgc_code is None:
            warnings.append(f"{unit.geographic_level} {code} has no resolvable parent")
    return units, warnings


def build_psgc_release_payload(
    *,
    version: str,
    fetched_at: str,
    collections: dict[str, list[dict[str, Any]]],
) -> bytes:
    document = {
        "source": "https://statistics.bettergov.ph/api/classification/psgc",
        "psa_source": "https://classification.psa.gov.ph",
        "snapshot": version,
        "fetched_at": fetched_at,
        "warning": (
            "BetterGov mirror of a PSA PSGC release. Not the latest official PSA workbook; "
            "use PSA for authoritative legal/administrative codes."
        ),
        "collections": collections,
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def load_psgc_release_payload(content: bytes) -> dict[str, list[dict[str, Any]]]:
    document = json.loads(content)
    return document.get("collections", document)


def parse_date_basis(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
