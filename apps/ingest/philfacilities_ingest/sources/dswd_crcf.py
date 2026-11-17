"""DSWD Centers and Residential Care Facilities (CRCF) directory parser.

The public DSWD CRCF page is a WordPress/Elementor directory. It renders the same
facility cards twice: one block layout for desktop and one for mobile. Each card
contains the facility name, the responsible DSWD Field Office and a postal
address. The page states that DSWD operates 77 CRCFs; the rendered page contains
76 unique facility cards after exact desktop/mobile deduplication. The one-card
difference is retained as a source warning rather than filled in.

This adapter publishes institutional facility identity only. It does not infer
coordinates, walk-in access, admission rules or operational status from directory
presence. The source is a government work; attribution is retained.
"""

from __future__ import annotations

import html as html_module
import re
from typing import Any

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

SOURCE_URL = "https://www.dswd.gov.ph/crcf/"
SOURCE_COLUMNS = (
    "Region",
    "Facility Name",
    "Field Office",
    "Address",
    "Detail URL",
)

_DETAILS_RE = re.compile(r"<details\b[^>]*>(.*?)</details>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(
    r'class=["\'][^"\']*e-n-accordion-item-title-text[^"\']*["\'][^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_FIGURE_RE = re.compile(r"<figure\b[^>]*>(.*?)</figure>", re.IGNORECASE | re.DOTALL)
_CAPTION_RE = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption>", re.IGNORECASE | re.DOTALL)
_H6_RE = re.compile(r"<h6\b[^>]*>(.*?)</h6>", re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_CLAIM_RE = re.compile(r"\b(\d+)\s+CRCF\b", re.IGNORECASE)


def _text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html_module.unescape(_TAG_RE.sub(" ", value))).strip()


def _h6_parts(value: str) -> tuple[str | None, str | None]:
    """Split an Elementor h6 into field office and address without inventing text."""

    strong = re.search(r"<strong\b[^>]*>(.*?)</strong>", value, re.IGNORECASE | re.DOTALL)
    field_office = _text(strong.group(1)) if strong else None
    tail = value[strong.end() :] if strong else value
    tail = re.sub(r"<br\s*/?>", ", ", tail, flags=re.IGNORECASE)
    address = re.sub(r"^[\s,;:\u2013-]+", "", _text(tail))
    if not field_office:
        lines = [clean_text(_text(line)) or "" for line in re.split(r"<br\s*/?>", value)]
        lines = [line for line in lines if line]
        if len(lines) > 1:
            field_office, address = lines[0], ", ".join(lines[1:])
        elif lines:
            address = lines[0]
    return field_office or None, address or None


def _page_claim(html: str) -> int | None:
    match = _CLAIM_RE.search(_text(html))
    return int(match.group(1)) if match else None


def parse_crcf_html(html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse unique CRCF cards and retain desktop/mobile duplicate evidence."""

    claim = _page_claim(html)
    raw_cards = 0
    unique: dict[str, dict[str, Any]] = {}
    duplicate_variants = 0
    accordion_blocks = 0

    for block_index, block_match in enumerate(_DETAILS_RE.finditer(html), start=1):
        block = block_match.group(1)
        title_match = _TITLE_RE.search(block)
        region = _text(title_match.group(1)) if title_match else None
        figures = list(_FIGURE_RE.finditer(block))
        if not figures:
            continue
        accordion_blocks += 1
        for figure_index, figure_match in enumerate(figures):
            figure = figure_match.group(1)
            caption = _CAPTION_RE.search(figure)
            name = _text(caption.group(1)) if caption else ""
            if not name:
                continue
            raw_cards += 1
            next_start = (
                figures[figure_index + 1].start() if figure_index + 1 < len(figures) else len(block)
            )
            h6 = _H6_RE.search(block[figure_match.end() : next_start])
            field_office, address = _h6_parts(h6.group(1)) if h6 else (None, None)
            href = _HREF_RE.search(figure)
            detail_url = html_module.unescape(href.group(1)).strip() if href else None
            key_base = normalise_code(f"{name}:{address or ''}")
            record = {
                "region": region,
                "facility_name": name,
                "field_office": field_office,
                "address": address,
                "detail_url": detail_url,
                "accordion_block": block_index,
                "card_index": figure_index + 1,
            }
            existing = unique.get(key_base)
            if existing is None:
                record["variant_count"] = 1
                unique[key_base] = record
            else:
                duplicate_variants += 1
                existing["variant_count"] += 1

    records = list(unique.values())
    metadata = {
        "page_claim": claim,
        "accordion_blocks": accordion_blocks,
        "raw_cards": raw_cards,
        "unique_cards": len(records),
        "duplicate_variants": duplicate_variants,
    }
    return records, metadata


class DswdCrcfDirectoryAdapter:
    source_code = "dswd"
    parser_version = "dswd-crcf-html-1.0.0"
    schema_version = "dswd-crcf-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records, metadata = parse_crcf_html(spec.content.decode("utf-8", errors="replace"))
        if not records:
            raise ValueError(
                "DSWD CRCF page contained no facility cards; the page structure changed."
            )
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            payload = {**record, "_row": index}
            rows.append(
                ParsedRow(
                    source_record_key=normalise_code(
                        f"{record['facility_name']}:{record['address'] or ''}"
                    )[:180],
                    row_reference=f"html:unique_card:{index}",
                    raw_payload=payload,
                    normalized_payload=payload,
                )
            )
        warnings: list[dict[str, Any]] = [
            {
                "code": "desktop_mobile_duplicate_cards",
                "message": (
                    "The Elementor page renders desktop and mobile accordion layouts. "
                    f"{metadata['raw_cards']} raw cards collapsed to "
                    f"{metadata['unique_cards']} unique facility cards by exact "
                    "facility-name/address matching."
                ),
                "metadata": metadata,
            },
            {
                "code": "no_coordinates",
                "message": (
                    "The directory supplies postal addresses only; no coordinates, PSGC "
                    "codes, walk-in access rules or operational status were inferred."
                ),
            },
        ]
        if metadata["page_claim"] and metadata["page_claim"] != metadata["unique_cards"]:
            warnings.append(
                {
                    "code": "source_count_discrepancy",
                    "message": (
                        f"The page states {metadata['page_claim']} CRCFs but exposes "
                        f"{metadata['unique_cards']} unique facility cards. The missing "
                        "record was not invented."
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
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("facility_name"))
            address = clean_text(payload.get("address"))
            region = clean_text(payload.get("region"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "A DSWD CRCF card has no facility name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not address:
                issues.append(
                    ValidationIssue(
                        "missing_address",
                        "warning",
                        f"CRCF {name} has no parsed postal address.",
                        row_reference=row.row_reference,
                    )
                )
            if not region:
                issues.append(
                    ValidationIssue(
                        "missing_region",
                        "warning",
                        f"CRCF {name} has no region heading.",
                        row_reference=row.row_reference,
                    )
                )
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_facility_card",
                        "error",
                        f"CRCF {name} appears more than once after deduplication.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
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
            name = clean_text(payload.get("facility_name"))
            if not name:
                continue
            address = clean_text(payload.get("address"))
            field_office = clean_text(payload.get("field_office"))
            region = clean_text(payload.get("region"))
            detail_url = clean_text(payload.get("detail_url"))
            evidence = {
                "source_page": SOURCE_URL,
                "region_heading": region,
                "field_office": field_office,
                "address": address,
                "detail_url": detail_url,
                "desktop_mobile_variants": payload.get("variant_count", 1),
            }
            location_text = ", ".join(part for part in (address, field_office, region) if part)
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="social_welfare_facility",
                    facility_subtype="CRCF",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    access_conditions=(
                        "DSWD-operated centre/residential care facility. The directory "
                        "does not state walk-in access, admission rules or current "
                        "operating status."
                    ),
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=location_text or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="SOCIAL_WELFARE",
                            source_value="Center and Residential Care Facility (CRCF)",
                            evidence=evidence,
                        )
                    ],
                    services=[
                        ServiceData(
                            service_code="SOCIAL_WELFARE_SERVICES",
                            service_name="Center-based and residential social welfare services",
                            source_field="DSWD CRCF directory",
                            details={"region": region, "field_office": field_office},
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OWNER",
                            entity_name="Department of Social Welfare and Development",
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "DSWD CRCF directory"},
                        ),
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Department of Social Welfare and Development",
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "DSWD CRCF directory"},
                        ),
                        RoleData(
                            role_type="MANAGER",
                            entity_name=field_office or "DSWD Field Office",
                            entity_type="NATIONAL_GOVERNMENT",
                            evidence={"basis": "Field Office named in the directory card"},
                        ),
                    ],
                )
            )
        return candidates
