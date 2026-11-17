"""Shared rights and publication vocabulary.

The values here are the enforced contract between the ingestion pipeline and the
public API. A dataset is only publishable when its redistribution status is one of
``PUBLIC_RIGHTS`` *and* its publication gate has been approved. ``PUBLIC_RIGHTS``
includes verified, publicly available sources for which no explicit prohibition was
found; that policy requires reviewed, non-personal fields, provenance, attribution,
and takedown-on-notice. Ingestion may still store, parse, and validate restricted or
review-pending records; those records stay internal and are never returned by public
endpoints.
"""

from __future__ import annotations

RIGHTS_UNKNOWN = "unknown"
RIGHTS_REVIEW_REQUIRED = "review_required"
RIGHTS_APPROVED_PUBLIC = "approved_public_redistribution"
RIGHTS_APPROVED_ATTRIBUTION = "approved_with_attribution"
RIGHTS_PUBLICLY_AVAILABLE_VERIFIED = "publicly_available_verified"
RIGHTS_RESTRICTED = "restricted_non_redistributable"
RIGHTS_DENIED = "denied"
RIGHTS_EXPIRED = "expired"

PUBLIC_RIGHTS = frozenset(
    {
        RIGHTS_APPROVED_PUBLIC,
        RIGHTS_APPROVED_ATTRIBUTION,
        RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
    }
)
NON_PUBLIC_RIGHTS = frozenset(
    {
        RIGHTS_UNKNOWN,
        RIGHTS_REVIEW_REQUIRED,
        RIGHTS_RESTRICTED,
        RIGHTS_DENIED,
        RIGHTS_EXPIRED,
    }
)
ALL_RIGHTS = PUBLIC_RIGHTS | NON_PUBLIC_RIGHTS

PUBLICATION_BLOCKED = "blocked"
PUBLICATION_INTERNAL_ONLY = "internal_only"
PUBLICATION_QUARANTINED = "quarantined"
PUBLICATION_APPROVED = "approved"
PUBLICATION_PUBLISHED = "published"

PUBLIC_GATE_STATUSES = frozenset({PUBLICATION_APPROVED, PUBLICATION_PUBLISHED})

# Older datasets and fixtures used these names. They remain accepted so existing
# databases and tests keep working, but every new release is written with the
# explicit vocabulary above.
LEGACY_RIGHTS = {
    "allowed": RIGHTS_APPROVED_PUBLIC,
    "allowed_with_conditions": RIGHTS_APPROVED_ATTRIBUTION,
    "not_applicable": RIGHTS_APPROVED_PUBLIC,
    "restricted": RIGHTS_RESTRICTED,
    "permission_required": RIGHTS_REVIEW_REQUIRED,
    "review_required": RIGHTS_REVIEW_REQUIRED,
}


def normalize_rights(value: str | None) -> str:
    """Return the canonical rights state for a stored or requested value."""

    if not value:
        return RIGHTS_UNKNOWN
    value = value.strip()
    if value in ALL_RIGHTS:
        return value
    return LEGACY_RIGHTS.get(value, RIGHTS_UNKNOWN)


def rights_allow_public(value: str | None) -> bool:
    return normalize_rights(value) in PUBLIC_RIGHTS


def gate_is_public(status: str | None) -> bool:
    return status in PUBLIC_GATE_STATUSES


def dataset_is_publishable(
    *,
    redistribution_status: str | None,
    gate_status: str | None,
    is_synthetic: bool = False,
    publication_status: str | None = None,
) -> bool:
    """Single source of truth for whether a dataset may feed public records."""

    if publication_status == PUBLICATION_INTERNAL_ONLY:
        return False
    if is_synthetic:
        return True
    return rights_allow_public(redistribution_status) and gate_is_public(gate_status)
