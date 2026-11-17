"""Add hot-path indexes and child-observation uniqueness.

Revision ID: 0010_ingest_hot_path_indexes
Revises: 0009_attribute_fusion
Create Date: 2026-11-16

The bulk ingestion path looks facilities up by agency entity identifier, checks
assertions by ``(facility_id, source_record_id)``, and retires release issues by
``(release_id, issue_code, status)``. None of those columns were indexed, so
each lookup scanned the growing national tables.

The unique constraints close the check-then-insert race in the candidate apply
path. They were audited against the working database first. Enrollment
observations already had a unique constraint. The health-profile natural key was
audited too: all 42 duplicate groups have a null DOH facility ID, and there are
zero duplicate groups with a non-null DOH ID. Profiles without a DOH ID are
legitimate separate records, so no constraint is added there.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0010_ingest_hot_path_indexes"
down_revision = "0009_attribute_fusion"
branch_labels = None
depends_on = None

INDEXES = (
    (
        "source",
        "facility_source_links",
        "ix_links_source_entity",
        ("source_entity_id",),
    ),
    (
        "core",
        "attribute_assertions",
        "ix_core_assertions_facility_record",
        ("facility_id", "source_record_id"),
    ),
    (
        "quality",
        "issues",
        "ix_quality_issues_release_code_status",
        ("release_id", "issue_code", "status"),
    ),
)

UNIQUE_CONSTRAINTS = (
    (
        "school",
        "profiles",
        "uq_school_profile_facility_deped",
        ("facility_id", "deped_school_id"),
    ),
    (
        "school",
        "resource_observations",
        "uq_resource_observation",
        ("facility_id", "school_year", "resource_code", "source_record_id"),
    ),
    (
        "health",
        "licenses",
        "uq_health_license_source",
        ("facility_id", "license_number", "source_record_id"),
    ),
    (
        "health",
        "accreditations",
        "uq_health_accreditation_source",
        (
            "facility_id",
            "provider_category",
            "accreditation_category",
            "valid_until",
            "source_record_id",
        ),
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for schema, table, name, columns in INDEXES:
        existing = {index["name"] for index in inspector.get_indexes(table, schema=schema)}
        if name not in existing:
            op.create_index(name, table, list(columns), schema=schema)

    for schema, table, name, columns in UNIQUE_CONSTRAINTS:
        existing = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(table, schema=schema)
        }
        if name not in existing:
            op.create_unique_constraint(name, table, list(columns), schema=schema)


def downgrade() -> None:
    for schema, table, name, _columns in reversed(UNIQUE_CONSTRAINTS):
        op.drop_constraint(name, table, schema=schema, type_="unique")
    for schema, _table, name, _columns in reversed(INDEXES):
        op.drop_index(name, schema=schema)
