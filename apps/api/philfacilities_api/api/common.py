from __future__ import annotations

import contextlib
import uuid
from typing import Literal

from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Facility, FacilitySlugAlias
from ..pagination import decode_cursor, encode_cursor
from ..schemas import FacilityListResponse
from ..services import build_summaries, facility_is_public, resolve_merged_facility

DetailView = Literal["full", "compact"]
DetailShape = Literal["wrapper", "detail"]
INCLUDE_SECTIONS = frozenset({"sources", "assertions", "domain"})
SECTION_FIELDS = {
    "sources": ("sources",),
    "assertions": ("assertions",),
    "domain": ("school", "health", "utility", "accreditations", "licenses", "resources"),
}
EXTENDED_FIELDS = frozenset(field for fields in SECTION_FIELDS.values() for field in fields)


def _json_value(value):
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _compact_payload(model, sections: set[str]) -> dict:
    """Keep all twelve compact fields (including nulls), add only asked-for sections."""

    payload = model.model_dump(mode="json", exclude=EXTENDED_FIELDS)
    for section in sorted(sections):
        for field in SECTION_FIELDS[section]:
            value = getattr(model, field)
            if value is None:
                continue  # an unestablished section is absent, never a fake []
            payload[field] = _json_value(value)
    return payload


def compact_extended_response(model, sections: set[str]) -> JSONResponse:
    """Serialize opt-in sections, omitting unrequested ones entirely.

    A typed extended model is used for the OpenAPI contract, but FastAPI's
    union serializer would otherwise emit every optional section as ``null``.
    Explicit JSON keeps `include=` additive and honest without dropping nulls
    from the underlying compact card.
    """

    return JSONResponse(content=_compact_payload(model, sections))


def compact_wrapper_response(model, sections: set[str], **collections) -> JSONResponse:
    """Serialize a legacy wrapper whose facility is an extended compact card."""

    payload = {"facility": _compact_payload(model, sections)}
    for key, values in collections.items():
        payload[key] = _json_value(values)
    return JSONResponse(content=payload)


def parse_include(include: str | None) -> set[str]:
    """Validate the additive ``include=`` CSV used by domain detail endpoints."""

    if not include or not include.strip():
        return set()
    sections = {part.strip() for part in include.split(",") if part.strip()}
    unknown = sections - set(INCLUDE_SECTIONS)
    if unknown:
        raise ApiError(
            400,
            "invalid_include",
            "include accepts sources, assertions, and domain.",
            {"unknown": sorted(unknown)},
        )
    return sections


def get_public_facility(db: Session, identifier: str) -> Facility:
    facility = None
    with contextlib.suppress(ValueError):
        facility = db.get(Facility, uuid.UUID(identifier))
    if facility is None:
        facility = db.scalars(select(Facility).where(Facility.slug == identifier)).first()
    if facility is None:
        # Slugs are renamed when source-derived suffixes are removed. The alias
        # keeps old bookmarks and exports resolving after that cleanup.
        alias = db.scalars(
            select(FacilitySlugAlias).where(FacilitySlugAlias.slug == identifier)
        ).first()
        if alias is not None:
            facility = db.get(Facility, alias.facility_id)
    if facility is not None:
        # A merged duplicate keeps its slug as an alias; follow it so old links
        # and exports keep resolving to the facility that holds the evidence.
        facility = resolve_merged_facility(db, facility)
    if facility is None or not facility_is_public(db, facility):
        raise ApiError(404, "facility_not_found", "No published facility exists with that ID.")
    return facility


def paginated_facilities(
    db: Session,
    conditions: list,
    limit: int,
    cursor: str | None,
    with_total: bool = True,
) -> FacilityListResponse:
    total = (
        db.scalar(select(func.count()).select_from(Facility).where(*conditions)) or 0
        if with_total
        else None
    )
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
