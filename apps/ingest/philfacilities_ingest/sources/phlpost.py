"""PHLPost post-office locator parser (internal-only pending rights review).

The public locator exposes a single HTML table with the source columns
``Provinces``, ``Post Offices``, ``Addresss`` (sic) and ``Services``. Some offices
are counters hosted in municipal halls, malls or terminals. This adapter keeps the
service point as a facility unit and preserves the address text; it does not treat
the host building as government-owned or create a second mall record.

PHLPost is a government-owned and controlled corporation. Its site carries an
explicit copyright/all-rights-reserved notice, so this dataset is stored for
research and relationship work but is requested as internal-only. No record may
be published until a documented reuse decision exists.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

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

SOURCE_COLUMNS = ("Provinces", "Post Offices", "Addresss", "Services")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, _attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = []
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(clean_text(" ".join(self._cell)) or "")
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            if self._depth == 1 and self._table is not None:
                self.tables.append(self._table)
                self._table = None
            self._depth -= 1


def parse_locator_html(html: str) -> tuple[list[str], list[dict[str, str]]]:
    parser = _TableParser()
    parser.feed(html)
    for table in parser.tables:
        if not table:
            continue
        header = [re.sub(r"\s+", " ", cell).strip() for cell in table[0]]
        if header[:4] != list(SOURCE_COLUMNS):
            continue
        rows = []
        for index, cells in enumerate(table[1:], start=2):
            if len(cells) < 4:
                continue
            row = {
                column: re.sub(r"\s+", " ", cells[position]).strip()
                for position, column in enumerate(SOURCE_COLUMNS)
            }
            row["_row"] = str(index)
            rows.append(row)
        return header, rows
    raise ValueError(
        "PHLPost locator did not contain the expected Provinces/Post Offices/Addresss/"
        "Services table; the page structure changed."
    )


def _service_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,/]|(?:\s+and\s+)", value or "") if item.strip()]


class PhlPostLocatorAdapter:
    source_code = "phlpost"
    parser_version = "phlpost-locator-1.0.0"
    schema_version = "phlpost-locator-html-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        _header, rows = parse_locator_html(spec.content.decode("utf-8", errors="replace"))
        if not rows:
            raise ValueError("PHLPost locator contained no post-office rows.")
        parsed: list[ParsedRow] = []
        seen: dict[str, int] = {}
        for row in rows:
            name = clean_text(row.get("Post Offices"))
            province = clean_text(row.get("Provinces"))
            address = clean_text(row.get("Addresss"))
            key_base = normalise_code(f"{province}:{name}:{address}")
            occurrence = seen.get(key_base, 0) + 1
            seen[key_base] = occurrence
            parsed.append(
                ParsedRow(
                    source_record_key=f"{key_base}:{occurrence}" if occurrence > 1 else key_base,
                    row_reference=f"html_row:{row['_row']}",
                    raw_payload=row,
                    normalized_payload=row,
                )
            )
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "internal_only_rights",
                    "message": (
                        "PHLPost's site carries an explicit copyright notice. This release is "
                        "internal-only and must not be published without a documented reuse "
                        "decision."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The locator supplies postal addresses only; no coordinates or PSGC "
                        "codes were invented."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        rejected = 0
        for row in parsed.rows:
            name = clean_text(row.normalized_payload.get("Post Offices"))
            province = clean_text(row.normalized_payload.get("Provinces"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_post_office_name",
                        "fatal",
                        "A post-office row has no office name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
            elif not province:
                issues.append(
                    ValidationIssue(
                        "missing_province",
                        "warning",
                        "A post-office row has no province value.",
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
            name = clean_text(payload.get("Post Offices"))
            if not name:
                continue
            province = clean_text(payload.get("Provinces"))
            address = clean_text(payload.get("Addresss"))
            services = _service_values(clean_text(payload.get("Services")) or "")
            host = _host_from_address(address)
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="government_office",
                    facility_subtype="POST_OFFICE",
                    facility_kind="facility_unit" if host else "facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOCC",
                    operator_type="GOCC",
                    public_access_class="UNKNOWN",
                    record_status="unknown",
                    location=LocationData(
                        address_text=", ".join(part for part in (address, province) if part)
                        or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="POSTAL_SERVICE",
                            source_value=clean_text(payload.get("Services")),
                            evidence={
                                "province": province,
                                "address": address,
                                "services": clean_text(payload.get("Services")),
                            },
                        )
                    ],
                    services=[
                        ServiceData(
                            service_code="POSTAL_SERVICE",
                            service_name=service,
                            source_field="Services",
                            details={"raw_value": service},
                        )
                        for service in services
                    ],
                    roles=[
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Philippine Postal Corporation (PHLPost)",
                            entity_type="GOCC",
                            evidence={"basis": "publisher and named operator of the locator"},
                        )
                    ]
                    + (
                        [
                            RoleData(
                                role_type="HOST",
                                entity_name=host,
                                entity_type="unknown",
                                evidence={"basis": "address text names the host premises"},
                            )
                        ]
                        if host
                        else []
                    ),
                )
            )
        return candidates


_HOST_RE = re.compile(
    r"^(?P<host>[^,]{3,80}?(?:Hall|Mall|Terminal|Building|Bldg\.?|Complex|Center|Centre|"
    r"Plaza|Market|Station))(?:\s*(?:Bldg\.?|Building))?\s*,",
    re.IGNORECASE,
)


def _host_from_address(address: str | None) -> str | None:
    if not address:
        return None
    match = _HOST_RE.match(address)
    if not match:
        return None
    host = clean_text(match.group("host"))
    return host or None
