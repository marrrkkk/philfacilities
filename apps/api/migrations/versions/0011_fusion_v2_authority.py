"""Fusion v2: explicit source authority and automated conflict resolution.

Revision ID: 0011_fusion_v2_authority
Revises: 0010_ingest_hot_path_indexes
Create Date: 2026-11-17

The first fusion pass inferred source authority from dataset-name tokens and had
no status/confidence guards. This revision adds an explicit
``source.datasets.authority_level`` that the selector reads instead, backfills
existing datasets conservatively, and guarantees the fusion status/confidence
constraints exist on databases created before those guards were modelled.

Fusion is fully automated: conflicts are resolved by the deterministic selector
and no review columns are introduced. The baseline migration materialises the
current SQLAlchemy metadata, so objects can already exist on a fresh database;
each operation checks first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0011_fusion_v2_authority"
down_revision = "0010_ingest_hot_path_indexes"
branch_labels = None
depends_on = None

# Review columns were an unreleased experiment. Drop them when present so a
# development database converges on the automated schema.
OBSOLETE_REVIEW_COLUMNS = (
    "review_status",
    "reviewed_value",
    "reviewed_normalized_value",
    "reviewed_source_record_id",
    "reviewed_by",
    "reviewed_at",
    "review_note",
)
OBSOLETE_REVIEW_FK = "fk_core_fusion_reviewed_source_record"
OBSOLETE_REVIEW_INDEX = "ix_core_attribute_fusions_review"
OBSOLETE_REVIEW_CHECK = "ck_facility_attribute_fusions_fusion_review_status_allowed"

FUSION_CHECKS = (
    (
        "ck_facility_attribute_fusions_fusion_status_allowed",
        "status IN ('single_source', 'agreed', 'conflict')",
    ),
    (
        "ck_facility_attribute_fusions_fusion_confidence_range",
        "confidence >= 0 AND confidence <= 1",
    ),
)


def _columns(table: str, schema: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table, schema=schema)}


def _checks(table: str, schema: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspect(op.get_bind()).get_check_constraints(table, schema=schema)
    }


def _foreign_keys(table: str, schema: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspect(op.get_bind()).get_foreign_keys(table, schema=schema)
    }


def _indexes(table: str, schema: str) -> set[str]:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table, schema=schema)}


def _drop_obsolete_review_objects() -> None:
    if OBSOLETE_REVIEW_INDEX in _indexes("facility_attribute_fusions", "core"):
        op.drop_index(
            OBSOLETE_REVIEW_INDEX,
            table_name="facility_attribute_fusions",
            schema="core",
        )
    existing_checks = _checks("facility_attribute_fusions", "core")
    if OBSOLETE_REVIEW_CHECK in existing_checks:
        op.drop_constraint(
            OBSOLETE_REVIEW_CHECK,
            "facility_attribute_fusions",
            schema="core",
            type_="check",
        )
    if OBSOLETE_REVIEW_FK in _foreign_keys("facility_attribute_fusions", "core"):
        op.drop_constraint(
            OBSOLETE_REVIEW_FK,
            "facility_attribute_fusions",
            schema="core",
            type_="foreignkey",
        )
    existing_columns = _columns("facility_attribute_fusions", "core")
    for name in reversed(OBSOLETE_REVIEW_COLUMNS):
        if name in existing_columns:
            op.drop_column("facility_attribute_fusions", name, schema="core")


def upgrade() -> None:
    if "authority_level" not in _columns("datasets", "source"):
        op.add_column(
            "datasets",
            sa.Column(
                "authority_level",
                sa.String(length=30),
                nullable=False,
                server_default=sa.text("'unknown'"),
            ),
            schema="source",
        )
    op.execute(
        """
        UPDATE source.datasets AS d
        SET authority_level = CASE
            WHEN d.is_synthetic OR a.publisher_type = 'synthetic_fixture' THEN 'synthetic'
            WHEN a.publisher_type = 'community' THEN 'community'
            WHEN a.publisher_type IS NULL THEN 'unknown'
            ELSE 'official'
        END
        FROM source.agencies AS a
        WHERE d.agency_id = a.id
        """
    )
    if "ck_datasets_authority_level_allowed" not in _checks("datasets", "source"):
        op.create_check_constraint(
            "ck_datasets_authority_level_allowed",
            "datasets",
            "authority_level IN ('official', 'community', 'synthetic', 'unknown')",
            schema="source",
        )

    _drop_obsolete_review_objects()
    existing_checks = _checks("facility_attribute_fusions", "core")
    for name, condition in FUSION_CHECKS:
        if name not in existing_checks:
            op.create_check_constraint(
                name,
                "facility_attribute_fusions",
                condition,
                schema="core",
            )


def downgrade() -> None:
    existing_checks = _checks("facility_attribute_fusions", "core")
    for name, _condition in reversed(FUSION_CHECKS):
        if name in existing_checks:
            op.drop_constraint(
                name,
                "facility_attribute_fusions",
                schema="core",
                type_="check",
            )
    if "ck_datasets_authority_level_allowed" in _checks("datasets", "source"):
        op.drop_constraint(
            "ck_datasets_authority_level_allowed",
            "datasets",
            schema="source",
            type_="check",
        )
    if "authority_level" in _columns("datasets", "source"):
        op.drop_column("datasets", "authority_level", schema="source")
