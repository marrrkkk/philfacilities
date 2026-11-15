"""Ownership-inclusive registry, functions, roles, services and coverage.

Revision ID: 0007_inclusion_model
Revises: 0006_search_trigram_indexes
Create Date: 2026-11-15

This migration implements the v3.0 scope correction:

* every facility receives an explicit inclusion class;
* granular ownership/operator/access fields are kept separate from the class;
* functions, services and role relationships become first-class tables;
* source datasets record their actual coverage scope.

Legacy records whose ownership cannot be established are deliberately left as
``DISCOVERY_CANDIDATE`` and made internal. Their source links and history are
retained, so they can be reclassified when evidence is acquired. The migration
does not invent owners, operators or access conditions.

The one evidence-based backfill is the PhilHealth provider sector code: the PDF
directory publishes an explicit ``SEC`` value of ``G`` (government) or ``P``
(private) per facility. It is used only when every accreditation for a facility
agrees; a mixed-sector facility stays unknown. Accreditation itself is not
treated as ownership.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import (
    FacilityFunction,
    FacilityRelationship,
    FacilityRole,
    FacilityService,
)
from sqlalchemy import inspect

revision = "0007_inclusion_model"
down_revision = "0006_search_trigram_indexes"
branch_labels = None
depends_on = None

FACILITY_COLUMNS = {
    "facility_kind": "VARCHAR(30) NOT NULL DEFAULT 'facility'",
    "inclusion_class": "VARCHAR(40)",
    "ownership_type": "VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN'",
    "operator_type": "VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN'",
    "public_access_class": "VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN'",
    "access_conditions": "TEXT",
}

CONSTRAINTS = (
    (
        "core",
        "facilities",
        "ck_core_facilities_facility_kind_allowed",
        "facility_kind IN ('facility', 'site', 'building', 'facility_unit', "
        "'infrastructure_asset', 'project')",
    ),
    (
        "core",
        "facilities",
        "ck_core_facilities_inclusion_class_allowed",
        "inclusion_class IN ('GOVERNMENT_FACILITY', 'PRIVATE_PUBLIC_SERVICE_PROVIDER', "
        "'PUBLIC_ACCESS_VENUE', 'DISCOVERY_CANDIDATE')",
    ),
)

INDEXES = (
    ("core", "ix_core_facilities_inclusion", "inclusion_class"),
    ("core", "ix_core_facilities_ownership_type", "ownership_type"),
)


def _columns(table: str, schema: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table, schema=schema)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    facility_columns = _columns("facilities", "core")
    for name, ddl in FACILITY_COLUMNS.items():
        if name not in facility_columns:
            op.execute(f"ALTER TABLE core.facilities ADD COLUMN {name} {ddl}")

    dataset_columns = _columns("datasets", "source")
    if "coverage_scope" not in dataset_columns:
        op.execute("ALTER TABLE source.datasets ADD COLUMN coverage_scope VARCHAR(40)")
    if "coverage_note" not in dataset_columns:
        op.execute("ALTER TABLE source.datasets ADD COLUMN coverage_note TEXT")

    # --- Evidence-based sector backfill -----------------------------------
    # Only for health facilities whose ownership is still unknown and whose
    # PhilHealth accreditations unanimously carry one sector value.
    if inspector.has_table("accreditations", schema="health"):
        op.execute(
            """
            WITH sectors AS (
                SELECT facility_id,
                       bool_or(sector_code = 'G') AS has_g,
                       bool_or(sector_code = 'P') AS has_p
                FROM health.accreditations
                GROUP BY facility_id
            )
            UPDATE core.facilities AS f
            SET ownership = CASE
                    WHEN s.has_g AND NOT s.has_p THEN 'government'
                    WHEN s.has_p AND NOT s.has_g THEN 'private'
                    ELSE f.ownership
                END
            FROM sectors AS s
            WHERE s.facility_id = f.id
              AND f.ownership = 'unknown'
              AND (s.has_g <> s.has_p)
            """
        )

    # --- Classification split --------------------------------------------
    op.execute(
        """
        UPDATE core.facilities
        SET ownership_type = CASE
                WHEN ownership = 'government' THEN 'GOVERNMENT_UNSPECIFIED'
                WHEN ownership = 'private' THEN 'PRIVATE_UNSPECIFIED'
                ELSE 'UNKNOWN'
            END
        WHERE ownership_type = 'UNKNOWN'
        """
    )
    op.execute(
        """
        UPDATE core.facilities
        SET inclusion_class = CASE
                WHEN ownership = 'government' THEN 'GOVERNMENT_FACILITY'
                WHEN ownership = 'private' THEN 'PRIVATE_PUBLIC_SERVICE_PROVIDER'
                ELSE 'DISCOVERY_CANDIDATE'
            END
        WHERE inclusion_class IS NULL
        """
    )
    op.execute(
        """
        UPDATE core.facilities
        SET publication_status = 'internal'
        WHERE inclusion_class = 'DISCOVERY_CANDIDATE'
          AND publication_status = 'public'
        """
    )

    # --- Constraints and indexes -----------------------------------------
    existing_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("facilities", schema="core")
    }
    for schema, table, name, condition in CONSTRAINTS:
        if name not in existing_constraints:
            op.execute(f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {name} CHECK ({condition})")
    op.execute("ALTER TABLE core.facilities ALTER COLUMN inclusion_class SET NOT NULL")

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("facilities", schema="core")
    }
    for _schema, name, column in INDEXES:
        if name not in existing_indexes:
            op.execute(f"CREATE INDEX {name} ON core.facilities ({column})")

    # --- New relationship tables -----------------------------------------
    for model in (FacilityFunction, FacilityService, FacilityRole, FacilityRelationship):
        if not inspector.has_table(model.__tablename__, schema="core"):
            model.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for model in (FacilityRelationship, FacilityRole, FacilityService, FacilityFunction):
        if inspector.has_table(model.__tablename__, schema="core"):
            op.drop_table(model.__tablename__, schema="core")

    for _schema, name, _column in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for _schema, _table, name, _condition in CONSTRAINTS:
        op.execute(f"ALTER TABLE core.facilities DROP CONSTRAINT IF EXISTS {name}")

    op.execute("ALTER TABLE core.facilities ALTER COLUMN inclusion_class DROP NOT NULL")
    for name in FACILITY_COLUMNS:
        op.execute(f"ALTER TABLE core.facilities DROP COLUMN IF EXISTS {name}")
    for name in ("coverage_scope", "coverage_note"):
        op.execute(f"ALTER TABLE source.datasets DROP COLUMN IF EXISTS {name}")
