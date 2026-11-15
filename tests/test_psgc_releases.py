"""Versioned PSGC releases and the crosswalk between them.

This test adds a second synthetic PSGC release to the shared integration database,
exercises the real ingestion path and the public crosswalk endpoint, then removes the
release again. Cleanup is explicit because the ingestion pipeline commits internally.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, select

pytestmark = [pytest.mark.integration, pytest.mark.data_quality]


def test_two_psgc_releases_coexist_and_crosswalk_renames_are_queryable(client, db_session):
    from philfacilities_api.models import (
        AdministrativeUnit,
        Dataset,
        GeographicRelease,
        GeographyCrosswalk,
        IngestionRun,
    )
    from philfacilities_ingest.contracts import ReleaseSpec
    from philfacilities_ingest.fixtures import (
        ALL_UNITS,
        BARANGAYS,
        FIXTURE_PUBLISHED_AT,
        FIXTURE_RETRIEVED_AT,
        psgc_workbook,
    )
    from philfacilities_ingest.pipeline import run_psgc_ingestion

    previous_label = "SYNTHETIC-DEMO-2026-Q3"
    second_label = "SYNTHETIC-TEST-2026-Q4"
    renamed_barangay = "Synthetic Barangay Renamed (demo)"
    renamed_code = BARANGAYS[0].code
    original_name = BARANGAYS[0].name

    existing_runs = set(db_session.scalars(select(IngestionRun.id)).all())
    existing_release = db_session.scalars(
        select(GeographicRelease).where(GeographicRelease.release_label == second_label)
    ).first()
    assert existing_release is None

    spec = ReleaseSpec(
        agency_code="psa",
        agency_name="Philippine Statistics Authority (synthetic demo fixture)",
        dataset_slug="demo-psgc",
        dataset_name="Synthetic demo geography (PSGC-shaped)",
        release_label=second_label,
        filename="synthetic-psgc-2026-q4.xlsx",
        content=psgc_workbook(rename_first_barangay=renamed_barangay),
        source_published_at=FIXTURE_PUBLISHED_AT,
        retrieved_at=FIXTURE_RETRIEVED_AT,
        reference_period_start=date(2026, 10, 1),
        reference_period_end=date(2026, 12, 31),
        redistribution_status="not_applicable",
        access_method="synthetic_fixture",
        update_pattern="generated for demonstration only",
        license_identifier="Synthetic fixture — no source-data rights",
        is_synthetic=True,
    )

    release_id = None
    try:
        result = run_psgc_ingestion(spec=spec, session=db_session)
        assert result.status == "published"
        assert result.stats["units"] == len(ALL_UNITS)
        assert result.stats["crosswalk_changes"] == 1

        releases = db_session.scalars(
            select(GeographicRelease).order_by(GeographicRelease.reference_date.desc())
        ).all()
        assert [release.release_label for release in releases] == [second_label, previous_label]
        second_release = releases[0]
        release_id = second_release.id
        assert second_release.is_synthetic is True
        assert second_release.sha256

        unit_count = db_session.scalar(
            select(func.count())
            .select_from(AdministrativeUnit)
            .where(AdministrativeUnit.release_id == release_id)
        )
        assert unit_count == len(ALL_UNITS)

        # Both releases remain queryable, newest first, through the public API.
        response = client.get("/v1/geography-releases")
        assert response.status_code == 200
        assert [row["release_label"] for row in response.json()] == [
            second_label,
            previous_label,
        ]

        crosswalk = client.get(
            "/v1/geography-crosswalk",
            params={"from_release": previous_label, "to_release": second_label},
        )
        assert crosswalk.status_code == 200
        changes = crosswalk.json()
        assert len(changes) == 1
        change = changes[0]
        assert change["from_psgc_code"] == renamed_code
        assert change["to_psgc_code"] == renamed_code
        assert change["change_type"] == "renamed"
        assert change["from_release"] == previous_label
        assert change["to_release"] == second_label
        assert change["evidence"] == {
            "old_name": original_name,
            "new_name": renamed_barangay,
        }
    finally:
        # The pipeline commits, so explicitly remove the test release and its dependants.
        db_session.rollback()
        if release_id is None:
            second_release = db_session.scalars(
                select(GeographicRelease).where(GeographicRelease.release_label == second_label)
            ).first()
            release_id = second_release.id if second_release else None
        if release_id is not None:
            db_session.execute(
                delete(GeographyCrosswalk).where(
                    (GeographyCrosswalk.from_release_id == release_id)
                    | (GeographyCrosswalk.to_release_id == release_id)
                )
            )
            db_session.execute(
                delete(AdministrativeUnit).where(AdministrativeUnit.release_id == release_id)
            )
            db_session.execute(
                delete(IngestionRun).where(
                    IngestionRun.id.not_in(existing_runs),
                    IngestionRun.dataset_id.in_(
                        select(Dataset.id).where(Dataset.slug == "demo-psgc")
                    ),
                )
            )
            release = db_session.get(GeographicRelease, release_id)
            if release is not None:
                db_session.delete(release)
            db_session.commit()
            assert (
                db_session.scalars(
                    select(GeographicRelease).where(GeographicRelease.release_label == second_label)
                ).first()
                is None
            )


def test_real_geography_release_is_not_masked_by_newer_synthetic_release(db_session):
    """The map/geography resolver must prefer real geography over demo fixtures."""

    from philfacilities_api.models import GeographicRelease
    from philfacilities_api.services import latest_geographic_release

    label = "TEST-REAL-GEOGRAPHY-PREFERENCE"
    existing = db_session.scalars(
        select(GeographicRelease).where(GeographicRelease.release_label == label)
    ).first()
    assert existing is None
    release = GeographicRelease(
        release_label=label,
        reference_date=date(2020, 1, 1),
        retrieved_at=datetime.now(UTC),
        is_synthetic=False,
    )
    db_session.add(release)
    db_session.commit()
    try:
        selected = latest_geographic_release(db_session)
        assert selected is not None
        assert selected.release_label == label
        assert selected.is_synthetic is False
    finally:
        db_session.delete(release)
        db_session.commit()
