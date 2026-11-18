"""Add feed, map, and latest-release indexes for the public read paths.

Revision ID: 0015_read_path_indexes
Revises: 0014_publish_unclassified
Create Date: 2026-11-18

The national working database exposed three sequential scans on every public
request:

* directory pages sorted all 258k facilities by ``updated_at, id``;
* map viewports scanned every current location because the bbox GiST index was
  combined with the full ``is_current`` set;
* the latest-published-release lookup sorted releases per dataset.

These indexes keep the cursor feed, the clustered map query, and the release
subquery on indexed paths. They change no vocabulary, publication rule, or row.
"""

from __future__ import annotations

from alembic import op

revision = "0015_read_path_indexes"
down_revision = "0014_publish_unclassified"
branch_labels = None
depends_on = None

INDEXES = (
    (
        "core",
        "ix_core_facilities_public_feed",
        "CREATE INDEX IF NOT EXISTS ix_core_facilities_public_feed "
        "ON core.facilities (publication_status, updated_at DESC, id DESC)",
    ),
    (
        "core",
        "ix_core_facilities_updated_feed",
        "CREATE INDEX IF NOT EXISTS ix_core_facilities_updated_feed "
        "ON core.facilities (updated_at DESC, id DESC)",
    ),
    (
        "core",
        "ix_core_facility_locations_current_geom",
        "CREATE INDEX IF NOT EXISTS ix_core_facility_locations_current_geom "
        "ON core.facility_locations USING gist (geom) WHERE is_current",
    ),
    (
        "source",
        "ix_source_releases_dataset_retrieved",
        "CREATE INDEX IF NOT EXISTS ix_source_releases_dataset_retrieved "
        "ON source.releases (dataset_id, retrieved_at DESC, created_at DESC)",
    ),
)


def upgrade() -> None:
    for _schema, _name, statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    for schema, name, _statement in reversed(INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {schema}.{name}")
