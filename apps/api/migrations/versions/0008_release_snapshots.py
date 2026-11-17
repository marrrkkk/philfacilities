"""Release-scoped facility snapshots for atomic rollback.

Revision ID: 0008_release_snapshots
Revises: 0007_inclusion_model
Create Date: 2026-11-16

The ingestion pipeline updates canonical facilities in place. This table records
the pre-release facility aggregate once per release/facility so an authorised
rollback can restore the prior state without deleting the retained raw release,
source records, or change history of the rollback itself.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import ReleaseFacilitySnapshot
from sqlalchemy import inspect

revision = "0008_release_snapshots"
down_revision = "0007_inclusion_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(ReleaseFacilitySnapshot.__tablename__, schema="source"):
        ReleaseFacilitySnapshot.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table(ReleaseFacilitySnapshot.__tablename__, schema="source"):
        op.drop_table(ReleaseFacilitySnapshot.__tablename__, schema="source")
