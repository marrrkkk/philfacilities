"""API routes split from the original sources router: changes.

Decorators and route order are preserved; ``sources_common`` owns the shared
``APIRouter`` so ``/v1`` path ordering and OpenAPI output stay identical.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..models import (
    Facility,
    FacilityChangeEvent,
)
from ..schemas import (
    ChangeListResponse,
)
from ..services import public_facility_filter
from .sources_common import _MATCH_STATUSES as _MATCH_STATUSES
from .sources_common import router as router
from .sources_common import settings as settings


@router.get("/changes", response_model=ChangeListResponse, summary="Canonical change feed")
def changes(
    db: Annotated[Session, Depends(get_db)],
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
):
    query = (
        select(FacilityChangeEvent)
        .join(Facility, Facility.id == FacilityChangeEvent.facility_id)
        .where(*public_facility_filter())
        .order_by(FacilityChangeEvent.changed_at.desc(), FacilityChangeEvent.id.desc())
    )
    if since:
        query = query.where(FacilityChangeEvent.changed_at >= since)
    if cursor:
        changed_at, event_id = _decode_event_cursor(cursor)
        query = query.where(
            or_(
                FacilityChangeEvent.changed_at < changed_at,
                and_(
                    FacilityChangeEvent.changed_at == changed_at,
                    FacilityChangeEvent.id < event_id,
                ),
            )
        )
    rows = list(db.scalars(query.limit(limit + 1)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
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
        ],
        next_cursor=(
            _encode_event_cursor(rows[-1].changed_at, rows[-1].id) if has_more and rows else None
        ),
        has_more=has_more,
    )


def _encode_event_cursor(changed_at: datetime, event_id: uuid.UUID) -> str:
    import base64
    import json

    payload = {"changed_at": changed_at.astimezone(UTC).isoformat(), "id": str(event_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_event_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    import base64
    import json

    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["changed_at"]), uuid.UUID(payload["id"])
    except Exception as exc:
        raise ApiError(400, "invalid_cursor", "The pagination cursor is invalid.") from exc
