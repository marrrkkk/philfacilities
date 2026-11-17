"""Release-level validation failure must not touch canonical facilities.

The runner records a governed failure and stages the rejected rows for audit,
but applies no candidate. This is the regression guard for the old behaviour
where validation was evaluated only after the apply loop had already mutated
canonical rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from philfacilities_ingest.contracts import (
    FacilityCandidate,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from philfacilities_ingest.pipeline import run_ingestion
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


class _RejectingAdapter:
    """Parse one row, then reject it at release level."""

    source_code = "synthetic"
    parser_version = "test-validation-gate-v1"
    schema_version = "test-validation-gate-v1"

    def __init__(self, candidates: list[FacilityCandidate]) -> None:
        self.candidates = candidates

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        return ParsedRelease(
            rows=[
                ParsedRow(
                    source_record_key=candidate.source_record_key,
                    row_reference=candidate.row_reference,
                    raw_payload={"name": candidate.display_name},
                    normalized_payload={"name": candidate.display_name},
                )
                for candidate in self.candidates
            ],
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        return ValidationResult(
            issues=[
                ValidationIssue(
                    code="missing_coordinates",
                    severity="fatal",
                    message="Synthetic row rejected to exercise the release gate.",
                    row_reference=parsed.rows[0].row_reference,
                )
            ],
            accepted_rows=0,
            rejected_rows=len(parsed.rows),
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        return self.candidates


def _spec(token: str) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code=f"test-validation-gate-{token}",
        agency_name="Synthetic validation-gate test agency",
        dataset_slug=f"test-validation-gate-{token}",
        dataset_name="Synthetic validation-gate release",
        release_label=f"TEST-VALIDATION-GATE-{token}",
        filename=f"validation-gate-{token}.json",
        content=f'{{"token":"{token}"}}'.encode(),
        source_url=None,
        source_published_at=datetime.now(UTC),
        retrieved_at=datetime.now(UTC),
        reference_period_start=date(2026, 1, 1),
        reference_period_end=date(2026, 1, 1),
        redistribution_status="review_required",
        access_method="synthetic_fixture",
        license_identifier="Synthetic fixture; no source-data rights",
        requested_publication_status="internal_only",
        is_synthetic=True,
        notes="Test-only release; not an official dataset.",
    )


def _candidate(token: str) -> FacilityCandidate:
    return FacilityCandidate(
        source_record_key=f"validation-gate-{token}",
        row_reference="row-1",
        display_name=f"Synthetic Validation Gate Facility {token}",
        facility_type="hospital",
        facility_subtype=None,
        ownership="government",
        record_status="active",
        location=LocationData(latitude=None, longitude=None, precision="unknown"),
        source_entity_id=f"validation-gate-{token}",
    )


def test_validation_failure_skips_canonical_apply(db_session) -> None:
    from philfacilities_api.models import Facility, QualityIssue, Release, SourceRecord

    token = uuid.uuid4().hex[:8]
    spec = _spec(token)
    candidate = _candidate(token)
    facilities_before = db_session.scalar(select(func.count()).select_from(Facility))

    result = run_ingestion(
        spec=spec,
        adapter=_RejectingAdapter([candidate]),
        session=db_session,
    )

    db_session.expire_all()
    facilities_after = db_session.scalar(select(func.count()).select_from(Facility))
    assert facilities_after == facilities_before
    assert result.status == "failed"
    assert result.stats["release_failed"] is True
    assert result.stats["apply_skipped"] == "validation_failed"
    assert result.stats["rejected_row_references"] == 1

    release = db_session.scalar(select(Release).where(Release.id == uuid.UUID(result.release_id)))
    assert release is not None
    assert release.ingestion_status == "failed"

    # Rejected rows remain staged for audit, but they are not published.
    staged = db_session.scalar(
        select(func.count()).select_from(SourceRecord).where(SourceRecord.release_id == release.id)
    )
    assert staged == 1
    record = db_session.scalar(select(SourceRecord).where(SourceRecord.release_id == release.id))
    assert record is not None
    assert record.validation_status == "rejected"
    issue = db_session.scalar(
        select(QualityIssue).where(
            QualityIssue.release_id == release.id,
            QualityIssue.issue_code == "missing_coordinates",
        )
    )
    assert issue is not None
    assert issue.source_record_id == record.id


class _DuplicateKeyAdapter:
    """Parse two physical rows that share one source business key."""

    source_code = "synthetic"
    parser_version = "test-duplicate-retention-v1"
    schema_version = "test-duplicate-retention-v1"

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        return ParsedRelease(
            rows=[
                ParsedRow(
                    source_record_key="duplicate-business-key",
                    row_reference="row-1",
                    raw_payload={"name": "First physical row"},
                    normalized_payload={"name": "First physical row"},
                ),
                ParsedRow(
                    source_record_key="duplicate-business-key",
                    row_reference="row-2",
                    raw_payload={"name": "Second physical row"},
                    normalized_payload={"name": "Second physical row"},
                ),
            ],
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        return ValidationResult(
            issues=[
                ValidationIssue(
                    code="duplicate_source_record",
                    severity="error",
                    message="The source business key appears twice.",
                    row_reference="row-2",
                )
            ],
            accepted_rows=1,
            rejected_rows=1,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        return [
            FacilityCandidate(
                source_record_key=row.source_record_key,
                row_reference=row.row_reference,
                display_name=row.normalized_payload["name"],
                facility_type="hospital",
                facility_subtype=None,
                ownership="government",
                record_status="active",
                location=LocationData(latitude=None, longitude=None, precision="unknown"),
                source_entity_id=row.source_record_key,
            )
            for row in parsed.rows
        ]


def test_duplicate_business_key_rows_are_retained_and_rejected(db_session) -> None:
    from philfacilities_api.models import QualityIssue, Release, SourceRecord

    token = uuid.uuid4().hex[:8]
    result = run_ingestion(
        spec=_spec(token),
        adapter=_DuplicateKeyAdapter(),
        session=db_session,
    )

    assert result.status == "published"
    assert result.stats["parsed_rows"] == 2
    assert result.stats["rejected_rows_by_code"] == {"duplicate_source_record": 1}
    release = db_session.scalar(select(Release).where(Release.id == uuid.UUID(result.release_id)))
    assert release is not None
    records = db_session.scalars(
        select(SourceRecord)
        .where(SourceRecord.release_id == release.id)
        .order_by(SourceRecord.row_number_or_page)
    ).all()
    assert len(records) == 2
    assert [record.validation_status for record in records] == ["valid", "rejected"]
    assert records[0].source_record_key == "duplicate-business-key"
    assert records[1].source_record_key.startswith("duplicate-business-key#staged-dup-")
    issue = db_session.scalar(
        select(QualityIssue).where(
            QualityIssue.release_id == release.id,
            QualityIssue.issue_code == "duplicate_source_record",
        )
    )
    assert issue is not None
    assert issue.source_record_id == records[1].id
