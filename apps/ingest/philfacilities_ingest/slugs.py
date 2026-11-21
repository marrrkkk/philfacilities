"""Normalize public facility slugs that still carry a source suffix.

Bulk ingestion originally appended the reporting agency code to every slug
(``-osm``, ``-doh``, ``-nha``, ``-philhealth``). A slug should identify the
facility, not the dataset that first reported it. After duplicates have been
consolidated, this pass removes the suffix and records the old value as an
alias so existing bookmarks and exports continue to resolve.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from philfacilities_api.models import (
    Agency,
    Facility,
    FacilityChangeEvent,
    FacilitySlugAlias,
)
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

MAX_SLUG_LENGTH = 180
DEFAULT_SOURCE_SUFFIXES = {
    "bir",
    "bucor",
    "cainta",
    "ched",
    "deped",
    "doh",
    "doe",
    "dswd",
    "dti",
    "lrta",
    "mandaluyong",
    "mrt3",
    "nbi",
    "nha",
    "nlp",
    "nmis",
    "osm",
    "pagasa",
    "pasay",
    "philhealth",
    "phlpost",
    "ppa",
    "prc",
    "psa",
    "quezon-city",
    "sss",
}


def _suffix_pattern(source_suffixes: set[str]) -> re.Pattern[str] | None:
    suffixes = sorted(
        {value.strip().lower() for value in source_suffixes if value and value.strip()},
        key=len,
        reverse=True,
    )
    if not suffixes:
        return None
    alternatives = "|".join(re.escape(value) for value in suffixes)
    return re.compile(rf"^(?P<base>.+)-(?:{alternatives})(?:-\d+)?$", re.IGNORECASE)


def _unique_slug(base: str, used: set[str]) -> str:
    base = base.strip("-")[:MAX_SLUG_LENGTH].strip("-") or "facility"
    candidate = base
    suffix = 1
    while candidate in used:
        suffix += 1
        tail = f"-{suffix}"
        candidate = f"{base[: MAX_SLUG_LENGTH - len(tail)].strip('-')}{tail}"
    used.add(candidate)
    return candidate


def _name_slug(name: str) -> str:
    """Return the slug an unmodified display name would produce."""

    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:MAX_SLUG_LENGTH]


def _suffix_is_part_of_name(old_slug: str, display_name: str) -> bool:
    """Whether the trailing agency-like token is actually part of the name.

    A facility called ``Maydolong NAS (Under CHED)`` produced the slug
    ``maydolong-nas-under-ched``. A blanket suffix rule would strip ``-ched``
    and rename the place to something it is not. Only strip when the name
    itself does not account for the whole slug.
    """

    name_slug = _name_slug(display_name)
    if not name_slug:
        return False
    if old_slug == name_slug:
        return True
    return re.fullmatch(rf"{re.escape(name_slug)}-\d+", old_slug) is not None


def normalize_facility_slugs(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 50_000,
    facility_type: str | None = None,
    source_suffixes: set[str] | None = None,
    example_limit: int = 20,
    batch_size: int = 5_000,
    commit_every: int | None = None,
) -> dict[str, Any]:
    """Remove source suffixes from current facility slugs.

    Only facilities whose slug matches a known source suffix are touched.
    Merged tombstones keep their slug because that slug is the redirect key for
    an old link. The old value of every renamed slug is written to
    ``core.facility_slug_aliases`` and a change event records the rename.

    ``commit_every`` commits completed renames in batches so a large pass keeps
    its progress if it is interrupted.
    """

    if source_suffixes is None:
        source_suffixes = set(session.scalars(select(Agency.short_code)).all())
        source_suffixes.update(DEFAULT_SOURCE_SUFFIXES)
    pattern = _suffix_pattern(source_suffixes)
    stats: dict[str, Any] = {
        "facilities_scanned": 0,
        "with_source_suffix": 0,
        "renamed": 0,
        "would_rename": 0,
        "skipped_collision": 0,
        "skipped_name": 0,
        "skipped_limit": 0,
        "aliases_created": 0,
        "dry_run": dry_run,
        "source_suffixes": sorted(source_suffixes),
        "examples": [],
    }
    if pattern is None:
        return stats

    used = set(session.scalars(select(Facility.slug)).all())
    used.update(session.scalars(select(FacilitySlugAlias.slug)).all())

    query = (
        select(
            Facility.slug,
            Facility.display_name,
            Facility.facility_type,
            Facility.id,
        )
        .where(Facility.record_status != "merged", Facility.slug.is_not(None))
        .order_by(Facility.created_at, Facility.id)
    )
    if facility_type is not None:
        query = query.where(Facility.facility_type == facility_type)

    pending_aliases: list[dict[str, Any]] = []
    pending_events: list[dict[str, Any]] = []
    renamed = 0
    uncommitted = 0

    # Stream columns, not ORM instances: a 100k-facility pass must not grow the
    # identity map for the whole run.
    for old_slug, display_name, facility_type_value, facility_id in session.execute(
        query
    ).yield_per(1_000):
        stats["facilities_scanned"] += 1
        old_slug = old_slug or ""
        match = pattern.match(old_slug)
        if match is None:
            continue
        stats["with_source_suffix"] += 1
        if _suffix_is_part_of_name(old_slug, display_name):
            stats["skipped_name"] += 1
            continue
        base = match.group("base")
        candidate = _unique_slug(base, used)
        if candidate == old_slug:
            continue
        if dry_run:
            stats["would_rename"] += 1
        else:
            if renamed >= limit:
                stats["skipped_limit"] += 1
                continue
            session.execute(
                update(Facility).where(Facility.id == facility_id).values(slug=candidate)
            )
            pending_aliases.append(
                {
                    "id": uuid.uuid4(),
                    "slug": old_slug,
                    "facility_id": facility_id,
                }
            )
            pending_events.append(
                {
                    "id": uuid.uuid4(),
                    "facility_id": facility_id,
                    "change_type": "facility_slug_normalized",
                    "attribute_name": "slug",
                    "old_value": old_slug,
                    "new_value": candidate,
                    "changed_by": "system:slug-normalization",
                }
            )
            renamed += 1
            stats["renamed"] = renamed
            if len(pending_aliases) >= batch_size:
                session.execute(insert(FacilitySlugAlias), pending_aliases)
                session.execute(insert(FacilityChangeEvent), pending_events)
                stats["aliases_created"] += len(pending_aliases)
                uncommitted += len(pending_aliases)
                pending_aliases.clear()
                pending_events.clear()
                if commit_every is not None and commit_every > 0 and uncommitted >= commit_every:
                    session.commit()
                    session.expunge_all()
                    uncommitted = 0
            if renamed >= limit:
                stats["skipped_limit"] += 1
        if len(stats["examples"]) < example_limit:
            stats["examples"].append(
                {
                    "facility_id": str(facility_id),
                    "name": display_name,
                    "facility_type": facility_type_value,
                    "old_slug": old_slug,
                    "new_slug": candidate,
                }
            )

    if not dry_run and pending_aliases:
        session.execute(insert(FacilitySlugAlias), pending_aliases)
        session.execute(insert(FacilityChangeEvent), pending_events)
        stats["aliases_created"] += len(pending_aliases)
    return stats


_NUMERIC_SLUG = re.compile(r"^(?P<base>.+)-(?P<index>\d+)$")


def _merged_target(session: Session, tombstone_id: uuid.UUID) -> uuid.UUID | None:
    """Return the facility that now holds a merged tombstone's evidence."""

    event = session.scalars(
        select(FacilityChangeEvent)
        .where(
            FacilityChangeEvent.facility_id == tombstone_id,
            FacilityChangeEvent.change_type == "facility_merged_into",
        )
        .order_by(FacilityChangeEvent.changed_at.desc())
        .limit(1)
    ).first()
    target = (event.new_value or {}).get("target_facility_id") if event else None
    if not target:
        return None
    try:
        return uuid.UUID(str(target))
    except ValueError:
        return None


def consolidate_numeric_slugs(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 50_000,
    facility_type: str | None = None,
    example_limit: int = 20,
    commit_every: int | None = None,
) -> dict[str, Any]:
    """Give a consolidated facility its clean, unnumbered slug.

    Identically named rows received ``-2``, ``-3`` … slugs at ingest time. After
    consolidation the base slug can be held by a merged tombstone that redirects
    to the survivor. This pass frees that base slug, moves it to the survivor,
    and keeps the numbered slug as a bookmark alias. Genuine same-name
    facilities that are still separate are never renamed.
    """

    stats: dict[str, Any] = {
        "facilities_scanned": 0,
        "with_numeric_suffix": 0,
        "renamed": 0,
        "would_rename": 0,
        "skipped_name": 0,
        "skipped_collision": 0,
        "skipped_limit": 0,
        "aliases_created": 0,
        "dry_run": dry_run,
        "examples": [],
    }
    used = set(session.scalars(select(Facility.slug)).all())
    query = (
        select(Facility.id, Facility.slug, Facility.display_name)
        .where(Facility.record_status != "merged", Facility.slug.is_not(None))
        .order_by(Facility.created_at, Facility.id)
    )
    if facility_type is not None:
        query = query.where(Facility.facility_type == facility_type)

    renamed = 0
    for facility_id, old_slug, display_name in session.execute(query).yield_per(1_000):
        stats["facilities_scanned"] += 1
        match = _NUMERIC_SLUG.match(old_slug)
        if match is None:
            continue
        stats["with_numeric_suffix"] += 1
        base = match.group("base")
        # A name that legitimately ends in a number keeps its slug.
        if _name_slug(display_name) != base:
            stats["skipped_name"] += 1
            continue
        holder = session.scalars(select(Facility).where(Facility.slug == base)).first()
        if holder is not None and holder.id != facility_id:
            if (
                holder.record_status != "merged"
                or _merged_target(session, holder.id) != facility_id
            ):
                stats["skipped_collision"] += 1
                continue
        elif (
            base in used
            or session.scalars(
                select(FacilitySlugAlias.id).where(FacilitySlugAlias.slug == base)
            ).first()
        ):
            stats["skipped_collision"] += 1
            continue

        if dry_run:
            stats["would_rename"] += 1
        else:
            if renamed >= limit:
                stats["skipped_limit"] += 1
                continue
            if holder is not None and holder.id != facility_id:
                reserved = f"merged-{holder.id}"[:MAX_SLUG_LENGTH]
                while reserved in used:
                    reserved = f"{reserved[: MAX_SLUG_LENGTH - 9]}-{uuid.uuid4().hex[:8]}"
                session.execute(
                    update(Facility).where(Facility.id == holder.id).values(slug=reserved)
                )
                session.execute(
                    insert(FacilityChangeEvent).values(
                        id=uuid.uuid4(),
                        facility_id=holder.id,
                        change_type="facility_slug_normalized",
                        attribute_name="slug",
                        old_value=base,
                        new_value=reserved,
                        changed_by="system:slug-consolidation",
                    )
                )
                used.discard(base)
                used.add(reserved)
            session.execute(update(Facility).where(Facility.id == facility_id).values(slug=base))
            session.execute(delete(FacilitySlugAlias).where(FacilitySlugAlias.slug == old_slug))
            session.execute(
                insert(FacilitySlugAlias).values(
                    id=uuid.uuid4(), slug=old_slug, facility_id=facility_id
                )
            )
            session.execute(
                insert(FacilityChangeEvent).values(
                    id=uuid.uuid4(),
                    facility_id=facility_id,
                    change_type="facility_slug_normalized",
                    attribute_name="slug",
                    old_value=old_slug,
                    new_value=base,
                    changed_by="system:slug-consolidation",
                )
            )
            used.discard(old_slug)
            used.add(base)
            renamed += 1
            stats["renamed"] = renamed
            stats["aliases_created"] += 1
            if commit_every is not None and commit_every > 0 and renamed % commit_every == 0:
                session.commit()
        if len(stats["examples"]) < example_limit:
            stats["examples"].append(
                {
                    "facility_id": str(facility_id),
                    "name": display_name,
                    "old_slug": old_slug,
                    "new_slug": base,
                }
            )
    return stats
