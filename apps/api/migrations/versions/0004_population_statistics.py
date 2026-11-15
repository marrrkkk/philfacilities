"""Add the population-statistics schema.

Revision ID: 0004_population_statistics
Revises: 0003_acquisition_rights
Create Date: 2026-11-15

Population counts are enrichment data, not facility records. Keeping them in a
separate ``stats`` schema prevents a demographic value from being joined or
displayed as a facility attribute by accident. The baseline migration creates
the table for fresh databases; this migration adds it to existing databases.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import PopulationObservation
from sqlalchemy import inspect

revision = "0004_population_statistics"
down_revision = "0003_acquisition_rights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS stats")
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("population_observations", schema="stats"):
        PopulationObservation.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("population_observations", schema="stats"):
        op.drop_table("population_observations", schema="stats")
