"""Add OSM administrative boundary polygons for map-location resolution.

Revision ID: 0016_osm_admin_boundaries
Revises: 0015_read_path_indexes
Create Date: 2026-11-18

The boundary layer is derived from one preserved Geofabrik PBF snapshot. It is
reference data: one current snapshot replaces the previous one on re-import, and
the raw Parquet extract remains the reproducible artifact.
"""

from __future__ import annotations

from alembic import op

revision = "0016_osm_admin_boundaries"
down_revision = "0015_read_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geo.osm_admin_boundaries (
            id uuid NOT NULL,
            osm_type varchar(10) NOT NULL,
            osm_id bigint NOT NULL,
            admin_level integer NOT NULL,
            name text,
            ref varchar(40),
            psgc_code varchar(12),
            geographic_level varchar(40),
            parent_psgc_code varchar(12),
            resolution_method varchar(40),
            geom geometry(MultiPolygon, 4326) NOT NULL,
            area_deg2 double precision,
            release_label varchar(120) NOT NULL,
            source_url text NOT NULL,
            source_sha256 varchar(64),
            source_published_at timestamptz,
            retrieved_at timestamptz NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_osm_admin_boundaries PRIMARY KEY (id),
            CONSTRAINT uq_geo_osm_admin_boundaries_osm UNIQUE (osm_type, osm_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_geo_osm_admin_boundaries_geom "
        "ON geo.osm_admin_boundaries USING gist (geom)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_geo_osm_admin_boundaries_psgc "
        "ON geo.osm_admin_boundaries (psgc_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_geo_osm_admin_boundaries_level "
        "ON geo.osm_admin_boundaries (admin_level)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS geo.osm_admin_boundaries")
