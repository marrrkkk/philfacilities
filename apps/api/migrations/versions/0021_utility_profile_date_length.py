"""Preserve the DOE commissioning-date text.

Revision ID: 0021_utility_profile_date_length
Revises: 0020_utility_profile_code_length
Create Date: 2026-11-18

Some DOE commissioning cells describe multiple unit dates in one string (the
longest observed is 64 characters). Keep the source text instead of truncating
or parsing it into an invented single date.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_utility_profile_date_length"
down_revision = "0020_utility_profile_code_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "profiles",
        "date_commissioned",
        existing_type=sa.String(length=40),
        type_=sa.String(length=160),
        existing_nullable=True,
        schema="utility",
    )


def downgrade() -> None:
    op.alter_column(
        "profiles",
        "date_commissioned",
        existing_type=sa.String(length=160),
        type_=sa.String(length=40),
        existing_nullable=True,
        schema="utility",
    )
