"""Professional Regulation Commission (PRC) office locator.

The PRC publishes its regional offices through a public Google Sites page. Each
office card embeds an official map pin (``q=latitude,longitude``) followed by
the office name and a short address. The page is a directory subset: it covers
PRC regional offices, not every satellite, mall-based or host-agency service
counter, and it does not state office hours, ownership of the premises,
accessibility or current operating status.

The adapter preserves the office name, the address text and the embedded map
coordinates. Coordinates are labelled ``map_geocoded`` because the source
supplies a map pin, not a survey-grade GPS observation. No PSGC code, building
ownership, service capacity or current-status claim is inferred.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

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
from .common import clean_text

PRC_LOCATOR_URL = "https://info.prc.gov.ph/prc-office-locator/regional-offices"
IFRAME_RE = re.compile(r"<iframe\b[^>]*\bsrc=\"(?P<src>[^\"]+)\"[^>]*>", re.I | re.S)
PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(?P<body>.*?)</p>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _coordinates(src: str) -> tuple[float, float] | None:
    url = html.unescape(src)
    query = parse_qs(urlparse(url).query)
    raw = (query.get("q") or [None])[0]
    if not raw or "," not in raw:
        return None
    latitude_text, longitude_text = raw.split(",", 1)
    try:
        latitude = float(latitude_text)
        longitude = float(longitude_text)
    except ValueError:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def parse_office_locator(document: str) -> list[dict[str, Any]]:
    """Return one record per official map card on the PRC locator page."""

    iframes = list(IFRAME_RE.finditer(document))
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, iframe in enumerate(iframes):
        coordinates = _coordinates(iframe.group("src"))
        if coordinates is None:
            continue
        end = iframes[index + 1].start() if index + 1 < len(iframes) else len(document)
        segment = document[iframe.end() : end]
        texts = [
            _clean(match.group("body"))
            for match in PARAGRAPH_RE.finditer(segment)
            if _clean(match.group("body"))
        ]
        if len(texts) < 2:
            continue
        office_name = texts[0]
        if not office_name.upper().startswith("PRC"):
            continue
        address = texts[1]
        key = (office_name.casefold(), address.casefold())
        if key in seen:
            continue
        seen.add(key)
        latitude, longitude = coordinates
        records.append(
            {
                "office_name": office_name,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "map_url": html.unescape(iframe.group("src")),
                "source_page": "regional-offices",
            }
        )
    return records


class PrcOfficeAdapter:
    source_code = "prc"
    parser_version = "prc-office-locator-html-1.0.0"
    schema_version = "prc-office-locator-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = parse_office_locator(spec.content.decode("utf-8", "replace"))
        if not records:
            raise ValueError("PRC office locator contained no office cards.")
        rows = [
            ParsedRow(
                source_record_key=f"PRC:OFFICE:{index:02d}",
                row_reference=f"prc-office-locator:{index:02d}",
                raw_payload=record,
                normalized_payload=record,
            )
            for index, record in enumerate(records, start=1)
        ]
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "directory_subset_not_national_inventory",
                    "message": (
                        "The page covers PRC regional offices, not every satellite, "
                        "mall-based or host-agency service counter. It is a directory "
                        "subset, not a national PRC facility inventory."
                    ),
                },
                {
                    "code": "embedded_map_pin_not_surveyed_location",
                    "message": (
                        "Coordinates come from the page's embedded map pin and are "
                        "labelled map_geocoded. They are not survey-grade GPS and do "
                        "not establish building-level precision or the office entrance."
                    ),
                },
                {
                    "code": "presence_is_not_operating_status",
                    "message": (
                        "Inclusion in the locator does not prove current office hours, "
                        "staffing, accessibility or operating status."
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
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_office_name",
                        "fatal",
                        "PRC locator card has no office name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if latitude is None or longitude is None:
                issues.append(
                    ValidationIssue(
                        "missing_coordinates",
                        "error",
                        f"PRC office {name} has no embedded map coordinates.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_office_key",
                        "error",
                        f"PRC office key {row.source_record_key} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(row.source_record_key)
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("office_name"))
            if not name:
                continue
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            address = clean_text(payload.get("address")) or None
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="government_office",
                    facility_subtype="NATIONAL_AGENCY_OFFICE",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    record_status="unknown",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision="map_geocoded",
                        method="official_embedded_map_pin",
                        address_text=address,
                        psgc_code=None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="LICENSING_SERVICE",
                            source_value="Professional Regulation Commission office locator",
                            designation_status="source_listed",
                            evidence={
                                "source": (
                                    "Professional Regulation Commission — Office Locator, "
                                    "Regional Offices"
                                ),
                                "source_page": payload.get("source_page"),
                                "map_url": payload.get("map_url"),
                                "address": address,
                            },
                        )
                    ],
                )
            )
        return candidates
