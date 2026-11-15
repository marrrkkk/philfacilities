"""Release snapshot and rollback behaviour against the live test database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityFunction,
    FacilityLocation,
    FacilitySourceLink,
    Release,
    ReleaseFacilitySnapshot,
    SourceRecord,
)
from philfacilities_ingest.release_rollback import (
    ReleaseRollbackError,
    capture_facility_snapshot,
    rollback_release,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _release_fixture(session, *, slug_prefix: str = "rollback"):
    suffix = uuid.uuid4().hex[:10]
    agency = Agency(name=f"Rollback agency {suffix}", short_code=f"RB-{suffix}")
    session.add(agency)
    session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"{slug_prefix}-{suffix}",
        name="Rollback test dataset",
        publication_status="published",
        redistribution_status="publicly_available_verified",
        coverage_scope="single_lgu",
    )
    session.add(dataset)
    session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"ROLLBACK-{suffix}",
        retrieved_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="published",
    )
    session.add(release)
    session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key=f"record-{suffix}",
        raw_payload={"name": "Original Hall"},
        raw_record_hash=uuid.uuid4().hex * 2,
    )
    session.add(record)
    session.flush()
    facility = Facility(
        slug=f"rollback-facility-{suffix}",
        display_name="Original Hall",
        official_name="Original Hall",
        facility_type="community_facility",
        facility_subtype="MULTIPURPOSE_HALL",
        facility_kind="facility",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        ownership_type="LOCAL_GOVERNMENT",
        operator_type="LOCAL_GOVERNMENT",
        publication_status="public",
        is_synthetic=True,
        updated_at=release.processed_at,
    )
    session.add(facility)
    session.flush()
    session.add_all(
        [
            FacilitySourceLink(
                facility_id=facility.id,
                source_record_id=record.id,
                match_method="exact",
                match_status="accepted",
            ),
            FacilityLocation(
                facility_id=facility.id,
                source_record_id=record.id,
                latitude=14.5,
                longitude=120.9,
                precision="map_geocoded",
                address_text="Original address",
                is_current=True,
            ),
            AttributeAssertion(
                facility_id=facility.id,
                source_record_id=record.id,
                attribute_name="display_name",
                raw_value="Original Hall",
                normalized_value="Original Hall",
            ),
            FacilityFunction(
                facility_id=facility.id,
                source_record_id=record.id,
                function_code="MULTIPURPOSE_HALL",
            ),
        ]
    )
    session.flush()
    return agency, dataset, release, record, facility


def _add_created_facility(session, *, release, record):
    facility = Facility(
        slug=f"created-{uuid.uuid4().hex[:10]}",
        display_name="Created by release",
        official_name="Created by release",
        facility_type="government_office",
        facility_subtype="BARANGAY_HALL",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        ownership_type="LOCAL_GOVERNMENT",
        operator_type="LOCAL_GOVERNMENT",
        publication_status="public",
        is_synthetic=True,
        updated_at=release.processed_at,
    )
    session.add(facility)
    session.flush()
    session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=record.id,
            match_method="new_canonical_record",
            match_status="automatic_high_confidence",
        )
    )
    session.flush()
    capture_facility_snapshot(session, release=release, facility=facility, was_created=True)
    return facility


def test_snapshot_is_recorded_once_per_release_and_facility(db_session) -> None:
    _agency, _dataset, release, _record, facility = _release_fixture(db_session)
    first = capture_facility_snapshot(
        db_session, release=release, facility=facility, was_created=False
    )
    second = capture_facility_snapshot(
        db_session, release=release, facility=facility, was_created=False
    )
    assert first.id == second.id
    assert first.state["facility"]["display_name"] == "Original Hall"
    assert len(first.state["children"]["facility_locations"]) == 1


def test_rollback_restores_facility_and_children(db_session) -> None:
    _agency, dataset, release, record, facility = _release_fixture(db_session)
    capture_facility_snapshot(db_session, release=release, facility=facility, was_created=False)
    db_session.flush()

    facility.display_name = "Renamed by release"
    facility.ownership_type = "PRIVATE_CORPORATE"
    facility.publication_status = "internal"
    facility.updated_at = datetime.now(UTC)
    # A release replaces rather than duplicates the current location row; the
    # table enforces one current location per facility.
    prior_location = db_session.scalars(
        select(FacilityLocation).where(FacilityLocation.facility_id == facility.id)
    ).one()
    prior_location.is_current = False
    db_session.add(
        FacilityLocation(
            facility_id=facility.id,
            source_record_id=record.id,
            latitude=15.0,
            longitude=121.0,
            precision="map_geocoded",
            address_text="New address",
            is_current=True,
        )
    )
    db_session.add(
        AttributeAssertion(
            facility_id=facility.id,
            source_record_id=record.id,
            attribute_name="display_name",
            raw_value="Renamed by release",
            normalized_value="Renamed by release",
        )
    )
    # The pipeline stamps processed_at after applying every candidate, so a
    # release's own writes are never newer than processed_at. Move the release
    # timestamp forward to model that ordering.
    release.processed_at = datetime.now(UTC)
    db_session.flush()

    result = rollback_release(
        db_session,
        dataset_slug=dataset.slug,
        release_label=release.source_release_label,
        reviewer="test-reviewer",
        note="test rollback",
    )
    db_session.flush()

    assert result["restored"] == 1
    db_session.refresh(facility)
    assert facility.display_name == "Original Hall"
    assert facility.ownership_type == "LOCAL_GOVERNMENT"
    assert facility.publication_status == "public"
    assert result["release_label"] == release.source_release_label
    assert release.ingestion_status == "rolled_back"
    assert release.publication_status == "quarantined"
    locations = db_session.scalars(
        select(FacilityLocation).where(FacilityLocation.facility_id == facility.id)
    ).all()
    assert len(locations) == 1
    assert locations[0].address_text == "Original address"
    assertions = db_session.scalars(
        select(AttributeAssertion).where(AttributeAssertion.facility_id == facility.id)
    ).all()
    assert len(assertions) == 1
    assert assertions[0].normalized_value == "Original Hall"
    snapshot = db_session.scalars(
        select(ReleaseFacilitySnapshot).where(ReleaseFacilitySnapshot.release_id == release.id)
    ).one()
    assert snapshot.restored_at is not None
    assert snapshot.restored_by == "test-reviewer"


def test_rollback_deletes_facility_created_by_release(db_session) -> None:
    _agency, dataset, release, record, _facility = _release_fixture(db_session)
    created = _add_created_facility(db_session, release=release, record=record)
    created_id = created.id

    result = rollback_release(
        db_session,
        dataset_slug=dataset.slug,
        release_label=release.source_release_label,
        reviewer="test-reviewer",
    )
    db_session.flush()

    assert result["deleted"] == 1
    assert db_session.get(Facility, created_id) is None
    snapshot = db_session.scalars(
        select(ReleaseFacilitySnapshot).where(
            ReleaseFacilitySnapshot.release_id == release.id,
            ReleaseFacilitySnapshot.was_created.is_(True),
        )
    ).one()
    assert snapshot.restored_at is not None
    assert snapshot.facility_id is None


def test_rollback_refuses_when_a_later_release_exists(db_session) -> None:
    _agency, dataset, release, _record, facility = _release_fixture(db_session)
    capture_facility_snapshot(db_session, release=release, facility=facility, was_created=False)
    later = Release(
        dataset_id=dataset.id,
        source_release_label=f"LATER-{uuid.uuid4().hex[:8]}",
        retrieved_at=datetime.now(UTC),
        processed_at=release.processed_at + timedelta(seconds=1),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="published",
    )
    db_session.add(later)
    db_session.flush()

    with pytest.raises(ReleaseRollbackError, match="processed after"):
        rollback_release(
            db_session,
            dataset_slug=dataset.slug,
            release_label=release.source_release_label,
            reviewer="test-reviewer",
        )


def test_rollback_refuses_when_later_evidence_is_linked(db_session) -> None:
    _agency, dataset, release, _record, facility = _release_fixture(db_session)
    capture_facility_snapshot(db_session, release=release, facility=facility, was_created=False)

    suffix = uuid.uuid4().hex[:8]
    other_agency = Agency(name=f"Other agency {suffix}", short_code=f"OA-{suffix}")
    db_session.add(other_agency)
    db_session.flush()
    other_dataset = Dataset(
        agency_id=other_agency.id,
        slug=f"other-{suffix}",
        name="Other dataset",
        publication_status="published",
    )
    db_session.add(other_dataset)
    db_session.flush()
    other_release = Release(
        dataset_id=other_dataset.id,
        source_release_label=f"OTHER-{suffix}",
        retrieved_at=datetime.now(UTC),
        processed_at=release.processed_at + timedelta(seconds=1),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="published",
    )
    db_session.add(other_release)
    db_session.flush()
    other_record = SourceRecord(
        release_id=other_release.id,
        source_record_key=f"other-{suffix}",
        raw_payload={},
        raw_record_hash=uuid.uuid4().hex * 2,
    )
    db_session.add(other_record)
    db_session.flush()
    db_session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=other_record.id,
            match_method="manual",
            match_status="accepted",
        )
    )
    db_session.flush()

    with pytest.raises(ReleaseRollbackError, match="later release"):
        rollback_release(
            db_session,
            dataset_slug=dataset.slug,
            release_label=release.source_release_label,
            reviewer="test-reviewer",
        )


def test_rollback_refuses_after_facility_changed(db_session) -> None:
    _agency, dataset, release, _record, facility = _release_fixture(db_session)
    capture_facility_snapshot(db_session, release=release, facility=facility, was_created=False)
    facility.display_name = "Manual edit"
    facility.updated_at = release.processed_at + timedelta(seconds=5)
    db_session.flush()

    with pytest.raises(ReleaseRollbackError, match="changed after release"):
        rollback_release(
            db_session,
            dataset_slug=dataset.slug,
            release_label=release.source_release_label,
            reviewer="test-reviewer",
        )
