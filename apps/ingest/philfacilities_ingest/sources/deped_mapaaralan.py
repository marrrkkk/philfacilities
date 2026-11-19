"""DepEd MaPaaralan school points, cleaned by OpenStreetMap Philippines.

The ``OSMaPaaralan`` repository publishes a 2019 table of Philippine schools
that OpenStreetMap Philippines compiled from the Department of Education's
MaPaaralan Project release. DepEd transmitted the school points to OSMPH for
open mapping in 2013, and the repository preserves that letter. Each row keeps
the official six-digit BEIS school ID along with the school name and a WGS84
point.

The table is **link-only enrichment**. Rows match an existing DepEd facility by
the exact six-digit school ID and supply a point only when the current location
has none. They never create a facility, rename one, fill sector/ownership, or
assert operational status. That matters because the 2019 snapshot predates the
SY 2020-2021 EBEIS masterlist and still names schools that were later closed,
renamed, split or merged; several hundred IDs no longer resolve.

A point is a mapped school location, not a surveyed building or parcel. It is
published with ``map_geocoded`` precision and the source's own method label; no
PSGC code is inferred from the coordinates or the OpenStreetMap address tags.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Any

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

SOURCE_URL = (
    "https://raw.githubusercontent.com/OSMPH/OSMaPaaralan/master/data/2019/"
    "OSMaPaaralan_v2019-282-full.tsv"
)
EXPECTED_SHA256 = "288f52e03626946ccabc936dd862bea77238da1b61249ffd2246ba6fe6ec018b"
MAX_BYTES = 32 * 1024 * 1024
EXPECTED_ROWS = 44_848
EXPECTED_POINTS = 40_082

REQUIRED_COLUMNS = ("@id", "name", "latitude", "longitude")

# Only fields that identify the row, establish its point, or preserve the
# source's own administrative context are retained. Population estimates and
# tasking metadata are not used and stay in the preserved raw artifact.
PUBLIC_FIELDS = (
    "@id",
    "name",
    "addr:region",
    "addr:province",
    "addr:town",
    "addr:city",
    "operator",
    "latitude",
    "longitude",
    "hrslph100m",
    "priority",
)

_PH_LONGITUDE_RANGE = (116.0, 127.0)
_PH_LATITUDE_RANGE = (4.0, 22.0)
_SIX_DIGIT_ID = re.compile(r"[0-9]{6}")


def _text(value: Any) -> str | None:
    text = clean_text(value)
    if not text or text.casefold() in {"<null>", "null", "n/a", "na", "-"}:
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


def fetch_deped_mapaaralan(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch the pinned OSMPH table and reject any checksum change."""

    result = acquirer.fetch(SOURCE_URL, max_bytes=MAX_BYTES)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"OSMPH MaPaaralan table returned HTTP {result.status_code}.",
            result=result,
        )
    digest = hashlib.sha256(result.content).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AcquisitionError(
            "OSMPH MaPaaralan table checksum changed; the connector is pinned to "
            f"{EXPECTED_SHA256} and no release was accepted."
        )
    return result.content, {
        "source_url": SOURCE_URL,
        "sha256": digest,
        "expected_rows": EXPECTED_ROWS,
        "expected_points": EXPECTED_POINTS,
    }


class DepEdMapaaralanAdapter:
    source_code = "deped"
    parser_version = "deped-mapaaralan-1.0.0"
    schema_version = "deped-mapaaralan-v1"
    # A 40k-row link-only release touches tens of thousands of schools. Resolve
    # the current location per row instead of preloading every location object
    # for the whole run, and drop the per-batch caches at each flush.
    bulk_apply_reset = True

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            text = spec.content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("OSMPH MaPaaralan table is not UTF-8 text.") from exc
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        header = tuple(reader.fieldnames or ())
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise ValueError(
                "OSMPH MaPaaralan table is missing required columns: " + ", ".join(missing)
            )
        rows: list[ParsedRow] = []
        for index, row in enumerate(reader, start=2):
            source_id = normalise_code(row.get("@id"))
            name = _text(row.get("name"))
            payload = {key: (row.get(key) or None) for key in PUBLIC_FIELDS}
            normalized = {
                "@id": source_id,
                "name": name,
                "latitude": _coordinate(row.get("latitude"), _PH_LATITUDE_RANGE),
                "longitude": _coordinate(row.get("longitude"), _PH_LONGITUDE_RANGE),
            }
            rows.append(
                ParsedRow(
                    # Duplicate school IDs exist in the source. A unique row key
                    # keeps both raw rows, while validation rejects the second
                    # occurrence before it can reach the registry.
                    source_record_key=f"{source_id or 'row'}-{index}",
                    row_reference=f"deped-mapaaralan:{source_id or 'row'}:{index}",
                    raw_payload=payload,
                    normalized_payload=normalized,
                )
            )
        if not rows:
            raise ValueError("OSMPH MaPaaralan table contained no school rows.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "community_compiled_snapshot",
                    "message": (
                        "Rows are a 2019 OSMPH cleaning of the DepEd MaPaaralan "
                        "release, not a current DepEd registry export. DepEd's 2013 "
                        "letter authorises open release of the school points."
                    ),
                },
                {
                    "code": "link_only_enrichment",
                    "message": (
                        "Rows link only to an existing facility with the exact "
                        "six-digit school ID and fill a missing point. Unmatched "
                        "IDs stay as source evidence; no facility is created."
                    ),
                },
                {
                    "code": "mapped_point_not_building",
                    "message": (
                        "Coordinates are the published school point, not a surveyed "
                        "building or parcel. They are stored with map_geocoded "
                        "precision."
                    ),
                },
                {
                    "code": "no_sector_or_status",
                    "message": (
                        "The table carries no sector, ownership, management or "
                        "operational status. None is inferred from the name, ID or "
                        "administrative tags."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        rejected_rows: set[str] = set()
        duplicates = 0
        missing_points = 0
        outside = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            source_id = normalise_code(payload.get("@id"))
            name = _text(payload.get("name"))
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            raw_latitude = _coordinate(row.raw_payload.get("latitude"), (-90.0, 90.0))
            raw_longitude = _coordinate(row.raw_payload.get("longitude"), (-180.0, 180.0))
            outside_bbox = (
                raw_latitude is not None
                and raw_longitude is not None
                and (latitude is None or longitude is None)
            )
            reason = None
            if not source_id or not _SIX_DIGIT_ID.fullmatch(source_id):
                reason = "School ID is not a six-digit DepEd code."
            elif not name:
                reason = "School name is missing."
            elif latitude is None or longitude is None:
                reason = "No usable point inside the Philippine bounding box."
            elif source_id in seen:
                reason = "Duplicate six-digit school ID."
                duplicates += 1
            if reason is not None:
                rejected += 1
                rejected_rows.add(row.row_reference)
                issues.append(
                    ValidationIssue(
                        code="invalid_mapaaralan_row",
                        severity="error",
                        message=reason,
                        row_reference=row.row_reference,
                        details={
                            "school_id": source_id,
                            "school_name": name,
                            "latitude": payload.get("latitude"),
                            "longitude": payload.get("longitude"),
                        },
                    )
                )
                if latitude is None or longitude is None:
                    missing_points += 1
                if outside_bbox:
                    outside += 1
                continue
            seen.add(source_id)
        issues.append(
            ValidationIssue(
                code="mapaaralan_rejections",
                severity="info",
                message=(
                    f"{rejected} of {len(parsed.rows)} rows were rejected; "
                    f"{duplicates} duplicate IDs and {missing_points} rows without "
                    "a point inside the Philippine bounding box."
                ),
                details={
                    "rows": len(parsed.rows),
                    "accepted": len(parsed.rows) - rejected,
                    "rejected": rejected,
                    "duplicates": duplicates,
                    "missing_points": missing_points,
                    "outside_philippines_bbox": outside,
                },
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
            source_id = normalise_code(payload.get("@id"))
            name = _text(payload.get("name"))
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            if (
                not source_id
                or not name
                or latitude is None
                or longitude is None
                or not _SIX_DIGIT_ID.fullmatch(source_id)
            ):
                continue
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=source_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="school",
                    facility_subtype=None,
                    ownership="unknown",
                    ownership_type="UNKNOWN",
                    operator_type="UNKNOWN",
                    inclusion_class=None,
                    record_status="unknown",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision="map_geocoded",
                        method="deped_mapaaralan_2019_osmph",
                        address_text=None,
                        psgc_code=None,
                        review_status="source_supplied",
                    ),
                    school=SchoolData(deped_school_id=source_id),
                    enrichment_only=True,
                    link_only=True,
                )
            )
        return candidates
