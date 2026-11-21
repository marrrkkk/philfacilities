"""DepEd Masterlist of Schools SY 2020-2021 — tabular detail adapter.

The official DepEd masterlist is published as a PDF. A machine-readable CSV
transcription is distributed through the BetterGov Open Data Portal (dataset
41), attributed to DepEd and licensed CC BY 4.0. It carries the same 60,924
six-digit BEIS IDs plus administrative fields that are clipped or absent in the
PDF: division, district, legislative district, settlement type,
school-management class, and the combined offering classification.

This is an **enrichment** source. Rows link to existing facilities by exact
six-digit BEIS School ID and fill only missing profile values. The adapter
never renames a facility, never changes its canonical subtype, and never
creates a facility for an unmatched ID. The combined offering string is kept
verbatim and the three offering booleans are derived only from the explicit
source categories.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
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

# Acquisition ---------------------------------------------------------------

BETTERGOV_DATASET_ID = 41
BETTERGOV_DATASET_URL = "https://data.bettergov.ph/datasets/41"
KAGGLE_DATASET_URL = (
    "https://www.kaggle.com/datasets/bendlikeabamboo/"
    "philippines-deped-basic-education-master-list-2020"
)
KAGGLE_DOWNLOAD_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "bendlikeabamboo/philippines-deped-basic-education-master-list-2020"
)
CSV_NAME = "basic_education_institutions.csv"
CSV_SHA256 = "8ff9e4483b3b32453819f14a1a5260ceffbcdbb972395c9e95241dcb3e42b3fd"
CSV_BYTES = 10_397_735
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024

REQUIRED_COLUMNS = {
    "region",
    "division",
    "district",
    "beis_school_id",
    "school_name",
    "street_address",
    "municipality",
    "legislative_district",
    "barangay",
    "sector",
    "settlement_type",
    "school_subclassification",
    "modified_cultural_offering_classification",
}

SECTOR_CLASSIFICATION = {
    "public": ("government", "GOVERNMENT_UNSPECIFIED", "GOVERNMENT_FACILITY"),
    "private": (
        "private",
        "PRIVATE_UNSPECIFIED",
        "PRIVATE_PUBLIC_SERVICE_PROVIDER",
    ),
    "suc_luc": (
        "government",
        "PUBLIC_EDUCATIONAL_INSTITUTION",
        "GOVERNMENT_FACILITY",
    ),
}

# The source's ``school_subclassification`` states who manages the school.
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

# Explicit combined offering categories; anything else leaves the booleans
# unknown rather than guessing.
OFFERING_LEVELS = {
    "purely_es": (True, False, False),
    "es_and_jhs": (True, True, False),
    "purely_jhs": (False, True, False),
    "jhs_with_shs": (False, True, True),
    "purely_shs": (False, False, True),
    "all_offering": (True, True, True),
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
                "DepEd masterlist archive does not contain the expected "
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
        raise ValueError(f"DepEd masterlist CSV schema changed: missing columns {sorted(missing)}")
    return list(reader)


def parse_masterlist_csv(content: bytes) -> list[dict[str, str]]:
    raw = _read_csv(content)
    if len(raw) != CSV_BYTES or hashlib.sha256(raw).hexdigest() != CSV_SHA256:
        raise ValueError(
            f"DepEd masterlist CSV checksum changed; expected {CSV_SHA256} ({CSV_BYTES} bytes)."
        )
    return _rows_from_csv(raw)


def fetch_deped_masterlist_detail(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch the public Kaggle mirror of the BetterGov dataset 41 CSV."""

    response = acquirer.fetch(KAGGLE_DOWNLOAD_URL, max_bytes=MAX_ARCHIVE_BYTES)
    if response.status_code != 200 or not response.content.startswith(b"PK"):
        raise AcquisitionError(
            f"DepEd masterlist detail archive is unavailable (HTTP {response.status_code})."
        )
    raw = _read_csv(response.content)
    if len(raw) != CSV_BYTES or hashlib.sha256(raw).hexdigest() != CSV_SHA256:
        raise AcquisitionError(
            "DepEd masterlist detail CSV checksum changed; refusing the new artifact."
        )
    return response.content, {
        "http_status": response.status_code,
        "acquired_from": KAGGLE_DOWNLOAD_URL,
        "dataset_page": BETTERGOV_DATASET_URL,
        "csv_name": CSV_NAME,
        "csv_sha256": CSV_SHA256,
    }


class DepEdMasterlistDetailAdapter:
    source_code = "deped"
    parser_version = "deped-masterlist-detail-csv-1.0.0"
    schema_version = "deped-masterlist-sy2020-2021-detail-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows = parse_masterlist_csv(spec.content)
        parsed: list[ParsedRow] = []
        for index, row in enumerate(rows, start=2):
            school_id = normalise_code(row.get("beis_school_id"))
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
                        "sector_normalized": clean_text(row.get("sector")).casefold(),
                    },
                )
            )
        if not parsed:
            raise ValueError("DepEd masterlist detail CSV returned no school rows.")
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "enrichment_only_release",
                    "message": (
                        "Rows link by exact six-digit BEIS School ID and fill only "
                        "missing school-profile fields. They never rename a facility, "
                        "replace an established value, or create an unmatched school."
                    ),
                },
                {
                    "code": "derived_offering_booleans",
                    "message": (
                        "The source's combined offering classification is retained "
                        "verbatim; elementary, junior-high and senior-high flags are "
                        "derived only from its explicit categories."
                    ),
                },
                {
                    "code": "tabular_transcription",
                    "message": (
                        "The official masterlist is a PDF. This CC BY 4.0 CSV "
                        "transcription is published through BetterGov Open Data "
                        "Portal dataset 41 and attributed to DepEd."
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
                        "Row does not carry a six-digit BEIS School ID.",
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
            if sector not in SECTOR_CLASSIFICATION:
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
            if not school_id or sector not in SECTOR_CLASSIFICATION or not name:
                continue
            ownership, ownership_type, inclusion_class = SECTOR_CLASSIFICATION[sector]
            management = clean_text(payload.get("school_subclassification"))
            management_key = (management or "").casefold()
            offering = clean_text(payload.get("modified_cultural_offering_classification"))
            offering_key = (offering or "").casefold()
            offers = OFFERING_LEVELS.get(offering_key, (None, None, None))
            address = clean_text(payload.get("street_address"))
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
                    operator_type=MANAGEMENT_OPERATOR.get(management_key),
                    inclusion_class=inclusion_class,
                    record_status="active_in_registry",
                    location=LocationData(address_text=address),
                    school=SchoolData(
                        deped_school_id=school_id,
                        sector=sector,
                        school_management=management,
                        division=clean_text(payload.get("division")),
                        district=clean_text(payload.get("district")),
                        legislative_district=clean_text(payload.get("legislative_district")),
                        settlement_type=clean_text(payload.get("settlement_type")),
                        offering_classification=offering,
                        offers_es=offers[0],
                        offers_jhs=offers[1],
                        offers_shs=offers[2],
                    ),
                    enrichment_only=True,
                )
            )
        return candidates
