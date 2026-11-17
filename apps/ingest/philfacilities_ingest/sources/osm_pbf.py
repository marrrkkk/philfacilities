"""Filtered facility features from an OpenStreetMap PBF extract.

The HOT GeoParquet layers cover health, education and a small set of
public-service tags.  A Geofabrik PBF contains additional facility-like tags
(government offices, parks, sports venues, DRRM/evacuation sites and healthcare
centres) that are not present in those layers.

This module has two parts:

``extract_pbf_features``
    Stream a local ``.osm.pbf`` snapshot with pyosmium and write a small,
    reproducible Parquet extract containing only named, qualifying features.
    The extract is the preserved release artifact; the upstream PBF URL,
    snapshot name and SHA-256 are recorded in the release notes.

``OsmPbfFacilityAdapter``
    Parse that extract into facility candidates.  The adapter never infers
    ownership, operational status or geography.  Way coordinates are the mean
    of their mapped nodes and are labelled as such.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..contracts import (
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

# Ordered rules: the first matching tag wins.  Specific government tags are
# checked before the generic office=government tag.
PBF_CLASSES: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (("government", "legislative"), ("government_office", "NATIONAL_AGENCY_OFFICE")),
    (("government", "administrative"), ("government_office", "OTHER_GOVERNMENT_OFFICE")),
    (("office", "government"), ("government_office", "OTHER_GOVERNMENT_OFFICE")),
    (("amenity", "townhall"), ("government_office", "LOCAL_GOVERNMENT_OFFICE")),
    (("leisure", "park"), ("public_space", "PUBLIC_PARK")),
    (("leisure", "garden"), ("public_space", "PUBLIC_PARK")),
    (("leisure", "nature_reserve"), ("public_space", "OTHER_PUBLIC_SPACE")),
    (("leisure", "recreation_ground"), ("public_space", "OTHER_PUBLIC_SPACE")),
    (("leisure", "playground"), ("public_space", "PLAYGROUND")),
    (("leisure", "sports_centre"), ("public_space", "SPORTS_COMPLEX")),
    (("leisure", "sports_hall"), ("public_space", "SPORTS_COMPLEX")),
    (("leisure", "stadium"), ("public_space", "SPORTS_COMPLEX")),
    (("leisure", "swimming_pool"), ("public_space", "SPORTS_COMPLEX")),
    (("leisure", "fitness_centre"), ("public_space", "OTHER_PUBLIC_SPACE")),
    (("emergency", "disaster_response"), ("emergency_facility", "DRRM_CENTER")),
    (("emergency", "evacuation_centre"), ("emergency_facility", "EVACUATION_CENTER")),
    (("emergency", "ambulance_station"), ("emergency_facility", "OTHER_EMERGENCY_FACILITY")),
    (("healthcare", "hospital"), ("health_facility", "HOSPITAL")),
    (("healthcare", "clinic"), ("health_facility", "CLINIC")),
    (("healthcare", "health_post"), ("health_facility", "OTHER_HEALTH_FACILITY")),
    (("healthcare", "birthing_centre"), ("health_facility", "BIRTHING_HOME")),
    (("healthcare", "laboratory"), ("health_facility", "LABORATORY")),
    (("amenity", "hospital"), ("health_facility", "HOSPITAL")),
    (("amenity", "clinic"), ("health_facility", "CLINIC")),
    (("amenity", "health_post"), ("health_facility", "OTHER_HEALTH_FACILITY")),
    (("amenity", "police"), ("emergency_facility", "POLICE_STATION")),
    (("amenity", "fire_station"), ("emergency_facility", "FIRE_STATION")),
    (("amenity", "courthouse"), ("justice_facility", "COURT")),
    (("amenity", "prison"), ("justice_facility", "JAIL")),
    (("amenity", "marketplace"), ("public_market", "PUBLIC_MARKET")),
    (("amenity", "library"), ("library", "PUBLIC_LIBRARY")),
    (("amenity", "community_centre"), ("community_facility", "COMMUNITY_CENTER")),
    (("amenity", "social_facility"), ("social_welfare_facility", "SOCIAL_WELFARE_FACILITY")),
    (("amenity", "childcare"), ("social_welfare_facility", "OTHER_SOCIAL_WELFARE_FACILITY")),
    (("amenity", "arts_centre"), ("cultural_facility", "ARTS_CENTRE")),
    (("amenity", "bus_station"), ("transport_facility", "LAND_TERMINAL")),
    (("amenity", "post_office"), ("government_office", "POST_OFFICE")),
    (("tourism", "museum"), ("museum", "OTHER_MUSEUM")),
    (("tourism", "gallery"), ("cultural_facility", "OTHER_CULTURAL_FACILITY")),
)

PBF_TAG_KEYS = (
    "government",
    "office",
    "leisure",
    "emergency",
    "healthcare",
    "amenity",
    "tourism",
)


def classify_pbf_feature(tags: dict[str, Any]) -> tuple[str, str] | None:
    """Return the canonical category/subtype for one OSM tag set."""

    for (key, value), classification in PBF_CLASSES:
        raw = clean_text(tags.get(key))
        if raw and raw.split(";", 1)[0].strip().casefold() == value:
            return classification
    return None


def _name(tags: dict[str, Any]) -> str | None:
    name = clean_text(
        tags.get("name") or tags.get("name:en") or tags.get("name:fil") or tags.get("official_name")
    )
    return name if has_usable_name(name) else None


def extract_pbf_features(
    pbf_path: str | Path,
    output_path: str | Path,
    *,
    source_url: str | None = None,
    source_sha256: str | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """Extract named qualifying features from a local OSM PBF snapshot.

    Requires ``osmium`` (pyosmium).  It is imported lazily so the normal test
    suite and Parquet adapter do not need the compiled dependency.
    """

    try:
        import osmium
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "PBF extraction requires pyosmium. Install it with "
            "`uv add --project apps/ingest osmium`."
        ) from exc

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped_unnamed = 0
    skipped_relation = 0
    counts: Counter[str] = Counter()

    processor = (
        osmium.FileProcessor(str(pbf_path))
        .with_filter(osmium.filter.KeyFilter(*PBF_TAG_KEYS))
        .with_locations()
    )
    for obj in processor:
        tags = dict(obj.tags)
        classification = classify_pbf_feature(tags)
        if classification is None:
            continue
        name = _name(tags)
        if not name:
            skipped_unnamed += 1
            continue
        if obj.is_relation():
            skipped_relation += 1
            continue
        if obj.is_node():
            latitude = obj.location.lat
            longitude = obj.location.lon
            geometry_type = "node"
            method = "openstreetmap_pbf_node"
        elif obj.is_way():
            coordinates = [
                (node.location.lat, node.location.lon)
                for node in obj.nodes
                if node.location.valid()
            ]
            if not coordinates:
                continue
            latitude = sum(point[0] for point in coordinates) / len(coordinates)
            longitude = sum(point[1] for point in coordinates) / len(coordinates)
            geometry_type = "way"
            method = "openstreetmap_pbf_way_node_mean"
        else:
            continue
        # pyosmium uses "n"/"w" for type_str(); OSM extracts and the existing
        # OSM source links use "node/…" and "way/…".  The exact prefix is part
        # of the source entity key and must match to avoid duplicate facilities.
        record_key = f"{'node' if obj.is_node() else 'way'}/{obj.id}"
        if record_key in seen:
            continue
        seen.add(record_key)
        counts[f"{classification[0]}/{classification[1]}"] += 1
        records.append(
            {
                "id": record_key,
                "name": name,
                "name_en": clean_text(tags.get("name:en")),
                "tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
                "latitude": latitude,
                "longitude": longitude,
                "geometry_type": geometry_type,
                "coordinate_method": method,
                "source_url": source_url,
                "source_sha256": source_sha256,
            }
        )
        if progress is not None and len(records) % 5000 == 0:
            progress(len(records))

    if not records:
        raise ValueError("PBF extract contained no named qualifying features.")

    table = pa.Table.from_pylist(records)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression="zstd")
    return {
        "features": len(records),
        "skipped_unnamed": skipped_unnamed,
        "skipped_relation": skipped_relation,
        "by_classification": dict(sorted(counts.items())),
        "output": str(output),
        "output_bytes": output.stat().st_size,
    }


class OsmPbfFacilityAdapter:
    source_code = "osm"
    parser_version = "osm-pbf-facility-1.0.0"
    schema_version = "osm-pbf-filtered-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        table = pq.read_table(io.BytesIO(spec.content))
        columns = set(table.column_names)
        missing = {"id", "name", "latitude", "longitude", "tags_json"} - columns
        if missing:
            raise ValueError(
                f"OSM PBF extract schema changed: missing columns {sorted(missing)}; "
                f"observed {sorted(columns)}"
            )
        rows: list[ParsedRow] = []
        seen: set[str] = set()
        duplicate_ids = 0
        skipped_classification = 0
        for index, record in enumerate(table.to_pylist(), start=1):
            record_key = str(record["id"])
            if record_key in seen:
                duplicate_ids += 1
                continue
            seen.add(record_key)
            try:
                tags = json.loads(record["tags_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                tags = {}
            classification = classify_pbf_feature(tags)
            if classification is None:
                skipped_classification += 1
                continue
            payload = {
                "id": record_key,
                "name": clean_text(record.get("name")),
                "name_en": clean_text(record.get("name_en")),
                "tags": tags,
                "latitude": parse_float(record.get("latitude")),
                "longitude": parse_float(record.get("longitude")),
                "geometry_type": record.get("geometry_type"),
                "coordinate_method": record.get("coordinate_method"),
                "source_url": record.get("source_url"),
                "source_sha256": record.get("source_sha256"),
                "_facility_type": classification[0],
                "_facility_subtype": classification[1],
                "_source_row": index,
            }
            rows.append(
                ParsedRow(
                    source_record_key=record_key,
                    row_reference=f"pbf_feature:{record_key}",
                    raw_payload=payload,
                    normalized_payload=payload,
                )
            )
        if not rows:
            raise ValueError("OSM PBF extract contained no qualifying facilities.")
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
                "code": "pbf_derived_extract",
                "message": (
                    "The preserved artifact is a filtered extract of a Geofabrik "
                    "Philippines PBF snapshot. The upstream snapshot URL and SHA-256 "
                    "are retained in feature metadata."
                ),
            },
            {
                "code": "way_coordinates_are_node_means",
                "message": (
                    "Way coordinates are the arithmetic mean of mapped nodes, not a "
                    "surveyed building or entrance location. Relation features are "
                    "not extracted."
                ),
            },
        ]
        if duplicate_ids:
            warnings.append(
                {
                    "code": "duplicate_osm_id",
                    "message": (
                        f"{duplicate_ids} repeated OSM feature ids were collapsed to their "
                        "first occurrence; the preserved extract retains every row."
                    ),
                }
            )
        if skipped_classification:
            warnings.append(
                {
                    "code": "nonqualifying_features_skipped",
                    "message": (
                        f"{skipped_classification} extracted features no longer matched the "
                        "classifier and were skipped."
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
            lat = parse_float(payload.get("latitude"))
            lon = parse_float(payload.get("longitude"))
            if not has_usable_name(payload.get("name")):
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
                        "OSM feature has no usable coordinate.",
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
            tags = payload.get("tags") or {}
            lat = parse_float(payload.get("latitude"))
            lon = parse_float(payload.get("longitude"))
            name = clean_text(payload.get("name"))
            if lat is None or lon is None or not has_usable_name(name):
                continue
            psgc_code, _psgc_method = _psgc_from_osm(tags)
            address = clean_text(tags.get("addr:full"))
            if not address:
                address_parts = [
                    clean_text(tags.get("addr:housenumber")),
                    clean_text(tags.get("addr:street")),
                    clean_text(tags.get("addr:city")),
                ]
                address = ", ".join(part for part in address_parts if part) or None
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=f"osm:{row.source_record_key}",
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type=payload["_facility_type"],
                    facility_subtype=payload["_facility_subtype"],
                    facility_kind="facility",
                    ownership=_osm_ownership(tags.get("operator_type")),
                    record_status="unknown",
                    location=LocationData(
                        latitude=lat,
                        longitude=lon,
                        precision="map_geocoded",
                        method=payload.get("coordinate_method") or "openstreetmap_pbf",
                        address_text=address,
                        psgc_code=psgc_code,
                        review_status="source_supplied",
                    ),
                )
            )
        return candidates
