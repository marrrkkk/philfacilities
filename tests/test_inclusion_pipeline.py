"""Ownership-inclusive ingestion invariants.

These tests exercise the pipeline with isolated test-only releases. Publication
tests use a non-synthetic, rights-cleared release so the API gate cannot take its
synthetic shortcut. They cover the rules that cannot be proven from parser output
alone:

* a licence/accreditation never turns a private provider into a government facility;
* conflicting provider sectors stay unknown and carry the unclassified label;
* unclassified records in a rights-cleared release are published with the
  explicit unclassified label and remain visible through the public API gate;
* enrichment-only releases cannot demote an already-classified facility;
* a government service counter hosted in a private building keeps its own class;
* review-required sources never publish records even when the parser succeeds.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import ClassVar

import pytest
from philfacilities_ingest.contracts import (
    AccreditationData,
    ContactData,
    FacilityCandidate,
    HealthData,
    LicenseData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    RoleData,
    SchoolData,
    UtilityData,
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


def _public_spec(token: str, *, suffix: str = "") -> ReleaseSpec:
    """A non-synthetic release with a reviewed public-rights decision."""

    spec = _spec(token, suffix=suffix)
    return replace(
        spec,
        redistribution_status="publicly_available_verified",
        requested_publication_status="published",
        access_method="manual_file",
        license_identifier=None,
        is_synthetic=False,
        notes="Test-only release with a reviewed public-rights decision; not an official dataset.",
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
        record_status="unknown",
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


def test_conflicting_sector_codes_stay_unclassified(db_session) -> None:
    """Mixed sector evidence is labelled, not treated as a publication block."""

    from philfacilities_api.services import facility_is_public

    token = uuid.uuid4().hex[:10]
    spec = _public_spec(token)
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
    assert facility.publication_status == "public"
    assert facility_is_public(db_session, facility)


def test_unclassified_record_in_public_release_is_published(db_session) -> None:
    """Unknown ownership is a label, not a publication block."""

    from philfacilities_api.services import facility_is_public

    token = uuid.uuid4().hex[:10]
    spec = _public_spec(token)
    candidate = _candidate(
        "unclassified-provider",
        "Synthetic Unclassified Clinic",
        ownership="unknown",
        ownership_type="UNKNOWN",
        inclusion_class=None,
    )

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    assert facility.ownership == "unknown"
    assert facility.ownership_type == "UNKNOWN"
    assert facility.inclusion_class == "DISCOVERY_CANDIDATE"
    assert facility.publication_status == "public"
    # The facility must not take the synthetic shortcut in the API gate.
    assert facility.is_synthetic is False
    assert facility_is_public(db_session, facility)


def test_enrichment_release_keeps_unclassified_facility_public(db_session) -> None:
    """A later unknown-ownership row must not demote an already-public record."""

    token = uuid.uuid4().hex[:10]
    entity_id = "stable-unclassified-provider"
    first_spec = _public_spec(token, suffix="-A")
    first_candidate = _candidate(
        "unclassified-first",
        "Synthetic Stable Unclassified Clinic",
        entity_id=entity_id,
    )
    first = run_ingestion(
        spec=first_spec,
        adapter=_StaticAdapter(first_spec, [first_candidate]),
        session=db_session,
    )
    assert first.status == "published"

    second_spec = _public_spec(token, suffix="-B")
    second_candidate = _candidate(
        "unclassified-enrichment",
        "Synthetic Stable Unclassified Clinic",
        entity_id=entity_id,
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
    assert facility.inclusion_class == "DISCOVERY_CANDIDATE"
    assert facility.publication_status == "public"


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


def test_enrichment_only_fills_gaps_without_renaming_or_replacing(db_session) -> None:
    """A masterlist enrichment fills unknown values and keeps established ones."""

    from philfacilities_api.models import SchoolProfile

    token = uuid.uuid4().hex[:10]
    entity_id = "stable-enrichment-school"
    school_id = f"TEST-{token}"
    first_spec = _public_spec(token, suffix="-A")
    first_candidate = replace(
        _candidate(
            "enrichment-base",
            "Synthetic Original School Name",
            entity_id=entity_id,
        ),
        facility_type="school",
        facility_subtype="OTHER_SCHOOL",
        public_access_class="UNKNOWN",
        record_status="active_in_registry",
        school=SchoolData(
            deped_school_id=school_id,
            sector=None,
            school_management="DepED Managed",
        ),
    )
    first = run_ingestion(
        spec=first_spec,
        adapter=_StaticAdapter(first_spec, [first_candidate]),
        session=db_session,
    )
    assert first.status == "published"

    facility = _facility_for_release(db_session, first.release_id)
    assert facility is not None
    assert facility.ownership == "unknown"
    assert facility.inclusion_class == "DISCOVERY_CANDIDATE"
    profile = db_session.scalars(
        select(SchoolProfile).where(
            SchoolProfile.facility_id == facility.id,
            SchoolProfile.deped_school_id == school_id,
        )
    ).one()
    original_profile_record = profile.source_record_id

    second_spec = _public_spec(token, suffix="-B")
    second_candidate = replace(
        _candidate(
            "enrichment-fill",
            "Different Name From Enrichment Source",
            entity_id=entity_id,
            ownership="government",
            ownership_type="GOVERNMENT_UNSPECIFIED",
            inclusion_class="GOVERNMENT_FACILITY",
        ),
        facility_type="school",
        facility_subtype="OTHER_SCHOOL",
        public_access_class="UNKNOWN",
        record_status="active_in_registry",
        school=SchoolData(
            deped_school_id=school_id,
            sector="public",
            school_management="Private",
        ),
        enrichment_only=True,
    )
    second = run_ingestion(
        spec=second_spec,
        adapter=_StaticAdapter(second_spec, [second_candidate]),
        session=db_session,
    )
    assert second.status == "published"

    facility = _facility_for_release(db_session, second.release_id)
    assert facility is not None
    assert facility.display_name == "Synthetic Original School Name"
    assert facility.ownership == "government"
    assert facility.ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert facility.inclusion_class == "GOVERNMENT_FACILITY"

    db_session.refresh(profile)
    assert profile.sector == "public"
    assert profile.school_management == "DepED Managed"
    assert profile.source_record_id == original_profile_record

    # A later enrichment that contradicts an established value cannot replace
    # it: only genuinely missing values are fillable.
    third_spec = _public_spec(token, suffix="-C")
    third_candidate = replace(
        _candidate(
            "enrichment-conflict",
            "Third Name Must Not Win",
            entity_id=entity_id,
            ownership="private",
            ownership_type="PRIVATE_UNSPECIFIED",
            inclusion_class="PRIVATE_PUBLIC_SERVICE_PROVIDER",
        ),
        facility_type="school",
        facility_subtype="PUBLIC_SCHOOL",
        public_access_class="UNKNOWN",
        record_status="inactive",
        school=SchoolData(
            deped_school_id=school_id,
            sector="private",
            school_management="Private",
        ),
        enrichment_only=True,
    )
    third = run_ingestion(
        spec=third_spec,
        adapter=_StaticAdapter(third_spec, [third_candidate]),
        session=db_session,
    )
    assert third.status == "published"

    facility = _facility_for_release(db_session, third.release_id)
    assert facility is not None
    assert facility.display_name == "Synthetic Original School Name"
    assert facility.facility_subtype == "OTHER_SCHOOL"
    assert facility.record_status == "active_in_registry"
    assert facility.ownership == "government"
    assert facility.ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert facility.inclusion_class == "GOVERNMENT_FACILITY"

    db_session.refresh(profile)
    assert profile.sector == "public"
    assert profile.school_management == "DepED Managed"
    assert profile.source_record_id == original_profile_record


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


def test_contacts_and_postal_code_are_persisted_with_source_provenance(db_session) -> None:
    from philfacilities_api.models import FacilityContact, FacilityLocation

    token = uuid.uuid4().hex[:10]
    spec = _spec(token)
    candidate = _candidate(
        "contact-provider",
        "Synthetic Contact Hospital",
        ownership="government",
        ownership_type="GOVERNMENT_UNSPECIFIED",
        inclusion_class="GOVERNMENT_FACILITY",
        latitude=14.599512,
        longitude=120.984222,
    )
    candidate.location.postal_code = "1000"
    candidate.contacts = [
        ContactData("phone", "+63 2 8555 0100", source_field="telephone"),
        ContactData("email", "records@example.test", source_field="email"),
    ]

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert result.status == "published"
    assert result.stats["contacts"] == 2

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    contacts = db_session.scalars(
        select(FacilityContact).where(FacilityContact.facility_id == facility.id)
    ).all()
    assert {(row.contact_type, row.value) for row in contacts} == {
        ("phone", "+63 2 8555 0100"),
        ("email", "records@example.test"),
    }
    assert all(row.source_record_id is not None for row in contacts)
    location = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(True),
        )
    ).one()
    assert location.postal_code == "1000"


def test_doe_utility_profile_is_written_with_source_assertions(db_session) -> None:
    """A DOE row creates one utility profile keyed by facility and DOE code."""

    from philfacilities_api.models import AttributeAssertion, UtilityProfile

    token = uuid.uuid4().hex[:10]
    code = f"DOE-{token}"
    spec = _public_spec(token)
    candidate = replace(
        _candidate(code, "Synthetic Power Plant", entity_id=code),
        facility_type="utility_facility",
        facility_subtype="POWER_PLANT",
        utility=UtilityData(
            doe_facility_code=code,
            resource_type="Coal",
            technology_type="Circulating Fluidized Bed (CFB) Coal",
            connection_type="Grid-connected",
            grid="Luzon",
            owner_type="NON-NPC/IPP",
            installed_mw=83.7,
            dependable_mw=80.0,
            number_of_units=1,
            date_commissioned="2016",
        ),
    )
    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert result.status == "published"

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    profile = db_session.scalars(
        select(UtilityProfile).where(UtilityProfile.facility_id == facility.id)
    ).one()
    assert profile.doe_facility_code == code
    assert profile.resource_type == "Coal"
    assert float(profile.installed_mw) == 83.7
    assert profile.number_of_units == 1
    assert profile.source_record_id is not None

    attributes = set(
        db_session.scalars(
            select(AttributeAssertion.attribute_name).where(
                AttributeAssertion.facility_id == facility.id
            )
        ).all()
    )
    assert {
        "utility.resource_type",
        "utility.technology_type",
        "utility.connection_type",
        "utility.grid",
        "utility.owner_type",
        "utility.installed_mw",
        "utility.dependable_mw",
        "utility.number_of_units",
        "utility.date_commissioned",
    } <= attributes


def test_force_reapply_rewrites_a_missing_utility_profile(db_session) -> None:
    """An explicit reapply recreates derived rows that a new profile table adds."""

    from philfacilities_api.models import AttributeAssertion, UtilityProfile

    token = uuid.uuid4().hex[:10]
    code = f"DOE-{token}"
    spec = _public_spec(token)
    candidate = replace(
        _candidate(code, "Synthetic Force-Reapply Plant", entity_id=code),
        facility_type="utility_facility",
        facility_subtype="POWER_PLANT",
        utility=UtilityData(
            doe_facility_code=code,
            resource_type="Coal",
            technology_type="Circulating Fluidized Bed (CFB) Coal",
            connection_type="Grid-connected",
            grid="Luzon",
            owner_type="NON-NPC/IPP",
            installed_mw=83.7,
            dependable_mw=80.0,
            number_of_units=1,
            date_commissioned="2016",
        ),
    )
    first = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert first.status == "published"

    facility = _facility_for_release(db_session, first.release_id)
    assert facility is not None
    profile = db_session.scalars(
        select(UtilityProfile).where(UtilityProfile.facility_id == facility.id)
    ).one()
    db_session.delete(profile)
    for claim in db_session.scalars(
        select(AttributeAssertion).where(
            AttributeAssertion.facility_id == facility.id,
            AttributeAssertion.attribute_name.like("utility.%"),
        )
    ).all():
        db_session.delete(claim)
    db_session.flush()

    second = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
        reprocess=True,
        force_reapply=True,
    )
    assert second.status == "published"
    assert second.stats["forced_reapply"] is True
    assert second.stats["reprocess_skipped_unchanged"] == 0

    recreated = db_session.scalars(
        select(UtilityProfile).where(UtilityProfile.facility_id == facility.id)
    ).one()
    assert recreated.doe_facility_code == code
    assert recreated.resource_type == "Coal"
    assert recreated.source_record_id is not None
    attributes = set(
        db_session.scalars(
            select(AttributeAssertion.attribute_name).where(
                AttributeAssertion.facility_id == facility.id
            )
        ).all()
    )
    assert "utility.installed_mw" in attributes
    assert "utility.doe_facility_code" in attributes


def test_nhfr_health_enrichment_matches_cross_agency_doh_code(db_session) -> None:
    """An NHFR row links to the facility already carrying its DOH code."""

    from philfacilities_api.models import HealthLicense, HealthProfile

    token = uuid.uuid4().hex[:10]
    doh_code = f"DOH{token:0>12}"[:22]
    first_spec = _public_spec(token, suffix="-NHA")
    first_candidate = replace(
        _candidate(
            "nha-health-base",
            "Synthetic Established Hospital",
            entity_id="nha-health-1",
            latitude=14.5,
            longitude=121.0,
        ),
        health=HealthData(
            doh_facility_id=doh_code,
            facility_category="Hospital",
        ),
    )
    first = run_ingestion(
        spec=first_spec,
        adapter=_StaticAdapter(first_spec, [first_candidate]),
        session=db_session,
    )
    assert first.status == "published"
    facility = _facility_for_release(db_session, first.release_id)
    assert facility is not None
    profile = db_session.scalars(
        select(HealthProfile).where(HealthProfile.doh_facility_id == doh_code)
    ).one()
    original_profile_record = profile.source_record_id

    second_spec = replace(
        _public_spec(token, suffix="-NHFR"),
        agency_code="doh",
        dataset_slug=f"test-doh-nhfr-{token}",
    )
    second_candidate = replace(
        _candidate(
            doh_code,
            "Different Official Registry Name",
            entity_id=doh_code,
            ownership="government",
            ownership_type="LOCAL_GOVERNMENT",
            inclusion_class="GOVERNMENT_FACILITY",
        ),
        facility_subtype="INFIRMARY",
        health=HealthData(
            doh_facility_id=doh_code,
            facility_major_type="Health Facility",
            facility_type_detail="Infirmary",
            facility_category="Infirmary",
            ownership_subclassification="Local Government Unit",
            licensing_status="With License",
            bed_capacity=25,
        ),
        licenses=[
            LicenseData(
                issuing_authority="Department of Health",
                license_type="Infirmary",
                source_status="With License",
                valid_until=date(2026, 12, 31),
            )
        ],
        enrichment_only=True,
    )
    second = run_ingestion(
        spec=second_spec,
        adapter=_StaticAdapter(second_spec, [second_candidate]),
        session=db_session,
    )
    assert second.status == "published"
    assert second.stats["facilities_created"] == 0

    db_session.refresh(facility)
    assert facility.display_name == "Synthetic Established Hospital"
    assert facility.facility_subtype == "HOSPITAL"
    assert facility.ownership == "government"
    assert facility.ownership_type == "LOCAL_GOVERNMENT"
    assert facility.inclusion_class == "GOVERNMENT_FACILITY"

    db_session.refresh(profile)
    assert profile.facility_category == "Hospital"
    assert profile.facility_major_type == "Health Facility"
    assert profile.facility_type_detail == "Infirmary"
    assert profile.ownership_subclassification == "Local Government Unit"
    assert profile.licensing_status == "With License"
    assert profile.bed_capacity == 25
    assert profile.source_record_id == original_profile_record
    license_row = db_session.scalars(
        select(HealthLicense).where(HealthLicense.facility_id == facility.id)
    ).one()
    assert license_row.source_status == "With License"

    from philfacilities_api.models import FacilitySourceLink, SourceRecord

    link = db_session.scalars(
        select(FacilitySourceLink)
        .join(SourceRecord, SourceRecord.id == FacilitySourceLink.source_record_id)
        .where(SourceRecord.release_id == second.release_id)
    ).one()
    assert link.match_method == "exact_doh_facility_code"
    assert link.evidence["matched_doh_facility_id"] == doh_code


def test_nhfr_creates_new_official_health_facility(db_session) -> None:
    """An unmatched official DOH code creates one new facility and profile."""

    from philfacilities_api.models import HealthProfile

    token = uuid.uuid4().hex[:10]
    doh_code = f"DOH{token:0>12}"[:22]
    spec = replace(
        _public_spec(token, suffix="-NHFR"),
        agency_code="doh",
        dataset_slug=f"test-doh-nhfr-new-{token}",
    )
    candidate = replace(
        _candidate(
            doh_code,
            "Synthetic New Rural Health Unit",
            entity_id=doh_code,
            ownership="government",
            ownership_type="LOCAL_GOVERNMENT",
            inclusion_class="GOVERNMENT_FACILITY",
        ),
        facility_subtype="RURAL_HEALTH_UNIT",
        health=HealthData(
            doh_facility_id=doh_code,
            facility_major_type="Health Facility",
            facility_type_detail="Rural Health Unit",
            facility_category="Rural Health Unit",
            ownership_subclassification="Local Government Unit",
            licensing_status="With License",
            bed_capacity=0,
        ),
        enrichment_only=True,
    )

    result = run_ingestion(
        spec=spec,
        adapter=_StaticAdapter(spec, [candidate]),
        session=db_session,
    )
    assert result.status == "published"
    assert result.stats["facilities_created"] == 1

    facility = _facility_for_release(db_session, result.release_id)
    assert facility is not None
    assert facility.facility_type == "health_facility"
    assert facility.facility_subtype == "RURAL_HEALTH_UNIT"
    assert facility.ownership == "government"
    assert facility.ownership_type == "LOCAL_GOVERNMENT"
    assert facility.inclusion_class == "GOVERNMENT_FACILITY"
    profile = db_session.scalars(
        select(HealthProfile).where(HealthProfile.facility_id == facility.id)
    ).one()
    assert profile.doh_facility_id == doh_code
    assert profile.facility_category == "Rural Health Unit"
    assert profile.licensing_status == "With License"
    assert profile.bed_capacity == 0


def test_nhfr_does_not_create_a_facility_for_an_ambiguous_doh_code(db_session) -> None:
    """A DOH code already mapped to two facilities stays unresolved."""

    from philfacilities_api.models import HealthProfile, QualityIssue
    from sqlalchemy import update

    token = uuid.uuid4().hex[:10]
    shared_code = f"DOH-SHARED-{token}"
    first_spec = _public_spec(token, suffix="-AMBIG")
    candidates = [
        replace(
            _candidate(
                f"ambiguous-{index}",
                f"Synthetic Ambiguous Health Facility {index}",
                entity_id=f"ambiguous-entity-{index}",
            ),
            health=HealthData(doh_facility_id=f"{shared_code}-{index}"),
        )
        for index in (1, 2)
    ]
    first = run_ingestion(
        spec=first_spec,
        adapter=_StaticAdapter(first_spec, candidates),
        session=db_session,
    )
    assert first.status == "published"
    assert first.stats["facilities_created"] == 2

    db_session.execute(
        update(HealthProfile)
        .where(HealthProfile.doh_facility_id.in_([f"{shared_code}-1", f"{shared_code}-2"]))
        .values(doh_facility_id=shared_code)
    )
    db_session.commit()

    second_spec = replace(
        _public_spec(token, suffix="-AMBIG-NHFR"),
        agency_code="doh",
        dataset_slug=f"test-doh-nhfr-ambiguous-{token}",
    )
    candidate = replace(
        _candidate(
            shared_code,
            "Synthetic Ambiguous Official Row",
            entity_id=shared_code,
            ownership="government",
            ownership_type="GOVERNMENT_UNSPECIFIED",
            inclusion_class="GOVERNMENT_FACILITY",
        ),
        health=HealthData(doh_facility_id=shared_code),
        enrichment_only=True,
    )
    second = run_ingestion(
        spec=second_spec,
        adapter=_StaticAdapter(second_spec, [candidate]),
        session=db_session,
    )
    assert second.status == "published"
    assert second.stats["facilities_created"] == 0
    assert second.stats["unresolved"] == 1
    issue = db_session.scalars(
        select(QualityIssue).where(QualityIssue.issue_code == "ambiguous_doh_facility_code")
    ).one()
    assert issue.details == {"doh_facility_id": shared_code}
