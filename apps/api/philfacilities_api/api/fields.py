"""Field-coverage discovery for API clients.

Counts come from the refresh-after-publication materialized view when present,
with an on-demand fallback for databases that have not run migration 0026.
Both paths derive their field list from the same declarative mapping and apply
the same publication gate. The endpoint is read-only and ETag-cached.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..db import get_db
from ..middleware import conditional_json
from ..schemas import FieldCoverageResponse
from ..services import collect_field_coverage
from ..services.coverage_mv import (
    MV_NAME,
    coverage_mv_fresh,
    read_coverage_mv,
    refresh_coverage_mv,
)

router = APIRouter(tags=["facilities"])


def _coverage_payload(db: Session, by_category: bool) -> dict:
    """Prefer the projection; fall back to on-demand counts if it is absent."""

    try:
        if not coverage_mv_fresh(db):
            # A publication without the ingest hook would leave a stale view.
            # Refresh defensively so the API never reports wrong counts.
            refresh_coverage_mv(db, concurrent=True)
        return read_coverage_mv(db, by_category=by_category)
    except OperationalError as exc:
        # UndefinedTable (or a related projection error) means migration 0026
        # has not been applied. Roll back the failed statement and keep serving
        # the original on-demand computation.
        db.rollback()
        if "does not exist" not in str(exc).lower() and MV_NAME.split(".")[-1] not in str(exc):
            raise
        return collect_field_coverage(db, by_category=by_category)


@router.get(
    "/fields",
    response_model=FieldCoverageResponse,
    summary="Public field coverage and null/empty semantics",
    description=(
        "Reports how many public facilities have an established value for each "
        "canonical field. Every entry carries its own scope and denominator, and "
        "all counts use the same publication gate as GET /v1/facilities. Pass "
        "by_category=true to include per-category denominators. Counts are read "
        "from a materialized view refreshed after publication and cached for one "
        "hour; databases without that view compute the same figures on demand."
    ),
)
def get_field_coverage(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    by_category: bool = Query(
        False, description="Include per-category populated/total denominators."
    ),
):
    return conditional_json(request, _coverage_payload(db, by_category), max_age=3600)
