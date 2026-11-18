"""Add facility lookup indexes used by merge, undo, and profile reads.

Revision ID: 0022_merge_lookup_indexes
Revises: 0021_utility_profile_date_length
Create Date: 2026-11-18

``core.facility_locations`` only had a partial unique index on
``facility_id WHERE is_current``, so every merge, undo, and profile read that
asked for all of a facility's locations scanned the table. ``quality.issues``
had no ``facility_id`` index at all, so the facility quality panel scanned it
too.

These indexes change no vocabulary, publication rule, or row.
"""

from __future__ import annotations

from alembic import op

revision = "0022_merge_lookup_indexes"
down_revision = "0021_utility_profile_date_length"
branch_labels = None
depends_on = None

INDEXES = (
    (
        "core",
        "ix_core_facility_locations_facility",
        "CREATE INDEX IF NOT EXISTS ix_core_facility_locations_facility "
        "ON core.facility_locations (facility_id)",
    ),
    (
        "quality",
        "ix_quality_issues_facility",
        "CREATE INDEX IF NOT EXISTS ix_quality_issues_facility ON quality.issues (facility_id)",
    ),
)


def upgrade() -> None:
    for _schema, _name, statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    for schema, name, _statement in reversed(INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {schema}.{name}")
