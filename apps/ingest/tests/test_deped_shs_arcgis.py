"""Parser and normalization tests for the DepEd SHS ArcGIS points."""

from __future__ import annotations

import json

from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.deped_shs_arcgis import (
    DepEdShsArcgisAdapter,
    _address_text,
)


def _spec(content: bytes) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-shs-arcgis",
        dataset_name="DepEd Senior High Schools (CHED GIS layer)",
        release_label="DEPED-SHS-ARCGIS-TEST",
        filename="deped-shs-arcgis.json",
        content=content,
    )


def _artifact(rows: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "layer_url": "https://example.test/FeatureServer/2",
            "feature_count": len(rows),
            "features": [{"attributes": row} for row in rows],
        }
    ).encode("utf-8")


def _row(**overrides: object) -> dict[str, object]:
    row = {
        "OBJECTID": 1,
        "Region": "Region XI",
        "Division": "Davao City",
        "District": "Paquibato",
        "BEIS_School_ID": 304341,
        "School_Name": "A. L. Navarro National High School",
        "Street_Address": "Purok Sagittarius. Lasang",
        "Mother_School_ID": None,
        "Province": "DAVAO DEL SUR",
        "Municipality": "DAVAO CITY",
        "Legislative_District": "2nd District",
        "Barangay": "ALEJANDRA NAVARRO (LASANG)",
        "Sector": "Public",
        "School_Subclassification": "DepED Managed",
        "School_Type": "Mother school",
        "IU_NON_IU": "IU",
        "Modified_COC": "JHS with SHS",
        "x": 125.665567,
        "y": 7.265302,
        "Remarks": "Based on OSMAPAARALAN",
    }
    row.update(overrides)
    return row


def test_parse_and_normalize_shs_point() -> None:
    adapter = DepEdShsArcgisAdapter(_spec(b"unused"))
    parsed = adapter.parse(_spec(_artifact([_row()])))
    validation = adapter.validate(parsed)
    assert validation.accepted_rows == 1
    assert validation.rejected_rows == 0
    assert not validation.failed

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_entity_id == "304341"
    assert candidate.enrichment_only is True
    assert candidate.facility_type == "school"
    assert candidate.ownership == "government"
    assert candidate.inclusion_class == "GOVERNMENT_FACILITY"
    assert candidate.school is not None
    assert candidate.school.deped_school_id == "304341"
    assert candidate.school.sector == "public"
    assert candidate.school.school_management == "deped_managed"
    assert candidate.school.offers_shs is True
    assert candidate.school.offering_classification == "JHS with SHS"
    assert candidate.school.division == "Davao City"
    assert candidate.school.district == "Paquibato"
    assert candidate.school.legislative_district == "2nd District"
    assert candidate.location.latitude == 7.265302
    assert candidate.location.longitude == 125.665567
    assert candidate.location.precision == "map_geocoded"
    assert candidate.location.psgc_code is None
    assert candidate.location.address_text == (
        "Purok Sagittarius. Lasang, ALEJANDRA NAVARRO (LASANG), DAVAO CITY, DAVAO DEL SUR"
    )


def test_duplicate_and_invalid_ids_are_rejected_without_losing_valid_rows() -> None:
    rows = [
        _row(),
        _row(OBJECTID=2, BEIS_School_ID=304341),
        _row(OBJECTID=3, BEIS_School_ID=12345),
        _row(OBJECTID=4, BEIS_School_ID=304342, School_Name=None),
        _row(
            OBJECTID=5,
            BEIS_School_ID=304343,
            x=None,
            y=None,
            School_Name="No Point High School",
        ),
    ]
    adapter = DepEdShsArcgisAdapter(_spec(b"unused"))
    parsed = adapter.parse(_spec(_artifact(rows)))
    validation = adapter.validate(parsed)
    assert validation.accepted_rows == 2
    assert validation.rejected_rows == 3
    assert not validation.failed
    codes = {issue.code for issue in validation.issues}
    assert "invalid_shs_row" in codes
    assert "missing_or_outside_point" in codes
    candidates = adapter.normalize(parsed)
    no_point = next(c for c in candidates if c.source_entity_id == "304343")
    assert no_point.location.latitude is None
    assert no_point.location.longitude is None
    assert no_point.location.precision == "unknown"


def test_outside_philippines_point_is_dropped_but_institution_retained() -> None:
    adapter = DepEdShsArcgisAdapter(_spec(b"unused"))
    parsed = adapter.parse(_spec(_artifact([_row(x=0.0, y=0.0)])))
    validation = adapter.validate(parsed)
    assert validation.accepted_rows == 1
    assert any(issue.code == "missing_or_outside_point" for issue in validation.issues)
    candidate = adapter.normalize(parsed)[0]
    assert candidate.location.latitude is None
    assert candidate.location.longitude is None


def test_empty_artifact_is_rejected() -> None:
    adapter = DepEdShsArcgisAdapter(_spec(b"unused"))
    try:
        adapter.parse(_spec(json.dumps({"features": []}).encode("utf-8")))
    except ValueError as exc:
        assert "no features" in str(exc)
    else:
        raise AssertionError("an empty SHS artifact must not parse")


def test_address_text_does_not_repeat_parent_cells() -> None:
    assert (
        _address_text(
            {
                "Street_Address": "Purok 2",
                "Barangay": "Poblacion",
                "Municipality": "Davao City",
                "Province": "Davao City",
            }
        )
        == "Purok 2, Poblacion, Davao City"
    )
