"""Commission on Higher Education HEIDA public HEI directory adapter.

The HEIDA ``/hei-directory`` pages are public, server-rendered directories of
higher-education institutions by CHED regional office. Each region page supplies
the institution name, CHED code (some entries say ``NEW`` or ``NO UII``), the
institutional type, a postal address and (when published) contact details and the
institutional head.

The adapter intentionally discards contact details and institutional-head fields:
they can contain personal names, email addresses and phone numbers and are not
needed for the facility registry. Only institutional name, source code, type,
address and region are retained.

The directory type is the only ownership evidence used here:

* ``Chartered State College/University`` -> public educational institution;
* ``Local Government College/University`` -> local-government institution;
* ``Private ...`` -> private public-service provider;
* ``Others`` or an unrecognised type -> internal discovery candidate.

A directory listing is not proof that an institution is currently operating, and
no coordinates, PSGC codes, campus count or public-access conditions are inferred.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

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
from .common import clean_text, normalise_code

DIRECTORY_URL = "https://heida.ched.gov.ph/hei-directory"
REGION_URL = "https://heida.ched.gov.ph/hei-directory/{region_id}"
PUBLIC_FIELDS = ("region_id", "region", "name", "code", "type", "address", "source_page")
TYPE_NAMES = (
    "Chartered State College/University (Main)",
    "Chartered State College/University (Satellite Campus)",
    "Local Government College/University",
    "Others, please specify",
    "Private Non-Sectarian Foundation",
    "Private Non-Sectarian Non-Stock",
    "Private Non-Sectarian Stock",
    "Private Non-Stock Non-Profit Corporation",
    "Private Sectarian Foundation",
    "Private Sectarian Non-Stock",
    "Private Sectarian Stock",
    "CHED-Supervised Institution",
)
OWNERSHIP_UNKNOWN_TYPES = {"Others, please specify", "CHED-Supervised Institution"}
_REGION_LINK = re.compile(
    r'href="https://heida\.ched\.gov\.ph/hei-directory/(?P<id>\d+)"[^>]*>'
    r".*?<h3[^>]*>(?P<name>.*?)</h3>",
    re.DOTALL,
)
_TOTAL = re.compile(r"(?P<count>[\d,]+)\s+Records?\s+Found", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value) or "").strip()


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return text or "UNNAMED"


def parse_region_links(html: str) -> list[dict[str, str]]:
    """Return the region IDs and labels advertised by the HEI directory page."""

    regions: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _REGION_LINK.finditer(html):
        region_id = match.group("id")
        name = _text(_TAG.sub(" ", match.group("name")))
        if not region_id or not name or region_id in seen:
            continue
        seen.add(region_id)
        regions.append({"id": region_id, "name": name})
    return regions


def parse_records_found(html: str) -> int | None:
    match = _TOTAL.search(_TAG.sub(" ", html))
    if not match:
        return None
    try:
        return int(match.group("count").replace(",", ""))
    except ValueError:
        return None


class _HeiTableParser(HTMLParser):
    """Extract only the institution table cells and typed spans from a region page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self._cell: list[str] | None = None
        self._span_class: str | None = None
        self._span_text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = {"cells": [], "spans": []}
        elif tag == "td" and self._row is not None:
            self._cell = []
            self._row["cells"].append(self._cell)
        elif tag == "span" and self._cell is not None and self._row is not None:
            self._span_class = dict(attrs).get("class") or ""
            self._span_text = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._span_text is not None:
            self._span_text.append(data)
        elif self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "span" and self._span_text is not None and self._row is not None:
            value = _text(" ".join(self._span_text))
            if value:
                self._row["spans"].append((self._span_class or "", value))
                if self._cell is not None:
                    self._cell.append(value)
            self._span_text = None
            self._span_class = None
        elif tag == "td":
            self._cell = None
        elif tag == "tr" and self._row is not None:
            cells = [_text(" ".join(cell)) for cell in self._row["cells"]]
            if len(cells) >= 5 and cells[0]:
                self._row["cells"] = cells
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def parse_hei_rows(html: str) -> list[dict[str, str | None]]:
    """Parse institution rows from one HEIDA region result page."""

    parser = _HeiTableParser()
    parser.feed(html)
    records: list[dict[str, str | None]] = []
    for parsed in parser.rows:
        cells: list[str] = parsed["cells"]
        name = ""
        code = ""
        hei_type = ""
        for span_class, value in parsed["spans"]:
            classes = span_class.split()
            if "font-bold" in classes and not name:
                name = value
            elif "font-mono" in classes and not code:
                code = value
            elif "uppercase" in classes and not hei_type:
                hei_type = value
        # Fall back to the cell text if the markup changes. The first cell has
        # the name followed by the code; the last token is the code only when it
        # is a short identifier.
        if not name:
            name = cells[0]
            if not code:
                parts = cells[0].rsplit(" ", 1)
                if len(parts) == 2 and len(parts[1]) <= 20:
                    name, code = parts
        address = cells[3] if len(cells) > 3 else ""
        if not name:
            continue
        records.append(
            {
                "name": name,
                "code": code or None,
                "type": hei_type or None,
                "address": address or None,
            }
        )
    return records


def fetch_heida_directory(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch every HEIDA region page and build a public institution-field artifact."""

    directory_result = acquirer.fetch(DIRECTORY_URL)
    if directory_result.status_code >= 400:
        raise AcquisitionError(
            f"CHED HEIDA directory returned HTTP {directory_result.status_code}.",
            result=directory_result,
        )
    directory_html = directory_result.content.decode("utf-8", errors="replace")
    regions = parse_region_links(directory_html)
    if not regions:
        raise AcquisitionError(
            "CHED HEIDA directory did not expose any region links; layout changed.",
            result=directory_result,
        )

    records: list[dict[str, Any]] = []
    region_summaries: list[dict[str, Any]] = []
    pages_fetched = 0
    for region in regions:
        base_url = REGION_URL.format(region_id=region["id"])
        first = acquirer.fetch(base_url)
        if first.status_code >= 400:
            raise AcquisitionError(
                f"CHED HEIDA region {region['name']} returned HTTP {first.status_code}.",
                result=first,
            )
        first_html = first.content.decode("utf-8", errors="replace")
        total = parse_records_found(first_html)
        first_rows = parse_hei_rows(first_html)
        pages_fetched += 1
        if total is None:
            raise AcquisitionError(
                f"CHED HEIDA region {region['name']} did not state a result count.",
                result=first,
            )
        if total == 0:
            region_summaries.append({**region, "records_found": 0, "pages_fetched": 1})
            continue
        if not first_rows:
            raise AcquisitionError(
                f"CHED HEIDA region {region['name']} stated {total} records but no rows "
                "could be parsed; layout changed.",
                result=first,
            )
        page_size = len(first_rows)
        pages = max(1, math.ceil(total / page_size))
        if pages > 100:
            raise AcquisitionError(
                f"CHED HEIDA region {region['name']} reported {total} records across "
                f"{pages} pages, above the connector safety limit.",
                result=first,
            )
        all_rows: list[dict[str, str | None]] = list(first_rows)
        for page in range(2, pages + 1):
            result = acquirer.fetch(f"{base_url}?page={page}")
            if result.status_code >= 400:
                raise AcquisitionError(
                    f"CHED HEIDA region {region['name']} page {page} returned HTTP "
                    f"{result.status_code}.",
                    result=result,
                )
            page_rows = parse_hei_rows(result.content.decode("utf-8", errors="replace"))
            if not page_rows:
                raise AcquisitionError(
                    f"CHED HEIDA region {region['name']} page {page} returned no rows.",
                    result=result,
                )
            all_rows.extend(page_rows)
            pages_fetched += 1
            time.sleep(0.15)
        if len(all_rows) != total:
            raise AcquisitionError(
                f"CHED HEIDA region {region['name']} stated {total} records but "
                f"{len(all_rows)} rows were parsed; no release was accepted."
            )
        for index, row in enumerate(all_rows, start=1):
            records.append(
                {
                    "region_id": region["id"],
                    "region": region["name"],
                    "name": row["name"],
                    "code": row["code"],
                    "type": row["type"],
                    "address": row["address"],
                    "source_page": f"{base_url}?page={math.ceil(index / page_size)}",
                    "source_row": index,
                }
            )
        region_summaries.append({**region, "records_found": total, "pages_fetched": pages})
        time.sleep(0.15)

    if not records:
        raise AcquisitionError("CHED HEIDA directory returned no institution records.")

    artifact = {
        "directory_url": DIRECTORY_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "regions": region_summaries,
        "pages_fetched": pages_fetched,
        "record_count": len(records),
        "note": (
            "Public CHED HEIDA HEI directory artifact. Only institutional name, CHED "
            "code, type, address and region are retained. Contact details and "
            "institutional-head names were discarded during acquisition. No coordinates "
            "or PSGC codes are present."
        ),
        "records": records,
    }
    metadata = {
        "regions": len(region_summaries),
        "pages_fetched": pages_fetched,
        "records": len(records),
        "directory_url": DIRECTORY_URL,
    }
    return json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8"), metadata


def _ownership(hei_type: str | None) -> tuple[str, str, str, str]:
    """Return legacy ownership, ownership type, inclusion class and operator type."""

    value = _text(hei_type)
    lowered = value.lower()
    if "chartered state college/university" in lowered:
        return (
            "government",
            "PUBLIC_EDUCATIONAL_INSTITUTION",
            "GOVERNMENT_FACILITY",
            "PUBLIC_EDUCATIONAL_INSTITUTION",
        )
    if "local government college/university" in lowered:
        return "government", "LOCAL_GOVERNMENT", "GOVERNMENT_FACILITY", "LOCAL_GOVERNMENT"
    if lowered.startswith("private"):
        if "non-sectarian" in lowered:
            if "stock" in lowered and "non-stock" not in lowered:
                ownership_type = "PRIVATE_CORPORATE"
            else:
                ownership_type = "NGO_NON_PROFIT"
        elif "sectarian" in lowered:
            ownership_type = "RELIGIOUS_FAITH_BASED"
        elif "non-stock" in lowered or "non-profit" in lowered or "foundation" in lowered:
            ownership_type = "NGO_NON_PROFIT"
        else:
            ownership_type = "PRIVATE_CORPORATE"
        return (
            "private",
            ownership_type,
            "PRIVATE_PUBLIC_SERVICE_PROVIDER",
            ownership_type,
        )
    return "unknown", "UNKNOWN", "DISCOVERY_CANDIDATE", "UNKNOWN"


class ChedHeidaAdapter:
    source_code = "ched-heida"
    parser_version = "ched-heida-html-1.0.0"
    schema_version = "ched-heida-directory-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content)
        except json.JSONDecodeError as exc:
            raise ValueError("CHED HEIDA release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("CHED HEIDA artifact contains no records.")
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            name = _text(record.get("name"))
            region_id = _text(record.get("region_id")) or "unknown"
            code = normalise_code(record.get("code")) or ""
            name_part = _slug(name) if name else f"ROW-{index}"
            fingerprint = hashlib.sha1(
                f"{_text(record.get('type'))}|{_text(record.get('address'))}".encode()
            ).hexdigest()[:8]
            # CHED codes are not unique in the published directory: the same code
            # can appear under different institutions, and some entries are marked
            # NEW or have no UII. Region, code, name and a row fingerprint keep
            # distinct published records distinct without merging them.
            key = f"CHED-HEI:{region_id}:{code or 'NOCODE'}:{name_part}:{fingerprint}"
            rows.append(
                ParsedRow(
                    source_record_key=key,
                    row_reference=f"ched-json:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("CHED HEIDA artifact contained no usable institution records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "institutional_fields_only",
                    "message": (
                        "Contact details and institutional-head names were discarded "
                        "during acquisition and are not present in the release."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "HEIDA supplies institution addresses and administrative labels "
                        "only; no coordinates or PSGC codes were invented."
                    ),
                },
                {
                    "code": "ownership_from_institutional_type",
                    "message": (
                        "Ownership is classified only from the published institutional "
                        "type. 'Others' and unrecognised types remain internal discovery "
                        "candidates because the source does not establish ownership."
                    ),
                },
                {
                    "code": "directory_not_operational_status",
                    "message": (
                        "Directory presence is registry evidence, not proof of current "
                        "operation, accreditation, campus count or public access."
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
            name = _text(payload.get("name"))
            key = row.source_record_key
            hei_type = _text(payload.get("type"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_institution_name",
                        "fatal",
                        "A CHED HEIDA row has no institution name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_institution_key",
                        "error",
                        f"HEI key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if not hei_type:
                issues.append(
                    ValidationIssue(
                        "missing_institution_type",
                        "warning",
                        f"HEI {name} has no institutional type; ownership remains unknown.",
                        row_reference=row.row_reference,
                    )
                )
            elif hei_type in OWNERSHIP_UNKNOWN_TYPES:
                issues.append(
                    ValidationIssue(
                        "ownership_not_established",
                        "warning",
                        f"HEI {name} has institutional type {hei_type!r}, which does not "
                        "establish ownership; it remains an internal discovery candidate.",
                        {"institution_type": hei_type},
                        row.row_reference,
                    )
                )
            elif hei_type not in TYPE_NAMES:
                issues.append(
                    ValidationIssue(
                        "unclassified_institution_type",
                        "warning",
                        f"HEI {name} has institutional type {hei_type!r}; it remains an "
                        "internal discovery candidate.",
                        {"institution_type": hei_type},
                        row.row_reference,
                    )
                )
            if not _text(payload.get("address")):
                issues.append(
                    ValidationIssue(
                        "missing_address",
                        "warning",
                        f"HEI {name} has no postal address.",
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
            name = _text(payload.get("name"))
            if not name:
                continue
            hei_type = _text(payload.get("type")) or None
            region = _text(payload.get("region"))
            address = _text(payload.get("address"))
            code = normalise_code(payload.get("code"))
            ownership, ownership_type, inclusion_class, operator_type = _ownership(hei_type)
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="school",
                    facility_subtype="HIGHER_EDUCATION_INSTITUTION",
                    facility_kind="facility",
                    inclusion_class=inclusion_class,
                    ownership=ownership,
                    ownership_type=ownership_type,
                    operator_type=operator_type,
                    public_access_class="UNKNOWN",
                    access_conditions=None,
                    record_status="active_in_registry",
                    location=LocationData(
                        address_text=address or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="EDUCATION",
                            source_value=hei_type,
                            designation_status="unknown",
                            evidence={
                                "source": "CHED HEIDA HEI directory",
                                "source_id": row.source_record_key,
                                "region": region,
                                "region_id": payload.get("region_id"),
                                "institution_code": code or None,
                                "institution_type": hei_type,
                                "address": address,
                                "source_page": payload.get("source_page"),
                            },
                        )
                    ],
                )
            )
        return candidates
