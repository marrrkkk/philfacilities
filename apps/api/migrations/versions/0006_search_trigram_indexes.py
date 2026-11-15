"""Add trigram indexes used by the public search.

Revision ID: 0006_search_trigram_indexes
Revises: 0005_unique_current_location
Create Date: 2026-11-15

The directory search matches substrings across facility names, source record
keys, addresses, and administrative-unit names. Without trigram indexes each
search degrades to a sequential scan of the national dataset. These indexes
were created manually during the performance investigation; this migration
brings fresh and test databases to the same state.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0006_search_trigram_indexes"
down_revision = "0005_unique_current_location"
branch_labels = None
depends_on = None

INDEXES = (
    (
        "core",
        "facilities",
        "ix_core_facilities_official_name_trgm",
        "official_name",
    ),
    (
        "core",
        "facility_locations",
        "ix_core_facility_locations_address_trgm",
        "address_text",
    ),
    (
        "source",
        "records",
        "ix_source_records_source_key_trgm",
        "source_record_key",
    ),
    (
        "geo",
        "administrative_units",
        "ix_geo_admin_units_name_trgm",
        "name",
    ),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    bind = op.get_bind()
    inspector = inspect(bind)
    for schema, table, name, column in INDEXES:
        existing = {index["name"] for index in inspector.get_indexes(table, schema=schema)}
        if name not in existing:
            op.execute(f"CREATE INDEX {name} ON {schema}.{table} USING gin ({column} gin_trgm_ops)")


def downgrade() -> None:
    for schema, _table, name, _column in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {schema}.{name}")
