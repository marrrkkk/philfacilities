"""NHA GeoServer WFS — Department of Health facility layer.

The National Housing Authority publishes a public GeoServer workspace
(``NHA_PH``) that includes a layer named ``DOH HF``. It is an official alternate
route for the blocked DOH National Health Facility Registry, but it is *not* the
NHFR: the layer is partial, uses the older ARMM PSGC series for that region, and
does not state an operating status, licence date or complete field dictionary.

The adapter preserves the source labels, facility code, ownership label, PSGC
labels/codes, coordinates and the source's own ``prec_latlo`` precision flag. It
never infers a licence, operating status or building-level precision.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from ..contracts import (
    FacilityCandidate,
    FunctionData,
    HealthData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from ..validators import coordinate_in_philippines
from .common import clean_text

SOURCE_URL = (
    "https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=NHA_PH:DOH%20HF&outputFormat=application/json"
)
PUBLIC_FIELDS = (
    "fac_code",
    "fac_name",
    "fac_type",
    "ownershp",
    "reg_name",
    "reg_psgc",
    "prov_name",
    "prov_psgc",
    "municity",
    "muni_psgc",
    "brgy_name",
    "brgy_psgc",
    "zip_code",
    "latitude",
    "longitude",
    "prec_latlo",
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value) or "").strip()


def _psgc(value: Any) -> str | None:
    text = _text(value)
    if text.upper().startswith("PH"):
        text = text[2:]
    return text if text.isdigit() and len(text) <= 10 else None


def _subtype(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    return text or "HEALTH_FACILITY"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper() or "UNNAMED"


def parse_geojson(content: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("NHA WFS response is not JSON.") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        raise ValueError("NHA WFS response contains no features.")
    records: list[dict[str, Any]] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        record = {key: properties.get(key) for key in PUBLIC_FIELDS}
        record["geometry_type"] = geometry.get("type") if isinstance(geometry, dict) else None
        record["geometry_coordinates"] = coordinates
        record["feature_id"] = feature.get("id")
        record["feature_index"] = index
        records.append(record)
    return records


def _source_key(record: dict[str, Any]) -> str:
    code = _text(record.get("fac_code"))
    if code:
        return f"NHA-DOH-HF:{code}"
    raw = json.dumps(record, sort_keys=True, default=str)
    return f"NHA-DOH-HF:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


class NhaDohFacilityAdapter:
    source_code = "nha"
    parser_version = "nha-wfs-doh-hf-1.0.0"
    schema_version = "nha-wfs-doh-hf-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = parse_geojson(spec.content)
        rows: list[ParsedRow] = []
        for record in records:
            name = _text(record.get("fac_name"))
            if not name:
                continue
            rows.append(
                ParsedRow(
                    source_record_key=_source_key(record),
                    row_reference=f"nha-wfs:{record.get('feature_index')}",
                    raw_payload=record,
                    normalized_payload=record,
                )
            )
        if not rows:
            raise ValueError("NHA WFS response contained no named facilities.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "partial_alternate_route",
                    "message": (
                        "The NHA 'DOH HF' layer is a partial alternate route for the blocked "
                        "DOH NHFR. It does not state a complete field dictionary, licence date "
                        "or operating status. Presence is registry evidence only."
                    ),
                },
                {
                    "code": "legacy_armm_psgc",
                    "message": (
                        "The layer uses the older ARMM PSGC series (15xxxxxxx) for the "
                        "Bangsamoro region. Codes are preserved as published and are not "
                        "remapped to the current BARMM (19xxxxxxx) series."
                    ),
                },
                {
                    "code": "precision_label_preserved",
                    "message": (
                        "The source's prec_latlo flag is retained. A 'Low' precision label "
                        "does not justify building-level accuracy claims."
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
            name = _text(payload.get("fac_name"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "NHA DOH HF feature has no facility name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_facility_code",
                        "error",
                        f"NHA facility code {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            if latitude is None or longitude is None:
                issues.append(
                    ValidationIssue(
                        "missing_coordinates",
                        "warning",
                        f"{name} has no source coordinates.",
                        row_reference=row.row_reference,
                    )
                )
            else:
                try:
                    lat, lon = float(latitude), float(longitude)
                except (TypeError, ValueError):
                    issues.append(
                        ValidationIssue(
                            "invalid_coordinates",
                            "error",
                            f"{name} has non-numeric coordinates.",
                            row_reference=row.row_reference,
                        )
                    )
                    rejected += 1
                    continue
                if not coordinate_in_philippines(lat, lon):
                    issues.append(
                        ValidationIssue(
                            "coordinates_outside_philippines",
                            "error",
                            f"{name} has coordinates outside the Philippine bounding box.",
                            {"latitude": lat, "longitude": lon},
                            row.row_reference,
                        )
                    )
                    rejected += 1
            if not _text(payload.get("reg_name")):
                issues.append(
                    ValidationIssue(
                        "missing_region",
                        "warning",
                        f"{name} has no region label.",
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
            name = _text(payload.get("fac_name"))
            if not name:
                continue
            facility_type = _text(payload.get("fac_type")) or "Health Facility"
            owner_label = _text(payload.get("ownershp"))
            is_government = owner_label.casefold() in {"government", "public", "gov't"}
            ownership = "government" if is_government else "private" if owner_label else "unknown"
            # ``ownershp`` has only a broad private label, so do not claim a
            # corporate, individual, or non-profit ownership type.
            ownership_type = (
                "GOVERNMENT_UNSPECIFIED"
                if is_government
                else "PRIVATE_UNSPECIFIED"
                if owner_label
                else "UNKNOWN"
            )
            address_parts = [
                _text(payload.get("brgy_name")),
                _text(payload.get("municity")),
                _text(payload.get("prov_name")),
                _text(payload.get("reg_name")),
            ]
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            try:
                latitude = float(latitude) if latitude is not None else None
                longitude = float(longitude) if longitude is not None else None
            except (TypeError, ValueError):
                latitude = longitude = None
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=_text(payload.get("fac_code")) or None,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="health_facility",
                    facility_subtype=_subtype(facility_type),
                    facility_kind="facility",
                    inclusion_class=(
                        "GOVERNMENT_FACILITY"
                        if is_government
                        else "PRIVATE_PUBLIC_SERVICE_PROVIDER"
                        if owner_label
                        else "DISCOVERY_CANDIDATE"
                    ),
                    ownership=ownership,
                    ownership_type=ownership_type,
                    operator_type=ownership_type,
                    public_access_class="UNKNOWN",
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision="source_gps" if latitude is not None else "unknown",
                        method="nha_geoserver_wfs",
                        address_text=", ".join(part for part in address_parts if part) or None,
                        postal_code=_text(payload.get("zip_code")) or None,
                        psgc_code=_psgc(payload.get("brgy_psgc"))
                        or _psgc(payload.get("muni_psgc"))
                        or _psgc(payload.get("prov_psgc"))
                        or _psgc(payload.get("reg_psgc")),
                        review_status="source_supplied",
                    ),
                    functions=[
                        FunctionData(
                            function_code="HEALTHCARE",
                            source_value=facility_type,
                            evidence={
                                "source": "NHA GeoServer NHA_PH:DOH HF",
                                "source_facility_code": payload.get("fac_code"),
                                "source_type": facility_type,
                                "source_ownership": owner_label,
                                "source_region": payload.get("reg_name"),
                                "source_region_psgc": payload.get("reg_psgc"),
                                "source_province": payload.get("prov_name"),
                                "source_municipality": payload.get("municity"),
                                "source_barangay": payload.get("brgy_name"),
                                "source_precision": payload.get("prec_latlo"),
                                "alternate_route_for": "DOH National Health Facility Registry",
                            },
                        )
                    ],
                    health=HealthData(
                        doh_facility_id=_text(payload.get("fac_code")) or None,
                        facility_category=facility_type,
                    ),
                )
            )
        return candidates


PROJECT_FIELDS = (
    "id",
    "proj_code",
    "proj_cod_1",
    "proj_name",
    "prj_class",
    "class_code",
    "office_cod",
    "reg_code",
    "prov_code",
    "city_code",
    "brgy_code",
    "developer",
    "tot_units",
    "awarded_da",
    "awarded_un",
)
LANDHOLDING_FIELDS = ("region", "layer", "propname", "area_sqm", "location")


def _parse_layer(content: bytes, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("NHA WFS response is not JSON.") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        raise ValueError("NHA WFS response contains no features.")
    records: list[dict[str, Any]] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        record = {key: properties.get(key) for key in fields}
        record["geometry_type"] = geometry.get("type") if isinstance(geometry, dict) else None
        record["geometry_coordinates"] = coordinates
        record["feature_id"] = feature.get("id")
        record["feature_index"] = index
        records.append(record)
    return records


def _point(record: dict[str, Any]) -> tuple[float | None, float | None]:
    coordinates = record.get("geometry_coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None, None
    try:
        return float(coordinates[1]), float(coordinates[0])
    except (TypeError, ValueError):
        return None, None


def _housing_key(prefix: str, *values: Any) -> str:
    raw = "|".join(_text(value) for value in values)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20] if raw else "UNKNOWN"
    return f"{prefix}:{digest}"


class NhaHousingProjectAdapter:
    source_code = "nha"
    parser_version = "nha-wfs-project-loc-1.0.0"
    schema_version = "nha-wfs-project-loc-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = _parse_layer(spec.content, PROJECT_FIELDS)
        base_keys = [
            _housing_key(
                "NHA-PROJECT",
                record.get("proj_code"),
                record.get("proj_name"),
                record.get("latitude"),
                record.get("longitude"),
                record.get("reg_code"),
                record.get("prov_code"),
                record.get("city_code"),
                record.get("brgy_code"),
            )
            for record in records
            if _text(record.get("proj_name"))
        ]
        counts = Counter(base_keys)
        seen: Counter[str] = Counter()
        rows = []
        for record, base_key in zip(
            (record for record in records if _text(record.get("proj_name"))),
            base_keys,
            strict=True,
        ):
            seen[base_key] += 1
            key = base_key if counts[base_key] == 1 else f"{base_key}#{seen[base_key]}"
            rows.append(
                ParsedRow(
                    source_record_key=key,
                    row_reference=f"nha-project:{record.get('feature_index')}",
                    raw_payload=record,
                    normalized_payload=record,
                )
            )
        if not rows:
            raise ValueError("NHA project layer contained no named projects.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "project_not_facility",
                    "message": (
                        "These are NHA project-location points, not operating facilities. "
                        "The layer does not state completion, occupancy or current status."
                    ),
                },
                {
                    "code": "no_standard_geography_codes",
                    "message": (
                        "The layer carries NHA office and place labels (reg_code, prov_code, "
                        "city_code, brgy_code) but no standard PSGC codes. No code is invented."
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
            name = _text(payload.get("proj_name"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_project_name",
                        "fatal",
                        "NHA project row has no project name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_project_code",
                        "error",
                        f"NHA project key {key} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if _point(payload) == (None, None):
                issues.append(
                    ValidationIssue(
                        "missing_coordinates",
                        "warning",
                        f"NHA project {name} has no point geometry.",
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
            name = _text(payload.get("proj_name"))
            if not name:
                continue
            latitude, longitude = _point(payload)
            address = ", ".join(
                part
                for part in (
                    _text(payload.get("brgy_code")),
                    _text(payload.get("city_code")),
                    _text(payload.get("prov_code")),
                )
                if part
            )
            project_class = _text(payload.get("prj_class"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=_text(payload.get("proj_code")) or None,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="housing_project",
                    facility_subtype=(
                        _subtype(project_class) if project_class else "HOUSING_PROJECT"
                    ),
                    facility_kind="project",
                    inclusion_class="DISCOVERY_CANDIDATE",
                    ownership="government",
                    ownership_type="GOVERNMENT_UNSPECIFIED",
                    operator_type="GOVERNMENT_UNSPECIFIED",
                    public_access_class="UNKNOWN",
                    record_status="unknown",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision="source_gps" if latitude is not None else "unknown",
                        method="nha_geoserver_wfs_project_location",
                        address_text=address or None,
                        psgc_code=None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="HOUSING",
                            source_value=project_class or "NHA project location",
                            designation_status="source_listed",
                            evidence={
                                "source": "NHA GeoServer NHA_PH:NHA_Project_Loc",
                                "project_code": payload.get("proj_code"),
                                "project_class": project_class,
                                "office_code": payload.get("office_cod"),
                                "source_region_label": payload.get("reg_code"),
                                "source_province_label": payload.get("prov_code"),
                                "source_city_label": payload.get("city_code"),
                                "source_barangay_label": payload.get("brgy_code"),
                                "source_units": payload.get("tot_units"),
                                "source_developer": payload.get("developer"),
                            },
                        )
                    ],
                )
            )
        return candidates


class NhaLandholdingAdapter:
    source_code = "nha"
    parser_version = "nha-wfs-landholdings-1.0.0"
    schema_version = "nha-wfs-landholdings-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = _parse_layer(spec.content, LANDHOLDING_FIELDS)
        rows = [
            ParsedRow(
                source_record_key=_housing_key(
                    "NHA-LANDHOLDING",
                    record.get("propname"),
                    record.get("location"),
                    record.get("feature_index"),
                ),
                row_reference=f"nha-landholding:{record.get('feature_index')}",
                raw_payload=record,
                normalized_payload=record,
            )
            for record in records
            if _text(record.get("propname"))
        ]
        if not rows:
            raise ValueError("NHA landholding layer contained no named properties.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "property_not_facility",
                    "message": (
                        "Landholding records are NHA property sites, not facilities or "
                        "service points. The layer supplies no occupancy, tenancy or "
                        "operating status."
                    ),
                },
                {
                    "code": "area_preserved_from_source",
                    "message": (
                        "area_sqm is the source value where supplied; it was not recalculated."
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
            key = row.source_record_key
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_landholding_key",
                        "error",
                        f"NHA landholding key {key} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if _point(payload) == (None, None):
                issues.append(
                    ValidationIssue(
                        "missing_coordinates",
                        "warning",
                        f"NHA landholding {_text(payload.get('propname'))} has no point geometry.",
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
            name = _text(payload.get("propname"))
            if not name:
                continue
            latitude, longitude = _point(payload)
            layer = _text(payload.get("layer")) or "NHA Landholding"
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="housing_service",
                    facility_subtype=_subtype(layer),
                    facility_kind="site",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOVERNMENT_UNSPECIFIED",
                    operator_type="GOVERNMENT_UNSPECIFIED",
                    public_access_class="UNKNOWN",
                    record_status="unknown",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision="source_gps" if latitude is not None else "unknown",
                        method="nha_geoserver_wfs_landholding",
                        address_text=_text(payload.get("location")) or None,
                        psgc_code=None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="PUBLIC_LAND_HOLDING",
                            source_value=layer,
                            designation_status="source_listed",
                            capacity_value=float(payload["area_sqm"])
                            if isinstance(payload.get("area_sqm"), (int, float))
                            else None,
                            capacity_unit="square_metres",
                            evidence={
                                "source": "NHA GeoServer NHA_PH:NHA LANDHOLDINGS",
                                "layer": layer,
                                "source_region": payload.get("region"),
                                "source_area_sqm": payload.get("area_sqm"),
                                "source_location": payload.get("location"),
                            },
                        )
                    ],
                )
            )
        return candidates
