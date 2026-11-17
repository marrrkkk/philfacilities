"""National Library of the Philippines public-library directory parser.

The official PDF is an annual directory of libraries affiliated with the NLP's
Public Libraries Division. It is a government work: RA 8293 section 176 provides
that no copyright subsists in a work of the Government of the Philippines, while
prior approval may be required for commercial use. PhilFacilities publishes the
institutional facility fields with attribution and does not republish librarian
personal contact fields that are not needed for facility identification.

The parser preserves the source column names, library ID, status and affiliation
date. It does not infer coordinates, PSGC codes, current opening hours or
operational state beyond the directory's own status value.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any

import pdfplumber

from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text, normalise_code

SOURCE_COLUMNS = (
    "NO.",
    "PHILIPPINE PUBLIC LIBRARY ID",
    "REGION",
    "LOCATION",
    "TYPE OF PUBLIC LIBRARY",
    "NAME OF LIBRARY",
    "ADDRESS",
    "TELEPHONE NUMBER",
    "STATUS",
    "DATE AFFILIATED",
)

LIBRARY_SUBTYPES = {
    "Regional": "REGIONAL_LIBRARY",
    "Provincial": "PROVINCIAL_LIBRARY",
    "City": "CITY_LIBRARY",
    "Municipal": "MUNICIPAL_LIBRARY",
    "Barangay Reading Center": "BARANGAY_READING_CENTER",
    "Congressional": "CONGRESSIONAL_LIBRARY",
    "Locally Funded Projects": "LOCALLY_FUNDED_LIBRARY",
}

STATUS_MAP = {
    "active": "active_in_registry",
    "inactive": "inactive_in_registry",
    "closed": "inactive_in_registry",
}


def _cell(value: Any) -> str:
    text = clean_text(value) or ""
    return re.sub(r"\s+", " ", text).strip()


def _affiliation_date(value: str) -> date | None:
    text = clean_text(value)
    if not text or text == "-":
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class NlpPublicLibraryPdfAdapter:
    source_code = "nlp"
    parser_version = "nlp-public-libraries-1.0.0"
    schema_version = "nlp-public-libraries-pdf-v1"
    expected_columns = {"required": {"PHILIPPINE PUBLIC LIBRARY ID", "NAME OF LIBRARY"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows: list[ParsedRow] = []
        pages_without_table: list[int] = []
        with pdfplumber.open(io.BytesIO(spec.content)) as document:
            for page_number, page in enumerate(document.pages, start=1):
                page_rows = 0
                for table in page.extract_tables():
                    for cells in table:
                        if not cells or len(cells) < len(SOURCE_COLUMNS):
                            continue
                        number = _cell(cells[0])
                        if not re.fullmatch(r"\d+", number):
                            continue
                        record = {
                            column: _cell(cells[index])
                            for index, column in enumerate(SOURCE_COLUMNS)
                        }
                        record["_page"] = page_number
                        record["_row"] = number
                        library_id = normalise_code(record["PHILIPPINE PUBLIC LIBRARY ID"])
                        if not library_id:
                            continue
                        rows.append(
                            ParsedRow(
                                source_record_key=library_id,
                                row_reference=f"pdf:page:{page_number}:row:{number}",
                                raw_payload=record,
                                normalized_payload=record,
                            )
                        )
                        page_rows += 1
                if page_rows == 0:
                    pages_without_table.append(page_number)
        if not rows:
            raise ValueError(
                "The NLP directory PDF produced no public-library rows; the layout or "
                "access state changed."
            )
        warnings: list[dict[str, Any]] = [
            {
                "code": "no_coordinates",
                "message": (
                    "The NLP directory supplies postal addresses but no coordinates or PSGC "
                    "codes. Libraries remain unmapped until an authorized geocoder is used."
                ),
            }
        ]
        if pages_without_table:
            warnings.append(
                {
                    "code": "pages_without_rows",
                    "message": (
                        "Pages without parsed library rows were retained in the raw file: "
                        f"{pages_without_table[:20]}"
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
            library_id = normalise_code(payload.get("PHILIPPINE PUBLIC LIBRARY ID"))
            name = clean_text(payload.get("NAME OF LIBRARY"))
            if not library_id:
                issues.append(
                    ValidationIssue(
                        "missing_library_id",
                        "fatal",
                        "A public-library row has no Philippine Public Library ID.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_library_name",
                        "fatal",
                        f"Library {library_id} has no name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if library_id in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_library_id",
                        "error",
                        f"Library ID {library_id} appears more than once.",
                        {"library_id": library_id},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(library_id)
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            library_id = normalise_code(payload.get("PHILIPPINE PUBLIC LIBRARY ID"))
            name = clean_text(payload.get("NAME OF LIBRARY"))
            if not library_id or not name:
                continue
            library_type = clean_text(payload.get("TYPE OF PUBLIC LIBRARY")) or ""
            subtype = LIBRARY_SUBTYPES.get(library_type, "OTHER_LIBRARY")
            status = (clean_text(payload.get("STATUS")) or "").lower()
            region = clean_text(payload.get("REGION"))
            location = clean_text(payload.get("LOCATION"))
            address = clean_text(payload.get("ADDRESS"))
            address_parts = [part for part in (address, location, region) if part]
            affiliation = _affiliation_date(payload.get("DATE AFFILIATED") or "")
            evidence = {
                "source_columns": list(SOURCE_COLUMNS),
                "philippine_public_library_id": library_id,
                "region": region,
                "location": location,
                "type_of_public_library": library_type,
                "status": clean_text(payload.get("STATUS")),
                "date_affiliated": affiliation.isoformat() if affiliation else None,
                "page": payload.get("_page"),
            }
            candidates.append(
                FacilityCandidate(
                    source_record_key=library_id,
                    source_entity_id=library_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="library",
                    facility_subtype=subtype,
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOVERNMENT_UNSPECIFIED",
                    operator_type="GOVERNMENT_UNSPECIFIED",
                    public_access_class="PUBLIC_FREE",
                    record_status=STATUS_MAP.get(status, "unknown"),
                    location=LocationData(
                        address_text=", ".join(address_parts) or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="PUBLIC_LIBRARY",
                            source_value=library_type or None,
                            valid_from=affiliation,
                            evidence=evidence,
                        )
                    ],
                )
            )
        return candidates
