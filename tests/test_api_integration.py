"""End-to-end API tests against the deterministic synthetic demo dataset."""

from __future__ import annotations

import csv
import io
import math

import pyarrow.parquet as pq
import pytest

pytestmark = pytest.mark.integration


def _items(client, path: str, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_statistics_and_facility_inventory_agree(client):
    stats = _items(client, "/v1/statistics")
    facilities = _items(client, "/v1/facilities", limit=100)

    assert facilities["total"] == stats["published_facilities"] == 22
    assert stats["schools"] == 12
    assert stats["health_facilities"] == 10
    assert stats["synthetic"] == stats["published_facilities"]
    assert stats["facilities_total"] == stats["published_facilities"]
    assert stats["with_coordinates"] > 0
    assert set(stats["by_precision"]) <= {
        "gps_verified",
        "field_verified",
        "source_gps",
        "map_geocoded",
        "barangay_centroid",
        "unknown",
    }
    assert any("synthetic" in caveat.lower() for caveat in stats["caveats"])
    assert all(item["is_synthetic"] for item in facilities["items"])


def test_cursor_pagination_is_stable_and_duplicate_free(client):
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params = {"limit": 5}
        if cursor:
            params["cursor"] = cursor
        payload = _items(client, "/v1/facilities", **params)
        assert payload["limit"] == 5
        assert payload["total"] == 22
        seen.extend(item["id"] for item in payload["items"])
        pages += 1
        if not payload["has_more"]:
            assert payload["next_cursor"] is None
            break
        assert payload["next_cursor"]
        cursor = payload["next_cursor"]
    assert pages == 5
    assert len(seen) == len(set(seen)) == 22


def test_filters_cover_type_ownership_precision_and_search(client):
    schools = _items(client, "/v1/facilities", type="school", limit=100)
    assert schools["total"] == 12
    assert {item["facility_type"] for item in schools["items"]} == {"school"}

    health = _items(client, "/v1/health-facilities", limit=100)
    assert health["total"] == 10
    assert {item["facility_type"] for item in health["items"]} == {"health_facility"}

    search = _items(client, "/v1/facilities", q="School 01")
    assert search["total"] == 1
    assert search["items"][0]["display_name"] == "Synthetic Demo School 01"

    precise = _items(client, "/v1/facilities", location_precision="source_gps", limit=100)
    assert precise["items"]
    assert {item["location"]["precision"] for item in precise["items"]} == {"source_gps"}

    unknown = _items(client, "/v1/facilities", location_precision="unknown", limit=100)
    assert unknown["items"]
    assert all(item["location"]["precision"] == "unknown" for item in unknown["items"])

    with_coordinates = _items(client, "/v1/facilities", has_coordinates="true", limit=100)
    without_coordinates = _items(client, "/v1/facilities", has_coordinates="false", limit=100)
    assert with_coordinates["total"] == 15
    assert without_coordinates["total"] == 7
    assert with_coordinates["total"] + without_coordinates["total"] == 22
    assert all(item["location"]["latitude"] is not None for item in with_coordinates["items"])
    assert all(item["location"]["longitude"] is not None for item in with_coordinates["items"])
    assert all(item["location"]["latitude"] is None for item in without_coordinates["items"])
    assert all(item["location"]["longitude"] is None for item in without_coordinates["items"])
    assert all(item["location"]["precision"] == "unknown" for item in without_coordinates["items"])

    private = _items(client, "/v1/facilities", ownership="private", limit=100)
    assert private["total"] > 0
    assert {item["ownership"] for item in private["items"]} == {"private"}

    deped = _items(client, "/v1/facilities", source="deped", limit=100)
    assert deped["total"] > 0
    assert {item["facility_type"] for item in deped["items"]} == {"school"}

    doh = _items(client, "/v1/facilities", source="doh", limit=100)
    assert doh["total"] > 0
    assert {item["facility_type"] for item in doh["items"]} == {"health_facility"}

    region = _items(client, "/v1/facilities", region_code="9900000000", limit=100)
    assert region["total"] > 0
    assert {item["geography"]["region_code"] for item in region["items"]} == {"9900000000"}

    province = _items(client, "/v1/facilities", province_code="9901000000", limit=100)
    assert province["total"] > 0
    assert {item["geography"]["province_code"] for item in province["items"]} == {"9901000000"}

    first_barangay = next(
        item["geography"]["barangay_code"]
        for item in _items(client, "/v1/facilities", limit=100)["items"]
        if item["geography"]["barangay_code"]
    )
    barangay = _items(client, "/v1/facilities", barangay_code=first_barangay, limit=100)
    assert barangay["total"] > 0
    assert {item["geography"]["barangay_code"] for item in barangay["items"]} == {first_barangay}

    past = _items(client, "/v1/facilities", updated_since="2020-01-01", limit=100)
    assert past["total"] == 22
    future = _items(client, "/v1/facilities", updated_since="2099-01-01", limit=100)
    assert future["total"] == 0

    school_period = _items(
        client,
        "/v1/facilities",
        type="school",
        reference_period_start="2024-06-01",
        reference_period_end="2025-03-31",
        limit=100,
    )
    assert school_period["total"] == 12
    health_period = _items(
        client,
        "/v1/facilities",
        reference_period_start="2026-01-01",
        reference_period_end="2026-09-30",
        limit=100,
    )
    assert health_period["total"] == 10
    assert {item["facility_type"] for item in health_period["items"]} == {"health_facility"}
    outside_period = _items(
        client,
        "/v1/facilities",
        reference_period_start="2099-01-01",
        reference_period_end="2099-12-31",
        limit=100,
    )
    assert outside_period["total"] == 0

    invalid_period = client.get(
        "/v1/facilities",
        params={
            "reference_period_start": "2026-12-31",
            "reference_period_end": "2026-01-01",
        },
    )
    assert invalid_period.status_code == 400
    assert invalid_period.json()["code"] == "invalid_reference_period"


def test_search_covers_addresses_localities_and_source_identifiers(client):
    municipality = _items(client, "/v1/facilities", q="Synthetic City A1-1", limit=100)
    assert municipality["total"] > 0
    assert {item["geography"]["municipality_name"] for item in municipality["items"]} == {
        "Synthetic City A1-1 (demo)"
    }

    province = _items(client, "/v1/facilities", q="Synthetic Province B1", limit=100)
    assert province["total"] > 0
    assert {item["geography"]["province_name"] for item in province["items"]} == {
        "Synthetic Province B1 (demo)"
    }

    health_address = _items(client, "/v1/facilities", q="Synthetic Health Street", limit=100)
    assert health_address["total"] == 6
    assert {item["facility_type"] for item in health_address["items"]} == {"health_facility"}

    source_id = _items(client, "/v1/facilities", q="SYN-DEPED-0001", limit=100)
    assert source_id["total"] == 1
    assert source_id["items"][0]["display_name"] == "Synthetic Demo School 01"


def test_facility_detail_carries_provenance_quality_and_typed_profile(client):
    detail_response = client.get("/v1/facilities/synthetic-demo-school-01-deped")
    assert detail_response.status_code == 200
    detail = detail_response.json()

    assert detail["display_name"] == "Synthetic Demo School 01"
    assert detail["is_synthetic"] is True
    assert detail["source_count"] >= 3
    assert detail["location"]["precision"] == "source_gps"
    assert detail["geography"]["barangay_name"].startswith("Synthetic Barangay")
    assert detail["quality"]["identity_status"] == "source_linked"
    assert any(w["code"] == "synthetic_record" for w in detail["quality"]["warnings"])
    assert detail["school"]["deped_school_id"] == "SYN-DEPED-0001"
    assert detail["sources"]
    for source in detail["sources"]:
        assert source["is_synthetic"] is True
        assert source["release_label"]
        assert source["retrieved_at"]
        assert source["match_method"]
        assert source["row_reference"]

    sources = client.get("/v1/facilities/synthetic-demo-school-01-deped/sources").json()
    assert len(sources) == detail["source_count"]

    history = client.get("/v1/facilities/synthetic-demo-school-01-deped/history").json()
    assert history["items"]
    assert history["items"][0]["change_type"] == "facility_created"
    assert history["items"][0]["source_record_id"]


def test_school_and_health_domain_endpoints_preserve_observations(client):
    school = client.get("/v1/schools/synthetic-demo-school-01-deped").json()
    assert school["facility"]["facility_type"] == "school"
    assert school["enrollment"]
    assert any(row["school_year"] == "2024-2025" for row in school["enrollment"])
    assert any(row["grade_level"] == "total" for row in school["enrollment"])
    assert all(row["observed_at"] for row in school["enrollment"])
    assert all(row["source_record_id"] for row in school["enrollment"])
    assert school["resources"]
    assert all(row["observed_at"] for row in school["resources"])

    enrollment = client.get(
        "/v1/schools/synthetic-demo-school-01-deped/enrollment",
        params={"school_year": "2024-2025"},
    )
    assert enrollment.status_code == 200
    assert all(row["school_year"] == "2024-2025" for row in enrollment.json())

    health = client.get(
        "/v1/health-facilities/synthetic-demo-accredited-hospital-01-philhealth"
    ).json()
    assert health["facility"]["facility_type"] == "health_facility"
    assert health["accreditations"]
    accreditation = health["accreditations"][0]
    assert accreditation["authority"] == "PhilHealth"
    assert accreditation["valid_until"]
    assert accreditation["page_reference"].startswith("page:")
    assert accreditation["source_record_id"]

    licensed = client.get("/v1/health-facilities/synthetic-demo-health-facility-01-doh")
    assert licensed.status_code == 200
    licensed_body = licensed.json()
    assert licensed_body["licenses"]
    assert licensed_body["facility"]["health"]["doh_facility_id"] == "SYN-DOH-0001"

    wrong_type = client.get("/v1/schools/synthetic-demo-health-facility-01-doh")
    assert wrong_type.status_code == 404
    assert wrong_type.json()["code"] == "school_not_found"
    wrong_type = client.get("/v1/health-facilities/synthetic-demo-school-01-deped")
    assert wrong_type.status_code == 404
    assert wrong_type.json()["code"] == "health_facility_not_found"

    accreditations = client.get("/v1/accreditations")
    assert accreditations.status_code == 200
    body = accreditations.json()
    assert body["total"] >= 1
    assert body["items"]
    assert all(row["facility_type"] == "health_facility" for row in body["items"])
    assert all(row["facility_name"] for row in body["items"])

    filtered = client.get(
        "/v1/accreditations",
        params={"facility_id": health["facility"]["id"], "authority": "PhilHealth"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] >= 1
    assert all(row["facility_id"] == health["facility"]["id"] for row in filtered.json()["items"])

    bad_filter = client.get("/v1/accreditations", params={"facility_id": "not-a-uuid"})
    assert bad_filter.status_code == 400
    assert bad_filter.json()["code"] == "invalid_facility_id"


def test_detail_exposes_source_contacts_postal_code_and_accreditation_contacts(client, db_session):
    from philfacilities_api.models import (
        Facility,
        FacilityContact,
        FacilityLocation,
        HealthAccreditation,
    )
    from sqlalchemy import select

    facility = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-health-facility-01-doh")
    ).one()
    location = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(True),
        )
    ).one()
    accredited = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-accredited-hospital-01-philhealth")
    ).one()
    accreditation = db_session.scalars(
        select(HealthAccreditation).where(HealthAccreditation.facility_id == accredited.id)
    ).first()
    assert accreditation is not None
    original_postal_code = location.postal_code
    original_contacts = {
        "telephone": accreditation.telephone,
        "email": accreditation.email,
        "street_address": accreditation.street_address,
        "municipality": accreditation.municipality,
    }

    location.postal_code = "1000"
    accreditation.telephone = "+63 2 8555 0100"
    accreditation.email = "records@example.test"
    accreditation.street_address = "100 Synthetic Avenue"
    accreditation.municipality = "Synthetic City"
    contact = FacilityContact(
        facility_id=facility.id,
        contact_type="phone",
        value="+63 2 8555 0100",
        label="Main line",
        source_record_id=location.source_record_id,
        source_field="telephone",
    )
    db_session.add(contact)
    db_session.commit()

    try:
        detail = _items(client, f"/v1/facilities/{facility.id}")
        assert detail["location"]["postal_code"] == "1000"
        phone = next(
            item
            for item in detail["contacts"]
            if item["contact_type"] == "phone" and item["value"] == "+63 2 8555 0100"
        )
        assert phone["source_record_id"] == str(location.source_record_id)

        detail = _items(client, f"/v1/facilities/{accredited.id}")
        exposed = next(
            item for item in detail["accreditations"] if item["id"] == str(accreditation.id)
        )
        assert exposed["telephone"] == "+63 2 8555 0100"
        assert exposed["email"] == "records@example.test"
        assert exposed["street_address"] == "100 Synthetic Avenue"
        assert exposed["municipality"] == "Synthetic City"

        listed = _items(client, "/v1/accreditations", facility_id=str(accredited.id))
        listed_row = next(item for item in listed["items"] if item["id"] == str(accreditation.id))
        assert listed_row["telephone"] == "+63 2 8555 0100"

        taxonomy = _items(client, "/v1/taxonomy")
        assert taxonomy["version"] == "3.0"
        school = next(item for item in taxonomy["categories"] if item["code"] == "school")
        assert school["label"] == "Education"
        assert any(
            item["code"] == "PUBLIC_ELEMENTARY_SCHOOL"
            and item["label"] == "Public elementary school"
            for item in school["subtypes"]
        )
        assert any(item["code"] == "phone" for item in taxonomy["contact_types"])
    finally:
        db_session.delete(contact)
        location.postal_code = original_postal_code
        accreditation.telephone = original_contacts["telephone"]
        accreditation.email = original_contacts["email"]
        accreditation.street_address = original_contacts["street_address"]
        accreditation.municipality = original_contacts["municipality"]
        db_session.commit()


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def test_spatial_queries_are_bounded_and_respect_coordinates(client):
    bbox = "120.55,14.40,121.18,14.85"
    within = client.get("/v1/facilities/within", params={"bbox": bbox, "limit": 100})
    assert within.status_code == 200
    body = within.json()
    assert body["bbox"] == bbox
    assert body["items"]
    assert body["truncated"] is False
    min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
    for item in body["items"]:
        latitude = item["location"]["latitude"]
        longitude = item["location"]["longitude"]
        assert latitude is not None and longitude is not None
        assert min_lat <= latitude <= max_lat
        assert min_lon <= longitude <= max_lon

    filtered_within = client.get(
        "/v1/facilities/within",
        params={"bbox": bbox, "type": "school", "source": "deped", "limit": 100},
    )
    assert filtered_within.status_code == 200
    assert filtered_within.json()["items"]
    assert {item["facility_type"] for item in filtered_within.json()["items"]} == {"school"}

    # Regression: the map query joins FacilityLocation. Subqueries in the shared
    # filter builder must correlate only Facility, or SQLAlchemy removes their FROM
    # clause and the request fails with a 500.
    combined_within = client.get(
        "/v1/facilities/within",
        params={
            "bbox": bbox,
            "type": "school",
            "source": "deped",
            "province_code": "9901000000",
            "location_precision": "source_gps",
            "updated_since": "2026-11-01",
            "limit": 100,
        },
    )
    assert combined_within.status_code == 200
    for item in combined_within.json()["items"]:
        assert item["location"]["precision"] == "source_gps"
        assert item["geography"]["province_code"] == "9901000000"

    nearby = client.get(
        "/v1/facilities/nearby",
        params={"lat": 14.5995, "lon": 120.9842, "radius_m": 20_000, "limit": 100},
    )
    assert nearby.status_code == 200
    nearby_body = nearby.json()
    assert nearby_body["items"]
    assert nearby_body["center"] == {"lat": 14.5995, "lon": 120.9842}
    for item in nearby_body["items"]:
        distance = _haversine_m(
            14.5995,
            120.9842,
            item["location"]["latitude"],
            item["location"]["longitude"],
        )
        assert distance <= 20_050

    unacceptable = client.get("/v1/facilities/within", params={"bbox": "116.0,4.0,127.0,22.0"})
    assert unacceptable.status_code == 400
    assert unacceptable.json()["code"] == "bbox_too_large"


def test_geography_release_chain_and_psgc_values(client):
    regions = _items(client, "/v1/geographies", level="region", limit=100)
    assert len(regions) == 2
    assert {row["geographic_level"] for row in regions} == {"region"}
    assert all(row["psgc_code"].isdigit() for row in regions)

    barangay = client.get("/v1/geographies/9901001001")
    assert barangay.status_code == 200
    assert barangay.json()["geographic_level"] == "barangay"
    assert barangay.json()["parent_psgc_code"] == "9901001000"

    children = _items(client, "/v1/geographies", parent="9901001000", limit=100)
    assert {row["geographic_level"] for row in children} == {"barangay"}

    facilities = client.get("/v1/geographies/9901001001/facilities").json()
    assert facilities["total"] > 0
    assert all(
        item["geography"]["psgc_code"] == "9901001001"
        for item in facilities["items"]
        if item["geography"]["psgc_code"] is not None
    )

    releases = client.get("/v1/geography-releases")
    assert releases.status_code == 200
    release_rows = releases.json()
    assert len(release_rows) == 1
    assert release_rows[0]["release_label"] == "SYNTHETIC-DEMO-2026-Q3"
    assert release_rows[0]["is_synthetic"] is True

    crosswalk = client.get(
        "/v1/geography-crosswalk",
        params={
            "from_release": release_rows[0]["release_label"],
            "to_release": release_rows[0]["release_label"],
        },
    )
    assert crosswalk.status_code == 200
    assert crosswalk.json() == []

    missing = client.get("/v1/geographies/0000000000")
    assert missing.status_code == 404
    assert missing.json()["code"] == "geography_not_found"


def test_source_catalogue_and_release_history_expose_rights(client):
    sources = client.get("/v1/sources").json()
    assert len(sources) == 6
    assert {source["slug"] for source in sources} == {
        "demo-psgc",
        "demo-deped-masterlist",
        "demo-deped-enrollment",
        "demo-deped-resources",
        "demo-doh-facilities",
        "demo-philhealth-accreditations",
    }
    for source in sources:
        assert source["is_synthetic"] is True
        assert source["agency_code"] in {"psa", "deped", "doh", "philhealth"}
        assert source["redistribution_status"] == "not_applicable"
        assert source["publication_status"] in {"approved", "published"}
        assert "rights_basis" in source
        assert "attribution_text" in source
        assert "personal_data_status" in source
        assert "Synthetic fixture" in source["license_identifier"]
        assert source["latest_release"] or source["latest_geography_release"]
        if source["slug"] == "demo-psgc":
            # PSGC releases live in the geography ledger, not the row-file ledger.
            assert source["latest_release"] is None
            assert source["latest_geography_release"]["release_label"] == "SYNTHETIC-DEMO-2026-Q3"
        else:
            assert source["latest_release"]["sha256"]
            assert source["latest_release"]["row_count_parsed"] is not None

    releases = client.get("/v1/source-releases").json()
    assert len(releases) == 5
    assert all(release["ingestion_status"] == "published" for release in releases)
    assert all(release["terms_review_status"] == "synthetic_demo" for release in releases)
    assert {release["dataset_slug"] for release in releases} == {
        "demo-deped-masterlist",
        "demo-deped-enrollment",
        "demo-deped-resources",
        "demo-doh-facilities",
        "demo-philhealth-accreditations",
    }

    deped_releases = client.get(
        "/v1/source-releases", params={"dataset": "demo-deped-masterlist"}
    ).json()
    assert len(deped_releases) == 1
    assert deped_releases[0]["source_release_label"] == "SYNTHETIC-DEMO-SY2024-2025"
    assert deped_releases[0]["source_published_at"]

    missing = client.get("/v1/sources/not-a-dataset")
    assert missing.status_code == 404
    assert missing.json()["code"] == "dataset_not_found"


def test_monitoring_endpoints_expose_measured_checks_only(client):
    monitoring = client.get("/v1/monitoring")
    assert monitoring.status_code == 200
    rows = monitoring.json()
    assert isinstance(rows, list)
    for row in rows:
        assert "latest_run_acceptance_rate" in row
        assert "latest_run_duration_ms" in row

    checks = client.get("/v1/source-checks", params={"limit": 10})
    assert checks.status_code == 200
    assert isinstance(checks.json(), list)
    for check in checks.json():
        assert check["dataset_slug"]
        assert check["status"]
        assert check["checked_at"]


def test_monitoring_query_is_bounded_to_latest_rows_per_dataset(client):
    """Monitoring must not load every historical check, release and run."""

    from philfacilities_api.db import engine
    from sqlalchemy import event

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _params, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = client.get("/v1/monitoring")
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    monitoring_sql = [
        statement
        for statement in statements
        if any(
            table in statement
            for table in ("source.source_checks", "source.releases", "source.ingestion_runs")
        )
    ]
    assert monitoring_sql
    for table in ("source.source_checks", "source.releases", "source.ingestion_runs"):
        assert any(
            table in statement and "DISTINCT ON" in statement.upper()
            for statement in monitoring_sql
        ), f"{table} was queried without a latest-per-dataset bound"


def test_quality_summary_is_measured_not_editorial(client):
    quality = client.get("/v1/quality/summary").json()
    assert quality["facility_count"] == 22
    assert quality["published_facility_count"] == 22
    assert quality["synthetic_facility_count"] == 22
    # Precision is measured over location rows. All 22 fixtures have some location
    # evidence: 15 carry a point and seven persist a PSGC-only location row under
    # data.md §9.1 rather than discarding non-coordinate evidence.
    assert sum(quality["coordinate_precision"].values()) == 22
    assert quality["coordinate_precision"].get("unknown", 0) == 10
    assert quality["datasets_by_redistribution_status"] == {"not_applicable": 6}
    assert quality["last_successful_runs"]
    assert {run["dataset"] for run in quality["last_successful_runs"]} == {
        "demo-psgc",
        "demo-deped-masterlist",
        "demo-deped-enrollment",
        "demo-deped-resources",
        "demo-doh-facilities",
        "demo-philhealth-accreditations",
    }
    assert any("synthetic" in caveat.lower() for caveat in quality["caveats"])


def test_bulk_downloads_match_publication_gate(client):
    csv_response = client.get("/v1/downloads/facilities.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert len(rows) == 22
    assert all(row["is_synthetic"] == "True" for row in rows)
    assert all(row["publication_status"] == "public" for row in rows)
    assert {
        "official_name",
        "ownership_type",
        "operator_type",
        "public_access_class",
        "facility_kind",
        "inclusion_class",
        "postal_code",
    } <= set(rows[0])

    schools = list(csv.DictReader(io.StringIO(client.get("/v1/downloads/schools.csv").text)))
    health = list(
        csv.DictReader(io.StringIO(client.get("/v1/downloads/health-facilities.csv").text))
    )
    assert len(schools) == 12
    assert len(health) == 10

    parquet_response = client.get("/v1/downloads/facilities.parquet")
    assert parquet_response.status_code == 200
    assert parquet_response.headers["content-type"] == "application/vnd.apache.parquet"
    table = pq.read_table(io.BytesIO(parquet_response.content))
    assert table.num_rows == 22
    assert "display_name" in table.column_names


def test_bulk_downloads_chunk_facility_id_lookups(client, monkeypatch):
    """Large exports must not exceed PostgreSQL's bind-parameter limit.

    The real database has tens of thousands of public facilities. Chunking the
    location and source-evidence lookups keeps each query bounded; this test
    forces a tiny chunk size so the multi-chunk path runs against the demo data.
    """

    from philfacilities_api import services

    original = services._chunked
    monkeypatch.setattr(services, "_chunked", lambda values: original(values, 3))

    csv_response = client.get("/v1/downloads/facilities.csv")
    assert csv_response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert len(rows) == 22
    assert len({row["id"] for row in rows}) == 22

    parquet_response = client.get("/v1/downloads/facilities.parquet")
    assert parquet_response.status_code == 200
    table = pq.read_table(io.BytesIO(parquet_response.content))
    assert table.num_rows == 22


def test_facility_csv_export_neutralizes_spreadsheet_formulas(client, db_session):
    from philfacilities_api.models import Facility
    from sqlalchemy import select

    facility = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-school-01-deped")
    ).one()
    original_name = facility.display_name
    facility.display_name = '=HYPERLINK("https://example.invalid","click")'
    db_session.commit()
    try:
        response = client.get("/v1/facilities/synthetic-demo-school-01-deped/export.csv")
        assert response.status_code == 200
        row = next(csv.DictReader(io.StringIO(response.text)))
        assert row["display_name"].startswith("'=")
        assert row["latitude"] != ""
        assert not row["latitude"].startswith("'")
    finally:
        facility.display_name = original_name
        db_session.commit()


def test_internal_accreditation_source_is_not_exposed(client, db_session):
    """A public facility must not leak an accreditation from a blocked dataset."""

    import uuid
    from datetime import UTC, date, datetime

    from philfacilities_api.models import (
        Agency,
        Dataset,
        Facility,
        HealthAccreditation,
        Release,
        SourceRecord,
    )
    from sqlalchemy import select

    token = uuid.uuid4().hex[:10]
    facility = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-accredited-hospital-01-philhealth")
    ).one()
    agency = db_session.scalars(select(Agency).where(Agency.short_code == "philhealth")).one()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"internal-accreditation-{token}",
        name="Internal accreditation test dataset",
        redistribution_status="restricted_non_redistributable",
        publication_status="blocked",
        coverage_scope="NATIONAL_PARTIAL",
    )
    db_session.add(dataset)
    db_session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"INTERNAL-{token}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="blocked",
    )
    db_session.add(release)
    db_session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key=f"internal-{token}",
        raw_payload={"provider": "Internal Only Hospital"},
        raw_record_hash=uuid.uuid4().hex * 2,
    )
    db_session.add(record)
    db_session.flush()
    accreditation = HealthAccreditation(
        facility_id=facility.id,
        authority="Internal Reviewer",
        provider_category="Hospital",
        accreditation_category=f"Internal {token}",
        valid_until=date(2027, 12, 31),
        source_record_id=record.id,
    )
    db_session.add(accreditation)
    db_session.commit()

    try:
        detail = _items(client, f"/v1/facilities/{facility.id}")
        assert detail["accreditations"]
        assert all(item["id"] != str(accreditation.id) for item in detail["accreditations"])

        nested = _items(client, f"/v1/facilities/{facility.id}/accreditations")
        assert all(item["id"] != str(accreditation.id) for item in nested)

        listed = _items(client, "/v1/accreditations", facility_id=str(facility.id))
        assert listed["items"]
        assert all(item["id"] != str(accreditation.id) for item in listed["items"])
    finally:
        # Delete in dependency order; the FK is not relationship-mapped, so a
        # single flush could otherwise emit the dataset delete too early.
        db_session.delete(accreditation)
        db_session.delete(record)
        db_session.commit()
        db_session.delete(release)
        db_session.commit()
        db_session.delete(dataset)
        db_session.commit()


def test_invalid_cursor_and_unknown_facility_fail_closed(client):
    bad_cursor = client.get("/v1/facilities", params={"cursor": "not-base64"})
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["code"] == "invalid_cursor"

    oversized_cursor = client.get("/v1/facilities", params={"cursor": "x" * 600})
    assert oversized_cursor.status_code == 400
    assert oversized_cursor.json()["code"] == "invalid_cursor"

    missing = client.get("/v1/facilities/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["code"] == "facility_not_found"
