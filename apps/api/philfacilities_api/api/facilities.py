from __future__ import annotations

import contextlib
import csv
import io
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from geoalchemy2.types import Geography
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..csv_safety import sanitize_csv_cell
from ..db import get_db
from ..errors import ApiError
from ..models import (
    Facility,
    FacilityChangeEvent,
    FacilityLocation,
    HealthAccreditation,
)
from ..pagination import clamp_limit, decode_cursor, encode_cursor
from ..schemas import (
    AccessClass,
    AccreditationOut,
    AttributeAssertionOut,
    ChangeListResponse,
    FacilityDetail,
    FacilityKind,
    FacilityListResponse,
    FacilityMapResponse,
    FacilityType,
    InclusionClass,
    NearbyResponse,
    OperatorType,
    OwnershipType,
    SourceEvidence,
)
from ..services import (
    build_facility_detail,
    build_summaries,
    load_attribute_assertions,
    load_source_evidence,
)
from .query import facility_conditions

router = APIRouter(prefix="/facilities", tags=["facilities"])
settings = get_settings()

FacilityTypeFilter = FacilityType
OwnershipFilter = Literal["government", "private", "unknown"]
PrecisionFilter = Literal[
    "gps_verified", "field_verified", "source_gps", "map_geocoded", "barangay_centroid", "unknown"
]


def _get_public_facility(db: Session, identifier: str) -> Facility:
    facility = None
    with contextlib.suppress(ValueError):
        facility = db.get(Facility, uuid.UUID(identifier))
    if facility is None:
        facility = db.scalars(select(Facility).where(Facility.slug == identifier)).first()
    if facility is None or facility.publication_status != "public":
        raise ApiError(404, "facility_not_found", "No published facility exists with that ID.")
    return facility


@router.get("", response_model=FacilityListResponse, summary="Search and list facilities")
def list_facilities(
    db: Annotated[Session, Depends(get_db)],
    type: FacilityTypeFilter | None = None,
    subtype: str | None = Query(None, max_length=80),
    inclusion_class: InclusionClass | None = None,
    ownership: OwnershipFilter | None = None,
    ownership_type: OwnershipType | None = None,
    operator_type: OperatorType | None = None,
    public_access_class: AccessClass | None = None,
    facility_kind: FacilityKind | None = None,
    function: str | None = Query(None, max_length=60),
    q: str | None = Query(None, max_length=200),
    psgc: str | None = Query(None, max_length=12),
    region_code: str | None = Query(None, max_length=12),
    province_code: str | None = Query(None, max_length=12),
    municipality_code: str | None = Query(None, max_length=12),
    barangay_code: str | None = Query(None, max_length=12),
    source: str | None = Query(None, max_length=40),
    has_coordinates: bool | None = None,
    location_precision: PrecisionFilter | None = None,
    reference_period_start: date | None = Query(
        None, description="Start of the source-release reference period (inclusive)."
    ),
    reference_period_end: date | None = Query(
        None, description="End of the source-release reference period (inclusive)."
    ),
    updated_since: datetime | None = None,
    limit: int = Query(20, ge=1),
    cursor: str | None = None,
):
    conditions = facility_conditions(
        facility_type=type,
        facility_subtype=subtype,
        inclusion_class=inclusion_class,
        ownership=ownership,
        ownership_type=ownership_type,
        operator_type=operator_type,
        public_access_class=public_access_class,
        facility_kind=facility_kind,
        function=function,
        q=q,
        psgc=psgc,
        region_code=region_code,
        province_code=province_code,
        municipality_code=municipality_code,
        barangay_code=barangay_code,
        source=source,
        has_coordinates=has_coordinates,
        location_precision=location_precision,
        reference_period_start=reference_period_start,
        reference_period_end=reference_period_end,
        updated_since=updated_since,
    )
    selected_limit = clamp_limit(limit, settings.max_page_size, settings.default_page_size)
    total = db.scalar(select(func.count()).select_from(Facility).where(*conditions)) or 0

    query = select(Facility).where(*conditions)
    if cursor:
        updated_at, facility_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Facility.updated_at < updated_at,
                and_(Facility.updated_at == updated_at, Facility.id < facility_id),
            )
        )
    facilities = list(
        db.scalars(
            query.order_by(Facility.updated_at.desc(), Facility.id.desc()).limit(selected_limit + 1)
        ).all()
    )
    has_more = len(facilities) > selected_limit
    facilities = facilities[:selected_limit]
    summaries = build_summaries(db, facilities)
    next_cursor = (
        encode_cursor(summaries[-1].updated_at, summaries[-1].id)
        if has_more and summaries
        else None
    )
    return FacilityListResponse(
        items=summaries,
        next_cursor=next_cursor,
        has_more=has_more,
        total=total,
        limit=selected_limit,
    )


@router.get("/within", response_model=FacilityMapResponse, summary="Facilities inside a bbox")
def facilities_within(
    db: Annotated[Session, Depends(get_db)],
    bbox: str = Query(..., description="min_lon,min_lat,max_lon,max_lat"),
    type: FacilityTypeFilter | None = None,
    subtype: str | None = Query(None, max_length=80),
    inclusion_class: InclusionClass | None = None,
    ownership: OwnershipFilter | None = None,
    ownership_type: OwnershipType | None = None,
    operator_type: OperatorType | None = None,
    public_access_class: AccessClass | None = None,
    facility_kind: FacilityKind | None = None,
    function: str | None = Query(None, max_length=60),
    q: str | None = Query(None, max_length=200),
    psgc: str | None = Query(None, max_length=12),
    region_code: str | None = Query(None, max_length=12),
    province_code: str | None = Query(None, max_length=12),
    municipality_code: str | None = Query(None, max_length=12),
    barangay_code: str | None = Query(None, max_length=12),
    source: str | None = Query(None, max_length=40),
    location_precision: PrecisionFilter | None = None,
    reference_period_start: date | None = None,
    reference_period_end: date | None = None,
    updated_since: datetime | None = None,
    limit: int = Query(200, ge=1),
):
    try:
        min_lon, min_lat, max_lon, max_lat = (float(value) for value in bbox.split(","))
    except (ValueError, TypeError) as exc:
        raise ApiError(
            400, "invalid_bbox", "bbox must be min_lon,min_lat,max_lon,max_lat."
        ) from exc
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ApiError(400, "invalid_bbox", "bbox coordinates are outside valid ranges.")
    area = (max_lon - min_lon) * (max_lat - min_lat)
    if area > settings.max_bbox_area_deg2:
        raise ApiError(
            400,
            "bbox_too_large",
            "The requested bounding box is too large; zoom in or narrow the viewport.",
            {"max_area_deg2": settings.max_bbox_area_deg2},
        )
    selected_limit = min(limit, settings.max_map_features)
    conditions = facility_conditions(
        facility_type=type,
        facility_subtype=subtype,
        inclusion_class=inclusion_class,
        ownership=ownership,
        ownership_type=ownership_type,
        operator_type=operator_type,
        public_access_class=public_access_class,
        facility_kind=facility_kind,
        function=function,
        q=q,
        psgc=psgc,
        region_code=region_code,
        province_code=province_code,
        municipality_code=municipality_code,
        barangay_code=barangay_code,
        source=source,
        location_precision=location_precision,
        reference_period_start=reference_period_start,
        reference_period_end=reference_period_end,
        updated_since=updated_since,
    )
    envelope = cast(func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326), Geography)
    facilities = list(
        db.scalars(
            select(Facility)
            .join(FacilityLocation, FacilityLocation.facility_id == Facility.id)
            .where(
                *conditions,
                FacilityLocation.is_current.is_(True),
                FacilityLocation.geom.is_not(None),
                func.ST_Intersects(FacilityLocation.geom, envelope),
            )
            .order_by(Facility.updated_at.desc())
            .limit(selected_limit + 1)
        ).all()
    )
    truncated = len(facilities) > selected_limit
    facilities = facilities[:selected_limit]
    return FacilityMapResponse(
        items=build_summaries(db, facilities),
        limit=selected_limit,
        truncated=truncated,
        bbox=bbox,
    )


@router.get("/nearby", response_model=NearbyResponse, summary="Facilities near a point")
def facilities_nearby(
    db: Annotated[Session, Depends(get_db)],
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(5000, ge=1),
    type: FacilityTypeFilter | None = None,
    subtype: str | None = Query(None, max_length=80),
    inclusion_class: InclusionClass | None = None,
    ownership: OwnershipFilter | None = None,
    ownership_type: OwnershipType | None = None,
    operator_type: OperatorType | None = None,
    public_access_class: AccessClass | None = None,
    facility_kind: FacilityKind | None = None,
    function: str | None = Query(None, max_length=60),
    q: str | None = Query(None, max_length=200),
    psgc: str | None = Query(None, max_length=12),
    region_code: str | None = Query(None, max_length=12),
    province_code: str | None = Query(None, max_length=12),
    municipality_code: str | None = Query(None, max_length=12),
    barangay_code: str | None = Query(None, max_length=12),
    source: str | None = Query(None, max_length=40),
    location_precision: PrecisionFilter | None = None,
    reference_period_start: date | None = None,
    reference_period_end: date | None = None,
    updated_since: datetime | None = None,
    limit: int = Query(50, ge=1),
):
    if radius_m > settings.max_nearby_radius_m:
        raise ApiError(
            400,
            "radius_too_large",
            "The requested radius is too large.",
            {"max_radius_m": settings.max_nearby_radius_m},
        )
    selected_limit = min(limit, settings.max_map_features)
    conditions = facility_conditions(
        facility_type=type,
        facility_subtype=subtype,
        inclusion_class=inclusion_class,
        ownership=ownership,
        ownership_type=ownership_type,
        operator_type=operator_type,
        public_access_class=public_access_class,
        facility_kind=facility_kind,
        function=function,
        q=q,
        psgc=psgc,
        region_code=region_code,
        province_code=province_code,
        municipality_code=municipality_code,
        barangay_code=barangay_code,
        source=source,
        location_precision=location_precision,
        reference_period_start=reference_period_start,
        reference_period_end=reference_period_end,
        updated_since=updated_since,
    )
    point = cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)
    distance = func.ST_Distance(FacilityLocation.geom, point)
    facilities = list(
        db.scalars(
            select(Facility)
            .join(FacilityLocation, FacilityLocation.facility_id == Facility.id)
            .where(
                *conditions,
                FacilityLocation.is_current.is_(True),
                FacilityLocation.geom.is_not(None),
                func.ST_DWithin(FacilityLocation.geom, point, radius_m),
            )
            .order_by(distance)
            .limit(selected_limit + 1)
        ).all()
    )
    truncated = len(facilities) > selected_limit
    facilities = facilities[:selected_limit]
    return NearbyResponse(
        items=build_summaries(db, facilities),
        center={"lat": lat, "lon": lon},
        radius_m=radius_m,
        limit=selected_limit,
        truncated=truncated,
    )


@router.get("/{facility_id}", response_model=FacilityDetail, summary="Facility detail")
def get_facility(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = _get_public_facility(db, facility_id)
    return build_facility_detail(db, facility)


@router.get(
    "/{facility_id}/sources",
    response_model=list[SourceEvidence],
    summary="Source records behind a facility",
)
def get_facility_sources(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = _get_public_facility(db, facility_id)
    return load_source_evidence(db, [facility.id]).get(facility.id, [])


@router.get(
    "/{facility_id}/assertions",
    response_model=list[AttributeAssertionOut],
    summary="Field-level source claims behind a facility",
)
def get_facility_assertions(
    facility_id: str,
    db: Annotated[Session, Depends(get_db)],
    attribute: str | None = Query(
        None, max_length=80, description="Only return claims for this canonical attribute."
    ),
    limit: int = Query(200, ge=1, le=1000),
):
    facility = _get_public_facility(db, facility_id)
    return load_attribute_assertions(db, facility.id, attribute=attribute, limit=limit)


@router.get(
    "/{facility_id}/accreditations",
    response_model=list[AccreditationOut],
    summary="Dated accreditation assertions",
)
def get_facility_accreditations(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = _get_public_facility(db, facility_id)
    rows = db.scalars(
        select(HealthAccreditation)
        .where(HealthAccreditation.facility_id == facility.id)
        .order_by(HealthAccreditation.valid_until.desc().nullslast())
    ).all()
    return [
        AccreditationOut(
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
            page_reference=row.page_reference,
            source_record_id=row.source_record_id,
        )
        for row in rows
    ]


@router.get(
    "/{facility_id}/history",
    response_model=ChangeListResponse,
    summary="Canonical change timeline",
)
def get_facility_history(
    facility_id: str,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
):
    facility = _get_public_facility(db, facility_id)
    rows = db.scalars(
        select(FacilityChangeEvent)
        .where(FacilityChangeEvent.facility_id == facility.id)
        .order_by(FacilityChangeEvent.changed_at.desc())
        .limit(limit)
    ).all()
    return ChangeListResponse(
        items=[
            {
                "id": row.id,
                "facility_id": row.facility_id,
                "change_type": row.change_type,
                "attribute_name": row.attribute_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "changed_at": row.changed_at,
                "changed_by": row.changed_by,
                "source_record_id": row.source_record_id,
            }
            for row in rows
        ]
    )


@router.get("/{facility_id}/export.csv", include_in_schema=False)
def export_facility_csv(facility_id: str, db: Annotated[Session, Depends(get_db)]):
    facility = _get_public_facility(db, facility_id)
    detail = build_facility_detail(db, facility)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "display_name",
            "facility_type",
            "ownership",
            "psgc_code",
            "latitude",
            "longitude",
            "precision",
            "synthetic",
            "updated_at",
        ]
    )
    writer.writerow(
        [
            sanitize_csv_cell(detail.id),
            sanitize_csv_cell(detail.display_name),
            sanitize_csv_cell(detail.facility_type),
            sanitize_csv_cell(detail.ownership),
            sanitize_csv_cell(detail.location.psgc_code),
            sanitize_csv_cell(detail.location.latitude),
            sanitize_csv_cell(detail.location.longitude),
            sanitize_csv_cell(detail.location.precision),
            sanitize_csv_cell(detail.is_synthetic),
            sanitize_csv_cell(detail.updated_at.isoformat()),
        ]
    )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{facility.id}.csv"'},
    )
