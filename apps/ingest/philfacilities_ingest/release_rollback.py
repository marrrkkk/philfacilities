"""Release-scoped snapshots and authorised rollback.

Ingestion updates canonical facilities in place. A source release can therefore
change a facility's name, class, publication state, location and child evidence
without an earlier copy being retained. This module records the pre-release
aggregate once per release/facility and restores it only when no later release
has touched the same facility. Raw source records and the original release are
never deleted by a rollback; the release is marked ``rolled_back`` and
``quarantined``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from philfacilities_api.models import (
    AttributeAssertion,
    Dataset,
    EnrollmentObservation,
    Facility,
    FacilityChangeEvent,
    FacilityFunction,
    FacilityLocation,
    FacilityRelationship,
    FacilityRole,
    FacilityService,
    FacilitySourceLink,
    HealthAccreditation,
    HealthLicense,
    HealthProfile,
    Release,
    ReleaseFacilitySnapshot,
    ResourceObservation,
    SchoolProfile,
    SourceRecord,
)
from philfacilities_api.rights import PUBLICATION_QUARANTINED
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

CHILD_MODELS = (
    FacilitySourceLink,
    FacilityLocation,
    AttributeAssertion,
    FacilityFunction,
    FacilityService,
    FacilityRole,
    FacilityRelationship,
    SchoolProfile,
    EnrollmentObservation,
    ResourceObservation,
    HealthProfile,
    HealthLicense,
    HealthAccreditation,
)


class ReleaseRollbackError(Exception):
    """Raised when a release cannot be rolled back safely."""


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, dict)):
        return value
    try:
        return to_shape(value).wkt
    except Exception:
        return str(value)


def _deserialize_value(column, value: Any) -> Any:
    if value is None:
        return None
    type_name = type(column.type).__name__
    if type_name in {"DateTime", "TIMESTAMP"}:
        return datetime.fromisoformat(value)
    if type_name == "Date":
        return date.fromisoformat(value)
    if type_name in {"Numeric", "DECIMAL"}:
        return Decimal(str(value))
    if type_name in {"Integer", "INTEGER", "BigInteger"}:
        return int(value)
    if type_name in {"Float", "FLOAT", "REAL"}:
        return float(value)
    if type_name in {"Boolean", "BOOLEAN"}:
        return bool(value)
    if type_name in {"UUID"}:
        return uuid.UUID(str(value))
    return value


def _row_to_dict(row: Any, model: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name == "geom":
            geom = getattr(row, "geom", None)
            payload["geom_wkt"] = to_shape(geom).wkt if geom is not None else None
            continue
        payload[column.name] = _serialize_value(getattr(row, column.name))
    return payload


def _children(session: Session, facility_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for model in CHILD_MODELS:
        if model is FacilityRelationship:
            rows = session.scalars(
                select(FacilityRelationship).where(
                    or_(
                        FacilityRelationship.subject_facility_id == facility_id,
                        FacilityRelationship.object_facility_id == facility_id,
                    )
                )
            ).all()
        else:
            rows = session.scalars(select(model).where(model.facility_id == facility_id)).all()
        result[model.__tablename__] = [_row_to_dict(row, model) for row in rows]
    return result


def _facility_state(session: Session, facility: Facility) -> dict[str, Any]:
    return {
        "facility": _row_to_dict(facility, Facility),
        "children": _children(session, facility.id),
    }


def capture_facility_snapshot(
    session: Session,
    *,
    release: Release,
    facility: Facility,
    was_created: bool,
) -> ReleaseFacilitySnapshot:
    """Record the pre-release state once, before the release first mutates it."""

    # Sessions in this project use autoflush=False, so a pending snapshot from an
    # earlier row for the same facility is not visible to the query below. Check
    # session.new first to keep repeated captures idempotent and avoid violating
    # the (release_id, facility_id) uniqueness constraint at commit time.
    for pending in session.new:
        if (
            isinstance(pending, ReleaseFacilitySnapshot)
            and pending.release_id == release.id
            and pending.facility_id == facility.id
        ):
            return pending

    existing = session.scalars(
        select(ReleaseFacilitySnapshot).where(
            ReleaseFacilitySnapshot.release_id == release.id,
            ReleaseFacilitySnapshot.facility_id == facility.id,
        )
    ).first()
    if existing is not None:
        return existing
    snapshot = ReleaseFacilitySnapshot(
        release_id=release.id,
        facility_id=facility.id,
        was_created=was_created,
        state=None if was_created else _facility_state(session, facility),
    )
    session.add(snapshot)
    return snapshot


def _delete_children(session: Session, facility_id: uuid.UUID) -> None:
    for model in CHILD_MODELS:
        if model is FacilityRelationship:
            session.execute(
                delete(FacilityRelationship).where(
                    or_(
                        FacilityRelationship.subject_facility_id == facility_id,
                        FacilityRelationship.object_facility_id == facility_id,
                    )
                )
            )
        else:
            session.execute(delete(model).where(model.facility_id == facility_id))


def _restore_row(model: Any, payload: dict[str, Any]) -> Any:
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name == "geom":
            wkt = payload.get("geom_wkt")
            values["geom"] = WKTElement(wkt, srid=4326) if wkt else None
            continue
        values[column.name] = _deserialize_value(column, payload.get(column.name))
    return model(**values)


def _restore_facility(
    session: Session, *, facility: Facility, state: dict[str, Any], reviewer: str, release: Release
) -> None:
    facility_payload = state.get("facility") or {}
    for column in Facility.__table__.columns:
        if column.name == "id":
            continue
        if column.name not in facility_payload:
            continue
        setattr(facility, column.name, _deserialize_value(column, facility_payload[column.name]))
    facility.updated_at = datetime.now(UTC)
    _delete_children(session, facility.id)
    for model in CHILD_MODELS:
        for row in (state.get("children") or {}).get(model.__tablename__, []):
            session.add(_restore_row(model, row))
    release_label = release.source_release_label
    session.add(
        FacilityChangeEvent(
            facility_id=facility.id,
            change_type="release_rollback",
            attribute_name=None,
            old_value=None,
            new_value={
                "release": release_label,
                "restored_from_snapshot": True,
                "reviewer": reviewer,
            },
            changed_by=f"release-rollback:{release_label}",
        )
    )


def _later_release(session: Session, release: Release) -> Release | None:
    if release.processed_at is None:
        return None
    return session.scalars(
        select(Release)
        .where(
            Release.dataset_id == release.dataset_id,
            Release.id != release.id,
            Release.processed_at > release.processed_at,
        )
        .order_by(Release.processed_at.desc())
        .limit(1)
    ).first()


def _later_facility_evidence(
    session: Session, *, facility_id: uuid.UUID, release: Release
) -> Release | None:
    if release.processed_at is None:
        return None
    return session.scalars(
        select(Release)
        .join(SourceRecord, SourceRecord.release_id == Release.id)
        .join(FacilitySourceLink, FacilitySourceLink.source_record_id == SourceRecord.id)
        .where(
            FacilitySourceLink.facility_id == facility_id,
            Release.id != release.id,
            Release.processed_at > release.processed_at,
        )
        .limit(1)
    ).first()


def rollback_release(
    session: Session,
    *,
    dataset_slug: str,
    release_label: str | None = None,
    reviewer: str,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Restore canonical state captured before an ingested release.

    The rollback is intentionally conservative: it refuses when a later release
    for the same dataset exists, when a facility has been changed after the
    release, or when another release has since linked evidence to the facility.
    """

    # Snapshots are captured by the pipeline without an intermediate flush per
    # facility. Persist any pending snapshot before reading them back; sessions use
    # autoflush=False so an explicit flush is required.
    session.flush()

    dataset = session.scalars(select(Dataset).where(Dataset.slug == dataset_slug)).first()
    if dataset is None:
        raise ReleaseRollbackError(f"Unknown dataset slug {dataset_slug!r}.")

    query = select(Release).where(Release.dataset_id == dataset.id)
    if release_label:
        query = query.where(Release.source_release_label == release_label)
    else:
        query = query.order_by(Release.processed_at.desc()).limit(1)
    release = session.scalars(query).first()
    if release is None:
        label = release_label or "(latest)"
        raise ReleaseRollbackError(f"Unknown release {label!r} for dataset {dataset_slug!r}.")
    if release.ingestion_status != "published":
        raise ReleaseRollbackError(
            f"Release {release.source_release_label!r} is {release.ingestion_status!r}, "
            "not a published release."
        )
    if release.processed_at is None:
        raise ReleaseRollbackError("Release has no processed_at timestamp; refusing rollback.")
    later = _later_release(session, release)
    if later is not None:
        raise ReleaseRollbackError(
            f"Release {later.source_release_label!r} was processed after "
            f"{release.source_release_label!r}; roll back the newest release first."
        )

    snapshots = session.scalars(
        select(ReleaseFacilitySnapshot).where(
            ReleaseFacilitySnapshot.release_id == release.id,
            ReleaseFacilitySnapshot.restored_at.is_(None),
        )
    ).all()
    if not snapshots:
        raise ReleaseRollbackError(
            f"Release {release.source_release_label!r} has no unrestored facility snapshots."
        )

    restore_count = 0
    delete_count = 0
    skipped = 0
    for snapshot in snapshots:
        if snapshot.facility_id is None:
            skipped += 1
            continue
        facility = session.get(Facility, snapshot.facility_id)
        if facility is None:
            skipped += 1
            continue
        if facility.updated_at > release.processed_at:
            raise ReleaseRollbackError(
                f"Facility {facility.id} changed after release "
                f"{release.source_release_label!r}; refusing to overwrite newer evidence."
            )
        later_evidence = _later_facility_evidence(session, facility_id=facility.id, release=release)
        if later_evidence is not None:
            raise ReleaseRollbackError(
                f"Facility {facility.id} has evidence from later release "
                f"{later_evidence.source_release_label!r}; refusing rollback."
            )
        if dry_run:
            if snapshot.was_created:
                delete_count += 1
            else:
                restore_count += 1
            continue
        if snapshot.was_created:
            snapshot.restored_at = datetime.now(UTC)
            snapshot.restored_by = reviewer
            snapshot.restore_note = note
            snapshot.facility_id = None
            session.delete(facility)
            delete_count += 1
        else:
            _restore_facility(
                session,
                facility=facility,
                state=snapshot.state or {},
                reviewer=reviewer,
                release=release,
            )
            snapshot.restored_at = datetime.now(UTC)
            snapshot.restored_by = reviewer
            snapshot.restore_note = note
            restore_count += 1

    if not dry_run:
        release.ingestion_status = "rolled_back"
        release.publication_status = PUBLICATION_QUARANTINED
        rollback_note = (
            f"Rolled back by {reviewer} on {datetime.now(UTC).isoformat()}: "
            f"{restore_count} facilities restored, {delete_count} created facilities removed."
        )
        if note:
            rollback_note = f"{rollback_note} {note}"
        release.notes = (
            f"{release.notes}\n{rollback_note}".strip() if release.notes else rollback_note
        )
        session.flush()

    return {
        "dataset": dataset.slug,
        "release_label": release.source_release_label,
        "dry_run": dry_run,
        "snapshots": len(snapshots),
        "restored": restore_count,
        "deleted": delete_count,
        "skipped": skipped,
        "reviewer": reviewer,
    }
