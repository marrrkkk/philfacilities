from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

# A release that rejects more than 10% of its rows is treated as schema drift
# rather than a slightly dirty snapshot. The row floor keeps tiny releases
# (a handful of offices) from being failed on one legitimately malformed row.
DEFAULT_MINIMUM_ACCEPTANCE_RATE = 0.90
DEFAULT_MINIMUM_ACCEPTANCE_ROWS = 20


@dataclass
class ReleaseSpec:
    agency_code: str
    agency_name: str
    dataset_slug: str
    dataset_name: str
    release_label: str
    filename: str
    content: bytes
    source_url: str | None = None
    source_published_at: datetime | None = None
    retrieved_at: datetime | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    terms_url: str | None = None
    redistribution_status: str = "unknown"
    rights_basis: str | None = None
    attribution_text: str | None = None
    personal_data_status: str | None = None
    requested_publication_status: str | None = None
    access_method: str = "fixture"
    update_pattern: str | None = None
    license_identifier: str | None = None
    authority_level: str | None = None
    coverage_scope: str | None = None
    coverage_note: str | None = None
    is_synthetic: bool = False
    enqueue_cross_source_matches: bool = True
    notes: str | None = None
    # Release-level acceptance policy. A release below the floor is quarantined
    # before any canonical row is touched.
    minimum_acceptance_rate: float = DEFAULT_MINIMUM_ACCEPTANCE_RATE
    minimum_acceptance_rows: int = DEFAULT_MINIMUM_ACCEPTANCE_ROWS
    # Recorded on the publication gate when an operator reviews a manual import
    # or reconciles a registry rights decision.
    rights_reviewer: str | None = None
    rights_review_note: str | None = None


@dataclass
class ParsedRow:
    source_record_key: str
    row_reference: str
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any]
    validation_status: str = "valid"


@dataclass
class ParsedRelease:
    rows: list[ParsedRow]
    parser_version: str
    schema_version: str
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    details: dict[str, Any] | None = None
    row_reference: str | None = None


@dataclass
class ValidationResult:
    issues: list[ValidationIssue]
    accepted_rows: int
    rejected_rows: int
    # Row references whose validation failed. The pipeline uses this set to
    # exclude rejected rows from candidate application without re-scanning the
    # issue list, and records it in the run report for reconciliation.
    rejected_row_references: set[str] = field(default_factory=set)
    # True when the release must not touch canonical rows at all (for example a
    # schema-valid file whose rows all failed validation). The pipeline decides
    # this before candidate application, not after.
    failed: bool = False


@dataclass
class LocationData:
    latitude: float | None = None
    longitude: float | None = None
    precision: str = "unknown"
    method: str | None = None
    address_text: str | None = None
    postal_code: str | None = None
    psgc_code: str | None = None
    review_status: str = "source_supplied"


@dataclass
class ContactData:
    """An institutional contact channel supplied by one source record."""

    contact_type: str
    value: str
    label: str | None = None
    source_field: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass(slots=True)
class EnrollmentData:
    school_year: str
    grade_level: str
    sex: str = "all"
    learner_count: int | None = None


@dataclass
class ResourceData:
    school_year: str
    resource_category: str
    resource_code: str
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None


@dataclass
class SchoolData:
    deped_school_id: str | None = None
    sector: str | None = None
    school_management: str | None = None
    division: str | None = None
    district: str | None = None
    legislative_district: str | None = None
    settlement_type: str | None = None
    offering_classification: str | None = None
    offers_es: bool | None = None
    offers_jhs: bool | None = None
    offers_shs: bool | None = None
    reference_school_year: str | None = None
    enrollment: list[EnrollmentData] = field(default_factory=list)
    resources: list[ResourceData] = field(default_factory=list)


@dataclass
class HealthData:
    doh_facility_id: str | None = None
    facility_major_type: str | None = None
    facility_type_detail: str | None = None
    facility_category: str | None = None
    ownership_subclassification: str | None = None
    licensing_status: str | None = None
    bed_capacity: int | None = None


@dataclass
class UtilityData:
    doe_facility_code: str | None = None
    resource_type: str | None = None
    technology_type: str | None = None
    connection_type: str | None = None
    grid: str | None = None
    owner_type: str | None = None
    contract_type: str | None = None
    installed_mw: float | None = None
    dependable_mw: float | None = None
    number_of_units: int | None = None
    date_commissioned: str | None = None


@dataclass
class LicenseData:
    issuing_authority: str | None = None
    license_number: str | None = None
    license_type: str | None = None
    source_status: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None


@dataclass
class AccreditationData:
    authority: str
    provider_category: str
    benefit_package: str | None = None
    accreditation_category: str | None = None
    bed_count: int | None = None
    sector_code: str | None = None
    source_status: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    source_as_of: date | None = None
    telephone: str | None = None
    email: str | None = None
    street_address: str | None = None
    municipality: str | None = None
    page_reference: str | None = None


@dataclass
class FunctionData:
    function_code: str
    source_value: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    capacity_value: float | None = None
    capacity_unit: str | None = None
    designation_status: str | None = None
    evidence: dict[str, Any] | None = None


@dataclass
class ServiceData:
    service_code: str
    service_name: str | None = None
    source_field: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    details: dict[str, Any] | None = None


@dataclass
class RoleData:
    role_type: str
    entity_name: str
    entity_type: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    evidence: dict[str, Any] | None = None


@dataclass
class FacilityCandidate:
    source_record_key: str
    row_reference: str
    display_name: str
    facility_type: str
    facility_subtype: str | None
    ownership: str
    record_status: str
    location: LocationData
    source_entity_id: str | None = None
    facility_kind: str = "facility"
    inclusion_class: str | None = None
    ownership_type: str = "UNKNOWN"
    operator_type: str = "UNKNOWN"
    public_access_class: str = "UNKNOWN"
    access_conditions: str | None = None
    functions: list[FunctionData] = field(default_factory=list)
    services: list[ServiceData] = field(default_factory=list)
    roles: list[RoleData] = field(default_factory=list)
    contacts: list[ContactData] = field(default_factory=list)
    school: SchoolData | None = None
    health: HealthData | None = None
    utility: UtilityData | None = None
    licenses: list[LicenseData] = field(default_factory=list)
    accreditations: list[AccreditationData] = field(default_factory=list)
    # An enrichment release fills only missing or placeholder canonical values
    # on an existing facility. It never renames the facility, never replaces an
    # established classification, and never changes the source record that owns
    # an existing school profile.
    enrichment_only: bool = False
    # Some enrichment releases are stale or community-compiled snapshots whose
    # rows must never become new facilities. They link only to a facility that
    # already carries the same agency entity ID; unmatched rows stay as source
    # evidence and are recorded as unresolved.
    link_only: bool = False


class SourceAdapter(Protocol):
    """Contract every source adapter must satisfy.

    Acquisition belongs to the connector (see ``sources.connectors``).  The
    generic pipeline owns preserve/resolve/publish/report; adapters own only
    parse, validation, and normalization.
    """

    source_code: str
    parser_version: str
    schema_version: str

    def parse(self, spec: ReleaseSpec) -> ParsedRelease: ...

    def validate(self, parsed: ParsedRelease) -> ValidationResult: ...

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]: ...
