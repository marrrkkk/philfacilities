"""Baseline PhilFacilities schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-14

The canonical schema is owned by the SQLAlchemy models. This first migration creates
the required PostgreSQL extensions and schemas, then materialises the model metadata.
Later migrations should be generated from model changes as normal.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("source", "core", "geo", "school", "health", "utility", "quality", "history", "stats")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
