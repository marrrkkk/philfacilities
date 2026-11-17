"""Mandaluyong City barangay directory adapter.

The Mandaluyong City Government publishes a server-rendered barangay directory at
``https://mandaluyong.gov.ph/government/barangays/``. Its public table lists the
city's 27 barangays with district, barangay code, office address, contact numbers,
chairperson and an optional portrait.

The adapter publishes the institutional facts needed to locate the barangay
office: barangay name, district, code and office address. Telephone numbers and
chairperson names are retained only in the private raw artifact and are removed
from normalized payloads. The source labels an "Office Address", not a barangay
hall; the adapter therefore does not invent a hall classification. The one
address that explicitly names a covered court is modelled as a community
facility with a covered-court function plus a barangay-office function.

No coordinates, PSGC codes, office hours, walk-in access rules or current
operating status are inferred. Presence in the city directory is registry
evidence only. Source scope is Mandaluyong City, not the national LGU universe.
"""

from __future__ import annotations

import html as html_module
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from ..acquisition import AcquisitionError, HttpAcquirer, is_blocker_page
from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    RoleData,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text

SOURCE_URL = "https://mandaluyong.gov.ph/government/barangays/"
PUBLIC_FIELDS = (
    "record_type",
    "name",
    "district",
    "code",
    "address",
    "detail_url",
    "source_url",
    "page_modified_time",
    "multi_use",
)


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return text or "unnamed"


def _text(value: Any) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = html_module.unescape(text).replace("\u200b", " ")
    return re.sub(r"\s+", " ", text).strip(" ,;")


class _BarangayTableParser(HTMLParser):
    """Collect cells from the directory's ``magic-table`` only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, str | None]]] = []
        self._in_table = False
        self._table_depth = 0
        self._row: list[dict[str, str | None]] | None = None
        self._cell: list[str] | None = None
        self._cell_href: str | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._in_table:
                self._table_depth += 1
            elif "magic-table" in (attributes.get("class") or ""):
                self._in_table = True
                self._table_depth = 1
            return
        if not self._in_table:
            return
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if tag == "tr":
            self._row = []
            return
        if tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._cell_href = None
            return
        if tag == "a" and self._cell is not None and self._cell_href is None:
            self._cell_href = attributes.get("href")
            return
        if tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None and self._skip_depth == 0:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if not self._in_table:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append({"text": _text("".join(self._cell)), "href": self._cell_href})
            self._cell = None
            self._cell_href = None
            return
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            return
        if tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_table = False
                self._table_depth = 0


def parse_page_modified_time(document: str) -> str | None:
    """Return the page's published modification timestamp, when present."""

    for match in re.finditer(r"<meta\b[^>]*>", document, re.IGNORECASE):
        tag = match.group(0)
        if "article:modified_time" not in tag:
            continue
        content = re.search(r'content=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if content:
            return content.group(1).strip()
    return None


def parse_barangay_table(document: str) -> list[dict[str, Any]]:
    """Parse the public barangay table without retaining portrait metadata."""

    parser = _BarangayTableParser()
    parser.feed(document)
    if not parser.rows:
        return []
    header = [str(cell.get("text") or "").strip().lower() for cell in parser.rows[0]]
    try:
        positions = {
            "district": header.index("district"),
            "code": header.index("code"),
            "name": header.index("barangay"),
            "address": header.index("office address"),
            "contacts": header.index("contact numbers"),
            "chairperson": header.index("chairperson"),
        }
    except ValueError:
        return []

    modified_time = parse_page_modified_time(document)
    records: list[dict[str, Any]] = []
    for row in parser.rows[1:]:
        if len(row) < max(positions.values()) + 1:
            continue
        name = _text(row[positions["name"]].get("text"))
        code = _text(row[positions["code"]].get("text"))
        address = _text(row[positions["address"]].get("text"))
        if not name or not code or not address:
            continue
        href = row[positions["name"]].get("href")
        records.append(
            {
                "record_type": "barangay_office",
                "name": name,
                "district": _text(row[positions["district"]].get("text")),
                "code": code,
                "address": address,
                "contacts": _text(row[positions["contacts"]].get("text")),
                "chairperson": _text(row[positions["chairperson"]].get("text")),
                "detail_url": urljoin(SOURCE_URL, href) if href else None,
                "multi_use": ("covered_court" if "covered court" in address.casefold() else None),
                "source_url": SOURCE_URL,
                "page_modified_time": modified_time,
            }
        )
    return records


def fetch_mandaluyong_directory(
    acquirer: HttpAcquirer,
) -> tuple[bytes, dict[str, Any]]:
    """Acquire and parse the public Mandaluyong barangay directory."""

    result = acquirer.fetch(SOURCE_URL, max_bytes=5 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"Mandaluyong barangay directory returned HTTP {result.status_code}.",
            result=result,
        )
    if is_blocker_page(result):
        raise AcquisitionError(
            "Mandaluyong barangay directory returned an access-control page.",
            result=result,
        )
    document = result.content.decode("utf-8", errors="replace")
    records = parse_barangay_table(document)
    if not records:
        raise AcquisitionError("Mandaluyong barangay directory contained no rows.")

    retrieved_at = datetime.now(UTC)
    payload = {
        "source": "City Government of Mandaluyong official website",
        "source_url": SOURCE_URL,
        "retrieved_at": retrieved_at.isoformat(),
        "page_modified_time": parse_page_modified_time(document),
        "record_count": len(records),
        "covered_court_count": sum(1 for record in records if record.get("multi_use")),
        "records": records,
    }
    metadata = {
        "page_sha256": result.sha256,
        "record_count": len(records),
        "covered_court_count": payload["covered_court_count"],
        "records_with_contact": sum(1 for record in records if record.get("contacts")),
        "records_with_chairperson": sum(1 for record in records if record.get("chairperson")),
        "retrieved_at": retrieved_at.isoformat(),
        "page_modified_time": payload["page_modified_time"],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), metadata


class MandaluyongBarangayAdapter:
    source_code = "mandaluyong"
    parser_version = "mandaluyong-lgu-html-1.0.0"
    schema_version = "mandaluyong-lgu-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError("Mandaluyong release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("Mandaluyong artifact contains no barangay records.")

        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            name = clean_text(record.get("name"))
            code = clean_text(record.get("code"))
            address = clean_text(record.get("address"))
            if not any((name, code, address)):
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            rows.append(
                ParsedRow(
                    source_record_key=(
                        f"MANDALUYONG-BARANGAY:{code or f'ROW-{index}'}:{_slug(name or 'unnamed')}"
                    )[:180],
                    row_reference=f"mandaluyong-barangay-table:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("Mandaluyong artifact contained no usable records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "contact_and_personal_fields_withheld",
                    "message": (
                        "Telephone numbers and chairperson names remain only in the "
                        "private raw artifact and are not present in normalized records."
                    ),
                },
                {
                    "code": "barangay_hall_label_not_stated",
                    "message": (
                        "The source publishes an 'Office Address', not a barangay-hall "
                        "classification. Records are modelled as barangay government "
                        "offices; no hall subtype is inferred."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The directory supplies postal office addresses but no "
                        "coordinates. No geocoding was performed."
                    ),
                },
                {
                    "code": "covered_court_multi_use",
                    "message": (
                        "The barangay whose office address explicitly names a covered "
                        "court is modelled as a community facility with barangay-office "
                        "and covered-court functions."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("name"))
            code = clean_text(payload.get("code"))
            address = clean_text(payload.get("address"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "A Mandaluyong directory row has no barangay name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not code:
                issues.append(
                    ValidationIssue(
                        "missing_barangay_code",
                        "fatal",
                        f"Mandaluyong barangay {name} has no published code.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_source_record",
                        "error",
                        f"Mandaluyong barangay {name} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(row.source_record_key)
            if not address:
                issues.append(
                    ValidationIssue(
                        "missing_address",
                        "fatal",
                        f"Mandaluyong barangay {name} has no published office address.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("name"))
            code = clean_text(payload.get("code"))
            address = clean_text(payload.get("address"))
            district = clean_text(payload.get("district"))
            multi_use = payload.get("multi_use")
            source_url = payload.get("source_url")
            detail_url = payload.get("detail_url")
            evidence = {
                "source_page": source_url,
                "barangay_detail_page": detail_url,
                "page_modified_time": payload.get("page_modified_time"),
                "district": district,
                "barangay_code": code,
                "office_address": address,
                "hall_label": "not stated by source",
            }
            address_text = address
            if "mandaluyong" not in address.casefold():
                address_text = f"{address}, Mandaluyong City"

            if multi_use == "covered_court":
                display_name = f"{name} Barangay Office — Covered Court"
                facility_type = "community_facility"
                facility_subtype = "COVERED_COURT"
                functions = [
                    FunctionData(
                        function_code="GOVERNMENT_ADMINISTRATION",
                        source_value="Barangay office address",
                        evidence=evidence,
                    ),
                    FunctionData(
                        function_code="COVERED_COURT",
                        source_value="Office address names a covered court",
                        evidence=evidence,
                    ),
                ]
                access_conditions = (
                    "Mandaluyong City barangay directory record. The source gives the "
                    "barangay office address as a covered court. It does not state "
                    "walk-in access, office hours, court availability, service "
                    "availability or current operating status."
                )
            else:
                display_name = f"{name} Barangay Office"
                facility_type = "government_office"
                facility_subtype = "OTHER_GOVERNMENT_OFFICE"
                functions = [
                    FunctionData(
                        function_code="GOVERNMENT_ADMINISTRATION",
                        source_value="Barangay office address",
                        evidence=evidence,
                    )
                ]
                access_conditions = (
                    "Mandaluyong City barangay directory record. The source publishes "
                    "an office address, not a barangay-hall classification. It does not "
                    "state walk-in access, office hours, service availability or current "
                    "operating status."
                )

            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=display_name,
                    facility_type=facility_type,
                    facility_subtype=facility_subtype,
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="LOCAL_GOVERNMENT",
                    operator_type="LOCAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    access_conditions=access_conditions,
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=address_text or None,
                        precision="unknown",
                    ),
                    functions=functions,
                    roles=[
                        RoleData(
                            role_type="OWNER",
                            entity_name=f"Barangay {name}",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Mandaluyong City barangay directory"},
                        ),
                        RoleData(
                            role_type="OPERATOR",
                            entity_name=f"Barangay {name}",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Mandaluyong City barangay directory"},
                        ),
                    ],
                )
            )
        return candidates
