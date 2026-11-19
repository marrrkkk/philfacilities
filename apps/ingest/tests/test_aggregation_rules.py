"""Pure aggregation rules that do not need a database."""

from __future__ import annotations

from types import SimpleNamespace

from philfacilities_ingest.aggregation import (
    _conflicting_location,
    _same_agency_duplicate,
)


def _ref(address: str, *, agencies: set[str] | None = None, specific: bool = True):
    return SimpleNamespace(
        agency_codes=agencies or {"osm"},
        specific=specific,
        generic=not specific,
        location=SimpleNamespace(address_text=address),
    )


def _is_duplicate(left, right, *, name_score=1.0, distance=None) -> bool:
    return _same_agency_duplicate(
        left,
        right,
        name_score=name_score,
        distance=distance,
        conflicting_ids=False,
        conflicting_location=False,
    )


def test_same_agency_duplicate_needs_a_shared_point() -> None:
    left = _ref("City Hall Drive, Baguio")
    assert _is_duplicate(left, _ref("City Hall Drive, Baguio"), distance=12.0)
    # Same name and exact same free-text address are not enough without a point.
    assert not _is_duplicate(left, _ref("City Hall Drive, Baguio"))
    # Same city and same name are not enough for two branches.
    assert not _is_duplicate(left, _ref("Session Road, Baguio"))
    assert not _is_duplicate(left, _ref("Other Road, Baguio"), distance=120.0)


def test_same_agency_duplicate_requires_exact_name_and_specific_place() -> None:
    left = _ref("City Hall Drive, Baguio")
    assert not _is_duplicate(left, _ref("City Hall Drive, Baguio"), name_score=0.95)
    assert not _is_duplicate(
        _ref("Barangay Hall", specific=False),
        _ref("Barangay Hall", specific=False),
    )
    assert not _is_duplicate(left, _ref("City Hall Drive, Baguio", agencies={"doh"}))


def test_conflicting_ids_or_locations_block_same_agency_merge() -> None:
    left = _ref("City Hall Drive, Baguio")
    right = _ref("City Hall Drive, Baguio")
    assert not _same_agency_duplicate(
        left,
        right,
        name_score=1.0,
        distance=None,
        conflicting_ids=True,
        conflicting_location=False,
    )
    assert not _same_agency_duplicate(
        left,
        right,
        name_score=1.0,
        distance=None,
        conflicting_ids=False,
        conflicting_location=True,
    )


def _placed(
    barangay: str,
    precision: str,
    *,
    specific: bool = True,
):
    return SimpleNamespace(
        barangay_code=barangay,
        specific=specific,
        generic=not specific,
        location=SimpleNamespace(address_text="", precision=precision),
    )


def _conflicts(left, right, distance=2.0, *, name_score=1.0) -> bool:
    return _conflicting_location(
        left,
        right,
        distance,
        same_barangay=False,
        name_score=name_score,
    )


def test_map_boundary_noise_does_not_block_an_exact_official_match() -> None:
    osm = _placed("0603030034", "map_geocoded")
    official = _placed("0603030002", "source_gps")
    assert not _conflicts(osm, official)


def test_distinct_barangays_still_conflict_without_map_derived_points() -> None:
    assert _conflicts(_placed("0603030034", "source_gps"), _placed("0603030002", "source_gps"))
    assert _conflicts(_placed("0603030034", "map_geocoded"), _placed("0603030002", "unknown"))


def test_two_map_derived_points_close_together_are_boundary_noise() -> None:
    assert not _conflicts(
        _placed("0603030034", "map_geocoded"),
        _placed("0603030002", "map_geocoded"),
    )
    assert not _conflicts(
        _placed("0603030034", "barangay_centroid"),
        _placed("0603030002", "source_gps"),
    )


def test_boundary_exception_needs_exact_specific_names_and_a_close_point() -> None:
    osm = _placed("0603030034", "map_geocoded")
    official = _placed("0603030002", "source_gps")
    assert _conflicts(osm, official, name_score=0.95)
    assert _conflicts(osm, official, distance=51.0)
    assert _conflicts(
        _placed("0603030034", "map_geocoded", specific=False),
        _placed("0603030002", "source_gps", specific=False),
    )


def test_shared_barangay_keeps_outranking_a_map_address() -> None:
    left = _placed("0603030002", "map_geocoded")
    right = _placed("0603030002", "source_gps")
    assert not _conflicting_location(
        left,
        right,
        12.0,
        same_barangay=True,
        name_score=1.0,
    )
