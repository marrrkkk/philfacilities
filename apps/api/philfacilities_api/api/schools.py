from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import ResourceObservation
from ..pagination import clamp_limit
from ..schemas import (
    FacilityCompact,
    FacilityCompactExtended,
    FacilityDetail,
    FacilityListResponse,
    ResourceObservationOut,
    SchoolDetailResponse,
)
from ..services import (
    build_facility_compact,
    build_facility_compact_extended,
    build_facility_detail,
    public_source_record_condition,
)
from .common import (
    DetailShape,
    DetailView,
    compact_extended_response,
    compact_wrapper_response,
    get_public_facility,
    paginated_facilities,
    parse_include,
)
from .query import facility_conditions

router = APIRouter(prefix="/schools", tags=["schools"])
settings = get_settings()


@router.get("", response_model=FacilityListResponse, summary="List schools")
def list_schools(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = Query(None, max_length=200),
    ownership: str | None = None,
    psgc: str | None = None,
    region_code: str | None = None,
    province_code: str | None = None,
    municipality_code: str | None = None,
    source: str | None = None,
    has_coordinates: bool | None = None,
    location_precision: str | None = None,
    reference_period_start: date | None = None,
    reference_period_end: date | None = None,
    limit: int = Query(20, ge=1),
    cursor: str | None = None,
    total: bool = Query(True, description="Set false to skip the count(*) query."),
):
    conditions = facility_conditions(
        facility_type="school",
        ownership=ownership,
        q=q,
        psgc=psgc,
        region_code=region_code,
        province_code=province_code,
        municipality_code=municipality_code,
        source=source,
        has_coordinates=has_coordinates,
        location_precision=location_precision,
        reference_period_start=reference_period_start,
        reference_period_end=reference_period_end,
    )
    return paginated_facilities(
        db,
        conditions,
        clamp_limit(limit, settings.max_page_size, settings.default_page_size),
        cursor,
        with_total=total,
    )


@router.get(
    "/{facility_id}",
    response_model=SchoolDetailResponse
    | FacilityDetail
    | FacilityCompact
    | FacilityCompactExtended,
    summary="School detail",
    description=(
        "The default `shape=wrapper` keeps the historical `{facility, resources}` keys. "
        "`shape=detail` opts in to the unified FacilityDetail shared with "
        "`GET /v1/facilities/{id}`. `view=compact` returns the twelve-key card, and "
        "`include=sources,assertions,domain` attaches only the requested sections "
        "to a compact card. `assertions` is capped at 200 rows; use the paginated "
        "`/v1/facilities/{facility_id}/assertions` endpoint for the complete claim set. "
        "School resource observations are currently empty in the working database "
        "until a public observation source is ingested."
    ),
)
def get_school(
    facility_id: str,
    db: Annotated[Session, Depends(get_db)],
    view: DetailView = "full",
    shape: DetailShape = "wrapper",
    include: str | None = Query(
        None,
        description=(
            "Comma-separated optional sections: sources, assertions, domain. "
            "Assertions are capped at 200; use /assertions for all claims."
        ),
    ),
):
    facility = get_public_facility(db, facility_id)
    if facility.facility_type != "school":
        from ..errors import ApiError

        raise ApiError(404, "school_not_found", "The requested facility is not a school.")
    sections = parse_include(include)
    resource_rows = db.scalars(
        select(ResourceObservation)
        .where(
            ResourceObservation.facility_id == facility.id,
            public_source_record_condition(ResourceObservation.source_record_id),
        )
        .order_by(ResourceObservation.school_year.desc(), ResourceObservation.resource_code)
    ).all()
    resources = [
        ResourceObservationOut(
            school_year=row.school_year,
            resource_category=row.resource_category,
            resource_code=row.resource_code,
            value_numeric=(float(row.value_numeric) if row.value_numeric is not None else None),
            value_text=row.value_text,
            unit=row.unit,
            observed_at=row.observed_at,
            source_record_id=row.source_record_id,
        )
        for row in resource_rows
    ]

    if shape == "detail":
        if view == "compact":
            if sections:
                return compact_extended_response(
                    build_facility_compact_extended(db, facility, sections, resources=resources),
                    sections,
                )
            return build_facility_compact(db, facility)
        return build_facility_detail(db, facility)

    if view == "compact":
        compact = (
            build_facility_compact_extended(db, facility, sections, resources=resources)
            if sections
            else build_facility_compact(db, facility)
        )
        return compact_wrapper_response(compact, sections, resources=resources)
    return SchoolDetailResponse(facility=build_facility_detail(db, facility), resources=resources)


@router.get(
    "/{facility_id}/resources",
    response_model=list[ResourceObservationOut],
    summary="School resource observations",
    description=(
        "Currently empty in the working database: no rights-cleared public "
        "resource-observation source has been ingested. The endpoint is kept in "
        "/v1 for compatibility and will populate when such a source is published."
    ),
)
def get_school_resources(
    facility_id: str,
    db: Annotated[Session, Depends(get_db)],
    school_year: str | None = None,
):
    facility = get_public_facility(db, facility_id)
    query = select(ResourceObservation).where(
        ResourceObservation.facility_id == facility.id,
        public_source_record_condition(ResourceObservation.source_record_id),
    )
    if school_year:
        query = query.where(ResourceObservation.school_year == school_year)
    rows = db.scalars(
        query.order_by(ResourceObservation.school_year.desc(), ResourceObservation.resource_code)
    ).all()
    return [
        ResourceObservationOut(
            school_year=row.school_year,
            resource_category=row.resource_category,
            resource_code=row.resource_code,
            value_numeric=float(row.value_numeric) if row.value_numeric is not None else None,
            value_text=row.value_text,
            unit=row.unit,
            observed_at=row.observed_at,
            source_record_id=row.source_record_id,
        )
        for row in rows
    ]
