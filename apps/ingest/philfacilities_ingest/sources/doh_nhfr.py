"""DOH National Health Facility Registry (NHFR), September 2026 snapshot.

The NHFR is the Department of Health's master list of licensed and registered
health facilities. This adapter reads the public XLSX export and keeps only
institution-level fields: DOH facility code, name, facility type, ownership,
administrative PSGC codes, bed capacity, and licensing status. Contact columns,
street/building addresses, and facility-head names are discarded.

The source is used in **enrichment** mode: an existing facility is matched by its
exact DOH facility code and only missing profile values are filled. NHFR rows
that do not match an existing facility create a new official facility record;
they never rename an established facility or downgrade an established
classification.

The official NHFR site sits behind a Cloudflare challenge for automated clients.
The preserved artifact is the public redacted September 2026 export mirrored by
the BHW Connect project; its SHA-256 is pinned below.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime
from typing import Any

import openpyxl

from ..acquisition import AcquisitionError, HttpAcquirer
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
from .common import clean_text

# Acquisition ---------------------------------------------------------------

NHFR_URL = "https://nhfr.doh.gov.ph/VActivefacilitiesList"
MIRROR_XLSX_URL = (
    "https://raw.githubusercontent.com/jongsky25/bhw-connect-dashboard/main/"
    "ingestion/data/nhfr_universe_as_of_September_2026.xlsx"
)
EXPECTED_SHA256 = "470c967db52e90bf9d7018d0434d3166e1d17ed04714edcc7ceadb78bad82835"
EXPECTED_ROWS = 44_799
MAX_XLSX_BYTES = 32 * 1024 * 1024
SNAPSHOT_LABEL = "DOH-NHFR-2026-09"

# Layout --------------------------------------------------------------------

REQUIRED_COLUMNS = (
    "Health Facility Code",
    "Facility Name",
    "Facility Major Type",
    "Health Facility Type",
    "Ownership Major Classification",
    "Region Name",
    "Region PSGC",
    "Province Name",
    "Province PSGC",
    "City/Municipality Name",
    "City/Municipality PSGC",
    "Barangay Name",
    "Barangay PSGC",
    "Service Capability",
    "Bed Capacity",
    "Licensing Status",
    "License Validity Date",
)
GOVERNMENT_SUBCLASS_COLUMN = "Ownership Sub-Classification for Government facilities"
PRIVATE_SUBCLASS_COLUMN = "Ownership Sub-Classification for private facilities"

# Ownership sub-classification -> controlled ownership type. A missing
# sub-classification stays unspecified; it is never inferred from the facility
# type or from the presence of a licence.
OWNERSHIP_TYPES = {
    "Local Government Unit": "LOCAL_GOVERNMENT",
    "National Government": "NATIONAL_GOVERNMENT",
    "Department Of Health": "NATIONAL_GOVERNMENT",
    "Department of National Defense": "NATIONAL_GOVERNMENT",
    "Philippine National Police": "NATIONAL_GOVERNMENT",
    "Armed Forces of the Philippines": "NATIONAL_GOVERNMENT",
    "Office of the President": "NATIONAL_GOVERNMENT",
    "Philippine Air Force": "NATIONAL_GOVERNMENT",
    "Government-Owned and Controlled Corporations": "GOCC",
    "University Hospital": "PUBLIC_EDUCATIONAL_INSTITUTION",
    "MOH BARMM": "OTHER_PUBLIC_BODY",
    "Single Proprietorship": "PRIVATE_INDIVIDUAL_OR_PARTNERSHIP",
    "Partnership": "PRIVATE_INDIVIDUAL_OR_PARTNERSHIP",
    "Corporation": "PRIVATE_CORPORATE",
    "Cooperative": "COOPERATIVE",
    "Non-government Organization": "NGO_NON_PROFIT",
    "Foundation": "NGO_NON_PROFIT",
    "Religious": "RELIGIOUS_FAITH_BASED",
}

# The NHFR has 45 facility types. Map them into the controlled health subtypes;
# the exact source value is retained in ``facility_type_detail``.
FACILITY_SUBTYPES = {
    "Hospital": "HOSPITAL",
    "Infirmary": "INFIRMARY",
    "Rural Health Unit": "RURAL_HEALTH_UNIT",
    "Barangay Health Station": "BARANGAY_HEALTH_STATION",
    "Birthing Home": "BIRTHING_HOME",
    "Dialysis Clinic": "DIALYSIS_CENTER",
    "Clinical Laboratory": "LABORATORY",
    "Drug Testing Laboratory": "LABORATORY",
    "Dental Laboratory": "LABORATORY",
    "Laboratory for Drinking Water Analysis": "LABORATORY",
    "COVID-19 Testing Laboratory": "LABORATORY",
    "Clinical Laboratory for Molecular Pathology": "LABORATORY",
    "Laboratory for Chemical Analysis for Dialysis Wate": "LABORATORY",
    "Special Clinical Laboratory": "LABORATORY",
    "Research and Teaching Laboratory": "LABORATORY",
    "Ambulatory Surgical Clinic": "CLINIC",
    "Medical Outpatient Clinic": "CLINIC",
    "Social Hygiene Clinic": "CLINIC",
    "School Clinic": "CLINIC",
    "Bagong Urgent Care and Ambulatory Service": "CLINIC",
    "Animal Bite Treatment Center": "CLINIC",
    "Animal Bite Center": "CLINIC",
    "Detention Facility Clinic": "CLINIC",
    "Medical Facility for Overseas Workers & Seafarers": "CLINIC",
    "Cancer Treatment Facility": "CLINIC",
    "Stem Cell Treatment Clinics": "CLINIC",
    "Psychiatric Care Facility": "OTHER_HEALTH_FACILITY",
    "Blood Service Facility": "OTHER_HEALTH_FACILITY",
    "Newborn Screening Center": "OTHER_HEALTH_FACILITY",
    "City Health Office": "OTHER_HEALTH_FACILITY",
    "City Department of Health Office": "OTHER_HEALTH_FACILITY",
    "Municipal Health Office": "OTHER_HEALTH_FACILITY",
    "Provincial Health Office": "OTHER_HEALTH_FACILITY",
    "Provincial Department of Health Office": "OTHER_HEALTH_FACILITY",
    "Center for Health Development": "OTHER_HEALTH_FACILITY",
    "Certifying Organization": "OTHER_HEALTH_FACILITY",
    "Central Warehouse - Ambient": "OTHER_HEALTH_FACILITY",
    "Central Warehouse - Combination": "OTHER_HEALTH_FACILITY",
    "Central Warehouse - Temperature Controlled": "OTHER_HEALTH_FACILITY",
    "Regional Warehouse - Ambient": "OTHER_HEALTH_FACILITY",
    "Regional Warehouse - Combination": "OTHER_HEALTH_FACILITY",
    "Regional Warehouse - Temperature Controlled": "OTHER_HEALTH_FACILITY",
}


def _psgc(value: Any) -> str | None:
    """Preserve a PSGC code as text and restore Excel-stripped leading zeros."""

    text = clean_text(value)
    if text is None:
        return None
    text = re.sub(r"\.0$", "", text)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    return digits.zfill(10)


def _int(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    text = clean_text(value)
    if text is None:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _licensing_status(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    return text.removeprefix("Licensing Status:").strip() or None


def parse_nhfr_workbook(content: bytes) -> list[dict[str, Any]]:
    """Read the official XLSX export into one institutional record per row."""

    if not content.startswith(b"PK"):
        raise ValueError("NHFR content is not an XLSX workbook.")
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        worksheet = workbook[workbook.sheetnames[0]]
        rows = worksheet.iter_rows(values_only=True)
        try:
            header = next(rows)
        except StopIteration as exc:
            raise ValueError("NHFR workbook is empty.") from exc
        columns = {str(value).strip(): index for index, value in enumerate(header) if value}
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise ValueError(f"NHFR workbook is missing columns: {', '.join(missing)}")
        if GOVERNMENT_SUBCLASS_COLUMN not in columns:
            raise ValueError("NHFR workbook is missing the government sub-classification column.")
        if PRIVATE_SUBCLASS_COLUMN not in columns:
            raise ValueError("NHFR workbook is missing the private sub-classification column.")

        records: list[dict[str, Any]] = []
        for row_number, row in enumerate(rows, start=2):
            if row is None or all(value in (None, "") for value in row):
                continue
            raw = {
                column: row[index] if index < len(row) else None
                for column, index in columns.items()
            }
            ownership_major = clean_text(raw.get("Ownership Major Classification"))
            subclass_column = (
                GOVERNMENT_SUBCLASS_COLUMN
                if ownership_major == "Government"
                else PRIVATE_SUBCLASS_COLUMN
            )
            records.append(
                {
                    "xlsx_row": row_number,
                    "health_facility_code": clean_text(raw.get("Health Facility Code")),
                    "health_facility_code_short": clean_text(raw.get("Health Facility Code Short")),
                    "facility_name": clean_text(raw.get("Facility Name")),
                    "facility_major_type": clean_text(raw.get("Facility Major Type")),
                    "health_facility_type": clean_text(raw.get("Health Facility Type")),
                    "ownership_major": ownership_major,
                    "ownership_subclassification": clean_text(raw.get(subclass_column)),
                    "region_name": clean_text(raw.get("Region Name")),
                    "region_psgc": _psgc(raw.get("Region PSGC")),
                    "province_name": clean_text(raw.get("Province Name")),
                    "province_psgc": _psgc(raw.get("Province PSGC")),
                    "city_municipality_name": clean_text(raw.get("City/Municipality Name")),
                    "city_municipality_psgc": _psgc(raw.get("City/Municipality PSGC")),
                    "barangay_name": clean_text(raw.get("Barangay Name")),
                    "barangay_psgc": _psgc(raw.get("Barangay PSGC")),
                    "service_capability": clean_text(raw.get("Service Capability")),
                    "bed_capacity": _int(raw.get("Bed Capacity")),
                    "licensing_status_raw": clean_text(raw.get("Licensing Status")),
                    "license_validity_raw": clean_text(raw.get("License Validity Date")),
                }
            )
        return records
    finally:
        workbook.close()


# Acquisition fallback ------------------------------------------------------


def fetch_doh_nhfr(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch the preserved official NHFR export and verify its checksum."""

    result = acquirer.fetch(MIRROR_XLSX_URL, max_bytes=MAX_XLSX_BYTES)
    if result.status_code != 200 or not result.content.startswith(b"PK"):
        raise AcquisitionError(
            "DOH NHFR export is unavailable from the preserved public mirror "
            f"(HTTP {result.status_code})."
        )
    digest = hashlib.sha256(result.content).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AcquisitionError(
            "DOH NHFR export checksum changed: expected "
            f"{EXPECTED_SHA256}, got {digest}. No data was accepted."
        )
    return result.content, {
        "http_status": result.status_code,
        "acquired_from": MIRROR_XLSX_URL,
        "sha256": digest,
        "official_registry": NHFR_URL,
    }


# Adapter -------------------------------------------------------------------


class DohNhfrAdapter:
    source_code = "doh"
    parser_version = "doh-nhfr-xlsx-1.0.0"
    schema_version = "doh-nhfr-2026-09-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = parse_nhfr_workbook(spec.content)
        rows: list[ParsedRow] = []
        for record in records:
            code = record["health_facility_code"]
            if not code:
                continue
            licensing_status = _licensing_status(record["licensing_status_raw"])
            license_date = _date(record["license_validity_raw"])
            rows.append(
                ParsedRow(
                    source_record_key=code,
                    row_reference=f"xlsx_row:{record['xlsx_row']}",
                    raw_payload=record,
                    normalized_payload={
                        **record,
                        "licensing_status": licensing_status,
                        "license_validity_date": (
                            license_date.isoformat() if license_date else None
                        ),
                        "ownership_type": OWNERSHIP_TYPES.get(
                            record["ownership_subclassification"],
                            "GOVERNMENT_UNSPECIFIED"
                            if record["ownership_major"] == "Government"
                            else "PRIVATE_UNSPECIFIED",
                        ),
                        "facility_subtype": FACILITY_SUBTYPES.get(
                            record["health_facility_type"], "OTHER_HEALTH_FACILITY"
                        ),
                    },
                )
            )
        if not rows:
            raise ValueError("NHFR workbook returned no facility rows.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "institution_level_only",
                    "message": (
                        "Contact fields, street/building addresses, and facility-head "
                        "names are discarded. Only institution-level facility fields "
                        "are normalized and published."
                    ),
                },
                {
                    "code": "enrichment_only",
                    "message": (
                        "Existing facilities are matched by exact DOH facility code; "
                        "only missing profile fields are filled. Unmatched official "
                        "rows create new health facilities."
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
        for row in parsed.rows:
            payload = row.normalized_payload
            code = clean_text(payload.get("health_facility_code"))
            name = clean_text(payload.get("facility_name"))
            major = clean_text(payload.get("ownership_major"))
            if not code or not re.fullmatch(r"DOH\d{10,}", code):
                issues.append(
                    ValidationIssue(
                        "invalid_facility_code",
                        "fatal",
                        "Row does not carry a valid DOH health facility code.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            if code in seen:
                duplicates += 1
                issues.append(
                    ValidationIssue(
                        "duplicate_facility_code",
                        "fatal",
                        f"Facility code {code} appears more than once.",
                        {"health_facility_code": code},
                        row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            seen.add(code)
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        f"Facility {code} has no name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            if major not in {"Government", "Private"}:
                issues.append(
                    ValidationIssue(
                        "missing_ownership",
                        "fatal",
                        f"Facility {code} has no recognised ownership classification.",
                        {"ownership_major": major},
                        row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            for field, label in (
                ("region_psgc", "region"),
                ("province_psgc", "province"),
                ("city_municipality_psgc", "city/municipality"),
            ):
                value = clean_text(payload.get(field))
                if value is None or not re.fullmatch(r"\d{10}", value):
                    issues.append(
                        ValidationIssue(
                            "invalid_psgc",
                            "fatal",
                            f"Facility {code} has no valid {label} PSGC code.",
                            {"field": field, "value": value},
                            row.row_reference,
                        )
                    )
                    rejected += 1
                    rejected_rows.add(row.row_reference)
                    break
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
            code = clean_text(payload.get("health_facility_code"))
            name = clean_text(payload.get("facility_name"))
            if not code or not name:
                continue
            major = clean_text(payload.get("ownership_major"))
            is_government = major == "Government"
            subtype = payload["facility_subtype"]
            facility_type = clean_text(payload.get("health_facility_type")) or "Health Facility"
            address_parts = [
                clean_text(payload.get("barangay_name")),
                clean_text(payload.get("city_municipality_name")),
                clean_text(payload.get("province_name")),
            ]
            licenses: list[LicenseData] = []
            if payload.get("licensing_status") == "With License":
                licenses.append(
                    LicenseData(
                        issuing_authority="Department of Health",
                        license_type=facility_type,
                        source_status="With License",
                        valid_until=(
                            date.fromisoformat(payload["license_validity_date"])
                            if payload.get("license_validity_date")
                            else None
                        ),
                    )
                )
            candidates.append(
                FacilityCandidate(
                    source_record_key=code,
                    source_entity_id=code,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="health_facility",
                    facility_subtype=subtype,
                    facility_kind="facility",
                    ownership="government" if is_government else "private",
                    ownership_type=payload["ownership_type"],
                    operator_type=payload["ownership_type"],
                    inclusion_class=(
                        "GOVERNMENT_FACILITY"
                        if is_government
                        else "PRIVATE_PUBLIC_SERVICE_PROVIDER"
                    ),
                    public_access_class="UNKNOWN",
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=", ".join(part for part in address_parts if part) or None,
                        psgc_code=(
                            payload.get("barangay_psgc")
                            or payload.get("city_municipality_psgc")
                            or payload.get("province_psgc")
                            or payload.get("region_psgc")
                        ),
                        review_status="source_supplied",
                    ),
                    health=HealthData(
                        doh_facility_id=code,
                        facility_major_type=clean_text(payload.get("facility_major_type")),
                        facility_type_detail=facility_type,
                        facility_category=facility_type,
                        ownership_subclassification=clean_text(
                            payload.get("ownership_subclassification")
                        ),
                        licensing_status=clean_text(payload.get("licensing_status")),
                        bed_capacity=payload.get("bed_capacity"),
                    ),
                    licenses=licenses,
                    enrichment_only=True,
                )
            )
        return candidates
