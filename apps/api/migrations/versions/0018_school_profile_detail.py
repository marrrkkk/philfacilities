"""Add tabular school-administration fields and drop the empty annex field.

Revision ID: 0018_school_profile_detail
Revises: 0017_health_profile_nhfr
Create Date: 2026-11-18

The DepEd Masterlist SY 2020-2021 tabular release carries the school division,
district, legislative district, settlement type, school-management class and
the combined offering classification for all 60,924 listed BEIS IDs. The old
``annex_status`` column was empty for every school profile and no ingested
source can fill it, so it is removed.

The baseline migration materialises the current SQLAlchemy metadata. This
migration checks before adding or dropping so a fresh database and an upgraded
database converge on the same schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0018_school_profile_detail"
down_revision = "0017_health_profile_nhfr"
branch_labels = None
depends_on = None

NEW_COLUMNS = (
    sa.Column("division", sa.String(length=120), nullable=True),
    sa.Column("district", sa.String(length=120), nullable=True),
    sa.Column("legislative_district", sa.String(length=120), nullable=True),
    sa.Column("settlement_type", sa.String(length=40), nullable=True),
    sa.Column("offering_classification", sa.String(length=60), nullable=True),
)


def _columns() -> set[str]:
    return {
        column["name"] for column in inspect(op.get_bind()).get_columns("profiles", schema="school")
    }


def upgrade() -> None:
    columns = _columns()
    for column in NEW_COLUMNS:
        if column.name not in columns:
            op.add_column("profiles", column, schema="school")
    if "annex_status" in columns:
        op.drop_column("profiles", "annex_status", schema="school")


def downgrade() -> None:
    columns = _columns()
    if "annex_status" not in columns:
        op.add_column(
            "profiles",
            sa.Column("annex_status", sa.String(length=80), nullable=True),
            schema="school",
        )
    for column in reversed(NEW_COLUMNS):
        if column.name in columns:
            op.drop_column("profiles", column.name, schema="school")
