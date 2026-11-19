"""Refine health-facility classifications from preserved official evidence.

Two gaps are repaired here without re-running any source release:

* PhilHealth benefit-package PDFs contributed their raw accreditation category
  as the facility subtype (``Postpartum``, ``GAMOT Package Providers``,
  ``LEVEL 1``). Those labels describe a benefit package, a hospital level or a
  profession, not a physical facility class. Only labels that identify a
  facility class are mapped into the controlled health subtypes; the rest are
  cleared. The raw value remains on ``health.profiles.facility_category`` and
  on the source record.
* The DOH NHFR ownership sub-classification (``Local Government Unit``,
  ``Single Proprietorship``) is more specific than the broad
  ``GOVERNMENT_UNSPECIFIED`` / ``PRIVATE_UNSPECIFIED`` written by earlier
  sources. It is applied only within the source's own government/private
  major class and never across it.

Every change writes a ``history.facility_change_events`` row. Merged
tombstones are left untouched because their public identity is the survivor.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from philfacilities_api.models import (
    Facility,
    FacilityChangeEvent,
    HealthProfile,
)
from philfacilities_api.taxonomy import FACILITY_CATEGORIES, FACILITY_SUBTYPES
from sqlalchemy import select
from sqlalchemy.orm import Session

from .health_labels import (
    CANONICAL_HEALTH_SUBTYPES,
    classify_health_subtype,
)
from .sources.doh_nhfr import OWNERSHIP_TYPES

CHANGED_BY = "refinement:health-classification-evidence-v1"

# A health facility must not carry another category's subtype. These labels are
# valid vocabulary elsewhere, but on a health facility they are source noise.
_FOREIGN_SUBTYPES = frozenset(FACILITY_SUBTYPES) - CANONICAL_HEALTH_SUBTYPES
_FACILITY_CATEGORY_CODES = frozenset(value.upper() for value in FACILITY_CATEGORIES)


def _major(ownership_type: str | None) -> str | None:
    if ownership_type in {"LOCAL_GOVERNMENT", "NATIONAL_GOVERNMENT", "GOCC", "OTHER_PUBLIC_BODY"}:
        return "government"
    if ownership_type in {
        "PRIVATE_INDIVIDUAL_OR_PARTNERSHIP",
        "PRIVATE_CORPORATE",
        "COOPERATIVE",
        "NGO_NON_PROFIT",
        "RELIGIOUS_FAITH_BASED",
    }:
        return "private"
    return None


def _inclusion_class(ownership: str) -> str:
    if ownership == "government":
        return "GOVERNMENT_FACILITY"
    if ownership == "private":
        return "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    return "DISCOVERY_CANDIDATE"


def refine_health_ownership(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 50_000,
    example_limit: int = 20,
) -> dict[str, Any]:
    """Apply the NHFR ownership sub-classification within its major class."""

    stats: dict[str, Any] = {
        "profiles_scanned": 0,
        "would_update": 0,
        "updated": 0,
        "skipped_conflict": 0,
        "skipped_unspecified_subclass": 0,
        "skipped_limit": 0,
        "by_target": Counter(),
        "examples": [],
        "dry_run": dry_run,
    }
    rows = session.execute(
        select(Facility, HealthProfile)
        .join(HealthProfile, HealthProfile.facility_id == Facility.id)
        .where(
            Facility.record_status != "merged",
            Facility.facility_type == "health_facility",
        )
        .order_by(Facility.id)
    ).all()

    for facility, profile in rows:
        stats["profiles_scanned"] += 1
        subclass = (profile.ownership_subclassification or "").strip()
        if not subclass:
            stats["skipped_unspecified_subclass"] += 1
            continue
        target_type = OWNERSHIP_TYPES.get(subclass)
        if target_type is None:
            stats["skipped_unspecified_subclass"] += 1
            continue
        target_major = _major(target_type)
        if target_major is None:
            stats["skipped_unspecified_subclass"] += 1
            continue
        if facility.ownership in {"government", "private"} and facility.ownership != target_major:
            stats["skipped_conflict"] += 1
            continue
        if facility.ownership_type == target_type:
            continue
        # Only broaden an unknown/major-level class. Do not overwrite a more
        # specific type that another official source already established.
        if facility.ownership == "unknown":
            if facility.ownership_type not in {
                "UNKNOWN",
                "GOVERNMENT_UNSPECIFIED",
                "PRIVATE_UNSPECIFIED",
            }:
                stats["skipped_conflict"] += 1
                continue
        elif facility.ownership_type not in {
            "UNKNOWN",
            f"{target_major.upper()}_UNSPECIFIED",
        }:
            stats["skipped_conflict"] += 1
            continue

        if stats["would_update"] >= limit and not dry_run:
            stats["skipped_limit"] += 1
            continue
        stats["would_update"] += 1
        stats["by_target"][target_type] += 1
        if len(stats["examples"]) < example_limit:
            stats["examples"].append(
                {
                    "facility_id": str(facility.id),
                    "name": facility.display_name,
                    "from": {
                        "ownership": facility.ownership,
                        "ownership_type": facility.ownership_type,
                        "inclusion_class": facility.inclusion_class,
                    },
                    "to": {
                        "ownership": target_major,
                        "ownership_type": target_type,
                        "inclusion_class": _inclusion_class(target_major),
                    },
                    "evidence": {
                        "ownership_subclassification": subclass,
                        "doh_facility_id": profile.doh_facility_id,
                    },
                }
            )
        if dry_run:
            continue
        old = {
            "ownership": facility.ownership,
            "ownership_type": facility.ownership_type,
            "inclusion_class": facility.inclusion_class,
        }
        facility.ownership = target_major
        facility.ownership_type = target_type
        facility.inclusion_class = _inclusion_class(target_major)
        for attribute in ("ownership", "ownership_type", "inclusion_class"):
            if old[attribute] == getattr(facility, attribute):
                continue
            session.add(
                FacilityChangeEvent(
                    facility_id=facility.id,
                    change_type="attribute_updated",
                    attribute_name=attribute,
                    old_value={"value": old[attribute]},
                    new_value={"value": getattr(facility, attribute)},
                    source_record_id=profile.source_record_id,
                    changed_by=CHANGED_BY,
                )
            )
        stats["updated"] += 1

    stats["by_target"] = dict(stats["by_target"])
    return stats


def normalize_health_subtypes(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 50_000,
    example_limit: int = 20,
) -> dict[str, Any]:
    """Replace raw accreditation labels with controlled health subtypes."""

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
        select(Facility, HealthProfile)
        .outerjoin(HealthProfile, HealthProfile.facility_id == Facility.id)
        .where(
            Facility.record_status != "merged",
            Facility.facility_type == "health_facility",
        )
        .order_by(Facility.id)
    ).all()

    for facility, profile in rows:
        stats["facilities_scanned"] += 1
        current = (facility.facility_subtype or "").strip()
        if not current:
            continue
        if current in CANONICAL_HEALTH_SUBTYPES:
            continue
        stats["non_canonical"] += 1
        known, target = classify_health_subtype(current)
        if not known:
            upper = current.upper()
            if upper in _FOREIGN_SUBTYPES or upper in _FACILITY_CATEGORY_CODES:
                # A label that is valid vocabulary for another facility type is
                # not evidence of a health class. Clear it instead of guessing.
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
                    "facility_category": profile.facility_category if profile else None,
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
                source_record_id=profile.source_record_id if profile else None,
                changed_by=CHANGED_BY,
            )
        )
        stats["updated"] += 1

    stats["by_target"] = dict(stats["by_target"])
    return stats
