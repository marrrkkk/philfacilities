"""Service helpers: search.

Split from ``services.py``; the package __init__ re-exports every name.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, select

from ..models import (
    AdministrativeUnit,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    GeographicRelease,
    SourceRecord,
)


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def dumps_with_default(value):
    import json

    return json.dumps(value, default=str)


def utcnow() -> datetime:
    return datetime.now(UTC)


def facility_search_condition(q: str):
    """Return a condition matching facilities by name, source key, address, or locality.

    Every branch is an uncorrelated ID query. The previous correlated EXISTS form
    re-ran the source and location joins for every facility and took tens of
    seconds against the national dataset. An uncorrelated UNION lets PostgreSQL
    use the trigram indexes once per branch and hash the result.
    """

    pattern = f"%{q.strip()}%"
    latest_release = (
        select(GeographicRelease.id)
        .order_by(GeographicRelease.reference_date.desc().nullslast())
        .limit(1)
        .scalar_subquery()
    )

    # A location stores only its own PSGC code. Truncate a matching unit's code
    # to its level prefix (region 2, province 5, municipality 7, barangay 10) so
    # a municipality/province/region name finds the facilities below it while a
    # province name does not pull in a whole municipality. The current geographic
    # release is used so retired names do not resurface.
    matched_prefix = case(
        (
            AdministrativeUnit.geographic_level == "region",
            func.substr(AdministrativeUnit.psgc_code, 1, 2),
        ),
        (
            AdministrativeUnit.geographic_level == "province",
            func.substr(AdministrativeUnit.psgc_code, 1, 5),
        ),
        (
            AdministrativeUnit.geographic_level == "municipality",
            func.substr(AdministrativeUnit.psgc_code, 1, 7),
        ),
        else_=AdministrativeUnit.psgc_code,
    )
    locality_ids = (
        select(FacilityLocation.facility_id)
        .join(
            AdministrativeUnit,
            and_(
                AdministrativeUnit.release_id == latest_release,
                AdministrativeUnit.name.ilike(pattern),
                func.starts_with(FacilityLocation.psgc_code, matched_prefix),
            ),
        )
        .where(FacilityLocation.is_current.is_(True))
    )

    source_ids = (
        select(FacilitySourceLink.facility_id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .where(SourceRecord.source_record_key.ilike(pattern))
    )
    address_ids = select(FacilityLocation.facility_id).where(
        FacilityLocation.is_current.is_(True),
        FacilityLocation.address_text.ilike(pattern),
    )

    matched_ids = (
        select(Facility.id)
        .where(Facility.display_name.ilike(pattern))
        .union(
            select(Facility.id).where(Facility.official_name.ilike(pattern)),
            source_ids,
            address_ids,
            locality_ids,
        )
    )
    return Facility.id.in_(matched_ids)
