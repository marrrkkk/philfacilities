"""Public slug normalization after duplicate consolidation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from philfacilities_api.models import (
    Agency,
    Facility,
    FacilityChangeEvent,
    FacilitySlugAlias,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _facility(session, name: str, slug: str) -> Facility:
    facility = Facility(
        display_name=name,
        official_name=name,
        facility_type="health_facility",
        slug=slug,
        facility_kind="facility",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        ownership_type="LOCAL_GOVERNMENT",
        operator_type="GOVERNMENT",
        public_access_class="PUBLIC",
        record_status="active",
        publication_status="public",
        is_synthetic=False,
        created_at=datetime.now(UTC),
    )
    session.add(facility)
    session.flush()
    return facility


def test_source_suffix_is_removed_and_old_slug_becomes_alias(db_session) -> None:
    from philfacilities_ingest.slugs import normalize_facility_slugs

    suffix = uuid.uuid4().hex[:10]
    agency = Agency(
        name=f"OSM test {suffix}",
        short_code=f"osm{suffix}",
        publisher_type="community",
    )
    db_session.add(agency)
    facility = _facility(
        db_session,
        f"Alpha Clinic {suffix}",
        f"alpha-clinic-{suffix}-osm{suffix}",
    )

    dry_run = normalize_facility_slugs(
        db_session,
        dry_run=True,
        source_suffixes={f"osm{suffix}"},
    )
    assert dry_run["would_rename"] == 1
    assert facility.slug == f"alpha-clinic-{suffix}-osm{suffix}"

    stats = normalize_facility_slugs(
        db_session,
        dry_run=False,
        source_suffixes={f"osm{suffix}"},
    )
    db_session.flush()

    assert stats["renamed"] == 1
    assert stats["aliases_created"] == 1
    assert facility.slug == f"alpha-clinic-{suffix}"
    alias = db_session.scalars(
        select(FacilitySlugAlias).where(
            FacilitySlugAlias.slug == f"alpha-clinic-{suffix}-osm{suffix}"
        )
    ).one()
    assert alias.facility_id == facility.id
    event = db_session.scalars(
        select(FacilityChangeEvent).where(
            FacilityChangeEvent.facility_id == facility.id,
            FacilityChangeEvent.change_type == "facility_slug_normalized",
        )
    ).one()
    assert event.old_value == f"alpha-clinic-{suffix}-osm{suffix}"
    assert event.new_value == f"alpha-clinic-{suffix}"


def test_clean_slug_collision_gets_numeric_suffix(db_session) -> None:
    from philfacilities_ingest.slugs import normalize_facility_slugs

    suffix = uuid.uuid4().hex[:10]
    db_session.add(
        Agency(name=f"DOH test {suffix}", short_code=f"doh{suffix}", publisher_type="government")
    )
    existing = _facility(db_session, f"Shared Name {suffix}", f"shared-name-{suffix}")
    renamed = _facility(db_session, f"Shared Name {suffix}", f"shared-name-{suffix}-doh{suffix}")

    stats = normalize_facility_slugs(
        db_session,
        dry_run=False,
        source_suffixes={f"doh{suffix}"},
    )
    db_session.flush()

    assert stats["renamed"] == 1
    assert existing.slug == f"shared-name-{suffix}"
    assert renamed.slug == f"shared-name-{suffix}-2"


def test_merged_tombstone_keeps_its_slug(db_session) -> None:
    from philfacilities_ingest.slugs import normalize_facility_slugs

    suffix = uuid.uuid4().hex[:10]
    db_session.add(
        Agency(name=f"NHA test {suffix}", short_code=f"nha{suffix}", publisher_type="government")
    )
    tombstone = _facility(db_session, f"Retired {suffix}", f"retired-{suffix}-nha{suffix}")
    tombstone.record_status = "merged"
    db_session.flush()

    stats = normalize_facility_slugs(
        db_session,
        dry_run=False,
        source_suffixes={f"nha{suffix}"},
    )
    db_session.flush()

    assert stats["renamed"] == 0
    assert tombstone.slug == f"retired-{suffix}-nha{suffix}"


def test_consolidated_facility_takes_the_clean_slug_from_its_tombstone(db_session) -> None:
    from philfacilities_ingest.slugs import consolidate_numeric_slugs

    suffix = uuid.uuid4().hex[:10]
    name = f"Consolidated Institute {suffix}"
    base = f"consolidated-institute-{suffix}"
    survivor = _facility(db_session, name, f"{base}-3")
    tombstone = _facility(db_session, name, base)
    tombstone.record_status = "merged"
    db_session.add(
        FacilityChangeEvent(
            id=uuid.uuid4(),
            facility_id=tombstone.id,
            change_type="facility_merged_into",
            new_value={"target_facility_id": str(survivor.id)},
            changed_by="system:test-merge",
        )
    )
    db_session.flush()

    dry_run = consolidate_numeric_slugs(db_session, dry_run=True)
    assert dry_run["would_rename"] == 1
    assert survivor.slug == f"{base}-3"

    stats = consolidate_numeric_slugs(db_session, dry_run=False)
    db_session.flush()

    assert stats["renamed"] == 1
    assert survivor.slug == base
    assert tombstone.slug.startswith("merged-")
    alias = db_session.scalars(
        select(FacilitySlugAlias).where(FacilitySlugAlias.slug == f"{base}-3")
    ).one()
    assert alias.facility_id == survivor.id
