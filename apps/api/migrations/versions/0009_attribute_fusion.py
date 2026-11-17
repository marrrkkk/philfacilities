"""Derived attribute fusion with retained conflicts.

Revision ID: 0009_attribute_fusion
Revises: 0008_release_snapshots
Create Date: 2026-11-16

Source claims stay immutable in ``core.attribute_assertions``. This table stores
the selected display value plus every conflicting value and its provenance, so
deduplication combines information instead of discarding it.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import FacilityAttributeFusion
from sqlalchemy import inspect

revision = "0009_attribute_fusion"
down_revision = "0008_release_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(FacilityAttributeFusion.__tablename__, schema="core"):
        FacilityAttributeFusion.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table(FacilityAttributeFusion.__tablename__, schema="core"):
        op.drop_table(FacilityAttributeFusion.__tablename__, schema="core")
