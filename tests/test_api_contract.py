"""Public API contract checks that do not require database rows."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


REQUIRED_PATHS = {
    "/healthz",
    "/v1",
    "/v1/facilities",
    "/v1/facilities/within",
    "/v1/facilities/map",
    "/v1/facilities/nearby",
    "/v1/facilities/{facility_id}",
    "/v1/facilities/{facility_id}/sources",
    "/v1/facilities/{facility_id}/assertions",
    "/v1/facilities/{facility_id}/history",
    "/v1/facilities/{facility_id}/accreditations",
    "/v1/accreditations",
    "/v1/schools",
    "/v1/schools/{facility_id}",
    "/v1/schools/{facility_id}/enrollment",
    "/v1/schools/{facility_id}/resources",
    "/v1/health-facilities",
    "/v1/health-facilities/{facility_id}",
    "/v1/health-facilities/{facility_id}/accreditations",
    "/v1/health-facilities/{facility_id}/licenses",
    "/v1/geographies",
    "/v1/geographies/{psgc_code}",
    "/v1/geographies/{psgc_code}/facilities",
    "/v1/geography-releases",
    "/v1/geography-crosswalk",
    "/v1/sources",
    "/v1/sources/{source_id}",
    "/v1/source-releases",
    "/v1/quality/summary",
    "/v1/quality/issues",
    "/v1/quality/match-candidates",
    "/v1/quality/match-candidates/{candidate_id}",
    "/v1/changes",
    "/v1/statistics",
    "/v1/coverage",
    "/v1/taxonomy",
    "/v1/downloads/facilities.csv",
    "/v1/downloads/facilities.parquet",
    "/v1/downloads/schools.csv",
    "/v1/downloads/health-facilities.csv",
    "/v1/monitoring",
    "/v1/population",
    "/v1/source-checks",
}


def test_openapi_contains_the_public_read_contract(openapi_client):
    response = openapi_client.get("/openapi.json")
    assert response.status_code == 200
    document = response.json()

    assert document["info"]["title"] == "PhilFacilities API"
    assert "Apache-2.0" in document["info"]["license"]["name"]
    assert document["info"]["description"].find("is_synthetic") > 0
    paths = set(document["paths"])
    assert paths == REQUIRED_PATHS

    schema_names = set(document["components"]["schemas"])
    assert {
        "FacilitySummary",
        "FacilityDetail",
        "ContactOut",
        "TaxonomyResponse",
        "FacilityListResponse",
        "SourceEvidence",
        "AttributeAssertionOut",
        "QualitySummary",
        "MatchCandidateOut",
        "MatchCandidateListResponse",
        "LatestReleaseOut",
        "IngestionRunSummary",
        "SchoolDetailResponse",
        "HealthDetailResponse",
        "UtilityProfileOut",
    } <= schema_names

    facility_detail = document["components"]["schemas"]["FacilityDetail"]["properties"]
    assert facility_detail["utility"]["anyOf"][0]["$ref"].endswith("UtilityProfileOut")

    facility_summary = document["components"]["schemas"]["FacilitySummary"]["properties"]
    assert facility_summary["is_synthetic"]["type"] == "boolean"
    assert facility_summary["source_count"]["type"] == "integer"
    assert facility_summary["location"]["$ref"].endswith("LocationOut")


def test_openapi_is_read_only(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    methods = {
        method
        for path in document["paths"].values()
        for method in path
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert methods == {"get"}


def test_committed_openapi_document_matches_the_application():
    import json
    from pathlib import Path

    from philfacilities_api.main import app

    contract_path = Path(__file__).resolve().parents[1] / "packages/api-client/openapi.json"
    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    assert committed == app.openapi()


def test_error_envelope_and_request_headers(client):
    response = client.get(
        "/v1/facilities/does-not-exist",
        headers={"X-Request-ID": "contract-test-request"},
    )
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "contract-test-request"
    assert "X-Response-Time-Ms" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    body = response.json()
    assert body["code"] == "facility_not_found"
    assert body["request_id"] == "contract-test-request"
    assert body["details"] is None


def test_untrusted_request_ids_are_replaced(openapi_client):
    for candidate in ("bad id with spaces", "x" * 300):
        response = openapi_client.get("/healthz", headers={"X-Request-ID": candidate})
        assert response.status_code == 200
        generated = response.headers["X-Request-ID"]
        assert generated != candidate
        assert len(generated) == 36


def test_invalid_bbox_and_radius_fail_with_structured_errors(openapi_client):
    response = openapi_client.get("/v1/facilities/within", params={"bbox": "not-a-bbox"})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_bbox"

    response = openapi_client.get("/v1/facilities/within", params={"bbox": "116.0,4.0,127.0,22.0"})
    assert response.status_code == 400
    assert response.json()["code"] == "bbox_too_large"
    assert response.json()["details"]["max_area_deg2"] == 25.0

    response = openapi_client.get(
        "/v1/facilities/nearby", params={"lat": 14.6, "lon": 121.0, "radius_m": 50001}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "radius_too_large"


def test_validation_errors_use_the_same_envelope(openapi_client):
    response = openapi_client.get("/v1/facilities", params={"limit": 0})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["request_id"]
    assert isinstance(body["details"], list)


def test_health_and_index_are_public(openapi_client):
    response = openapi_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "philfacilities-api"
    assert response.json()["database"] in {"ok", "unavailable"}

    index = openapi_client.get("/v1").json()
    assert index["resources"]["facilities"] == "/v1/facilities"
    assert "is_synthetic" in index["notice"]
