from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..middleware import conditional_json
from ..models import AdministrativeUnit, GeographicRelease, GeographyCrosswalk
from ..pagination import clamp_limit
from ..schemas import (
    AdministrativeUnitOut,
    FacilityListResponse,
    GeographyCrosswalkOut,
    GeographyReleaseOut,
)
from .common import paginated_facilities
from .query import facility_conditions

router = APIRouter(tags=["geography"])


def _release(db: Session, release_label: str | None) -> GeographicRelease | None:
    if release_label:
        return db.scalars(
            select(GeographicRelease).where(GeographicRelease.release_label == release_label)
        ).first()
    return db.scalars(
        select(GeographicRelease).order_by(GeographicRelease.reference_date.desc().nullslast())
    ).first()


@router.get(
    "/geographies",
    response_model=list[AdministrativeUnitOut],
    summary="PSGC administrative units",
)
def list_geographies(
    db: Annotated[Session, Depends(get_db)],
    release: str | None = Query(None, description="PSGC release label"),
    level: str | None = Query(None, description="region, province, municipality, barangay"),
    parent: str | None = Query(None, description="Parent PSGC code"),
    q: str | None = Query(None, max_length=200),
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
):
    selected_release = _release(db, release)
    if not selected_release:
        return []
    query = select(AdministrativeUnit).where(AdministrativeUnit.release_id == selected_release.id)
    if level:
        query = query.where(AdministrativeUnit.geographic_level == level)
    if parent:
        query = query.where(AdministrativeUnit.parent_psgc_code == parent)
    if q:
        query = query.where(AdministrativeUnit.name.ilike(f"%{q.strip()}%"))
    rows = db.scalars(
        query.order_by(AdministrativeUnit.psgc_code).offset(offset).limit(min(limit, 500))
    ).all()
    return [AdministrativeUnitOut.model_validate(row) for row in rows]


@router.get(
    "/geographies/{psgc_code}",
    response_model=AdministrativeUnitOut,
    summary="One PSGC administrative unit",
)
def get_geography(
    psgc_code: str,
    db: Annotated[Session, Depends(get_db)],
    release: str | None = None,
):
    selected_release = _release(db, release)
    if not selected_release:
        raise ApiError(404, "geography_release_not_found", "No PSGC release is available.")
    unit = db.scalars(
        select(AdministrativeUnit).where(
            AdministrativeUnit.release_id == selected_release.id,
            AdministrativeUnit.psgc_code == psgc_code,
        )
    ).first()
    if not unit:
        raise ApiError(404, "geography_not_found", "No administrative unit has that PSGC code.")
    return AdministrativeUnitOut.model_validate(unit)


@router.get(
    "/geographies/{psgc_code}/facilities",
    response_model=FacilityListResponse,
    summary="Facilities in a PSGC area",
)
def get_geography_facilities(
    psgc_code: str,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(20, ge=1),
    cursor: str | None = None,
):
    conditions = facility_conditions(psgc=psgc_code)
    return paginated_facilities(db, conditions, clamp_limit(limit, 100, 20), cursor)


@router.get(
    "/geography-releases",
    response_model=list[GeographyReleaseOut],
    summary="PSGC release history",
)
def list_geography_releases(request: Request, db: Annotated[Session, Depends(get_db)]):
    rows = db.scalars(
        select(GeographicRelease).order_by(GeographicRelease.reference_date.desc().nullslast())
    ).all()
    payload = [GeographyReleaseOut.model_validate(row).model_dump(mode="json") for row in rows]
    return conditional_json(request, payload, max_age=300)


@router.get(
    "/geography-crosswalk",
    response_model=list[GeographyCrosswalkOut],
    summary="Code changes between two PSGC releases",
)
def get_geography_crosswalk(
    db: Annotated[Session, Depends(get_db)],
    from_release: str = Query(...),
    to_release: str = Query(...),
):
    source = db.scalars(
        select(GeographicRelease).where(GeographicRelease.release_label == from_release)
    ).first()
    target = db.scalars(
        select(GeographicRelease).where(GeographicRelease.release_label == to_release)
    ).first()
    if not source or not target:
        raise ApiError(404, "geography_release_not_found", "One of the releases was not found.")
    rows = db.scalars(
        select(GeographyCrosswalk).where(
            GeographyCrosswalk.from_release_id == source.id,
            GeographyCrosswalk.to_release_id == target.id,
        )
    ).all()
    return [
        GeographyCrosswalkOut(
            from_psgc_code=row.from_psgc_code,
            to_psgc_code=row.to_psgc_code,
            change_type=row.change_type,
            from_release=source.release_label,
            to_release=target.release_label,
            evidence=row.evidence,
        )
        for row in rows
    ]
