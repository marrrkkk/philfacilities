"""NMIS NARIS accredited meat-establishment directory parser.

The NARIS public page renders an accredited-establishments list and a Leaflet map.
The list is generated from a server-side ``ltoLocations`` JSON array containing the
company name, LTO number, establishment type, address parts and, for some rows, a
cached address geocode. The public page carries an "All rights reserved" notice and
states that pins use each company's saved full address.

PhilFacilities publishes only the factual establishment fields needed for facility
discovery. The establishment type is preserved; it is not treated as an operational
status. A company name containing "Municipal" is the only evidence used to classify
a municipal-named establishment as local-government operated; the page does not
state ownership, operator, public access or LTO validity, so that classification is
recorded as a name-based caveat rather than a legal ownership finding.

The page currently lists 362 rows but only 357 unique LTO numbers. Five LTOs have
two address variants. One facility record is produced per LTO and every variant is
retained in the source payload.
"""

from __future__ import annotations

import html as html_module
import json
import re
from collections import Counter
from typing import Any, ClassVar

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
from .common import clean_text

NMIS_NARIS_URL = "https://naris.nmis.gov.ph/"
SOURCE_COLUMNS = (
    "company_name",
    "full_address",
    "region_code",
    "province_code",
    "municipality_code",
    "barangay",
    "lto_number",
    "establishment_type",
    "geocode_address",
    "cached_lat",
    "cached_lng",
)

_TYPE_SUBTYPES = {
    "slaughterhouse": "SLAUGHTERHOUSE",
    "coldstorage_warehouse": "COLD_STORAGE_WAREHOUSE",
    "cold_storage_warehouse": "COLD_STORAGE_WAREHOUSE",
    "meat_cutting_plant": "MEAT_CUTTING_PLANT",
    "poultry_dressing_plant": "POULTRY_DRESSING_PLANT",
    "meat_distribution_center": "MEAT_DISTRIBUTION_CENTER",
}
_TYPE_LABELS = {
    "slaughterhouse": "Slaughterhouse",
    "coldstorage_warehouse": "Cold storage warehouse",
    "cold_storage_warehouse": "Cold storage warehouse",
    "meat_cutting_plant": "Meat cutting plant",
    "poultry_dressing_plant": "Poultry dressing plant",
    "meat_distribution_center": "Meat distribution center",
}
_LOCAL_GOVERNMENT_RE = re.compile(
    r"\b(?:municipal|city government|provincial government|lgu)\b", re.IGNORECASE
)
_LTO_JSON_RE = re.compile(r"const\s+ltoLocations\s*=\s*(\[.*?\])\s*;", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html_module.unescape(_TAG_RE.sub(" ", str(value)))).strip()


def parse_naris_html(html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one record per LTO, retaining duplicate address variants."""

    match = _LTO_JSON_RE.search(html)
    if not match:
        raise ValueError(
            "NARIS page did not contain the expected ltoLocations array; the page "
            "structure changed or the response was not the public directory."
        )
    try:
        raw_rows = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"NARIS ltoLocations array is not valid JSON: {exc}") from exc
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("NARIS ltoLocations array was empty.")

    grouped: dict[str, list[dict[str, Any]]] = {}
    skipped = 0
    for raw in raw_rows:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        lto = clean_text(raw.get("lto_number"))
        company = clean_text(raw.get("company_name"))
        if not lto or not company:
            skipped += 1
            continue
        grouped.setdefault(lto, []).append(raw)

    records: list[dict[str, Any]] = []
    duplicate_rows = 0
    cached_coordinate_rows = 0
    for lto, variants in grouped.items():
        first = variants[0]
        duplicate_rows += max(0, len(variants) - 1)
        coordinate_variants = [
            variant
            for variant in variants
            if variant.get("cached_lat") is not None and variant.get("cached_lng") is not None
        ]
        if coordinate_variants:
            cached_coordinate_rows += 1
        coordinate_source = coordinate_variants[0] if coordinate_variants else first
        records.append(
            {
                "lto_number": lto,
                "company_name": clean_text(first.get("company_name")),
                "establishment_type": clean_text(first.get("establishment_type")).lower(),
                "full_address": clean_text(first.get("full_address")) or None,
                "region_code": clean_text(first.get("region_code")) or None,
                "province_name": clean_text(first.get("province_code")) or None,
                "municipality_name": clean_text(first.get("municipality_code")) or None,
                "barangay_name": clean_text(first.get("barangay")) or None,
                "cached_lat": coordinate_source.get("cached_lat"),
                "cached_lng": coordinate_source.get("cached_lng"),
                "variant_count": len(variants),
                "address_variants": [
                    {
                        "full_address": clean_text(variant.get("full_address")) or None,
                        "province_name": clean_text(variant.get("province_code")) or None,
                        "municipality_name": clean_text(variant.get("municipality_code")) or None,
                        "barangay_name": clean_text(variant.get("barangay")) or None,
                        "cached_lat": variant.get("cached_lat"),
                        "cached_lng": variant.get("cached_lng"),
                    }
                    for variant in variants
                ],
            }
        )

    type_counts = Counter(record["establishment_type"] for record in records)
    metadata = {
        "raw_rows": len(raw_rows),
        "unique_lto_rows": len(records),
        "duplicate_lto_rows": duplicate_rows,
        "skipped_rows": skipped,
        "rows_with_cached_coordinates": cached_coordinate_rows,
        "type_counts": dict(sorted(type_counts.items())),
    }
    return records, metadata


class NmisNarisDirectoryAdapter:
    source_code = "nmis"
    parser_version = "nmis-naris-html-1.0.0"
    schema_version = "nmis-naris-lto-v1"
    expected_columns: ClassVar[dict[str, set[str]]] = {
        "required": {
            "company_name",
            "lto_number",
            "establishment_type",
            "full_address",
        }
    }

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records, metadata = parse_naris_html(spec.content.decode("utf-8", errors="replace"))
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            raw_payload = {**record, "_row": index}
            rows.append(
                ParsedRow(
                    source_record_key=f"LTO:{record['lto_number']}",
                    row_reference=f"naris:lto:{record['lto_number']}",
                    raw_payload=raw_payload,
                    normalized_payload=raw_payload,
                )
            )
        warnings: list[dict[str, Any]] = [
            {
                "code": "duplicate_lto_rows",
                "message": (
                    f"{metadata['raw_rows']} rendered rows collapsed to "
                    f"{metadata['unique_lto_rows']} unique LTO records. "
                    f"{metadata['duplicate_lto_rows']} duplicate LTO row(s) have "
                    "address variants; all variants are retained in the source payload."
                ),
                "metadata": metadata,
            },
            {
                "code": "no_operational_status_or_validity",
                "message": (
                    "NARIS publishes accredited establishments and LTO numbers but no "
                    "LTO validity dates, operating status, public-access rules or "
                    "coordinates of its own. Cached address geocodes are used only where "
                    "present and are labelled geocoded, not survey coordinates."
                ),
            },
        ]
        if metadata["skipped_rows"]:
            warnings.append(
                {
                    "code": "incomplete_rows_skipped",
                    "message": (
                        f"{metadata['skipped_rows']} NARIS row(s) lacked an LTO number or "
                        "company name and were not turned into facility records."
                    ),
                }
            )
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=warnings,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        rejected = 0
        seen: set[str] = set()
        for row in parsed.rows:
            payload = row.normalized_payload
            lto = clean_text(payload.get("lto_number"))
            company = clean_text(payload.get("company_name"))
            establishment_type = clean_text(payload.get("establishment_type"))
            if not lto:
                issues.append(
                    ValidationIssue(
                        "missing_lto_number",
                        "fatal",
                        "NARIS establishment row has no LTO number.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not company:
                issues.append(
                    ValidationIssue(
                        "missing_company_name",
                        "fatal",
                        f"NARIS LTO {lto} has no company name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if establishment_type not in _TYPE_SUBTYPES:
                issues.append(
                    ValidationIssue(
                        "unknown_establishment_type",
                        "warning",
                        f"NARIS LTO {lto} has an unrecognized establishment type "
                        f"{establishment_type!r}; it is retained with the fallback subtype.",
                        row_reference=row.row_reference,
                    )
                )
            if not clean_text(payload.get("full_address")):
                issues.append(
                    ValidationIssue(
                        "missing_address",
                        "warning",
                        f"NARIS LTO {lto} has no postal address.",
                        row_reference=row.row_reference,
                    )
                )
            latitude = payload.get("cached_lat")
            longitude = payload.get("cached_lng")
            if (latitude is None) != (longitude is None):
                issues.append(
                    ValidationIssue(
                        "partial_coordinates",
                        "warning",
                        f"NARIS LTO {lto} has only one cached coordinate value.",
                        row_reference=row.row_reference,
                    )
                )
            elif latitude is not None and (
                not isinstance(latitude, (int, float))
                or not isinstance(longitude, (int, float))
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                issues.append(
                    ValidationIssue(
                        "coordinate_range",
                        "warning",
                        f"NARIS LTO {lto} has an invalid cached coordinate.",
                        row_reference=row.row_reference,
                    )
                )
            if lto in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_lto_number",
                        "error",
                        f"NARIS LTO {lto} appears more than once after grouping.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
            seen.add(lto)
        return ValidationResult(
            issues=issues,
            accepted_rows=len(parsed.rows) - rejected,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            lto = clean_text(payload.get("lto_number"))
            company = clean_text(payload.get("company_name"))
            establishment_type = clean_text(payload.get("establishment_type"))
            if not lto or not company:
                continue
            subtype = _TYPE_SUBTYPES.get(establishment_type, "OTHER_AGRICULTURAL_FACILITY")
            type_label = _TYPE_LABELS.get(establishment_type, establishment_type)
            address = clean_text(payload.get("full_address")) or None
            latitude = payload.get("cached_lat")
            longitude = payload.get("cached_lng")
            has_coordinates = isinstance(latitude, (int, float)) and isinstance(
                longitude, (int, float)
            )
            if has_coordinates and not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                has_coordinates = False
            local_government = bool(_LOCAL_GOVERNMENT_RE.search(company))
            ownership_type = "LOCAL_GOVERNMENT" if local_government else "PRIVATE_UNSPECIFIED"
            inclusion_class = (
                "GOVERNMENT_FACILITY" if local_government else "PRIVATE_PUBLIC_SERVICE_PROVIDER"
            )
            evidence = {
                "source_page": NMIS_NARIS_URL,
                "lto_number": lto,
                "establishment_type": establishment_type,
                "company_name": company,
                "address_variants": payload.get("address_variants", []),
                "classification_basis": (
                    "company name contains a municipal/local-government token"
                    if local_government
                    else "LTO holder is a non-government company; ownership is not stated"
                ),
            }
            functions = [
                FunctionData(
                    function_code="FOOD_SAFETY",
                    source_value=type_label,
                    evidence=evidence,
                )
            ]
            if subtype == "SLAUGHTERHOUSE":
                functions.append(
                    FunctionData(
                        function_code="SLAUGHTERHOUSE",
                        source_value=type_label,
                        evidence=evidence,
                    )
                )
            roles = [
                RoleData(
                    role_type="OPERATOR",
                    entity_name=company,
                    entity_type=ownership_type,
                    evidence={"basis": "LTO holder named in the NARIS accredited list"},
                ),
                RoleData(
                    role_type="LICENSOR",
                    entity_name="National Meat Inspection Service",
                    entity_type="NATIONAL_GOVERNMENT",
                    evidence={"basis": "NARIS is the NMIS LTO accreditation registry"},
                ),
            ]
            if local_government:
                roles.append(
                    RoleData(
                        role_type="OWNER",
                        entity_name=company,
                        entity_type="LOCAL_GOVERNMENT",
                        evidence={
                            "basis": (
                                "Source establishment name contains a municipal token; "
                                "the page does not formally state ownership."
                            )
                        },
                    )
                )
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=lto,
                    row_reference=row.row_reference,
                    display_name=company,
                    facility_type="agricultural_facility",
                    facility_subtype=subtype,
                    facility_kind="facility",
                    inclusion_class=inclusion_class,
                    ownership="government" if local_government else "private",
                    ownership_type=ownership_type,
                    operator_type=ownership_type,
                    public_access_class="UNKNOWN",
                    access_conditions=(
                        "Licensed meat establishment. NARIS does not state public access, "
                        "walk-in service, ownership or current operating status. The LTO "
                        "number is registry evidence, not proof of current operation."
                    ),
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=latitude if has_coordinates else None,
                        longitude=longitude if has_coordinates else None,
                        precision="geocoded" if has_coordinates else "unknown",
                        method=("naris_cached_address_geocode" if has_coordinates else None),
                        address_text=address,
                        review_status=(
                            "source_cached_geocode" if has_coordinates else "source_supplied"
                        ),
                    ),
                    functions=functions,
                    services=[
                        ServiceData(
                            service_code=subtype,
                            service_name=type_label,
                            source_field="establishment_type",
                            details={
                                "lto_number": lto,
                                "address_variants": payload.get("address_variants", []),
                            },
                        )
                    ],
                    roles=roles,
                )
            )
        return candidates
