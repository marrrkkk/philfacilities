"""Refine school-facility classifications from preserved source evidence.

The OSM education layers publish the raw ``amenity`` or ``building`` value as
the facility subtype (``school``, ``university``, ``kindergarten``). Those are
source tags, not the controlled school vocabulary. A facility can also carry a
subtype that belongs to another category (``PUBLIC_LIBRARY``, ``SPORTS_COMPLEX``,
``LOCAL_GOVERNMENT_OFFICE``) when a shared map feature was imported through a
health, community or government layer.

This pass maps the labels that establish a school class, clears labels that are
valid vocabulary elsewhere, and reports anything it cannot classify. It never
guesses a school level or sector from the facility name, and it never changes
the facility type. The raw tag stays on the source record.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from philfacilities_api.models import Facility, FacilityChangeEvent
from philfacilities_api.taxonomy import FACILITY_SUBTYPES
from sqlalchemy import select
from sqlalchemy.orm import Session

from .school_labels import (
    CANONICAL_SCHOOL_SUBTYPES,
    classify_school_subtype,
)

CHANGED_BY = "refinement:school-classification-evidence-v1"

# A school must not carry another category's subtype. These labels are valid
# vocabulary elsewhere, but on a school they are source noise.
_FOREIGN_SUBTYPES = frozenset(FACILITY_SUBTYPES) - CANONICAL_SCHOOL_SUBTYPES


def normalize_school_subtypes(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 50_000,
    example_limit: int = 20,
) -> dict[str, Any]:
    """Replace raw map tags with controlled school subtypes."""

    stats: dict[str, Any] = {
        "facilities_scanned": 0,
        "non_canonical": 0,
        "would_update": 0,
        "updated": 0,
        "cleared": 0,
        "mapped": 0,
        "unmapped": 0,
        "skipped_limit": 0,
        "by_target": Counter(),
        "examples": [],
        "unmapped_examples": [],
        "dry_run": dry_run,
    }
    rows = session.execute(
        select(Facility)
        .where(
            Facility.record_status != "merged",
            Facility.facility_type == "school",
        )
        .order_by(Facility.id)
    ).scalars()

    for facility in rows:
        stats["facilities_scanned"] += 1
        current = (facility.facility_subtype or "").strip()
        if not current:
            continue
        if current in CANONICAL_SCHOOL_SUBTYPES:
            continue
        stats["non_canonical"] += 1
        known, target = classify_school_subtype(current)
        if not known and current.upper() in _FOREIGN_SUBTYPES:
            # A category label from another facility type is not evidence of a
            # school class. Clear it instead of guessing.
            known, target = True, None
        if not known:
            stats["unmapped"] += 1
            if len(stats["unmapped_examples"]) < example_limit:
                stats["unmapped_examples"].append(
                    {
                        "facility_id": str(facility.id),
                        "name": facility.display_name,
                        "subtype": current,
                    }
                )
            continue
        if target == current:
            continue
        if stats["would_update"] >= limit:
            stats["skipped_limit"] += 1
            continue
        stats["would_update"] += 1
        key = target or "(none)"
        stats["by_target"][key] += 1
        if target is None:
            stats["cleared"] += 1
        else:
            stats["mapped"] += 1
        if len(stats["examples"]) < example_limit:
            stats["examples"].append(
                {
                    "facility_id": str(facility.id),
                    "name": facility.display_name,
                    "from": current or None,
                    "to": target,
                }
            )
        if dry_run:
            continue
        facility.facility_subtype = target
        session.add(
            FacilityChangeEvent(
                facility_id=facility.id,
                change_type="attribute_updated",
                attribute_name="facility_subtype",
                old_value={"value": current or None},
                new_value={"value": target},
                changed_by=CHANGED_BY,
            )
        )
        stats["updated"] += 1

    stats["by_target"] = dict(stats["by_target"])
    return stats
