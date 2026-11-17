"""Filtered HOT/OSM GeoParquet facility layers.

The HOT Philippines extracts include broad OpenStreetMap layers (points of
interest, airports, sea ports and railways). These are crowd-sourced features,
not official registries. This adapter filters each layer to named, qualifying
public-service features and preserves the OSM id, source tags and administrative
codes. Coordinates are bounding-box centres and operational status is unknown.
"""

from __future__ import annotations

import io
from typing import Any

import pyarrow.parquet as pq

from ..contracts import (
    ContactData,
    FacilityCandidate,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from .bettergov import _osm_ownership, _psgc_from_osm, parse_float
from .common import clean_text, has_usable_name

# (tag, value) -> (facility_type, facility_subtype)
POINT_OF_INTEREST_CLASSES: dict[tuple[str, str], tuple[str, str]] = {
    ("amenity", "fire_station"): ("emergency_facility", "FIRE_STATION"),
    ("amenity", "police"): ("emergency_facility", "POLICE_STATION"),
    ("amenity", "townhall"): ("government_office", "LOCAL_GOVERNMENT_OFFICE"),
    ("amenity", "public_building"): ("government_office", "PUBLIC_BUILDING"),
    ("amenity", "post_office"): ("government_office", "POST_OFFICE"),
    ("amenity", "courthouse"): ("justice_facility", "COURTHOUSE"),
    ("amenity", "prison"): ("justice_facility", "PRISON"),
    ("amenity", "marketplace"): ("public_market", "PUBLIC_MARKET"),
    ("amenity", "library"): ("library", "PUBLIC_LIBRARY"),
    ("amenity", "community_centre"): ("community_facility", "COMMUNITY_CENTRE"),
    ("amenity", "social_facility"): ("social_welfare_facility", "SOCIAL_WELFARE_FACILITY"),
    ("amenity", "childcare"): ("social_welfare_facility", "OTHER_SOCIAL_WELFARE_FACILITY"),
    ("amenity", "health_post"): ("health_facility", "OTHER_HEALTH_FACILITY"),
    ("amenity", "arts_centre"): ("cultural_facility", "ARTS_CENTRE"),
    ("amenity", "bus_station"): ("transport_facility", "BUS_STATION"),
    ("tourism", "museum"): ("museum", "MUSEUM"),
    ("tourism", "gallery"): ("cultural_facility", "GALLERY"),
}

AIRPORT_CLASSES: dict[str, tuple[str, str]] = {
    "aerodrome": ("transport_facility", "AIRPORT"),
    "helipad": ("transport_facility", "HELIPORT"),
    "terminal": ("transport_facility", "AIRPORT_TERMINAL"),
}

LAYER_FILES = {
    "points-of-interest": "points_of_interest.parquet",
    "airports": "airports.parquet",
    "sea-ports": "sea_ports.parquet",
    "railways": "railways.parquet",
}


def classify_osm_feature(layer: str, payload: dict[str, Any]) -> tuple[str, str] | None:
    if layer == "points-of-interest":
        for (tag, value), classification in POINT_OF_INTEREST_CLASSES.items():
            if _primary(payload.get(tag)) == value:
                return classification
        return None
    if layer == "airports":
        return AIRPORT_CLASSES.get(_primary(payload.get("aeroway")))
    if layer == "sea-ports":
        if _primary(payload.get("amenity")) == "ferry_terminal":
            return ("transport_facility", "FERRY_TERMINAL")
        if payload.get("port") or payload.get("harbour") or payload.get("industrial") == "port":
            return ("transport_facility", "SEAPORT")
        return None
    if layer == "railways":
        if _primary(payload.get("railway")) in {"station", "halt"}:
            return ("transport_facility", "RAIL_STATION")
        return None
    raise ValueError(f"Unknown OSM facility layer {layer!r}")


def _primary(value: Any) -> str:
    """Return the first semicolon-separated tag value, normalised."""

    text = clean_text(value)
    if not text:
        return ""
    return text.split(";", 1)[0].strip().casefold()


class OsmFacilityLayerAdapter:
    source_code = "osm"
    parser_version = "osm-facility-layer-1.0.0"
    schema_version = "hotosm-phl-geoparquet-v1"

    def __init__(self, spec: ReleaseSpec, *, layer: str) -> None:
        if layer not in LAYER_FILES:
            raise ValueError(f"Unknown OSM facility layer {layer!r}")
        self.spec = spec
        self.layer = layer

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        table = pq.read_table(io.BytesIO(spec.content))
        columns = set(table.column_names)
        missing = {"id", "name", "bbox"} - columns
        if missing:
            raise ValueError(
                f"OSM GeoParquet schema changed: missing columns {sorted(missing)}; "
                f"observed {sorted(columns)}"
            )
        rows: list[ParsedRow] = []
        seen_ids: set[str] = set()
        duplicate_ids = 0
        skipped_unnamed = 0
        for index, record in enumerate(table.to_pylist(), start=1):
            name = clean_text(
                record.get("name") or record.get("name_en") or record.get("name_latin")
            )
            if not has_usable_name(name):
                skipped_unnamed += 1
                continue
            record_key = str(record["id"])
            if record_key in seen_ids:
                duplicate_ids += 1
                continue
            seen_ids.add(record_key)
            classification = classify_osm_feature(self.layer, record)
            if classification is None:
                continue
            lat, lon = _centre(record.get("bbox"))
            payload = {key: value for key, value in record.items() if key != "geom"}
            payload["_facility_type"] = classification[0]
            payload["_facility_subtype"] = classification[1]
            payload["_bbox_center_latitude"] = lat
            payload["_bbox_center_longitude"] = lon
            payload["_source_row"] = index
            rows.append(
                ParsedRow(
                    source_record_key=record_key,
                    row_reference=f"parquet_row:{index}",
                    raw_payload=payload,
                    normalized_payload=payload,
                )
            )
        if not rows:
            raise ValueError(f"OSM {self.layer} layer contained no named qualifying features.")
        warnings = [
            {
                "code": "osm_crowd_sourced",
                "message": (
                    "OpenStreetMap features are crowd-sourced and are not an official "
                    "government registry. Presence is not evidence of opening, licensing "
                    "or current operation."
                ),
            },
            {
                "code": "unnamed_and_nonqualifying_features_skipped",
                "message": (
                    f"{skipped_unnamed} unnamed or punctuation-only features and features "
                    "outside the selected facility tags are retained in the preserved raw "
                    "file but not turned into facility records."
                ),
            },
        ]
        if duplicate_ids:
            warnings.append(
                {
                    "code": "duplicate_osm_id",
                    "message": (
                        f"{duplicate_ids} repeated OSM feature ids were collapsed to their "
                        "first occurrence; the preserved raw file retains every row."
                    ),
                }
            )
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=warnings,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            lat = parse_float(payload.get("_bbox_center_latitude"))
            lon = parse_float(payload.get("_bbox_center_longitude"))
            if not has_usable_name(payload.get("name") or payload.get("name_en")):
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "OSM feature has no usable name.",
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
                        f"Duplicate OSM feature id {row.source_record_key}.",
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
                        "OSM feature has no usable point or bounding box.",
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
                        "OSM coordinate lies outside the Philippines plausibility box.",
                        {"latitude": lat, "longitude": lon},
                        row.row_reference,
                    )
                )
                rejected += 1
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            lat = parse_float(payload.get("_bbox_center_latitude"))
            lon = parse_float(payload.get("_bbox_center_longitude"))
            name = clean_text(payload.get("name") or payload.get("name_en"))
            if lat is None or lon is None or not has_usable_name(name):
                continue
            psgc_code, _psgc_method = _psgc_from_osm(payload)
            address = clean_text(payload.get("addr_full"))
            if not address and payload.get("addr_city"):
                address = clean_text(payload.get("addr_city"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=f"osm:{row.source_record_key}",
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type=payload["_facility_type"],
                    facility_subtype=payload["_facility_subtype"],
                    facility_kind="facility",
                    ownership=_osm_ownership(payload.get("operator_type")),
                    record_status="unknown",
                    location=LocationData(
                        latitude=lat,
                        longitude=lon,
                        precision="map_geocoded",
                        method="openstreetmap_bbox_center",
                        address_text=address,
                        postal_code=_postal_code(payload),
                        psgc_code=psgc_code,
                        review_status="source_supplied",
                    ),
                    contacts=_contacts(payload),
                )
            )
        return candidates


def _contacts(payload: dict[str, Any]) -> list[ContactData]:
    """Return institutional contact tags, preferring the contact:* convention."""

    tags = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
    contacts: list[ContactData] = []
    seen: set[tuple[str, str]] = set()
    for contact_type, fields in (
        ("phone", ("contact:phone", "phone")),
        ("email", ("contact:email", "email")),
        ("website", ("contact:website", "website")),
    ):
        for field in fields:
            value = clean_text(tags.get(field) or payload.get(field))
            if not value:
                continue
            key = (contact_type, value)
            if key in seen:
                continue
            seen.add(key)
            contacts.append(ContactData(contact_type, value, source_field=field))
    opening_hours = clean_text(payload.get("opening_hours") or tags.get("opening_hours"))
    if opening_hours:
        contacts.append(ContactData("opening_hours", opening_hours, source_field="opening_hours"))
    return contacts


def _postal_code(payload: dict[str, Any]) -> str | None:
    tags = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
    return (
        clean_text(tags.get("addr:postcode"))
        or clean_text(payload.get("addr:postcode"))
        or clean_text(payload.get("postal_code"))
        or None
    )


def _centre(bbox: Any) -> tuple[float | None, float | None]:
    if not isinstance(bbox, dict):
        return None, None
    xmin = parse_float(bbox.get("xmin"))
    xmax = parse_float(bbox.get("xmax"))
    ymin = parse_float(bbox.get("ymin"))
    ymax = parse_float(bbox.get("ymax"))
    if None in (xmin, xmax, ymin, ymax):
        return None, None
    return (ymin + ymax) / 2, (xmin + xmax) / 2
