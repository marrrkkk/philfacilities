"""Pure aggregation rules that do not need a database."""

from __future__ import annotations

from types import SimpleNamespace

from philfacilities_ingest.aggregation import (
    _conflicting_location,
    _same_agency_duplicate,
)


def _ref(
    address: str,
    *,
    agencies: set[str] | None = None,
    specific: bool = True,
    barangay_code: str | None = None,
):
    return SimpleNamespace(
        agency_codes=agencies or {"osm"},
        specific=specific,
        generic=not specific,
        barangay_code=barangay_code,
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


def _conflicts(
    left,
    right,
    distance=2.0,
    *,
    name_score=1.0,
    administrative_names: set[str] | None = None,
) -> bool:
    return _conflicting_location(
        left,
        right,
        distance,
        same_barangay=False,
        name_score=name_score,
        administrative_names=administrative_names,
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


def test_street_address_against_locality_text_is_not_a_conflict() -> None:
    # One source names the street while the other records only an
    # administrative description of the same site. The locality is less
    # precise, not a competing address.
    osm = _ref("Florentino Cayco Street")
    official = _ref(
        "BARANGAY 457, CITY OF MANILA, NCR, FIRST DISTRICT "
        "(Not a Province), NATIONAL CAPITAL REGION (NCR)"
    )
    assert not _conflicts(osm, official, distance=8.0)
    assert not _conflicts(
        _ref("Diversion Road, Brgy. Gulang-gulang, Lucena City"),
        _ref("Lucena City, Quezon"),
    )


def test_two_distinct_street_addresses_still_conflict() -> None:
    assert _conflicts(
        _ref("123 Rizal Street, Lucena City"),
        _ref("456 Mabini Street, Lucena City"),
        distance=120.0,
        administrative_names={"lucena", "city"},
    )


def test_name_variant_key_ignores_connector_order_only() -> None:
    from philfacilities_ingest.aggregation import _name_variant_key

    assert _name_variant_key("perpetual succor maternity hospital") == _name_variant_key(
        "perpetual succor hospital and maternity"
    )
    assert _name_variant_key("rural health unit") != _name_variant_key(
        "rural health unit birthing facility"
    )


def test_near_points_share_a_bucket_across_different_city_codes() -> None:
    from philfacilities_ingest.aggregation import _bucket_keys

    def facility(city_code: str, latitude: float, longitude: float):
        return SimpleNamespace(
            city_code=city_code,
            location=SimpleNamespace(latitude=latitude, longitude=longitude),
        )

    # OSM placed this school in Talisay and DepEd placed it in Silay, but the
    # points are nine metres apart. A city-only bucket would never compare them.
    osm = facility("1804528", 10.730906, 123.086718)
    deped = facility("1804526", 10.730879, 123.086797)
    assert _bucket_keys(osm) & _bucket_keys(deped)

    far = facility("0431200000", 14.599512, 120.984222)
    assert not _bucket_keys(osm) & _bucket_keys(far)
