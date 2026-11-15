from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import EnrollmentObservation, ResourceObservation
from ..pagination import clamp_limit
from ..schemas import (
    EnrollmentObservationOut,
    FacilityListResponse,
    ResourceObservationOut,
    SchoolDetailResponse,
)
from ..services import build_facility_detail
from .common import get_public_facility, paginated_facilities
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
    )


@router.get("/{facility_id}", response_model=SchoolDetailResponse, summary="School detail")
def get_school(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = get_public_facility(db, facility_id)
    if facility.facility_type != "school":
        from ..errors import ApiError

        raise ApiError(404, "school_not_found", "The requested facility is not a school.")
    detail = build_facility_detail(db, facility)
    rows = db.scalars(
        select(EnrollmentObservation)
        .where(EnrollmentObservation.facility_id == facility.id)
        .order_by(EnrollmentObservation.school_year.desc(), EnrollmentObservation.grade_level)
    ).all()
    resources = db.scalars(
        select(ResourceObservation)
        .where(ResourceObservation.facility_id == facility.id)
        .order_by(ResourceObservation.school_year.desc(), ResourceObservation.resource_code)
    ).all()
    return SchoolDetailResponse(
        facility=detail,
        enrollment=[
            EnrollmentObservationOut(
                school_year=row.school_year,
                grade_level=row.grade_level,
                sex=row.sex,
                learner_count=row.learner_count,
                observed_at=row.observed_at,
                source_record_id=row.source_record_id,
            )
            for row in rows
        ],
        resources=[
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
            for row in resources
        ],
    )


@router.get(
    "/{facility_id}/enrollment",
    response_model=list[EnrollmentObservationOut],
    summary="School enrollment observations",
)
def get_school_enrollment(
    facility_id: str,
    db: Annotated[Session, Depends(get_db)],
    school_year: str | None = None,
):
    facility = get_public_facility(db, facility_id)
    query = select(EnrollmentObservation).where(EnrollmentObservation.facility_id == facility.id)
    if school_year:
        query = query.where(EnrollmentObservation.school_year == school_year)
    rows = db.scalars(
        query.order_by(EnrollmentObservation.school_year.desc(), EnrollmentObservation.grade_level)
    ).all()
    return [
        EnrollmentObservationOut(
            school_year=row.school_year,
            grade_level=row.grade_level,
            sex=row.sex,
            learner_count=row.learner_count,
            observed_at=row.observed_at,
            source_record_id=row.source_record_id,
        )
        for row in rows
    ]


@router.get(
    "/{facility_id}/resources",
    response_model=list[ResourceObservationOut],
    summary="School resource observations",
)
def get_school_resources(
    facility_id: str,
    db: Annotated[Session, Depends(get_db)],
    school_year: str | None = None,
):
    facility = get_public_facility(db, facility_id)
    query = select(ResourceObservation).where(ResourceObservation.facility_id == facility.id)
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
