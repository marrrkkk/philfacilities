"""Department of Energy — list of existing power plants.

The DOE Energy Planning and Policy Bureau publishes dated PDF lists of existing
grid-connected and off-grid power plants. The lists carry the DOE facility code,
the official facility name, resource and technology type, connection type,
installed and dependable capacity, unit count, municipality/province, region,
operator, owner/IPPA, owner type, contract type and commissioning date. They do
not carry coordinates or a public-access classification.

The adapter preserves the source labels and capacities. It does not infer a
legal owner from an operator name, a completion status from inclusion in the
list, or coordinates from a municipality. The source's OWNER TYPE is retained as
evidence; only explicit NPC/PSALM government markers produce a government
ownership class. Other IPP/NON-NPC records are treated as private public-service
providers, with ``ownership_type=PRIVATE_UNSPECIFIED`` rather than a guessed
corporate form.
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
    UtilityData,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text

GOVERNMENT_MARKERS = (
    "NPC",
    "NATIONAL POWER CORPORATION",
    "PSALM",
    "POWER SECTOR ASSETS AND LIABILITIES MANAGEMENT",
)
CATEGORY_WORDS = {
    "COAL",
    "OIL-BASED",
    "OIL BASED",
    "RENEWABLE ENERGY",
    "NATURAL GAS",
    "GEOTHERMAL",
    "HYDRO",
    "SOLAR",
    "WIND",
    "BIOMASS",
    "ENERGY STORAGE",
    "LUZON OFF-GRID",
    "VISAYAS OFF-GRID",
    "MINDANAO OFF-GRID",
    "TOTAL",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value) or "").strip()


def _number(value: Any) -> float | None:
    text = _text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper() or "UNNAMED"


def _is_header(row: list[Any]) -> bool:
    first = _text(row[0]).upper() if row else ""
    second = _text(row[1]).upper() if len(row) > 1 else ""
    return (
        "FACILITY NAME" in first
        or "POWER PLANT" in first
        or first.startswith("DEPARTMENT OF ENERGY")
        or first.endswith("GRID")
        or (not first and second in {"POWER PLANT", "FACILITY NAME", "SUBTYPE"})
        or second.startswith("DEPARTMENT OF ENERGY")
        or second.startswith("LIST OF EXISTING")
    )


def _row_value(row: list[Any], index: int) -> str:
    return _text(row[index]) if index < len(row) else ""


def _category_row(name: str) -> bool:
    return name.upper().strip() in CATEGORY_WORDS or name.upper().startswith("TOTAL")


def parse_power_plants(content: bytes, *, grid: str) -> list[dict[str, Any]]:
    """Return one record per DOE row, preserving blank unit-level fields."""

    records: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table:
                    continue
                for row in table:
                    if not row or _is_header(row):
                        continue
                    if len(row) >= 18:
                        record = _grid_record(row, grid)
                    elif len(row) >= 9:
                        record = _offgrid_record(row, grid)
                    else:
                        record = None
                    if record is not None:
                        records.append(record)
    return records


def _grid_record(row: list[Any], grid: str) -> dict[str, Any] | None:
    code = _row_value(row, 0)
    official_name = _row_value(row, 1)
    resource_type = _row_value(row, 2)
    if not code or _category_row(code) or not resource_type:
        return None
    visit = len(row) >= 20
    installed_index = 6 if visit else 5
    installed = _number(_row_value(row, installed_index))
    if installed is None:
        return None
    return {
        "facility_code": code,
        "official_name": official_name or None,
        "resource_type": resource_type,
        "technology": _row_value(row, 3),
        "technology_type": (_row_value(row, 4) if visit else _row_value(row, 3)),
        "connection_type": (_row_value(row, 5) if visit else _row_value(row, 4)),
        "installed_mw": installed,
        "dependable_mw": _number(_row_value(row, 7 if visit else 6)),
        "number_of_units": _row_value(row, 8 if visit else 7),
        "municipality_province": _row_value(row, 9 if visit else 8),
        "province": _row_value(row, 10 if visit else 9),
        "sub_grid": _row_value(row, 11) if visit else None,
        "city_municipality": (_row_value(row, 12) if visit else _row_value(row, 10)),
        "region": _row_value(row, 13 if visit else 11),
        "operator": _row_value(row, 14 if visit else 12),
        "owner": _row_value(row, 15 if visit else 13),
        "fit_approved": _row_value(row, 16 if visit else 14),
        "owner_type": _row_value(row, 17 if visit else 15),
        "contract_type": _row_value(row, 18 if visit else 16),
        "date_commissioned": _row_value(row, 19 if visit else 17),
        "grid": grid,
    }


def _offgrid_record(row: list[Any], grid: str) -> dict[str, Any] | None:
    code = _row_value(row, 1)
    subtype = _row_value(row, 2)
    if not code or _category_row(code) or not subtype:
        return None
    installed = _number(_row_value(row, 3))
    if installed is None:
        return None
    return {
        "facility_code": code,
        "official_name": None,
        "resource_type": subtype,
        "technology": subtype,
        "technology_type": subtype,
        "connection_type": "Off-grid",
        "installed_mw": installed,
        "dependable_mw": _number(_row_value(row, 4)),
        "number_of_units": None,
        "municipality_province": _row_value(row, 5),
        "province": None,
        "sub_grid": None,
        "city_municipality": None,
        "region": _row_value(row, 6),
        "operator": _row_value(row, 7),
        "owner": None,
        "owner_type": _row_value(row, 8),
        "operating_hours": _row_value(row, 9),
        "contract_type": None,
        "date_commissioned": _row_value(row, 10),
        "grid": grid,
    }


def _ownership(record: dict[str, Any]) -> tuple[str, str, str, str]:
    owner_type = (record.get("owner_type") or "").upper()
    owner = (record.get("owner") or "").upper()
    operator = (record.get("operator") or "").upper()
    haystack = f"{owner_type} {owner} {operator}"
    if "NON-NPC" in owner_type:
        return (
            "private",
            "PRIVATE_UNSPECIFIED",
            "PRIVATE_UNSPECIFIED",
            "PRIVATE_PUBLIC_SERVICE_PROVIDER",
        )
    if any(marker in haystack for marker in GOVERNMENT_MARKERS):
        return (
            "government",
            "NATIONAL_GOVERNMENT",
            "NATIONAL_GOVERNMENT",
            "GOVERNMENT_FACILITY",
        )
    if owner_type or owner or operator:
        return (
            "private",
            "PRIVATE_UNSPECIFIED",
            "PRIVATE_UNSPECIFIED",
            "PRIVATE_PUBLIC_SERVICE_PROVIDER",
        )
    return ("unknown", "UNKNOWN", "UNKNOWN", "DISCOVERY_CANDIDATE")


def _record_key(record: dict[str, Any]) -> str:
    return f"DOE:{_slug(record['grid'])}:{_slug(record['facility_code'])}"


class DoePowerPlantAdapter:
    source_code = "doe"
    parser_version = "doe-loepp-pdf-1.1.0"
    schema_version = "doe-loepp-pdf-v1"

    def __init__(self, spec: ReleaseSpec, *, grid: str) -> None:
        self.spec = spec
        self.grid = grid

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        records = parse_power_plants(spec.content, grid=self.grid)
        if not records:
            raise ValueError(f"DOE {self.grid} PDF contained no power-plant rows.")
        counts: dict[str, int] = {}
        rows: list[ParsedRow] = []
        for record in records:
            base = _record_key(record)
            counts[base] = counts.get(base, 0) + 1
            key = base if counts[base] == 1 else f"{base}#{counts[base]}"
            rows.append(
                ParsedRow(
                    source_record_key=key,
                    row_reference=f"doe:{self.grid}:{record['facility_code']}"
                    + ("" if counts[base] == 1 else f"#{counts[base]}"),
                    raw_payload=record,
                    normalized_payload=record,
                )
            )
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "registry_presence_is_not_operating_status",
                    "message": (
                        "Inclusion in the DOE existing-power-plant list is registry "
                        "evidence only. It does not prove that a unit is currently "
                        "operating, available or connected."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The DOE lists supply municipality/province and region labels, "
                        "not coordinates. No coordinates or PSGC codes are inferred."
                    ),
                },
                {
                    "code": "unit_rows_preserved",
                    "message": (
                        "Unit rows with blank official-name/operator cells are preserved "
                        "as separate DOE-coded rows; blanks are not filled from the "
                        "preceding row."
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
            name = _text(payload.get("facility_code"))
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_facility_code",
                        "fatal",
                        "DOE power-plant row has no facility code.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if _number(payload.get("installed_mw")) is None:
                issues.append(
                    ValidationIssue(
                        "missing_installed_capacity",
                        "error",
                        f"DOE power plant {name} has no installed capacity.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if row.source_record_key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_facility_code",
                        "error",
                        f"DOE facility key {row.source_record_key} appears more than once.",
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
            code = _text(payload.get("facility_code"))
            if not code:
                continue
            official_name = _text(payload.get("official_name")) or None
            display_name = official_name or code
            ownership, ownership_type, operator_type, inclusion = _ownership(payload)
            address = ", ".join(
                part
                for part in (
                    _text(payload.get("municipality_province")),
                    _text(payload.get("province")),
                    _text(payload.get("region")),
                )
                if part
            )
            installed = _number(payload.get("installed_mw"))
            dependable = _number(payload.get("dependable_mw"))
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=display_name,
                    facility_type="utility_facility",
                    facility_subtype="POWER_PLANT",
                    facility_kind="facility",
                    inclusion_class=inclusion,
                    ownership=ownership,
                    ownership_type=ownership_type,
                    operator_type=operator_type,
                    public_access_class="UNKNOWN",
                    record_status="unknown",
                    location=LocationData(
                        precision="unknown",
                        method=None,
                        address_text=address or None,
                        psgc_code=None,
                    ),
                    functions=[
                        FunctionData(
                            function_code="POWER_SERVICE",
                            source_value=_text(payload.get("resource_type")) or "Power plant",
                            designation_status="source_listed",
                            capacity_value=installed,
                            capacity_unit="megawatts_installed",
                            evidence={
                                "source": (
                                    "Department of Energy — List of Existing Power Plants "
                                    f"({payload.get('grid')})"
                                ),
                                "doe_facility_code": code,
                                "official_name": official_name,
                                "resource_type": payload.get("resource_type"),
                                "technology": payload.get("technology"),
                                "technology_type": payload.get("technology_type"),
                                "connection_type": payload.get("connection_type"),
                                "installed_mw": installed,
                                "dependable_mw": dependable,
                                "number_of_units": payload.get("number_of_units"),
                                "region": payload.get("region"),
                                "province": payload.get("province"),
                                "municipality_province": payload.get("municipality_province"),
                                "city_municipality": payload.get("city_municipality"),
                                "sub_grid": payload.get("sub_grid"),
                                "operator": payload.get("operator"),
                                "owner": payload.get("owner"),
                                "owner_type": payload.get("owner_type"),
                                "contract_type": payload.get("contract_type"),
                                "date_commissioned": payload.get("date_commissioned"),
                                "operating_hours": payload.get("operating_hours"),
                            },
                        )
                    ],
                    utility=UtilityData(
                        doe_facility_code=code,
                        resource_type=_text(payload.get("resource_type")) or None,
                        technology_type=_text(payload.get("technology_type")) or None,
                        connection_type=_text(payload.get("connection_type")) or None,
                        grid=_text(payload.get("grid")) or None,
                        owner_type=_text(payload.get("owner_type")) or None,
                        contract_type=_text(payload.get("contract_type")) or None,
                        installed_mw=installed,
                        dependable_mw=dependable,
                        number_of_units=_integer(payload.get("number_of_units")),
                        date_commissioned=_text(payload.get("date_commissioned")) or None,
                    ),
                )
            )
        return candidates
