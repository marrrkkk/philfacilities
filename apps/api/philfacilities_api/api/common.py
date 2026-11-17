from __future__ import annotations

import contextlib
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Facility
from ..pagination import decode_cursor, encode_cursor
from ..schemas import FacilityListResponse
from ..services import build_summaries, facility_is_public


def get_public_facility(db: Session, identifier: str) -> Facility:
    facility = None
    with contextlib.suppress(ValueError):
        facility = db.get(Facility, uuid.UUID(identifier))
    if facility is None:
        facility = db.scalars(select(Facility).where(Facility.slug == identifier)).first()
    if facility is None or not facility_is_public(db, facility):
        raise ApiError(404, "facility_not_found", "No published facility exists with that ID.")
    return facility


def paginated_facilities(
    db: Session,
    conditions: list,
    limit: int,
    cursor: str | None,
) -> FacilityListResponse:
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
    rows = list(
        db.scalars(
            query.order_by(Facility.updated_at.desc(), Facility.id.desc()).limit(limit + 1)
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    summaries = build_summaries(db, rows)
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
        limit=limit,
    )
