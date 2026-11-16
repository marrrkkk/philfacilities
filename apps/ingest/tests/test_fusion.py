"""Fusion must combine conflicting claims without losing either value."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityAttributeFusion,
    Release,
    SourceRecord,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _source(session, suffix: str, agency_code: str, slug: str):
    agency = Agency(
        name=f"Fusion agency {agency_code} {suffix}",
        short_code=f"{agency_code}-{suffix}",
        publisher_type="government",
    )
    session.add(agency)
    session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"fusion-{slug}-{suffix}",
        name=f"Fusion {slug}",
        publication_status="public",
        redistribution_status="publicly_available_verified",
    )
    session.add(dataset)
    session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"FUSION-{slug}-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="public",
    )
    session.add(release)
    session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key=f"record-{slug}-{suffix}",
        raw_payload={"name": "Sample"},
        raw_record_hash=uuid.uuid4().hex * 2,
    )
    session.add(record)
    session.flush()
    return record


def test_conflicting_claims_are_retained(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = Facility(
        slug=f"fusion-facility-{suffix}",
        display_name="Fusion Test Health Centre",
        facility_type="health",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership_type="GOVERNMENT",
        publication_status="public",
        is_synthetic=True,
    )
    db_session.add(facility)
    db_session.flush()
    record_a = _source(db_session, suffix, "FA", "a")
    record_b = _source(db_session, suffix, "FB", "b")
    db_session.add_all(
        [
            AttributeAssertion(
                facility_id=facility.id,
                attribute_name="ownership",
                source_record_id=record_a.id,
                raw_value="government",
                normalized_value="government",
            ),
            AttributeAssertion(
                facility_id=facility.id,
                attribute_name="ownership",
                source_record_id=record_b.id,
                raw_value="private",
                normalized_value="private",
            ),
        ]
    )
    db_session.flush()

    stats = build_attribute_fusions(db_session, facility_ids=[facility.id])
    assert stats.attributes_written == 1
    assert stats.conflict == 1
    fusion = db_session.scalars(
        select(FacilityAttributeFusion).where(
            FacilityAttributeFusion.facility_id == facility.id,
            FacilityAttributeFusion.attribute_name == "ownership",
        )
    ).one()
    assert fusion.status == "conflict"
    assert fusion.distinct_value_count == 2
    values = {entry["normalized_value"] for entry in fusion.alternatives}
    assert values == {"government", "private"}
    assert all(entry["source_record_ids"] for entry in fusion.alternatives)


def test_agreed_claim_is_marked_agreed(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = Facility(
        slug=f"fusion-agree-{suffix}",
        display_name="Fusion Agreed Centre",
        facility_type="health",
        inclusion_class="GOVERNMENT_FACILITY",
        publication_status="public",
        is_synthetic=True,
    )
    db_session.add(facility)
    db_session.flush()
    record_a = _source(db_session, suffix, "GA", "a")
    record_b = _source(db_session, suffix, "GB", "b")
    for record in (record_a, record_b):
        db_session.add(
            AttributeAssertion(
                facility_id=facility.id,
                attribute_name="ownership",
                source_record_id=record.id,
                raw_value="Government",
                normalized_value="Government",
            )
        )
    db_session.flush()

    build_attribute_fusions(db_session, facility_ids=[facility.id])
    fusion = db_session.scalars(
        select(FacilityAttributeFusion).where(
            FacilityAttributeFusion.facility_id == facility.id,
            FacilityAttributeFusion.attribute_name == "ownership",
        )
    ).one()
    assert fusion.status == "agreed"
    assert fusion.distinct_value_count == 1
