"""DepEd EBEIS public school-masterlist HTML connector.

The EBEIS result page is a public, server-rendered HTML table. It contains school
head names, so the dataset is ingested as internal-only until DepEd's terms and
privacy position are reviewed. The parser preserves the full source row in the
private source-record store; the public API never exposes this dataset.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

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


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_table = False
        self._tables = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._tables += 1
            self._in_table = self._tables == 1
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(clean_text(" ".join(self._cell)) or "")
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._in_table:
            self._in_table = False


def parse_masterlist_html(html: str) -> tuple[list[str], list[dict[str, Any]]]:
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return [], []
    header = [clean_text(cell) or "" for cell in parser.rows[0]]
    if "School ID" not in header:
        raise ValueError(
            "DepEd EBEIS response did not contain the expected School ID table header; "
            "the page structure or access state changed."
        )
    rows = []
    for index, cells in enumerate(parser.rows[1:], start=2):
        if len(cells) < len(header):
            continue
        row = {header[i]: cells[i] for i in range(len(header))}
        row["_table_row"] = index
        rows.append(row)
    return header, rows


PERSONAL_FIELD = "Head / Position"


def school_levels(value: str | None) -> tuple[bool | None, bool | None, bool | None]:
    """Map the free-text EBEIS School Type cell to elementary/JHS/SHS flags.

    The source cell lists grade bands rather than an ownership or sector code. Values
    that cannot be interpreted are returned as ``None`` instead of guessed.
    """

    text = clean_text(value)
    if not text:
        return None, None, None
    normalized = re.sub(r"\s+", " ", text.casefold())
    offers_es = True if ("kinder" in normalized or "grade 1-6" in normalized) else None
    offers_jhs = True if "grade 7-10" in normalized else None
    offers_shs = True if "grade 11-12" in normalized else None
    if offers_es is None and offers_jhs is None and offers_shs is None:
        return None, None, None
    return offers_es, offers_jhs, offers_shs


class DepEdEBEISAdapter:
    source_code = "deped"
    parser_version = "deped-ebeis-html-1.1.0"
    schema_version = "deped-ebeis-masterlist-html-v2"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        _header, rows = parse_masterlist_html(spec.content.decode("utf-8", errors="replace"))
        parsed: list[ParsedRow] = []
        for row in rows:
            school_id = normalise_code(row.get("School ID"))
            if not school_id:
                continue
            normalized = {key: value for key, value in row.items() if key != PERSONAL_FIELD}
            parsed.append(
                ParsedRow(
                    # Duplicate school IDs can legitimately appear when EBEIS lists
                    # multiple head/position records for one school. The composite
                    # source key preserves each source row; the canonical entity id
                    # remains the official school ID.
                    source_record_key=f"{school_id}:row:{row['_table_row']}",
                    row_reference=f"html_row:{row['_table_row']}",
                    raw_payload=row,
                    normalized_payload=normalized,
                )
            )
        if not parsed:
            raise ValueError("DepEd EBEIS masterlist returned no school rows.")
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "withheld_school_head_names",
                    "message": (
                        "The source table contains school-head personal names. The raw row is "
                        "retained in the private source store, but the normalized payload and "
                        "facility candidate omit 'Head / Position'."
                    ),
                },
                {
                    "code": "ownership_not_in_source",
                    "message": (
                        "The EBEIS result set has no reliable per-row public/private sector "
                        "field. Ownership is left unknown, so canonical rows remain discovery "
                        "candidates rather than public government or private-provider records."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        duplicates = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(payload.get("School ID"))
            name = clean_text(payload.get("School Name"))
            if not school_id:
                issues.append(
                    ValidationIssue(
                        "missing_school_id",
                        "fatal",
                        "School row has no School ID",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_school_name",
                        "fatal",
                        f"School {school_id} has no name",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if school_id in seen:
                duplicates += 1
                issues.append(
                    ValidationIssue(
                        "duplicate_school_id",
                        "warning",
                        f"School ID {school_id} appears more than once; rows were preserved.",
                        {"school_id": school_id},
                        row.row_reference,
                    )
                )
            seen.add(school_id)
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(payload.get("School ID"))
            name = clean_text(payload.get("School Name"))
            if not school_id or not name:
                continue
            offers_es, offers_jhs, offers_shs = school_levels(payload.get("School Type"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=school_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="school",
                    # Sector is missing, so no public/private subtype can be asserted.
                    facility_subtype="OTHER_SCHOOL",
                    ownership="unknown",
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=clean_text(payload.get("Address")),
                    ),
                    school=SchoolData(
                        deped_school_id=school_id,
                        offers_es=offers_es,
                        offers_jhs=offers_jhs,
                        offers_shs=offers_shs,
                    ),
                )
            )
        return candidates
