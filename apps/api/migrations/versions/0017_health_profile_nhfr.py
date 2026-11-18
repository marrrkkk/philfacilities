"""Replace the unused health capability field with NHFR-derived profile fields.

Revision ID: 0017_health_profile_nhfr
Revises: 0016_osm_admin_boundaries
Create Date: 2026-11-18

``service_capability_level`` was empty for every published health profile and no
ingested source populated it. The DOH National Health Facility Registry carries
the fields health users actually need: facility major/detail type, ownership
sub-classification, licensing status, and bed capacity. This migration drops the
empty field and adds those profile fields. No row value is discarded: the old
column was null or an empty string on every row.

The baseline migration materialises the current SQLAlchemy metadata, so the
columns can already exist on a fresh database. The migration checks first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0017_health_profile_nhfr"
down_revision = "0016_osm_admin_boundaries"
branch_labels = None
depends_on = None

NEW_COLUMNS = (
    sa.Column("facility_major_type", sa.String(length=120), nullable=True),
    sa.Column("facility_type_detail", sa.String(length=120), nullable=True),
    sa.Column("ownership_subclassification", sa.String(length=120), nullable=True),
    sa.Column("licensing_status", sa.String(length=80), nullable=True),
)


def _columns() -> set[str]:
    return {
        column["name"] for column in inspect(op.get_bind()).get_columns("profiles", schema="health")
    }


def upgrade() -> None:
    columns = _columns()
    for column in NEW_COLUMNS:
        if column.name not in columns:
            op.add_column("profiles", column, schema="health")
    if "service_capability_level" in columns:
        op.drop_column("profiles", "service_capability_level", schema="health")


def downgrade() -> None:
    columns = _columns()
    if "service_capability_level" not in columns:
        op.add_column(
            "profiles",
            sa.Column("service_capability_level", sa.String(length=120), nullable=True),
            schema="health",
        )
    for column in reversed(NEW_COLUMNS):
        if column.name in columns:
            op.drop_column("profiles", column.name, schema="health")
