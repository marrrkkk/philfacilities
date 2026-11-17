"""Tests for the Quezon City LGU directory adapter."""

from __future__ import annotations

import json

from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.quezon_city import (
    QuezonCityLguAdapter,
    parse_barangay_page,
    parse_health_center_page,
    parse_sitemap_urls,
)


def _health_page() -> str:
    return """
    <html><body>
    <main class="health_center_category-brgy-health-centers">
      <article>
        <h4 class="healthcenter-title text-blue">North Fairview HC</h4>
        <ul class="nostyle">
          <li><i class="dashicons dashicons-location"></i>
            Avon Street, North Fairview Park Subd., Brgy. North Fairview, District 5</li>
          <li><i class="dashicons dashicons-phone"></i> 7003-7839</li>
        </ul>
      </article>
    </main>
    </body></html>
    """


def _barangay_page(map_place: str = "North+Fairview+Barangay+Hall") -> str:
    return f"""
    <html><body>
    <h2>North Fairview</h2>
    <p class="wp-block-paragraph">
      <strong>Address</strong>: <br>
      <a href="https://www.google.com/maps/place/{map_place}/@14.7224742,121.060273,17z/data=!3d14.722469!4d121.0628479">
        Brookside Street cor. Brimley Street, Fairville Homes, Barangay North Fairview,
        District 5, Quezon City
      </a>
    </p>
    <p><strong>Punong Barangay:</strong> A Person</p>
    </body></html>
    """


def _spec(payload: dict) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="quezon-city",
        agency_name="Quezon City Government",
        dataset_slug="quezon-city-lgu-directory",
        dataset_name="Quezon City directories",
        release_label="QC-TEST",
        filename="qc.json",
        content=json.dumps(payload).encode(),
    )


def _record(**overrides):
    record = {
        "record_type": "health_center",
        "name": "North Fairview HC",
        "address": "Avon Street, Brgy. North Fairview, District 5",
        "phone": "7003-7839",
        "category": "brgy-health-centers",
        "district": "District 5",
        "source_url": "https://quezoncity.gov.ph/health_centers/north-fairview-hc/",
        "slug": "north-fairview-hc",
        "sha256": "a" * 64,
        "fetched_at": "2026-11-16T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def _barangay_record(**overrides):
    record = {
        "record_type": "barangay",
        "name": "North Fairview",
        "address": "Brookside Street, Barangay North Fairview, District 5",
        "map_url": "https://www.google.com/maps/place/North+Fairview+Barangay+Hall/",
        "map_place": "North Fairview Barangay Hall",
        "latitude": 14.722469,
        "longitude": 121.0628479,
        "hall_evidence": True,
        "district": "District 5",
        "source_url": "https://quezoncity.gov.ph/brgy-directory/north-fairview/",
        "slug": "north-fairview",
        "sha256": "b" * 64,
        "fetched_at": "2026-11-16T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def test_parse_sitemap_urls_keeps_only_same_directory() -> None:
    document = """
    <urlset>
      <url><loc>https://quezoncity.gov.ph/health_centers/north-fairview-hc/</loc></url>
      <url><loc>https://quezoncity.gov.ph/health_centers/north-fairview-hc/</loc></url>
      <url><loc>https://example.com/health_centers/other/</loc></url>
      <url><loc>https://quezoncity.gov.ph/health_centers/ngc-lying-in-clinic-2/</loc></url>
    </urlset>
    """
    assert parse_sitemap_urls(document, prefix="https://quezoncity.gov.ph/health_centers/") == [
        "https://quezoncity.gov.ph/health_centers/north-fairview-hc/",
        "https://quezoncity.gov.ph/health_centers/ngc-lying-in-clinic-2/",
    ]


def test_parse_health_center_page_extracts_institutional_fields() -> None:
    record = parse_health_center_page(
        _health_page(), "https://quezoncity.gov.ph/health_centers/north-fairview-hc/"
    )
    assert record["name"] == "North Fairview HC"
    assert record["address"].startswith("Avon Street")
    assert record["district"] == "District 5"
    assert record["category"] == "brgy-health-centers"
    assert record["phone"] == "7003-7839"
    assert record["slug"] == "north-fairview-hc"


def test_parse_barangay_page_requires_explicit_hall_evidence() -> None:
    record = parse_barangay_page(
        _barangay_page(), "https://quezoncity.gov.ph/brgy-directory/north-fairview/"
    )
    assert record["name"] == "North Fairview"
    assert record["address"].startswith("Brookside Street")
    assert record["map_place"] == "North Fairview Barangay Hall"
    assert record["hall_evidence"] is True
    assert record["latitude"] == 14.722469
    assert record["longitude"] == 121.0628479

    without_hall = parse_barangay_page(
        _barangay_page("North+Fairview"), "https://quezoncity.gov.ph/brgy-directory/x/"
    )
    assert without_hall["hall_evidence"] is False

    without_link = parse_barangay_page(
        "<h2>Amihan</h2><p><strong>Address</strong>: 13 Palosapis St.</p>",
        "https://quezoncity.gov.ph/brgy-directory/amihan/",
    )
    assert without_link["hall_evidence"] is False
    assert without_link["map_place"] is None


def test_adapter_publishes_only_eligible_rows_and_withholds_contacts() -> None:
    payload = {
        "health_center_pages": 3,
        "barangay_pages": 2,
        "health_centers": [
            _record(),
            _record(
                name="District 1 Health Office",
                slug="district-1-health-office",
                source_url="https://quezoncity.gov.ph/health_centers/district-1-health-office/",
            ),
            _record(
                name="Amoranto Stadium",
                category="swab-testing-center",
                address="",
                slug="amoranto-stadium",
                source_url="https://quezoncity.gov.ph/health_centers/amoranto-stadium/",
            ),
        ],
        "barangays": [
            _barangay_record(),
            _barangay_record(
                name="Amihan",
                address="13 Palosapis St.",
                map_place=None,
                map_url=None,
                latitude=None,
                longitude=None,
                hall_evidence=False,
                slug="amihan",
                source_url="https://quezoncity.gov.ph/brgy-directory/amihan/",
            ),
        ],
    }
    spec = _spec(payload)
    adapter = QuezonCityLguAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 5
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0
    candidates = adapter.normalize(parsed)
    assert len(candidates) == 2
    health, hall = candidates
    assert health.facility_subtype == "BARANGAY_HEALTH_STATION"
    assert health.ownership_type == "LOCAL_GOVERNMENT"
    assert health.inclusion_class == "GOVERNMENT_FACILITY"
    assert "phone" not in parsed.rows[0].normalized_payload
    assert parsed.rows[0].raw_payload["phone"] == "7003-7839"
    assert hall.facility_subtype == "BARANGAY_HALL"
    assert hall.location.precision == "map_geocoded"
    assert hall.location.latitude == 14.722469
    assert hall.display_name == "North Fairview Barangay Hall"


def test_adapter_rejects_included_rows_without_address() -> None:
    payload = {
        "health_centers": [_record(address="")],
        "barangays": [],
    }
    spec = _spec(payload)
    adapter = QuezonCityLguAdapter(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 1
    assert any(issue.code == "missing_address" for issue in validation.issues)


def test_adapter_rejects_out_of_bounds_coordinates() -> None:
    payload = {
        "health_centers": [],
        "barangays": [_barangay_record(latitude=51.5, longitude=-0.1)],
    }
    spec = _spec(payload)
    adapter = QuezonCityLguAdapter(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    assert any(issue.code == "coordinate_outside_philippines" for issue in validation.issues)
