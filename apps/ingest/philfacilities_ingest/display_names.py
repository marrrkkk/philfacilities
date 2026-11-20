"""Normalize source display names that are published entirely in capitals.

Many agency exports write a facility name in all caps. That style makes the
directory and map labels hard to read and is not the way the institution names
itself. The canonical ``display_name`` is therefore title-cased, while the
source's original spelling remains available through ``official_name``, the
source payload, and the field assertions.

The pass is intentionally conservative: mixed-case names are never touched,
and abbreviations, Roman numerals, ordinals, single letters and consonant-only
initialisms keep their uppercase form.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from philfacilities_api.models import Facility, FacilityChangeEvent
from sqlalchemy import bindparam, func, insert, select, update
from sqlalchemy.orm import Session

from .identity import normalize_display_name

CHANGED_BY = "system:display-name-normalization"


def normalize_facility_display_names(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 100_000,
    example_limit: int = 20,
    batch_size: int = 1_000,
    commit_every: int | None = None,
) -> dict[str, Any]:
    """Title-case uppercase display names and record an audit event per change.

    ``commit_every`` commits completed batches so a large backfill keeps its
    progress if interrupted. Merged tombstones are included: if a merge is ever
    undone, the restored facility should already have a readable name.
    """

    stats: dict[str, Any] = {
        "facilities_scanned": 0,
        "normalizable": 0,
        "would_normalize": 0,
        "normalized": 0,
        "skipped_abbreviation_only": 0,
        "skipped_limit": 0,
        "dry_run": dry_run,
        "examples": [],
    }
    query = (
        select(Facility.id, Facility.display_name, Facility.facility_type)
        .where(
            Facility.display_name.is_not(None),
            Facility.display_name == func.upper(Facility.display_name),
        )
        .order_by(Facility.created_at, Facility.id)
    )

    now = datetime.now(UTC)
    pending_updates: list[dict[str, Any]] = []
    pending_events: list[dict[str, Any]] = []
    normalized = 0
    uncommitted = 0

    def flush_batch() -> None:
        nonlocal uncommitted
        if not pending_updates:
            return
        table = Facility.__table__
        session.execute(
            update(table)
            .where(table.c.id == bindparam("facility_id"))
            .values(
                display_name=bindparam("display_name"),
                updated_at=bindparam("updated_at"),
            ),
            pending_updates,
        )
        session.execute(insert(FacilityChangeEvent), pending_events)
        uncommitted += len(pending_updates)
        pending_updates.clear()
        pending_events.clear()

    for facility_id, old_name, facility_type in session.execute(query).yield_per(1_000):
        stats["facilities_scanned"] += 1
        new_name = normalize_display_name(old_name)
        if not new_name or new_name == old_name:
            stats["skipped_abbreviation_only"] += 1
            continue
        stats["normalizable"] += 1
        if dry_run:
            stats["would_normalize"] += 1
        else:
            if normalized >= limit:
                stats["skipped_limit"] += 1
                continue
            pending_updates.append(
                {
                    "facility_id": facility_id,
                    "display_name": new_name,
                    "updated_at": now,
                }
            )
            pending_events.append(
                {
                    "id": uuid.uuid4(),
                    "facility_id": facility_id,
                    "change_type": "display_name_normalized",
                    "attribute_name": "display_name",
                    "old_value": {"value": old_name},
                    "new_value": {"value": new_name},
                    "changed_by": CHANGED_BY,
                }
            )
            normalized += 1
            stats["normalized"] = normalized
            if len(pending_updates) >= batch_size:
                flush_batch()
                if commit_every is not None and commit_every > 0 and uncommitted >= commit_every:
                    session.commit()
                    uncommitted = 0
        if len(stats["examples"]) < example_limit:
            stats["examples"].append(
                {
                    "facility_id": str(facility_id),
                    "facility_type": facility_type,
                    "old_name": old_name,
                    "new_name": new_name,
                }
            )

    if not dry_run:
        flush_batch()
        if normalized:
            # The bulk update bypasses the identity map. Expire loaded rows so
            # a caller in the same session sees the new names.
            session.expire_all()
    return stats
