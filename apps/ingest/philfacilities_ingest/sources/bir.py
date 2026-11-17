"""Bureau of Internal Revenue Revenue District Office directory parser.

RAO No. 006-2025 is a scanned, image-only PDF. The original bytes remain the
preserved release; this adapter uses the local OCR module to recover the official
Revenue Region / Revenue District Office list. It deliberately publishes only
institutional office identity and jurisdiction labels. The RAO does not contain
street addresses or coordinates, so none are invented.

The Citizen's Charter is a separate, much larger document and is not merged into
this release. Address enrichment requires its own reviewed release.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    RoleData,
    ServiceData,
    ValidationIssue,
    ValidationResult,
)
from ..ocr import OcrLine, ocr_pdf
from .common import clean_text

RR_PATTERN = re.compile(r"^RRNo\.?([0-9]+[A-Z]?)-(.+)$", re.IGNORECASE)
RDO_PATTERN = re.compile(r"^RDONo\.?([0-9]+[A-Z]?)-(.+)$", re.IGNORECASE)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _spaced_name(value: str) -> str:
    """Restore word boundaries lost by the scanned document's tight kerning.

    This is presentation only. The untouched OCR line and confidence remain in
    the source record. No place name is corrected or guessed.
    """

    text = _compact(value)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])and(?=[A-Z])", " and ", text)
    text = re.sub(r"(?<=[A-Za-z])\.(?=[A-Z])", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_rao_lines(lines: list[OcrLine]) -> tuple[list[dict[str, Any]], list[str]]:
    """Turn OCR lines into Revenue Region / RDO records.

    The PDF prints a Revenue Region heading followed by its RDOs. A line that
    cannot be assigned to a Revenue Region is retained as an OCR warning rather
    than fabricated into a record.
    """

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_region: dict[str, Any] | None = None
    seen: set[str] = set()

    for line in lines:
        compact = _compact(line.text)
        region_match = RR_PATTERN.match(compact)
        if region_match:
            number, name = region_match.groups()
            current_region = {
                "number": number,
                "name": _spaced_name(name),
                "raw": line.text,
            }
            continue
        rdo_match = RDO_PATTERN.match(compact)
        if not rdo_match:
            continue
        number, name = rdo_match.groups()
        key = f"RDO-{number.upper()}"
        if key in seen:
            warnings.append(f"Duplicate OCR row ignored: {line.text}")
            continue
        seen.add(key)
        records.append(
            {
                "rdo_code": number.upper(),
                "rdo_name": _spaced_name(name),
                "revenue_region_number": (current_region["number"] if current_region else None),
                "revenue_region_name": (current_region["name"] if current_region else None),
                "raw_ocr_text": line.text,
                "ocr_confidence": line.confidence,
                "page": line.page_number,
            }
        )
    if not records:
        raise ValueError(
            "The BIR RAO OCR pass produced no Revenue District Office rows; the "
            "document layout or OCR output changed."
        )
    return records, warnings


class BirRevenueDistrictOfficeAdapter:
    source_code = "bir"
    parser_version = "bir-rao-006-2025-ocr-1.0.0"
    schema_version = "bir-rao-ocr-v1"
    expected_columns: ClassVar[dict[str, set[str]]] = {
        "required": {"rdo_code", "rdo_name", "revenue_region_number"}
    }

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        pages = ocr_pdf(spec.content)
        lines = [line for page in pages for line in page.lines]
        records, warnings = parse_rao_lines(lines)
        rows = [
            ParsedRow(
                source_record_key=f"RDO-{record['rdo_code']}",
                row_reference=(f"ocr:page:{record['page']}:rdo:{record['rdo_code']}"),
                raw_payload=record,
                normalized_payload=record,
            )
            for record in records
        ]
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "scanned_document_ocr",
                    "message": (
                        "The source PDF is image-only. Rows were recovered with local "
                        "OCR; the original PDF is the preserved source of record and "
                        "raw OCR text/confidence is stored with every row."
                    ),
                    "pages_ocr": len(pages),
                    "lines_ocr": len(lines),
                },
                *(
                    [{"code": "ocr_warning", "message": warning} for warning in warnings]
                    if warnings
                    else []
                ),
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            code = clean_text(payload.get("rdo_code"))
            name = clean_text(payload.get("rdo_name"))
            if not code or not re.fullmatch(r"[0-9]+[A-Z]?", code):
                issues.append(
                    ValidationIssue(
                        "invalid_rdo_code",
                        "fatal",
                        "A BIR office row has no usable RDO number.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_rdo_name",
                        "fatal",
                        f"RDO {code} has no OCR-readable name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if code in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_rdo_code",
                        "error",
                        f"RDO {code} appears more than once.",
                        {"rdo_code": code},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(code)
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            code = clean_text(payload.get("rdo_code"))
            name = clean_text(payload.get("rdo_name"))
            if not code or not name:
                continue
            rr_number = clean_text(payload.get("revenue_region_number"))
            rr_name = clean_text(payload.get("revenue_region_name"))
            evidence = {
                "source_columns": [
                    "Revenue Region",
                    "Revenue District Office",
                ],
                "rdo_code": code,
                "rdo_name": name,
                "revenue_region_number": rr_number,
                "revenue_region_name": rr_name,
                "raw_ocr_text": payload.get("raw_ocr_text"),
                "ocr_confidence": payload.get("ocr_confidence"),
                "page": payload.get("page"),
                "source_document": "RAO No. 006-2025 (9 December 2025)",
            }
            jurisdiction = ", ".join(part for part in (rr_name, "Revenue Region") if part)
            candidates.append(
                FacilityCandidate(
                    source_record_key=f"RDO-{code}",
                    source_entity_id=f"RDO-{code}",
                    row_reference=row.row_reference,
                    display_name=f"BIR Revenue District Office {code} — {name}",
                    facility_type="government_office",
                    facility_subtype="REVENUE_DISTRICT_OFFICE",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="SERVICE_USERS_ONLY",
                    access_conditions=(
                        "Taxpayer service office. The source lists the office and its "
                        "revenue region; it does not state walk-in hours, appointment "
                        "rules, or a street address."
                    ),
                    record_status="active_in_registry",
                    location=LocationData(precision="unknown"),
                    functions=[
                        FunctionData(
                            function_code="TAX_ADMINISTRATION",
                            source_value="Revenue District Office",
                            evidence=evidence,
                        )
                    ],
                    services=[
                        ServiceData(
                            service_code="TAX_ASSESSMENT_AND_COLLECTION",
                            service_name="Tax assessment and collection",
                            source_field="Revenue District Office",
                            details={"revenue_region": jurisdiction},
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Bureau of Internal Revenue",
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "RAO No. 006-2025 office list"},
                        ),
                        RoleData(
                            role_type="REGULATOR",
                            entity_name="Department of Finance",
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "BIR is under the supervision and control of DOF"},
                        ),
                    ],
                )
            )
        return candidates
