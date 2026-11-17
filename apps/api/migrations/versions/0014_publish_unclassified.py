"""Publish unclassified institution-level records.

Revision ID: 0014_publish_unclassified
Revises: 0013_contacts_postal
Create Date: 2026-11-18

Publication is a rights/safety decision, not a classification decision. Records
whose source has no ownership or sector evidence stay labelled
``DISCOVERY_CANDIDATE`` but are now eligible for public release, so the registry
does not hide already-ingested facility rows merely because ownership is unknown.

This backfill mirrors the API publication gate: the facility must have a source
link in its dataset's latest published release, and that dataset/release must
still be rights-cleared. Personal and safety exclusions are enforced earlier in
ingestion and are not touched here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_publish_unclassified"
down_revision = "0013_contacts_postal"
branch_labels = None
depends_on = None


_PUBLISHABLE = """
UPDATE core.facilities AS f
SET publication_status = 'public',
    updated_at = now()
WHERE f.publication_status = 'internal'
  AND f.inclusion_class = 'DISCOVERY_CANDIDATE'
  AND EXISTS (
    SELECT 1
    FROM source.facility_source_links AS l
    JOIN source.records AS sr
      ON sr.id = l.source_record_id
    JOIN source.releases AS r
      ON r.id = sr.release_id
    JOIN source.datasets AS d
      ON d.id = r.dataset_id
    WHERE l.facility_id = f.id
      AND r.ingestion_status = 'published'
      AND r.publication_status IN ('approved', 'published')
      AND (
        d.is_synthetic
        OR (
          d.publication_status IN ('approved', 'published')
          AND d.redistribution_status IN (
            'approved_public_redistribution',
            'approved_with_attribution',
            'publicly_available_verified'
          )
        )
      )
      AND r.id = (
        SELECT r2.id
        FROM source.releases AS r2
        WHERE r2.dataset_id = d.id
          AND r2.ingestion_status = 'published'
          AND r2.publication_status IN ('approved', 'published')
        ORDER BY r2.retrieved_at DESC, r2.created_at DESC
        LIMIT 1
      )
  )
"""


def upgrade() -> None:
    op.execute(sa.text(_PUBLISHABLE))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE core.facilities
            SET publication_status = 'internal',
                updated_at = now()
            WHERE publication_status = 'public'
              AND inclusion_class = 'DISCOVERY_CANDIDATE'
            """
        )
    )
