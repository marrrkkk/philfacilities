"""Spatial PSGC resolution from OSM administrative boundaries."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import philfacilities_ingest.psgc_spatial_fill as spatial
from shapely.geometry import box


def _unit(
    code: str,
    name: str,
    level: str,
    parent: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        psgc_code=code,
        name=name,
        geographic_level=level,
        parent_psgc_code=parent,
        correspondence_code=None,
    )


UNITS = [
    _unit("0100000000", "Region", "region"),
    _unit("0100100000", "Province", "province", "0100000000"),
    _unit("0100101000", "Municipality", "municipality", "0100100000"),
    _unit("0100101001", "Barangay One", "barangay", "0100101000"),
    _unit("0100101002", "Barangay Two", "barangay", "0100101000"),
    _unit("0100102000", "Other Municipality", "municipality", "0100100000"),
]
GEOGRAPHY = spatial.GeographyIndex(UNITS)


def _feature(
    code: str,
    admin_level: int,
    geometry,
    level: str,
    parent: str | None = None,
) -> spatial.BoundaryFeature:
    return spatial.BoundaryFeature(
        psgc_code=code,
        admin_level=admin_level,
        geographic_level=level,
        parent_psgc_code=parent,
        geom=geometry,
    )


FEATURES = [
    _feature("0100000000", 3, box(0, 0, 10, 10), "region"),
    _feature("0100100000", 4, box(0, 0, 5, 5), "province", "0100000000"),
    _feature("0100101000", 6, box(0, 0, 4, 4), "municipality", "0100100000"),
    _feature("0100101001", 10, box(0, 0, 2, 2), "barangay", "0100101000"),
    _feature("0100101002", 10, box(2, 2, 4, 4), "barangay", "0100101000"),
]
INDEX = spatial.BoundaryIndex(FEATURES, GEOGRAPHY)


def test_deepest_containing_boundary_wins():
    lookup = INDEX.lookup(1, 1)
    assert lookup.outcome == "resolved"
    assert lookup.psgc_code == "0100101001"
    assert lookup.admin_level == 10


def test_a_point_outside_every_boundary_stays_unknown():
    lookup = INDEX.lookup(20, 20)
    assert lookup.outcome == spatial.NO_BOUNDARY
    decision = spatial.classify(None, lookup, GEOGRAPHY)
    assert decision.outcome == spatial.NO_BOUNDARY
    assert decision.psgc_code is None


def test_null_code_is_filled_from_map_containment():
    decision = spatial.classify(None, INDEX.lookup(1, 1), GEOGRAPHY)
    assert decision.outcome == spatial.FILL
    assert decision.psgc_code == "0100101001"
    assert decision.method == "osm_boundary_containment"


def test_more_specific_map_code_only_refines_when_enabled():
    lookup = INDEX.lookup(1, 1)
    planned = spatial.classify("0100101000", lookup, GEOGRAPHY)
    applied = spatial.classify("0100101000", lookup, GEOGRAPHY, refine=True)
    assert planned.outcome == spatial.REFINE_AVAILABLE
    assert planned.psgc_code == "0100101001"
    assert applied.outcome == spatial.REFINE
    assert applied.method == "osm_boundary_refinement"


def test_existing_code_is_only_replaced_by_a_more_specific_map_unit():
    lookup = INDEX.lookup(1, 1)
    assert spatial.classify("0100101000", lookup, GEOGRAPHY, refine=True).outcome == spatial.REFINE
    assert (
        spatial.classify("0100101002", lookup, GEOGRAPHY, refine=True).outcome == spatial.CONFLICT
    )
    assert (
        spatial.classify("0100102000", lookup, GEOGRAPHY, refine=True).outcome == spatial.CONFLICT
    )

    coarser = spatial.classify(
        "0100101001",
        INDEX.lookup(4.5, 4.5),
        GEOGRAPHY,
        refine=True,
    )
    assert coarser.outcome == spatial.CURRENT_MORE_SPECIFIC


def test_prefer_map_overrides_same_level_and_different_branch_codes():
    lookup = INDEX.lookup(1, 1)
    same_level = spatial.classify("0100101002", lookup, GEOGRAPHY, prefer_map=True)
    different_branch = spatial.classify("0100102000", lookup, GEOGRAPHY, prefer_map=True)
    for decision in (same_level, different_branch):
        assert decision.outcome == spatial.OVERRIDE
        assert decision.psgc_code == "0100101001"
        assert decision.method == "osm_boundary_override"


def test_prefer_map_refines_and_never_downgrades_a_more_specific_source_code():
    assert (
        spatial.classify("0100101000", INDEX.lookup(1, 1), GEOGRAPHY, prefer_map=True).outcome
        == spatial.REFINE
    )
    coarser = spatial.classify("0100101001", INDEX.lookup(4.5, 4.5), GEOGRAPHY, prefer_map=True)
    assert coarser.outcome == spatial.CURRENT_MORE_SPECIFIC


def test_prefer_map_leaves_undeterminable_map_outcomes_unknown():
    outside = spatial.classify(None, INDEX.lookup(20, 20), GEOGRAPHY, prefer_map=True)
    assert outside.outcome == spatial.NO_BOUNDARY
    assert outside.psgc_code is None

    features = [
        _feature("0100101001", 10, box(0, 0, 2, 2), "barangay", "0100101000"),
        _feature("0100101002", 10, box(0, 0, 2, 2), "barangay", "0100101000"),
    ]
    overlapping = spatial.BoundaryIndex(features, GEOGRAPHY).lookup(1, 1)
    assert overlapping.outcome == spatial.POLYGON_CONFLICT
    assert spatial.classify(None, overlapping, GEOGRAPHY, prefer_map=True).psgc_code is None


def test_overlapping_boundaries_with_different_codes_are_a_polygon_conflict():
    features = [
        _feature("0100101001", 10, box(0, 0, 2, 2), "barangay", "0100101000"),
        _feature("0100101002", 10, box(0, 0, 2, 2), "barangay", "0100101000"),
    ]
    lookup = spatial.BoundaryIndex(features, GEOGRAPHY).lookup(1, 1)
    assert lookup.outcome == spatial.POLYGON_CONFLICT
    assert lookup.psgc_code is None


def test_a_containing_boundary_outside_the_hierarchy_is_inconsistent():
    features = [
        _feature("0100102000", 6, box(0, 0, 4, 4), "municipality", "0100100000"),
        _feature("0100101001", 10, box(0, 0, 2, 2), "barangay", "0100101000"),
    ]
    lookup = spatial.BoundaryIndex(features, GEOGRAPHY).lookup(1, 1)
    assert lookup.outcome == spatial.INCONSISTENT


def test_map_fill_writes_a_derived_source_linked_assertion():
    facility_id = uuid.uuid4()
    record_id = uuid.uuid4()
    location = SimpleNamespace(
        facility_id=facility_id,
        source_record_id=record_id,
        psgc_code=None,
        latitude=Decimal("1.0"),
        longitude=Decimal("1.0"),
    )
    session = SimpleNamespace(added=[])
    session.add = session.added.append
    decision = spatial.classify(None, INDEX.lookup(1, 1), GEOGRAPHY)

    assert spatial._apply_decision(session, location, decision, set()) is True
    assert location.psgc_code == "0100101001"
    assertion = session.added[0]
    assert assertion.facility_id == facility_id
    assert assertion.source_record_id == record_id
    assert assertion.attribute_name == "psgc_code"
    assert assertion.source_field == "geom"
    assert assertion.normalized_value == "0100101001"
    assert assertion.transformation_version == "psgc-spatial-v1"
    assert assertion.review_status == "derived"


def test_map_fill_requires_a_source_record_for_the_assertion():
    location = SimpleNamespace(
        facility_id=uuid.uuid4(),
        source_record_id=None,
        psgc_code=None,
        latitude=Decimal("1.0"),
        longitude=Decimal("1.0"),
    )
    session = SimpleNamespace(added=[])
    session.add = session.added.append
    decision = spatial.classify(None, INDEX.lookup(1, 1), GEOGRAPHY)

    assert spatial._apply_decision(session, location, decision, set()) is False
    assert location.psgc_code is None
    assert session.added == []
