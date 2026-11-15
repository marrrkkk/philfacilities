"""Quezon City local-government facility directories adapter.

The Quezon City Government publishes two server-rendered public directories:

* ``/health_centers/<slug>/`` pages. Most carry the WordPress category
  ``brgy-health-centers``; the sitemap also contains five COVID-19
  ``swab-testing-center`` pages and one ``hope-facilities`` information page.
* ``/brgy-directory/<slug>/`` pages. Each page carries the barangay's official
  address, contact fields, officials and schools. A subset links the address to
  a Google Maps place explicitly named ``... Barangay Hall``.

The adapter publishes two narrowly defined subsets:

* health-centre pages formally categorised ``brgy-health-centers``, excluding
  seven administrative-office entries (``Central Office`` and the six District
  Health Offices) that would duplicate the host health centre;
* barangay directory pages whose address link explicitly identifies a
  ``Barangay Hall``.

The remaining source rows are retained in the private release payload and
reported as warnings. They are not silently converted into facilities. In
particular, a barangay directory page without a hall-labelled map place proves
that the barangay exists and publishes a contact address, not that the address
is a barangay hall. COVID-19 swab-testing designations are not treated as
current health facilities without current-operational evidence.

Only institutional fields reach the public record. Telephone numbers, e-mail
addresses, social-media links, barangay officials and school listings are
discarded from normalized payloads; health-centre telephone numbers remain only
in the private raw payload. Coordinates come solely from Google Maps links
embedded on the official page and are labelled ``map_geocoded``; they are not
field-verified building coordinates. No PSGC code, walk-in access rule,
operating status, service schedule or capacity is inferred.

Source scope is Quezon City only. Presence in the LGU directory is not proof of
current operation, public access or service availability.
"""

from __future__ import annotations

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
    ServiceData,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text, normalise_code

SOURCE_URL = "https://quezoncity.gov.ph/qc-barangays/"
HEALTH_SITEMAP_URL = "https://quezoncity.gov.ph/health_centers-sitemap.xml"
BARANGAY_SITEMAP_URL = "https://quezoncity.gov.ph/brgy-directory-sitemap.xml"
HEALTH_PREFIX = "https://quezoncity.gov.ph/health_centers/"
BARANGAY_PREFIX = "https://quezoncity.gov.ph/brgy-directory/"
HEALTH_CATEGORY_INCLUDED = "brgy-health-centers"
PUBLIC_FIELDS = (
    "record_type",
    "name",
    "address",
    "district",
    "category",
    "map_place",
    "latitude",
    "longitude",
    "source_url",
)
PHILIPPINES_BOUNDS = {"min_lat": 4.2, "max_lat": 21.5, "min_lon": 116.0, "max_lon": 127.0}
HEALTH_OFFICE_NAMES = frozenset(
    {
        "Central Office",
        "District 1 Health Office",
        "District 2 Health Office",
        "District 3 Health Office",
        "District 4 Health Office",
        "District 5 Health Office",
        "District 6 Health Office",
    }
)

_TAG_RE = re.compile(r"<[^>]+>")
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_CATEGORY_RE = re.compile(r"health_center_category-([a-z0-9-]+)", re.IGNORECASE)
_HC_NAME_RE = re.compile(
    r'<h4[^>]*class="[^"]*healthcenter-title[^"]*"[^>]*>(.*?)</h4>',
    re.IGNORECASE | re.DOTALL,
)
_HC_ADDRESS_RE = re.compile(
    r"dashicons-location[^>]*>\s*</i>\s*(.*?)</li>", re.IGNORECASE | re.DOTALL
)
_HC_PHONE_RE = re.compile(r"dashicons-phone[^>]*>\s*</i>\s*(.*?)</li>", re.IGNORECASE | re.DOTALL)
_H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_ADDRESS_PARAGRAPH_RE = re.compile(
    r"<p[^>]*>(?:(?!</p>).)*?<strong>Address</strong>.*?</p>",
    re.IGNORECASE | re.DOTALL,
)
_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_GOOGLE_MAPS_RE = re.compile(r"https?://(?:www\.)?(?:google\.[^/]+/maps|maps\.app\.goo\.gl)", re.I)
_DISTRICT_RE = re.compile(r"\bDistrict\s+\d+\b", re.IGNORECASE)


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


def parse_sitemap_urls(document: str, *, prefix: str) -> list[str]:
    """Return unique, same-directory URLs from a public sitemap."""

    urls: list[str] = []
    seen: set[str] = set()
    for raw in _LOC_RE.findall(document):
        url = html_module.unescape(raw).strip()
        if not url.startswith(prefix) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _google_map_link(paragraph: str | None) -> tuple[str | None, str | None]:
    """Return the first Google Maps link and its place name, if stated."""

    if not paragraph:
        return None, None
    for href in _HREF_RE.findall(paragraph):
        url = html_module.unescape(href).strip()
        if not _GOOGLE_MAPS_RE.match(url):
            continue
        place_match = re.search(r"/place/([^/@?]+)", url)
        place = None
        if place_match:
            place = clean_text(place_match.group(1).replace("+", " "))
            place = html_module.unescape(place)
        return url, place or None
    return None, None


def _map_coordinates(url: str | None) -> tuple[float | None, float | None]:
    if not url:
        return None, None
    decoded = html_module.unescape(url)
    match = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", decoded)
    if not match:
        match = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", decoded)
    if not match:
        return None, None
    latitude, longitude = float(match.group(1)), float(match.group(2))
    if not (
        PHILIPPINES_BOUNDS["min_lat"] <= latitude <= PHILIPPINES_BOUNDS["max_lat"]
        and PHILIPPINES_BOUNDS["min_lon"] <= longitude <= PHILIPPINES_BOUNDS["max_lon"]
    ):
        return None, None
    return latitude, longitude


def parse_health_center_page(document: str, source_url: str) -> dict[str, Any]:
    """Parse one Quezon City health-centre page without retaining contact fields."""

    name_match = _HC_NAME_RE.search(document)
    if not name_match:
        name_match = _H2_RE.search(document)
    name = _text(name_match.group(1)) if name_match else ""
    address_match = _HC_ADDRESS_RE.search(document)
    address = _text(address_match.group(1)) if address_match else ""
    phone_match = _HC_PHONE_RE.search(document)
    phone = _text(phone_match.group(1)) if phone_match else ""
    category_match = _CATEGORY_RE.search(document)
    category = category_match.group(1).lower() if category_match else None
    district_match = _DISTRICT_RE.search(address)
    return {
        "record_type": "health_center",
        "name": name,
        "address": address,
        "phone": phone or None,
        "category": category,
        "district": district_match.group(0) if district_match else None,
        "source_url": source_url,
        "slug": source_url.rstrip("/").rsplit("/", 1)[-1],
    }


def parse_barangay_page(document: str, source_url: str) -> dict[str, Any]:
    """Parse one Quezon City barangay directory page.

    The page's address paragraph may link to a Google Maps place. Only a place
    explicitly named ``Barangay Hall`` is treated as hall evidence.
    """

    name_match = _H2_RE.search(document)
    name = _text(name_match.group(1)) if name_match else ""
    paragraph_match = _ADDRESS_PARAGRAPH_RE.search(document)
    paragraph = paragraph_match.group(0) if paragraph_match else None
    address = _text(paragraph) if paragraph else ""
    address = re.sub(r"^\s*Address\s*:?\s*", "", address, flags=re.IGNORECASE)
    address = address.lstrip(" ,;:")
    map_url, map_place = _google_map_link(paragraph)
    latitude, longitude = _map_coordinates(map_url)
    district_match = _DISTRICT_RE.search(address)
    hall_evidence = bool(map_place and "barangay hall" in map_place.lower())
    return {
        "record_type": "barangay",
        "name": name,
        "address": address,
        "map_url": map_url,
        "map_place": map_place,
        "latitude": latitude,
        "longitude": longitude,
        "hall_evidence": hall_evidence,
        "district": district_match.group(0) if district_match else None,
        "source_url": source_url,
        "slug": source_url.rstrip("/").rsplit("/", 1)[-1],
    }


def _fetch_page(acquirer: HttpAcquirer, url: str, *, delay_seconds: float = 0.15) -> dict[str, Any]:
    result = acquirer.fetch(url, max_bytes=5 * 1024 * 1024)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"Quezon City directory page {url} returned HTTP {result.status_code}.",
            result=result,
        )
    time.sleep(delay_seconds)
    return {
        "source_url": url,
        "sha256": result.sha256,
        "fetched_at": datetime.now(UTC).isoformat(),
        "content": result.content.decode("utf-8", errors="replace"),
    }


def fetch_quezon_city_directory(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Acquire both QC sitemaps and every advertised directory page.

    The function fails rather than silently publishing a partial directory when
    any advertised page cannot be retrieved.
    """

    health_sitemap = acquirer.fetch(HEALTH_SITEMAP_URL, max_bytes=2 * 1024 * 1024)
    if health_sitemap.status_code >= 400:
        raise AcquisitionError(
            f"Quezon City health-centre sitemap returned HTTP {health_sitemap.status_code}.",
            result=health_sitemap,
        )
    barangay_sitemap = acquirer.fetch(BARANGAY_SITEMAP_URL, max_bytes=2 * 1024 * 1024)
    if barangay_sitemap.status_code >= 400:
        raise AcquisitionError(
            f"Quezon City barangay sitemap returned HTTP {barangay_sitemap.status_code}.",
            result=barangay_sitemap,
        )

    health_urls = parse_sitemap_urls(
        health_sitemap.content.decode("utf-8", errors="replace"), prefix=HEALTH_PREFIX
    )
    barangay_urls = parse_sitemap_urls(
        barangay_sitemap.content.decode("utf-8", errors="replace"), prefix=BARANGAY_PREFIX
    )
    if not health_urls:
        raise AcquisitionError("Quezon City health-centre sitemap contained no directory URLs.")
    if not barangay_urls:
        raise AcquisitionError("Quezon City barangay sitemap contained no directory URLs.")

    health_centers: list[dict[str, Any]] = []
    for url in health_urls:
        page = _fetch_page(acquirer, url)
        record = parse_health_center_page(page.pop("content"), url)
        record.update(page)
        health_centers.append(record)

    barangays: list[dict[str, Any]] = []
    for url in barangay_urls:
        page = _fetch_page(acquirer, url)
        record = parse_barangay_page(page.pop("content"), url)
        record.update(page)
        barangays.append(record)

    retrieved_at = datetime.now(UTC)
    payload = {
        "source": "Quezon City Government official website",
        "source_url": SOURCE_URL,
        "health_sitemap_url": HEALTH_SITEMAP_URL,
        "barangay_sitemap_url": BARANGAY_SITEMAP_URL,
        "retrieved_at": retrieved_at.isoformat(),
        "health_center_pages": len(health_centers),
        "barangay_pages": len(barangays),
        "health_centers": health_centers,
        "barangays": barangays,
    }
    metadata = {
        "health_sitemap_sha256": health_sitemap.sha256,
        "barangay_sitemap_sha256": barangay_sitemap.sha256,
        "health_center_pages": len(health_centers),
        "barangay_pages": len(barangays),
        "explicit_barangay_hall_pages": sum(
            1 for record in barangays if record.get("hall_evidence")
        ),
        "retrieved_at": retrieved_at.isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), metadata


class QuezonCityLguAdapter:
    source_code = "quezon-city"
    parser_version = "quezon-city-lgu-html-1.0.0"
    schema_version = "quezon-city-lgu-html-v1"
    expected_columns = {  # noqa: RUF012
        "required": {"record_type", "name", "address", "source_url"}
    }

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def _included_health(self, record: dict[str, Any]) -> bool:
        return (
            record.get("category") == HEALTH_CATEGORY_INCLUDED
            and record.get("name") not in HEALTH_OFFICE_NAMES
        )

    def _included_barangay(self, record: dict[str, Any]) -> bool:
        return bool(record.get("hall_evidence"))

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        payload = json.loads(spec.content.decode("utf-8", errors="replace"))
        rows: list[ParsedRow] = []
        excluded_health = 0
        excluded_barangays = 0
        for record in payload.get("health_centers", []):
            name = clean_text(record.get("name"))
            if not name:
                continue
            included = self._included_health(record)
            if not included:
                excluded_health += 1
            raw = {
                "record_type": "health_center",
                "name": name,
                "address": clean_text(record.get("address")),
                "phone": record.get("phone"),
                "category": record.get("category"),
                "district": record.get("district"),
                "source_url": record.get("source_url"),
                "page_sha256": record.get("sha256"),
                "fetched_at": record.get("fetched_at"),
                "included": included,
            }
            normalized = {
                key: raw[key]
                for key in (
                    "record_type",
                    "name",
                    "address",
                    "category",
                    "district",
                    "source_url",
                    "page_sha256",
                    "fetched_at",
                    "included",
                )
            }
            rows.append(
                ParsedRow(
                    source_record_key=normalise_code(f"QC-HEALTH:{record.get('slug')}")[:180],
                    row_reference=f"health_centers:{record.get('slug')}",
                    raw_payload=raw,
                    normalized_payload=normalized,
                )
            )
        for record in payload.get("barangays", []):
            name = clean_text(record.get("name"))
            if not name:
                continue
            included = self._included_barangay(record)
            if not included:
                excluded_barangays += 1
            raw = {
                "record_type": "barangay",
                "name": name,
                "address": clean_text(record.get("address")),
                "map_url": record.get("map_url"),
                "map_place": record.get("map_place"),
                "latitude": record.get("latitude"),
                "longitude": record.get("longitude"),
                "hall_evidence": included,
                "district": record.get("district"),
                "source_url": record.get("source_url"),
                "page_sha256": record.get("sha256"),
                "fetched_at": record.get("fetched_at"),
                "included": included,
            }
            normalized = {
                key: raw[key]
                for key in (
                    "record_type",
                    "name",
                    "address",
                    "map_url",
                    "map_place",
                    "latitude",
                    "longitude",
                    "hall_evidence",
                    "district",
                    "source_url",
                    "page_sha256",
                    "fetched_at",
                    "included",
                )
            }
            rows.append(
                ParsedRow(
                    source_record_key=normalise_code(f"QC-BARANGAY:{record.get('slug')}")[:180],
                    row_reference=f"brgy-directory:{record.get('slug')}",
                    raw_payload=raw,
                    normalized_payload=normalized,
                )
            )
        warnings: list[dict[str, Any]] = [
            {
                "code": "source_subset_only",
                "message": (
                    "The Quezon City sitemaps advertise more pages than this release "
                    "treats as facilities. Health pages outside the brgy-health-centers "
                    "category, health administrative offices and barangay pages without "
                    "an explicit Barangay Hall map place are retained in the private "
                    "payload and excluded from the facility registry."
                ),
                "metadata": {
                    "health_pages": payload.get("health_center_pages"),
                    "barangay_pages": payload.get("barangay_pages"),
                    "excluded_health_rows": excluded_health,
                    "excluded_barangay_rows": excluded_barangays,
                },
            },
            {
                "code": "personal_and_contact_fields_withheld",
                "message": (
                    "Health-centre telephone numbers remain only in the private raw "
                    "payload. Barangay officials, telephone numbers, e-mail addresses "
                    "and social-media links are not retained in normalized records."
                ),
            },
            {
                "code": "no_coordinates_for_health_centres",
                "message": (
                    "Health-centre pages supply postal addresses but no coordinates. "
                    "No geocoding was performed."
                ),
            },
            {
                "code": "map_coordinates_are_not_field_verified",
                "message": (
                    "Barangay-hall coordinates are extracted from Google Maps links "
                    "published on the official LGU page and are labelled map_geocoded."
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
        included = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("name"))
            address = clean_text(payload.get("address"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "A Quezon City directory row has no facility or barangay name.",
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
                        f"Quezon City record {name} appears more than once.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(row.source_record_key)
            if not payload.get("included"):
                continue
            included += 1
            if not address:
                issues.append(
                    ValidationIssue(
                        "missing_address",
                        "fatal",
                        f"Quezon City facility {name} has no published address.",
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
                            f"Quezon City facility {name} has only one coordinate.",
                            row_reference=row.row_reference,
                        )
                    )
                    continue
                if not (
                    PHILIPPINES_BOUNDS["min_lat"]
                    <= float(latitude)
                    <= PHILIPPINES_BOUNDS["max_lat"]
                    and PHILIPPINES_BOUNDS["min_lon"]
                    <= float(longitude)
                    <= PHILIPPINES_BOUNDS["max_lon"]
                ):
                    issues.append(
                        ValidationIssue(
                            "coordinate_outside_philippines",
                            "error",
                            f"Quezon City facility {name} has coordinates outside the Philippines.",
                            row_reference=row.row_reference,
                        )
                    )
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
            name = clean_text(payload.get("name"))
            address = clean_text(payload.get("address"))
            district = clean_text(payload.get("district"))
            source_url = payload.get("source_url")
            if payload.get("record_type") == "health_center":
                location_text = ", ".join(part for part in (address, "Quezon City") if part)
                evidence = {
                    "source_page": source_url,
                    "page_sha256": payload.get("page_sha256"),
                    "fetched_at": payload.get("fetched_at"),
                    "category": payload.get("category"),
                    "district": district,
                    "address": address,
                }
                candidates.append(
                    FacilityCandidate(
                        source_record_key=row.source_record_key,
                        source_entity_id=row.source_record_key,
                        row_reference=row.row_reference,
                        display_name=name,
                        facility_type="health_facility",
                        facility_subtype="BARANGAY_HEALTH_STATION",
                        facility_kind="facility",
                        inclusion_class="GOVERNMENT_FACILITY",
                        ownership="government",
                        ownership_type="LOCAL_GOVERNMENT",
                        operator_type="LOCAL_GOVERNMENT",
                        public_access_class="UNKNOWN",
                        access_conditions=(
                            "Quezon City health-centre directory record. The page does not "
                            "state walk-in access, service hours, service availability or "
                            "current operating status."
                        ),
                        record_status="active_in_registry",
                        location=LocationData(
                            address_text=location_text or None,
                            precision="unknown",
                        ),
                        functions=[
                            FunctionData(
                                function_code="HEALTHCARE",
                                source_value="Quezon City health centre",
                                evidence=evidence,
                            )
                        ],
                        services=[
                            ServiceData(
                                service_code="PRIMARY_HEALTH_CARE",
                                service_name="Barangay health-centre services",
                                source_field="Quezon City health-centre directory",
                                details={"district": district, "category": payload.get("category")},
                            )
                        ],
                        roles=[
                            RoleData(
                                role_type="OWNER",
                                entity_name="Quezon City Government",
                                entity_type="LOCAL_GOVERNMENT",
                                evidence={"basis": "Quezon City health-centre directory"},
                            ),
                            RoleData(
                                role_type="OPERATOR",
                                entity_name="Quezon City Government",
                                entity_type="LOCAL_GOVERNMENT",
                                evidence={"basis": "Quezon City health-centre directory"},
                            ),
                        ],
                    )
                )
                continue
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            precision = (
                "map_geocoded" if latitude is not None and longitude is not None else "unknown"
            )
            map_place = clean_text(payload.get("map_place"))
            evidence = {
                "source_page": source_url,
                "page_sha256": payload.get("page_sha256"),
                "fetched_at": payload.get("fetched_at"),
                "google_maps_url": payload.get("map_url"),
                "google_maps_place": map_place,
                "district": district,
                "address": address,
                "hall_evidence": "Google Maps place name on the LGU page contains 'Barangay Hall'",
            }
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=map_place or f"{name} Barangay Hall",
                    facility_type="government_office",
                    facility_subtype="BARANGAY_HALL",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="LOCAL_GOVERNMENT",
                    operator_type="LOCAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    access_conditions=(
                        "Quezon City barangay directory record with an explicit Barangay "
                        "Hall map place. The page does not state walk-in access, office "
                        "hours or current operating status."
                    ),
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=float(latitude) if latitude is not None else None,
                        longitude=float(longitude) if longitude is not None else None,
                        precision=precision,
                        method=(
                            "google_maps_place_link_published_by_lgu"
                            if precision == "map_geocoded"
                            else None
                        ),
                        address_text=address or None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="BARANGAY_HALL",
                            source_value="Barangay Hall map place",
                            evidence=evidence,
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OWNER",
                            entity_name=f"Barangay {name}",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Quezon City barangay directory"},
                        ),
                        RoleData(
                            role_type="OPERATOR",
                            entity_name=f"Barangay {name}",
                            entity_type="LOCAL_GOVERNMENT",
                            evidence={"basis": "Quezon City barangay directory"},
                        ),
                    ],
                )
            )
        return candidates
