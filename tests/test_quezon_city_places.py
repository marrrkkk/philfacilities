"""Tests for the Quezon City Places to Visit park and market adapter."""

from __future__ import annotations

import json

from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.quezon_city_places import (
    QuezonCityPlacesAdapter,
    classify_place,
    parse_place_page,
    parse_places_search,
)


def _place_page(
    name: str,
    address: str,
    *,
    map_url: str | None = None,
    fee: str = "Free",
    hours: str = "Monday to Sunday 8:00 a.m. - 5:00 p.m.",
) -> str:
    link = f'<a href="{map_url}">{address}</a>' if map_url else address
    return f"""
    <html><head><title>{name} - Quezon City Government</title></head>
    <body>
      <h1>{name}</h1>
      <p>{link}</p>
      <p>Operating Hours: {hours}</p>
      <p>Admission Fee: {fee}</p>
      <p>Last updated on November 28th, 2024</p>
      <p>Contact Number: 0000-0000 | person@example.com</p>
    </body></html>
    """


def _spec(payload: dict) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="quezon-city",
        agency_name="Quezon City Government",
        dataset_slug="quezon-city-lgu-places",
        dataset_name="Quezon City places",
        release_label="QC-PLACES-TEST",
        filename="qc-places.json",
        content=json.dumps(payload).encode(),
    )


def _record(**overrides):
    record = {
        "record_type": "place",
        "name": "Kamuning Market",
        "address": "19 Park Ave, Cubao, Quezon City, Philippines",
        "operating_hours": "Monday to Sunday 8:00 a.m. - 8:00 p.m.",
        "admission_fee": "Free",
        "last_updated": "November 28th, 2024",
        "map_url": None,
        "latitude": None,
        "longitude": None,
        "source_url": "https://quezoncity.gov.ph/place/kamuning-market/",
        "slug": "kamuning-market",
        "sha256": "a" * 64,
        "fetched_at": "2026-11-16T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def test_parse_places_search_keeps_unique_public_places() -> None:
    payload = [
        {
            "id": 1,
            "title": "Kamuning Market",
            "url": "https://quezoncity.gov.ph/place/kamuning-market/",
            "subtype": "places",
        },
        {
            "id": 1,
            "title": "Kamuning Market",
            "url": "https://quezoncity.gov.ph/place/kamuning-market/",
            "subtype": "places",
        },
        {
            "id": 2,
            "title": "A news post",
            "url": "https://quezoncity.gov.ph/a-news-post/",
            "subtype": "post",
        },
        {
            "id": 3,
            "title": "Elsewhere",
            "url": "https://example.com/place/elsewhere/",
            "subtype": "places",
        },
    ]
    assert parse_places_search(payload) == [
        {
            "source_key": "1",
            "title": "Kamuning Market",
            "url": "https://quezoncity.gov.ph/place/kamuning-market/",
        }
    ]


def test_parse_place_page_extracts_institutional_fields_and_coordinates() -> None:
    record = parse_place_page(
        _place_page(
            "Quezon Memorial Circle",
            "Elliptical Road, Brgy. Central, Diliman, Quezon City",
            map_url=(
                "https://www.google.com/maps/search/Elliptical+Road/@14.6500873,121.0365867,15z"
            ),
        ),
        "https://quezoncity.gov.ph/place/quezon-memorial-circle/",
    )
    assert record["name"] == "Quezon Memorial Circle"
    assert record["address"].startswith("Elliptical Road")
    assert record["operating_hours"].startswith("Monday to Sunday")
    assert record["admission_fee"] == "Free"
    assert record["last_updated"] == "November 28th, 2024"
    assert record["latitude"] == 14.6500873
    assert record["longitude"] == 121.0365867


def test_parse_place_page_uses_plain_text_address_when_no_map_link_exists() -> None:
    record = parse_place_page(
        _place_page("Kamuning Market", "19 Park Ave, Cubao, Quezon City, Philippines"),
        "https://quezoncity.gov.ph/place/kamuning-market/",
    )
    assert record["address"] == "19 Park Ave, Cubao, Quezon City, Philippines"
    assert record["latitude"] is None
    assert record["longitude"] is None


def test_classify_place_includes_market_and_parks_but_not_libraries_or_churches() -> None:
    market = classify_place({"name": "Kamuning Market"})
    assert market is not None
    assert market["category"] == "public_market"
    assert market["inclusion_class"] == "PUBLIC_ACCESS_VENUE"

    city_park = classify_place({"name": "Quezon Memorial Circle"})
    assert city_park is not None
    assert city_park["inclusion_class"] == "GOVERNMENT_FACILITY"
    assert city_park["ownership_type"] == "LOCAL_GOVERNMENT"

    joint_park = classify_place({"name": "La Mesa Eco Park"})
    assert joint_park is not None
    assert joint_park["ownership_type"] == "PUBLIC_PRIVATE_JOINT"

    assert classify_place({"name": "Quezon City Public Library - Main"}) is None
    assert classify_place({"name": "Sto. Domingo Church"}) is None


def test_adapter_publishes_only_the_market_and_park_subset() -> None:
    payload = {
        "place_count": 4,
        "places": [
            _record(),
            _record(
                name="Quezon Memorial Circle",
                address="Elliptical Road, Diliman, Quezon City",
                admission_fee="Free",
                map_url="https://www.google.com/maps/place/Quezon+Memorial+Circle/@14.65,121.03",
                latitude=14.65,
                longitude=121.03,
                source_url="https://quezoncity.gov.ph/place/quezon-memorial-circle/",
                slug="quezon-memorial-circle",
            ),
            _record(
                name="Quezon City Public Library - Main",
                source_url="https://quezoncity.gov.ph/place/quezon-city-public-library-main/",
                slug="quezon-city-public-library-main",
            ),
            _record(
                name="Sto. Domingo Church",
                source_url="https://quezoncity.gov.ph/place/sto-domingo-church/",
                slug="sto-domingo-church",
            ),
        ],
    }
    spec = _spec(payload)
    adapter = QuezonCityPlacesAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 4
    assert sum(1 for row in parsed.rows if row.normalized_payload["included"]) == 2
    assert any(
        warning["code"] == "libraries_already_published_from_nlp" for warning in parsed.warnings
    )

    result = adapter.validate(parsed)
    assert result.rejected_rows == 0
    assert result.accepted_rows == 4

    candidates = adapter.normalize(parsed)
    assert [candidate.display_name for candidate in candidates] == [
        "Kamuning Market",
        "Quezon Memorial Circle",
    ]
    market, park = candidates
    assert market.facility_type == "public_market"
    assert market.inclusion_class == "PUBLIC_ACCESS_VENUE"
    assert market.public_access_class == "PUBLIC_FREE"
    assert market.ownership_type == "UNKNOWN"
    assert park.facility_type == "public_space"
    assert park.facility_subtype == "PUBLIC_PARK"
    assert park.inclusion_class == "GOVERNMENT_FACILITY"
    assert park.ownership_type == "LOCAL_GOVERNMENT"
    assert park.location.precision == "map_geocoded"
    assert park.location.latitude == 14.65


def test_adapter_rejects_an_included_place_without_an_address() -> None:
    spec = _spec({"place_count": 1, "places": [_record(address="")]})
    adapter = QuezonCityPlacesAdapter(spec)
    parsed = adapter.parse(spec)
    result = adapter.validate(parsed)
    assert result.rejected_rows == 1
    assert any(issue.code == "missing_address" for issue in result.issues)


def test_adapter_bounds_long_source_keys_without_collisions() -> None:
    long_slug = "a" * 180
    payload = {
        "place_count": 2,
        "places": [
            _record(
                name="Kamuning Market",
                source_url=f"https://quezoncity.gov.ph/place/{long_slug}/",
                slug=long_slug,
            ),
            _record(
                name="Quezon Memorial Circle",
                address="Elliptical Road, Diliman, Quezon City",
                source_url=f"https://quezoncity.gov.ph/place/{long_slug}-2/",
                slug=f"{long_slug}-2",
            ),
        ],
    }
    spec = _spec(payload)
    parsed = QuezonCityPlacesAdapter(spec).parse(spec)
    assert all(len(row.source_record_key) <= 200 for row in parsed.rows)
    assert all(len(row.row_reference) <= 80 for row in parsed.rows)
    assert len({row.source_record_key for row in parsed.rows}) == 2
    assert len({row.row_reference for row in parsed.rows}) == 2
