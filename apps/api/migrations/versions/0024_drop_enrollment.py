"""Drop school enrollment observations.

Enrollment cells remain in the preserved DepEd source artifacts and source
records, but they are no longer materialised as canonical child rows or exposed
by the API. The related ``reference_school_year`` and ``enrollment_total``
fields were derived from this table and disappear with it.

Revision ID: 0024_drop_enrollment
Revises: 0023_facility_slug_aliases
Create Date: 2026-11-21

The baseline migration materialises the current SQLAlchemy metadata, so a fresh
database never has this table; the migration checks before dropping it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0024_drop_enrollment"
down_revision = "0023_facility_slug_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "enrollment_observations" in inspector.get_table_names(schema="school"):
        op.drop_index(
            "ix_school_enrollment_facility_year",
            table_name="enrollment_observations",
            schema="school",
        )
        op.drop_table("enrollment_observations", schema="school")


def downgrade() -> None:
    op.create_table(
        "enrollment_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("school_year", sa.String(length=20), nullable=False),
        sa.Column("grade_level", sa.String(length=40), nullable=False),
        sa.Column("sex", sa.String(length=20), nullable=False),
        sa.Column("learner_count", sa.Integer(), nullable=True),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["core.facilities.id"],
            name="fk_enrollment_observations_facility_id_facilities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source.records.id"],
            name="fk_enrollment_observations_source_record_id_records",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_enrollment_observations"),
        sa.UniqueConstraint(
            "facility_id",
            "school_year",
            "grade_level",
            "sex",
            "source_record_id",
            name="uq_enrollment_observation",
        ),
        schema="school",
    )
    op.create_index(
        "ix_school_enrollment_facility_year",
        "enrollment_observations",
        ["facility_id", "school_year"],
        schema="school",
    )
