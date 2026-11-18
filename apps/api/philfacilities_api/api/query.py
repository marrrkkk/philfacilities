from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import and_, exists, or_, select

from ..errors import ApiError
from ..models import (
    Agency,
    Dataset,
    Facility,
    FacilityFunction,
    FacilityLocation,
    FacilitySourceLink,
    Release,
    SourceRecord,
)
from ..rights import PUBLIC_RIGHTS
from ..services import public_facility_index_filter


def facility_conditions(
    *,
    facility_type: str | None = None,
    facility_subtype: str | None = None,
    inclusion_class: str | None = None,
    ownership: str | None = None,
    ownership_type: str | None = None,
    operator_type: str | None = None,
    public_access_class: str | None = None,
    facility_kind: str | None = None,
    function: str | None = None,
    q: str | None = None,
    psgc: str | None = None,
    region_code: str | None = None,
    province_code: str | None = None,
    municipality_code: str | None = None,
    barangay_code: str | None = None,
    source: str | None = None,
    has_coordinates: bool | None = None,
    location_precision: str | None = None,
    reference_period_start: date | None = None,
    reference_period_end: date | None = None,
    updated_since: datetime | None = None,
) -> list:
    # A reference-period match already requires a rights-cleared source release, so
    # the correlated public-source EXISTS would only add work and trigger a slow
    # nested-loop plan at national scale. Keep the stored public flag in that case.
    # Browse/map/search paths use the indexed stored publication flag. Detail
    # endpoints still re-validate live source evidence in `facility_is_public`.
    conditions = list(public_facility_index_filter())
    if (
        reference_period_start
        and reference_period_end
        and reference_period_start > reference_period_end
    ):
        raise ApiError(
            400,
            "invalid_reference_period",
            "reference_period_start must be on or before reference_period_end.",
        )
    if facility_type:
        conditions.append(Facility.facility_type == facility_type)
    if facility_subtype:
        conditions.append(Facility.facility_subtype == facility_subtype)
    if inclusion_class:
        conditions.append(Facility.inclusion_class == inclusion_class)
    if ownership:
        conditions.append(Facility.ownership == ownership)
    if ownership_type:
        conditions.append(Facility.ownership_type == ownership_type)
    if operator_type:
        conditions.append(Facility.operator_type == operator_type)
    if public_access_class:
        conditions.append(Facility.public_access_class == public_access_class)
    if facility_kind:
        conditions.append(Facility.facility_kind == facility_kind)
    if function:
        conditions.append(
            exists(
                select(1)
                .select_from(FacilityFunction)
                .where(
                    FacilityFunction.facility_id == Facility.id,
                    FacilityFunction.function_code == function,
                )
                .correlate(Facility)
            )
        )
    if q and q.strip():
        from ..services import facility_search_condition

        conditions.append(facility_search_condition(q))
    if updated_since:
        conditions.append(Facility.updated_at >= updated_since)

    # PSGC codes are hierarchical but zero-padded, so a region code is not a literal
    # prefix of its provinces/municipalities/barangays. Match against the meaningful
    # prefix for the requested level instead.
    geography_filters = {
        "psgc": (psgc, None),
        "region_code": (region_code, 2),
        "province_code": (province_code, 5),
        "municipality_code": (municipality_code, 7),
        "barangay_code": (barangay_code, None),
    }
    for code, prefix_length in geography_filters.values():
        if code:
            prefix = code[:prefix_length] if prefix_length else code
            conditions.append(
                exists(
                    select(1)
                    .select_from(FacilityLocation)
                    .where(
                        FacilityLocation.facility_id == Facility.id,
                        FacilityLocation.is_current.is_(True),
                        FacilityLocation.psgc_code.startswith(prefix),
                    )
                    # The map query joins FacilityLocation outside this subquery; without
                    # an explicit correlation target SQLAlchemy removes the subquery FROM
                    # and raises "no FROM clauses due to auto-correlation".
                    .correlate(Facility)
                )
            )

    if source:
        source_exists = exists(
            select(1)
            .select_from(FacilitySourceLink)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .join(Agency, Dataset.agency_id == Agency.id)
            .where(
                FacilitySourceLink.facility_id == Facility.id,
                Agency.short_code == source.lower(),
            )
            .correlate(Facility)
        )
        conditions.append(source_exists)

    if reference_period_start or reference_period_end:
        # Match a facility when at least one of its rights-cleared source releases
        # overlaps the requested interval. A release with no recorded boundary cannot
        # be proven to fall inside the interval, so it does not match.
        period_conditions = [
            or_(
                Dataset.is_synthetic.is_(True),
                and_(
                    Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
                    Dataset.publication_status.in_(("approved", "published")),
                    Release.publication_status.in_(("approved", "published")),
                ),
            ),
        ]
        if reference_period_start:
            period_conditions.append(Release.reference_period_end >= reference_period_start)
        if reference_period_end:
            period_conditions.append(Release.reference_period_start <= reference_period_end)
        conditions.append(
            Facility.id.in_(
                select(FacilitySourceLink.facility_id)
                .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
                .join(Release, SourceRecord.release_id == Release.id)
                .join(Dataset, Release.dataset_id == Dataset.id)
                .where(*period_conditions)
            )
        )

    if has_coordinates is not None:
        coord_condition = (
            FacilityLocation.facility_id == Facility.id,
            FacilityLocation.is_current.is_(True),
            FacilityLocation.latitude.is_not(None),
            FacilityLocation.longitude.is_not(None),
        )
        if has_coordinates:
            conditions.append(
                exists(
                    select(1)
                    .select_from(FacilityLocation)
                    .where(*coord_condition)
                    .correlate(Facility)
                )
            )
        else:
            conditions.append(
                ~exists(
                    select(1)
                    .select_from(FacilityLocation)
                    .where(*coord_condition)
                    .correlate(Facility)
                )
            )

    if location_precision:
        conditions.append(
            exists(
                select(1)
                .select_from(FacilityLocation)
                .where(
                    FacilityLocation.facility_id == Facility.id,
                    FacilityLocation.is_current.is_(True),
                    FacilityLocation.precision == location_precision,
                )
                .correlate(Facility)
            )
        )
    return conditions
