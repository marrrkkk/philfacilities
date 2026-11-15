"""Structural inclusion/exclusion rules for facility candidates.

The binding policy is in ``expand/docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md``. This
module implements only the parts that can be decided without guessing: a candidate
must use the published facility categories and kinds, must not be a raw commercial
property label, and an ``OTHER_QUALIFYING_FACILITY`` must carry some evidence of a
public-service role. Name matching is deliberately not used; a service counter inside
a mall is not excluded merely because the host building name contains "mall".
"""

from __future__ import annotations

from philfacilities_api.taxonomy import (
    BUILDING,
    FACILITY,
    FACILITY_CATEGORIES,
    FACILITY_KINDS,
    FACILITY_UNIT,
    INFRASTRUCTURE_ASSET,
    OTHER_QUALIFYING_FACILITY,
    PROJECT,
    SITE,
)

from .contracts import FacilityCandidate

# Raw commercial/residential labels that must never become a canonical subtype.
EXCLUDED_SUBTYPES = frozenset(
    {
        "APARTMENT",
        "BUSINESS",
        "CINEMA",
        "COMMERCIAL",
        "CONDOMINIUM",
        "DEPARTMENT_STORE",
        "ENTERTAINMENT",
        "FACTORY",
        "HOTEL",
        "HOUSE",
        "INDUSTRIAL",
        "MALL",
        "OFFICE",
        "OFFICE_TOWER",
        "RESIDENCE",
        "RESIDENTIAL",
        "RESORT",
        "RESTAURANT",
        "RETAIL",
        "SHOP",
        "SHOPPING_CENTER",
        "SUPERMARKET",
        "WAREHOUSE",
    }
)

# Kinds that belong to the related-asset/project model, not the public facility registry.
EXCLUDED_FACILITY_KINDS = frozenset({INFRASTRUCTURE_ASSET, PROJECT})
ALLOWED_FACILITY_KINDS = frozenset({FACILITY, SITE, BUILDING, FACILITY_UNIT})


def exclusion_reason(candidate: FacilityCandidate) -> str | None:
    """Return a policy reason when a candidate must not enter the public registry."""

    kind = (candidate.facility_kind or FACILITY).strip().lower()
    if kind in EXCLUDED_FACILITY_KINDS:
        return (
            f"facility_kind={kind!r} is a related asset or project, not an operating "
            "facility record"
        )
    if kind not in ALLOWED_FACILITY_KINDS:
        return f"facility_kind={kind!r} is not a recognised facility kind"
    if kind not in FACILITY_KINDS:
        return f"facility_kind={kind!r} is outside the published taxonomy"

    facility_type = (candidate.facility_type or "").strip().lower()
    if facility_type not in FACILITY_CATEGORIES:
        return f"facility_type={facility_type!r} is outside the published taxonomy"

    subtype = (candidate.facility_subtype or "").strip().upper().replace(" ", "_")
    if subtype in EXCLUDED_SUBTYPES:
        return f"facility_subtype={subtype!r} is an excluded commercial/residential label"

    if facility_type == OTHER_QUALIFYING_FACILITY and not (
        candidate.functions or candidate.services or candidate.access_conditions
    ):
        return (
            "OTHER_QUALIFYING_FACILITY requires documented functions, services or "
            "public-access conditions; a generic company/place record is not enough"
        )
    return None
