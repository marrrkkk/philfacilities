"""Quezon City ``Places to Visit`` park and public-market adapter.

The Quezon City Government publishes a server-rendered ``/places/<slug>/``
directory. Its public search endpoint advertises 65 place pages covering
libraries, parks, markets, museums, churches, commercial districts and
monuments. This connector deliberately publishes a narrow subset:

* the official Kamuning Market page;
* four park/open-space pages whose official page supplies a postal address and
  public-access evidence (Quezon Memorial Circle, QC Elevated Promenade, Ninoy
  Aquino Parks and Wildlife Center and La Mesa Eco Park).

The 23 Quezon City Public Library pages are not re-ingested. The National
Library of the Philippines public-library release already contains 22 Quezon
City Public Library records; importing the LGU pages as additional facilities
would duplicate published records without a documented merge review. Museum,
church, commercial-district, campus and monument pages are outside this
release's scope and are retained only as excluded source evidence.

Only institutional fields are normalized: facility name, postal address,
official page URL, page checksum, retrieval time, published operating hours,
admission-fee text and coordinates extracted from a Google Maps link embedded
on the official page. Telephone numbers, e-mail addresses, contact-person names
and social-media links are not copied into normalized records. Presence in the
city's visitor directory is not proof of current operation, ownership or
service availability.
"""

from __future__ import annotations

import hashlib
import html as html_module
import json
import re
import time
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
from ..validators import coordinate_in_philippines
from .common import clean_text

PLACES_DIRECTORY_URL = "https://quezoncity.gov.ph/places/"
PLACES_SEARCH_URL = (
    "https://quezoncity.gov.ph/wp-json/wp/v2/search?subtype=places&per_page=100&page=1"
)
PLACE_PREFIX = "https://quezoncity.gov.ph/place/"
PUBLIC_FIELDS = (
    "record_type",
    "name",
    "address",
    "category",
    "facility_subtype",
    "inclusion_class",
    "ownership_type",
    "operator_type",
    "public_access_class",
    "operating_hours",
    "admission_fee",
    "last_updated",
    "latitude",
    "longitude",
    "source_url",
)
PARK_NAMES = frozenset(
    {
        "QC Elevated Promenade",
        "Quezon Memorial Circle",
        "Ninoy Aquino Parks and Wildlife Center",
        "La Mesa Eco Park",
    }
)
CITY_PARK_NAMES = frozenset({"QC Elevated Promenade", "Quezon Memorial Circle"})
LIBRARY_PREFIX = "quezon city public library"

_TAG_RE = re.compile(r"<[^>]+>")
_ANCHOR_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_GOOGLE_MAPS_RE = re.compile(r"https?://(?:www\.)?(?:google\.[^/]+/maps|maps\.app\.goo\.gl)", re.I)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LAST_UPDATED_RE = re.compile(
    r"Last updated on ([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?, \d{4})", re.IGNORECASE
)


def _text(value: Any) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", ", ", str(value), flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", html_module.unescape(_TAG_RE.sub(" ", text)))
    text = re.sub(r"\s*,\s*,+", ", ", text)
    return text.strip(" ,;")


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return text or "unnamed"


def _bounded_key(prefix: str, value: str, limit: int) -> str:
    """Keep a source key within a database column without losing uniqueness."""

    candidate = f"{prefix}{value}"
    if len(candidate) <= limit:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:12]
    keep = limit - len(prefix) - len(digest) - 1
    return f"{prefix}{value[:keep]}-{digest}"


def _page_lines(document: str) -> list[str]:
    stripped = re.sub(r"<script.*?</script>", " ", document, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<style.*?</style>", " ", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<br\s*/?>", "\n", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"</(?:p|div|li|h[1-6])>", "\n", stripped, flags=re.IGNORECASE)
    text = html_module.unescape(_TAG_RE.sub(" ", stripped))
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _label_value(lines: list[str], label: str) -> str:
    lowered = label.lower()
    for index, line in enumerate(lines):
        if lowered not in line.lower():
            continue
        remainder = re.sub(rf"^.*?{re.escape(label)}\s*:?\s*", "", line, flags=re.IGNORECASE)
        remainder = clean_text(remainder)
        if remainder and remainder.lower() != label.lower():
            return remainder[:240]
        for following in lines[index + 1 : index + 4]:
            value = clean_text(following)
            if value and not value.endswith(":"):
                return value[:240]
    return ""


def _fallback_address(lines: list[str], name: str) -> str:
    start = 0
    for index, line in enumerate(lines):
        if name.lower() in line.lower():
            start = index + 1
            break
    for line in lines[start:]:
        lowered = line.lower()
        if "quezon city" not in lowered:
            continue
        if any(
            marker in lowered
            for marker in (
                "quezon city government",
                "quezoncity.gov.ph",
                "places to visit",
                "all rights reserved",
                "privacy policy",
            )
        ):
            continue
        if re.match(r"^\d", line) or any(
            marker in lowered
            for marker in ("street", " st.", " st,", "avenue", " ave", "road", " brgy", "barangay")
        ):
            return clean_text(line)
    return ""


def _map_coordinates(url: str | None) -> tuple[float | None, float | None]:
    if not url:
        return None, None
    decoded = html_module.unescape(url)
    match = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", decoded)
    if not match:
        match = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", decoded)
    if not match:
        destination = re.search(r"!1d(-?\d+(?:\.\d+)?)!2d(-?\d+(?:\.\d+)?)", decoded)
        if destination:
            longitude, latitude = float(destination.group(1)), float(destination.group(2))
            if coordinate_in_philippines(latitude, longitude):
                return latitude, longitude
        return None, None
    latitude, longitude = float(match.group(1)), float(match.group(2))
    if not coordinate_in_philippines(latitude, longitude):
        return None, None
    return latitude, longitude


def parse_places_search(payload: Any) -> list[dict[str, str]]:
    """Return the unique public ``places`` entries from a search response."""

    if not isinstance(payload, list):
        raise ValueError("Quezon City places search response is not a JSON array.")
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or item.get("subtype") != "places":
            continue
        url = clean_text(item.get("url"))
        if not url.startswith(PLACE_PREFIX) or url in seen:
            continue
        seen.add(url)
        records.append(
            {
                "source_key": str(item.get("id") or _slug(url)),
                "title": _text(item.get("title")),
                "url": url,
            }
        )
    return records


def parse_place_page(document: str, source_url: str) -> dict[str, Any]:
    """Parse one public place page without retaining personal contact fields."""

    name_match = _H1_RE.search(document)
    if not name_match:
        name_match = _TITLE_RE.search(document)
    name = _text(name_match.group(1)) if name_match else ""
    name = re.sub(r"\s+-\s+Quezon City Government$", "", name, flags=re.IGNORECASE)

    map_url = ""
    address = ""
    for href, body in _ANCHOR_RE.findall(document):
        candidate = html_module.unescape(href).strip()
        if not _GOOGLE_MAPS_RE.match(candidate):
            continue
        map_url = candidate
        address = _text(body)
        break

    lines = _page_lines(document)
    if not address:
        address = _fallback_address(lines, name)
    latitude, longitude = _map_coordinates(map_url)
    updated = _LAST_UPDATED_RE.search(document)
    return {
        "record_type": "place",
        "name": name,
        "address": address,
        "operating_hours": _label_value(lines, "Operating Hours"),
        "admission_fee": _label_value(lines, "Admission Fee"),
        "last_updated": updated.group(1) if updated else "",
        "map_url": map_url or None,
        "latitude": latitude,
        "longitude": longitude,
        "source_url": source_url,
        "slug": source_url.rstrip("/").rsplit("/", 1)[-1],
    }


def _fetch_place_page(
    acquirer: HttpAcquirer, url: str, *, delay_seconds: float = 0.15
) -> dict[str, Any]:
    result = acquirer.fetch(url, max_bytes=5 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"Quezon City place page {url} returned HTTP {result.status_code}.",
            result=result,
        )
    time.sleep(delay_seconds)
    return {
        "source_url": url,
        "sha256": result.sha256,
        "fetched_at": datetime.now(UTC).isoformat(),
        "content": result.content.decode("utf-8", errors="replace"),
    }


def fetch_quezon_city_places(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Acquire the public places search page and every advertised place page."""

    payload, search_result = acquirer.get_json(
        PLACES_SEARCH_URL,
        headers={"Accept": "application/json"},
        max_bytes=2 * 1024 * 1024,
    )
    entries = parse_places_search(payload)
    if not entries:
        raise AcquisitionError(
            "Quezon City places search returned no place entries.", result=search_result
        )
    places: list[dict[str, Any]] = []
    for entry in entries:
        page = _fetch_place_page(acquirer, entry["url"])
        record = parse_place_page(page.pop("content"), entry["url"])
        record.update(page)
        record["search_title"] = entry["title"]
        places.append(record)
    retrieved_at = datetime.now(UTC)
    artifact = {
        "source": "Quezon City Government Places to Visit directory",
        "source_url": PLACES_DIRECTORY_URL,
        "search_url": PLACES_SEARCH_URL,
        "retrieved_at": retrieved_at.isoformat(),
        "place_count": len(places),
        "places": places,
    }
    metadata = {
        "search_sha256": search_result.sha256,
        "place_pages": len(places),
        "retrieved_at": retrieved_at.isoformat(),
    }
    return json.dumps(artifact, ensure_ascii=False).encode("utf-8"), metadata


def classify_place(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the publishable classification for a place page, if any."""

    name = clean_text(record.get("name")) or ""
    lowered = name.casefold()
    if lowered.startswith(LIBRARY_PREFIX):
        return None
    if lowered == "kamuning market":
        return {
            "record_type": "public_market",
            "category": "public_market",
            "facility_subtype": "PUBLIC_MARKET",
            "facility_kind": "facility",
            "inclusion_class": "PUBLIC_ACCESS_VENUE",
            "ownership_type": "UNKNOWN",
            "operator_type": "UNKNOWN",
            "function_code": "PUBLIC_MARKET",
            "source_value": "Quezon City Places to Visit — Kamuning Market",
            "role_entity": None,
            "role_type": None,
        }
    if name in PARK_NAMES:
        city_park = name in CITY_PARK_NAMES
        joint = name == "La Mesa Eco Park"
        return {
            "record_type": "public_space",
            "category": "public_space",
            "facility_subtype": "PUBLIC_PARK",
            "facility_kind": "site",
            "inclusion_class": "GOVERNMENT_FACILITY" if city_park else "PUBLIC_ACCESS_VENUE",
            "ownership_type": (
                "LOCAL_GOVERNMENT"
                if city_park
                else ("PUBLIC_PRIVATE_JOINT" if joint else "UNKNOWN")
            ),
            "operator_type": (
                "LOCAL_GOVERNMENT"
                if city_park
                else ("PUBLIC_PRIVATE_JOINT" if joint else "UNKNOWN")
            ),
            "function_code": "PUBLIC_SPACE",
            "source_value": f"Quezon City Places to Visit — {name}",
            "role_entity": (
                "Quezon City Government"
                if city_park
                else (
                    "Metropolitan Waterworks and Sewerage System; Quezon City Government; "
                    "Manila Water Company"
                    if joint
                    else None
                )
            ),
            "role_type": "PUBLIC_PRIVATE_JOINT" if joint else "LOCAL_GOVERNMENT",
        }
    return None


def _access_class(record: dict[str, Any]) -> str:
    fee = (clean_text(record.get("admission_fee")) or "").lower()
    if not fee:
        return "UNKNOWN"
    if re.search(r"(?:php|p)\s*\d|\d+\s*(?:php|pesos?)", fee):
        return "PUBLIC_PAID_OR_CONDITIONAL"
    if "free" in fee:
        return "PUBLIC_FREE"
    return "UNKNOWN"


class QuezonCityPlacesAdapter:
    source_code = "quezon-city-places"
    parser_version = "quezon-city-places-html-1.0.0"
    schema_version = "quezon-city-places-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        payload = json.loads(spec.content.decode("utf-8", errors="replace"))
        places = payload.get("places") if isinstance(payload, dict) else None
        if not isinstance(places, list) or not places:
            raise ValueError("Quezon City places artifact contains no place pages.")
        rows: list[ParsedRow] = []
        excluded_libraries = 0
        excluded_other = 0
        for record in places:
            name = clean_text(record.get("name")) or ""
            if not name:
                continue
            classification = classify_place(record)
            included = classification is not None
            if not included:
                if name.casefold().startswith(LIBRARY_PREFIX):
                    excluded_libraries += 1
                else:
                    excluded_other += 1
            raw = {
                "record_type": "place",
                "name": name,
                "address": clean_text(record.get("address")),
                "operating_hours": clean_text(record.get("operating_hours")),
                "admission_fee": clean_text(record.get("admission_fee")),
                "last_updated": record.get("last_updated"),
                "map_url": record.get("map_url"),
                "latitude": record.get("latitude"),
                "longitude": record.get("longitude"),
                "source_url": record.get("source_url"),
                "page_sha256": record.get("sha256"),
                "fetched_at": record.get("fetched_at"),
                "included": included,
                "classification": classification,
            }
            normalized = {
                key: raw[key]
                for key in (
                    "record_type",
                    "name",
                    "address",
                    "operating_hours",
                    "admission_fee",
                    "last_updated",
                    "map_url",
                    "latitude",
                    "longitude",
                    "source_url",
                    "page_sha256",
                    "fetched_at",
                    "included",
                    "classification",
                )
            }
            rows.append(
                ParsedRow(
                    source_record_key=_bounded_key("QC-PLACE:", str(record.get("slug")), 200),
                    row_reference=_bounded_key("places:", str(record.get("slug")), 80),
                    raw_payload=raw,
                    normalized_payload=normalized,
                )
            )
        warnings: list[dict[str, Any]] = [
            {
                "code": "source_subset_only",
                "message": (
                    "The Quezon City Places to Visit directory contains 65 pages covering "
                    "libraries, parks, markets, museums, churches, commercial districts, "
                    "campuses and monuments. This release publishes only Kamuning Market and "
                    "four park/open-space pages. Museum, church, commercial, campus and "
                    "monument pages are excluded from the facility registry."
                ),
                "metadata": {
                    "place_pages": payload.get("place_count"),
                    "excluded_library_pages": excluded_libraries,
                    "excluded_other_pages": excluded_other,
                },
            },
            {
                "code": "libraries_already_published_from_nlp",
                "message": (
                    "The 23 Quezon City Public Library pages are not re-ingested. The "
                    "National Library of the Philippines public-library release already "
                    "contains 22 Quezon City Public Library records. Adding the LGU pages "
                    "would duplicate published records without a documented merge review."
                ),
                "metadata": {"excluded_library_pages": excluded_libraries},
            },
            {
                "code": "personal_and_contact_fields_withheld",
                "message": (
                    "Telephone numbers, e-mail addresses, contact-person names and "
                    "social-media links on the place pages are not copied into normalized "
                    "records. Only institutional address, operating-hours and admission-fee "
                    "text is retained."
                ),
            },
            {
                "code": "map_coordinates_are_not_field_verified",
                "message": (
                    "Coordinates are extracted from Google Maps links embedded on the "
                    "official LGU page and are labelled map_geocoded, not field-verified."
                ),
            },
        ]
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
            if not payload.get("included"):
                continue
            name = clean_text(payload.get("name")) or ""
            address = clean_text(payload.get("address")) or ""
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "A Quezon City place row has no facility name.",
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
                        f"Quezon City place {name} appears more than once.",
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
                        f"Quezon City place {name} has no published address.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            if latitude is not None or longitude is not None:
                if latitude is None or longitude is None:
                    issues.append(
                        ValidationIssue(
                            "incomplete_coordinates",
                            "error",
                            f"Quezon City place {name} has only one coordinate.",
                            row_reference=row.row_reference,
                        )
                    )
                    rejected += 1
                    continue
                if not coordinate_in_philippines(float(latitude), float(longitude)):
                    issues.append(
                        ValidationIssue(
                            "coordinate_outside_philippines",
                            "error",
                            f"Quezon City place {name} has coordinates outside the Philippines.",
                            row_reference=row.row_reference,
                        )
                    )
                    rejected += 1
                    continue
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            if not payload.get("included"):
                continue
            classification = payload.get("classification") or {}
            name = clean_text(payload.get("name")) or ""
            address = clean_text(payload.get("address")) or ""
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            precision = (
                "map_geocoded" if latitude is not None and longitude is not None else "unknown"
            )
            hours = clean_text(payload.get("operating_hours")) or ""
            fee = clean_text(payload.get("admission_fee")) or ""
            access_notes = []
            if hours:
                access_notes.append(f"Published operating hours: {hours}.")
            if fee:
                access_notes.append(f"Published admission fee: {fee}.")
            access_notes.append(
                "The official visitor-directory page does not establish current operating "
                "status or service availability."
            )
            evidence = {
                "source_page": payload.get("source_url"),
                "page_sha256": payload.get("page_sha256"),
                "fetched_at": payload.get("fetched_at"),
                "address": address,
                "google_maps_url": payload.get("map_url"),
                "operating_hours": hours or None,
                "admission_fee": fee or None,
                "last_updated": payload.get("last_updated"),
            }
            roles: list[RoleData] = []
            role_entity = classification.get("role_entity")
            role_type = classification.get("role_type")
            if role_entity:
                roles = [
                    RoleData(
                        role_type="OWNER",
                        entity_name=role_entity,
                        entity_type=role_type,
                        evidence={"basis": "Official Quezon City Places to Visit page"},
                    ),
                    RoleData(
                        role_type="OPERATOR",
                        entity_name=role_entity,
                        entity_type=role_type,
                        evidence={"basis": "Official Quezon City Places to Visit page"},
                    ),
                ]
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type=classification.get("category", "other_qualifying_facility"),
                    facility_subtype=classification.get("facility_subtype"),
                    facility_kind=classification.get("facility_kind", "facility"),
                    inclusion_class=classification.get("inclusion_class"),
                    ownership=(
                        "government"
                        if classification.get("ownership_type") == "LOCAL_GOVERNMENT"
                        else "unknown"
                    ),
                    ownership_type=classification.get("ownership_type", "UNKNOWN"),
                    operator_type=classification.get("operator_type", "UNKNOWN"),
                    public_access_class=_access_class(payload),
                    access_conditions=" ".join(access_notes),
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=float(latitude) if latitude is not None else None,
                        longitude=float(longitude) if longitude is not None else None,
                        precision=precision,
                        method=(
                            "google_maps_link_published_by_lgu"
                            if precision == "map_geocoded"
                            else None
                        ),
                        address_text=address or None,
                    ),
                    functions=[
                        FunctionData(
                            function_code=classification.get(
                                "function_code", "OTHER_PUBLIC_SERVICE"
                            ),
                            source_value=classification.get("source_value"),
                            evidence=evidence,
                        )
                    ],
                    roles=roles,
                )
            )
        return candidates
