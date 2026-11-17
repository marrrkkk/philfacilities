from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import HealthAccreditation, HealthLicense
from ..pagination import clamp_limit
from ..schemas import (
    AccreditationOut,
    FacilityListResponse,
    HealthDetailResponse,
    LicenseOut,
)
from ..services import build_facility_detail, public_source_record_condition
from .common import get_public_facility, paginated_facilities
from .query import facility_conditions

router = APIRouter(prefix="/health-facilities", tags=["health"])
settings = get_settings()


def _accreditation(row: HealthAccreditation) -> AccreditationOut:
    return AccreditationOut(
        id=row.id,
        authority=row.authority,
        provider_category=row.provider_category,
        benefit_package=row.benefit_package,
        accreditation_category=row.accreditation_category,
        bed_count=row.bed_count,
        sector_code=row.sector_code,
        source_status=row.source_status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        source_as_of=row.source_as_of,
        telephone=row.telephone,
        email=row.email,
        street_address=row.street_address,
        municipality=row.municipality,
        page_reference=row.page_reference,
        source_record_id=row.source_record_id,
    )


@router.get("", response_model=FacilityListResponse, summary="List health facilities")
def list_health_facilities(
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
        facility_type="health_facility",
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


@router.get("/{facility_id}", response_model=HealthDetailResponse, summary="Health facility detail")
def get_health_facility(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = get_public_facility(db, facility_id)
    if facility.facility_type != "health_facility":
        from ..errors import ApiError

        raise ApiError(
            404, "health_facility_not_found", "The requested facility is not a health facility."
        )
    detail = build_facility_detail(db, facility)
    licenses = db.scalars(
        select(HealthLicense)
        .where(
            HealthLicense.facility_id == facility.id,
            public_source_record_condition(HealthLicense.source_record_id),
        )
        .order_by(HealthLicense.valid_until.desc().nullslast())
    ).all()
    accreditations = db.scalars(
        select(HealthAccreditation)
        .where(
            HealthAccreditation.facility_id == facility.id,
            public_source_record_condition(HealthAccreditation.source_record_id),
        )
        .order_by(HealthAccreditation.valid_until.desc().nullslast())
    ).all()
    return HealthDetailResponse(
        facility=detail,
        licenses=[
            LicenseOut(
                id=row.id,
                issuing_authority=row.issuing_authority,
                license_number=row.license_number,
                license_type=row.license_type,
                source_status=row.source_status,
                valid_from=row.valid_from,
                valid_until=row.valid_until,
                source_record_id=row.source_record_id,
            )
            for row in licenses
        ],
        accreditations=[_accreditation(row) for row in accreditations],
    )


@router.get(
    "/{facility_id}/licenses",
    response_model=list[LicenseOut],
    summary="Health facility licenses",
)
def get_health_licenses(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = get_public_facility(db, facility_id)
    rows = db.scalars(
        select(HealthLicense)
        .where(
            HealthLicense.facility_id == facility.id,
            public_source_record_condition(HealthLicense.source_record_id),
        )
        .order_by(HealthLicense.valid_until.desc().nullslast())
    ).all()
    return [
        LicenseOut(
            id=row.id,
            issuing_authority=row.issuing_authority,
            license_number=row.license_number,
            license_type=row.license_type,
            source_status=row.source_status,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            source_record_id=row.source_record_id,
        )
        for row in rows
    ]


@router.get(
    "/{facility_id}/accreditations",
    response_model=list[AccreditationOut],
    summary="Health facility accreditations",
)
def get_health_accreditations(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = get_public_facility(db, facility_id)
    rows = db.scalars(
        select(HealthAccreditation)
        .where(
            HealthAccreditation.facility_id == facility.id,
            public_source_record_condition(HealthAccreditation.source_record_id),
        )
        .order_by(HealthAccreditation.valid_until.desc().nullslast())
    ).all()
    return [_accreditation(row) for row in rows]
