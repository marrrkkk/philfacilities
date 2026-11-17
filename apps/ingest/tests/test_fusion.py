"""Fusion must combine conflicting claims without losing either value."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityAttributeFusion,
    FacilityChangeEvent,
    FacilitySourceLink,
    Release,
    SourceRecord,
)
from sqlalchemy import delete, func, select

pytestmark = pytest.mark.integration


def _source(
    session,
    suffix: str,
    agency_code: str,
    slug: str,
    *,
    agency: Agency | None = None,
    authority_level: str = "official",
    coverage_scope: str = "NATIONAL_PARTIAL",
    publisher_type: str = "government",
    rights: str = "publicly_available_verified",
    publication_status: str = "published",
):
    if agency is None:
        agency = Agency(
            name=f"Fusion agency {agency_code} {suffix}",
            short_code=f"{agency_code}-{suffix}",
            publisher_type=publisher_type,
        )
        session.add(agency)
        session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"fusion-{slug}-{suffix}",
        name=f"Fusion {slug}",
        publication_status=publication_status,
        redistribution_status=rights,
        authority_level=authority_level,
        coverage_scope=coverage_scope,
    )
    session.add(dataset)
    session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"FUSION-{slug}-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="published",
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


def _facility(session, suffix: str, **overrides):
    values = {
        "slug": f"fusion-facility-{suffix}",
        "display_name": "Fusion Test Health Centre",
        "facility_type": "health_facility",
        "inclusion_class": "GOVERNMENT_FACILITY",
        "ownership": "unknown",
        "ownership_type": "UNKNOWN",
        "operator_type": "UNKNOWN",
        "public_access_class": "UNKNOWN",
        "record_status": "unknown",
        "publication_status": "public",
        "is_synthetic": True,
    }
    values.update(overrides)
    facility = Facility(**values)
    session.add(facility)
    session.flush()
    return facility


def _link(session, facility: Facility, record: SourceRecord) -> None:
    existing = session.scalar(
        select(FacilitySourceLink.id).where(
            FacilitySourceLink.facility_id == facility.id,
            FacilitySourceLink.source_record_id == record.id,
        )
    )
    if existing is not None:
        return
    session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=record.id,
            match_method="exact",
            match_status="accepted",
        )
    )
    session.flush()


def _assert_claim(
    session,
    facility: Facility,
    record: SourceRecord,
    attribute: str,
    value: str,
    *,
    review_status: str = "source_supplied",
) -> None:
    _link(session, facility, record)
    session.add(
        AttributeAssertion(
            facility_id=facility.id,
            attribute_name=attribute,
            source_record_id=record.id,
            raw_value=value,
            normalized_value=value,
            review_status=review_status,
        )
    )
    session.flush()


def _fusion(session, facility: Facility, attribute: str = "ownership") -> FacilityAttributeFusion:
    return session.scalars(
        select(FacilityAttributeFusion).where(
            FacilityAttributeFusion.facility_id == facility.id,
            FacilityAttributeFusion.attribute_name == attribute,
        )
    ).one()


def test_conflicting_claims_are_retained(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    record_a = _source(db_session, suffix, "FA", "a")
    record_b = _source(db_session, suffix, "FB", "b")
    _assert_claim(db_session, facility, record_a, "ownership", "government")
    _assert_claim(db_session, facility, record_b, "ownership", "private")

    stats = build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)
    assert stats.attributes_written == 1
    assert stats.conflict == 1
    fusion = _fusion(db_session, facility)
    assert fusion.status == "conflict"
    assert fusion.distinct_value_count == 2
    values = {entry["normalized_value"] for entry in fusion.alternatives}
    assert values == {"government", "private"}
    assert all(entry["source_record_ids"] for entry in fusion.alternatives)
    assert sum(1 for entry in fusion.alternatives if entry["selected"]) == 1


def test_internal_claim_does_not_participate_in_fusion(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    public_record = _source(db_session, suffix, "PUB", "a")
    internal_record = _source(
        db_session,
        suffix,
        "INT",
        "b",
        rights="restricted_non_redistributable",
        publication_status="blocked",
    )
    _assert_claim(db_session, facility, public_record, "ownership", "government")
    _assert_claim(db_session, facility, internal_record, "ownership", "private")

    stats = build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)

    assert stats.attributes_written == 1
    fusion = _fusion(db_session, facility)
    assert fusion.status == "single_source"
    assert fusion.claim_count == 1
    assert fusion.selected_value == "government"
    assert all(
        str(internal_record.id) not in entry["source_record_ids"] for entry in fusion.alternatives
    )


def test_cross_agency_agreement_is_marked_agreed_and_applied(db_session):
    from philfacilities_ingest.fusion import apply_fusions, build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    record_a = _source(db_session, suffix, "GA", "a")
    record_b = _source(db_session, suffix, "GB", "b")
    _assert_claim(db_session, facility, record_a, "ownership", "Government")
    _assert_claim(db_session, facility, record_b, "ownership", "Government")

    build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)
    fusion = _fusion(db_session, facility)
    assert fusion.status == "agreed"
    assert fusion.confidence == Decimal("0.950")
    assert fusion.distinct_value_count == 1
    assert len(fusion.alternatives) == 1
    assert fusion.alternatives[0]["selected"] is True

    result = apply_fusions(db_session, facility_ids=[facility.id])
    assert result["applied"] == 1
    assert facility.ownership == "government"


def test_same_agency_records_are_not_cross_source_agreement(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    agency = Agency(
        name=f"Fusion same agency {suffix}",
        short_code=f"SA-{suffix}",
        publisher_type="government",
    )
    db_session.add(agency)
    db_session.flush()
    facility = _facility(session=db_session, suffix=suffix)
    record_a = _source(db_session, suffix, "S1", "a", agency=agency)
    record_b = _source(db_session, suffix, "S2", "b", agency=agency)
    _assert_claim(db_session, facility, record_a, "ownership", "government")
    _assert_claim(db_session, facility, record_b, "ownership", "government")

    build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)
    fusion = _fusion(db_session, facility)
    assert fusion.status == "single_source"
    assert fusion.claim_count == 2
    assert fusion.confidence == Decimal("0.700")


def test_authority_beats_raw_claim_frequency(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    community_a = _source(
        db_session,
        suffix,
        "CA",
        "a",
        authority_level="community",
        coverage_scope="DISCOVERY_LAYER",
        publisher_type="community",
    )
    community_b = _source(
        db_session,
        suffix,
        "CB",
        "b",
        authority_level="community",
        coverage_scope="DISCOVERY_LAYER",
        publisher_type="community",
    )
    official = _source(
        db_session,
        suffix,
        "OA",
        "c",
        authority_level="official",
        coverage_scope="NATIONAL_OFFICIAL_INVENTORY",
    )
    _assert_claim(db_session, facility, community_a, "ownership", "private")
    _assert_claim(db_session, facility, community_b, "ownership", "private")
    _assert_claim(db_session, facility, official, "ownership", "government")

    build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)
    fusion = _fusion(db_session, facility)
    assert fusion.status == "conflict"
    assert fusion.selected_value == "government"
    selected = [entry for entry in fusion.alternatives if entry["selected"]]
    assert len(selected) == 1
    assert selected[0]["normalized_value"] == "government"


def test_explicit_facility_ids_respect_multi_source_scope(db_session):
    from philfacilities_ingest.fusion import build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    record = _source(db_session, suffix, "MS", "a")
    _link(db_session, facility, record)
    _assert_claim(db_session, facility, record, "ownership", "government")

    scoped = build_attribute_fusions(
        db_session,
        facility_ids=[facility.id],
        multi_source_only=True,
    )
    assert scoped.attributes_written == 0
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(FacilityAttributeFusion)
            .where(FacilityAttributeFusion.facility_id == facility.id)
        )
        == 0
    )

    full = build_attribute_fusions(
        db_session,
        facility_ids=[facility.id],
        multi_source_only=False,
    )
    assert full.attributes_written == 1


def test_single_source_only_fills_missing_canonical_field(db_session):
    from philfacilities_ingest.fusion import apply_fusions, build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    missing = _facility(session=db_session, suffix=f"{suffix}-missing")
    existing = _facility(
        session=db_session,
        suffix=f"{suffix}-existing",
        ownership_type="LOCAL_GOVERNMENT",
    )
    record_a = _source(db_session, suffix, "M1", "a")
    record_b = _source(db_session, suffix, "M2", "b")
    _assert_claim(db_session, missing, record_a, "ownership_type", "GOVERNMENT_UNSPECIFIED")
    _assert_claim(db_session, existing, record_b, "ownership_type", "GOVERNMENT_UNSPECIFIED")
    build_attribute_fusions(
        db_session,
        facility_ids=[missing.id, existing.id],
        multi_source_only=False,
    )

    result = apply_fusions(db_session, facility_ids=[missing.id, existing.id])
    assert result["applied"] == 1
    assert missing.ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert existing.ownership_type == "LOCAL_GOVERNMENT"
    assert result["skipped_by_reason"]["existing_value_not_missing"] == 1


def test_clear_authority_conflict_is_applied_automatically(db_session):
    from philfacilities_ingest.fusion import apply_fusions, build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(
        session=db_session,
        suffix=suffix,
        ownership_type="LOCAL_GOVERNMENT",
    )
    community = _source(
        db_session,
        suffix,
        "AU",
        "a",
        authority_level="community",
        coverage_scope="DISCOVERY_LAYER",
        publisher_type="community",
    )
    official = _source(
        db_session,
        suffix,
        "OF",
        "b",
        authority_level="official",
        coverage_scope="NATIONAL_OFFICIAL_INVENTORY",
    )
    _assert_claim(db_session, facility, community, "ownership_type", "LOCAL_GOVERNMENT")
    _assert_claim(db_session, facility, official, "ownership_type", "NATIONAL_GOVERNMENT")
    build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)

    fusion = _fusion(db_session, facility, "ownership_type")
    assert fusion.status == "conflict"
    assert fusion.confidence == Decimal("0.650")

    result = apply_fusions(db_session, facility_ids=[facility.id])
    assert result["applied"] == 1
    assert facility.ownership_type == "NATIONAL_GOVERNMENT"
    event = db_session.scalars(
        select(FacilityChangeEvent).where(
            FacilityChangeEvent.facility_id == facility.id,
            FacilityChangeEvent.change_type == "attribute_fused",
        )
    ).one()
    assert event.changed_by == "fusion:fusion-v2"
    assert event.new_value["decision"] == "conflict_auto"


def test_ambiguous_conflict_is_left_derived_only(db_session):
    from philfacilities_ingest.fusion import apply_fusions, build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    record_a = _source(db_session, suffix, "E1", "a")
    record_b = _source(db_session, suffix, "E2", "b")
    _assert_claim(db_session, facility, record_a, "ownership_type", "LOCAL_GOVERNMENT")
    _assert_claim(db_session, facility, record_b, "ownership_type", "NATIONAL_GOVERNMENT")
    build_attribute_fusions(db_session, facility_ids=[facility.id], multi_source_only=False)

    fusion = _fusion(db_session, facility, "ownership_type")
    assert fusion.status == "conflict"
    assert fusion.confidence == Decimal("0.350")

    result = apply_fusions(db_session, facility_ids=[facility.id])
    assert facility.ownership_type == "UNKNOWN"
    assert result["applied"] == 0
    assert result["skipped_by_reason"]["ambiguous_conflict"] == 1


def test_invalid_canonical_value_is_not_applied(db_session):
    from philfacilities_ingest.fusion import apply_fusions, build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    record = _source(db_session, suffix, "IV", "a")
    _assert_claim(db_session, facility, record, "ownership_type", "Government")
    build_attribute_fusions(
        db_session,
        facility_ids=[facility.id],
        multi_source_only=False,
    )

    result = apply_fusions(db_session, facility_ids=[facility.id])
    assert facility.ownership_type == "UNKNOWN"
    assert result["applied"] == 0
    assert result["skipped_by_reason"]["invalid_canonical_value"] == 1


def test_stale_fusion_is_removed_when_claims_disappear(db_session):
    from philfacilities_ingest.fusion import apply_fusions, build_attribute_fusions

    suffix = uuid.uuid4().hex[:8]
    facility = _facility(session=db_session, suffix=suffix)
    record = _source(db_session, suffix, "ST", "a")
    _assert_claim(db_session, facility, record, "ownership", "government")
    build_attribute_fusions(
        db_session,
        facility_ids=[facility.id],
        multi_source_only=False,
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(FacilityAttributeFusion)
            .where(FacilityAttributeFusion.facility_id == facility.id)
        )
        == 1
    )

    db_session.execute(
        delete(AttributeAssertion).where(AttributeAssertion.facility_id == facility.id)
    )
    db_session.flush()
    stats = build_attribute_fusions(
        db_session,
        facility_ids=[facility.id],
        multi_source_only=False,
    )
    assert stats.removed == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(FacilityAttributeFusion)
            .where(FacilityAttributeFusion.facility_id == facility.id)
        )
        == 0
    )
    result = apply_fusions(db_session, facility_ids=[facility.id])
    assert result["applied"] == 0
