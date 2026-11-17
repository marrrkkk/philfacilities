"""Shared validation primitives used by the pipeline and source adapters.

These helpers only answer factual questions about a source value: is it inside
the Philippines plausibility box, does it look like a PSGC code, which required
fields are absent, and which keys repeat. They never fill, coerce, or infer a
missing value. Keeping them in one module stops each adapter from inventing a
slightly different bbox or code shape.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

PHILIPPINES_BBOX = {
    "min_lat": 4.2,
    "max_lat": 21.5,
    "min_lon": 116.0,
    "max_lon": 127.0,
}

# PSGC codes are hierarchical decimal strings: region (2), province (4),
# municipality/city (6), barangay (10). Leading zeros are significant.
PSGC_CODE_LENGTHS = (2, 4, 6, 10)
PSGC_PATTERN = re.compile(r"^\d+$")


def coordinate_in_philippines(latitude: float, longitude: float) -> bool:
    """Return whether a coordinate lies inside the Philippines plausibility box."""

    return (
        PHILIPPINES_BBOX["min_lat"] <= latitude <= PHILIPPINES_BBOX["max_lat"]
        and PHILIPPINES_BBOX["min_lon"] <= longitude <= PHILIPPINES_BBOX["max_lon"]
    )


def coordinate_issue(latitude: float | None, longitude: float | None) -> dict[str, Any] | None:
    """Describe an implausible coordinate, or return ``None`` when it is usable."""

    if latitude is None or longitude is None:
        return None
    if coordinate_in_philippines(latitude, longitude):
        return None
    return {
        "message": (
            "Coordinate lies outside the Philippines plausibility box; retained with warning."
        ),
        "details": {"latitude": latitude, "longitude": longitude},
    }


def psgc_shape_issue(value: str | None) -> str | None:
    """Return a reason when a PSGC code is malformed, without changing it."""

    if value is None or value == "":
        return None
    code = str(value)
    if not PSGC_PATTERN.fullmatch(code):
        return f"PSGC code {code!r} is not a decimal string; leading zeros must be preserved."
    if len(code) not in PSGC_CODE_LENGTHS:
        return f"PSGC code {code!r} has length {len(code)}; expected one of {PSGC_CODE_LENGTHS}."
    return None


def missing_required_fields(payload: Mapping[str, Any], required: Iterable[str]) -> list[str]:
    """Return required field names whose value is absent or an empty string."""

    return [name for name in required if name not in payload or payload[name] in (None, "")]


def duplicate_values(values: Iterable[Any]) -> list[Any]:
    """Return values that occur more than once, in first-seen order."""

    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates
