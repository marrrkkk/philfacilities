"""PhilHealth office-directory adapter.

The official PhilHealth "Directory of Offices" page is a public, server-rendered
accordion of regional offices (PROs), Local Health Insurance Offices (LHIOs),
satellite offices, PhilHealth Express counters, service desks, business centres
and one-stop service centres. Each entry carries an institutional office name,
a source section/category and, for many entries, a postal address together with
telephone, e-mail and schedule text.

The normalized public payload keeps only the institutional office identity,
source category, region grouping and postal address. Telephone numbers, e-mail
addresses and schedule text remain in the private preserved artifact and are
never exposed. Where the page supplies only a phone number or schedule and no
address, the office is still recorded with an explicit missing-address warning
rather than inventing a location.

Directory presence is not proof that an office is currently open, that its
published address is current, or that walk-in service is available. The page
does not supply coordinates, PSGC codes or a completeness statement.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import Any

from ..acquisition import AcquisitionError, HttpAcquirer
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

DIRECTORY_URL = "https://www.philhealth.gov.ph/about_us/directory/"
PUBLIC_FIELDS = (
    "office_name",
    "office_category",
    "source_section",
    "region_office",
    "address",
)
TOKEN_RE = re.compile(r"<(h2|h4|h6|p)(?:\s[^>]*)?>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
SCHEDULE_RE = re.compile(
    r"(?i)(office hours|business hours|open every|every\s+(?:last|1st|2nd|3rd|4th|\d)"
    r"|daily|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}\s*(?:am|pm)\b)"
)
PHONE_LABEL_RE = re.compile(
    r"(?i)\b(telefax|telephone|tel\.?|fax|mobile|avaya|loc\.?|local|for employers"
    r"|for individuals|contact)\b"
)
ADDRESS_WORD_RE = re.compile(
    r"(?i)(street|st\.|floor|flr\.?|building|bldg\.?|road|ave\.?|avenue|brgy\.?"
    r"|barangay|city|municipal|province|compound|plaza|mall|market|center|centre"
    r"|highway|drive|cor\.?|corner|poblacion|subd\.?|village|terminal|complex)"
)
MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u201c": "\u2013",
    "\u00e2\u20ac\u201d": "\u2014",
    "\u00c2\u00b7": "\u00b7",
    "\u00c3\u00b1": "\u00f1",
    "\u00e2\u20ac\u00a6": "\u2026",
}

CATEGORY_LABELS = {
    "REGIONAL_OFFICE": "Regional Office",
    "BRANCH_OFFICE": "Branch Office",
    "LOCAL_HEALTH_INSURANCE_OFFICE": "LHIO",
    "SATELLITE_OFFICE": "Satellite Office",
    "PHILHEALTH_EXPRESS": "Express",
    "SERVICE_DESK": "Service Desk",
    "BUSINESS_CENTER": "Business Center",
    "ONE_STOP_SERVICE_CENTER": "One Stop Service Center",
    "OTHER_PHILHEALTH_OFFICE": "Office",
}
CATEGORY_MATCHERS = (
    ("LOCAL_HEALTH_INSURANCE_OFFICE", re.compile(r"local health insurance", re.I)),
    ("PHILHEALTH_EXPRESS", re.compile(r"philhealth express", re.I)),
    ("SERVICE_DESK", re.compile(r"service desks?", re.I)),
    ("ONE_STOP_SERVICE_CENTER", re.compile(r"one[- ]stop", re.I)),
    ("SATELLITE_OFFICE", re.compile(r"satellite office", re.I)),
    ("BUSINESS_CENTER", re.compile(r"business cent(?:er|re)s?", re.I)),
    ("BRANCH_OFFICE", re.compile(r"branch office", re.I)),
    ("REGIONAL_OFFICE", re.compile(r"regional office", re.I)),
)
FACILITY_KIND_BY_CATEGORY = {
    "PHILHEALTH_EXPRESS": "facility_unit",
    "SERVICE_DESK": "facility_unit",
    "ONE_STOP_SERVICE_CENTER": "facility_unit",
}


def _fix_mojibake(value: str) -> str:
    for source, replacement in MOJIBAKE_REPLACEMENTS.items():
        value = value.replace(source, replacement)
    return value


def _slug(value: str | None) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value or "").strip("-").upper()
    return text or "UNNAMED"


def _category_code(section: str | None) -> str:
    text = section or ""
    for code, pattern in CATEGORY_MATCHERS:
        if pattern.search(text):
            return code
    return "OTHER_PHILHEALTH_OFFICE"


def _text_lines(fragment: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(_fix_mojibake(text))
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip(" \t\u00a0;,")
        line = re.sub(r"^[·•]\s*", "", line)
        if line:
            lines.append(line)
    return lines


def _is_phone_line(line: str) -> bool:
    if EMAIL_RE.search(line):
        return False
    digits = sum(character.isdigit() for character in line)
    letters = sum(character.isalpha() for character in line)
    if PHONE_LABEL_RE.search(line) and digits:
        return True
    if digits >= 6 and letters <= 6 and not ADDRESS_WORD_RE.search(line):
        return True
    return bool(re.fullmatch(r"[\d\s()+./;,:\-]+", line) and digits >= 6)


def _classify_lines(lines: list[str]) -> dict[str, Any]:
    address_lines: list[str] = []
    phones: list[str] = []
    emails: list[str] = []
    schedules: list[str] = []
    for line in lines:
        found_emails = EMAIL_RE.findall(line)
        if found_emails:
            emails.extend(found_emails)
            remainder = EMAIL_RE.sub("", line).strip(" ;,|")
            if remainder and not _is_phone_line(remainder) and not SCHEDULE_RE.search(remainder):
                address_lines.append(remainder)
            continue
        if SCHEDULE_RE.search(line):
            schedules.append(line)
            continue
        if _is_phone_line(line):
            phones.append(line)
            continue
        address_lines.append(line)
    address = ", ".join(part.rstrip(" ,;") for part in address_lines if part.strip(" ,;"))
    address = re.sub(r"\s*,\s*", ", ", address).strip(" ,")
    address = re.sub(r",\s*,+", ", ", address)
    return {
        "address": address or None,
        "address_lines": address_lines,
        "phone_numbers": phones,
        "emails": emails,
        "schedule_text": schedules,
    }


def _record_key(region: str, section: str, name: str) -> str:
    return f"PHILHEALTH:{_slug(region)}:{_slug(section)}:{_slug(name)}"


def parse_office_html(document: str) -> list[dict[str, Any]]:
    """Parse office entries from the official PhilHealth directory page."""

    records: list[dict[str, Any]] = []
    region: str | None = None
    section: str | None = None
    pending_name: str | None = None
    pending_section: str | None = None

    def flush(name: str | None, source_section: str | None, lines: list[str]) -> None:
        if not region or not name or not source_section:
            return
        classified = _classify_lines(lines)
        category = _category_code(source_section)
        record = {
            "office_name": name,
            "source_section": source_section,
            "office_category": category,
            "region_office": region,
            "address": classified["address"],
            "address_lines": classified["address_lines"],
            "phone_numbers": classified["phone_numbers"],
            "emails": classified["emails"],
            "schedule_text": classified["schedule_text"],
        }
        record["office_key"] = _record_key(region, source_section, name)
        if any(existing["office_key"] == record["office_key"] for existing in records):
            record["office_key"] = f"{record['office_key']}:{len(records) + 1}"
        records.append(record)

    for match in TOKEN_RE.finditer(document):
        tag = match.group(1).lower()
        body = match.group(2)
        text = re.sub(
            r"\s+",
            " ",
            html.unescape(_fix_mojibake(re.sub(r"<[^>]+>", " ", body))),
        ).strip()
        if tag == "h2":
            flush(pending_name, pending_section, [])
            pending_name = None
            pending_section = None
            region = text or None
            section = None
        elif tag == "h4":
            flush(pending_name, pending_section, [])
            pending_name = None
            pending_section = None
            section = text or None
        elif tag == "h6":
            flush(pending_name, pending_section, [])
            pending_name = text or None
            pending_section = section
        elif tag == "p" and region:
            if pending_name and pending_section:
                flush(pending_name, pending_section, _text_lines(body))
                pending_name = None
                pending_section = None
            elif section:
                flush(section, section, _text_lines(body))
    flush(pending_name, pending_section, [])
    return records


def fetch_philhealth_offices(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    result = acquirer.fetch(DIRECTORY_URL, max_bytes=5 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"PhilHealth office directory returned HTTP {result.status_code}.",
            result=result,
        )
    document = result.content.decode("utf-8", errors="replace")
    records = parse_office_html(document)
    if not records:
        raise AcquisitionError("PhilHealth office directory returned no office records.")

    artifact = {
        "source_url": DIRECTORY_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "record_count": len(records),
        "with_address": sum(1 for record in records if record.get("address")),
        "with_phone": sum(1 for record in records if record.get("phone_numbers")),
        "with_email": sum(1 for record in records if record.get("emails")),
        "note": (
            "Public PhilHealth Directory of Offices artifact. Telephone numbers, "
            "e-mail addresses and schedule text are retained only in this private "
            "raw release; normalized public rows expose office name, source "
            "category, region grouping and postal address. No coordinates, PSGC "
            "codes or current operating status are present."
        ),
        "records": records,
    }
    metadata = {
        "records": len(records),
        "with_address": artifact["with_address"],
        "with_phone": artifact["with_phone"],
        "with_email": artifact["with_email"],
        "source_url": DIRECTORY_URL,
    }
    return json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8"), metadata


def _display_name(name: str, category: str, region: str, source_section: str | None) -> str:
    label = CATEGORY_LABELS.get(category, "Office")
    clean_name = clean_text(name) or ""
    clean_section = clean_text(source_section) or ""
    clean_region = re.sub(r"^PRO\s+", "", clean_text(region) or "", flags=re.IGNORECASE).strip()
    if (
        clean_name.casefold() == clean_section.casefold()
        or clean_name.casefold() == label.casefold()
    ):
        return f"PhilHealth {label} — {clean_region}"[:300]
    if clean_name.casefold().startswith("philhealth"):
        return clean_name[:300]
    if clean_name.casefold().startswith(label.casefold()):
        return f"PhilHealth {clean_name}"[:300]
    return f"PhilHealth {label} — {clean_name}"[:300]


class PhilHealthOfficeAdapter:
    source_code = "philhealth-offices"
    parser_version = "philhealth-offices-html-1.0.0"
    schema_version = "philhealth-offices-html-v1"
    expected_columns = {"required": {"office_name", "office_category"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content)
        except json.JSONDecodeError as exc:
            raise ValueError("PhilHealth office release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("PhilHealth office artifact contains no records.")
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            name = clean_text(record.get("office_name"))
            category = clean_text(record.get("office_category"))
            if not name or not category:
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            rows.append(
                ParsedRow(
                    source_record_key=(
                        f"PHILHEALTH-OFFICE:{record.get('office_key') or _slug(name)}"
                    ),
                    row_reference=f"philhealth-directory-html:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("PhilHealth office artifact contained no usable office records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "contact_and_schedule_fields_withheld",
                    "message": (
                        "Telephone numbers, e-mail addresses and schedule text remain in "
                        "the private preserved artifact and are excluded from the normalized "
                        "public payload."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The PhilHealth directory supplies postal addresses and region "
                        "groupings only; no coordinates or PSGC codes were invented."
                    ),
                },
                {
                    "code": "directory_not_operational_status",
                    "message": (
                        "Directory presence is not proof of current operation, office hours, "
                        "walk-in availability or completeness of the office network."
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
            name = clean_text(payload.get("office_name"))
            category = clean_text(payload.get("office_category"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_office_name",
                        "fatal",
                        "A PhilHealth office row has no office name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_office_key",
                        "error",
                        f"PhilHealth office key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if not clean_text(payload.get("address")):
                issues.append(
                    ValidationIssue(
                        "missing_office_address",
                        "warning",
                        f"PhilHealth office {name} has no postal address in the directory entry.",
                        row_reference=row.row_reference,
                    )
                )
            if category == "OTHER_PHILHEALTH_OFFICE":
                issues.append(
                    ValidationIssue(
                        "unrecognised_office_category",
                        "warning",
                        f"PhilHealth office {name} uses an unrecognised source section.",
                        row_reference=row.row_reference,
                    )
                )
            source_section = clean_text(payload.get("source_section")) or ""
            if (
                "express" in source_section.casefold() and "express" not in (name or "").casefold()
            ) or (
                "service desk" in source_section.casefold()
                and "service desk" not in (name or "").casefold()
                and "sd" not in (name or "").casefold()
            ):
                issues.append(
                    ValidationIssue(
                        "source_section_name_mismatch",
                        "warning",
                        (
                            f"PhilHealth office {name} is listed under source section "
                            f"'{source_section}' and may be misgrouped on the page."
                        ),
                        row_reference=row.row_reference,
                    )
                )
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("office_name"))
            category = clean_text(payload.get("office_category"))
            region = clean_text(payload.get("region_office")) or ""
            if not name or not category:
                continue
            address = clean_text(payload.get("address"))
            facility_kind = FACILITY_KIND_BY_CATEGORY.get(category, "facility")
            source_section = clean_text(payload.get("source_section"))
            display_name = _display_name(name, category, region, source_section)
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=display_name,
                    facility_type="government_office",
                    facility_subtype="PUBLIC_SERVICE_CENTER",
                    facility_kind=facility_kind,
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOCC",
                    operator_type="GOCC",
                    public_access_class="SERVICE_USERS_ONLY",
                    access_conditions=(
                        "PhilHealth office or service counter serving members, employers "
                        "and accredited providers. The directory does not state appointment "
                        "requirements or reliable walk-in rules."
                    ),
                    record_status="unknown",
                    location=LocationData(
                        address_text=address or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="PUBLIC_SERVICE_COUNTER",
                            source_value=f"PhilHealth {CATEGORY_LABELS.get(category, category)}",
                            designation_status="unknown",
                            evidence={
                                "source": "PhilHealth Directory of Offices",
                                "office_category": category,
                                "source_section": clean_text(payload.get("source_section")),
                                "region_office": region,
                                "address": address,
                            },
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Philippine Health Insurance Corporation",
                            entity_type="GOCC",
                            evidence={"basis": "Official PhilHealth Directory of Offices"},
                        )
                    ],
                )
            )
        return candidates
