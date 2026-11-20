"""Resolution of the pending identity-candidate queue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from philfacilities_api.models import (
    Agency,
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    MatchCandidate,
    Release,
    SourceRecord,
)

pytestmark = pytest.mark.integration


def _agency(session, suffix: str) -> Agency:
    agency = Agency(name=f"Resolution agency {suffix}", short_code=f"RA-{suffix}")
    session.add(agency)
    session.flush()
    return agency


def _facility(
    session,
    *,
    agency: Agency,
    suffix: str,
    tag: str,
    name: str,
    facility_type: str = "health_facility",
    subtype: str = "HOSPITAL",
    official: bool = False,
    record_status: str = "active",
    publication_status: str = "public",
    psgc_code: str = "1374040010",
    latitude: float = 14.5995,
    longitude: float = 120.9842,
):
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"resolution-{suffix}-{tag}",
        name="Resolution test dataset",
        publication_status="public",
        redistribution_status="publicly_available_verified",
        authority_level="official" if official else "community",
    )
    session.add(dataset)
    session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"RES-{suffix}-{tag}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="public",
    )
    session.add(release)
    session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key=f"{suffix}-{tag}",
        raw_payload={"name": name},
        raw_record_hash=uuid.uuid4().hex * 2,
        validation_status="valid",
    )
    session.add(record)
    session.flush()
    facility = Facility(
        slug=f"{tag}-{suffix}",
        display_name=name,
        official_name=name,
        facility_type=facility_type,
        facility_subtype=subtype,
        facility_kind="facility",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        ownership_type="GOVERNMENT",
        operator_type="GOVERNMENT",
        record_status=record_status,
        publication_status=publication_status,
        is_synthetic=True,
    )
    session.add(facility)
    session.flush()
    session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=record.id,
            match_method="exact",
            match_status="accepted",
        )
    )
    session.add(
        FacilityLocation(
            facility_id=facility.id,
            latitude=latitude,
            longitude=longitude,
            precision="map_geocoded",
            psgc_code=psgc_code,
            address_text="",
            is_current=True,
        )
    )
    session.flush()
    return facility, record


def _candidate(
    session,
    *,
    source: Facility,
    source_record: SourceRecord,
    source_agency: Agency,
    target: Facility,
    target_agency: Agency,
) -> MatchCandidate:
    candidate = MatchCandidate(
        candidate_key=uuid.uuid4().hex,
        source_record_id=source_record.id,
        source_facility_id=source.id,
        candidate_facility_id=target.id,
        source_agency_code=source_agency.short_code,
        candidate_agency_code=target_agency.short_code,
        match_method="facility_identity_evidence_v1",
        algorithm_version="2",
        match_confidence=Decimal("0.985"),
        match_status="pending",
        evidence={"algorithm": "facility_identity_evidence_v1"},
    )
    session.add(candidate)
    session.flush()
    return candidate


def test_resolver_merges_a_pair_that_still_meets_the_automatic_rule(db_session) -> None:
    from philfacilities_ingest.aggregation import resolve_pending_match_candidates

    suffix = uuid.uuid4().hex[:10]
    name = f"Test Community Hospital {suffix}"
    source_agency = _agency(db_session, f"{suffix}-src")
    target_agency = _agency(db_session, f"{suffix}-tgt")
    source, source_record = _facility(
        db_session,
        agency=source_agency,
        suffix=suffix,
        tag="source",
        name=name,
        official=False,
    )
    target, _ = _facility(
        db_session,
        agency=target_agency,
        suffix=suffix,
        tag="target",
        name=name,
        official=True,
        latitude=14.5996,
        longitude=120.9843,
    )
    candidate = _candidate(
        db_session,
        source=source,
        source_record=source_record,
        source_agency=source_agency,
        target=target,
        target_agency=target_agency,
    )

    dry_run = resolve_pending_match_candidates(db_session, dry_run=True)
    assert dry_run["would_merge"] >= 1
    assert candidate.match_status == "pending"

    stats = resolve_pending_match_candidates(db_session, dry_run=False)
    db_session.flush()

    assert stats["merged"] >= 1
    assert source.record_status == "merged"
    assert candidate.match_status == "merged"


def test_resolver_rejects_same_agency_city_only_pairs(db_session) -> None:
    from philfacilities_ingest.aggregation import resolve_pending_match_candidates

    suffix = uuid.uuid4().hex[:10]
    name = f"Branch Office {suffix}"
    agency = _agency(db_session, suffix)
    source, source_record = _facility(
        db_session,
        agency=agency,
        suffix=suffix,
        tag="branch-a",
        name=name,
        facility_type="government_office",
        subtype="LOCAL_GOVERNMENT_OFFICE",
        psgc_code="1374040010",
    )
    target, _ = _facility(
        db_session,
        agency=agency,
        suffix=suffix,
        tag="branch-b",
        name=name,
        facility_type="government_office",
        subtype="LOCAL_GOVERNMENT_OFFICE",
        psgc_code="1374040020",
        latitude=14.7000,
        longitude=121.1000,
    )
    candidate = _candidate(
        db_session,
        source=source,
        source_record=source_record,
        source_agency=agency,
        target=target,
        target_agency=agency,
    )

    stats = resolve_pending_match_candidates(db_session, dry_run=False)
    db_session.flush()

    assert stats["rejected"] >= 1
    assert candidate.match_status == "rejected"
    assert candidate.reviewer == "system:match-candidate-resolution"
    assert "different places" in (candidate.review_note or "")
    assert source.record_status == "active"


def test_resolver_rejects_stale_candidates(db_session) -> None:
    from philfacilities_ingest.aggregation import resolve_pending_match_candidates

    suffix = uuid.uuid4().hex[:10]
    name = f"Retired Hospital {suffix}"
    agency = _agency(db_session, suffix)
    source, source_record = _facility(
        db_session,
        agency=agency,
        suffix=suffix,
        tag="retired",
        name=name,
        record_status="merged",
    )
    target, _ = _facility(
        db_session,
        agency=agency,
        suffix=suffix,
        tag="survivor",
        name=name,
    )
    candidate = _candidate(
        db_session,
        source=source,
        source_record=source_record,
        source_agency=agency,
        target=target,
        target_agency=agency,
    )

    stats = resolve_pending_match_candidates(db_session, dry_run=False)
    db_session.flush()

    assert stats["rejected"] >= 1
    assert candidate.match_status == "rejected"
    assert "stale" in (candidate.review_note or "")


def test_resolver_rejects_cross_type_candidates_as_review_only(db_session) -> None:
    from philfacilities_ingest.aggregation import resolve_pending_match_candidates

    suffix = uuid.uuid4().hex[:10]
    name = f"Shared Site {suffix}"
    source_agency = _agency(db_session, f"{suffix}-src")
    target_agency = _agency(db_session, f"{suffix}-tgt")
    source, source_record = _facility(
        db_session,
        agency=source_agency,
        suffix=suffix,
        tag="source-type",
        name=name,
        facility_type="government_office",
        subtype="LOCAL_GOVERNMENT_OFFICE",
    )
    target, _ = _facility(
        db_session,
        agency=target_agency,
        suffix=suffix,
        tag="target-type",
        name=name,
        facility_type="health_facility",
        subtype="HOSPITAL",
        official=True,
    )
    candidate = _candidate(
        db_session,
        source=source,
        source_record=source_record,
        source_agency=source_agency,
        target=target,
        target_agency=target_agency,
    )

    stats = resolve_pending_match_candidates(db_session, dry_run=False)
    db_session.flush()

    assert stats["rejected"] >= 1
    assert candidate.match_status == "rejected"
    assert "review-only" in (candidate.review_note or "")
    assert source.record_status == "active"


def test_resolver_leaves_non_public_pairs_pending(db_session) -> None:
    from philfacilities_ingest.aggregation import resolve_pending_match_candidates

    suffix = uuid.uuid4().hex[:10]
    name = f"Unpublished Hospital {suffix}"
    source_agency = _agency(db_session, f"{suffix}-src")
    target_agency = _agency(db_session, f"{suffix}-tgt")
    source, source_record = _facility(
        db_session,
        agency=source_agency,
        suffix=suffix,
        tag="public-source",
        name=name,
    )
    target, _ = _facility(
        db_session,
        agency=target_agency,
        suffix=suffix,
        tag="internal-target",
        name=name,
        official=True,
        publication_status="internal",
        latitude=14.5996,
        longitude=120.9843,
    )
    candidate = _candidate(
        db_session,
        source=source,
        source_record=source_record,
        source_agency=source_agency,
        target=target,
        target_agency=target_agency,
    )

    stats = resolve_pending_match_candidates(db_session, dry_run=False)
    db_session.flush()
    db_session.refresh(candidate)

    assert stats["skipped_not_public"] >= 1
    assert stats["rejected"] == 0
    assert candidate.match_status == "pending"
    assert source.record_status == "active"


def test_resolver_leaves_no_pending_candidate_behind(db_session) -> None:
    from philfacilities_ingest.aggregation import resolve_pending_match_candidates

    suffix = uuid.uuid4().hex[:10]
    name = f"Queue Drain Hospital {suffix}"
    agency = _agency(db_session, suffix)
    source, source_record = _facility(
        db_session,
        agency=agency,
        suffix=suffix,
        tag="drain-a",
        name=name,
        psgc_code="1374040010",
    )
    target, _ = _facility(
        db_session,
        agency=agency,
        suffix=suffix,
        tag="drain-b",
        name=name,
        psgc_code="1374040020",
        latitude=14.7000,
        longitude=121.1000,
    )
    candidate = _candidate(
        db_session,
        source=source,
        source_record=source_record,
        source_agency=agency,
        target=target,
        target_agency=agency,
    )

    resolve_pending_match_candidates(db_session, dry_run=False)
    db_session.flush()

    db_session.refresh(candidate)
    assert candidate.match_status == "rejected"
