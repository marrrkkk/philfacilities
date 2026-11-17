"""Persist the parsed schema version on each release.

Adapters declare both ``parser_version`` and ``schema_version``. The pipeline
stored only the parser version, so a release could not be audited against the
schema it was parsed with even though the run report recorded it.

Revision ID: 0011_release_schema_version
Revises: 0010_ingest_hot_path_indexes
Create Date: 2026-11-17

The baseline migration materialises the current SQLAlchemy metadata, so the
column can already exist on a fresh database. The migration checks first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0011_release_schema_version"
down_revision = "0010_ingest_hot_path_indexes"
branch_labels = None
depends_on = None


def _release_columns() -> set[str]:
    return {
        column["name"] for column in inspect(op.get_bind()).get_columns("releases", schema="source")
    }


def upgrade() -> None:
    if "schema_version" not in _release_columns():
        op.add_column(
            "releases",
            sa.Column("schema_version", sa.String(length=60), nullable=True),
            schema="source",
        )


def downgrade() -> None:
    if "schema_version" in _release_columns():
        op.drop_column("releases", "schema_version", schema="source")
