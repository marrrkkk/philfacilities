from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _default_inclusion_class(context) -> str:
    """Keep direct ORM construction safe for legacy/tests.

    Ingested records pass an explicit class. A caller that only sets ownership
    still gets the conservative mapping; unknown ownership never becomes a
    public government facility by accident.
    """

    ownership = (context.get_current_parameters().get("ownership") or "").strip().lower()
    if ownership == "government":
        return "GOVERNMENT_FACILITY"
    if ownership == "private":
        return "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    return "DISCOVERY_CANDIDATE"


class Agency(Base):
    __tablename__ = "agencies"
    __table_args__ = {"schema": "source"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    short_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    official_domain: Mapped[str | None] = mapped_column(String(255))
    publisher_type: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = created_at()


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("agency_id", "slug", name="uq_datasets_agency_slug"),
        {"schema": "source"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    agency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.agencies.id", ondelete="RESTRICT"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    access_method: Mapped[str | None] = mapped_column(String(80))
    terms_url: Mapped[str | None] = mapped_column(Text)
    license_identifier: Mapped[str | None] = mapped_column(String(120))
    redistribution_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown"
    )
    rights_basis: Mapped[str | None] = mapped_column(Text)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    personal_data_status: Mapped[str | None] = mapped_column(String(60))
    publication_status: Mapped[str] = mapped_column(String(40), nullable=False, default="blocked")
    coverage_scope: Mapped[str | None] = mapped_column(String(40))
    coverage_note: Mapped[str | None] = mapped_column(Text)
    update_pattern: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str | None] = mapped_column(String(40))
    is_public_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at()


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.datasets.id", ondelete="RESTRICT"), nullable=False
    )
    source_release_label: Mapped[str] = mapped_column(String(120), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference_period_start: Mapped[date | None] = mapped_column(Date)
    reference_period_end: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_object_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str | None] = mapped_column(String(40))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    row_count_reported: Mapped[int | None] = mapped_column(Integer)
    row_count_parsed: Mapped[int | None] = mapped_column(Integer)
    ingestion_status: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered")
    terms_review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    publication_status: Mapped[str] = mapped_column(String(40), nullable=False, default="blocked")
    parser_version: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("dataset_id", "sha256", name="uq_releases_dataset_sha256"),
        Index("ix_source_releases_dataset_label", "dataset_id", "source_release_label"),
        {"schema": "source"},
    )


class SourceRecord(Base):
    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint("release_id", "source_record_key", name="uq_records_release_source_key"),
        Index("ix_source_records_release", "release_id"),
        Index(
            "ix_source_records_source_key_trgm",
            "source_record_key",
            postgresql_using="gin",
            postgresql_ops={"source_record_key": "gin_trgm_ops"},
        ),
        {"schema": "source"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.releases.id", ondelete="CASCADE"), nullable=False
    )
    source_record_key: Mapped[str] = mapped_column(String(200), nullable=False)
    row_number_or_page: Mapped[str | None] = mapped_column(String(80))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False, default="valid")


class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = (
        Index(
            "ix_core_facilities_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_core_facilities_official_name_trgm",
            "official_name",
            postgresql_using="gin",
            postgresql_ops={"official_name": "gin_trgm_ops"},
        ),
        Index("ix_core_facilities_type", "facility_type"),
        Index("ix_core_facilities_publication", "publication_status"),
        Index("ix_core_facilities_inclusion", "inclusion_class"),
        Index("ix_core_facilities_ownership_type", "ownership_type"),
        CheckConstraint(
            "facility_kind IN ('facility', 'site', 'building', 'facility_unit', "
            "'infrastructure_asset', 'project')",
            name="facility_kind_allowed",
        ),
        CheckConstraint(
            "inclusion_class IN ('GOVERNMENT_FACILITY', 'PRIVATE_PUBLIC_SERVICE_PROVIDER', "
            "'PUBLIC_ACCESS_VENUE', 'DISCOVERY_CANDIDATE')",
            name="inclusion_class_allowed",
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str | None] = mapped_column(String(180), unique=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    official_name: Mapped[str | None] = mapped_column(String(300))
    facility_type: Mapped[str] = mapped_column(String(40), nullable=False)
    facility_subtype: Mapped[str | None] = mapped_column(String(80))
    facility_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="facility")
    inclusion_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default=_default_inclusion_class
    )
    ownership: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    ownership_type: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    operator_type: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    public_access_class: Mapped[str] = mapped_column(String(40), nullable=False, default="UNKNOWN")
    access_conditions: Mapped[str | None] = mapped_column(Text)
    record_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    publication_status: Mapped[str] = mapped_column(String(40), nullable=False, default="internal")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FacilityFunction(Base):
    """A source-backed purpose or designation of a physical facility.

    A barangay multipurpose hall that is also an evacuation centre keeps one
    canonical facility and two dated function rows. The raw source vocabulary is
    retained in ``evidence``; ``function_code`` is the normalized taxonomy value.
    """

    __tablename__ = "facility_functions"
    __table_args__ = (
        UniqueConstraint(
            "facility_id", "function_code", "source_record_id", name="uq_facility_function_source"
        ),
        Index("ix_core_facility_functions_code", "function_code"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    function_code: Mapped[str] = mapped_column(String(60), nullable=False)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    source_value: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    capacity_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    capacity_unit: Mapped[str | None] = mapped_column(String(40))
    designation_status: Mapped[str | None] = mapped_column(String(40))
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class FacilityService(Base):
    """A service delivered at a facility, only where an authoritative record says so."""

    __tablename__ = "facility_services"
    __table_args__ = (
        UniqueConstraint(
            "facility_id", "service_code", "source_record_id", name="uq_facility_service_source"
        ),
        Index("ix_core_facility_services_code", "service_code"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    service_name: Mapped[str | None] = mapped_column(String(200))
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    source_field: Mapped[str | None] = mapped_column(String(160))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class FacilityRole(Base):
    """One role relationship (owner, operator, host, regulator, ...) with evidence.

    Roles are deliberately not collapsed into a single ``agency`` field: a private
    hospital can be privately owned and operated, licensed by DOH and accredited by
    PhilHealth, and none of those facts makes it government-owned.
    """

    __tablename__ = "facility_roles"
    __table_args__ = (
        UniqueConstraint(
            "facility_id",
            "role_type",
            "entity_name",
            "source_record_id",
            name="uq_facility_role_source",
        ),
        Index("ix_core_facility_roles_type", "role_type"),
        CheckConstraint(
            "role_type IN ('OWNER', 'OPERATOR', 'MANAGER', 'HOST', 'LANDLORD', 'FUNDER', "
            "'REGULATOR', 'LICENSOR', 'ACCREDITOR', 'RECOGNITION_AUTHORITY', 'AFFILIATOR')",
            name="facility_role_type_allowed",
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    role_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(300), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class FacilityRelationship(Base):
    """A typed link between two canonical facilities or a facility and its site.

    ``LOCATED_WITHIN`` and ``SHARED_SITE`` let a service unit and its host property
    coexist without duplicating either record or inferring that the host qualifies.
    """

    __tablename__ = "facility_relationships"
    __table_args__ = (
        UniqueConstraint(
            "subject_facility_id",
            "object_facility_id",
            "relationship_type",
            name="uq_facility_relationship",
        ),
        CheckConstraint(
            "relationship_type IN ('LOCATED_WITHIN', 'SHARED_SITE', 'HOSTED_AT', 'PARENT_OF', "
            "'SUCCESSOR_OF', 'REPLACED_BY')",
            name="facility_relationship_type_allowed",
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    subject_facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    object_facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class FacilitySourceLink(Base):
    __tablename__ = "facility_source_links"
    __table_args__ = (
        UniqueConstraint("facility_id", "source_record_id", name="uq_links_facility_source_record"),
        Index("ix_links_source_record", "source_record_id"),
        {"schema": "source"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.records.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[str | None] = mapped_column(String(200))
    match_method: Mapped[str] = mapped_column(String(80), nullable=False)
    match_confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("1.000")
    )
    match_status: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_dataset_started", "dataset_id", "started_at"),
        {"schema": "source"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.datasets.id", ondelete="RESTRICT"), nullable=False
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.releases.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running")
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    report_path: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)


class SourceCheck(Base):
    """One reachability/discovery check against a source endpoint.

    Checks are append-only monitoring evidence: they record what the source
    actually returned, including conditional-request metadata and blockers. A
    failed check never deletes or replaces the last successful release.
    """

    __tablename__ = "source_checks"
    __table_args__ = (
        Index("ix_source_checks_dataset_checked", "dataset_id", "checked_at"),
        Index("ix_source_checks_status_checked", "status", "checked_at"),
        {"schema": "source"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.datasets.id", ondelete="CASCADE"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(120))
    content_type: Mapped[str | None] = mapped_column(String(160))
    content_length: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeographicRelease(Base):
    __tablename__ = "geographic_releases"
    __table_args__ = {"schema": "geo"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = uuid_pk()
    release_label: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    reference_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_object_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at()


class AdministrativeUnit(Base):
    __tablename__ = "administrative_units"
    __table_args__ = (
        UniqueConstraint("release_id", "psgc_code", name="uq_admin_units_release_code"),
        Index("ix_geo_admin_units_code", "psgc_code"),
        Index("ix_geo_admin_units_parent", "parent_psgc_code"),
        Index(
            "ix_geo_admin_units_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        {"schema": "geo"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("geo.geographic_releases.id", ondelete="CASCADE"), nullable=False
    )
    psgc_code: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    geographic_level: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_psgc_code: Mapped[str | None] = mapped_column(String(12))
    correspondence_code: Mapped[str | None] = mapped_column(String(12))
    old_name: Mapped[str | None] = mapped_column(String(200))
    city_class: Mapped[str | None] = mapped_column(String(40))
    income_classification: Mapped[str | None] = mapped_column(String(40))
    urban_rural: Mapped[str | None] = mapped_column(String(20))
    island_region: Mapped[str | None] = mapped_column(String(80))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class GeographyCrosswalk(Base):
    __tablename__ = "geography_crosswalk"
    __table_args__ = (
        UniqueConstraint(
            "from_release_id",
            "to_release_id",
            "from_psgc_code",
            name="uq_crosswalk_releases_from_code",
        ),
        {"schema": "geo"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    from_release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("geo.geographic_releases.id", ondelete="CASCADE"), nullable=False
    )
    to_release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("geo.geographic_releases.id", ondelete="CASCADE"), nullable=False
    )
    from_psgc_code: Mapped[str] = mapped_column(String(12), nullable=False)
    to_psgc_code: Mapped[str | None] = mapped_column(String(12))
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class FacilityLocation(Base):
    __tablename__ = "facility_locations"
    __table_args__ = (
        Index("ix_core_facility_locations_geom", "geom", postgresql_using="gist"),
        Index("ix_core_facility_locations_psgc", "psgc_code"),
        Index(
            "ix_core_facility_locations_address_trgm",
            "address_text",
            postgresql_using="gin",
            postgresql_ops={"address_text": "gin_trgm_ops"},
        ),
        Index(
            "uq_core_facility_locations_current",
            "facility_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    geom: Mapped[Any | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    precision: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    method: Mapped[str | None] = mapped_column(String(80))
    address_text: Mapped[str | None] = mapped_column(Text)
    psgc_code: Mapped[str | None] = mapped_column(String(12))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="source_supplied"
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()


class AttributeAssertion(Base):
    __tablename__ = "attribute_assertions"
    __table_args__ = (
        Index("ix_core_assertions_facility_attr", "facility_id", "attribute_name"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    attribute_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.records.id", ondelete="CASCADE"), nullable=False
    )
    source_field: Mapped[str | None] = mapped_column(String(160))
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    transformation_version: Mapped[str | None] = mapped_column(String(40))
    review_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="source_supplied"
    )
    asserted_at: Mapped[datetime] = created_at()


class SchoolProfile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        Index("ix_school_profiles_facility", "facility_id"),
        {"schema": "school"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    deped_school_id: Mapped[str | None] = mapped_column(String(40), index=True)
    sector: Mapped[str | None] = mapped_column(String(60))
    school_management: Mapped[str | None] = mapped_column(String(80))
    annex_status: Mapped[str | None] = mapped_column(String(80))
    offers_es: Mapped[bool | None] = mapped_column(Boolean)
    offers_jhs: Mapped[bool | None] = mapped_column(Boolean)
    offers_shs: Mapped[bool | None] = mapped_column(Boolean)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class EnrollmentObservation(Base):
    __tablename__ = "enrollment_observations"
    __table_args__ = (
        UniqueConstraint(
            "facility_id",
            "school_year",
            "grade_level",
            "sex",
            "source_record_id",
            name="uq_enrollment_observation",
        ),
        Index("ix_school_enrollment_facility_year", "facility_id", "school_year"),
        {"schema": "school"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    grade_level: Mapped[str] = mapped_column(String(40), nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    learner_count: Mapped[int | None] = mapped_column(Integer)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    observed_at: Mapped[datetime] = created_at()


class ResourceObservation(Base):
    __tablename__ = "resource_observations"
    __table_args__ = (
        Index("ix_school_resource_facility_year", "facility_id", "school_year"),
        {"schema": "school"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_category: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(80), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    observed_at: Mapped[datetime] = created_at()


class HealthProfile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        Index("ix_health_profiles_facility", "facility_id"),
        {"schema": "health"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    doh_facility_id: Mapped[str | None] = mapped_column(String(80), index=True)
    facility_category: Mapped[str | None] = mapped_column(String(120))
    service_capability_level: Mapped[str | None] = mapped_column(String(120))
    bed_capacity: Mapped[int | None] = mapped_column(Integer)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class HealthLicense(Base):
    __tablename__ = "licenses"
    __table_args__ = (
        Index("ix_health_licenses_facility", "facility_id"),
        {"schema": "health"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    issuing_authority: Mapped[str | None] = mapped_column(String(120))
    license_number: Mapped[str | None] = mapped_column(String(120))
    license_type: Mapped[str | None] = mapped_column(String(120))
    source_status: Mapped[str | None] = mapped_column(String(80))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )


class HealthAccreditation(Base):
    __tablename__ = "accreditations"
    __table_args__ = (
        Index("ix_health_accreditations_facility", "facility_id"),
        {"schema": "health"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    authority: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_category: Mapped[str] = mapped_column(String(120), nullable=False)
    benefit_package: Mapped[str | None] = mapped_column(String(120))
    accreditation_category: Mapped[str | None] = mapped_column(String(120))
    bed_count: Mapped[int | None] = mapped_column(Integer)
    sector_code: Mapped[str | None] = mapped_column(String(20))
    source_status: Mapped[str | None] = mapped_column(String(80))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source_as_of: Mapped[date | None] = mapped_column(Date)
    telephone: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(200))
    street_address: Mapped[str | None] = mapped_column(Text)
    municipality: Mapped[str | None] = mapped_column(String(120))
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    page_reference: Mapped[str | None] = mapped_column(String(80))


class PopulationObservation(Base):
    """A population or household count published for a named geography.

    These are statistical observations, not facility records. They are kept in a
    separate schema so a population count can never be mistaken for a facility
    attribute. The original PSA/OpenSTAT table, release and dimension codes are
    retained alongside every value.
    """

    __tablename__ = "population_observations"
    __table_args__ = (
        UniqueConstraint(
            "release_id", "source_record_key", name="uq_population_release_source_key"
        ),
        Index("ix_stats_population_psgc", "psgc_code"),
        Index("ix_stats_population_release", "release_id"),
        {"schema": "stats"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.releases.id", ondelete="CASCADE"), nullable=False
    )
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    source_record_key: Mapped[str] = mapped_column(String(200), nullable=False)
    psgc_code: Mapped[str] = mapped_column(String(12), nullable=False)
    geographic_level: Mapped[str | None] = mapped_column(String(40))
    geographic_name: Mapped[str | None] = mapped_column(String(200))
    indicator_code: Mapped[str] = mapped_column(String(20), nullable=False)
    indicator_label: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    unit: Mapped[str | None] = mapped_column(String(80))
    reference_date: Mapped[date | None] = mapped_column(Date)
    reference_period: Mapped[str | None] = mapped_column(String(80))
    dimensions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class QualityIssue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("ix_quality_issues_status_severity", "status", "severity"),
        {"schema": "quality"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE")
    )
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.releases.id", ondelete="SET NULL")
    )
    issue_code: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    created_at: Mapped[datetime] = created_at()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchCandidate(Base):
    """A deterministic cross-source identity candidate awaiting human review.

    The row is created instead of merging facilities. Accepting a candidate records the
    decision; a separate explicit merge command applies it. Rejected rows are retained so
    the same pair is not queued again for the same algorithm version.
    """

    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_key", name="uq_match_candidates_candidate_key"),
        CheckConstraint(
            "match_status IN ('pending', 'accepted', 'rejected', 'merged')",
            name="match_status_allowed",
        ),
        CheckConstraint(
            "match_confidence >= 0 AND match_confidence <= 1",
            name="match_confidence_range",
        ),
        Index("ix_quality_match_candidates_status_created", "match_status", "created_at"),
        Index("ix_quality_match_candidates_source_record", "source_record_id"),
        {"schema": "quality"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.records.id", ondelete="CASCADE"), nullable=False
    )
    source_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="SET NULL")
    )
    candidate_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="SET NULL")
    )
    source_agency_code: Mapped[str | None] = mapped_column(String(40))
    candidate_agency_code: Mapped[str | None] = mapped_column(String(40))
    match_method: Mapped[str] = mapped_column(String(80), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    match_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class PublicationGate(Base):
    __tablename__ = "publication_gates"
    __table_args__ = {"schema": "quality"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.datasets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="review_required")
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class FacilityChangeEvent(Base):
    __tablename__ = "facility_change_events"
    __table_args__ = (
        Index("ix_history_changes_facility_changed", "facility_id", "changed_at"),
        {"schema": "history"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.facilities.id", ondelete="CASCADE"), nullable=False
    )
    change_type: Mapped[str] = mapped_column(String(60), nullable=False)
    attribute_name: Mapped[str | None] = mapped_column(String(80))
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.records.id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = created_at()
    changed_by: Mapped[str | None] = mapped_column(String(120))
