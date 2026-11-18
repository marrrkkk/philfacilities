"""Deterministic PSGC resolution for locations with source evidence."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import philfacilities_ingest.psgc_fill as fill


def _unit(
    code: str,
    name: str,
    level: str,
    parent: str | None = None,
    correspondence: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        psgc_code=code,
        name=name,
        geographic_level=level,
        parent_psgc_code=parent,
        correspondence_code=correspondence,
    )


UNITS = [
    _unit("1300000000", "National Capital Region (NCR)", "region", correspondence="130000000"),
    _unit("0700000000", "Region VII (Central Visayas)", "region", correspondence="070000000"),
    _unit("0730000000", "Cebu", "province", "0700000000", "073000000"),
    _unit("1380600000", "City of Manila", "municipality", "1300000000", "133900000"),
    _unit("1380608000", "Ermita", "municipality", "1380600000", "133908000"),
    _unit(
        "1380608011",
        "Barangay 669",
        "barangay",
        "1380608000",
        "133908011",
    ),
    _unit("1380608012", "Poblacion", "barangay", "1380608000"),
    _unit("0730600000", "City of Cebu", "municipality", "0730000000", "073060000"),
    _unit("0730601013", "Poblacion", "barangay", "0730600000"),
    _unit("1800000000", "Negros Island Region (NIR)", "region", correspondence="180000000"),
    _unit("1806100000", "Siquijor", "province", "1800000000", "076100000"),
    _unit("1806103000", "Lazi", "municipality", "1806100000", "076103000"),
    _unit("1806103007", "Kimba", "barangay", "1806103000", "076103007"),
]


def test_exact_current_code_preserves_leading_zeros():
    index = fill.GeographyIndex(UNITS)
    outcome = index.resolve_payload({"brgy_psgc": "PH1380608011"})
    assert outcome.reason == "resolved"
    assert outcome.match is not None
    assert outcome.match.psgc_code == "1380608011"
    assert outcome.match.method == "source_code_exact"


def test_legacy_code_uses_the_release_correspondence_code():
    index = fill.GeographyIndex(UNITS)
    outcome = index.resolve_payload({"brgy_psgc": "PH133908011"})
    assert outcome.reason == "resolved"
    assert outcome.match is not None
    assert outcome.match.psgc_code == "1380608011"
    assert outcome.match.method == "source_code_correspondence"


def test_name_hierarchy_resolves_a_stale_osm_barangay():
    index = fill.GeographyIndex(UNITS)
    outcome = index.resolve_payload(
        {
            "adm4_name": "Barangay 669",
            "adm3_name": "City of Manila",
            "adm2_name": "Metropolitan Manila First District",
            "adm1_name": "National Capital Region (NCR)",
        }
    )
    assert outcome.reason == "resolved"
    assert outcome.match is not None
    assert outcome.match.psgc_code == "1380608011"
    assert outcome.match.method == "admin_name_hierarchy"


def test_ambiguous_barangay_name_stays_unresolved():
    index = fill.GeographyIndex(UNITS)
    outcome = index.resolve_payload({"adm4_name": "Poblacion"})
    assert outcome.reason == "ambiguous"
    assert outcome.match is None


def test_same_level_codes_disagree_is_a_conflict():
    index = fill.GeographyIndex(UNITS)
    outcome = index.resolve_payload({"brgy_psgc": "PH1380608011", "adm4_pcode": "PH1380608012"})
    assert outcome.reason == "conflict"
    assert outcome.match is None


def test_stale_region_code_does_not_invalidate_a_deeper_nir_chain():
    index = fill.GeographyIndex(UNITS)
    outcome = index.resolve_payload(
        {
            "brgy_psgc": "PH076103007",
            "muni_psgc": "PH076103000",
            "prov_psgc": "PH076100000",
            "reg_psgc": "PH070000000",
        }
    )
    assert outcome.reason == "resolved"
    assert outcome.match is not None
    assert outcome.match.psgc_code == "1806103007"
    assert outcome.match.method == "source_code_correspondence"


def test_independent_city_beats_its_geographic_province():
    index = fill.GeographyIndex(
        [
            _unit("0700000000", "Region VII (Central Visayas)", "region"),
            _unit("0702200000", "Cebu", "province", "0700000000", "072200000"),
            _unit("0731300000", "City of Mandaue", "municipality", "0700000000", "072230000"),
        ]
    )
    outcome = index.resolve_payload(
        {
            "muni_psgc": "PH072230000",
            "prov_psgc": "PH072200000",
            "reg_psgc": "PH070000000",
        }
    )
    assert outcome.reason == "resolved"
    assert outcome.match is not None
    assert outcome.match.psgc_code == "0731300000"


def test_resolution_never_overwrites_a_non_null_location_code():
    location = SimpleNamespace(facility_id=uuid.uuid4(), psgc_code="1380608011")
    match = fill.SourcedMatch(
        match=fill.PsgcMatch(
            psgc_code="1380608012",
            method="source_code_exact",
            source_field="brgy_psgc",
            raw_value="1380608012",
        ),
        source_record_id=uuid.uuid4(),
        dataset_slug="osm-education-facilities",
    )
    session = SimpleNamespace(added=[])
    session.add = session.added.append

    assert fill._apply_resolution(session, location, match, set()) is False
    assert location.psgc_code == "1380608011"
    assert session.added == []


def test_resolution_writes_a_source_linked_assertion():
    facility_id = uuid.uuid4()
    record_id = uuid.uuid4()
    location = SimpleNamespace(facility_id=facility_id, psgc_code=None)
    match = fill.SourcedMatch(
        match=fill.PsgcMatch(
            psgc_code="1380608011",
            method="source_code_correspondence",
            source_field="brgy_psgc",
            raw_value="PH133908011",
        ),
        source_record_id=record_id,
        dataset_slug="nha-doh-health-facilities",
    )
    session = SimpleNamespace(added=[])
    session.add = session.added.append

    assert fill._apply_resolution(session, location, match, set()) is True
    assert location.psgc_code == "1380608011"
    assertion = session.added[0]
    assert assertion.facility_id == facility_id
    assert assertion.source_record_id == record_id
    assert assertion.attribute_name == "psgc_code"
    assert assertion.normalized_value == "1380608011"
    assert assertion.review_status == "derived"


def test_backfill_targets_only_current_null_codes():
    class EmptyResult:
        def partitions(self, size):
            return iter(())

    class RecordingSession:
        statement = None

        def execute(self, statement):
            self.statement = statement
            return EmptyResult()

    session = RecordingSession()
    assert list(fill._target_rows(session)) == []
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "psgc_code IS NULL" in sql
    assert "is_current" in sql
