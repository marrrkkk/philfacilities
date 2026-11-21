"""Service helpers: quality.

Split from ``services.py``; the package __init__ re-exports every name.
"""

from __future__ import annotations

from ..models import (
    Facility,
    FacilityLocation,
)
from ..schemas import (
    FacilityQuality,
    QualityWarning,
)


def _urban_rural(value: str | None) -> str | None:
    """Normalise the PSGC ``U``/``R`` barangay code without inferring a class."""

    return {"U": "urban", "R": "rural"}.get((value or "").strip().upper())


def quality_for(
    facility: Facility,
    location: FacilityLocation | None,
    source_count: int,
) -> FacilityQuality:
    warnings: list[QualityWarning] = []
    precision = location.precision if location else "unknown"
    if not location or location.latitude is None or location.longitude is None:
        warnings.append(
            QualityWarning(
                code="no_coordinates",
                severity="info",
                message="No source coordinates were supplied. Location is unknown.",
            )
        )
    elif precision in {"barangay_centroid", "map_geocoded"}:
        warnings.append(
            QualityWarning(
                code="low_precision_location",
                severity="warning",
                message="Coordinates are area-level or geocoded; they do not represent a building.",
            )
        )
    if facility.is_synthetic:
        warnings.append(
            QualityWarning(
                code="synthetic_record",
                severity="info",
                message=(
                    "Synthetic demonstration record; not an official government facility record."
                ),
            )
        )
    if source_count == 0:
        warnings.append(
            QualityWarning(
                code="no_source_evidence",
                severity="warning",
                message="No source record is linked to this facility.",
            )
        )
    return FacilityQuality(
        identity_status="source_linked" if source_count else "unverified",
        location_precision=precision,  # type: ignore[arg-type]
        warnings=warnings,
        source_count=source_count,
    )
