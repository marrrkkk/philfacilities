"""Pipeline hardening: gates, locks, gating, replay, and governance."""

from __future__ import annotations

import hashlib
import json
import types
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from philfacilities_api.db import SessionLocal
from philfacilities_api.models import (
    Dataset,
    Facility,
    FacilityFunction,
    FacilityLocation,
    FacilityService,
    IngestionRun,
    PublicationGate,
    QualityIssue,
    Release,
    SchoolProfile,
    SourceRecord,
)
from philfacilities_ingest.acquisition import send_ingestion_failure_alert
from philfacilities_ingest.cli import app as cli_app
from philfacilities_ingest.config import get_settings
from philfacilities_ingest.contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    SchoolData,
    ServiceData,
    ValidationIssue,
    ValidationResult,
)
from philfacilities_ingest.pipeline import run_ingestion
from philfacilities_ingest.pipeline.locking import (
    IngestionLockError,
    dataset_ingestion_lock,
)
from philfacilities_ingest.pipeline.release import ensure_source
from philfacilities_ingest.replay import replay_manifest
from philfacilities_ingest.sources.registry import apply_publication_decisions
from philfacilities_ingest.storage import build_store
from sqlalchemy import func, select
from typer.testing import CliRunner

pytestmark = pytest.mark.integration


class _ScriptedAdapter:
    """Parse a fixed candidate list and report a scripted validation outcome."""

    source_code = "synthetic"

    def __init__(
        self,
        candidates: list[FacilityCandidate],
        *,
        parser_version: str = "hardening-v1",
        schema_version: str = "hardening-schema-v1",
        accepted: int | None = None,
        rejected: int | None = None,
    ) -> None:
        self.candidates = candidates
        self.parser_version = parser_version
        self.schema_version = schema_version
        self.accepted = accepted
        self.rejected = rejected

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
        total = len(parsed.rows)
        accepted = self.accepted if self.accepted is not None else total
        rejected = self.rejected if self.rejected is not None else total - accepted
        issues = [
            ValidationIssue(
                "synthetic_rejected",
                "error",
                "Synthetic row rejected for the hardening test.",
                row_reference=row.row_reference,
            )
            for row in parsed.rows[accepted : accepted + rejected]
        ]
        return ValidationResult(
            issues=issues,
            accepted_rows=accepted,
            rejected_rows=rejected,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        return self.candidates


def _spec(
    *,
    token: str,
    agency_code: str | None = None,
    dataset_slug: str | None = None,
    content: bytes | None = None,
    is_synthetic: bool = True,
    requested_publication_status: str | None = None,
    retrieved_at: datetime | None = None,
    minimum_acceptance_rate: float = 0.90,
    minimum_acceptance_rows: int = 20,
) -> ReleaseSpec:
    dataset_slug = dataset_slug or f"hardening-{token}"
    return ReleaseSpec(
        agency_code=agency_code or f"test-hardening-{token}",
        agency_name=f"Hardening test agency {token}",
        dataset_slug=dataset_slug,
        dataset_name=f"Hardening test dataset {token}",
        release_label=f"TEST-HARDENING-{token}-{dataset_slug}",
        filename=f"{dataset_slug}-{token}.json",
        content=content or f'{{"token":"{token}","dataset":"{dataset_slug}"}}'.encode(),
        source_url=None,
        source_published_at=datetime(2026, 1, 1, tzinfo=UTC),
        retrieved_at=retrieved_at or datetime.now(UTC),
        reference_period_start=date(2026, 1, 1),
        reference_period_end=date(2026, 1, 31),
        redistribution_status=("not_applicable" if is_synthetic else "publicly_available_verified"),
        access_method="synthetic_fixture" if is_synthetic else "manual_file",
        requested_publication_status=requested_publication_status,
        license_identifier=("Synthetic fixture; no source-data rights" if is_synthetic else None),
        is_synthetic=is_synthetic,
        notes="Test-only release; not an official dataset.",
        minimum_acceptance_rate=minimum_acceptance_rate,
        minimum_acceptance_rows=minimum_acceptance_rows,
    )


def _candidate(
    *,
    key: str,
    name: str,
    entity_id: str | None = None,
    facility_type: str = "government_office",
    ownership: str = "government",
    inclusion_class: str = "GOVERNMENT_FACILITY",
    latitude: float | None = None,
    longitude: float | None = None,
    precision: str = "unknown",
    method: str | None = None,
    school: SchoolData | None = None,
    functions: list[FunctionData] | None = None,
    services: list[ServiceData] | None = None,
) -> FacilityCandidate:
    return FacilityCandidate(
        source_record_key=f"record-{key}",
        row_reference=f"row-{key}",
        display_name=name,
        facility_type=facility_type,
        facility_subtype=None,
        ownership=ownership,
        record_status="active_in_registry",
        location=LocationData(
            latitude=latitude,
            longitude=longitude,
            precision=precision,
            method=method,
        ),
        source_entity_id=entity_id or f"entity-{key}",
        inclusion_class=inclusion_class,
        school=school,
        functions=functions or [],
        services=services or [],
    )


def _release_for(db_session, dataset_slug: str) -> Release:
    return db_session.scalars(
        select(Release)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(Dataset.slug == dataset_slug)
        .order_by(Release.retrieved_at.desc())
    ).first()


def test_acceptance_floor_quarantines_before_canonical_writes(db_session) -> None:
    token = uuid.uuid4().hex[:8]
    candidates = [
        _candidate(key=f"{token}-{index}", name=f"Acceptance Floor Facility {index}")
        for index in range(10)
    ]
    spec = _spec(
        token=token,
        dataset_slug=f"acceptance-{token}",
        content=b'{"rows":10}',
        minimum_acceptance_rate=0.90,
        minimum_acceptance_rows=1,
    )
    facilities_before = db_session.scalar(select(func.count()).select_from(Facility))

    result = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter(candidates, accepted=1, rejected=9),
        session=db_session,
    )

    db_session.expire_all()
    assert result.status == "failed"
    assert result.stats["acceptance_floor_failed"] is True
    assert result.stats["acceptance_rate"] == 0.1
    assert db_session.scalar(select(func.count()).select_from(Facility)) == facilities_before

    release = db_session.get(Release, uuid.UUID(result.release_id))
    assert release is not None
    assert release.ingestion_status == "failed"
    assert release.publication_status == "quarantined"
    issue = db_session.scalars(
        select(QualityIssue).where(
            QualityIssue.release_id == release.id,
            QualityIssue.issue_code == "acceptance_rate_below_floor",
        )
    ).first()
    assert issue is not None


def test_empty_release_is_quarantined(db_session) -> None:
    token = uuid.uuid4().hex[:8]
    spec = _spec(token=token, dataset_slug=f"empty-{token}", content=b'{"rows":0}')

    result = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter([], accepted=0, rejected=0),
        session=db_session,
    )

    assert result.status == "failed"
    assert result.stats["release_failed"] is True
    release = db_session.get(Release, uuid.UUID(result.release_id))
    assert release is not None
    assert release.ingestion_status == "failed"
    assert release.publication_status == "quarantined"
    issue = db_session.scalars(
        select(QualityIssue).where(
            QualityIssue.release_id == release.id,
            QualityIssue.issue_code == "release_empty",
        )
    ).first()
    assert issue is not None


def test_unexpected_apply_error_leaves_release_quarantined(db_session) -> None:
    token = uuid.uuid4().hex[:8]
    candidate = _candidate(
        key=token,
        name=f"Broken Inclusion Class {token}",
        inclusion_class="NOT_A_REAL_CLASS",
    )
    spec = _spec(token=token, dataset_slug=f"unexpected-{token}", content=b'{"rows":1}')

    with pytest.raises(ValueError, match="Unsupported inclusion class"):
        run_ingestion(
            spec=spec,
            adapter=_ScriptedAdapter([candidate], accepted=1),
            session=db_session,
        )

    db_session.expire_all()
    release = _release_for(db_session, spec.dataset_slug)
    assert release is not None
    assert release.ingestion_status == "failed"
    assert release.publication_status == "quarantined"
    run = db_session.scalars(
        select(IngestionRun).where(IngestionRun.release_id == release.id)
    ).first()
    assert run is not None
    assert run.status == "failed"


def test_dataset_lock_fails_fast_for_a_second_worker(db_session) -> None:
    agency = f"lock-agency-{uuid.uuid4().hex[:8]}"
    dataset = "lock-dataset"
    first = SessionLocal()
    second = SessionLocal()
    try:
        with (
            dataset_ingestion_lock(first, agency_code=agency, dataset_slug=dataset),
            pytest.raises(IngestionLockError),
            dataset_ingestion_lock(second, agency_code=agency, dataset_slug=dataset),
        ):
            pytest.fail("The second worker must not enter the locked block.")
    finally:
        first.close()
        second.close()


def test_internal_release_cannot_rewrite_public_facility_or_leak_children(
    db_session, client
) -> None:
    token = uuid.uuid4().hex[:8]
    agency = f"test-gating-{token}"
    public_dataset = f"public-{token}"
    internal_dataset = f"internal-{token}"
    shared_entity = f"shared-entity-{token}"
    public_name = f"Public Source School {token}"
    internal_name = f"Internal Overwrite School {token}"
    public_deped_id = f"PUB-{token}"
    internal_deped_id = f"INT-{token}"

    public_school = SchoolData(
        deped_school_id=public_deped_id,
        sector="public",
        school_management="deped",
        offers_es=True,
        offers_jhs=True,
        offers_shs=True,
    )
    public_candidate = _candidate(
        key=f"public-{token}",
        name=public_name,
        entity_id=shared_entity,
        facility_type="school",
        latitude=14.5995,
        longitude=120.9842,
        precision="barangay_centroid",
        method="source_centroid",
        school=public_school,
        functions=[FunctionData(function_code="classroom")],
        services=[ServiceData(service_code="elementary", service_name="Elementary")],
    )
    public_result = run_ingestion(
        spec=_spec(
            token=token,
            agency_code=agency,
            dataset_slug=public_dataset,
            content=b'{"release":"public"}',
            is_synthetic=False,
        ),
        adapter=_ScriptedAdapter([public_candidate], accepted=1),
        session=db_session,
    )
    assert public_result.status == "published"

    db_session.expire_all()
    facility = db_session.scalars(
        select(Facility).where(Facility.display_name == public_name)
    ).one()
    assert facility.publication_status == "public"
    public_record = db_session.scalars(
        select(SourceRecord).where(SourceRecord.release_id == uuid.UUID(public_result.release_id))
    ).one()

    internal_school = SchoolData(
        deped_school_id=internal_deped_id,
        sector="private",
        offers_shs=False,
    )
    internal_candidate = _candidate(
        key=f"internal-{token}",
        name=internal_name,
        entity_id=shared_entity,
        facility_type="school",
        ownership="private",
        inclusion_class="PRIVATE_PUBLIC_SERVICE_PROVIDER",
        latitude=10.0,
        longitude=122.0,
        precision="source_gps",
        method="source_gps",
        school=internal_school,
        functions=[FunctionData(function_code="library")],
        services=[ServiceData(service_code="feeding", service_name="Feeding")],
    )
    internal_result = run_ingestion(
        spec=_spec(
            token=token,
            agency_code=agency,
            dataset_slug=internal_dataset,
            content=b'{"release":"internal"}',
            is_synthetic=False,
            requested_publication_status="internal_only",
        ),
        adapter=_ScriptedAdapter([internal_candidate], accepted=1),
        session=db_session,
    )
    assert internal_result.status == "published"

    db_session.expire_all()
    facility = db_session.get(Facility, facility.id)
    assert facility is not None
    assert facility.display_name == public_name
    assert facility.ownership == "government"
    assert facility.publication_status == "public"

    current_location = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(True),
        )
    ).one()
    assert float(current_location.latitude) == pytest.approx(14.5995)
    assert float(current_location.longitude) == pytest.approx(120.9842)
    assert current_location.source_record_id == public_record.id

    internal_record = db_session.scalars(
        select(SourceRecord).where(SourceRecord.release_id == uuid.UUID(internal_result.release_id))
    ).one()
    internal_location = db_session.scalars(
        select(FacilityLocation).where(FacilityLocation.source_record_id == internal_record.id)
    ).one()
    assert internal_location.is_current is False

    public_profile = db_session.scalars(
        select(SchoolProfile).where(SchoolProfile.facility_id == facility.id)
    ).all()
    assert [profile.deped_school_id for profile in public_profile] == [public_deped_id]
    assert public_profile[0].sector == "public"
    assert public_profile[0].offers_shs is True
    assert (
        db_session.scalars(
            select(SchoolProfile).where(
                SchoolProfile.facility_id == facility.id,
                SchoolProfile.deped_school_id == internal_deped_id,
            )
        ).first()
        is None
    )

    # The internal evidence is stored, but every public read path filters it.
    assert (
        db_session.scalars(
            select(FacilityFunction).where(FacilityFunction.source_record_id == internal_record.id)
        )
        .one()
        .function_code
        == "library"
    )
    assert (
        db_session.scalars(
            select(FacilityService).where(FacilityService.source_record_id == internal_record.id)
        )
        .one()
        .service_code
        == "feeding"
    )

    response = client.get(f"/v1/facilities/{facility.slug}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["display_name"] == public_name
    assert detail["school"]["sector"] == "public"
    assert detail["school"]["offers_shs"] is True
    assert [row["function_code"] for row in detail["function_details"]] == ["classroom"]
    assert [row["service_code"] for row in detail["services"]] == ["elementary"]
    assert float(detail["location"]["latitude"]) == pytest.approx(14.5995)
    assert {source["dataset_slug"] for source in detail["sources"]} == {public_dataset}

    sources = client.get(f"/v1/facilities/{facility.slug}/sources").json()
    assert [source["dataset_slug"] for source in sources] == [public_dataset]

    assertions = client.get(
        f"/v1/facilities/{facility.slug}/assertions", params={"attribute": "display_name"}
    ).json()
    assert assertions
    assert {row["source"]["dataset_slug"] for row in assertions} == {public_dataset}

    assert client.get(f"/v1/schools/{facility.slug}/enrollment").status_code == 404


def test_latest_published_release_controls_current_membership(db_session, client) -> None:
    token = uuid.uuid4().hex[:8]
    agency = f"test-latest-{token}"
    dataset_slug = f"latest-{token}"
    first_name = f"First Release Facility {token}"
    second_name = f"Second Release Facility {token}"
    first_spec = _spec(
        token=token,
        agency_code=agency,
        dataset_slug=dataset_slug,
        content=b'{"release":"first"}',
        is_synthetic=False,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    first = run_ingestion(
        spec=first_spec,
        adapter=_ScriptedAdapter([_candidate(key=f"first-{token}", name=first_name)], accepted=1),
        session=db_session,
    )
    assert first.status == "published"
    db_session.expire_all()
    first_facility = db_session.scalars(
        select(Facility).where(Facility.display_name == first_name)
    ).one()
    assert client.get(f"/v1/facilities/{first_facility.slug}").status_code == 200

    second_spec = _spec(
        token=token,
        agency_code=agency,
        dataset_slug=dataset_slug,
        content=b'{"release":"second"}',
        is_synthetic=False,
        retrieved_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    second = run_ingestion(
        spec=second_spec,
        adapter=_ScriptedAdapter([_candidate(key=f"second-{token}", name=second_name)], accepted=1),
        session=db_session,
    )
    assert second.status == "published"
    db_session.expire_all()
    second_facility = db_session.scalars(
        select(Facility).where(Facility.display_name == second_name)
    ).one()

    # The first release is no longer the dataset's latest published snapshot.
    assert client.get(f"/v1/facilities/{first_facility.slug}").status_code == 404
    assert client.get(f"/v1/facilities/{second_facility.slug}").status_code == 200

    failed_spec = _spec(
        token=token,
        agency_code=agency,
        dataset_slug=dataset_slug,
        content=b'{"release":"failed"}',
        is_synthetic=False,
        retrieved_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    failed = run_ingestion(
        spec=failed_spec,
        adapter=_ScriptedAdapter(
            [_candidate(key=f"failed-{token}", name=f"Failed Release {token}")],
            accepted=0,
            rejected=1,
        ),
        session=db_session,
    )
    assert failed.status == "failed"

    # A failed newer attempt does not displace the last good release.
    assert client.get(f"/v1/facilities/{second_facility.slug}").status_code == 200


def test_failed_reprocess_keeps_last_good_release_visible_and_retries(db_session, client) -> None:
    token = uuid.uuid4().hex[:8]
    dataset_slug = f"failed-reprocess-{token}"
    original_name = f"Stable Reprocess Facility {token}"
    failed_name = f"Failed Overwrite Facility {token}"
    spec = _spec(
        token=token,
        dataset_slug=dataset_slug,
        content=b'{"release":"stable"}',
    )
    original = _candidate(key=f"stable-{token}", name=original_name)
    first = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter([original], accepted=1),
        session=db_session,
    )
    assert first.status == "published"
    release_id = uuid.UUID(first.release_id)
    db_session.expire_all()
    release = db_session.get(Release, release_id)
    assert release is not None
    record = db_session.scalars(
        select(SourceRecord).where(SourceRecord.release_id == release.id)
    ).one()
    record_id = record.id
    record_payload = dict(record.raw_payload)
    facility = db_session.scalars(
        select(Facility).where(Facility.display_name == original_name)
    ).one()
    assert client.get(f"/v1/facilities/{facility.slug}").status_code == 200

    failed = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter(
            [_candidate(key=f"stable-{token}", name=failed_name)],
            accepted=0,
            rejected=1,
        ),
        session=db_session,
        reprocess=True,
    )
    assert failed.status == "failed"
    assert failed.stats["staging_skipped"] == "published_reprocess_failed"
    assert uuid.UUID(failed.release_id) == release_id
    db_session.expire_all()
    release = db_session.get(Release, release_id)
    assert release is not None
    assert release.ingestion_status == "published"
    assert release.publication_status == "published"
    record = db_session.get(SourceRecord, record_id)
    assert record is not None
    assert record.raw_payload == record_payload
    assert (
        db_session.scalars(select(SourceRecord).where(SourceRecord.release_id == release_id))
        .one()
        .id
        == record_id
    )
    # The last good canonical snapshot is still public.
    assert client.get(f"/v1/facilities/{facility.slug}").status_code == 200

    retry = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter([original], accepted=1),
        session=db_session,
    )
    # A failed run must not turn the unchanged checksum into skipped_duplicate.
    assert retry.status == "published"
    assert retry.release_id == first.release_id


def test_parser_version_change_reprocesses_without_a_flag(db_session) -> None:
    token = uuid.uuid4().hex[:8]
    spec = _spec(token=token, dataset_slug=f"parser-{token}", content=b'{"rows":1}')
    candidate = _candidate(key=token, name=f"Parser Version Facility {token}")

    first = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter([candidate], accepted=1, parser_version="v1"),
        session=db_session,
    )
    assert first.status == "published"
    release = db_session.get(Release, uuid.UUID(first.release_id))
    assert release is not None
    assert release.parser_version == "v1"
    assert release.schema_version == "hardening-schema-v1"

    second = run_ingestion(
        spec=spec,
        adapter=_ScriptedAdapter(
            [candidate],
            accepted=1,
            parser_version="v2",
            schema_version="hardening-schema-v2",
        ),
        session=db_session,
    )

    assert second.status == "published"
    assert second.stats["parser_reprocess"] is True
    db_session.expire_all()
    release = db_session.get(Release, uuid.UUID(first.release_id))
    assert release is not None
    assert release.parser_version == "v2"
    assert release.schema_version == "hardening-schema-v2"


def test_replay_manifest_verifies_and_reprocesses_the_same_release(db_session) -> None:
    token = uuid.uuid4().hex[:8]
    settings = get_settings()
    store = build_store(settings)
    identifier = int(token[:6], 16)
    artifact = json.dumps(
        {
            "retrieved_at": "2026-01-01T00:00:00+00:00",
            "regions": ["NCR"],
            "record_count": 1,
            "records": [
                {
                    "id": identifier,
                    "region": "NCR",
                    "province": "Metro Manila",
                    "city": "Makati",
                    "name": f"Replay Negosyo Center {token}",
                    "address": "Synthetic replay address",
                    "is_active": True,
                }
            ],
        }
    ).encode()
    stored = store.preserve(
        agency="dti",
        dataset="dti-negosyo-centers",
        release_label=f"REPLAY-{token}",
        filename=f"dti-replay-{token}.json",
        content=artifact,
    )
    manifest = Path(settings.report_dir).parent / f"replay-{token}.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "source": "dti-negosyo",
                        "raw_object_uri": stored.uri,
                        "release_label": f"REPLAY-{token}",
                        "filename": f"dti-replay-{token}.json",
                        "sha256": hashlib.sha256(artifact).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    first = replay_manifest(session=db_session, settings=settings, manifest_path=manifest)
    assert first[0]["status"] == "published"
    release_id = uuid.UUID(first[0]["release_id"])
    release = db_session.get(Release, release_id)
    assert release is not None

    second_manifest = manifest.with_name(f"replay-id-{token}.json")
    second_manifest.write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "source": "dti-negosyo",
                        "release_id": str(release_id),
                        "filename": f"dti-replay-{token}.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    second = replay_manifest(session=db_session, settings=settings, manifest_path=second_manifest)
    assert second[0]["status"] == "published"
    assert uuid.UUID(second[0]["release_id"]) == release_id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(SourceRecord.release_id == release_id)
        )
        == 1
    )

    Path(stored.uri).write_bytes(b'{"tampered":true}')
    tampered = replay_manifest(session=db_session, settings=settings, manifest_path=manifest)
    assert tampered[0]["status"] == "failed"
    assert "SHA-256" in tampered[0]["error"] or "mismatch" in tampered[0]["error"]

    unknown_manifest = manifest.with_name(f"replay-unknown-{token}.json")
    unknown_manifest.write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "source": "not-a-real-source",
                        "raw_object_uri": stored.uri,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    unknown = replay_manifest(session=db_session, settings=settings, manifest_path=unknown_manifest)
    assert unknown[0]["status"] == "failed"
    assert "Unknown source" in unknown[0]["error"]


def test_manual_public_decisions_require_a_reviewer(db_session) -> None:
    with pytest.raises(ValueError, match="reviewer"):
        apply_publication_decisions(db_session, keys=["dti-negosyo"])
    db_session.rollback()


def test_ensure_source_records_the_rights_reviewer(db_session) -> None:
    token = uuid.uuid4().hex[:8]
    spec = _spec(
        token=token,
        dataset_slug=f"reviewer-{token}",
        is_synthetic=False,
        requested_publication_status="approved",
    )
    spec.rights_reviewer = "Test Reviewer"
    spec.rights_review_note = "Reviewed the source terms for this test."

    _agency, _dataset, gate = ensure_source(db_session, spec)
    db_session.flush()
    assert gate.reviewer == "Test Reviewer"
    assert gate.reviewed_at is not None
    assert gate.notes == "Reviewed the source terms for this test."
    stored = db_session.scalars(
        select(PublicationGate).where(PublicationGate.dataset_id == gate.dataset_id)
    ).one()
    assert stored.reviewer == "Test Reviewer"
    db_session.rollback()


def test_manual_ingest_cli_requires_a_reviewer_for_public_rights(tmp_path) -> None:
    artifact = tmp_path / "manual.csv"
    artifact.write_bytes(b"name\nSynthetic manual import\n")
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "ingest-file",
            "doh",
            str(artifact),
            "--release-label",
            "MANUAL-TEST",
            "--dataset",
            "manual-test",
            "--redistribution-status",
            "approved_public_redistribution",
        ],
    )

    assert result.exit_code != 0
    assert "reviewer" in result.output.lower()


def test_ingestion_failure_alert_only_reports_failed_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(204, request=httpx.Request("POST", url))

    monkeypatch.setattr("philfacilities_ingest.acquisition.httpx.post", fake_post)
    settings = types.SimpleNamespace(alert_webhook_url="https://alerts.invalid/hook")

    assert (
        send_ingestion_failure_alert(
            settings,
            [{"key": "ok", "status": "published"}],
            command="test",
        )
        is False
    )
    assert captured == {}

    assert (
        send_ingestion_failure_alert(
            settings,
            [{"key": "broken", "status": "failed", "error": "boom"}],
            command="test",
        )
        is True
    )
    payload = captured["json"]
    assert payload["failures"]["broken:0"]["error"] == "boom"
