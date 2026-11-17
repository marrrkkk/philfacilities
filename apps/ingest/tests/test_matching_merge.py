"""Merge audit and undo behaviour against the live test database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityContact,
    FacilityLocation,
    FacilitySourceLink,
    Release,
    SourceRecord,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _fixture(session, *, with_contacts: bool = False) -> dict[str, object]:
    from philfacilities_ingest.matching import enqueue_match_candidate

    suffix = uuid.uuid4().hex[:10]
    agency = Agency(name=f"Merge test agency {suffix}", short_code=f"MT-{suffix}")
    session.add(agency)
    session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"merge-test-{suffix}",
        name="Merge test dataset",
        publication_status="public",
        redistribution_status="publicly_available_verified",
        coverage_scope="selected_lgu",
    )
    session.add(dataset)
    session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"MERGE-TEST-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="public",
    )
    session.add(release)
    session.flush()

    source_record = SourceRecord(
        release_id=release.id,
        source_record_key=f"source-{suffix}",
        raw_payload={"name": "Test Health Centre"},
        raw_record_hash=uuid.uuid4().hex * 2,
    )
    session.add(source_record)
    session.flush()

    source = Facility(
        slug=f"test-health-centre-source-{suffix}",
        display_name=f"Test Health Centre {suffix}",
        facility_type="health",
        facility_subtype="health_centre",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership_type="GOVERNMENT",
        operator_type="GOVERNMENT",
        record_status="active",
        publication_status="public",
        is_synthetic=True,
    )
    target = Facility(
        slug=f"test-health-centre-target-{suffix}",
        display_name=f"Test Health Centre {suffix}",
        facility_type="health",
        facility_subtype="health_centre",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership_type="GOVERNMENT",
        operator_type="GOVERNMENT",
        record_status="active",
        publication_status="public",
        is_synthetic=True,
    )
    session.add_all([source, target])
    session.flush()

    session.add(
        FacilitySourceLink(
            facility_id=source.id,
            source_record_id=source_record.id,
            match_method="exact",
            match_status="accepted",
        )
    )
    source_location = FacilityLocation(
        facility_id=source.id,
        latitude=14.5995,
        longitude=120.9842,
        precision="map_geocoded",
        address_text="Source address",
        is_current=True,
    )
    target_location = FacilityLocation(
        facility_id=target.id,
        latitude=14.6000,
        longitude=120.9850,
        precision="map_geocoded",
        address_text="Target address",
        is_current=True,
    )
    session.add_all([source_location, target_location])
    assertion = AttributeAssertion(
        facility_id=source.id,
        attribute_name="display_name",
        source_record_id=source_record.id,
        raw_value="Test Health Centre",
        normalized_value="Test Health Centre",
    )
    session.add(assertion)
    session.flush()

    source_contact = None
    duplicate_contact = None
    if with_contacts:
        # Same channel and value on both facilities, with no source record, so
        # the contact unique key would collide if the merge moved it.
        source_contact = FacilityContact(
            facility_id=source.id,
            contact_type="phone",
            value=f"+63 2 555 {suffix[:4]}",
            label="Source line",
        )
        duplicate_contact = FacilityContact(
            facility_id=target.id,
            contact_type="phone",
            value=source_contact.value,
            label="Target line",
        )
        session.add_all(
            [
                source_contact,
                duplicate_contact,
                FacilityContact(
                    facility_id=source.id,
                    contact_type="email",
                    value=f"{suffix}@example.test",
                    label="Source email",
                ),
            ]
        )
        session.flush()

    candidate, created = enqueue_match_candidate(
        session,
        source_record=source_record,
        source_facility=source,
        candidate_facility=target,
        source_agency_code=agency.short_code,
        candidate_agency_code="OTHER",
        source_location=source_location,
        candidate_location=target_location,
    )
    assert created and candidate is not None
    return {
        "source": source,
        "target": target,
        "association": assertion,
        "candidate": candidate,
        "source_location": source_location,
        "target_location": target_location,
        "source_contact": source_contact,
        "duplicate_contact": duplicate_contact,
    }


def test_merge_can_be_undone_and_restores_evidence(db_session) -> None:
    from philfacilities_ingest.matching import (
        accept_match_candidate,
        merge_match_candidate,
        undo_match_merge,
    )

    try:
        data = _fixture(db_session)
        source = data["source"]
        target = data["target"]
        candidate = data["candidate"]
        assertion = data["association"]

        accept_match_candidate(db_session, candidate.id, reviewer="reviewer-1")
        merge_match_candidate(db_session, candidate.id, reviewer="reviewer-1", note="duplicate")
        db_session.flush()

        assert source.record_status == "merged"
        assert source.publication_status == "internal"
        assert assertion.facility_id == target.id
        assert candidate.resolution["active"] is True

        undone = undo_match_merge(
            db_session, candidate.id, reviewer="reviewer-2", note="wrong merge"
        )
        db_session.flush()

        assert undone.match_status == "accepted"
        assert undone.resolution["active"] is False
        assert undone.resolution["undo_history"][0]["undone_by"] == "reviewer-2"
        assert source.record_status == "active"
        assert source.publication_status == "public"
        assert assertion.facility_id == source.id
        link = db_session.scalars(
            select(FacilitySourceLink).where(
                FacilitySourceLink.facility_id == source.id,
                FacilitySourceLink.source_record_id == candidate.source_record_id,
            )
        ).one()
        assert link is not None
        locations = db_session.scalars(
            select(FacilityLocation).where(FacilityLocation.facility_id == source.id)
        ).all()
        assert len(locations) == 1
        assert locations[0].is_current is True
        assert locations[0].valid_to is None
    finally:
        db_session.rollback()


def test_merge_moves_unique_contacts_and_retains_duplicate_contacts(db_session) -> None:
    from philfacilities_ingest.matching import (
        accept_match_candidate,
        merge_match_candidate,
        undo_match_merge,
    )

    try:
        data = _fixture(db_session, with_contacts=True)
        source = data["source"]
        target = data["target"]
        candidate = data["candidate"]
        source_contact = data["source_contact"]
        duplicate_contact = data["duplicate_contact"]
        unique_contact = db_session.scalars(
            select(FacilityContact).where(
                FacilityContact.facility_id == source.id,
                FacilityContact.contact_type == "email",
            )
        ).one()

        accept_match_candidate(db_session, candidate.id, reviewer="reviewer-1")
        merge_match_candidate(db_session, candidate.id, reviewer="reviewer-1")
        db_session.flush()

        assert source_contact.facility_id == source.id
        assert duplicate_contact.facility_id == target.id
        assert unique_contact.facility_id == target.id
        assert candidate.resolution["retained_on_source"] == {"facility_contacts": 1}
        assert candidate.resolution["moved_counts"]["facility_contacts"] == 1

        undo_match_merge(db_session, candidate.id, reviewer="reviewer-2")
        db_session.flush()

        assert unique_contact.facility_id == source.id
        assert source_contact.facility_id == source.id
        assert duplicate_contact.facility_id == target.id
    finally:
        db_session.rollback()


def test_undo_refuses_when_moved_evidence_has_changed(db_session) -> None:
    from philfacilities_ingest.matching import (
        MatchingError,
        accept_match_candidate,
        merge_match_candidate,
        undo_match_merge,
    )

    try:
        data = _fixture(db_session)
        candidate = data["candidate"]
        assertion = data["association"]
        target = data["target"]

        accept_match_candidate(db_session, candidate.id, reviewer="reviewer-1")
        merge_match_candidate(db_session, candidate.id, reviewer="reviewer-1")
        db_session.flush()

        assertion.facility_id = target.id
        other = Facility(
            slug=f"unrelated-{uuid.uuid4().hex[:8]}",
            display_name="Unrelated facility",
            facility_type="health",
            facility_subtype="health_centre",
            publication_status="internal",
            record_status="active",
            is_synthetic=True,
        )
        db_session.add(other)
        db_session.flush()
        assertion.facility_id = other.id
        db_session.flush()

        with pytest.raises(MatchingError, match="changed after the merge"):
            undo_match_merge(db_session, candidate.id, reviewer="reviewer-2")
    finally:
        db_session.rollback()
