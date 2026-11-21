"""DepEd Project Bukas — Enrollment in SY 2024-2025.

Project Bukas is DepEd's public education-data release. The enrollment module
publishes one wide CSV row per school with the official six-digit school ID,
sector, school management, administrative location, offering flags, and
enrollment counts by grade/strand and sex.

The official ``deped.gov.ph`` URL returns HTTP 403 to automated clients. The
adapter therefore accepts the same artifact from the preserved Wayback copy and
pins its SHA-256. The release is **enrichment-only**: rows link to existing
DepEd facilities by exact school ID and fill only missing school-profile values.
They never rename a facility, replace an established sector/management value, or
invent coordinates or PSGC codes the source does not contain. Enrollment counts
remain in the preserved raw release; no enrollment observations are derived.

The source retains enrollment zeroes for levels the school reports as offered.
A zero in a level the school does not offer is not a zero enrollment count, so
those non-applicable cells are not meaningful even in the raw data. Any non-zero
count is retained in the raw release even if the offering flag is false, because
the source's own values conflict and the reported value must not be lost.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from typing import Any

from philfacilities_api.taxonomy import DISCOVERY_CANDIDATE

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
from .common import clean_text, normalise_code, parse_bool, parse_int
from .deped_masterlist import SECTOR_CLASSIFICATION, SECTOR_NORMALIZED

# Acquisition ---------------------------------------------------------------

OFFICIAL_ZIP_URL = "https://www.deped.gov.ph/wp-content/uploads/Enrollment-in-SY-2024-2025.zip"
ARCHIVE_ZIP_URL = (
    "https://web.archive.org/web/20251118093101id_/"
    "https://www.deped.gov.ph/wp-content/uploads/Enrollment-in-SY-2024-2025.zip"
)
DATASET_PAGE_URL = "https://www.deped.gov.ph/machine-ready-files/"
CSV_NAME = "Enrollment in SY 2024-2025/enrollment_2024-25.csv"
EXPECTED_ZIP_SHA256 = "fd5dd74a62b828608c62335b7c324ddf05be58e3f05465fee68854795f5b1a92"
EXPECTED_ROWS = 60_129
MAX_ZIP_BYTES = 16 * 1024 * 1024

REQUIRED_COLUMNS = {
    "school_id",
    "school_name",
    "region",
    "division",
    "province",
    "school_district",
    "legislative_district",
    "municipality",
    "barangay",
    "street_address",
    "sector",
    "school_management",
    "annex_status",
    "offers_es",
    "offers_jhs",
    "offers_shs",
}

ENROLLMENT_COLUMNS = (
    "kinder_male",
    "kinder_female",
    "g1_male",
    "g1_female",
    "g2_male",
    "g2_female",
    "g3_male",
    "g3_female",
    "g4_male",
    "g4_female",
    "g5_male",
    "g5_female",
    "g6_male",
    "g6_female",
    "esng_male",
    "esng_female",
    "g7_male",
    "g7_female",
    "g8_male",
    "g8_female",
    "g9_male",
    "g9_female",
    "g10_male",
    "g10_female",
    "jhsng_male",
    "jhsng_female",
    "g11_abm_male",
    "g11_abm_female",
    "g11_arts_male",
    "g11_arts_female",
    "g11_gas_male",
    "g11_gas_female",
    "g11_humss_male",
    "g11_humss_female",
    "g11_maritime_male",
    "g11_maritime_female",
    "g11_sports_male",
    "g11_sports_female",
    "g11_stem_male",
    "g11_stem_female",
    "g11_tvl_male",
    "g11_tvl_female",
    "g11_unique_male",
    "g11_unique_female",
    "g12_abm_male",
    "g12_abm_female",
    "g12_arts_male",
    "g12_arts_female",
    "g12_gas_male",
    "g12_gas_female",
    "g12_humss_male",
    "g12_humss_female",
    "g12_maritime_male",
    "g12_maritime_female",
    "g12_sports_male",
    "g12_sports_female",
    "g12_stem_male",
    "g12_stem_female",
    "g12_tvl_male",
    "g12_tvl_female",
    "g12_unique_male",
    "g12_unique_female",
)

# The source's sector cell names the sector; PSO is Philippine Schools
# Overseas. Its ownership is not stated by the sector label, so it remains
# unclassified rather than being guessed as private or government.
SECTOR_NORMALIZED_BUKAS = {
    **SECTOR_NORMALIZED,
    "suc/luc": "suc_luc",
    "pso": "pso",
}

# Project Bukas uses display labels for school management. Map them onto the
# existing DepEd masterlist vocabulary already used by school profiles.
MANAGEMENT_NORMALIZED = {
    "deped": "deped_managed",
    "deped managed": "deped_managed",
    "local government": "local_government",
    "suc": "suc_managed",
    "luc": "luc",
    "dost": "dost_managed",
    "dost managed": "dost_managed",
    "other ga": "other_ga_managed",
    "other ga managed": "other_ga_managed",
    "non-sectarian": "non_sectarian",
    "sectarian": "sectarian",
    "international school": "local_international_school",
    "pso": "pso",
}

MANAGEMENT_OPERATOR = {
    "deped_managed": "NATIONAL_GOVERNMENT",
    "local_government": "LOCAL_GOVERNMENT",
    "suc_managed": "PUBLIC_EDUCATIONAL_INSTITUTION",
    "luc": "PUBLIC_EDUCATIONAL_INSTITUTION",
    "dost_managed": "NATIONAL_GOVERNMENT",
    "other_ga_managed": "NATIONAL_GOVERNMENT",
    "non_sectarian": "PRIVATE_UNSPECIFIED",
    "sectarian": "PRIVATE_UNSPECIFIED",
    "local_international_school": "PRIVATE_UNSPECIFIED",
}


def _read_csv(content: bytes) -> bytes:
    if content.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [name for name in archive.namelist() if name.endswith(".csv")]
            if CSV_NAME in names:
                return archive.read(CSV_NAME)
            if len(names) == 1:
                return archive.read(names[0])
            raise ValueError(
                "DepEd Project Bukas enrollment archive does not contain the expected "
                f"{CSV_NAME!r}; observed {sorted(archive.namelist())}"
            )
    return content


def _rows_from_csv(content: bytes) -> list[dict[str, str]]:
    raw = _read_csv(content)
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or ())
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(
            f"DepEd Project Bukas enrollment CSV schema changed: missing columns {sorted(missing)}"
        )
    missing_counts = set(ENROLLMENT_COLUMNS) - columns
    if missing_counts:
        raise ValueError(
            "DepEd Project Bukas enrollment CSV is missing grade/sex columns: "
            f"{sorted(missing_counts)}"
        )
    return list(reader)


def parse_bukas_csv(content: bytes) -> list[dict[str, str]]:
    raw = _read_csv(content)
    if not content.startswith(b"PK") or hashlib.sha256(content).hexdigest() != EXPECTED_ZIP_SHA256:
        raise ValueError(
            "DepEd Project Bukas enrollment archive checksum changed; expected "
            f"{EXPECTED_ZIP_SHA256}."
        )
    rows = _rows_from_csv(raw)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(
            "DepEd Project Bukas enrollment row count changed; expected "
            f"{EXPECTED_ROWS}, observed {len(rows)}."
        )
    return rows


def fetch_deped_bukas_enrollment(
    acquirer: HttpAcquirer,
) -> tuple[bytes, dict[str, Any]]:
    """Fetch the official ZIP, falling back to the preserved Wayback copy."""

    official = acquirer.fetch(OFFICIAL_ZIP_URL, max_bytes=MAX_ZIP_BYTES)
    if (
        official.status_code == 200
        and official.content.startswith(b"PK")
        and hashlib.sha256(official.content).hexdigest() == EXPECTED_ZIP_SHA256
    ):
        return official.content, {
            "http_status": official.status_code,
            "acquired_from": OFFICIAL_ZIP_URL,
            "zip_sha256": EXPECTED_ZIP_SHA256,
            "csv_name": CSV_NAME,
            "expected_rows": EXPECTED_ROWS,
        }
    archive = acquirer.fetch(ARCHIVE_ZIP_URL, max_bytes=MAX_ZIP_BYTES)
    if archive.status_code != 200 or not archive.content.startswith(b"PK"):
        raise AcquisitionError(
            "DepEd Project Bukas enrollment data is unavailable from both the official "
            f"URL (HTTP {official.status_code}) and the preserved archive "
            f"(HTTP {archive.status_code})."
        )
    digest = hashlib.sha256(archive.content).hexdigest()
    if digest != EXPECTED_ZIP_SHA256:
        raise AcquisitionError(
            "DepEd Project Bukas enrollment archive checksum changed; refusing the new "
            f"artifact (expected {EXPECTED_ZIP_SHA256}, observed {digest})."
        )
    return archive.content, {
        "http_status": archive.status_code,
        "acquired_from": ARCHIVE_ZIP_URL,
        "official_http_status": official.status_code,
        "zip_sha256": digest,
        "csv_name": CSV_NAME,
        "expected_rows": EXPECTED_ROWS,
    }


def _address_text(payload: dict[str, Any]) -> str | None:
    """Compose a postal address from the source's own location cells.

    No value is invented. Duplicate cells are dropped, and PSO rows use the
    overseas city/country columns that the publisher documents for those rows.
    """

    region = clean_text(payload.get("region"))
    if (region or "").casefold() == "pso":
        parts = [
            clean_text(payload.get("street_address")),
            clean_text(payload.get("school_district")),
            clean_text(payload.get("division")),
        ]
    else:
        parts = [
            clean_text(payload.get("street_address")),
            clean_text(payload.get("barangay")),
            clean_text(payload.get("municipality")),
            clean_text(payload.get("province")),
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


def _offering_flags(payload: dict[str, Any]) -> dict[str, bool | None]:
    return {
        "es": parse_bool(payload.get("offers_es")),
        "jhs": parse_bool(payload.get("offers_jhs")),
        "shs": parse_bool(payload.get("offers_shs")),
    }


class DepEdBukasEnrollmentAdapter:
    source_code = "deped"
    parser_version = "deped-project-bukas-enrollment-1.0.0"
    schema_version = "deped-project-bukas-enrollment-sy2024-2025-v1"
    # A 60k-row enrichment release touches every school. The runner bounds the
    # session between flush batches instead of pinning all touched facilities.
    bulk_apply_reset = True

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows = parse_bukas_csv(spec.content)
        parsed: list[ParsedRow] = []
        for index, row in enumerate(rows, start=2):
            school_id = normalise_code(row.get("school_id"))
            if not school_id:
                continue
            parsed.append(
                ParsedRow(
                    source_record_key=school_id,
                    row_reference=f"csv_row:{index}",
                    raw_payload=dict(row),
                    normalized_payload={
                        **row,
                        "school_id": school_id,
                        "sector_normalized": SECTOR_NORMALIZED_BUKAS.get(
                            (clean_text(row.get("sector")) or "").casefold()
                        ),
                        "management_normalized": MANAGEMENT_NORMALIZED.get(
                            (clean_text(row.get("school_management")) or "").casefold()
                        ),
                    },
                )
            )
        if not parsed:
            raise ValueError("DepEd Project Bukas enrollment CSV returned no school rows.")
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "enrichment_only_release",
                    "message": (
                        "Rows link by exact six-digit school ID and fill only missing "
                        "school-profile values. They never rename a facility, replace "
                        "an established sector/management value, or create an "
                        "unmatched school."
                    ),
                },
                {
                    "code": "no_coordinates_or_psgc",
                    "message": (
                        "The enrollment file carries administrative location names but "
                        "no coordinates or PSGC codes. No location point is inferred."
                    ),
                },
                {
                    "code": "enrollment_zero_semantics",
                    "message": (
                        "The source reports enrollment counts by grade/strand and sex, "
                        "including zeros for levels the school offers. Counts stay in "
                        "the preserved raw release; no enrollment observations are "
                        "derived into canonical records."
                    ),
                },
                {
                    "code": "archived_public_copy",
                    "message": (
                        "The official deped.gov.ph URL returns HTTP 403 to automated "
                        "clients. The preserved Wayback copy of the same ZIP is "
                        "checksum-verified before parsing."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        rejected_rows: set[str] = set()
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(payload.get("school_id"))
            sector = payload.get("sector_normalized")
            name = clean_text(payload.get("school_name"))
            if not school_id or not re.fullmatch(r"\d{6}", school_id):
                issues.append(
                    ValidationIssue(
                        "invalid_school_id",
                        "fatal",
                        "Row does not carry a six-digit school ID.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            if school_id in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_school_id",
                        "fatal",
                        f"School ID {school_id} appears more than once.",
                        {"school_id": school_id},
                        row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            seen.add(school_id)
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_school_name",
                        "fatal",
                        f"School {school_id} has no school-name text.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            if sector not in SECTOR_NORMALIZED_BUKAS.values():
                issues.append(
                    ValidationIssue(
                        "unknown_sector",
                        "fatal",
                        f"School {school_id} has an unrecognized sector.",
                        {"school_id": school_id, "sector": payload.get("sector")},
                        row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
                continue
            if payload.get("management_normalized") is None:
                issues.append(
                    ValidationIssue(
                        "unknown_school_management",
                        "warning",
                        f"School {school_id} has an unrecognized management value.",
                        {
                            "school_id": school_id,
                            "school_management": payload.get("school_management"),
                        },
                        row.row_reference,
                    )
                )
            for column in ("offers_es", "offers_jhs", "offers_shs"):
                if parse_bool(payload.get(column)) is None:
                    issues.append(
                        ValidationIssue(
                            "invalid_offering_flag",
                            "warning",
                            f"School {school_id} has an unreadable {column} value.",
                            {"school_id": school_id, column: payload.get(column)},
                            row.row_reference,
                        )
                    )
            invalid_count = next(
                (
                    column
                    for column in ENROLLMENT_COLUMNS
                    if clean_text(payload.get(column)) is not None
                    and (
                        parse_int(payload.get(column)) is None
                        or (parse_int(payload.get(column)) or 0) < 0
                    )
                ),
                None,
            )
            if invalid_count is not None:
                issues.append(
                    ValidationIssue(
                        "invalid_learner_count",
                        "fatal",
                        f"School {school_id} has an invalid count in {invalid_count}.",
                        {
                            "school_id": school_id,
                            "column": invalid_count,
                            "value": payload.get(invalid_count),
                        },
                        row.row_reference,
                    )
                )
                rejected += 1
                rejected_rows.add(row.row_reference)
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
            school_id = normalise_code(payload.get("school_id"))
            sector = payload.get("sector_normalized")
            name = clean_text(payload.get("school_name"))
            if not school_id or sector not in SECTOR_NORMALIZED_BUKAS.values() or not name:
                continue
            management = payload.get("management_normalized")
            if sector == "pso":
                # PSO is a sector label, not ownership evidence.
                ownership, ownership_type, inclusion_class = (
                    "unknown",
                    "UNKNOWN",
                    DISCOVERY_CANDIDATE,
                )
            else:
                ownership, ownership_type, inclusion_class = SECTOR_CLASSIFICATION[sector]
            flags = _offering_flags(payload)
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
                    location=LocationData(address_text=_address_text(payload)),
                    school=SchoolData(
                        deped_school_id=school_id,
                        sector=sector,
                        school_management=management,
                        division=clean_text(payload.get("division")),
                        district=clean_text(payload.get("school_district")),
                        legislative_district=clean_text(payload.get("legislative_district")),
                        offers_es=flags["es"],
                        offers_jhs=flags["jhs"],
                        offers_shs=flags["shs"],
                    ),
                    enrichment_only=True,
                )
            )
        return candidates
