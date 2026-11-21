"""Service helpers: filters.

Split from ``services.py``; the package __init__ re-exports every name.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import (
    Dataset,
    Facility,
    FacilityChangeEvent,
    FacilitySourceLink,
    SourceRecord,
)
from ..publication import (
    latest_public_release_cte,
    public_dataset_condition,
)


def public_source_condition():
    """True when a facility has a rights-cleared link in its current release.

    The evidence set is built once in a CTE instead of probing source links per
    facility. At national scale the correlated form turned an unfiltered
    directory count into a multi-second nested loop.
    """

    latest = latest_public_release_cte()
    public_links = (
        select(FacilitySourceLink.facility_id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(latest, SourceRecord.release_id == latest.c.id)
        .join(Dataset, latest.c.dataset_id == Dataset.id)
        .where(public_dataset_condition())
        .distinct()
        .cte("public_facility_links")
    )
    return Facility.id.in_(select(public_links.c.facility_id))


def public_facility_filter() -> list:
    # Keep the stored publication flag and additionally require current source-link
    # evidence. If rights are withdrawn or a release is quarantined, the record stops
    # being public even before a re-ingestion pass rewrites the cached flag.
    return [
        Facility.publication_status == "public",
        or_(Facility.is_synthetic.is_(True), public_source_condition()),
    ]


def public_facility_index_filter() -> list:
    """Fast publication gate for high-volume browse, map, and aggregate queries.

    ``Facility.publication_status`` is written as ``public`` by canonical ingestion
    only when the record has a rights-cleared current source link. That stored flag
    is indexed, so directory pages and map viewports can use it directly instead of
    rebuilding the national public-evidence set on every request.

    Detail endpoints still call :func:`facility_is_public` and re-validate the live
    source evidence, so a withdrawn source cannot expose a profile. A rights change
    that is not accompanied by the normal ingest/reconciliation pass will be
    reflected on the next publication pass; it is not treated as a second,
    independently mutable publication state.
    """
    return [Facility.publication_status == "public"]


def facility_is_public(session: Session, facility: Facility) -> bool:
    """True when the stored public flag still has current public evidence.

    Detail endpoints receive a facility object loaded by id or slug, so they
    cannot rely on the list query's filter. A facility whose dataset rights were
    withdrawn, or whose newest published release no longer contains it, must
    return the same not-found response as a hidden search result.
    """

    if facility.publication_status != "public":
        return False
    if facility.is_synthetic:
        return True
    return (
        session.scalar(
            select(Facility.id).where(
                Facility.id == facility.id,
                public_source_condition(),
            )
        )
        is not None
    )


def resolve_merged_facility(session: Session, facility: Facility) -> Facility:
    """Follow a merged tombstone to the facility that now holds its evidence.

    A merge retires the duplicate as an internal tombstone but keeps its slug,
    so an old link, export, or bookmark must still resolve. The surviving
    facility is recorded on the ``facility_merged_into`` change event. The walk
    is bounded and stops when a facility is not currently merged, which also
    makes an undone merge resolve to the restored record.
    """

    current = facility
    seen: set[uuid.UUID] = set()
    for _ in range(8):
        if current.record_status != "merged" or current.id in seen:
            return current
        seen.add(current.id)
        event = session.scalars(
            select(FacilityChangeEvent)
            .where(
                FacilityChangeEvent.facility_id == current.id,
                FacilityChangeEvent.change_type == "facility_merged_into",
            )
            .order_by(FacilityChangeEvent.changed_at.desc())
            .limit(1)
        ).first()
        target_id = (event.new_value or {}).get("target_facility_id") if event else None
        if not target_id:
            return current
        try:
            target = session.get(Facility, uuid.UUID(str(target_id)))
        except ValueError:
            return current
        if target is None:
            return current
        current = target
    return current
