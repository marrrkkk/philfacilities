"""Refresh the API field-coverage projection after a publication commit.

The materialized view is a read-side performance projection: a failed refresh
must never fail a publication or roll back canonical data. A missing view means
migration 0026 has not been applied yet, which is also non-fatal.
"""

from __future__ import annotations

import logging

from philfacilities_api.services.coverage_mv import refresh_coverage_mv
from sqlalchemy.orm import Session

logger = logging.getLogger("philfacilities.ingest.coverage_refresh")


def refresh_coverage_after_publication(session: Session) -> None:
    """Best-effort refresh; callers invoke this only after a successful commit."""

    try:
        refresh_coverage_mv(session)
    except Exception as exc:  # pragma: no cover - defensive against DB state
        # Missing projection on an older database, or a transient refresh
        # failure. Publication itself must remain successful.
        logger.warning("field-coverage projection refresh skipped: %s", exc)
