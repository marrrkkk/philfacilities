"""Pasay City health-centre directory adapter.

The Pasay City Government publishes a "Mga Health Center ng Lungsod Pasay"
section on its health-care programme page. The section contains one card per
facility: a heading with the facility name, an optional service label and a
printed postal address, followed by contact numbers.

The adapter publishes the 13 city health centres and the one lying-in clinic
listed in the section. Telephone numbers are withheld from the public record.
No coordinates, office hours, walk-in access rules or current operating status
are inferred.
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

SOURCE_URL = "https://pasay.gov.ph/programa/health-care/"
SECTION_HEADING = "Mga Health Center ng Lungsod Pasay"
PUBLIC_FIELDS = (
    "record_type",
    "name",
    "service_label",
    "address",
    "source_url",
    "page_sha256",
    "fetched_at",
)
HEALTH_CENTRE_MARKERS = ("health center",)
CLINIC_MARKERS = ("lying-in clinic", "lying in clinic")
CONTACT_MARKERS = ("tel.", "tel:", "telephone", "e-mail", "email", "@")


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


def _is_contact_line(line: str) -> bool:
    lowered = line.casefold()
    return any(marker in lowered for marker in CONTACT_MARKERS)


def _record_type(name: str) -> str | None:
    lowered = name.casefold()
    if any(marker in lowered for marker in CLINIC_MARKERS):
        return "lying_in_clinic"
    if any(marker in lowered for marker in HEALTH_CENTRE_MARKERS):
        return "health_center"
    return None


def parse_health_cards(document: str, url: str = SOURCE_URL) -> list[dict[str, Any]]:
    """Parse the health-centre cards in the Pasay programme page.

    Each card starts with an ``h6`` heading and runs until the next ``h6``. A
    card is accepted only when it has a printed ``Address:`` line, which keeps
    the page's footer headings out of the result.
    """

    if SECTION_HEADING.casefold() not in html_module.unescape(document).casefold():
        raise ValueError("Pasay page has no 'Mga Health Center ng Lungsod Pasay' section.")
    headings = list(re.finditer(r"<h6[^>]*>(.*?)</h6>", document, re.IGNORECASE | re.DOTALL))
    cards: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(document)
        name = clean_text(re.sub(r"<[^>]+>", " ", heading.group(1)))
        if not name:
            continue
        record_type = _record_type(name)
        lines = _visible_lines(document[heading.end() : end])
        address_index = next(
            (i for i, line in enumerate(lines) if line.casefold().startswith("address")),
            None,
        )
        if address_index is None:
            continue
        if record_type is None:
            continue
        address = re.sub(
            r"^Address\s*:\s*",
            "",
            lines[address_index],
            flags=re.IGNORECASE,
        ).strip()
        if not address:
            continue
        # Every card on the inspected page supplies its address on one line.
        # Do not append later lines: superscript floor numbers in the contact
        # block would otherwise be mistaken for address text.
        service_label = clean_text(" ".join(lines[:address_index]))
        contacts = [line for line in lines[address_index + 1 :] if _is_contact_line(line)]
        cards.append(
            {
                "record_type": record_type,
                "name": name,
                "service_label": service_label or None,
                "address": address,
                "contact_text": " | ".join(contacts) or None,
                "source_url": url,
            }
        )
    if not cards:
        raise ValueError("Pasay page contained no health-centre cards with addresses.")
    return cards


def fetch_pasay_health_centers(
    acquirer: HttpAcquirer,
) -> tuple[bytes, dict[str, Any]]:
    """Acquire the Pasay health-care programme page."""

    result = acquirer.fetch(SOURCE_URL, max_bytes=3 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"Pasay health-care page returned HTTP {result.status_code}.",
            result=result,
        )
    if is_blocker_page(result):
        raise AcquisitionError(
            "Pasay health-care page returned an access-control page.",
            result=result,
        )
    document = result.content.decode("utf-8", errors="replace")
    cards = parse_health_cards(document, SOURCE_URL)
    health_centres = [card for card in cards if card["record_type"] == "health_center"]
    clinics = [card for card in cards if card["record_type"] == "lying_in_clinic"]
    if not health_centres:
        raise AcquisitionError("Pasay page contained no city health-centre cards.")

    fetched_at = datetime.now(UTC).isoformat()
    records = [{**card, "page_sha256": result.sha256, "fetched_at": fetched_at} for card in cards]
    for record in records:
        record.pop("contact_text", None)
    payload = {
        "source": "Pasay City Government official website",
        "source_url": SOURCE_URL,
        "retrieved_at": fetched_at,
        "section_heading": SECTION_HEADING,
        "health_centre_count": len(health_centres),
        "lying_in_clinic_count": len(clinics),
        "records": records,
    }
    metadata = {
        "page_sha256": result.sha256,
        "health_centre_count": len(health_centres),
        "lying_in_clinic_count": len(clinics),
        "retrieved_at": fetched_at,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), metadata


class PasayHealthCenterAdapter:
    source_code = "pasay"
    parser_version = "pasay-lgu-health-html-1.0.0"
    schema_version = "pasay-lgu-health-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError("Pasay release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("Pasay artifact contains no health-centre records.")

        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            name = clean_text(record.get("name"))
            address = clean_text(record.get("address"))
            if not any((name, address)):
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            rows.append(
                ParsedRow(
                    source_record_key=(f"PASAY-HEALTH:{_slug(name or 'unnamed')}")[:180],
                    row_reference=f"pasay-health:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("Pasay artifact contained no usable records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "health_centre_level_not_stated",
                    "message": (
                        "The Pasay page labels these facilities 'Health Center' and does "
                        "not state RHU, BHS or barangay-health-centre level. They are "
                        "published as OTHER_HEALTH_FACILITY with the source label retained."
                    ),
                },
                {
                    "code": "lying_in_clinic_retained",
                    "message": (
                        "The page also lists the Doña Marta Lying-In Clinic at the same "
                        "address as the Doña Marta Health Center. It is retained as a "
                        "separate CLINIC record with co-location evidence rather than "
                        "merged into the health centre."
                    ),
                },
                {
                    "code": "contacts_withheld",
                    "message": (
                        "Telephone numbers printed on the cards are withheld from the "
                        "public record and are not stored in this artifact."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The Pasay page supplies postal addresses but no coordinates. "
                        "No geocoding was performed."
                    ),
                },
                {
                    "code": "registry_presence_not_operational_status",
                    "message": (
                        "Presence in the city health-centre directory is registry evidence "
                        "only. Office hours, walk-in access and current operating status "
                        "are not stated."
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
            record_type = clean_text(payload.get("record_type"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "A Pasay health-facility row has no name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if record_type not in {"health_center", "lying_in_clinic"}:
                issues.append(
                    ValidationIssue(
                        "invalid_record_type",
                        "error",
                        f"Pasay facility {name} has an unrecognised record type {record_type!r}.",
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
                        f"Pasay facility {name} appears more than once.",
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
                        f"Pasay facility {name} has no published address.",
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
            record_type = clean_text(payload.get("record_type"))
            service_label = clean_text(payload.get("service_label"))
            source_url = payload.get("source_url")
            address_text = address
            if "pasay" not in address.casefold():
                address_text = f"{address}, Pasay City"
            subtype = "CLINIC" if record_type == "lying_in_clinic" else "OTHER_HEALTH_FACILITY"
            evidence = {
                "source_page": source_url,
                "source_section": SECTION_HEADING,
                "source_record_type": record_type,
                "source_service_label": service_label or None,
                "office_address": address,
                "page_sha256": payload.get("page_sha256"),
                "fetched_at": payload.get("fetched_at"),
                "no_coordinates": "source supplied no coordinates",
            }
            if record_type == "lying_in_clinic":
                evidence["co_located_with"] = "Doña Marta Health Center"
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
                        "Pasay City health-facility directory record. The source supplies "
                        "a printed address and, for some cards, a service label; it does "
                        "not state office hours, walk-in access, service availability or "
                        "current operating status."
                    ),
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=address_text or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="HEALTHCARE",
                            source_value=(
                                service_label
                                or f"{record_type.replace('_', ' ')} listed by Pasay City"
                            ),
                            evidence=evidence,
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OWNER",
                            entity_name="Pasay City Government",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Pasay City health-care programme page"},
                        ),
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Pasay City Government",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Pasay City health-care programme page"},
                        ),
                    ],
                )
            )
        return candidates
