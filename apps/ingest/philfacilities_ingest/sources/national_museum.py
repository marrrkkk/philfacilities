"""National Museum of the Philippines regional/area/site museum directory.

The official public page lists the NMP-run museums outside Metro Manila and links
each museum's own page. The detail pages supply a postal address and, for some
sites, contact details. The source is a government work (RA 8293 section 176);
PhilFacilities publishes the institutional site fields with attribution.

The acquisition step stores one JSON artifact containing the directory entry and
the fields read from each official detail page. That artifact is the preserved
source release, so a later page redesign cannot silently change an old release.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

from ..acquisition import AcquisitionError, HttpAcquirer
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

DIRECTORY_URL = "https://www.nationalmuseum.gov.ph/our-museums/regional-area-and-site-museums/"
BASE_URL = "https://www.nationalmuseum.gov.ph"

_CARD_RE = re.compile(
    r'<a class="uk-card[^"]*"[^>]*href="([^"]+)"(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_META_RE = re.compile(r'<div class="el-meta[^"]*"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", value))).strip()


def parse_directory_html(html: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, body in _CARD_RE.findall(html):
        meta = _META_RE.search(body)
        if meta is None:
            continue
        name = _text(meta.group(1))
        if not name:
            continue
        url = urljoin(BASE_URL, unescape(href))
        if url in seen:
            continue
        seen.add(url)
        records.append({"name": name, "url": url})
    return records


def _page_text(html: str) -> list[str]:
    without_scripts = re.sub(r"<script.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(
        r"<style.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL
    )
    text = unescape(_TAG_RE.sub("\n", without_styles))
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def parse_detail_html(html: str) -> dict[str, str | None]:
    lines = _page_text(html)
    values: dict[str, str | None] = {"address": None, "telephone": None, "email": None}
    for line in lines:
        lowered = line.lower()
        for key in values:
            if values[key] is not None:
                continue
            if lowered.startswith(f"{key}:"):
                value = clean_text(line.split(":", 1)[1])
                if value:
                    values[key] = value
    return values


def build_artifact(records: list[dict[str, Any]], retrieved_at: datetime | None = None) -> bytes:
    payload = {
        "directory_url": DIRECTORY_URL,
        "retrieved_at": (retrieved_at or datetime.now(UTC)).isoformat(),
        "note": (
            "Acquisition artifact built from the official NMP directory and linked detail "
            "pages. Fields are copied from the official pages; no coordinates were added."
        ),
        "records": records,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def fetch_national_museum_directory(
    acquirer: HttpAcquirer,
) -> tuple[bytes, dict[str, Any]]:
    result = acquirer.fetch(DIRECTORY_URL)
    if result.status_code >= 400:
        raise AcquisitionError(
            f"National Museum directory returned HTTP {result.status_code}.", result=result
        )
    entries = parse_directory_html(result.content.decode("utf-8", errors="replace"))
    if not entries:
        raise AcquisitionError(
            "National Museum directory contained no museum cards.", result=result
        )
    records: list[dict[str, Any]] = []
    for entry in entries:
        detail = acquirer.fetch(entry["url"])
        if detail.status_code >= 400:
            records.append({**entry, "detail_status": detail.status_code})
            continue
        fields = parse_detail_html(detail.content.decode("utf-8", errors="replace"))
        records.append({**entry, "detail_status": detail.status_code, **fields})
    metadata = {
        "directory_url": DIRECTORY_URL,
        "directory_status": result.status_code,
        "museums": len(records),
        "detail_pages_fetched": sum(1 for record in records if record.get("detail_status") == 200),
    }
    return build_artifact(records), metadata


class NationalMuseumDirectoryAdapter:
    source_code = "national-museum"
    parser_version = "national-museum-1.0.0"
    schema_version = "national-museum-json-v1"
    expected_columns = {"required": {"name", "url"}}  # noqa: RUF012

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
            raise ValueError("National Museum release is not a JSON acquisition artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("National Museum artifact contains no records.")
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            name = clean_text(record.get("name"))
            url = clean_text(record.get("url"))
            if not name or not url:
                continue
            slug = urlparse(url).path.strip("/").rsplit("/", 1)[-1] or f"museum-{index}"
            rows.append(
                ParsedRow(
                    source_record_key=slug,
                    row_reference=f"nmp-directory:{index}",
                    raw_payload=record,
                    normalized_payload=record,
                )
            )
        if not rows:
            raise ValueError("National Museum artifact contained no usable museum records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "no_coordinates",
                    "message": (
                        "NMP detail pages supply postal addresses, not coordinates or PSGC "
                        "codes. Museums remain unmapped unless an authorized geocoder is used."
                    ),
                }
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            name = clean_text(row.normalized_payload.get("name"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_museum_name",
                        "fatal",
                        "A museum record has no name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
            elif key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_museum_key",
                        "error",
                        f"Museum key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
            else:
                seen.add(key)
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            record = row.normalized_payload
            name = clean_text(record.get("name"))
            if not name:
                continue
            address = clean_text(record.get("address"))
            website = clean_text(record.get("url"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="museum",
                    facility_subtype="OTHER_MUSEUM",
                    facility_kind="site",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="NATIONAL_GOVERNMENT",
                    operator_type="NATIONAL_GOVERNMENT",
                    public_access_class="UNKNOWN",
                    access_conditions=None,
                    record_status="active_in_registry",
                    location=LocationData(address_text=address, precision="unknown"),
                    functions=[
                        FunctionData(
                            function_code="MUSEUM",
                            source_value="Regional, area and site museum",
                            evidence={
                                "directory_url": DIRECTORY_URL,
                                "museum_url": website,
                                "address": address,
                                "telephone": record.get("telephone"),
                                "email": record.get("email"),
                            },
                        )
                    ],
                )
            )
        return candidates
