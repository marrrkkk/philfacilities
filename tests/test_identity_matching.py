"""Deterministic identity matching, review decisions, and explicit merges."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

pytestmark = [pytest.mark.integration, pytest.mark.data_quality]


def _seed_duplicate_pair(db_session, label: str):
    from philfacilities_api.models import (
        Agency,
        Dataset,
        Facility,
        FacilityLocation,
        FacilitySourceLink,
        Release,
        SourceRecord,
    )

    token = uuid.uuid4().hex[:10]
    name = f"Synthetic Identity Test School {label} {token}"
    psgc = "9901001001"
    now = datetime.now(UTC)
    created: dict[str, object] = {}

    facilities = []
    for index, (side, offset) in enumerate((("a", timedelta(days=-2)), ("b", timedelta(0)))):
        agency = Agency(
            name=f"Synthetic test agency {side.upper()} {token}",
            short_code=f"tst-{side}-{token}",
        )
        db_session.add(agency)
        db_session.flush()
        dataset = Dataset(
            agency_id=agency.id,
            slug=f"test-identity-{side}-{token}",
            name=f"Synthetic identity test dataset {side.upper()}",
            description="Test-only dataset; not an official release.",
            redistribution_status="not_applicable",
            access_method="synthetic_fixture",
            is_public_source=True,
            is_synthetic=True,
        )
        db_session.add(dataset)
        db_session.flush()
        release = Release(
            dataset_id=dataset.id,
            source_release_label=f"TEST-ACQUISITION-{side.upper()}-{token}",
            retrieved_at=now,
            processed_at=now,
            ingestion_status="published",
            publication_status="published",
            terms_review_status="synthetic_demo",
            parser_version="test",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        )
        db_session.add(release)
        db_session.flush()
        record = SourceRecord(
            release_id=release.id,
            source_record_key=f"TEST-{side.upper()}-{token}",
            row_number_or_page=str(index + 1),
            raw_payload={"name": name, "psgc": psgc},
            raw_record_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            validation_status="valid",
        )
        db_session.add(record)
        db_session.flush()
        facility = Facility(
            slug=f"synthetic-identity-{side}-{token}",
            display_name=name,
            official_name=name,
            facility_type="school",
            facility_subtype="elementary",
            ownership="government",
            record_status="active_in_registry",
            publication_status="public",
            is_synthetic=True,
            created_at=now + offset,
            updated_at=now + offset,
        )
        db_session.add(facility)
        db_session.flush()
        db_session.add(
            FacilityLocation(
                facility_id=facility.id,
                source_record_id=record.id,
                latitude=14.5995,
                longitude=120.9842,
                precision="source_gps",
                method="synthetic_test",
                address_text=f"{name} address",
                psgc_code=psgc,
                review_status="source_supplied",
                is_current=True,
            )
        )
        db_session.add(
            FacilitySourceLink(
                facility_id=facility.id,
                source_record_id=record.id,
                source_entity_id=f"TEST-{side.upper()}-{token}",
                match_method="new_canonical_record",
                match_confidence=1,
                match_status="automatic_high_confidence",
                evidence={"test": True},
            )
        )
        facilities.append(facility)
        created[side] = {
            "agency": agency,
            "dataset": dataset,
            "release": release,
            "record": record,
            "facility": facility,
        }
    db_session.commit()
    return created["a"], created["b"]


def _cleanup_pair(db_session, older, newer) -> None:
    from philfacilities_api.models import (
        Agency,
        Dataset,
        Facility,
        MatchCandidate,
        Release,
        SourceRecord,
    )

    db_session.rollback()
    facility_ids = [older["facility"].id, newer["facility"].id]
    record_ids = [older["record"].id, newer["record"].id]
    db_session.execute(
        delete(MatchCandidate).where(
            (MatchCandidate.source_facility_id.in_(facility_ids))
            | (MatchCandidate.candidate_facility_id.in_(facility_ids))
            | (MatchCandidate.source_record_id.in_(record_ids))
        )
    )
    for facility_id in facility_ids:
        facility = db_session.get(Facility, facility_id)
        if facility is not None:
            db_session.delete(facility)
    db_session.flush()
    db_session.execute(delete(SourceRecord).where(SourceRecord.id.in_(record_ids)))
    for item in (older, newer):
        release = db_session.get(Release, item["release"].id)
        if release is not None:
            db_session.delete(release)
    db_session.flush()
    for item in (older, newer):
        dataset = db_session.get(Dataset, item["dataset"].id)
        if dataset is not None:
            db_session.delete(dataset)
    db_session.flush()
    for item in (older, newer):
        agency = db_session.get(Agency, item["agency"].id)
        if agency is not None:
            db_session.delete(agency)
    db_session.commit()


def _cleanup_ingested_agency(db_session, agency_code: str) -> None:
    """Remove every row created by a test-only ingestion run."""

    from philfacilities_api.models import (
        Agency,
        Dataset,
        Facility,
        FacilitySourceLink,
        IngestionRun,
        MatchCandidate,
        PublicationGate,
        QualityIssue,
        Release,
        SourceRecord,
    )

    db_session.rollback()
    agency = db_session.scalars(select(Agency).where(Agency.short_code == agency_code)).first()
    if agency is None:
        return

    dataset_ids = list(db_session.scalars(select(Dataset.id).where(Dataset.agency_id == agency.id)))
    release_ids = list(
        db_session.scalars(select(Release.id).where(Release.dataset_id.in_(dataset_ids)))
    )
    record_ids = list(
        db_session.scalars(select(SourceRecord.id).where(SourceRecord.release_id.in_(release_ids)))
    )
    facility_ids = list(
        db_session.scalars(
            select(FacilitySourceLink.facility_id).where(
                FacilitySourceLink.source_record_id.in_(record_ids)
            )
        )
    )

    if record_ids or facility_ids:
        db_session.execute(
            delete(MatchCandidate).where(
                MatchCandidate.source_record_id.in_(record_ids)
                | MatchCandidate.source_facility_id.in_(facility_ids)
                | MatchCandidate.candidate_facility_id.in_(facility_ids)
            )
        )
    if facility_ids:
        db_session.execute(delete(Facility).where(Facility.id.in_(facility_ids)))
    if release_ids:
        db_session.execute(delete(QualityIssue).where(QualityIssue.release_id.in_(release_ids)))
    if dataset_ids:
        db_session.execute(delete(IngestionRun).where(IngestionRun.dataset_id.in_(dataset_ids)))
    db_session.execute(delete(SourceRecord).where(SourceRecord.id.in_(record_ids)))
    db_session.execute(delete(Release).where(Release.id.in_(release_ids)))
    db_session.execute(delete(PublicationGate).where(PublicationGate.dataset_id.in_(dataset_ids)))
    db_session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
    db_session.execute(delete(Agency).where(Agency.id == agency.id))
    db_session.commit()


def _candidate_for(db_session, newer, older):
    from philfacilities_api.models import MatchCandidate

    return db_session.scalars(
        select(MatchCandidate).where(
            MatchCandidate.source_facility_id == newer["facility"].id,
            MatchCandidate.candidate_facility_id == older["facility"].id,
        )
    ).one()


def test_candidate_generation_is_idempotent_and_rejections_are_retained(client, db_session):
    from philfacilities_api.models import MatchCandidate
    from philfacilities_ingest.matching import generate_match_candidates, reject_match_candidate

    older, newer = _seed_duplicate_pair(db_session, "reject")
    try:
        first = generate_match_candidates(db_session)
        db_session.commit()
        assert first["created"] >= 1

        candidate = _candidate_for(db_session, newer, older)
        assert candidate.match_status == "pending"
        assert candidate.match_method == "exact_normalized_name_psgc_type"
        assert float(candidate.match_confidence) == 0.950
        assert candidate.evidence["psgc_code"] == "9901001001"
        assert candidate.evidence["address_match"] is True

        second = generate_match_candidates(db_session)
        db_session.commit()
        assert second["created"] == 0
        assert second["existing"] >= 1
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(MatchCandidate)
                .where(MatchCandidate.source_facility_id == newer["facility"].id)
            )
            == 1
        )

        listing = client.get(
            "/v1/quality/match-candidates", params={"status": "pending", "limit": 200}
        )
        assert listing.status_code == 200
        body = listing.json()
        assert body["limit"] == 200
        assert body["total"] >= 1
        assert body["by_status"]["pending"] >= 1
        assert set(body["by_status"]) == {"pending", "accepted", "rejected", "merged"}
        item = next(row for row in body["items"] if row["id"] == str(candidate.id))
        assert item["source_facility_id"] == str(newer["facility"].id)
        assert item["candidate_facility_id"] == str(older["facility"].id)
        assert item["source_facility_name"] == newer["facility"].display_name
        assert item["candidate_facility_name"] == older["facility"].display_name
        assert "reviewer" not in item
        assert "review_note" not in item

        detail = client.get(f"/v1/quality/match-candidates/{candidate.id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == str(candidate.id)

        rejected = reject_match_candidate(
            db_session, candidate.id, reviewer="test-reviewer", note="Different catchment area."
        )
        db_session.commit()
        assert rejected.match_status == "rejected"

        third = generate_match_candidates(db_session)
        db_session.commit()
        assert third["created"] == 0
        assert _candidate_for(db_session, newer, older).match_status == "rejected"

        rejected_list = client.get(
            "/v1/quality/match-candidates", params={"status": "rejected"}
        ).json()
        assert any(row["id"] == str(candidate.id) for row in rejected_list["items"])
        assert (
            client.get(
                "/v1/quality/match-candidates", params={"status": "not-a-status"}
            ).status_code
            == 400
        )
    finally:
        _cleanup_pair(db_session, older, newer)


def test_accepted_candidate_can_be_merged_with_audit_history(client, db_session):
    from philfacilities_api.models import Facility, FacilityChangeEvent, FacilitySourceLink
    from philfacilities_ingest.matching import (
        MatchingError,
        accept_match_candidate,
        generate_match_candidates,
        merge_match_candidate,
        reject_match_candidate,
    )

    older, newer = _seed_duplicate_pair(db_session, "merge")
    try:
        generate_match_candidates(db_session)
        db_session.commit()
        candidate = _candidate_for(db_session, newer, older)

        accepted = accept_match_candidate(
            db_session, candidate.id, reviewer="test-reviewer", note="Same school."
        )
        db_session.commit()
        assert accepted.match_status == "accepted"

        with pytest.raises(MatchingError, match="only pending candidates can be rejected"):
            reject_match_candidate(
                db_session, candidate.id, reviewer="test-reviewer", note="No longer pending."
            )
        db_session.rollback()

        merged = merge_match_candidate(
            db_session, candidate.id, reviewer="test-reviewer", note="Confirmed duplicate."
        )
        db_session.commit()
        assert merged.match_status == "merged"
        assert merged.resolution["moved_counts"]["facility_source_links"] == 1

        source = db_session.get(Facility, newer["facility"].id)
        target = db_session.get(Facility, older["facility"].id)
        assert source.publication_status == "internal"
        assert source.record_status == "merged"
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(FacilitySourceLink)
                .where(FacilitySourceLink.facility_id == source.id)
            )
            == 0
        )
        target_links = db_session.scalars(
            select(FacilitySourceLink).where(FacilitySourceLink.facility_id == target.id)
        ).all()
        assert len(target_links) == 2
        assert {link.source_record_id for link in target_links} == {
            older["record"].id,
            newer["record"].id,
        }

        events = db_session.scalars(
            select(FacilityChangeEvent)
            .where(
                FacilityChangeEvent.facility_id.in_([source.id, target.id]),
                FacilityChangeEvent.change_type.in_(
                    ["facility_merged_into", "facility_merged_from"]
                ),
            )
            .order_by(FacilityChangeEvent.changed_at)
        ).all()
        assert {event.change_type for event in events} == {
            "facility_merged_into",
            "facility_merged_from",
        }
        source_event = next(
            event for event in events if event.change_type == "facility_merged_into"
        )
        assert source_event.old_value["publication_status"] == "public"
        assert source_event.old_value["record_status"] == "active_in_registry"
        target_event = next(
            event for event in events if event.change_type == "facility_merged_from"
        )
        assert target_event.old_value["publication_status"] == "public"
        assert target_event.old_value["record_status"] == "active_in_registry"
        assert target_event.new_value["merged_source_facility"]["id"] == str(source.id)

        detail = client.get(f"/v1/quality/match-candidates/{merged.id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["match_status"] == "merged"
        assert body["resolution"]["moved_counts"]["facility_source_links"] == 1
        assert body["resolution"]["source_facility_snapshot"]["publication_status"] == "public"
        assert body["resolution"]["source_facility_after"]["record_status"] == "merged"
        assert "reviewer" not in body["resolution"]

        assert client.get(f"/v1/facilities/{newer['facility'].slug}").status_code == 404
        target_detail = client.get(f"/v1/facilities/{older['facility'].slug}")
        assert target_detail.status_code == 200
        assert target_detail.json()["source_count"] == 2
    finally:
        _cleanup_pair(db_session, older, newer)


def test_same_agency_and_incompatible_subtypes_are_not_queued(db_session):
    from philfacilities_api.models import MatchCandidate
    from philfacilities_ingest.matching import generate_match_candidates, normalize_name

    assert normalize_name("  Saint  Mary's (Poblacion)  ") == "saint mary s poblacion"
    older, newer = _seed_duplicate_pair(db_session, "guard")
    try:
        older["facility"].facility_subtype = "secondary"
        db_session.commit()
        stats = generate_match_candidates(db_session)
        db_session.commit()
        assert stats["skipped_subtype"] >= 1
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(MatchCandidate)
                .where(MatchCandidate.source_facility_id == newer["facility"].id)
            )
            == 0
        )

        # Same agency cannot produce a cross-source candidate.
        dataset = newer["dataset"]
        older_agency = older["agency"]
        dataset.agency_id = older_agency.id
        db_session.commit()
        older["facility"].facility_subtype = "elementary"
        db_session.commit()
        stats = generate_match_candidates(db_session)
        db_session.commit()
        assert stats["skipped_same_agency"] >= 1
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(MatchCandidate)
                .where(MatchCandidate.source_facility_id == newer["facility"].id)
            )
            == 0
        )
    finally:
        _cleanup_pair(db_session, older, newer)


def test_ingestion_hook_queues_candidate_without_merging(client, db_session):
    """A real ingestion run flags a cross-agency duplicate but creates two facilities."""

    import csv
    import io

    from philfacilities_api.models import (
        Agency,
        Dataset,
        Facility,
        FacilityLocation,
        FacilitySourceLink,
        MatchCandidate,
        QualityIssue,
        Release,
        SourceRecord,
    )
    from philfacilities_ingest.contracts import ReleaseSpec
    from philfacilities_ingest.pipeline import run_ingestion
    from philfacilities_ingest.sources.doh import DOHNHFRAdapter

    existing = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-health-facility-01-doh")
    ).one()
    existing_location = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == existing.id,
            FacilityLocation.is_current.is_(True),
        )
    ).one()

    token = uuid.uuid4().hex[:10]
    agency_code = f"xsrc-{token}"
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "facility_id",
            "facility_name",
            "facility_category",
            "ownership",
            "service_capability_level",
            "bed_capacity",
            "latitude",
            "longitude",
            "coordinate_precision",
            "coordinate_method",
            "psgc_code",
            "address",
        ]
    )
    writer.writerow(
        [
            f"XSRC-{token}",
            existing.display_name,
            existing.facility_subtype,
            "Government",
            "Level 1",
            "25",
            str(existing_location.latitude),
            str(existing_location.longitude),
            existing_location.precision,
            "Synthetic cross-source test",
            existing_location.psgc_code,
            existing_location.address_text,
        ]
    )
    spec = ReleaseSpec(
        agency_code=agency_code,
        agency_name=f"Synthetic cross-source test agency {token}",
        dataset_slug=f"test-cross-source-{token}",
        dataset_name="Synthetic cross-source ingestion test",
        release_label=f"TEST-CROSS-SOURCE-{token}",
        filename=f"cross-source-{token}.csv",
        content=buffer.getvalue().encode(),
        source_published_at=datetime.now(UTC),
        retrieved_at=datetime.now(UTC),
        reference_period_start=date(2026, 1, 1),
        reference_period_end=date(2026, 9, 30),
        redistribution_status="not_applicable",
        access_method="synthetic_fixture",
        license_identifier="Synthetic fixture; no source-data rights",
        is_synthetic=True,
        notes="Test-only release; not an official dataset.",
    )

    try:
        result = run_ingestion(spec=spec, adapter=DOHNHFRAdapter(spec), session=db_session)
        assert result.status == "published"
        assert result.stats["facilities_created"] == 1
        assert result.stats["candidate_matches"] == 1

        dataset = db_session.scalars(
            select(Dataset)
            .join(Agency, Dataset.agency_id == Agency.id)
            .where(Agency.short_code == agency_code)
        ).one()
        record = db_session.scalars(
            select(SourceRecord).join(Release).where(Release.dataset_id == dataset.id)
        ).one()
        link = db_session.scalars(
            select(FacilitySourceLink).where(FacilitySourceLink.source_record_id == record.id)
        ).one()
        new_facility = db_session.get(Facility, link.facility_id)
        assert new_facility.id != existing.id
        assert new_facility.publication_status == "public"
        assert new_facility.record_status == "active_in_registry"
        assert existing.publication_status == "public"
        assert existing.record_status == "active_in_registry"

        candidate = db_session.scalars(
            select(MatchCandidate).where(MatchCandidate.source_record_id == record.id)
        ).one()
        assert candidate.match_status == "pending"
        assert candidate.source_facility_id == new_facility.id
        assert candidate.candidate_facility_id == existing.id
        assert candidate.source_agency_code == agency_code
        assert candidate.candidate_agency_code == "doh"
        assert candidate.match_method == "exact_normalized_name_psgc_type"
        assert float(candidate.match_confidence) == 0.950
        assert candidate.evidence["psgc_code"] == existing_location.psgc_code
        assert candidate.evidence["address_match"] is True
        assert candidate.evidence["distance_m"] == 0.0
        assert candidate.reviewed_at is None

        issue = db_session.scalars(
            select(QualityIssue).where(
                QualityIssue.source_record_id == record.id,
                QualityIssue.issue_code == "cross_source_match_candidate",
            )
        ).one()
        assert issue.severity == "info"
        assert issue.status == "open"
        assert issue.details["match_candidate_id"] == str(candidate.id)

        # No merge occurred: the original DOH evidence stays put and the new facility keeps
        # its own source link while both remain separately published.
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(FacilitySourceLink)
                .where(FacilitySourceLink.facility_id == existing.id)
            )
            == 1
        )
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(Facility)
                .where(
                    Facility.display_name == existing.display_name,
                    Facility.publication_status == "public",
                )
            )
            == 2
        )

        listing = client.get(
            "/v1/quality/match-candidates", params={"status": "pending", "limit": 200}
        )
        assert listing.status_code == 200
        assert any(row["id"] == str(candidate.id) for row in listing.json()["items"])
        assert client.get(f"/v1/facilities/{new_facility.slug}").status_code == 200
        assert client.get(f"/v1/facilities/{existing.slug}").status_code == 200
    finally:
        _cleanup_ingested_agency(db_session, agency_code)
