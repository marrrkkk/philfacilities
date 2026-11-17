"""National Bureau of Investigation (NBI) regional and district office adapter.

The official NBI "Regional & District Offices" page is a public HTML directory.
Each office card carries the office name, a postal location, an embedded Google
Maps frame and contact fields. Some cards also print the regional director or
agent-in-charge name. Those personal names, telephone numbers and protected
e-mail values are retained only in the private acquisition artifact. The public
record exposes the institutional office name, postal location and, where the
official page embeds a map pin, an approximate map-geocoded coordinate.

The page footer states that NBI content is in the public domain unless otherwise
stated. The directory is not a station-level police register, does not state
office hours or walk-in rules, and does not prove that an office is currently
open. Map-embed coordinates are labelled ``map_geocoded``; they are not
field-verified building coordinates.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

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

OFFICES_URL = "https://nbi.gov.ph/regional-district-offices/"
PHILIPPINES_BOUNDS = {"min_lat": 4.2, "max_lat": 21.5, "min_lon": 116.0, "max_lon": 127.0}
PERSONAL_LABELS = (
    "Regional Director",
    "Agent In Charge",
    "Officer In Charge",
    "District Director",
    "Head",
)
PUBLIC_FIELDS = ("office_name", "region", "location", "latitude", "longitude")


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", ", ", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", html.unescape(text))
    text = re.sub(r"\s*,\s*,+", ", ", text)
    text = re.sub(r"\s+,", ",", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return text or "UNNAMED"


def _map_coordinates(embed_url: str | None) -> tuple[float | None, float | None]:
    if not embed_url:
        return None, None
    decoded = unquote(html.unescape(embed_url))
    match = re.search(r"!2d(?P<lon>-?\d+(?:\.\d+)?)!3d(?P<lat>-?\d+(?:\.\d+)?)", decoded)
    if not match:
        match = re.search(r"!3d(?P<lat>-?\d+(?:\.\d+)?)!2d(?P<lon>-?\d+(?:\.\d+)?)", decoded)
    if not match:
        return None, None
    latitude = float(match.group("lat"))
    longitude = float(match.group("lon"))
    if not (
        PHILIPPINES_BOUNDS["min_lat"] <= latitude <= PHILIPPINES_BOUNDS["max_lat"]
        and PHILIPPINES_BOUNDS["min_lon"] <= longitude <= PHILIPPINES_BOUNDS["max_lon"]
    ):
        return None, None
    return latitude, longitude


def parse_office_html(document: str) -> list[dict[str, Any]]:
    """Parse the regional/district office cards from the official NBI page."""

    records: list[dict[str, Any]] = []
    for block in re.findall(
        r'<ul class="reg-offices">(.*?)</ul>', document, flags=re.DOTALL | re.IGNORECASE
    ):
        region_match = re.search(
            r'<div class="blueBar">(.*?)</div>', block, flags=re.DOTALL | re.IGNORECASE
        )
        region = _strip_html(region_match.group(1)) if region_match else ""
        for card in re.findall(r"<li>(.*?)</li>", block, flags=re.DOTALL | re.IGNORECASE):
            name_match = re.search(
                r'<div[^>]*class="fancybox-hidden"[^>]*>.*?<div class="blueBar"><p>(.*?)</p></div>',
                card,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if not name_match:
                continue
            name = _strip_html(name_match.group(1))
            location_match = re.search(
                r"<b>Location</b><p>(.*?)</p>", card, flags=re.DOTALL | re.IGNORECASE
            )
            location = _strip_html(location_match.group(1)) if location_match else ""
            embed_match = re.search(r'<iframe[^>]+src="([^"]+)"', card, flags=re.IGNORECASE)
            latitude, longitude = _map_coordinates(
                html.unescape(embed_match.group(1)) if embed_match else None
            )
            contact_match = re.search(
                r"<b>Contact Details</b><p>(.*?)</p>", card, flags=re.DOTALL | re.IGNORECASE
            )
            contact = _strip_html(contact_match.group(1)) if contact_match else ""
            person_label = ""
            person_name = ""
            for label in PERSONAL_LABELS:
                person_match = re.search(
                    rf"<b>{re.escape(label)}</b><p>(.*?)</p>",
                    card,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                if person_match:
                    person_label = label
                    person_name = _strip_html(person_match.group(1))
                    break
            records.append(
                {
                    "office_name": name,
                    "region": region,
                    "location": location,
                    "latitude": latitude,
                    "longitude": longitude,
                    "contact_details": contact or None,
                    "personal_role": person_label or None,
                    "personal_name": person_name or None,
                    "has_protected_email": "data-cfemail" in card,
                }
            )
    return records


def fetch_nbi_offices(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    result = acquirer.fetch(OFFICES_URL, max_bytes=5 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"NBI regional/district offices page returned HTTP {result.status_code}.",
            result=result,
        )
    document = result.content.decode("utf-8", errors="replace")
    records = parse_office_html(document)
    if not records:
        raise AcquisitionError("NBI regional/district offices page returned no office records.")

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        name = clean_text(record.get("office_name"))
        if not name:
            continue
        key = _slug(name)
        if key in seen:
            continue
        seen.add(key)
        record["office_key"] = key
        unique.append(record)

    artifact = {
        "source_url": OFFICES_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "record_count": len(unique),
        "with_map_coordinates": sum(1 for record in unique if record.get("latitude") is not None),
        "note": (
            "Public NBI regional/district office directory artifact. Personal names, "
            "telephone numbers and protected e-mail values are retained only in this "
            "private raw release; normalized public rows expose office name, region, "
            "postal location and map-embed coordinates. The page footer states that NBI "
            "content is in the public domain unless otherwise stated. Map coordinates "
            "are approximate and not field-verified."
        ),
        "records": unique,
    }
    metadata = {
        "records": len(unique),
        "with_map_coordinates": artifact["with_map_coordinates"],
        "source_url": OFFICES_URL,
    }
    return json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8"), metadata


class NbiOfficeAdapter:
    source_code = "nbi"
    parser_version = "nbi-offices-html-1.0.0"
    schema_version = "nbi-offices-html-v1"
    expected_columns = {"required": {"office_name", "location"}}  # noqa: RUF012

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
            raise ValueError("NBI office release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("NBI office artifact contains no records.")
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            name = clean_text(record.get("office_name"))
            if not name:
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            rows.append(
                ParsedRow(
                    source_record_key=f"NBI:{record.get('office_key') or _slug(name)}",
                    row_reference=f"nbi-html:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("NBI office artifact contained no usable records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "personal_fields_withheld",
                    "message": (
                        "Regional director/agent-in-charge names, telephone numbers and "
                        "protected e-mail values remain in the private artifact and are "
                        "excluded from the normalized public payload."
                    ),
                },
                {
                    "code": "map_embed_coordinates_are_approximate",
                    "message": (
                        "Coordinates were extracted from the official page's embedded "
                        "Google Maps frames and are labelled 'map_geocoded', not "
                        "field-verified building coordinates."
                    ),
                },
                {
                    "code": "directory_not_operational_status",
                    "message": (
                        "Directory presence is not proof of current operation, office "
                        "hours or walk-in availability."
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
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_office_name",
                        "fatal",
                        "An NBI office row has no office name.",
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
                        f"NBI office key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if not clean_text(payload.get("location")):
                issues.append(
                    ValidationIssue(
                        "missing_office_location",
                        "warning",
                        f"NBI office {name} has no postal location.",
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
            if not name:
                continue
            region = clean_text(payload.get("region"))
            location = clean_text(payload.get("location"))
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            precision = (
                "map_geocoded" if latitude is not None and longitude is not None else "unknown"
            )
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=f"NBI {name}"[:300],
                    facility_type="government_office",
                    facility_subtype="NATIONAL_AGENCY_OFFICE",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="SERVICE_USERS_ONLY",
                    access_conditions=(
                        "NBI regional/district office. The directory does not state "
                        "office hours, appointment requirements or walk-in rules."
                    ),
                    record_status="unknown",
                    location=LocationData(
                        latitude=float(latitude) if latitude is not None else None,
                        longitude=float(longitude) if longitude is not None else None,
                        precision=precision,
                        method="google_maps_embed_on_official_page"
                        if precision == "map_geocoded"
                        else None,
                        address_text=location or None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="PUBLIC_SERVICE_COUNTER",
                            source_value="NBI regional/district office",
                            designation_status="unknown",
                            evidence={
                                "source": "NBI Regional & District Offices page",
                                "region": region,
                                "location": location,
                            },
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="National Bureau of Investigation",
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "Official NBI office directory"},
                        )
                    ],
                )
            )
        return candidates
