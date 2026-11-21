"""Public API contract checks that do not require database rows."""

from __future__ import annotations

import json

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
    "/v1/schools/{facility_id}/resources",
    "/v1/fields",
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
    assert "/v1/schools/{facility_id}/enrollment" not in paths
    assert "EnrollmentObservationOut" not in document["components"]["schemas"]

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
    assert facility_summary["source_refs"]["items"]["$ref"].endswith("SourceRefOut")
    assert facility_summary["location"]["$ref"].endswith("LocationOut")


def test_interactive_docs_render_the_openapi_contract(openapi_client):
    docs = openapi_client.get("/docs")
    assert docs.status_code == 200
    assert "scalar" in docs.text.lower()
    assert "/openapi.json" in docs.text
    assert "#0038a8" in docs.text  # design-system primary token
    assert "#2b2b2b" in docs.text  # dark-mode code surface
    assert "--scalar-radius: 0px" in docs.text
    assert ".light-mode.light-mode" in docs.text  # outranks Scalar's own theme CSS
    assert ".scalar-code-block" in docs.text
    assert "forceDarkModeState" not in docs.text
    assert "/docs" not in openapi_client.get("/openapi.json").json()["paths"]


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
    # Discovery links must not drift as endpoints are added.
    assert index["resources"]["taxonomy"] == "/v1/taxonomy"
    assert index["resources"]["statistics"] == "/v1/statistics"
    assert index["resources"]["category_counts"].startswith("/v1/statistics")
    assert index["resources"]["fields"] == "/v1/fields"
    assert "is_synthetic" in index["notice"]


def test_index_description_states_category_breadth(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    description = document["info"]["description"]
    assert "16 categories" in description
    assert "/v1/taxonomy" in description


def test_field_coverage_is_a_documented_read_only_endpoint(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    operation = document["paths"]["/v1/fields"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "FieldCoverageResponse"
    )
    assert {"by_category"} <= {parameter["name"] for parameter in operation.get("parameters", [])}
    entry = document["components"]["schemas"]["FieldCoverageEntry"]["properties"]
    assert {"field", "scope", "populated", "total", "fill_ratio", "semantics"} <= set(entry)
    assert set(entry["scope"]["enum"]) == {
        "summary",
        "detail",
        "profile_school",
        "profile_health",
        "profile_utility",
    }


def _assert_flat_error(response, expected_status: int) -> dict:
    assert response.status_code == expected_status, response.text
    body = response.json()
    assert set(body) == {"code", "message", "details", "request_id"}
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert response.headers["X-Request-ID"] == "contract-request-id"
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


@pytest.mark.parametrize(
    ("path", "params", "expected_status", "expected_code"),
    [
        ("/v1/does-not-exist", {}, 404, "not_found"),
        ("/v1/facilities/within", {"bbox": "not-a-bbox"}, 400, "invalid_bbox"),
        ("/v1/facilities", {"limit": 0}, 422, "validation_error"),
    ],
)
def test_error_envelope_is_flat_on_400_404_and_422(
    openapi_client, path, params, expected_status, expected_code
):
    response = openapi_client.get(
        path, params=params, headers={"X-Request-ID": "contract-request-id"}
    )
    assert _assert_flat_error(response, expected_status)["code"] == expected_code


def test_error_envelope_is_flat_on_429_and_500():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from philfacilities_api.middleware import (
        RateLimitMiddleware,
        RequestContextMiddleware,
        install_error_handlers,
    )

    limited = FastAPI()

    @limited.get("/probe")
    def probe():
        return {"ok": True}

    limited.add_middleware(RateLimitMiddleware, limit=1)
    limited.add_middleware(RequestContextMiddleware)
    install_error_handlers(limited)
    with TestClient(limited, raise_server_exceptions=False) as client:
        client.get("/probe")
        limited_response = client.get("/probe", headers={"X-Request-ID": "contract-request-id"})
    assert _assert_flat_error(limited_response, 429)["code"] == "rate_limit_exceeded"
    assert "Retry-After" in limited_response.headers
    assert limited_response.headers["X-RateLimit-Limit"] == "1"
    assert limited_response.headers["X-RateLimit-Remaining"] == "0"

    failing = FastAPI()

    @failing.get("/boom")
    def boom():
        raise RuntimeError("test-only failure")

    failing.add_middleware(RequestContextMiddleware)
    install_error_handlers(failing)
    with TestClient(failing, raise_server_exceptions=False) as client:
        failing_response = client.get("/boom", headers={"X-Request-ID": "contract-request-id"})
    assert _assert_flat_error(failing_response, 500)["code"] == "internal_error"


def test_openapi_error_responses_reference_the_flat_schema(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    error_schema = document["components"]["schemas"]["ErrorBody"]
    assert set(error_schema["properties"]) == {"code", "message", "details", "request_id"}
    detail = document["paths"]["/v1/facilities"]["get"]["responses"]
    for status in ("400", "404", "422", "429", "500"):
        reference = detail[status]["content"]["application/json"]["schema"]["$ref"]
        assert reference == "#/components/schemas/ErrorBody"


def test_list_endpoints_document_total_false(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    for path in (
        "/v1/facilities",
        "/v1/schools",
        "/v1/health-facilities",
        "/v1/geographies/{psgc_code}/facilities",
    ):
        parameters = {p["name"] for p in document["paths"][path]["get"]["parameters"]}
        assert "total" in parameters
        if path == "/v1/facilities":
            assert "view" in parameters


def test_response_schemas_carry_synthetic_examples(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]
    for name in ("FacilitySummary", "FacilityDetail", "FacilityCompact", "FacilityMapPoint"):
        examples = schemas[name].get("examples")
        assert examples and "Synthetic" in json.dumps(examples[0])
    detail_example = schemas["FacilityDetail"]["examples"][0]
    assert detail_example["school"] is None
    assert detail_example["relationships"] == []
    compact_example = schemas["FacilityCompact"]["examples"][0]
    assert compact_example["name"] == compact_example["display_name"]
    assert len(compact_example) == 12
    error_examples = schemas["ErrorBody"]["examples"]
    assert {example["code"] for example in error_examples} >= {
        "validation_error",
        "invalid_bbox",
        "facility_not_found",
        "rate_limit_exceeded",
    }
    notes = document["paths"]["/v1/facilities"]["get"]["description"]
    assert all(
        phrase in notes for phrase in ("Publication gate", "Freshness", "Coordinates", "/v1/fields")
    )


def test_domain_details_document_unified_shapes(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    for path in ("/v1/schools/{facility_id}", "/v1/health-facilities/{facility_id}"):
        operation = document["paths"][path]["get"]
        parameters = {parameter["name"] for parameter in operation.get("parameters", [])}
        assert {"view", "shape", "include"} <= parameters
    assert "FacilityCompactExtended" in document["components"]["schemas"]
    resources = document["paths"]["/v1/schools/{facility_id}/resources"]["get"]
    assert "currently empty" in resources["description"].lower()


def test_filtered_downloads_document_list_filters(openapi_client):
    document = openapi_client.get("/openapi.json").json()
    for path in ("/v1/downloads/facilities.csv", "/v1/downloads/facilities.parquet"):
        parameters = {p["name"] for p in document["paths"][path]["get"]["parameters"]}
        assert {
            "type",
            "facility_type",
            "subtype",
            "psgc",
            "region_code",
            "province_code",
            "municipality_code",
            "source",
            "has_coordinates",
            "location_precision",
            "reference_period_start",
            "reference_period_end",
            "q",
        } <= parameters


def test_documented_error_example_matches_a_real_422_response(openapi_client):
    """Prose cannot drift again: the fenced example must be the runtime shape."""

    import json
    import re
    from pathlib import Path

    api_doc = (Path(__file__).resolve().parents[1] / "docs/api.md").read_text(encoding="utf-8")
    errors_section = api_doc.split("## 8. Errors", 1)[1]
    example = json.loads(re.search(r"```json\n(.*?)\n```", errors_section, re.S).group(1))
    actual = openapi_client.get("/v1/facilities", params={"limit": 0}).json()
    assert set(example) == set(actual)
    assert example["code"] == actual["code"]
    assert example["message"] == actual["message"]


def test_conditional_responses_have_an_empty_framed_body(openapi_client):
    """A 304 must carry no body; a stray payload breaks keep-alive framing.

    JSONResponse(status_code=304, content=None) serializes ``null``, which makes
    uvicorn raise "Response content longer than Content-Length" and leaves the
    connection unusable for the next streaming response.
    """

    first = openapi_client.get("/v1/taxonomy")
    assert first.status_code == 200
    etag = first.headers["etag"]

    second = openapi_client.get("/v1/taxonomy", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["content-length"] == "0"
    assert second.headers["etag"] == etag
