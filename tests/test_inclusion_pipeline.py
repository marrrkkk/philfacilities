"""Ownership-inclusive ingestion invariants.

These tests exercise the pipeline with synthetic, internal-only releases so they
do not perturb public fixture counts. They cover the rules that cannot be proven
from parser output alone:

* a licence/accreditation never turns a private provider into a government facility;
* conflicting provider sectors stay unknown and internal;
* enrichment-only releases cannot demote an already-classified facility;
* a government service counter hosted in a private building keeps its own class;
* review-required sources never publish records even when the parser succeeds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import ClassVar

import pytest
from philfacilities_ingest.contracts import (
    AccreditationData,
    FacilityCandidate,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    RoleData,
    ValidationResult,
)
from philfacilities_ingest.pipeline import run_ingestion
from sqlalchemy import select

pytestmark = pytest.mark.integration


class _StaticAdapter:
    """Minimal adapter that returns pre-built candidates from one synthetic row."""

    parser_version = "test-static-v1"
    schema_version = "test-static-v1"
    expected_columns: ClassVar[dict[str, set[str]]] = {"row": {"name"}}
    source_code = "synthetic"

    def __init__(
        self,
        spec: ReleaseSpec,
        candidates: list[FacilityCandidate],
        *,
        warning: str | None = None,
    ) -> None:
        self.spec = spec
        self.candidates = candidates
        self.warning = warning

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows = [
            ParsedRow(
                source_record_key=candidate.source_record_key,
                row_reference=candidate.row_reference,
                raw_payload={"name": candidate.display_name},
                normalized_payload={"name": candidate.display_name},
            )
            for candidate in self.candidates
        ]
        warnings = [{"code": self.warning, "message": self.warning}] if self.warning else []
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=warnings,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        return ValidationResult(
            issues=[],
            accepted_rows=len(parsed.rows),
            rejected_rows=0,
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        return self.candidates


def _spec(token: str, *, suffix: str = "", agency: str | None = None) -> ReleaseSpec:
    agency_code = agency or f"test-inclusion-{token}"
    return ReleaseSpec(
        agency_code=agency_code,
        agency_name="Synthetic inclusion-policy test agency",
        dataset_slug=f"test-inclusion-{token}",
        dataset_name="Synthetic inclusion-policy test release",
        release_label=f"TEST-INCLUSION-{token}{suffix}",
        filename=f"inclusion-{token}{suffix}.json",
        content=f'{{"token":"{token}","suffix":"{suffix}"}}'.encode(),
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


def _candidate(
    key: str,
    name: str,
    *,
    entity_id: str | None = None,
    ownership: str = "unknown",
    ownership_type: str = "UNKNOWN",
    inclusion_class: str | None = None,
    sector_code: str | None = None,
    roles: list[RoleData] | None = None,
    facility_kind: str = "facility",
    latitude: float | None = None,
    longitude: float | None = None,
) -> FacilityCandidate:
    accreditations = []
    if sector_code is not None:
        accreditations.append(
            AccreditationData(
                authority="PhilHealth",
                provider_category="Hospital",
                sector_code=sector_code,
            )
        )
    return FacilityCandidate(
        source_record_key=key,
        row_reference=f"row:{key}",
        source_entity_id=entity_id or key,
        display_name=name,
        facility_type="health_facility",
        facility_subtype="HOSPITAL",
        facility_kind=facility_kind,
        ownership=ownership,
        ownership_type=ownership_type,
        inclusion_class=inclusion_class,
        public_access_class="SERVICE_USERS_ONLY",
        record_status="operational",
        location=LocationData(
            latitude=latitude,
            longitude=longitude,
            precision="source_gps" if latitude is not None else "unknown",
            method="synthetic_point" if latitude is not None else None,
        ),
        accreditations=accreditations,
        roles=roles or [],
    )


def _facility_for_release(db_session, release_id: str):
    from philfacilities_api.models import Facility, FacilitySourceLink, SourceRecord

    return db_session.scalars(
        select(Facility)
        .join(FacilitySourceLink, FacilitySourceLink.facility_id == Facility.id)
        .join(SourceRecord, SourceRecord.id == FacilitySourceLink.source_record_id)
        .where(SourceRecord.release_id == uuid.UUID(release_id))
    ).first()


def test_private_accreditation_never_implies_government_ownership(db_session) -> None:
    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    candidate = _candidate(
        "private-provider",
        "Synthetic Private Accredited Hospital",
        ownership="private",
        ownership_type="PRIVATE_UNSPECIFIED",
        inclusion_class="PRIVATE_PUBLIC_SERVICE_PROVIDER",
        sector_code="P",
    )

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    assert facility.ownership == "private"
    assert facility.ownership_type == "PRIVATE_UNSPECIFIED"
    assert facility.inclusion_class == "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    assert facility.publication_status == "internal"


def test_conflicting_sector_codes_stay_unknown_and_internal(db_session) -> None:
    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    entity_id = "mixed-sector-provider"
    candidates = [
        _candidate("mixed-g", "Synthetic Mixed Hospital", entity_id=entity_id, sector_code="G"),
        _candidate("mixed-p", "Synthetic Mixed Hospital", entity_id=entity_id, sector_code="P"),
    ]

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, candidates),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    assert facility.ownership == "unknown"
    assert facility.ownership_type == "UNKNOWN"
    assert facility.inclusion_class == "DISCOVERY_CANDIDATE"
    assert facility.publication_status == "internal"


def test_duplicate_entity_rows_replace_the_current_location(db_session) -> None:
    """A repeated agency ID maps to one facility; only one location stays current."""

    from philfacilities_api.models import FacilityLocation

    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    entity_id = "duplicate-osm-node"
    candidates = [
        _candidate(
            "duplicate-a",
            "Synthetic Duplicate Feature",
            entity_id=entity_id,
            latitude=14.100001,
            longitude=121.100001,
        ),
        _candidate(
            "duplicate-b",
            "Synthetic Duplicate Feature",
            entity_id=entity_id,
            latitude=14.200002,
            longitude=121.200002,
        ),
    ]

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, candidates),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    locations = db_session.scalars(
        select(FacilityLocation)
        .where(FacilityLocation.facility_id == facility.id)
        .order_by(FacilityLocation.created_at)
    ).all()
    current = [location for location in locations if location.is_current]
    retired = [location for location in locations if not location.is_current]
    assert len(current) == 1
    assert len(retired) == 1
    assert float(current[0].latitude) == 14.200002
    assert retired[0].valid_to is not None


def test_enrichment_release_cannot_demote_classified_facility(db_session) -> None:
    token = uuid.uuid4().hex[:10]
    entity_id = "stable-classified-provider"
    first_spec = _spec(token, suffix="-A")
    first_candidate = _candidate(
        "classified",
        "Synthetic Classified Hospital",
        entity_id=entity_id,
        ownership="government",
        ownership_type="NATIONAL_GOVERNMENT",
        inclusion_class="GOVERNMENT_FACILITY",
    )
    first = run_ingestion(
        spec=first_spec,
        adapter=_StaticAdapter(first_spec, [first_candidate]),
        session=db_session,
    )
    assert first.status == "published"

    second_spec = _spec(token, suffix="-B")
    second_candidate = _candidate(
        "classified-enrichment",
        "Synthetic Classified Hospital",
        entity_id=entity_id,
        ownership="unknown",
        ownership_type="UNKNOWN",
        inclusion_class=None,
    )
    second = run_ingestion(
        spec=second_spec,
        adapter=_StaticAdapter(second_spec, [second_candidate]),
        session=db_session,
    )
    assert second.status == "published"

    facility = _facility_for_release(db_session, second.release_id)
    assert facility is not None
    assert facility.ownership == "government"
    assert facility.ownership_type == "NATIONAL_GOVERNMENT"
    assert facility.inclusion_class == "GOVERNMENT_FACILITY"
    assert facility.publication_status == "internal"


def test_hosted_government_counter_keeps_its_own_class_and_host_role(db_session) -> None:
    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    candidate = _candidate(
        "hosted-counter",
        "Synthetic Hosted Government Service Counter",
        ownership="government",
        ownership_type="NATIONAL_GOVERNMENT",
        inclusion_class="GOVERNMENT_FACILITY",
        roles=[
            RoleData(
                role_type="HOST",
                entity_name="Synthetic Private Mall",
                entity_type="PRIVATE_CORPORATE",
                evidence={"basis": "address text names the host premises"},
            )
        ],
        facility_kind="facility_unit",
    )

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    assert facility.facility_kind == "facility_unit"
    assert facility.inclusion_class == "GOVERNMENT_FACILITY"
    assert facility.ownership == "government"

    from philfacilities_api.models import FacilityRole

    roles = db_session.scalars(
        select(FacilityRole).where(FacilityRole.facility_id == facility.id)
    ).all()
    assert [(role.role_type, role.entity_name) for role in roles] == [
        ("HOST", "Synthetic Private Mall")
    ]


def test_review_required_release_marks_every_record_internal(db_session) -> None:
    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    candidate = _candidate(
        "rights-gated",
        "Synthetic Rights-Gated Post Office",
        ownership="government",
        ownership_type="GOCC",
        inclusion_class="GOVERNMENT_FACILITY",
    )

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate], warning="internal_only_rights"),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    assert facility.publication_status == "internal"
