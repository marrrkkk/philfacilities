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


FULL_DETAIL_GOLDEN_KEYS = {
    "access_conditions",
    "accreditations",
    "contacts",
    "created_at",
    "display_name",
    "facility_kind",
    "facility_subtype",
    "facility_type",
    "function_details",
    "functions",
    "geography",
    "health",
    "id",
    "inclusion_class",
    "is_synthetic",
    "location",
    "official_name",
    "operator_type",
    "ownership",
    "ownership_type",
    "public_access_class",
    "publication_status",
    "quality",
    "record_status",
    "relationships",
    "roles",
    "school",
    "services",
    "slug",
    "source_count",
    "source_refs",
    "sources",
    "updated_at",
    "utility",
}


def test_domain_details_share_the_generic_detail_shape(client):
    school = _items(client, "/v1/facilities", type="school", limit=1)["items"][0]["slug"]
    health = _items(client, "/v1/facilities", type="health_facility", limit=1)["items"][0]["slug"]

    cases = (
        (f"/v1/schools/{school}", "resources", "school"),
        (f"/v1/health-facilities/{health}", "licenses", "health"),
    )
    for path, collection_key, profile_key in cases:
        wrapper = client.get(path).json()
        assert set(wrapper) == (
            {"facility", "resources"}
            if collection_key == "resources"
            else {"facility", "licenses", "accreditations"}
        )
        assert set(wrapper["facility"]) == FULL_DETAIL_GOLDEN_KEYS
        assert wrapper["facility"][profile_key] is not None

        unified = client.get(path, params={"shape": "detail"}).json()
        assert set(unified) == FULL_DETAIL_GOLDEN_KEYS
        generic = client.get(
            f"/v1/facilities/{school if profile_key == 'school' else health}"
        ).json()
        for field in ("id", "display_name", "facility_type", "inclusion_class", "ownership"):
            assert unified[field] == generic[field]
        assert unified["location"] == generic["location"]

        compact = client.get(path, params={"shape": "detail", "view": "compact"}).json()
        assert len(compact) <= 12
        assert compact["name"] == compact["display_name"]

        wrapper_compact = client.get(path, params={"view": "compact"}).json()
        assert len(wrapper_compact["facility"]) == 12

        with_sources = client.get(path, params={"view": "compact", "include": "sources"}).json()
        assert "sources" in with_sources["facility"]
        assert "school" not in with_sources["facility"]

        invalid = client.get(path, params={"include": "bogus"})
        assert invalid.status_code == 400
        assert invalid.json()["code"] == "invalid_include"

    # Every domain collection row must trace to a public source record.
    evidence = {
        row["source_record_uuid"] for row in client.get(f"/v1/facilities/{health}/sources").json()
    }
    detail = client.get(f"/v1/health-facilities/{health}").json()
    for row in detail["licenses"] + detail["accreditations"]:
        assert row["source_record_id"] in evidence


def test_field_coverage_counts_use_the_public_gate(client, db_session):
    payload = _items(client, "/v1/fields")
    assert payload["version"]
    assert payload["caveats"]
    fields = {entry["field"]: entry for entry in payload["fields"]}

    for entry in payload["fields"]:
        assert 0 <= entry["populated"] <= entry["total"] <= 22
        expected_ratio = round(entry["populated"] / entry["total"], 6) if entry["total"] else 0.0
        assert entry["fill_ratio"] == expected_ratio
        assert entry["semantics"]

    # Synthetic demo fixtures have no relationships; they do carry one resource
    # observation per school (the working database has none, see the baseline).
    assert fields["relationships[]"]["populated"] == 0
    assert fields["relationships[]"]["total"] == 22
    assert fields["school.resources[]"]["populated"] == 12
    assert fields["school.resources[]"]["total"] == 12
    # All 22 demo facilities have a current location row (7 have no coordinates);
    # the denominator is rows, not facilities with coordinates.
    assert fields["location.postal_code"]["total"] == 22
    assert fields["school.sector"]["total"] == 12  # schools only, not all facilities
    assert fields["health.licensing_status"]["total"] == 10  # health facilities only

    # An internal facility with a filled field must not change any public count.
    from philfacilities_api.models import Facility

    hidden = Facility(
        slug="coverage-internal-fixture",
        display_name="Internal coverage fixture",
        facility_type="library",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        ownership_type="GOVERNMENT_AGENCY",
        operator_type="UNKNOWN",
        public_access_class="PUBLIC_FREE",
        record_status="active",
        publication_status="internal",
        is_synthetic=True,
        official_name="Should not be counted",
    )
    db_session.add(hidden)
    db_session.commit()
    try:
        after = {entry["field"]: entry for entry in _items(client, "/v1/fields")["fields"]}
        assert after["official_name"]["populated"] == fields["official_name"]["populated"]
        assert after["public_access_class"]["total"] == fields["public_access_class"]["total"]
        assert after["relationships[]"]["total"] == fields["relationships[]"]["total"]
    finally:
        db_session.delete(hidden)
        db_session.commit()


def test_field_coverage_materialized_view_reconciles_with_on_demand(db_session):
    """The projection must not drift from the declarative field definitions."""

    from philfacilities_api.services.coverage_mv import (
        MV_NAME,
        coverage_mv_fresh,
        read_coverage_mv,
    )
    from philfacilities_api.services.field_coverage import (
        FIELD_COVERAGE_VERSION,
        FIELDS,
        collect_field_coverage,
    )
    from sqlalchemy import text

    assert coverage_mv_fresh(db_session), "demo load must refresh the view after publication"
    assert read_coverage_mv(db_session)["version"] == FIELD_COVERAGE_VERSION
    # The reader back-fills zero entries for declared fields, so comparing its
    # output alone cannot detect a field added after migration 0026. Compare the
    # view's own rows with fields that have eligible public facilities; a field
    # with no eligible rows legitimately has no MV row.
    stored_fields = {
        row.field for row in db_session.execute(text(f"SELECT DISTINCT field FROM {MV_NAME}")).all()
    }
    projected = read_coverage_mv(db_session, by_category=True)
    computed = collect_field_coverage(db_session, by_category=True)
    eligible_fields = {
        entry["field"] for entries in computed["by_category"].values() for entry in entries
    }
    assert stored_fields == eligible_fields
    assert stored_fields <= {definition.path for definition in FIELDS}
    projected_fields = {entry["field"]: entry for entry in projected["fields"]}
    computed_fields = {entry["field"]: entry for entry in computed["fields"]}
    assert set(projected_fields) == set(computed_fields)
    for field, entry in computed_fields.items():
        assert projected_fields[field]["populated"] == entry["populated"], field
        assert projected_fields[field]["total"] == entry["total"], field
        assert projected_fields[field]["scope"] == entry["scope"], field
    assert set(projected["by_category"]) == set(computed["by_category"])


def test_publication_refresh_hook_updates_field_coverage(client, db_session):
    """The ingest hook must move the projection after a new public record."""

    from philfacilities_api.models import Facility
    from philfacilities_api.services.coverage_mv import read_coverage_mv
    from philfacilities_ingest.pipeline.coverage_refresh import (
        refresh_coverage_after_publication,
    )

    def official_name_populated() -> int:
        return next(
            entry["populated"]
            for entry in read_coverage_mv(db_session)["fields"]
            if entry["field"] == "official_name"
        )

    before = official_name_populated()
    facility = Facility(
        slug="coverage-refresh-hook",
        display_name="Coverage refresh hook fixture",
        official_name="Refreshed official name",
        facility_type="library",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        record_status="active",
        publication_status="public",
        is_synthetic=True,
    )
    db_session.add(facility)
    db_session.commit()
    try:
        refresh_coverage_after_publication(db_session)
        assert official_name_populated() == before + 1
        payload = client.get("/v1/fields").json()
        assert (
            next(
                entry["populated"]
                for entry in payload["fields"]
                if entry["field"] == "official_name"
            )
            == before + 1
        )
    finally:
        db_session.delete(facility)
        db_session.commit()
        refresh_coverage_after_publication(db_session)


def test_field_coverage_by_category_and_etag(client):
    payload = _items(client, "/v1/fields", by_category="true")
    assert set(payload["by_category"]) == {"school", "health_facility"}
    school_entries = {entry["field"]: entry for entry in payload["by_category"]["school"]}
    assert school_entries["school.sector"]["total"] == 12
    assert school_entries["school.sector"]["populated"] <= 12
    overall = {entry["field"]: entry for entry in payload["fields"]}
    assert school_entries["school.sector"]["populated"] == overall["school.sector"]["populated"]

    first = client.get("/v1/fields")
    etag = first.headers["etag"]
    assert first.headers["cache-control"] == "public, max-age=3600"
    second = client.get("/v1/fields", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["content-length"] == "0"
    assert second.headers["etag"] == etag


def test_compact_detail_is_small_and_full_view_is_unchanged(client):
    path = "/v1/facilities/synthetic-demo-school-01"
    default = client.get(path)
    assert default.status_code == 200
    assert set(default.json()) == FULL_DETAIL_GOLDEN_KEYS
    explicit_full = client.get(path, params={"view": "full"})
    assert explicit_full.json() == default.json()

    compact_response = client.get(path, params={"view": "compact"})
    assert compact_response.status_code == 200
    compact = compact_response.json()
    assert len(compact) <= 12
    assert len(compact_response.content) < 2_500
    assert compact["name"] == compact["display_name"] == "Synthetic Demo School 01"
    assert compact["id"] == default.json()["id"]
    assert {"sources", "school", "health", "contacts", "relationships", "quality"} <= set(
        default.json()
    )
    assert not {"sources", "school", "health", "contacts", "relationships", "quality"} & set(
        compact
    )

    missing = client.get("/v1/facilities/does-not-exist", params={"view": "compact"})
    assert missing.status_code == 404
    assert missing.json()["code"] == "facility_not_found"


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


def test_compact_list_keeps_pages_and_cuts_payload(client):
    full = client.get("/v1/facilities", params={"limit": 100})
    compact = client.get("/v1/facilities", params={"limit": 100, "view": "compact"})
    assert full.status_code == compact.status_code == 200
    full_payload, compact_payload = full.json(), compact.json()
    assert full_payload["total"] == compact_payload["total"] == 22
    assert full_payload["next_cursor"] == compact_payload["next_cursor"]
    assert len(compact_payload["items"]) == len(full_payload["items"]) == 22
    assert all(len(item) == 12 for item in compact_payload["items"])
    assert all(
        "name" in item and item["name"] == item["display_name"] for item in compact_payload["items"]
    )
    assert all("quality" not in item for item in compact_payload["items"])
    assert all(
        "source_count" in item and "source_refs" not in item for item in compact_payload["items"]
    )
    assert len(compact.content) < len(full.content) * 0.7


def test_total_false_skips_the_count_without_changing_pages(client):
    default = _items(client, "/v1/facilities", limit=5)
    assert default["total"] == 22
    lean = _items(client, "/v1/facilities", limit=5, total="false")
    assert lean["total"] is None
    assert lean["items"] == default["items"]
    assert lean["has_more"] == default["has_more"]
    assert lean["next_cursor"] == default["next_cursor"]

    schools = _items(client, "/v1/schools", limit=5, total="false")
    assert schools["total"] is None
    assert len(schools["items"]) == 5


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
    detail_response = client.get("/v1/facilities/synthetic-demo-school-01")
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

    sources = client.get("/v1/facilities/synthetic-demo-school-01/sources").json()
    assert len(sources) == detail["source_count"]
    assert len(detail["source_refs"]) == len(sources)
    for ref, source in zip(detail["source_refs"], sources, strict=True):
        assert ref["agency_code"] == source["agency_code"]
        assert ref["dataset_slug"] == source["dataset_slug"]
        assert ref["source_record_id"] == source["source_record_id"]

    history = client.get("/v1/facilities/synthetic-demo-school-01/history").json()
    assert history["items"]
    assert history["items"][0]["change_type"] == "facility_created"
    assert history["items"][0]["source_record_id"]


def test_school_and_health_domain_endpoints_preserve_observations(client):
    school = client.get("/v1/schools/synthetic-demo-school-01").json()
    assert school["facility"]["facility_type"] == "school"
    assert "enrollment" not in school
    assert school["resources"]
    assert all(row["observed_at"] for row in school["resources"])

    enrollment = client.get(
        "/v1/schools/synthetic-demo-school-01/enrollment",
        params={"school_year": "2024-2025"},
    )
    assert enrollment.status_code == 404

    health = client.get("/v1/health-facilities/synthetic-demo-accredited-hospital-01").json()
    assert health["facility"]["facility_type"] == "health_facility"
    assert health["accreditations"]
    accreditation = health["accreditations"][0]
    assert accreditation["authority"] == "PhilHealth"
    assert accreditation["valid_until"]
    assert accreditation["page_reference"].startswith("page:")
    assert accreditation["source_record_id"]

    licensed = client.get("/v1/health-facilities/synthetic-demo-health-facility-01")
    assert licensed.status_code == 200
    licensed_body = licensed.json()
    assert licensed_body["licenses"]
    assert licensed_body["facility"]["health"]["doh_facility_id"] == "SYN-DOH-0001"

    wrong_type = client.get("/v1/schools/synthetic-demo-health-facility-01")
    assert wrong_type.status_code == 404
    assert wrong_type.json()["code"] == "school_not_found"
    wrong_type = client.get("/v1/health-facilities/synthetic-demo-school-01")
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
        select(Facility).where(Facility.slug == "synthetic-demo-health-facility-01")
    ).one()
    location = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(True),
        )
    ).one()
    accredited = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-accredited-hospital-01")
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


def test_map_endpoint_returns_minimal_points_and_server_clusters(client, monkeypatch):
    bbox = "120.55,14.40,121.18,14.85"
    points = client.get("/v1/facilities/map", params={"bbox": bbox, "zoom": 9})
    assert points.status_code == 200
    body = points.json()
    assert body["mode"] == "points"
    assert body["total"] == len(body["points"])
    assert body["points"]
    assert set(body["points"][0]) == {
        "id",
        "slug",
        "name",
        "facility_type",
        "inclusion_class",
        "precision",
        "latitude",
        "longitude",
    }
    min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
    for point in body["points"]:
        assert min_lat <= point["latitude"] <= max_lat
        assert min_lon <= point["longitude"] <= max_lon

    # A wide national viewport must never fail just because it is large; the
    # endpoint switches to count circles instead of rejecting the view.
    wide = client.get("/v1/facilities/map", params={"bbox": "116.0,4.0,127.0,22.0", "zoom": 5})
    assert wide.status_code == 200
    assert wide.json()["mode"] in {"points", "clusters"}

    from philfacilities_api.api import facilities as facilities_api

    monkeypatch.setattr(facilities_api.settings, "max_map_points", 1)
    clustered = client.get("/v1/facilities/map", params={"bbox": bbox, "zoom": 10})
    assert clustered.status_code == 200
    clustered_body = clustered.json()
    assert clustered_body["mode"] == "clusters"
    assert clustered_body["clusters"]
    assert clustered_body["total"] == sum(
        cluster["count"] for cluster in clustered_body["clusters"]
    )
    for cluster in clustered_body["clusters"]:
        assert cluster["label"].endswith(("facility", "facilities"))
        assert min_lat <= cluster["latitude"] <= max_lat
        assert min_lon <= cluster["longitude"] <= max_lon

    invalid = client.get("/v1/facilities/map", params={"bbox": "0,0,0,0"})
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "invalid_bbox"


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


def test_filtered_downloads_match_list_counts_and_stay_gated(client, db_session):
    """Every category can be exported by filtering the generic download."""

    for params, expected in (
        ({"type": "school"}, 12),
        ({"facility_type": "health_facility"}, 10),
        ({"has_coordinates": "true"}, 15),
        ({"source": "deped"}, None),
        ({"type": "school", "psgc": "99"}, None),
        ({"q": "Synthetic Demo School"}, None),
        ({"location_precision": "source_gps"}, None),
    ):
        listed = _items(client, "/v1/facilities", limit=100, **params)
        if expected is not None:
            assert listed["total"] == expected
        csv_response = client.get("/v1/downloads/facilities.csv", params=params)
        assert csv_response.status_code == 200, csv_response.text
        rows = list(csv.DictReader(io.StringIO(csv_response.text)))
        assert len(rows) == listed["total"]
        assert all(row["publication_status"] == "public" for row in rows)
        assert all(row["is_synthetic"] == "True" for row in rows)
        assert [row["display_name"] for row in rows] == sorted(
            row["display_name"] for row in rows
        ), "export ordering must remain stable"

    parquet = client.get("/v1/downloads/facilities.parquet", params={"type": "library"})
    assert parquet.status_code == 404  # no matching rows -> same gate as the list
    school_parquet = client.get("/v1/downloads/facilities.parquet", params={"type": "school"})
    assert school_parquet.status_code == 200
    assert pq.read_table(io.BytesIO(school_parquet.content)).num_rows == 12

    # A hidden facility must never appear in a filtered export.
    from philfacilities_api.models import Facility

    hidden = Facility(
        slug="download-internal-fixture",
        display_name="Hidden library export fixture",
        facility_type="library",
        inclusion_class="GOVERNMENT_FACILITY",
        ownership="government",
        record_status="active",
        publication_status="internal",
        is_synthetic=True,
    )
    db_session.add(hidden)
    db_session.commit()
    try:
        rows = list(
            csv.DictReader(
                io.StringIO(
                    client.get("/v1/downloads/facilities.csv", params={"type": "library"}).text
                )
            )
        )
        assert all(row["id"] != str(hidden.id) for row in rows)
    finally:
        db_session.delete(hidden)
        db_session.commit()


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
        select(Facility).where(Facility.slug == "synthetic-demo-school-01")
    ).one()
    original_name = facility.display_name
    facility.display_name = '=HYPERLINK("https://example.invalid","click")'
    db_session.commit()
    try:
        response = client.get("/v1/facilities/synthetic-demo-school-01/export.csv")
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
        select(Facility).where(Facility.slug == "synthetic-demo-accredited-hospital-01")
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


def test_retired_source_suffix_slug_still_resolves(client, db_session):
    """A normalized slug keeps the previous source-suffixed URL working."""

    from philfacilities_api.models import Facility, FacilitySlugAlias
    from sqlalchemy import select

    facility = db_session.scalars(
        select(Facility).where(Facility.slug == "synthetic-demo-school-01")
    ).one()
    alias = FacilitySlugAlias(
        slug="synthetic-demo-school-01-deped",
        facility_id=facility.id,
    )
    db_session.add(alias)
    db_session.commit()
    try:
        response = client.get("/v1/facilities/synthetic-demo-school-01-deped")
        assert response.status_code == 200
        assert response.json()["id"] == str(facility.id)
    finally:
        db_session.delete(alias)
        db_session.commit()
