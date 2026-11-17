"""Deterministic OSM coordinate gap-fill (data.md section 10.6)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import philfacilities_ingest.location_fill as fill
import pytest


def test_already_filled_batches_large_id_sets():
    """More ids than PostgreSQL's 65535-parameter limit must not fail."""

    class RecordingSession:
        def __init__(self):
            self.chunk_sizes = []

        def scalars(self, statement):
            compiled = statement.compile(compile_kwargs={"render_postcompile": True})
            self.chunk_sizes.append(len(compiled.params) - 1)  # minus the method bind
            return []

    session = RecordingSession()
    ids = {uuid.uuid4() for _ in range(12001)}
    assert fill._already_filled(session, ids) == set()
    assert session.chunk_sizes == [5000, 5000, 2001]


def test_coordinate_prefers_bbox_centre_then_lat_lon():
    assert fill._coordinate({"_bbox_center_latitude": 14.5, "_bbox_center_longitude": 121.0}) == (
        14.5,
        121.0,
    )
    assert fill._coordinate({"latitude": "14.6", "longitude": "121.1"}) == (14.6, 121.1)
    assert fill._coordinate({"lat": "not-a-number", "lon": "121"}) == (None, None)


def test_psgc_preserves_leading_zeros_and_accepts_ph_prefix():
    assert fill._psgc_from_payload({"adm4_pcode": "PH012801000"}) == "0128010000"
    assert fill._psgc_from_payload({"adm3_pcode": "012801000"}) == "0128010000"
    assert fill._psgc_from_payload({"adm4_pcode": "PH133901001"}) == "1339010000"
    # A province-only code cannot identify the city/municipality.
    assert fill._psgc_from_payload({"adm2_pcode": "PH0128"}) is None
    assert fill._psgc_from_payload({}) is None


def test_city_resolver_uses_lowercase_levels_and_province_names():
    province = SimpleNamespace(
        psgc_code="0128000000",
        name="Ilocos Norte",
        geographic_level="province",
        parent_psgc_code="0100000000",
    )
    city = SimpleNamespace(
        psgc_code="0128010000",
        name="Adams",
        geographic_level="municipality",
        parent_psgc_code="0128000000",
    )
    duplicate_city = SimpleNamespace(
        psgc_code="0228010000",
        name="Adams",
        geographic_level="municipality",
        parent_psgc_code="0228000000",
    )
    result = MagicMock()
    result.first.return_value = SimpleNamespace(id="release")
    units = MagicMock()
    units.all.return_value = [province, city, duplicate_city]
    session = SimpleNamespace(scalars=MagicMock(side_effect=[result, units]))

    resolver = fill._CityResolver(session)
    assert resolver.resolve({"addr_city": "Adams", "addr_province": "Ilocos Norte"}) == "0128010"
    # Without a province, the duplicate city name is not guessed.
    assert resolver.resolve({"addr_city": "Adams"}) is None


def _candidate(name="Barangay Health Station", city_prefix="0128010", osm_id="node/1"):
    return {
        "record_id": uuid.uuid4(),
        "osm_id": osm_id,
        "name": name,
        "normalized_name": fill.normalize_name(name),
        "city_prefix": city_prefix,
        "latitude": 14.6,
        "longitude": 121.0,
        "dataset": "osm-health",
        "release_id": uuid.uuid4(),
        "snapshot": "2026-11-16",
        "address": None,
    }


def _facility_and_location(psgc="012801000"):
    facility = SimpleNamespace(
        id=uuid.uuid4(),
        slug="barangay-health-station",
        display_name="Barangay Health Station",
        facility_type="health_facility",
    )
    location = SimpleNamespace(
        psgc_code=psgc,
        address_text=None,
        postal_code=None,
    )
    return facility, location


def test_unique_exact_name_and_city_match_is_a_dry_run_fill(monkeypatch):
    facility, location = _facility_and_location()
    candidate = _candidate()
    monkeypatch.setattr(fill, "_CityResolver", lambda session: object())
    monkeypatch.setattr(fill, "_osm_candidates", lambda session, resolver: [candidate])
    monkeypatch.setattr(fill, "_target_facilities", lambda session: [(facility, location)])
    monkeypatch.setattr(fill, "_already_filled", lambda session, ids: set())

    result = fill.fill_locations_from_osm(session=None, apply=False)
    assert result.candidates == 1
    assert result.unlocated == 1
    assert result.matched == 1
    assert result.ambiguous == 0
    row = result.rows[0]
    assert row["osm_id"] == "node/1"
    assert row["match_method"] == "openstreetmap_match"
    assert row["precision"] == "map_geocoded"
    assert row["community_fallback"] is True
    assert "ODbL" in row["attribution"]


def test_two_candidates_leave_the_facility_unmapped(monkeypatch):
    facility, location = _facility_and_location()
    candidates = [_candidate(osm_id="node/1"), _candidate(osm_id="node/2")]
    monkeypatch.setattr(fill, "_CityResolver", lambda session: object())
    monkeypatch.setattr(fill, "_osm_candidates", lambda session, resolver: candidates)
    monkeypatch.setattr(fill, "_target_facilities", lambda session: [(facility, location)])
    monkeypatch.setattr(fill, "_already_filled", lambda session, ids: set())

    result = fill.fill_locations_from_osm(session=None, apply=False)
    assert result.matched == 0
    assert result.ambiguous == 1
    assert result.rows == []


def test_missing_city_evidence_is_not_geocoded(monkeypatch):
    facility, location = _facility_and_location(psgc=None)
    monkeypatch.setattr(fill, "_CityResolver", lambda session: object())
    monkeypatch.setattr(fill, "_osm_candidates", lambda session, resolver: [_candidate()])
    monkeypatch.setattr(fill, "_target_facilities", lambda session: [(facility, location)])
    monkeypatch.setattr(fill, "_already_filled", lambda session, ids: set())

    result = fill.fill_locations_from_osm(session=None, apply=False)
    assert result.matched == 0
    assert result.unmatched == 1


def test_city_aliases_resolve_city_of_and_city_suffix():
    city = SimpleNamespace(
        psgc_code="1430300000",
        name="City of Baguio",
        geographic_level="municipality",
        parent_psgc_code="1400000000",
    )
    result = MagicMock()
    result.first.return_value = SimpleNamespace(id="release")
    units = MagicMock()
    units.all.return_value = [city]
    session = SimpleNamespace(scalars=MagicMock(side_effect=[result, units]))

    resolver = fill._CityResolver(session)
    assert resolver.resolve_fields("Baguio City") == "1430300"
    assert resolver.resolve_fields("City of Baguio") == "1430300"
    assert resolver.resolve_address("PUROK 5, LOAKAN ROAD, BAGUIO CITY") == "1430300"


def test_target_city_uses_structured_source_municipality():
    _facility, location = _facility_and_location(psgc=None)
    location.address_text = None

    class Resolver:
        def resolve_fields(self, city, province):
            return "1430300" if city == "BAGUIO CITY" else None

    prefix, evidence = fill._resolve_target_city(
        location, [{"municipality": "BAGUIO CITY"}], Resolver()
    )
    assert prefix == "1430300"
    assert "BAGUIO CITY" in evidence


def test_target_city_uses_exact_address_city_name():
    _facility, location = _facility_and_location(psgc=None)
    location.address_text = "PUROK 5, LOAKAN ROAD, SCOUT BARRIO, BAGUIO CITY"

    class Resolver:
        def resolve_address(self, text, province=None):
            return "1430300" if "BAGUIO CITY" in text else None

    prefix, evidence = fill._resolve_target_city(location, [], Resolver())
    assert prefix == "1430300"
    assert "address" in evidence


def test_report_is_written_and_contains_no_fabricated_point(monkeypatch, tmp_path):
    facility, location = _facility_and_location()
    monkeypatch.setattr(fill, "_CityResolver", lambda session: object())
    monkeypatch.setattr(fill, "_osm_candidates", lambda session, resolver: [_candidate()])
    monkeypatch.setattr(fill, "_target_facilities", lambda session: [(facility, location)])
    monkeypatch.setattr(fill, "_already_filled", lambda session, ids: set())

    report = tmp_path / "osm-location-fills.json"
    result = fill.fill_locations_from_osm(session=None, apply=False, report_path=report)
    assert result.matched == 1
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "openstreetmap_match" in text
    assert "map_geocoded" in text


@pytest.mark.integration
def test_city_resolver_never_uses_synthetic_geography(db_session):
    from datetime import UTC, datetime, timedelta

    from philfacilities_api.models import AdministrativeUnit, GeographicRelease
    from sqlalchemy import delete

    token = uuid.uuid4().hex[:8]
    synthetic = GeographicRelease(
        release_label=f"SYNTHETIC-LOCATION-FILL-{token}",
        retrieved_at=datetime.now(UTC),
        is_synthetic=True,
    )
    real = GeographicRelease(
        release_label=f"REAL-LOCATION-FILL-{token}",
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
        is_synthetic=False,
    )
    db_session.add_all([synthetic, real])
    db_session.flush()
    db_session.add_all(
        [
            AdministrativeUnit(
                release_id=synthetic.id,
                psgc_code="9912302000",
                name="Synthetic Only City",
                geographic_level="city",
            ),
            AdministrativeUnit(
                release_id=real.id,
                psgc_code="9912301000",
                name="Real Only City",
                geographic_level="city",
            ),
        ]
    )
    db_session.flush()
    try:
        resolver = fill._CityResolver(db_session)
        assert resolver.resolve_fields("Synthetic Only City") is None
        assert resolver.resolve_fields("Real Only City") == "9912301"
    finally:
        db_session.execute(
            delete(AdministrativeUnit).where(
                AdministrativeUnit.release_id.in_([synthetic.id, real.id])
            )
        )
        db_session.execute(
            delete(GeographicRelease).where(GeographicRelease.id.in_([synthetic.id, real.id]))
        )
        db_session.commit()
