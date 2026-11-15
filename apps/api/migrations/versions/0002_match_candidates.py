"""Add the deterministic identity-match review queue.

Revision ID: 0002_match_candidates
Revises: 0001_baseline
Create Date: 2026-11-14

The baseline migration materialises the current SQLAlchemy metadata, so a fresh
database already contains this table when the baseline runs. This migration is
therefore idempotent for fresh installs and adds the table to existing databases.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import MatchCandidate
from sqlalchemy import inspect

revision = "0002_match_candidates"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("match_candidates", schema="quality"):
        MatchCandidate.__table__.create(bind=bind)


def downgrade() -> None:
    op.drop_table("match_candidates", schema="quality")
