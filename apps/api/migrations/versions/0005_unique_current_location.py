"""Enforce one current location per canonical facility.

Revision ID: 0005_unique_current_location
Revises: 0004_population_statistics
Create Date: 2026-11-15

A facility may have many historical location rows, but only one may be current.
The previous non-unique index allowed duplicate current rows after repeated
imports, which inflated location-based statistics. This migration retires older
duplicates deterministically, keeping the newest row, and then adds a partial
unique index so the invariant is enforced by the database.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0005_unique_current_location"
down_revision = "0004_population_statistics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    index_names = {
        index["name"] for index in inspector.get_indexes("facility_locations", schema="core")
    }

    if "ix_core_facility_locations_current" in index_names:
        op.drop_index(
            "ix_core_facility_locations_current",
            table_name="facility_locations",
            schema="core",
        )

    # Keep the newest current row per facility; the id tie-break makes the
    # choice deterministic if timestamps collide.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY facility_id
                       ORDER BY created_at DESC, id DESC
                   ) AS row_number
            FROM core.facility_locations
            WHERE is_current
        )
        UPDATE core.facility_locations AS location
        SET is_current = false
        FROM ranked
        WHERE location.id = ranked.id
          AND ranked.row_number > 1
        """
    )

    if "uq_core_facility_locations_current" not in index_names:
        op.execute(
            """
            CREATE UNIQUE INDEX uq_core_facility_locations_current
            ON core.facility_locations (facility_id)
            WHERE is_current
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS core.uq_core_facility_locations_current")
    inspector = inspect(op.get_bind())
    index_names = {
        index["name"] for index in inspector.get_indexes("facility_locations", schema="core")
    }
    if "ix_core_facility_locations_current" not in index_names:
        op.create_index(
            "ix_core_facility_locations_current",
            "facility_locations",
            ["facility_id", "is_current"],
            schema="core",
        )
