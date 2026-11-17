"""Bureau of Corrections (BuCor) operating prison facilities.

The official BuCor "OPPF" page publishes a short, centre-aligned list of the
seven operating prison and penal facilities with links to one page per facility.
It is a directory subset, not a national corrections register: the page does not
state addresses, coordinates, capacity, population, opening dates or current
operating status, and it does not include every jail or detention facility in
the country (BJMP and provincial jails are separate custodians).

The adapter exposes only the facility name and its official detail-page URL.
The detail pages are retained as acquisition evidence but are not parsed for
personal names, contact details or security-sensitive information.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin

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

OPPF_URL = "https://bucor.gov.ph/?page_id=303"
FACILITY_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*\?page_id=(?P<page_id>\d+))"[^>]*>(?P<label>.*?)</a>',
    re.S | re.I,
)
TAG_RE = re.compile(r"<[^>]+>")
PAGE_TITLE_RE = re.compile(r'<h1[^>]*class="[^"]*page-title[^"]*"[^>]*>.*?</h1>', re.S | re.I)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def parse_facility_links(document: str) -> list[dict[str, Any]]:
    """Return the facility links embedded in the OPPF page content."""

    title = PAGE_TITLE_RE.search(document)
    start = title.end() if title else 0
    end = document.lower().find("contact us", start)
    if end == -1:
        end = len(document)
    segment = document[start:end]
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in FACILITY_LINK_RE.finditer(segment):
        name = _clean(match.group("label"))
        page_id = match.group("page_id")
        if not name or page_id in seen:
            continue
        seen.add(page_id)
        records.append(
            {
                "facility_name": name,
                "source_page_id": page_id,
                "detail_url": urljoin(OPPF_URL, html.unescape(match.group("href"))),
            }
        )
    return records


class BucorFacilityAdapter:
    source_code = "bucor"
    parser_version = "bucor-oppf-html-1.0.0"
    schema_version = "bucor-oppf-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = parse_facility_links(spec.content.decode("utf-8", "replace"))
        if not records:
            raise ValueError("BuCor OPPF page contained no facility links.")
        rows = [
            ParsedRow(
                source_record_key=f"BUCOR:OPPF:{record['source_page_id']}",
                row_reference=f"bucor-oppf:{record['source_page_id']}",
                raw_payload=record,
                normalized_payload=record,
            )
            for record in records
        ]
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "directory_subset_not_national_register",
                    "message": (
                        "The OPPF page lists seven BuCor operating prison and penal "
                        "facilities. It is not a complete national corrections register "
                        "and omits BJMP, provincial and sub-provincial jails."
                    ),
                },
                {
                    "code": "no_location_fields",
                    "message": (
                        "The page supplies no address, coordinate, capacity or operating "
                        "status. Those values remain unknown and are not inferred."
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
            name = clean_text(payload.get("facility_name"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "BuCor OPPF row has no facility name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_facility",
                        "error",
                        f"BuCor facility {row.source_record_key} appears more than once.",
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
            name = clean_text(payload.get("facility_name"))
            if not name:
                continue
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="justice_facility",
                    facility_subtype="JAIL",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="RESTRICTED",
                    record_status="unknown",
                    location=LocationData(
                        precision="unknown",
                        method=None,
                        address_text=None,
                        psgc_code=None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="CORRECTIONAL_CUSTODY",
                            source_value="BuCor operating prison or penal farm",
                            designation_status="source_listed",
                            evidence={
                                "source": "Bureau of Corrections — OPPF facilities page",
                                "source_page_id": payload.get("source_page_id"),
                                "detail_url": payload.get("detail_url"),
                            },
                        )
                    ],
                )
            )
        return candidates
