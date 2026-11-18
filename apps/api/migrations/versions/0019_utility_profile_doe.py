"""Add the DOE power-plant profile.

Revision ID: 0019_utility_profile_doe
Revises: 0018_school_profile_detail
Create Date: 2026-11-18

The DOE existing-power-plant lists carry facility-level values that were only
retained in function evidence: resource and technology type, connection type,
grid, owner type, contract type, installed and dependable capacity, unit count
and commissioning date. The utility profile exposes those values without
changing the canonical facility classification.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0019_utility_profile_doe"
down_revision = "0018_school_profile_detail"
branch_labels = None
depends_on = None


def _has_table() -> bool:
    return inspect(op.get_bind()).has_table("profiles", schema="utility")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS utility")
    if _has_table():
        return
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "facility_id",
            sa.Uuid(),
            sa.ForeignKey("core.facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doe_facility_code", sa.String(length=40), nullable=True),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("technology_type", sa.String(length=160), nullable=True),
        sa.Column("connection_type", sa.String(length=40), nullable=True),
        sa.Column("grid", sa.String(length=40), nullable=True),
        sa.Column("owner_type", sa.String(length=80), nullable=True),
        sa.Column("contract_type", sa.String(length=80), nullable=True),
        sa.Column("installed_mw", sa.Numeric(12, 2), nullable=True),
        sa.Column("dependable_mw", sa.Numeric(12, 2), nullable=True),
        sa.Column("number_of_units", sa.Integer(), nullable=True),
        sa.Column("date_commissioned", sa.String(length=40), nullable=True),
        sa.Column(
            "source_record_id",
            sa.Uuid(),
            sa.ForeignKey("source.records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.UniqueConstraint(
            "facility_id", "doe_facility_code", name="uq_utility_profile_facility_code"
        ),
        schema="utility",
    )
    op.create_index("ix_utility_profiles_facility", "profiles", ["facility_id"], schema="utility")
    op.create_index(
        "ix_utility_profiles_doe_facility_code",
        "profiles",
        ["doe_facility_code"],
        schema="utility",
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table("profiles", schema="utility")
