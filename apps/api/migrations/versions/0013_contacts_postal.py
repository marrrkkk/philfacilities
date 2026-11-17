"""Add source-linked facility contacts and postal codes.

Revision ID: 0013_contacts_postal
Revises: 0012_merge_0011_heads
Create Date: 2026-11-17

Contacts are separate rows because a facility can have several institutional
channels from several sources. The postal code is a source-supplied part of the
address, not a value derived from PSGC or geocoding.

The baseline migration materialises the current SQLAlchemy metadata, so the
table and column can already exist on a fresh database. The migration checks
first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from philfacilities_api.models import FacilityContact
from sqlalchemy import inspect

revision = "0013_contacts_postal"
down_revision = "0012_merge_0011_heads"
branch_labels = None
depends_on = None


def _location_columns() -> set[str]:
    return {
        column["name"]
        for column in inspect(op.get_bind()).get_columns("facility_locations", schema="core")
    }


def upgrade() -> None:
    if "postal_code" not in _location_columns():
        op.add_column(
            "facility_locations",
            sa.Column("postal_code", sa.String(length=20), nullable=True),
            schema="core",
        )
    FacilityContact.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    FacilityContact.__table__.drop(bind=op.get_bind(), checkfirst=True)
    if "postal_code" in _location_columns():
        op.drop_column("facility_locations", "postal_code", schema="core")
