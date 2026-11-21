"""Materialized view for GET /v1/fields (Phase 1.1 performance fallback).

The on-demand coverage aggregation exceeded the plan's ~500 ms gate on the
working dataset (27-31 s for 229k facilities). This migration adds a refresh-
after-publication projection generated from the same declarative field mapping
in ``services/field_coverage``. The endpoint reads the view; the ingest publish
hook and the demo loader refresh it after a successful publication.

Revision ID: 0026_api_field_coverage_mv
Revises: 0025_source_link_facility_index
Create Date: 2026-11-21

Rollback: downgrade drops the unique index and the view. No canonical table is
modified, and the endpoint falls back to on-demand computation when the view is
absent. A future field addition requires a new migration to regenerate the view.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.services.coverage_mv import (
    MV_INDEX,
    MV_NAME,
    build_definition_sql,
    create_index_sql,
)

revision = "0026_api_field_coverage_mv"
down_revision = "0025_source_link_facility_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(build_definition_sql())
    op.execute(create_index_sql())
    # Populate immediately so a freshly migrated database can serve the endpoint
    # before the first publication. Later refreshes happen in the ingest hook.
    op.execute(f"REFRESH MATERIALIZED VIEW {MV_NAME}")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {MV_INDEX}")
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {MV_NAME}")
