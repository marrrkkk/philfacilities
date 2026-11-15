from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..models import (
    Dataset,
    Facility,
    FacilityLocation,
    HealthAccreditation,
    Release,
    SourceRecord,
)
from ..rights import PUBLIC_RIGHTS
from ..schemas import AccreditationListItem, AccreditationListResponse
from ..services import public_facility_filter
from .health import _accreditation

router = APIRouter(prefix="/accreditations", tags=["health"])
settings = get_settings()


def _public_accreditation_source():
    """Only expose accreditations whose release still permits public redistribution."""

    return exists(
        select(1)
        .select_from(SourceRecord)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(
            SourceRecord.id == HealthAccreditation.source_record_id,
            or_(
                Dataset.is_synthetic.is_(True),
                and_(
                    Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
                    Dataset.publication_status.in_(("approved", "published")),
                    Release.publication_status.in_(("approved", "published")),
                ),
            ),
        )
        .correlate(HealthAccreditation)
    )


def _conditions(
    *,
    facility_id: str | None,
    q: str | None,
    provider_category: str | None,
    authority: str | None,
    sector_code: str | None,
    source_status: str | None,
    psgc: str | None,
    region_code: str | None,
    municipality_code: str | None,
    valid_on: date | None,
) -> list:
    conditions = [
        *public_facility_filter(),
        _public_accreditation_source(),
    ]
    if facility_id:
        try:
            identifier = uuid.UUID(facility_id)
        except ValueError as exc:
            raise ApiError(
                400,
                "invalid_facility_id",
                "facility_id must be a PhilFacilities UUID.",
            ) from exc
        conditions.append(HealthAccreditation.facility_id == identifier)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                Facility.display_name.ilike(pattern),
                HealthAccreditation.provider_category.ilike(pattern),
                HealthAccreditation.benefit_package.ilike(pattern),
            )
        )
    if provider_category:
        conditions.append(HealthAccreditation.provider_category == provider_category)
    if authority:
        conditions.append(HealthAccreditation.authority == authority)
    if sector_code:
        conditions.append(HealthAccreditation.sector_code == sector_code)
    if source_status:
        conditions.append(HealthAccreditation.source_status == source_status)
    if valid_on:
        conditions.append(HealthAccreditation.valid_from <= valid_on)
        conditions.append(
            or_(
                HealthAccreditation.valid_until.is_(None),
                HealthAccreditation.valid_until >= valid_on,
            )
        )
    geography_filters = {
        "psgc": (psgc, None),
        "region_code": (region_code, 2),
        "municipality_code": (municipality_code, 7),
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
                    .correlate(Facility)
                )
            )
    return conditions


@router.get("", response_model=AccreditationListResponse, summary="List health accreditations")
def list_accreditations(
    db: Annotated[Session, Depends(get_db)],
    facility_id: str | None = None,
    q: str | None = Query(None, max_length=200),
    provider_category: str | None = None,
    authority: str | None = None,
    sector_code: str | None = None,
    source_status: str | None = None,
    psgc: str | None = None,
    region_code: str | None = None,
    municipality_code: str | None = None,
    valid_on: date | None = None,
    limit: int = Query(20, ge=1),
    offset: int = Query(0, ge=0),
):
    conditions = _conditions(
        facility_id=facility_id,
        q=q,
        provider_category=provider_category,
        authority=authority,
        sector_code=sector_code,
        source_status=source_status,
        psgc=psgc,
        region_code=region_code,
        municipality_code=municipality_code,
        valid_on=valid_on,
    )
    page_size = min(limit, settings.max_page_size)
    total = (
        db.scalar(
            select(func.count())
            .select_from(HealthAccreditation)
            .join(Facility, Facility.id == HealthAccreditation.facility_id)
            .where(*conditions)
        )
        or 0
    )
    rows = db.execute(
        select(HealthAccreditation, Facility)
        .join(Facility, Facility.id == HealthAccreditation.facility_id)
        .where(*conditions)
        .order_by(
            HealthAccreditation.valid_until.desc().nullslast(),
            Facility.display_name,
            HealthAccreditation.id,
        )
        .offset(offset)
        .limit(page_size)
    ).all()
    items = []
    for accreditation, facility in rows:
        payload = _accreditation(accreditation)
        items.append(
            AccreditationListItem(
                **payload.model_dump(),
                facility_id=facility.id,
                facility_slug=facility.slug,
                facility_name=facility.display_name,
                facility_type=facility.facility_type,
                is_synthetic=facility.is_synthetic,
            )
        )
    return AccreditationListResponse(
        items=items,
        total=total,
        limit=page_size,
        offset=offset,
    )
