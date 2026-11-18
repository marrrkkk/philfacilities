"""DepEd Masterlist of Schools, SY 2020-2021 PDF adapter.

The official file is a 544-page PDF published by the Department of Education.
It carries the BEIS School ID and an explicit per-school Sector
(``Public``, ``Private``, or ``SUCs/LUCs``), which the EBEIS result pages do
not expose reliably. The adapter is intentionally an **enrichment** source: it
links rows to existing DepEd facilities by exact BEIS ID and fills only
missing or placeholder values. It never renames a facility and never replaces
an existing school profile or canonical classification.

The PDF has one visual row per school and a text layer with semantic line
order. Reading is deliberately fast:

* one full-page text extraction to locate the six-digit BEIS IDs;
* one ``get_charbox`` call per ID (not per character) for row y-anchors;
* one ``get_text_bounded`` call per column, zipped to the IDs;
* per-row band re-extraction only for the few pages where an empty cell
  (mostly Barangay) collapses a column's line count.

Names, street addresses, and municipalities can touch adjacent columns in the
published layout. Only the BEIS ID and Sector are used to enrich canonical
records; the other extracted values are retained as raw context.
"""

from __future__ import annotations

import re
from typing import Any

import pypdfium2 as pdfium

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

OFFICIAL_PDF_URL = (
    "https://deped.gov.ph/wp-content/uploads/2021/06/"
    "SY-2020-2021-Masterlist-of-Schools-Address-only-1-1.pdf"
)
ARCHIVE_PDF_URL = (
    "https://web.archive.org/web/20250418094400if_/https://www.deped.gov.ph/"
    "wp-content/uploads/2021/06/SY-2020-2021-Masterlist-of-Schools-Address-only-1-1.pdf"
)
DATASET_PAGE_URL = (
    "https://data.gov.ph/index/public/dataset/"
    "SY%202020-2021%20Masterlist%20of%20Schools/5dpij7nd-uhrj-wk5l-xv2h-q5pgkiccv9ag"
)
MAX_PDF_BYTES = 32 * 1024 * 1024

# Layout --------------------------------------------------------------------

# x ranges are measured from the published page (792 x 612 points). The BEIS
# ID column is right-aligned around x=201.6; the school-name column begins at
# 202.9. The Sector column ends before the overlapping Urban/Rural and
# Subclassification text begins.
COLUMNS: tuple[tuple[str, float, float, str], ...] = (
    ("region", 50.0, 114.6, "Region"),
    ("division", 114.6, 155.9, "Division"),
    ("district", 155.9, 176.0, "District"),
    ("id_raw", 176.0, 201.7, "BEIS"),
    ("school_name", 202.9, 309.2, "School Name"),
    ("street", 309.2, 425.9, "Street"),
    ("municipality", 425.9, 486.6, "Municipality"),
    ("legislative_district", 486.6, 520.0, "Legislative"),
    ("barangay", 520.0, 591.5, "Barangay"),
    ("sector", 591.5, 607.5, "Sector"),
)
ID_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
ID_MIN_X = 176.0
ID_MAX_X = 203.0
ROW_BAND = 1.8

SECTOR_NORMALIZED = {
    "public": "public",
    "private": "private",
    "sucs/lucs": "suc_luc",
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


def _header_index(lines: list[str], token: str) -> int | None:
    for index, line in enumerate(lines):
        if line.startswith(token):
            return index
    return None


def parse_masterlist_pdf(content: bytes) -> list[dict[str, Any]]:
    """Extract one row per school from the official PDF.

    The returned mapping preserves the source's printed values. ``sector`` is
    the raw cell (for example ``"SUCs/LUCs"``); normalization happens in
    :meth:`DepEdMasterlistAdapter.normalize`.
    """

    if not content.startswith(b"%PDF"):
        raise ValueError("DepEd masterlist content is not a PDF.")
    rows: list[dict[str, Any]] = []
    document = pdfium.PdfDocument(content)
    try:
        for page_number in range(len(document)):
            page = document[page_number]
            text_page = page.get_textpage()
            try:
                height = float(page.get_size()[1])
                char_count = text_page.count_chars()
                full_text = text_page.get_text_range(0, char_count)
                ids: list[str] = []
                centers: list[float] = []
                for match in ID_PATTERN.finditer(full_text):
                    left, bottom, _right, top = text_page.get_charbox(match.start())
                    if ID_MIN_X <= left <= ID_MAX_X:
                        ids.append(match.group(1))
                        centers.append((bottom + top) / 2)
                if not ids:
                    continue

                columns: dict[str, list[str]] = {}
                counts: dict[str, int] = {}
                for name, left, right, token in COLUMNS:
                    text = text_page.get_text_bounded(left=left, bottom=0, right=right, top=height)
                    lines = [line.strip() for line in text.splitlines()]
                    header = _header_index(lines, token)
                    values = lines[header + 1 :] if header is not None else lines
                    columns[name] = values
                    counts[name] = len(values)

                # An empty Barangay (or any other blank cell) produces no line,
                # so the column no longer zips against the IDs. Re-read only
                # that column in each row's y-band.
                for name in [key for key, count in counts.items() if count != len(ids)]:
                    left, right = next((x0, x1) for key, x0, x1, _ in COLUMNS if key == name)
                    columns[name] = [
                        " ".join(
                            text_page.get_text_bounded(
                                left=left,
                                bottom=center - ROW_BAND,
                                right=right,
                                top=center + ROW_BAND,
                            ).split()
                        )
                        for center in centers
                    ]

                for index, school_id in enumerate(ids):
                    row: dict[str, Any] = {
                        "school_id": school_id,
                        "page": page_number + 1,
                    }
                    for name, _left, _right, _token in COLUMNS:
                        if name == "id_raw":
                            continue
                        row[name] = columns[name][index] if index < len(columns[name]) else ""
                    rows.append(row)
            finally:
                text_page.close()
    finally:
        document.close()
    return rows


# Acquisition fallback ------------------------------------------------------


def fetch_deped_masterlist(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch the official PDF, falling back to the preserved Wayback copy.

    The DepEd URL returns HTTP 403 to non-browser clients. The archive copy is
    the same 5,893,824-byte artifact (SHA-256
    ``461a96d3fa2bca1f046ac4fb5c5ea1b7430e2f190c7253fe54f64dfdf87547d5``).
    """

    official = acquirer.fetch(OFFICIAL_PDF_URL, max_bytes=MAX_PDF_BYTES)
    if official.status_code == 200 and official.content.startswith(b"%PDF"):
        return official.content, {
            "http_status": official.status_code,
            "acquired_from": OFFICIAL_PDF_URL,
        }
    archive = acquirer.fetch(ARCHIVE_PDF_URL, max_bytes=MAX_PDF_BYTES)
    if archive.status_code != 200 or not archive.content.startswith(b"%PDF"):
        raise AcquisitionError(
            "DepEd masterlist is unavailable from both the official URL "
            f"(HTTP {official.status_code}) and the preserved archive "
            f"(HTTP {archive.status_code})."
        )
    return archive.content, {
        "http_status": archive.status_code,
        "acquired_from": ARCHIVE_PDF_URL,
        "official_http_status": official.status_code,
    }


# Adapter -------------------------------------------------------------------


class DepEdMasterlistAdapter:
    source_code = "deped"
    parser_version = "deped-masterlist-pdf-1.0.0"
    schema_version = "deped-masterlist-sy2020-2021-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows = parse_masterlist_pdf(spec.content)
        parsed: list[ParsedRow] = []
        for index, row in enumerate(rows):
            school_id = normalise_code(row.get("school_id"))
            if not school_id:
                continue
            parsed.append(
                ParsedRow(
                    source_record_key=school_id,
                    row_reference=(f"pdf_page:{row['page']}:row:{index + 1}"),
                    raw_payload=row,
                    normalized_payload={
                        **row,
                        "school_id": school_id,
                        "sector_normalized": SECTOR_NORMALIZED.get(
                            str(row.get("sector", "")).strip().casefold()
                        ),
                    },
                )
            )
        if not parsed:
            raise ValueError("DepEd masterlist PDF returned no school rows.")
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "fixed_column_pdf_extraction",
                    "message": (
                        "Rows are read from the PDF by fixed x-column ranges. "
                        "School names and addresses can touch adjacent columns in "
                        "the published layout, so only the BEIS ID and Sector are "
                        "used for canonical enrichment."
                    ),
                },
                {
                    "code": "enrichment_only_release",
                    "message": (
                        "Rows fill missing ownership, ownership type, inclusion "
                        "class, and school sector by exact BEIS ID. Existing names "
                        "and other canonical values are not replaced."
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
            if not sector:
                issues.append(
                    ValidationIssue(
                        "missing_sector",
                        "fatal",
                        f"School {school_id} has no recognized Sector value.",
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
                continue
            if school_id in seen:
                duplicates += 1
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
            if not school_id or not sector or not name:
                continue
            ownership, ownership_type, inclusion_class = SECTOR_CLASSIFICATION[sector]
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=school_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="school",
                    # The masterlist does not state a finer subtype; do not
                    # overwrite a subtype already established by EBEIS.
                    facility_subtype=None,
                    ownership=ownership,
                    ownership_type=ownership_type,
                    inclusion_class=inclusion_class,
                    record_status="active_in_registry",
                    location=LocationData(),
                    school=SchoolData(
                        deped_school_id=school_id,
                        sector=sector,
                    ),
                    enrichment_only=True,
                )
            )
        return candidates
