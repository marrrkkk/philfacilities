"""Display-name casing for canonical creation and the backfill pass."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityChangeEvent,
    PublicationGate,
    Release,
    SourceRecord,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _facility(session, name: str, slug: str, *, status: str = "active") -> Facility:
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
        record_status=status,
        publication_status="public",
        is_synthetic=True,
        created_at=datetime.now(UTC),
    )
    session.add(facility)
    session.flush()
    return facility


def test_backfill_title_cases_uppercase_names_and_records_events(db_session) -> None:
    from philfacilities_ingest.display_names import normalize_facility_display_names

    suffix = uuid.uuid4().hex[:10]
    old_name = f"ALPHA RURAL HEALTH UNIT {suffix.upper()}"
    caps = _facility(db_session, old_name, f"alpha-rural-health-unit-{suffix}")
    mixed = _facility(db_session, f"Beta Clinic {suffix}", f"beta-clinic-{suffix}")
    abbreviation_only = _facility(db_session, "RHU", f"rhu-{suffix}")

    dry_run = normalize_facility_display_names(db_session, dry_run=True)
    assert dry_run["would_normalize"] >= 1
    assert caps.display_name == old_name

    stats = normalize_facility_display_names(db_session, dry_run=False)
    db_session.flush()

    assert stats["normalized"] >= 1
    assert caps.display_name == f"Alpha Rural Health Unit {suffix.upper()}"
    assert mixed.display_name == f"Beta Clinic {suffix}"
    assert abbreviation_only.display_name == "RHU"

    event = db_session.scalars(
        select(FacilityChangeEvent).where(
            FacilityChangeEvent.facility_id == caps.id,
            FacilityChangeEvent.change_type == "display_name_normalized",
        )
    ).one()
    assert event.attribute_name == "display_name"
    assert event.old_value == {"value": old_name}
    assert event.new_value == {"value": caps.display_name}
    assert event.changed_by == "system:display-name-normalization"

    second = normalize_facility_display_names(db_session, dry_run=False)
    db_session.flush()
    assert second["normalized"] == 0
    assert db_session.scalars(
        select(FacilityChangeEvent).where(
            FacilityChangeEvent.facility_id == caps.id,
            FacilityChangeEvent.change_type == "display_name_normalized",
        )
    ).all() == [event]


def test_canonical_creation_normalizes_display_name_but_keeps_official_name(
    db_session,
) -> None:
    from philfacilities_ingest.contracts import FacilityCandidate, LocationData
    from philfacilities_ingest.pipeline.canonical import (
        BULK_ASSERTIONS_KEY,
        _apply_candidate,
        flush_attribute_assertions,
    )
    from philfacilities_ingest.pipeline.stats import IngestStats

    suffix = uuid.uuid4().hex[:10]
    agency = Agency(name=f"Test education agency {suffix}", short_code=f"TEA-{suffix}")
    db_session.add(agency)
    db_session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"test-education-{suffix}",
        name="Test education dataset",
        publication_status="public",
        redistribution_status="publicly_available_verified",
        authority_level="official",
    )
    db_session.add(dataset)
    db_session.flush()
    gate = PublicationGate(dataset_id=dataset.id, status="approved")
    db_session.add(gate)
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"TEST-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="processing",
        publication_status="public",
        terms_review_status="approved_with_attribution",
    )
    db_session.add(release)
    db_session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key="row-1",
        raw_payload={"name": "TAUNGOH ELEMENTARY SCHOOL"},
        raw_record_hash=uuid.uuid4().hex * 2,
        validation_status="valid",
    )
    db_session.add(record)
    db_session.flush()

    candidate = FacilityCandidate(
        source_record_key="row-1",
        source_entity_id=f"entity-{suffix}",
        row_reference="test:1",
        display_name="TAUNGOH ELEMENTARY SCHOOL",
        facility_type="school",
        facility_subtype="PUBLIC_ELEMENTARY_SCHOOL",
        ownership="government",
        ownership_type="NATIONAL_GOVERNMENT",
        operator_type="GOVERNMENT",
        record_status="active_in_registry",
        inclusion_class="GOVERNMENT_FACILITY",
        location=LocationData(
            latitude=4.706311,
            longitude=119.492008,
            precision="map_geocoded",
        ),
    )
    # The production runner batches assertions until after the facility rows
    # are flushed. Do the same here so the test exercises the canonical creation
    # path without changing its bulk ordering.
    db_session.info[BULK_ASSERTIONS_KEY] = True
    result = _apply_candidate(
        db_session,
        candidate=candidate,
        release=release,
        record=record,
        agency=agency,
        dataset=dataset,
        gate=gate,
        parser_version="test-1.0.0",
        stats=IngestStats(),
        enqueue_matches=False,
    )
    db_session.flush()
    flush_attribute_assertions(db_session)
    db_session.flush()

    assert result is not None
    assert result.display_name == "Taungoh Elementary School"
    assert result.official_name == "TAUNGOH ELEMENTARY SCHOOL"
    assertion = db_session.scalars(
        select(AttributeAssertion).where(
            AttributeAssertion.facility_id == result.id,
            AttributeAssertion.attribute_name == "display_name",
        )
    ).one()
    assert assertion.raw_value == "TAUNGOH ELEMENTARY SCHOOL"
