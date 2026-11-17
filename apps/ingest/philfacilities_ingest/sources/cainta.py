"""Cainta, Rizal municipal health-centre directory adapter.

The Municipality of Cainta publishes a public health-services page and six
Rural Health Unit (RHU) pages. The RHU pages list the RHU itself plus barangay
health stations (BHS) with a printed postal address. The landing page states
that Cainta has 28 health centres across its seven barangays.

The adapter publishes only records that the source explicitly labels ``(RHU)``
or ``(BHS)``. The landing page's unlabelled health centres and the satellite
health station are retained as acquisition evidence but are not converted into
facilities. Telephone numbers, e-mail addresses and personal names are not
published. No coordinates, office hours, walk-in access rules or current
operating status are inferred.
"""

from __future__ import annotations

import html as html_module
import json
import re
from datetime import UTC, datetime
from typing import Any

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

SOURCE_URL = "https://www.cainta.gov.ph/healthcentersandservices2025"
RHU_URLS = {
    1: "https://www.cainta.gov.ph/rhu1",
    2: "https://www.cainta.gov.ph/rhu2",
    3: "https://www.cainta.gov.ph/rhu3",
    4: "https://www.cainta.gov.ph/rhu4",
    5: "https://www.cainta.gov.ph/rhu5",
    6: "https://www.cainta.gov.ph/rhu6",
}
PUBLIC_FIELDS = (
    "record_type",
    "name",
    "level",
    "address",
    "rhu_number",
    "rhu_barangay",
    "source_url",
    "page_sha256",
    "fetched_at",
)


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return text or "unnamed"


def _visible_lines(document: str) -> list[str]:
    text = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1\s*>",
        " ",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html_module.unescape(text).replace("\u200b", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line and len(line) > 1]


def parse_claimed_total(document: str) -> int | None:
    """Return the number of health centres stated on the landing page."""

    text = " ".join(_visible_lines(document))
    match = re.search(
        r"there are a total of\s+([\d,]+)\s+health centers",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _entry_name(line: str) -> tuple[str, str | None] | None:
    """Return the institution name and explicit RHU/BHS label, if present."""

    match = re.match(r"^(.*?)\s*\((RHU|BHS)\)\s*$", line, re.IGNORECASE)
    if match:
        name = clean_text(match.group(1))
        return (name, match.group(2).upper()) if name else None
    if re.search(r"\b(health center|health station)\b", line, re.IGNORECASE):
        # Unlabelled entries are retained in the acquisition artifact but are
        # not published because the source did not classify them as RHU/BHS.
        if line.casefold().startswith(("health and health", "list of")):
            return None
        return (clean_text(line), None)
    return None


def parse_rhu_page(document: str, url: str, rhu_number: int) -> dict[str, Any]:
    """Parse one RHU page into its heading and listed health facilities."""

    lines = _visible_lines(document)
    heading_pattern = re.compile(rf"^RHU\s*{rhu_number}\s*-\s*BRGY\.\s*(.+)$", re.IGNORECASE)
    heading_index = None
    heading = None
    for index, line in enumerate(lines):
        match = heading_pattern.match(line)
        if match:
            heading_index = index
            heading = line
            break
    if heading_index is None or heading is None:
        raise ValueError(f"Cainta RHU {rhu_number} page has no RHU heading.")

    barangay = heading_pattern.match(heading).group(1).strip()
    entries: list[dict[str, Any]] = []
    index = heading_index + 1
    while index < len(lines):
        line = lines[index]
        if line.upper().startswith("BACK") or heading_pattern.match(line):
            break
        parsed_name = _entry_name(line)
        if not parsed_name:
            index += 1
            continue
        name, level = parsed_name
        address_lines: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            if (
                candidate.upper().startswith("BACK")
                or heading_pattern.match(candidate)
                or _entry_name(candidate)
            ):
                break
            address_lines.append(candidate)
            cursor += 1
        address = clean_text(" ".join(address_lines))
        address = re.sub(r"^Address\s*:\s*", "", address, flags=re.IGNORECASE)
        if name and address:
            entries.append(
                {
                    "name": name,
                    "level": level,
                    "address": address,
                    "rhu_number": rhu_number,
                    "rhu_barangay": barangay,
                    "source_url": url,
                }
            )
        index = max(cursor, index + 1)
    return {
        "rhu_number": rhu_number,
        "heading": heading,
        "barangay": barangay,
        "entries": entries,
    }


def fetch_cainta_health_centers(
    acquirer: HttpAcquirer,
) -> tuple[bytes, dict[str, Any]]:
    """Acquire the landing page and every RHU page."""

    landing = acquirer.fetch(SOURCE_URL, max_bytes=3 * 1024 * 1024)
    if landing.status_code >= 400:
        raise AcquisitionError(
            f"Cainta health-centres page returned HTTP {landing.status_code}.",
            result=landing,
        )
    if is_blocker_page(landing):
        raise AcquisitionError(
            "Cainta health-centres page returned an access-control page.",
            result=landing,
        )
    landing_document = landing.content.decode("utf-8", errors="replace")
    claimed_total = parse_claimed_total(landing_document)

    records: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for rhu_number, url in RHU_URLS.items():
        result = acquirer.fetch(url, max_bytes=3 * 1024 * 1024)
        if result.status_code >= 400:
            raise AcquisitionError(
                f"Cainta RHU {rhu_number} page returned HTTP {result.status_code}.",
                result=result,
            )
        if is_blocker_page(result):
            raise AcquisitionError(
                f"Cainta RHU {rhu_number} page returned an access-control page.",
                result=result,
            )
        parsed = parse_rhu_page(result.content.decode("utf-8", errors="replace"), url, rhu_number)
        if not parsed["entries"]:
            raise AcquisitionError(
                f"Cainta RHU {rhu_number} page contained no health-centre entries."
            )
        fetched_at = datetime.now(UTC).isoformat()
        pages.append(
            {
                "rhu_number": rhu_number,
                "url": url,
                "sha256": result.sha256,
                "heading": parsed["heading"],
                "barangay": parsed["barangay"],
                "entry_count": len(parsed["entries"]),
                "fetched_at": fetched_at,
            }
        )
        for entry in parsed["entries"]:
            record = {
                "record_type": "health_center",
                **entry,
                "page_sha256": result.sha256,
                "fetched_at": fetched_at,
            }
            if entry["level"]:
                records.append(record)
            else:
                excluded.append(record)

    if claimed_total is not None and len(records) != claimed_total:
        raise AcquisitionError(
            f"Cainta states {claimed_total} health centres but the RHU pages "
            f"supplied {len(records)} explicitly labelled records; the release "
            "was not accepted."
        )
    if not records:
        raise AcquisitionError("Cainta RHU pages contained no labelled health centres.")

    retrieved_at = datetime.now(UTC)
    payload = {
        "source": "Municipality of Cainta official website",
        "source_url": SOURCE_URL,
        "retrieved_at": retrieved_at.isoformat(),
        "claimed_total": claimed_total,
        "rhu_pages": pages,
        "records": records,
        "excluded_records": excluded,
    }
    metadata = {
        "landing_page_sha256": landing.sha256,
        "rhu_pages": len(pages),
        "claimed_total": claimed_total,
        "labelled_records": len(records),
        "excluded_unlabelled_records": len(excluded),
        "retrieved_at": retrieved_at.isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), metadata


class CaintaHealthCenterAdapter:
    source_code = "cainta"
    parser_version = "cainta-lgu-health-html-1.0.0"
    schema_version = "cainta-lgu-health-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError("Cainta release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("Cainta artifact contains no health-centre records.")

        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            name = clean_text(record.get("name"))
            address = clean_text(record.get("address"))
            level = clean_text(record.get("level")).upper()
            if not any((name, address, level)):
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            public_record["record_type"] = "health_center"
            rows.append(
                ParsedRow(
                    source_record_key=(
                        f"CAINTA-HEALTH:{record.get('rhu_number')}:{_slug(name or 'unnamed')}"
                    )[:180],
                    row_reference=f"cainta-rhu-{record.get('rhu_number')}:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("Cainta artifact contained no usable records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "unlabelled_records_excluded",
                    "message": (
                        "The landing page states 28 health centres. RHU 5's two "
                        "unlabelled health centres and the One Cainta satellite health "
                        "station are retained in the raw artifact but are not published "
                        "because the source did not label them RHU or BHS."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The RHU pages supply postal addresses but no coordinates. "
                        "No geocoding was performed."
                    ),
                },
                {
                    "code": "registry_presence_not_operational_status",
                    "message": (
                        "Presence in the municipal health-centre directory is registry "
                        "evidence only. Office hours, walk-in access and current "
                        "operating status are not stated."
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
            address = clean_text(payload.get("address"))
            level = clean_text(payload.get("level")).upper()
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "A Cainta health-centre row has no institution name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if level not in {"RHU", "BHS"}:
                issues.append(
                    ValidationIssue(
                        "invalid_health_centre_level",
                        "error",
                        f"Cainta health centre {name} has an unrecognised level {level!r}.",
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
                        f"Cainta health centre {name} appears more than once.",
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
                        f"Cainta health centre {name} has no published address.",
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
            address = clean_text(payload.get("address"))
            level = clean_text(payload.get("level")).upper()
            rhu_number = payload.get("rhu_number")
            rhu_barangay = clean_text(payload.get("rhu_barangay"))
            source_url = payload.get("source_url")
            address_text = address
            if "cainta" not in address.casefold():
                address_text = f"{address}, Cainta, Rizal"
            subtype = "RURAL_HEALTH_UNIT" if level == "RHU" else "BARANGAY_HEALTH_STATION"
            evidence = {
                "source_page": source_url,
                "rhu_page_number": rhu_number,
                "rhu_barangay": rhu_barangay,
                "source_health_centre_level": level,
                "office_address": address,
                "page_sha256": payload.get("page_sha256"),
                "fetched_at": payload.get("fetched_at"),
                "no_coordinates": "source supplied no coordinates",
            }
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="health_facility",
                    facility_subtype=subtype,
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="LOCAL_GOVERNMENT",
                    operator_type="LOCAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    access_conditions=(
                        "Municipality of Cainta health-centre directory record. The "
                        "source supplies a printed address and an RHU/BHS label; it "
                        "does not state office hours, walk-in access, service "
                        "availability or current operating status."
                    ),
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=address_text or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="HEALTHCARE",
                            source_value=f"{level} health centre listed by Cainta",
                            evidence=evidence,
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OWNER",
                            entity_name="Municipality of Cainta",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Cainta municipal health-centre directory"},
                        ),
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Municipality of Cainta",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Cainta municipal health-centre directory"},
                        ),
                    ],
                )
            )
        return candidates
