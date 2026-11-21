"""Index facility_source_links by facility for bulk evidence reads.

Public source evidence is loaded by facility id on every detail page and bulk
export. Without a leading facility_id index PostgreSQL sequentially scanned the
whole link table for each lookup, which made national exports impractical. The
unique (facility_id, source_record_id) constraint already exists but its wider
key is not used for these single-column probes, so add a covering index.

Revision ID: 0025_source_link_facility_index
Revises: 0024_drop_enrollment
Create Date: 2026-11-21

The baseline migration materialises the current metadata, so a fresh database
may already have the index. The migration checks before creating it.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0025_source_link_facility_index"
down_revision = "0024_drop_enrollment"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_links_facility_id"
TABLE_NAME = "facility_source_links"
SCHEMA = "source"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes(TABLE_NAME, schema=SCHEMA)}
    if INDEX_NAME not in existing:
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["facility_id"],
            unique=False,
            schema=SCHEMA,
            postgresql_include=["source_record_id"],
        )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME, schema=SCHEMA)
