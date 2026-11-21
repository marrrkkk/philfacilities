from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from philfacilities_api.taxonomy import (
    ACCESS_CLASSES,
    CONTACT_TYPES,
    FACILITY_CATEGORIES,
    INCLUSION_CLASSES,
    OWNERSHIP_TYPES,
    OWNERSHIP_VALUES,
    RECORD_STATUSES,
)

FacilityType = Literal[*FACILITY_CATEGORIES]
InclusionClass = Literal[*INCLUSION_CLASSES]
Ownership = Literal[*OWNERSHIP_VALUES]
OwnershipType = Literal[*OWNERSHIP_TYPES]
OperatorType = OwnershipType
AccessClass = Literal[*ACCESS_CLASSES]
FacilityKind = Literal[
    "facility",
    "site",
    "building",
    "facility_unit",
    "infrastructure_asset",
    "project",
]
CoverageScope = Literal[
    # Legacy value still present in earlier retained source datasets.
    "NATIONAL",
    "NATIONAL_OFFICIAL_INVENTORY",
    "NATIONAL_PARTIAL",
    "REGIONAL",
    "PARTICIPATING_LGUS",
    "SELECTED_LGUS",
    "SINGLE_LGU",
    "DIRECTORY_SUBSET",
    "DISCOVERY_LAYER",
    "UNKNOWN_COVERAGE",
]
RecordStatus = Literal[*RECORD_STATUSES]
ContactType = Literal[*CONTACT_TYPES]
LocationPrecision = Literal[
    "gps_verified",
    "field_verified",
    "source_gps",
    "map_geocoded",
    "barangay_centroid",
    "unknown",
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LocationOut(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    precision: LocationPrecision = "unknown"
    method: str | None = None
    address_text: str | None = None
    postal_code: str | None = None
    psgc_code: str | None = None
    review_status: str | None = None


class GeographyOut(BaseModel):
    psgc_code: str | None = None
    psgc_release: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    province_code: str | None = None
    province_name: str | None = None
    municipality_code: str | None = None
    municipality_name: str | None = None
    barangay_code: str | None = None
    barangay_name: str | None = None
    # PSGC barangay classification (``U``/``R``), normalised for clients. A
    # blank or ``-`` value in the source stays unknown rather than being guessed.
    urban_rural: Literal["urban", "rural"] | None = None


class QualityWarning(BaseModel):
    code: str
    severity: str
    message: str


class FacilityQuality(BaseModel):
    identity_status: str = "source_linked"
    location_precision: LocationPrecision = "unknown"
    warnings: list[QualityWarning] = Field(default_factory=list)
    source_count: int = 0


class SourceEvidence(BaseModel):
    id: uuid.UUID
    agency: str
    agency_code: str
    dataset: str
    dataset_slug: str
    release_id: uuid.UUID
    release_label: str
    source_record_id: str
    source_record_uuid: uuid.UUID
    row_reference: str | None = None
    source_published_at: datetime | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    retrieved_at: datetime
    processed_at: datetime | None = None
    match_method: str
    match_status: str
    match_confidence: float
    rights_status: str = "unknown"
    publication_status: str = "blocked"
    license_identifier: str | None = None
    attribution_text: str | None = None
    is_synthetic: bool = False


class AttributeAssertionOut(BaseModel):
    """One source's claim about one canonical field."""

    id: uuid.UUID
    attribute: str
    source_field: str | None = None
    raw_value: str | None = None
    normalized_value: str | None = None
    transformation_version: str | None = None
    review_status: str
    asserted_at: datetime
    source: SourceEvidence


class SchoolProfileOut(BaseModel):
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
    source_record_id: uuid.UUID | None = None


class ResourceObservationOut(BaseModel):
    school_year: str
    resource_category: str
    resource_code: str
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    observed_at: datetime
    source_record_id: uuid.UUID | None = None


class HealthProfileOut(BaseModel):
    doh_facility_id: str | None = None
    facility_major_type: str | None = None
    facility_type_detail: str | None = None
    facility_category: str | None = None
    ownership_subclassification: str | None = None
    licensing_status: str | None = None
    bed_capacity: int | None = None
    source_record_id: uuid.UUID | None = None


class UtilityProfileOut(BaseModel):
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
    source_record_id: uuid.UUID | None = None


class LicenseOut(BaseModel):
    id: uuid.UUID
    issuing_authority: str | None = None
    license_number: str | None = None
    license_type: str | None = None
    source_status: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    source_record_id: uuid.UUID | None = None


class AccreditationOut(BaseModel):
    id: uuid.UUID
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
    source_record_id: uuid.UUID | None = None


class AccreditationListItem(AccreditationOut):
    facility_id: uuid.UUID
    facility_slug: str | None = None
    facility_name: str
    facility_type: FacilityType
    is_synthetic: bool = False


class AccreditationListResponse(BaseModel):
    items: list[AccreditationListItem]
    total: int
    limit: int
    offset: int


class FacilityFunctionOut(BaseModel):
    function_code: str
    source_value: str | None = None
    source_record_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    capacity_value: float | None = None
    capacity_unit: str | None = None
    designation_status: str | None = None


class FacilityServiceOut(BaseModel):
    service_code: str
    service_name: str | None = None
    source_field: str | None = None
    source_record_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class FacilityRoleOut(BaseModel):
    role_type: str
    entity_name: str
    entity_type: str | None = None
    source_record_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    evidence: dict[str, Any] | None = None


class FacilityRelationshipOut(BaseModel):
    relationship_type: str
    related_facility_id: uuid.UUID
    related_facility_name: str | None = None
    related_facility_slug: str | None = None


class ContactOut(BaseModel):
    id: uuid.UUID
    contact_type: ContactType
    value: str
    label: str | None = None
    source_field: str | None = None
    source_record_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    review_status: str


class SourceRefOut(BaseModel):
    """Compact public identity of one source record behind a facility.

    Raw source values are preserved in the source record; this ref exists so a
    list result can distinguish registries that publish the same facility name.
    """

    agency_code: str
    dataset_slug: str
    source_record_id: str


class FacilitySummary(BaseModel):
    id: uuid.UUID
    slug: str | None = None
    display_name: str
    facility_type: FacilityType
    facility_subtype: str | None = None
    facility_kind: FacilityKind = "facility"
    inclusion_class: InclusionClass
    ownership: Ownership
    ownership_type: OwnershipType = "UNKNOWN"
    operator_type: OperatorType = "UNKNOWN"
    public_access_class: AccessClass = "UNKNOWN"
    record_status: RecordStatus
    publication_status: str
    is_synthetic: bool = False
    functions: list[str] = Field(default_factory=list)
    location: LocationOut
    geography: GeographyOut
    source_count: int = 0
    source_refs: list[SourceRefOut] = Field(default_factory=list)
    updated_at: datetime


class FacilityDetail(FacilitySummary):
    official_name: str | None = None
    access_conditions: str | None = None
    school: SchoolProfileOut | None = None
    health: HealthProfileOut | None = None
    utility: UtilityProfileOut | None = None
    accreditations: list[AccreditationOut] = Field(default_factory=list)
    contacts: list[ContactOut] = Field(default_factory=list)
    function_details: list[FacilityFunctionOut] = Field(default_factory=list)
    services: list[FacilityServiceOut] = Field(default_factory=list)
    roles: list[FacilityRoleOut] = Field(default_factory=list)
    relationships: list[FacilityRelationshipOut] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)
    quality: FacilityQuality
    created_at: datetime


class FacilityListResponse(BaseModel):
    items: list[FacilitySummary]
    next_cursor: str | None = None
    has_more: bool = False
    total: int
    limit: int


class FacilityMapResponse(BaseModel):
    items: list[FacilitySummary]
    limit: int
    truncated: bool = False
    bbox: str | None = None


class FacilityMapPoint(BaseModel):
    """Minimal map feature; deliberately excludes detail-only summary fields."""

    id: uuid.UUID
    slug: str | None = None
    name: str
    facility_type: FacilityType
    inclusion_class: InclusionClass
    precision: LocationPrecision = "unknown"
    latitude: float
    longitude: float


class FacilityMapCluster(BaseModel):
    latitude: float
    longitude: float
    count: int
    label: str


class FacilityMapPointsResponse(BaseModel):
    bbox: str
    zoom: int
    total: int
    mode: Literal["points", "clusters"]
    points: list[FacilityMapPoint] = Field(default_factory=list)
    clusters: list[FacilityMapCluster] = Field(default_factory=list)
    cell_deg: float | None = None
    truncated: bool = False


class NearbyResponse(BaseModel):
    items: list[FacilitySummary]
    center: dict[str, float]
    radius_m: int
    limit: int
    truncated: bool = False


class SchoolDetailResponse(BaseModel):
    facility: FacilityDetail
    resources: list[ResourceObservationOut]


class HealthDetailResponse(BaseModel):
    facility: FacilityDetail
    licenses: list[LicenseOut]
    accreditations: list[AccreditationOut]


class GeographyReleaseOut(ORMModel):
    id: uuid.UUID
    release_label: str
    reference_date: date | None = None
    published_at: datetime | None = None
    retrieved_at: datetime
    source_url: str | None = None
    is_synthetic: bool = False


class AdministrativeUnitOut(ORMModel):
    id: uuid.UUID
    release_id: uuid.UUID
    psgc_code: str
    name: str
    geographic_level: str
    parent_psgc_code: str | None = None
    correspondence_code: str | None = None
    old_name: str | None = None
    city_class: str | None = None
    income_classification: str | None = None
    urban_rural: str | None = None
    island_region: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class GeographyCrosswalkOut(BaseModel):
    from_psgc_code: str
    to_psgc_code: str | None = None
    change_type: str
    from_release: str
    to_release: str
    evidence: dict[str, Any] | None = None


class LatestReleaseOut(BaseModel):
    id: uuid.UUID
    label: str
    retrieved_at: datetime
    source_published_at: datetime | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    ingestion_status: str
    terms_review_status: str
    publication_status: str = "blocked"
    row_count_parsed: int | None = None
    sha256: str


class IngestionRunSummary(BaseModel):
    dataset: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report_path: str | None = None


class DatasetOut(BaseModel):
    id: uuid.UUID
    agency: str
    agency_code: str
    slug: str
    name: str
    description: str | None = None
    source_url: str | None = None
    access_method: str | None = None
    terms_url: str | None = None
    license_identifier: str | None = None
    redistribution_status: str
    rights_basis: str | None = None
    attribution_text: str | None = None
    personal_data_status: str | None = None
    publication_status: str = "blocked"
    coverage_scope: CoverageScope | None = None
    coverage_note: str | None = None
    update_pattern: str | None = None
    schema_version: str | None = None
    is_public_source: bool
    is_synthetic: bool
    publication_gate_status: str | None = None
    latest_release: LatestReleaseOut | None = None
    latest_geography_release: GeographyReleaseOut | None = None


class ReleaseOut(BaseModel):
    id: uuid.UUID
    dataset_slug: str
    dataset_name: str
    agency: str
    source_release_label: str
    source_published_at: datetime | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    retrieved_at: datetime
    processed_at: datetime | None = None
    file_format: str | None = None
    file_size_bytes: int | None = None
    row_count_parsed: int | None = None
    ingestion_status: str
    terms_review_status: str
    publication_status: str = "blocked"
    parser_version: str | None = None
    sha256: str


class SourceCheckOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_slug: str
    agency_code: str | None = None
    checked_at: datetime
    status: str
    url: str
    final_url: str | None = None
    http_status: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    sha256: str | None = None
    duration_ms: int | None = None
    message: str | None = None
    details: dict[str, Any] | None = None
    next_check_at: datetime | None = None


class SourceMonitoringOut(BaseModel):
    dataset_id: uuid.UUID
    dataset_slug: str
    dataset_name: str
    agency: str
    agency_code: str
    access_method: str | None = None
    rights_status: str
    publication_status: str
    last_checked_at: datetime | None = None
    last_successful_at: datetime | None = None
    check_status: str | None = None
    http_status: int | None = None
    last_message: str | None = None
    latest_release_label: str | None = None
    latest_release_at: datetime | None = None
    latest_release_rows: int | None = None
    latest_run_acceptance_rate: float | None = None
    latest_run_rejection_rate: float | None = None
    latest_run_status: str | None = None
    latest_run_at: datetime | None = None
    latest_run_duration_ms: float | None = None
    next_check_at: datetime | None = None
    warning: str | None = None


class QualityIssueOut(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID | None = None
    release_id: uuid.UUID | None = None
    issue_code: str
    severity: str
    message: str
    details: dict[str, Any] | None = None
    status: str
    created_at: datetime
    resolved_at: datetime | None = None


class QualitySummary(BaseModel):
    as_of: datetime
    facility_count: int
    published_facility_count: int
    synthetic_facility_count: int
    coordinate_precision: dict[str, int]
    open_issues_by_severity: dict[str, int]
    match_candidates_by_status: dict[str, int] = Field(default_factory=dict)
    datasets_by_redistribution_status: dict[str, int]
    last_successful_runs: list[IngestionRunSummary]
    caveats: list[str] = Field(default_factory=list)


class MatchCandidateOut(BaseModel):
    id: uuid.UUID
    candidate_key: str
    match_status: str
    match_method: str
    algorithm_version: str
    match_confidence: float
    source_record_id: uuid.UUID
    source_facility_id: uuid.UUID | None = None
    source_facility_name: str | None = None
    source_facility_slug: str | None = None
    candidate_facility_id: uuid.UUID | None = None
    candidate_facility_name: str | None = None
    candidate_facility_slug: str | None = None
    source_agency_code: str | None = None
    candidate_agency_code: str | None = None
    evidence: dict[str, Any] | None = None
    reviewed_at: datetime | None = None
    resolution: dict[str, Any] | None = None
    created_at: datetime


class MatchCandidateListResponse(BaseModel):
    items: list[MatchCandidateOut]
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    limit: int


class ChangeEventOut(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    change_type: str
    attribute_name: str | None = None
    old_value: Any | None = None
    new_value: Any | None = None
    changed_at: datetime
    changed_by: str | None = None
    source_record_id: uuid.UUID | None = None


class ChangeListResponse(BaseModel):
    items: list[ChangeEventOut]
    next_cursor: str | None = None
    has_more: bool = False


class StatisticsOut(BaseModel):
    as_of: datetime
    facilities_total: int
    published_facilities: int
    schools: int
    health_facilities: int
    with_coordinates: int
    synthetic: int
    by_precision: dict[str, int]
    by_region: list[dict[str, Any]]
    by_inclusion_class: dict[str, int] = Field(default_factory=dict)
    by_ownership_type: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_access_class: dict[str, int] = Field(default_factory=dict)
    source_releases: int
    caveats: list[str] = Field(default_factory=list)


class CoverageRow(BaseModel):
    key: str
    label: str | None = None
    facility_count: int
    published_count: int
    with_coordinates: int = 0


class CoverageSubtypeRow(BaseModel):
    category: str
    subtype: str
    label: str | None = None
    facility_count: int
    published_count: int
    with_coordinates: int = 0


class LguCoverageRow(BaseModel):
    state: Literal["NATIONAL", "REGIONAL", "PARTICIPATING_LGUS", "SELECTED_LGUS", "UNKNOWN"]
    label: str
    source_count: int
    dataset_slugs: list[str] = Field(default_factory=list)


class SourceCoverageRow(BaseModel):
    dataset_slug: str
    dataset_name: str
    agency_code: str
    coverage_scope: str = "UNKNOWN_COVERAGE"
    coverage_note: str | None = None
    latest_release_label: str | None = None
    source_published_at: datetime | None = None
    reference_period_end: date | None = None
    retrieved_at: datetime | None = None
    row_count_parsed: int | None = None
    publication_status: str = "blocked"
    rights_status: str = "unknown"
    freshness_days: int | None = None
    is_stale: bool | None = None


class CoverageOut(BaseModel):
    as_of: datetime
    registry_records: int
    published_records: int
    by_inclusion_class: list[CoverageRow]
    by_category: list[CoverageRow]
    by_subtype: list[CoverageSubtypeRow] = Field(default_factory=list)
    by_ownership_type: list[CoverageRow]
    by_access_class: list[CoverageRow]
    by_region: list[CoverageRow]
    by_lgu_coverage: list[LguCoverageRow] = Field(default_factory=list)
    source_coverage: list[SourceCoverageRow]
    coverage_stale_after_days: int = 365
    stale_source_count: int = 0
    caveats: list[str] = Field(default_factory=list)


class PopulationObservationOut(BaseModel):
    id: uuid.UUID
    psgc_code: str
    geographic_level: str | None = None
    geographic_name: str | None = None
    indicator_code: str
    indicator_label: str
    value: float | None = None
    unit: str | None = None
    reference_date: date | None = None
    reference_period: str | None = None
    dimensions: dict[str, Any] | None = None
    source_url: str | None = None
    source_updated_at: datetime | None = None
    retrieved_at: datetime | None = None
    release_id: uuid.UUID
    release_label: str
    dataset_slug: str
    attribution_text: str | None = None


class PopulationListResponse(BaseModel):
    items: list[PopulationObservationOut]
    total: int
    limit: int
    offset: int
    caveats: list[str] = Field(default_factory=list)


class TaxonomyTermOut(BaseModel):
    code: str
    label: str


class TaxonomyCategoryOut(TaxonomyTermOut):
    subtypes: list[TaxonomyTermOut] = Field(default_factory=list)


class TaxonomyResponse(BaseModel):
    version: str
    categories: list[TaxonomyCategoryOut]
    facility_kinds: list[TaxonomyTermOut]
    inclusion_classes: list[TaxonomyTermOut]
    ownership_types: list[TaxonomyTermOut]
    operator_types: list[TaxonomyTermOut]
    access_classes: list[TaxonomyTermOut]
    record_statuses: list[TaxonomyTermOut]
    contact_types: list[TaxonomyTermOut]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str
