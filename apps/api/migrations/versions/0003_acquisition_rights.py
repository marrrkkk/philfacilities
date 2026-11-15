"""Add acquisition monitoring and explicit rights/publication metadata.

Revision ID: 0003_acquisition_rights
Revises: 0002_match_candidates
Create Date: 2026-11-15

Fresh databases receive every column from the baseline metadata. This migration
upgrades databases created before the acquisition ledger existed and is safe to
run against either state.
"""

from __future__ import annotations

from alembic import op
from philfacilities_api.models import SourceCheck
from sqlalchemy import inspect

revision = "0003_acquisition_rights"
down_revision = "0002_match_candidates"
branch_labels = None
depends_on = None


def _columns(table: str, schema: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table, schema=schema)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    dataset_columns = _columns("datasets", "source")
    dataset_additions = {
        "rights_basis": "TEXT",
        "attribution_text": "TEXT",
        "personal_data_status": "VARCHAR(60)",
        "publication_status": "VARCHAR(40) NOT NULL DEFAULT 'blocked'",
    }
    for name, ddl in dataset_additions.items():
        if name not in dataset_columns:
            op.execute(f"ALTER TABLE source.datasets ADD COLUMN {name} {ddl}")

    release_columns = _columns("releases", "source")
    if "publication_status" not in release_columns:
        op.execute(
            "ALTER TABLE source.releases ADD COLUMN publication_status "
            "VARCHAR(40) NOT NULL DEFAULT 'blocked'"
        )

    accreditation_columns = _columns("accreditations", "health")
    accreditation_additions = {
        "telephone": "VARCHAR(160)",
        "email": "VARCHAR(200)",
        "street_address": "TEXT",
        "municipality": "VARCHAR(120)",
    }
    for name, ddl in accreditation_additions.items():
        if name not in accreditation_columns:
            op.execute(f"ALTER TABLE health.accreditations ADD COLUMN {name} {ddl}")

    if not inspector.has_table("source_checks", schema="source"):
        SourceCheck.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("source_checks", schema="source"):
        op.drop_table("source_checks", schema="source")
    for name in ("rights_basis", "attribution_text", "personal_data_status", "publication_status"):
        if name in _columns("datasets", "source"):
            op.execute(f"ALTER TABLE source.datasets DROP COLUMN {name}")
    if "publication_status" in _columns("releases", "source"):
        op.execute("ALTER TABLE source.releases DROP COLUMN publication_status")
    for name in ("telephone", "email", "street_address", "municipality"):
        if name in _columns("accreditations", "health"):
            op.execute(f"ALTER TABLE health.accreditations DROP COLUMN {name}")
