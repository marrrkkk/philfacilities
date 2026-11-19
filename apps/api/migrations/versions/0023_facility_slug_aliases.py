"""Add aliases for retired public facility slugs.

Slugs created by bulk ingestion carried a source suffix (``-osm``, ``-doh``,
``-nha`` and so on). Consolidation removes duplicate facilities, and a later
slug-normalization pass removes those suffixes from surviving public slugs.
The alias table keeps the previous slug resolvable without retaining a second
facility record.

Revision ID: 0023_facility_slug_aliases
Revises: 0022_merge_lookup_indexes
Create Date: 2026-11-19

The baseline migration materialises the current SQLAlchemy metadata, so the
table and index can already exist on a fresh database. The migration checks
first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0023_facility_slug_aliases"
down_revision = "0022_merge_lookup_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "facility_slug_aliases" not in inspector.get_table_names(schema="core"):
        op.create_table(
            "facility_slug_aliases",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("slug", sa.String(length=180), nullable=False),
            sa.Column("facility_id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["facility_id"],
                ["core.facilities.id"],
                name="fk_facility_slug_aliases_facility_id_facilities",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_facility_slug_aliases"),
            sa.UniqueConstraint("slug", name="uq_facility_slug_aliases_slug"),
            schema="core",
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_core_facility_slug_aliases_facility "
        "ON core.facility_slug_aliases (facility_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS core.ix_core_facility_slug_aliases_facility")
    op.execute("DROP TABLE IF EXISTS core.facility_slug_aliases")
