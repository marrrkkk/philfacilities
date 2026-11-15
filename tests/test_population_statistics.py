"""Tests for the BetterGov/PSA population connector and its public shape."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime

import httpx
import pytest
from philfacilities_ingest.acquisition import HttpAcquirer
from philfacilities_ingest.sources.bettergov_stats import (
    PopulationSnapshot,
    _geographic_level,
    _indicator_unit,
    _observation_payload,
    fetch_population_snapshot,
)

DATASET_ID = "a" * 20
RELEASE = "2026-08-12T09-17-54-c9118a9b8b64"


def _snapshot() -> PopulationSnapshot:
    return PopulationSnapshot(
        dataset_id=DATASET_ID,
        title=(
            "Total Population, Household Population, and Number of Households by "
            "Province, City, Municipality, and Barangay as of 01 July 2024: Test Region"
        ),
        release=RELEASE,
        psa_source_url="https://openstat.psa.gov.ph/example.px",
        source_updated_at=datetime(2026, 8, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
        unit="Reported value — see source for units",
        dimensions=["Geographic Location", "Parameter"],
        geographic_values=[],
        parameter_values=[],
        rows=[],
        reported_cells=4,
    )


def test_geographic_level_uses_openstat_depth_and_handles_hucs():
    assert _geographic_level("1300000000", "..National Capital Region (NCR)") == "region"
    assert _geographic_level("1001300000", "....Bukidnon") == "province_or_huc"
    assert _geographic_level("1380100000", "....City of Caloocan") == "province_or_huc"
    assert _geographic_level("1001301000", "......Baungon") == "municipality"
    assert _geographic_level("1001301001", "........Balintad") == "barangay"
    assert _geographic_level("x", "") == "unknown"


def test_indicator_units_are_explicit_and_do_not_invent_capacity():
    assert _indicator_unit("Total Population", "reported") == "persons"
    assert _indicator_unit("Household Population", "reported") == "persons"
    assert _indicator_unit("Number of Households", "reported") == "households"
    assert _indicator_unit("Some Other Indicator", "reported") == "reported"


def test_observation_payload_preserves_null_and_source_dimensions():
    snapshot = _snapshot()
    payload = _observation_payload(
        snapshot,
        {
            "codes": ["1001301001", "0"],
            "labels": ["........Balintad", "Total Population"],
            "value": None,
            "status": "..",
        },
    )
    assert payload["source_record_key"] == f"{DATASET_ID}:1001301001:0"
    assert payload["psgc_code"] == "1001301001"
    assert payload["geographic_name"] == "Balintad"
    assert payload["geographic_level"] == "barangay"
    assert payload["indicator_label"] == "Total Population"
    assert payload["value"] is None
    assert payload["unit"] == "persons"
    assert payload["raw_payload"]["status"] == ".."


def test_fetch_population_snapshot_paginates_and_bounds_queries():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == f"/api/v1/datasets/{DATASET_ID}":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": DATASET_ID,
                        "title": ("Total Population ... as of 01 July 2024: Test Region"),
                        "source": "https://openstat.psa.gov.ph/example.px",
                        "sourceUpdated": "2026-08-12T09:17:54",
                        "retrieved": "2026-09-09T18:49:33.963Z",
                        "release": RELEASE,
                        "ready": True,
                        "cells": "4",
                        "unit": "Reported value — see source for units",
                        "dimensions": [
                            {"code": "Geographic Location", "label": "Geographic Location"},
                            {"code": "Parameter", "label": "Parameter"},
                        ],
                    }
                },
            )
        if path.endswith("/values"):
            dimension = request.url.params["dimension"]
            if dimension == "Geographic Location":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"code": "1000000000", "label": "..Test Region"},
                            {"code": "1001301001", "label": "........Balintad"},
                        ],
                        "pagination": {"total": 2, "limit": 200, "offset": 0, "nextOffset": None},
                        "dimension": {"code": dimension, "label": dimension},
                        "release": RELEASE,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"code": "0", "label": "Total Population"},
                        {"code": "1", "label": "Number of Households"},
                    ],
                    "pagination": {"total": 2, "limit": 200, "offset": 0, "nextOffset": None},
                    "dimension": {"code": dimension, "label": dimension},
                    "release": RELEASE,
                },
            )
        if path.endswith("/query"):
            body = json.loads(request.content)
            assert body["release"] == RELEASE
            assert set(body["selection"]) == {"Geographic Location", "Parameter"}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "rows": [
                            {
                                "codes": ["1000000000", "0"],
                                "labels": ["..Test Region", "Total Population"],
                                "value": 100,
                                "status": "",
                            },
                            {
                                "codes": ["1000000000", "1"],
                                "labels": ["..Test Region", "Number of Households"],
                                "value": 20,
                                "status": "",
                            },
                            {
                                "codes": ["1001301001", "0"],
                                "labels": ["........Balintad", "Total Population"],
                                "value": 5,
                                "status": "",
                            },
                            {
                                "codes": ["1001301001", "1"],
                                "labels": ["........Balintad", "Number of Households"],
                                "value": None,
                                "status": "..",
                            },
                        ],
                        "count": 4,
                        "release": RELEASE,
                    }
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    with HttpAcquirer(transport=httpx.MockTransport(handler)) as acquirer:
        snapshot, results = fetch_population_snapshot(acquirer, DATASET_ID)

    assert snapshot.region_label == "Test Region"
    assert snapshot.reported_cells == 4
    assert len(snapshot.rows) == 4
    assert len(results) == 2
    assert _observation_payload(snapshot, snapshot.rows[-1])["value"] is None


@pytest.mark.integration
def test_population_api_filters_and_hides_blocked_sources(db_session):
    from philfacilities_api.api.population import population
    from philfacilities_api.models import Agency, Dataset, PopulationObservation, Release

    agency = Agency(name="Population Test Publisher", short_code="pop-test")
    db_session.add(agency)
    db_session.flush()

    def make_dataset(status: str, rights: str) -> tuple[Dataset, Release]:
        dataset = Dataset(
            agency_id=agency.id,
            slug=f"pop-test-{status}-{uuid.uuid4().hex[:6]}",
            name="Population test dataset",
            redistribution_status=rights,
            publication_status=status,
            is_public_source=True,
            is_synthetic=False,
        )
        db_session.add(dataset)
        db_session.flush()
        release = Release(
            dataset_id=dataset.id,
            source_release_label=f"POP-TEST-{status}-{uuid.uuid4().hex[:8]}",
            retrieved_at=datetime.now(UTC),
            sha256=uuid.uuid4().hex,
            row_count_parsed=1,
            ingestion_status="published",
            terms_review_status=rights,
            publication_status=status,
        )
        db_session.add(release)
        db_session.flush()
        return dataset, release

    approved_dataset, approved_release = make_dataset("published", "approved_with_attribution")
    _blocked_dataset, blocked_release = make_dataset("blocked", "blocked")
    try:
        for index, (release, value) in enumerate(((approved_release, 123), (blocked_release, 999))):
            db_session.add(
                PopulationObservation(
                    release_id=release.id,
                    source_record_key=f"test:{'approved' if index == 0 else 'blocked'}:0",
                    psgc_code="9999999999",
                    geographic_level="region",
                    geographic_name="Test Region",
                    indicator_code="0",
                    indicator_label="Total Population",
                    value=value,
                    unit="persons",
                    reference_date=date(2024, 7, 1),
                    reference_period="2024 Census test",
                    dimensions={
                        "Geographic Location": "Test Region",
                        "Parameter": "Total Population",
                    },
                    source_url="https://openstat.psa.gov.ph/example.px",
                )
            )
        db_session.flush()

        result = population(db=db_session, psgc="9999999999", indicator="Total Population")
        assert result.total == 1
        assert result.items[0].value == 123
        assert result.items[0].release_id == approved_release.id
        assert result.items[0].dataset_slug == approved_dataset.slug
        assert result.caveats

        blocked = population(
            db=db_session,
            psgc="9999999999",
            indicator="Total Population",
            level="region",
        )
        assert all(item.release_id != blocked_release.id for item in blocked.items)
    finally:
        db_session.rollback()


@pytest.mark.integration
def test_population_loader_flushes_source_records_before_observations(db_session):
    """Regression: a chunked load must insert records before their FK dependants.

    SQLAlchemy's unit of work does not infer a per-row insert order from a bare
    foreign key, so the loader flushes each source-record chunk first. Before that
    fix a 500-row chunk raised a foreign-key violation on ``source_record_id``.
    """

    from philfacilities_api.models import (
        Dataset,
        IngestionRun,
        PopulationObservation,
        PublicationGate,
        Release,
        SourceRecord,
    )
    from philfacilities_ingest.config import get_settings
    from philfacilities_ingest.sources.bettergov_stats import load_population_snapshot
    from sqlalchemy import delete, func, select

    settings = get_settings()
    geographic_values = [
        {"code": f"9999{index:06d}", "label": f"......Test Place {index}"} for index in range(501)
    ]
    rows = [
        {
            "codes": [value["code"], "0"],
            "labels": [value["label"], "Total Population"],
            "value": index,
            "status": "",
        }
        for index, value in enumerate(geographic_values)
    ]
    snapshot = PopulationSnapshot(
        dataset_id="test-population-insert-order",
        title="Total Population ... as of 01 July 2024: Test Insert Order",
        release="test-release",
        psa_source_url="https://openstat.psa.gov.ph/example.px",
        source_updated_at=datetime(2026, 8, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
        unit="persons",
        dimensions=["Geographic Location", "Parameter"],
        geographic_values=geographic_values,
        parameter_values=[{"code": "0", "label": "Total Population"}],
        rows=rows,
        reported_cells=len(rows),
    )

    result = load_population_snapshot(
        session=db_session,
        settings=settings,
        snapshot=snapshot,
    )
    release = db_session.get(Release, uuid.UUID(result["release_id"]))
    assert release is not None
    dataset_id = release.dataset_id
    try:
        assert result["observations"] == 501
        observation_count = db_session.scalar(
            select(func.count())
            .select_from(PopulationObservation)
            .where(PopulationObservation.release_id == release.id)
        )
        record_count = db_session.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(SourceRecord.release_id == release.id)
        )
        assert observation_count == 501
        assert record_count == 501
        joined = db_session.execute(
            select(func.count())
            .select_from(PopulationObservation)
            .join(SourceRecord, SourceRecord.id == PopulationObservation.source_record_id)
            .where(PopulationObservation.release_id == release.id)
        ).scalar_one()
        assert joined == 501
    finally:
        db_session.execute(
            delete(PopulationObservation).where(PopulationObservation.release_id == release.id)
        )
        db_session.execute(delete(SourceRecord).where(SourceRecord.release_id == release.id))
        db_session.execute(delete(IngestionRun).where(IngestionRun.release_id == release.id))
        db_session.delete(release)
        db_session.flush()
        remaining = db_session.scalar(
            select(func.count()).select_from(Release).where(Release.dataset_id == dataset_id)
        )
        if remaining == 0:
            db_session.execute(
                delete(PublicationGate).where(PublicationGate.dataset_id == dataset_id)
            )
            db_session.execute(delete(Dataset).where(Dataset.id == dataset_id))
        db_session.commit()
