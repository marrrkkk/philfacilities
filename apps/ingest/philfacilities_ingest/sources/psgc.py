from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from typing import Any

from openpyxl import load_workbook

from ..contracts import ReleaseSpec
from .common import clean_text, jsonify, normalise_code, normalise_header

PSGC_ALIASES = ["psgc_code", "psgc", "code", "geographic_code"]
NAME_ALIASES = ["name", "area_name", "geographic_name", "name_of_area"]
LEVEL_ALIASES = ["geographic_level", "level", "geo_level"]
PARENT_ALIASES = ["parent_psgc_code", "parent_code", "parent_psgc"]
CORRESPONDENCE_ALIASES = ["correspondence_code", "correspondence"]
OLD_NAME_ALIASES = ["old_name", "previous_name"]
CITY_CLASS_ALIASES = ["city_class", "city_classification"]
INCOME_ALIASES = ["income_classification", "income_class"]
URBAN_RURAL_ALIASES = ["urban_rural", "urbanrural"]
ISLAND_ALIASES = ["island_region", "island_group"]


class PSGCSchemaError(ValueError):
    pass


@dataclass
class ParsedUnit:
    psgc_code: str
    name: str
    geographic_level: str
    parent_psgc_code: str | None
    correspondence_code: str | None
    old_name: str | None
    city_class: str | None
    income_classification: str | None
    urban_rural: str | None
    island_region: str | None
    raw_payload: dict[str, Any]
    sheet: str
    row: int


def _level_from_sheet(title: str) -> str | None:
    lowered = title.lower()
    for level, tokens in {
        "region": ("region",),
        "province": ("province",),
        "municipality": ("city", "municipal", "huc", "cc"),
        "barangay": ("barangay", "bgy"),
    }.items():
        if any(token in lowered for token in tokens):
            return level
    return None


def _infer_parent(code: str, candidates: set[str]) -> str | None:
    best: str | None = None
    for candidate in candidates:
        if candidate == code:
            continue
        prefix = candidate.rstrip("0")
        if (
            prefix
            and code.startswith(prefix)
            and (best is None or len(prefix) > len(best.rstrip("0")))
        ):
            best = candidate
    return best


def parse_psgc_workbook(
    content: bytes, *, expected_filename: str = "psgc.xlsx"
) -> tuple[list[ParsedUnit], list[str]]:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    units: list[ParsedUnit] = []
    warnings: list[str] = []
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            header_index = None
            headers: list[str] = []
            for index, row in enumerate(rows[:15]):
                normalised = [normalise_header(value) for value in row]
                if len(set(normalised) & set(PSGC_ALIASES)) and len(
                    set(normalised) & set(NAME_ALIASES)
                ):
                    header_index = index
                    headers = normalised
                    break
            if header_index is None:
                warnings.append(f"sheet {sheet.title!r}: no PSGC/name header row; skipped")
                continue
            for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
                payload = {
                    headers[i]: jsonify(value)
                    for i, value in enumerate(row)
                    if i < len(headers) and headers[i]
                }
                code = normalise_code(
                    next((payload.get(name) for name in PSGC_ALIASES if payload.get(name)), None)
                )
                name = clean_text(
                    next((payload.get(name) for name in NAME_ALIASES if payload.get(name)), None)
                )
                if not code or not name:
                    continue
                level = clean_text(
                    next((payload.get(name) for name in LEVEL_ALIASES if payload.get(name)), None)
                )
                level = (level or _level_from_sheet(sheet.title) or "").lower()
                if level not in {"region", "province", "municipality", "barangay"}:
                    if level in {"city", "municipality", "huc", "cc"}:
                        level = "municipality"
                    else:
                        warnings.append(
                            f"sheet {sheet.title!r} row {offset}: unknown geographic "
                            f"level {level!r}; skipped"
                        )
                        continue
                units.append(
                    ParsedUnit(
                        psgc_code=code,
                        name=name,
                        geographic_level=level,
                        parent_psgc_code=normalise_code(
                            next(
                                (payload.get(name) for name in PARENT_ALIASES if payload.get(name)),
                                None,
                            )
                        ),
                        correspondence_code=normalise_code(
                            next(
                                (
                                    payload.get(name)
                                    for name in CORRESPONDENCE_ALIASES
                                    if payload.get(name)
                                ),
                                None,
                            )
                        ),
                        old_name=clean_text(
                            next(
                                (
                                    payload.get(name)
                                    for name in OLD_NAME_ALIASES
                                    if payload.get(name)
                                ),
                                None,
                            )
                        ),
                        city_class=clean_text(
                            next(
                                (
                                    payload.get(name)
                                    for name in CITY_CLASS_ALIASES
                                    if payload.get(name)
                                ),
                                None,
                            )
                        ),
                        income_classification=clean_text(
                            next(
                                (payload.get(name) for name in INCOME_ALIASES if payload.get(name)),
                                None,
                            )
                        ),
                        urban_rural=clean_text(
                            next(
                                (
                                    payload.get(name)
                                    for name in URBAN_RURAL_ALIASES
                                    if payload.get(name)
                                ),
                                None,
                            )
                        ),
                        island_region=clean_text(
                            next(
                                (payload.get(name) for name in ISLAND_ALIASES if payload.get(name)),
                                None,
                            )
                        ),
                        raw_payload=payload,
                        sheet=sheet.title,
                        row=offset,
                    )
                )
    finally:
        workbook.close()

    codes = {unit.psgc_code for unit in units}
    levels = {"region": 0, "province": 1, "municipality": 2, "barangay": 3}
    for unit in units:
        if not unit.parent_psgc_code:
            parent = _infer_parent(unit.psgc_code, codes)
            if parent:
                unit.parent_psgc_code = parent
        elif unit.parent_psgc_code not in codes:
            warnings.append(
                f"unit {unit.psgc_code}: declared parent {unit.parent_psgc_code} "
                "not found in release"
            )
    for unit in units:
        if unit.parent_psgc_code:
            parent = next((item for item in units if item.psgc_code == unit.parent_psgc_code), None)
            if parent and levels.get(parent.geographic_level, 0) >= levels.get(
                unit.geographic_level, 0
            ):
                warnings.append(
                    f"unit {unit.psgc_code}: parent level is not higher than child level"
                )
    if not units:
        raise PSGCSchemaError("No PSGC rows could be extracted from the workbook.")
    return units, warnings


def build_crosswalk(previous: list[ParsedUnit], current: list[ParsedUnit]) -> list[dict[str, Any]]:
    previous_by_code = {unit.psgc_code: unit for unit in previous}
    current_by_code = {unit.psgc_code: unit for unit in current}
    changes: list[dict[str, Any]] = []
    for code in sorted(set(previous_by_code) | set(current_by_code)):
        old = previous_by_code.get(code)
        new = current_by_code.get(code)
        if old and new:
            if old.name.strip() != new.name.strip():
                changes.append(
                    {
                        "from_psgc_code": code,
                        "to_psgc_code": code,
                        "change_type": "renamed",
                        "evidence": {"old_name": old.name, "new_name": new.name},
                    }
                )
        elif old and not new:
            changes.append(
                {
                    "from_psgc_code": code,
                    "to_psgc_code": old.correspondence_code,
                    "change_type": "retired",
                    "evidence": {
                        "old_name": old.name,
                        "correspondence_code": old.correspondence_code,
                    },
                }
            )
        elif new and not old:
            changes.append(
                {
                    "from_psgc_code": new.correspondence_code or new.psgc_code,
                    "to_psgc_code": new.psgc_code,
                    "change_type": "added",
                    "evidence": {
                        "new_name": new.name,
                        "correspondence_code": new.correspondence_code,
                    },
                }
            )
    return changes


def release_dates(spec: ReleaseSpec) -> dict[str, date | None]:
    return {
        "reference_date": spec.reference_period_end,
        "published_at": spec.source_published_at.date() if spec.source_published_at else None,
    }
