"""Widen the DOE facility code.

Revision ID: 0020_utility_profile_code_length
Revises: 0019_utility_profile_doe
Create Date: 2026-11-18

The off-grid DOE list includes descriptive facility codes longer than the
original 40-character profile column (the longest observed is 51 characters).
Preserve the source code verbatim instead of truncating it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_utility_profile_code_length"
down_revision = "0019_utility_profile_doe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "profiles",
        "doe_facility_code",
        existing_type=sa.String(length=40),
        type_=sa.String(length=120),
        existing_nullable=True,
        schema="utility",
    )


def downgrade() -> None:
    op.alter_column(
        "profiles",
        "doe_facility_code",
        existing_type=sa.String(length=120),
        type_=sa.String(length=40),
        existing_nullable=True,
        schema="utility",
    )
