"""Explicit reprocessing preserves source-record identity while applying parser fixes."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.fixtures import philhealth_pdf
from philfacilities_ingest.pipeline import run_ingestion
from philfacilities_ingest.sources.philhealth import PhilHealthPdfAdapter
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


class _KeyVariantAdapter(PhilHealthPdfAdapter):
    """Simulate an older parser that collapsed every physical row onto one key."""

    collapse_keys = True

    def parse(self, spec: ReleaseSpec):
        parsed = super().parse(spec)
        if self.collapse_keys:
            for row in parsed.rows:
                row.source_record_key = "collapsed-source-key"
        return parsed


def _spec(token: str, *, label_suffix: str = "", content: bytes | None = None) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="philhealth",
        agency_name="PhilHealth synthetic reprocess test",
        dataset_slug=f"test-reprocess-{token}",
        dataset_name="Synthetic parser reprocess test",
        release_label=f"TEST-REPROCESS-{token}{label_suffix}",
        filename=f"reprocess-{token}{label_suffix}.pdf",
        content=content or philhealth_pdf(),
        source_url=None,
        source_published_at=datetime.now(UTC),
        retrieved_at=datetime.now(UTC),
        reference_period_start=date(2026, 9, 30),
        reference_period_end=date(2026, 9, 30),
        redistribution_status="not_applicable",
        access_method="synthetic_fixture",
        license_identifier="Synthetic fixture; no source-data rights",
        is_synthetic=True,
        notes="Test-only release; not an official dataset.",
    )


def test_reprocess_retains_rows_from_an_older_key_scheme(db_session) -> None:
    from philfacilities_api.models import (
        FacilitySourceLink,
        Release,
        SourceRecord,
    )

    token = uuid.uuid4().hex[:10]
    spec = _spec(token)

    first = run_ingestion(
        spec=spec,
        adapter=_KeyVariantAdapter(spec, provider_category="Hospital"),
        session=db_session,
    )
    assert first.status == "published"
    release = db_session.get(Release, first.release_id)
    assert release is not None

    before_records = db_session.scalars(
        select(SourceRecord).where(SourceRecord.release_id == release.id)
    ).all()
    # The old parser collapsed every physical row onto one business key. The
    # staging layer retains every physical row under deterministic distinct
    # keys; only the first occurrence is applied.
    assert len(before_records) == 4
    assert len({record.source_record_key for record in before_records}) == 4
    linked_record_ids = set(
        db_session.scalars(
            select(FacilitySourceLink.source_record_id)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .where(SourceRecord.release_id == release.id)
        ).all()
    )
    assert len(linked_record_ids) == 1
    retained_record_id = linked_record_ids.pop()
    retained_link = db_session.scalars(
        select(FacilitySourceLink).where(FacilitySourceLink.source_record_id == retained_record_id)
    ).one()
    retained_facility_id = retained_link.facility_id

    adapter = _KeyVariantAdapter(spec, provider_category="Hospital")
    adapter.collapse_keys = False
    second = run_ingestion(
        spec=spec,
        adapter=adapter,
        session=db_session,
        reprocess=True,
    )

    assert second.status == "published"
    assert second.stats["reprocessed"] is True
    assert second.stats["reprocess_skipped_unchanged"] == 1
    records = db_session.scalars(
        select(SourceRecord).where(SourceRecord.release_id == release.id)
    ).all()
    assert len(records) == 4
    assert len({record.source_record_key for record in records}) == 4

    retained = db_session.get(SourceRecord, retained_record_id)
    assert retained is not None
    assert retained.source_record_key != "collapsed-source-key"
    preserved_link = db_session.scalars(
        select(FacilitySourceLink).where(FacilitySourceLink.source_record_id == retained_record_id)
    ).one()
    assert preserved_link.facility_id == retained_facility_id

    assert (
        db_session.scalar(
            select(func.count())
            .select_from(FacilitySourceLink)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .where(SourceRecord.release_id == release.id)
        )
        == 4
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(SourceRecord.release_id == release.id)
        )
        == 4
    )


class _FailingAdapter(PhilHealthPdfAdapter):
    """Simulate a parser/schema failure after an earlier release published."""

    def parse(self, spec: ReleaseSpec):
        raise ValueError("synthetic parse failure")


def test_failed_new_release_is_quarantined_and_keeps_previous_public_release(db_session) -> None:
    from philfacilities_api.models import (
        Facility,
        FacilitySourceLink,
        Release,
        SourceRecord,
    )

    token = uuid.uuid4().hex[:10]
    good_spec = _spec(token, label_suffix="-A")
    first = run_ingestion(
        spec=good_spec,
        adapter=PhilHealthPdfAdapter(good_spec, provider_category="Hospital"),
        session=db_session,
    )
    assert first.status == "published"
    good_release = db_session.get(Release, first.release_id)
    assert good_release is not None
    assert good_release.ingestion_status == "published"
    assert good_release.publication_status == "published"

    linked_facility_ids = db_session.scalars(
        select(FacilitySourceLink.facility_id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .where(SourceRecord.release_id == good_release.id)
    ).all()
    assert linked_facility_ids
    facility_id = linked_facility_ids[0]
    facility = db_session.get(Facility, facility_id)
    assert facility is not None
    assert facility.publication_status == "public"

    failed_spec = _spec(
        token,
        label_suffix="-B",
        content=philhealth_pdf(layout="official"),
    )
    failed = run_ingestion(
        spec=failed_spec,
        adapter=_FailingAdapter(failed_spec, provider_category="Hospital"),
        session=db_session,
    )
    assert failed.status == "failed"
    failed_release = db_session.get(Release, failed.release_id)
    assert failed_release is not None
    assert failed_release.ingestion_status == "failed"
    assert failed_release.publication_status == "quarantined"

    db_session.refresh(good_release)
    db_session.refresh(facility)
    assert good_release.publication_status == "published"
    assert facility.publication_status == "public"


def test_repeated_ingestion_is_idempotent(db_session) -> None:
    from philfacilities_api.models import Release, SourceRecord

    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    adapter = PhilHealthPdfAdapter(spec, provider_category="Hospital")

    first = run_ingestion(spec=spec, adapter=adapter, session=db_session)
    assert first.status == "published"
    release = db_session.get(Release, first.release_id)
    assert release is not None
    dataset_id = release.dataset_id
    record_count = db_session.scalar(
        select(func.count()).select_from(SourceRecord).where(SourceRecord.release_id == release.id)
    )
    assert record_count

    second = run_ingestion(spec=spec, adapter=adapter, session=db_session)
    assert second.status == "skipped_duplicate"
    assert second.release_id == first.release_id
    assert (
        db_session.scalar(
            select(func.count()).select_from(Release).where(Release.dataset_id == dataset_id)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(SourceRecord.release_id == release.id)
        )
        == record_count
    )


def test_release_comparison_reports_rows_and_links_without_mutation(db_session) -> None:
    from philfacilities_ingest.compare import compare_releases

    token = uuid.uuid4().hex[:10]
    first_spec = _spec(token, label_suffix="-A")
    second_spec = _spec(
        token,
        label_suffix="-B",
        content=philhealth_pdf(layout="official"),
    )

    first = run_ingestion(
        spec=first_spec,
        adapter=PhilHealthPdfAdapter(first_spec, provider_category="Hospital"),
        session=db_session,
    )
    second = run_ingestion(
        spec=second_spec,
        adapter=PhilHealthPdfAdapter(second_spec, provider_category="Hospital"),
        session=db_session,
    )
    assert first.status == "published"
    assert second.status == "published"

    report = compare_releases(db_session, dataset_slug=first_spec.dataset_slug)
    assert report["from"]["release_label"] == first_spec.release_label
    assert report["to"]["release_label"] == second_spec.release_label

    records = report["source_records"]
    assert records["from"] > 0
    assert records["to"] > 0
    assert records["added"] + records["retained"] == records["to"]
    assert records["removed"] + records["retained"] == records["from"]
    assert len(records["sample_added"]) <= 10
    assert len(records["sample_removed"]) <= 10
    assert len(records["sample_changed_payload"]) <= 10

    links = report["facility_links"]
    assert links["added"] + links["retained"] == links["to"]
    assert links["removed"] + links["retained"] == links["from"]

    explicit = compare_releases(
        db_session,
        dataset_slug=first_spec.dataset_slug,
        from_label=first_spec.release_label,
        to_label=second_spec.release_label,
    )
    assert explicit["from"]["release_id"] == report["from"]["release_id"]
    assert explicit["to"]["release_id"] == report["to"]["release_id"]


def test_row_count_anomaly_detects_large_changes() -> None:
    from philfacilities_ingest.pipeline import row_count_anomaly

    assert row_count_anomaly(100, 90) is None
    assert row_count_anomaly(100, 60) is None
    assert row_count_anomaly(100, 49) == {
        "previous_count": 100,
        "current_count": 49,
        "ratio": 0.49,
    }
    assert row_count_anomaly(100, 201) == {
        "previous_count": 100,
        "current_count": 201,
        "ratio": 2.01,
    }
    assert row_count_anomaly(10, 0) is None
    assert row_count_anomaly(None, 100) is None
