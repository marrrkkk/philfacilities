from __future__ import annotations

from ..contracts import (
    FacilityCandidate,
    HealthData,
    LicenseData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from .common import (
    clean_text,
    first_present,
    normalise_code,
    normalise_ownership,
    parse_date,
    parse_float,
    parse_int,
    read_csv_rows,
    require_column_groups,
)

FACILITY_ID_ALIASES = ["facility_id", "doh_facility_id", "nhfr_id", "id"]
NAME_ALIASES = ["facility_name", "name", "health_facility_name"]
LAT_ALIASES = ["latitude", "lat", "y"]
LON_ALIASES = ["longitude", "lon", "lng", "x"]
PRECISION_ALIASES = ["coordinate_precision", "location_precision", "geocode_precision"]
METHOD_ALIASES = ["coordinate_method", "coordinate_source", "geocode_method", "location_method"]
PSGC_ALIASES = ["psgc_code", "barangay_psgc", "barangay_code"]
OWNERSHIP_ALIASES = ["ownership", "ownership_type", "sector"]
CATEGORY_ALIASES = ["facility_category", "facility_type", "category", "classification"]
SERVICE_ALIASES = ["service_capability_level", "service_capability", "hospital_level", "level"]
BED_ALIASES = ["bed_capacity", "beds", "bed_count", "authorized_beds"]
LICENSE_ALIASES = ["license_number", "license_no", "doh_license_number"]
LICENSE_STATUS_ALIASES = ["license_status", "registration_status", "source_status"]
LICENSE_VALID_FROM_ALIASES = ["license_valid_from", "license_issued", "valid_from"]
LICENSE_VALID_UNTIL_ALIASES = ["license_valid_until", "license_expiry", "valid_until"]

PRECISION_VALUES = {
    "gps_verified",
    "field_verified",
    "source_gps",
    "map_geocoded",
    "barangay_centroid",
    "unknown",
}


def _infer_precision(explicit: str | None, method: str | None) -> str:
    if explicit in PRECISION_VALUES:
        return explicit
    text = (method or "").lower()
    if "gps" in text:
        return "source_gps"
    if "barangay" in text or "centroid" in text:
        return "barangay_centroid"
    if "map" in text or "geocode" in text:
        return "map_geocoded"
    if "field" in text or "verified" in text:
        return "field_verified"
    return "unknown"


class DOHNHFRAdapter:
    source_code = "doh"
    parser_version = "doh-nhfr-csv-1.0.0"
    schema_version = "doh-nhfr-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        headers, rows = read_csv_rows(spec.content)
        require_column_groups(
            headers,
            [FACILITY_ID_ALIASES, NAME_ALIASES],
            "DOH NHFR",
        )
        parsed = []
        for index, row in enumerate(rows, start=2):
            facility_id = normalise_code(first_present(row, FACILITY_ID_ALIASES))
            name = clean_text(first_present(row, NAME_ALIASES))
            if not facility_id or not name:
                continue
            parsed.append(
                ParsedRow(
                    source_record_key=facility_id,
                    row_reference=f"row:{index}",
                    raw_payload=row,
                    normalized_payload=row,
                )
            )
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            facility_id = normalise_code(first_present(payload, FACILITY_ID_ALIASES))
            if facility_id in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_facility_id",
                        "error",
                        f"Duplicate DOH facility ID {facility_id}",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(facility_id or "")
            latitude = parse_float(first_present(payload, LAT_ALIASES))
            longitude = parse_float(first_present(payload, LON_ALIASES))
            if latitude is not None and not -90 <= latitude <= 90:
                issues.append(
                    ValidationIssue(
                        "latitude_range",
                        "fatal",
                        f"DOH facility {facility_id} latitude is out of range",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
            if longitude is not None and not -180 <= longitude <= 180:
                issues.append(
                    ValidationIssue(
                        "longitude_range",
                        "fatal",
                        f"DOH facility {facility_id} longitude is out of range",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
            beds = parse_int(first_present(payload, BED_ALIASES))
            if beds is not None and beds < 0:
                issues.append(
                    ValidationIssue(
                        "negative_bed_count",
                        "fatal",
                        f"DOH facility {facility_id} has a negative bed count",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates = []
        for row in parsed.rows:
            payload = row.normalized_payload
            facility_id = normalise_code(first_present(payload, FACILITY_ID_ALIASES))
            name = clean_text(first_present(payload, NAME_ALIASES))
            if not facility_id or not name:
                continue
            latitude = parse_float(first_present(payload, LAT_ALIASES))
            longitude = parse_float(first_present(payload, LON_ALIASES))
            method = clean_text(first_present(payload, METHOD_ALIASES))
            precision = _infer_precision(
                clean_text(first_present(payload, PRECISION_ALIASES)), method
            )
            license_number = clean_text(first_present(payload, LICENSE_ALIASES))
            licenses = []
            if license_number:
                licenses.append(
                    LicenseData(
                        issuing_authority="DOH",
                        license_number=license_number,
                        license_type=clean_text(first_present(payload, ["license_type"])),
                        source_status=clean_text(first_present(payload, LICENSE_STATUS_ALIASES)),
                        valid_from=parse_date(first_present(payload, LICENSE_VALID_FROM_ALIASES)),
                        valid_until=parse_date(first_present(payload, LICENSE_VALID_UNTIL_ALIASES)),
                    )
                )
            candidates.append(
                FacilityCandidate(
                    source_record_key=facility_id,
                    source_entity_id=facility_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="health_facility",
                    facility_subtype=clean_text(first_present(payload, CATEGORY_ALIASES)),
                    ownership=normalise_ownership(first_present(payload, OWNERSHIP_ALIASES)),
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision=precision,
                        method=method,
                        address_text=clean_text(
                            first_present(payload, ["address", "street", "complete_address"])
                        ),
                        psgc_code=normalise_code(first_present(payload, PSGC_ALIASES)),
                        review_status="source_supplied",
                    ),
                    health=HealthData(
                        doh_facility_id=facility_id,
                        facility_category=clean_text(first_present(payload, CATEGORY_ALIASES)),
                        service_capability_level=clean_text(
                            first_present(payload, SERVICE_ALIASES)
                        ),
                        bed_capacity=parse_int(first_present(payload, BED_ALIASES)),
                    ),
                    licenses=licenses,
                )
            )
        return candidates
