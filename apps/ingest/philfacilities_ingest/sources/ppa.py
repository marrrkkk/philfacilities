"""Philippine Ports Authority (PPA) official port-list parser.

The source is PPA's published "List of Ports Covered in PPA Statistics". It is a
22-page PDF with two related sections:

* the statistics list, grouped by PPA region, Port Management Office (PMO),
  base port / Terminal Management Office (TMO) / other government port; and
* a separate list of private ports, grouped by the PMO that covers them.

The adapter preserves the source hierarchy (region, PMO, group, source name,
RORO/NON-RORO marks and remarks). It does not infer coordinates, PSGC codes,
berth capacity, public access or current operational status. A port's presence in
PPA statistics is registry evidence only.

Ownership is also not inferred beyond what the document states. Base ports and
TMO/OTP entries are PPA-managed (PPA is a government-owned and controlled
corporation) and are classified as government facilities. "Other government
ports" are government but the owning agency is not stated, so the ownership type
remains ``GOVERNMENT_UNSPECIFIED``. Private ports are classified as private
public-service providers without naming an owner/operator, because the list does
not state one.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pdfplumber

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

SOURCE_URL = (
    "https://ppa.com.ph/sites/default/files/List%20of%20Ports%20covered%20in%20PPA%20Statistics.pdf"
)
SOURCE_COLUMNS = ("NAME", "RORO", "NON-RORO", "REMARKS")
CHECK_GLYPHS = frozenset({"\uf0fc", "\uf0fe", "\u2713", "\u2714", "\u221a"})

REGION_CODES = {
    "MANILA/NORTHERN LUZON": "MANILA_NORTHERN_LUZON",
    "SOUTHERN LUZON": "SOUTHERN_LUZON",
    "VISAYAS": "VISAYAS",
    "NORTHERN MINDANAO": "NORTHERN_MINDANAO",
    "SOUTHERN MINDANAO": "SOUTHERN_MINDANAO",
}

GROUP_BASEPORT = "BASEPORT"
GROUP_TMO = "TMO_OR_OTP"
GROUP_OTHER_GOVERNMENT = "OTHER_GOVERNMENT_PORT"
GROUP_PRIVATE = "PRIVATE_PORT"

PRIVATE_PORT_HEADING = re.compile(r"^PRIVATE PORTS?$", re.IGNORECASE)
NUMBERED_ROW = re.compile(r"^(?P<number>\d+)[\.\)]\s*(?P<name>.+)$")
REGION_HEADING = re.compile(
    r"^(?P<code>\d\.\d|[IVX]+)\.?\s+(?P<name>"
    + "|".join(re.escape(name) for name in REGION_CODES)
    + r")(?=[_\-\s]|$)",
    re.IGNORECASE,
)
PMO_HEADING = re.compile(
    r"^(?P<letter>[A-Z])\.\s*PORT MANAGEMENT\s+(?:OFFICE\s+)?(?:OF\s+)?"
    r"(?P<body>.+?)(?:\s*\((?:PMO\s*)?(?P<code>[A-Z]{2,6})\))?\s*$",
    re.IGNORECASE,
)
PMO_CODE_IN_TEXT = re.compile(r"\((?:PMO\s*)?(?P<code>[A-Z]{2,6})\)")
OTHER_GOVERNMENT_HEADING = re.compile(r"^OTHER\s+GOVER(?:N)?MENT\s+POR(?:T|ST)S?$", re.IGNORECASE)
TMO_HEADING = re.compile(r"^TMO\s*[-\u2013\u2014]\s*(?P<name>.+)$", re.IGNORECASE)
HEADER_ROW = re.compile(r"^NAME(\s+RORO\s+NON-?RORO\s+REMARKS?)?$", re.IGNORECASE)
PAGE_FOOTER = re.compile(r"^\d+\s*\|\s*P\s*age$", re.IGNORECASE)
UNREGISTERED_NOTE = re.compile(r"^\*?\s*Unregistered Ports?$", re.IGNORECASE)
ANCHORAGE = re.compile(r"\banchorage\b|\bIBW\b|\bOBW\b", re.IGNORECASE)
MICT_HEADING = "MANILA INTERNATIONAL CONTAINER TERMINAL (MICT)"


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value) or "").strip()


def _is_mark(value: Any) -> bool:
    text = _text(value)
    return bool(text) and (text in CHECK_GLYPHS or text.lower() in {"x", "yes", "y"})


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return text or "UNNAMED"


def _region_name(line: str) -> str | None:
    match = REGION_HEADING.match(line.strip())
    if not match:
        return None
    return REGION_CODES.get(_text(match.group("name")).upper())


def _pmo_heading(line: str) -> tuple[str, str] | None:
    match = PMO_HEADING.match(line.strip())
    if not match or "PORT MANAGEMENT" not in line.upper():
        return None
    body = _text(match.group("body"))
    code_match = PMO_CODE_IN_TEXT.search(body) or PMO_CODE_IN_TEXT.search(line)
    code = _text(code_match.group("code")).upper() if code_match else ""
    name = _text(PMO_CODE_IN_TEXT.sub("", body))
    if not code:
        return None
    return code, name


def _heading_events(lines: list[dict[str, Any]]) -> list[tuple[float, str, Any]]:
    """Collapse wrapped PMO headings into ordered, position-aware events."""

    events: list[tuple[float, str, Any]] = []
    index = 0
    while index < len(lines):
        line = _text(lines[index]["text"])
        top = float(lines[index]["top"])
        if not line or PAGE_FOOTER.match(line):
            index += 1
            continue
        region = _region_name(line)
        if region:
            events.append((top, "region", region))
            index += 1
            continue
        if MICT_HEADING in line.upper():
            events.append((top, "mict", line))
            index += 1
            continue
        pmo = _pmo_heading(line)
        if pmo is not None:
            events.append((top, "pmo", pmo))
            index += 1
            continue
        if "PORT MANAGEMENT" in line.upper():
            combined = line
            lookahead = index + 1
            while lookahead < len(lines) and lookahead <= index + 2:
                candidate = _text(lines[lookahead]["text"])
                if PMO_CODE_IN_TEXT.search(candidate):
                    combined = f"{combined} {candidate}"
                    lookahead += 1
                    break
                if candidate.startswith("(") or not NUMBERED_ROW.match(candidate):
                    combined = f"{combined} {candidate}"
                    lookahead += 1
                    continue
                break
            pmo = _pmo_heading(combined)
            if pmo is not None:
                events.append((top, "pmo", pmo))
                index = lookahead
                continue
        index += 1
    return events


def _update_context(
    events: list[tuple[float, str, Any]],
    top: float,
    bottom: float,
    state: dict[str, Any],
) -> None:
    for event_top, kind, value in events:
        if event_top < top or event_top >= bottom:
            continue
        if kind == "region":
            state["region"] = value
            state["pmo_code"] = None
            state["pmo_name"] = None
            state["group"] = None
            state["unregistered_section"] = False
        elif kind == "pmo":
            state["pmo_code"], state["pmo_name"] = value
            state["group"] = None
            state["unregistered_section"] = False
        elif kind == "mict":
            state["mict_heading"] = True


def _record_key(state: dict[str, Any], group: str, name: str, ordinal: int) -> str:
    pmo_code = state.get("pmo_code") or "UNKNOWN"
    base = f"PPA:{pmo_code}:{group}:{_slug(name)}"
    return base if ordinal <= 1 else f"{base}#{ordinal}"


def _classify_group(state: dict[str, Any], group: str | None) -> str:
    if group in {
        GROUP_BASEPORT,
        GROUP_TMO,
        GROUP_OTHER_GOVERNMENT,
        GROUP_PRIVATE,
    }:
        return group
    return GROUP_TMO


def _row_record(
    *,
    state: dict[str, Any],
    group: str,
    ordinal: int,
    name: str,
    number: str,
    roro: bool | None,
    non_roro: bool | None,
    remarks: str | None,
    page: int,
    reference: str,
) -> dict[str, Any]:
    return {
        "region": state.get("region"),
        "pmo_code": state.get("pmo_code"),
        "pmo_name": state.get("pmo_name"),
        "group": group,
        "source_number": number,
        "name": name,
        "roro": roro,
        "non_roro": non_roro,
        "remarks": remarks,
        "unregistered": bool(state.get("unregistered_section")),
        "_ordinal": ordinal,
        "page": page,
        "row_reference": reference,
    }


def parse_port_pdf(content: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract port rows and source hierarchy from the PPA PDF."""

    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    standalone: list[str] = []
    mict_seen = False
    state: dict[str, Any] = {
        "region": None,
        "pmo_code": None,
        "pmo_name": None,
        "group": None,
        "unregistered_section": False,
        "mict_heading": False,
    }
    session_ordinals: dict[tuple[str, str, str], int] = {}

    with pdfplumber.open(io.BytesIO(content)) as document:
        for page_index, page in enumerate(document.pages, start=1):
            lines = page.extract_text_lines()
            events = _heading_events(lines)
            tables = page.find_tables()
            if not tables:
                page_text = "\n".join(_text(line["text"]) for line in lines)
                if (
                    "PRIVATE PORT" not in page_text.upper()
                    and "LIST OF PRIVATE PORTS" not in page_text.upper()
                ):
                    continue
                # Private-port list pages are plain text rather than tables.
                _parse_private_page(
                    lines=lines,
                    events=events,
                    state=state,
                    records=records,
                    counts=counts,
                    session_ordinals=session_ordinals,
                    page_index=page_index,
                )
                continue

            table_bottom = 0.0
            for table in tables:
                _update_context(
                    events,
                    top=table_bottom,
                    bottom=float(table.bbox[1]),
                    state=state,
                )
                if state.get("mict_heading"):
                    mict_seen = True
                    state["mict_heading"] = False
                for cells in table.extract():
                    first = _text(cells[0]) if cells else ""
                    if not first or HEADER_ROW.match(first):
                        continue
                    if first.upper() == GROUP_BASEPORT:
                        state["group"] = GROUP_BASEPORT
                        continue
                    if TMO_HEADING.match(first):
                        state["group"] = GROUP_TMO
                        continue
                    if OTHER_GOVERNMENT_HEADING.match(first):
                        state["group"] = GROUP_OTHER_GOVERNMENT
                        continue
                    if PRIVATE_PORT_HEADING.match(first):
                        state["group"] = GROUP_PRIVATE
                        continue
                    row = NUMBERED_ROW.match(first)
                    if not row:
                        continue
                    group = _classify_group(state, state.get("group"))
                    name = _text(row.group("name"))
                    remarks = _text(cells[3]) if len(cells) > 3 else ""
                    ordinal_key = (state.get("pmo_code") or "", group, _slug(name))
                    session_ordinals[ordinal_key] = session_ordinals.get(ordinal_key, 0) + 1
                    record = _row_record(
                        state=state,
                        group=group,
                        ordinal=session_ordinals[ordinal_key],
                        name=name,
                        number=row.group("number"),
                        roro=True if _is_mark(cells[1]) else None,
                        non_roro=True if _is_mark(cells[2]) else None,
                        remarks=remarks or None,
                        page=page_index,
                        reference=f"pdf:page:{page_index}:row:{row.group('number')}",
                    )
                    records.append(record)
                    counts[group] = counts.get(group, 0) + 1
                table_bottom = float(table.bbox[3])

            # Preserve evidence of main-section entries that sit outside a table.
            if page_index <= 14:
                for line in lines:
                    text = _text(line["text"])
                    top = float(line["top"])
                    if top < table_bottom or top > float(page.height) - 30:
                        continue
                    if MICT_HEADING in text.upper():
                        mict_seen = True
                        continue
                    if NUMBERED_ROW.match(text):
                        standalone.append(text)
    if not records:
        raise ValueError(
            "The PPA port-list PDF produced no port rows; the layout or access state changed."
        )
    if mict_seen:
        warnings.append(
            {
                "code": "standalone_mict_entry_not_ingested",
                "message": (
                    "The PDF contains a separate 'MANILA INTERNATIONAL CONTAINER "
                    "TERMINAL (MICT)' note outside the statistics tables. Its ownership "
                    "and relationship to the listed ports are not stated, so it was not "
                    "ingested or assigned to a PMO."
                ),
            }
        )
    if standalone:
        warnings.append(
            {
                "code": "standalone_numbered_entries_not_ingested",
                "message": (
                    "Numbered entries outside the port tables were retained as evidence "
                    "but not ingested because their hierarchy is not stated: "
                    f"{standalone[:10]}"
                ),
            }
        )
    metadata = {
        "pages": page_index,
        "records": len(records),
        "group_counts": counts,
        "mict_seen": mict_seen,
        "standalone_entries": standalone[:20],
        "source_columns": list(SOURCE_COLUMNS),
    }
    return records, metadata


def _parse_private_page(
    *,
    lines: list[dict[str, Any]],
    events: list[tuple[float, str, Any]],
    state: dict[str, Any],
    records: list[dict[str, Any]],
    counts: dict[str, int],
    session_ordinals: dict[tuple[str, str, str], int],
    page_index: int,
) -> None:
    event_positions = {event[0] for event in events}
    last_record: dict[str, Any] | None = None
    index = 0
    while index < len(lines):
        line = _text(lines[index]["text"])
        top = float(lines[index]["top"])
        if not line or PAGE_FOOTER.match(line):
            index += 1
            continue
        if top in event_positions:
            _update_context(events, top, top + 0.001, state)
            last_record = None
            index += 1
            continue
        if UNREGISTERED_NOTE.match(line):
            state["unregistered_section"] = True
            last_record = None
            index += 1
            continue
        if PRIVATE_PORT_HEADING.match(line):
            state["group"] = GROUP_PRIVATE
            last_record = None
            index += 1
            continue
        row = NUMBERED_ROW.match(line)
        if row:
            name = _text(row.group("name"))
            ordinal_key = (
                state.get("pmo_code") or "",
                GROUP_PRIVATE,
                _slug(name),
            )
            session_ordinals[ordinal_key] = session_ordinals.get(ordinal_key, 0) + 1
            record = _row_record(
                state=state,
                group=GROUP_PRIVATE,
                ordinal=session_ordinals[ordinal_key],
                name=name,
                number=row.group("number"),
                roro=None,
                non_roro=None,
                remarks=None,
                page=page_index,
                reference=f"pdf:private:page:{page_index}:row:{row.group('number')}",
            )
            records.append(record)
            counts[GROUP_PRIVATE] = counts.get(GROUP_PRIVATE, 0) + 1
            last_record = record
            index += 1
            continue
        # A line that is not a heading or numbered entry continues the previous name.
        if last_record is not None and not line.startswith("*"):
            last_record["name"] = f"{last_record['name']} {line}".strip()
        index += 1


def _split_name_flags(name: str) -> tuple[str, bool | None, bool | None, bool]:
    """Extract RORO markers and trailing unregistered asterisks from a private name."""

    cleaned = name.strip()
    unregistered = cleaned.endswith("*")
    cleaned = cleaned.rstrip("* ").strip()
    match = re.search(r"(?i)(non[\s-]?roro|roro)\s*$", cleaned)
    roro: bool | None = None
    non_roro: bool | None = None
    if match:
        marker = match.group(1).lower().replace(" ", "").replace("-", "")
        if marker == "roro":
            roro = True
        else:
            non_roro = True
        base = cleaned[: match.start()].rstrip(" -\u2013\u2014")
        if base:
            cleaned = base
    return cleaned, roro, non_roro, unregistered


def _candidate(record: dict[str, Any]) -> FacilityCandidate:
    raw_name = record["name"]
    name, embedded_roro, embedded_non_roro, unregistered = _split_name_flags(raw_name)
    group = record["group"]
    roro = record.get("roro") if record.get("roro") is not None else embedded_roro
    non_roro = record.get("non_roro") if record.get("non_roro") is not None else embedded_non_roro
    unregistered = bool(record.get("unregistered") or unregistered)
    evidence = {
        "source_page": SOURCE_URL,
        "pdf_page": record["page"],
        "region": record.get("region"),
        "pmo_code": record.get("pmo_code"),
        "pmo_name": record.get("pmo_name"),
        "source_group": group,
        "source_number": record.get("source_number"),
        "source_name": raw_name,
        "roro_marked": roro,
        "non_roro_marked": non_roro,
        "remarks": record.get("remarks"),
        "unregistered": unregistered,
    }
    anchorage = bool(ANCHORAGE.search(name))
    private = group == GROUP_PRIVATE
    ppa_managed = group in {GROUP_BASEPORT, GROUP_TMO}
    access_note = (
        "Private port listed under PPA's published port statistics. The source does not "
        "state public access, berth capacity or current operating status; private port "
        "access is commonly restricted and must not be assumed."
        if private
        else "Port listed under PPA's published port statistics. The source does not "
        "state public access, berth capacity or current operating status."
    )
    roles: list[RoleData] = []
    if ppa_managed:
        roles.append(
            RoleData(
                role_type="OPERATOR",
                entity_name="Philippine Ports Authority",
                entity_type="GOCC",
                evidence={
                    "basis": "Listed under a PPA Port Management Office heading",
                    "pmo_code": record.get("pmo_code"),
                },
            )
        )
    functions = [FunctionData(function_code="SEA_TRANSPORT", evidence=evidence)]
    return FacilityCandidate(
        source_record_key=record["source_record_key"],
        source_entity_id=None,
        row_reference=record["row_reference"],
        display_name=name[:300],
        facility_type="transport_facility",
        facility_subtype="SEAPORT",
        facility_kind="site" if anchorage else "facility",
        inclusion_class=("PRIVATE_PUBLIC_SERVICE_PROVIDER" if private else "GOVERNMENT_FACILITY"),
        ownership="private" if private else "government",
        ownership_type="PRIVATE_UNSPECIFIED" if private else "GOVERNMENT_UNSPECIFIED",
        operator_type="GOCC" if ppa_managed else "UNKNOWN",
        public_access_class="UNKNOWN",
        access_conditions=access_note,
        record_status="unknown",
        location=LocationData(address_text=None, precision="unknown"),
        functions=functions,
        roles=roles,
    )


class PpaPortListAdapter:
    source_code = "ppa"
    parser_version = "ppa-port-list-1.0.0"
    schema_version = "ppa-port-list-pdf-v1"
    expected_columns = {"required": {"NAME"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records, metadata = parse_port_pdf(spec.content)
        rows: list[ParsedRow] = []
        for record in records:
            record["source_record_key"] = _record_key(
                record,
                record["group"],
                record["name"],
                record.get("_ordinal", 1),
            )
            rows.append(
                ParsedRow(
                    source_record_key=record["source_record_key"],
                    row_reference=record["row_reference"],
                    raw_payload=record,
                    normalized_payload=record,
                )
            )
        # Ordinals are attached after parsing so duplicate source names stay distinct.
        seen: dict[str, int] = {}
        for row in rows:
            base = _record_key(
                row.normalized_payload,
                row.normalized_payload["group"],
                row.normalized_payload["name"],
                1,
            )
            seen[base] = seen.get(base, 0) + 1
            if seen[base] > 1:
                row.source_record_key = f"{base}#{seen[base]}"
                row.normalized_payload["source_record_key"] = row.source_record_key
        warnings: list[dict[str, Any]] = [
            {
                "code": "no_coordinates",
                "message": (
                    "The PPA port list supplies names and RORO/NON-RORO marks but no "
                    "coordinates, PSGC codes, berth capacity or public-access rules. "
                    "Ports remain unmapped until an authorized geocoder is used."
                ),
            }
        ]
        if metadata.get("standalone_entries") or metadata.get("mict_seen"):
            warnings.append(
                {
                    "code": "standalone_entries_preserved_as_evidence",
                    "message": (
                        "Main-section entries outside the port tables, including the "
                        "separate MICT note, were not ingested because the source does "
                        "not state their hierarchy or ownership."
                    ),
                    "metadata": {
                        "mict_seen": metadata.get("mict_seen"),
                        "standalone_entries": metadata.get("standalone_entries"),
                    },
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
            name = _text(payload.get("name"))
            pmo_code = _text(payload.get("pmo_code"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_port_name",
                        "fatal",
                        "A PPA port row has no port name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if not pmo_code:
                issues.append(
                    ValidationIssue(
                        "missing_pmo_code",
                        "warning",
                        f"Port {name} has no parsed PPA Port Management Office code.",
                        row_reference=row.row_reference,
                    )
                )
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_port_key",
                        "error",
                        f"Port key {row.source_record_key} appears more than once.",
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
        return [_candidate(row.normalized_payload) for row in parsed.rows]
