"""Pipeline idempotency against the live test database."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def _counts(session) -> dict[str, int]:
    from philfacilities_api.models import (
        Dataset,
        Facility,
        GeographicRelease,
        QualityIssue,
        Release,
        SourceRecord,
    )

    return {
        "facilities": session.scalar(select(func.count()).select_from(Facility)),
        "datasets": session.scalar(select(func.count()).select_from(Dataset)),
        "releases": session.scalar(select(func.count()).select_from(Release)),
        "geographic_releases": session.scalar(select(func.count()).select_from(GeographicRelease)),
        "source_records": session.scalar(select(func.count()).select_from(SourceRecord)),
        "quality_issues": session.scalar(select(func.count()).select_from(QualityIssue)),
    }


def test_loading_the_demo_twice_is_idempotent(db_session):
    from philfacilities_ingest.cli import load_demo

    before = _counts(db_session)
    assert before["facilities"] == 22
    assert before["datasets"] == 6
    assert before["releases"] == 5
    assert before["geographic_releases"] == 1

    load_demo(reset=False)
    after = _counts(db_session)
    assert after == before

    # A duplicate checksum must not append another published release row.
    from philfacilities_api.models import Release

    published = db_session.scalar(
        select(func.count()).select_from(Release).where(Release.ingestion_status == "published")
    )
    assert published == 5

    # Duplicate runs are still recorded for auditability.
    from philfacilities_api.models import IngestionRun

    skipped = db_session.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(IngestionRun.status == "skipped_duplicate")
    )
    assert skipped and skipped >= 5
