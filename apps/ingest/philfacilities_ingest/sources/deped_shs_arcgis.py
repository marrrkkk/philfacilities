"""DepEd Senior High School points published through the CHED GIS service.

The ``CHEDDepEdTesda_WFL1`` ArcGIS feature service exposes one point layer of
DepEd senior high schools. Each row carries the official six-digit BEIS School
ID, the DepEd region/division/district/barangay names, the school's sector and
senior-high offering classification, and WGS84 ``x``/``y`` coordinates.

The layer is **enrichment-only**. Rows link to existing DepEd facilities by the
exact six-digit school ID and fill only missing sector/management/administrative
values plus a mapped point. They never rename a facility, never replace an
established classification, and never create a parallel school for an ID that is
already in the EBEIS masterlist. The layer also repeats G11/G12 enrollment
counts; those columns are deliberately not requested, because Project Bukas owns
enrollment observations.

A point is a mapped school location, not a surveyed building or parcel. It is
published with ``map_geocoded`` precision and the source layer's own method
label; no PSGC code is inferred from the coordinates or address text.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from ..acquisition import AcquisitionError, HttpAcquirer
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
from .common import clean_text, normalise_code
from .deped_bukas import MANAGEMENT_NORMALIZED, MANAGEMENT_OPERATOR
from .deped_masterlist import SECTOR_CLASSIFICATION, SECTOR_NORMALIZED

LAYER_URL = (
    "https://services5.arcgis.com/KIpFXsYgUlJPgoun/arcgis/rest/services/"
    "CHEDDepEdTesda_WFL1/FeatureServer/2"
)
SERVICE_URL = (
    "https://services5.arcgis.com/KIpFXsYgUlJPgoun/arcgis/rest/services/"
    "CHEDDepEdTesda_WFL1/FeatureServer"
)
PAGE_SIZE = 1_000
MAX_FEATURES = 10_000
EXPECTED_FEATURES = 7_886

# Only institutional fields are requested. In particular the layer's G11/G12
# enrollment columns are excluded at acquisition time.
PUBLIC_FIELDS = (
    "OBJECTID",
    "Region",
    "Division",
    "District",
    "BEIS_School_ID",
    "School_Name",
    "Street_Address",
    "Mother_School_ID",
    "Province",
    "Municipality",
    "Legislative_District",
    "Barangay",
    "Sector",
    "School_Subclassification",
    "School_Type",
    "IU_NON_IU",
    "Modified_COC",
    "x",
    "y",
    "Remarks",
)

_PH_LONGITUDE_RANGE = (116.0, 127.0)
_PH_LATITUDE_RANGE = (4.0, 22.0)


def _query_url(*, count_only: bool = False, offset: int | None = None) -> str:
    params: dict[str, str] = {
        "where": "1=1",
        "f": "json",
        "outFields": ",".join(PUBLIC_FIELDS),
        "returnGeometry": "false",
        "orderByFields": "OBJECTID ASC",
    }
    if count_only:
        params["returnCountOnly"] = "true"
    else:
        params["resultOffset"] = str(offset or 0)
        params["resultRecordCount"] = str(PAGE_SIZE)
    return f"{LAYER_URL}/query?{urlencode(params)}"


def _read_json(result: Any, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(result.content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AcquisitionError(
            f"DepEd SHS layer returned non-JSON content for {label}.", result=result
        ) from exc
    if not isinstance(payload, dict):
        raise AcquisitionError(
            f"DepEd SHS layer returned an unexpected JSON shape for {label}.", result=result
        )
    if payload.get("error"):
        raise AcquisitionError(
            f"DepEd SHS layer returned an ArcGIS error for {label}: {payload['error']}",
            result=result,
        )
    return payload


def fetch_deped_shs_arcgis(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch every school in the DepEd SHS layer and build one JSON artifact."""

    count_result = acquirer.fetch(_query_url(count_only=True))
    if count_result.status_code >= 400:
        raise AcquisitionError(
            f"DepEd SHS count query returned HTTP {count_result.status_code}.",
            result=count_result,
        )
    count_payload = _read_json(count_result, "count")
    total = count_payload.get("count")
    if not isinstance(total, int) or total <= 0:
        raise AcquisitionError("DepEd SHS layer did not report a positive feature count.")
    if total > MAX_FEATURES:
        raise AcquisitionError(
            f"DepEd SHS layer reported {total} features, above the {MAX_FEATURES} "
            "connector safety limit; the layer may have changed."
        )

    records: list[dict[str, Any]] = []
    pages_fetched = 0
    offset = 0
    while offset < total:
        result = acquirer.fetch(_query_url(offset=offset))
        if result.status_code >= 400:
            raise AcquisitionError(
                f"DepEd SHS page at offset {offset} returned HTTP {result.status_code}.",
                result=result,
            )
        payload = _read_json(result, f"offset {offset}")
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            raise AcquisitionError(
                f"DepEd SHS page at offset {offset} returned no features while "
                f"{total} were reported."
            )
        for feature in features:
            attributes = feature.get("attributes") if isinstance(feature, dict) else None
            if isinstance(attributes, dict):
                records.append({key: attributes.get(key) for key in PUBLIC_FIELDS})
        pages_fetched += 1
        offset += len(features)
        if len(features) < PAGE_SIZE:
            break
        time.sleep(0.1)

    if len(records) != total:
        raise AcquisitionError(
            f"DepEd SHS layer reported {total} features but {len(records)} were "
            "retrieved; no release was accepted."
        )

    artifact = {
        "layer_url": LAYER_URL,
        "service_url": SERVICE_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "feature_count": total,
        "pages_fetched": pages_fetched,
        "note": (
            "Public DepEd Senior High School point layer published by CHED GIS. "
            "Only institutional fields and the source x/y point are retained. "
            "G11/G12 enrollment columns are deliberately omitted."
        ),
        "features": [{"attributes": record} for record in records],
    }
    metadata = {
        "layer_url": LAYER_URL,
        "features": total,
        "pages_fetched": pages_fetched,
        "public_fields": list(PUBLIC_FIELDS),
    }
    return json.dumps(artifact, ensure_ascii=False).encode("utf-8"), metadata


def _text(value: Any) -> str | None:
    text = clean_text(value)
    if not text or text.casefold() in {"<null>", "null", "n/a", "na"}:
        return None
    return text


def _coordinate(value: Any, bounds: tuple[float, float]) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not bounds[0] <= number <= bounds[1]:
        return None
    return number


def _address_text(payload: dict[str, Any]) -> str | None:
    parts = [
        _text(payload.get("Street_Address")),
        _text(payload.get("Barangay")),
        _text(payload.get("Municipality")),
        _text(payload.get("Province")),
    ]
    kept: list[str] = []
    for part in parts:
        if not part:
            continue
        folded = part.casefold()
        if any(folded in value.casefold() for value in kept):
            continue
        kept.append(part)
    return ", ".join(kept) or None


class DepEdShsArcgisAdapter:
    source_code = "deped"
    parser_version = "deped-shs-arcgis-1.0.0"
    schema_version = "deped-shs-arcgis-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            artifact = json.loads(spec.content)
        except json.JSONDecodeError as exc:
            raise ValueError("DepEd SHS artifact is not valid JSON.") from exc
        features = artifact.get("features") if isinstance(artifact, dict) else None
        if not isinstance(features, list) or not features:
            raise ValueError("DepEd SHS artifact contains no features.")
        rows: list[ParsedRow] = []
        for index, feature in enumerate(features, start=1):
            attributes = feature.get("attributes") if isinstance(feature, dict) else None
            if not isinstance(attributes, dict):
                continue
            public = {key: attributes.get(key) for key in PUBLIC_FIELDS}
            school_id = normalise_code(public.get("BEIS_School_ID"))
            rows.append(
                ParsedRow(
                    source_record_key=school_id or f"row-{index}",
                    row_reference=f"deped-shs:{public.get('OBJECTID') or index}",
                    raw_payload=public,
                    normalized_payload=public,
                )
            )
        if not rows:
            raise ValueError("DepEd SHS artifact contained no usable feature rows.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "enrichment_only_release",
                    "message": (
                        "Rows link by exact six-digit BEIS School ID and fill only "
                        "missing school values and a mapped point. Enrollment columns "
                        "are omitted from acquisition and no facility is renamed."
                    ),
                },
                {
                    "code": "mapped_point_not_building",
                    "message": (
                        "Coordinates are the layer's published school point, not a "
                        "surveyed building or parcel. They are stored with "
                        "map_geocoded precision."
                    ),
                },
                {
                    "code": "no_psgc_inference",
                    "message": (
                        "The layer publishes administrative names but no PSGC code. "
                        "No code is inferred from the address or coordinates."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        rejected_rows: set[str] = set()
        missing_points = 0
        outside = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(payload.get("BEIS_School_ID"))
            name = _text(payload.get("School_Name"))
            reason = None
            if not school_id or not (len(school_id) == 6 and school_id.isdigit()):
                reason = "BEIS School ID is not a six-digit code."
            elif school_id in seen:
                reason = "Duplicate BEIS School ID."
            elif not name:
                reason = "School name is missing."
            if reason is not None:
                rejected += 1
                rejected_rows.add(row.row_reference)
                issues.append(
                    ValidationIssue(
                        code="invalid_shs_row",
                        severity="error",
                        message=reason,
                        row_reference=row.row_reference,
                        details={"school_id": school_id, "school_name": name},
                    )
                )
                continue
            seen.add(school_id)
            latitude = _coordinate(payload.get("y"), _PH_LATITUDE_RANGE)
            longitude = _coordinate(payload.get("x"), _PH_LONGITUDE_RANGE)
            if latitude is None or longitude is None:
                missing_points += 1
            elif payload.get("y") is not None or payload.get("x") is not None:
                raw_latitude = _coordinate(payload.get("y"), (-90.0, 90.0))
                raw_longitude = _coordinate(payload.get("x"), (-180.0, 180.0))
                if raw_latitude != latitude or raw_longitude != longitude:
                    outside += 1
        if missing_points:
            issues.append(
                ValidationIssue(
                    code="missing_or_outside_point",
                    severity="warning",
                    message=(
                        f"{missing_points} rows have no usable point inside the "
                        "Philippine bounding box; their institutional fields are "
                        "still accepted."
                    ),
                    details={"rows": missing_points, "outside_philippines_bbox": outside},
                )
            )
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
            rejected_row_references=rejected_rows,
            failed=rejected == len(parsed.rows),
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(payload.get("BEIS_School_ID"))
            name = _text(payload.get("School_Name"))
            if not school_id or not name:
                continue
            sector = SECTOR_NORMALIZED.get((_text(payload.get("Sector")) or "").casefold())
            if sector in SECTOR_CLASSIFICATION:
                ownership, ownership_type, inclusion_class = SECTOR_CLASSIFICATION[sector]
            else:
                ownership, ownership_type, inclusion_class = (
                    "unknown",
                    "UNKNOWN",
                    None,
                )
            management = MANAGEMENT_NORMALIZED.get(
                (_text(payload.get("School_Subclassification")) or "").casefold()
            )
            latitude = _coordinate(payload.get("y"), _PH_LATITUDE_RANGE)
            longitude = _coordinate(payload.get("x"), _PH_LONGITUDE_RANGE)
            has_point = latitude is not None and longitude is not None
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=school_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="school",
                    facility_subtype=None,
                    ownership=ownership,
                    ownership_type=ownership_type,
                    operator_type=MANAGEMENT_OPERATOR.get(management or "", "UNKNOWN"),
                    inclusion_class=inclusion_class,
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=latitude if has_point else None,
                        longitude=longitude if has_point else None,
                        precision="map_geocoded" if has_point else "unknown",
                        method="deped_shs_arcgis" if has_point else None,
                        address_text=_address_text(payload),
                        psgc_code=None,
                        review_status="source_supplied",
                    ),
                    school=SchoolData(
                        deped_school_id=school_id,
                        sector=sector,
                        school_management=management,
                        division=_text(payload.get("Division")),
                        district=_text(payload.get("District")),
                        legislative_district=_text(payload.get("Legislative_District")),
                        offering_classification=_text(payload.get("Modified_COC")),
                        offers_shs=True,
                    ),
                    enrichment_only=True,
                )
            )
        return candidates
