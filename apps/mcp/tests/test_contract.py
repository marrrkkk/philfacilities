"""Tool calls must stay inside the committed public API contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from philfacilities_mcp.client import API_ROUTES, DOWNLOAD_PATHS

pytestmark = pytest.mark.contract

CONTRACT = Path(__file__).resolve().parents[3] / "packages/api-client/openapi.json"

# Every query argument a tool can forward, per endpoint. Adding a tool argument
# without adding it here is a contract error, not a runtime surprise.
QUERY_ARGS = {
    "/v1/facilities": {
        "q",
        "type",
        "subtype",
        "function",
        "inclusion_class",
        "ownership_type",
        "operator_type",
        "public_access_class",
        "region_code",
        "province_code",
        "municipality_code",
        "barangay_code",
        "psgc",
        "source",
        "location_precision",
        "limit",
        "cursor",
    },
    "/v1/facilities/nearby": {"lat", "lon", "radius_m", "q", "type", "limit"},
    "/v1/geographies": {"q", "level", "parent", "release", "limit", "offset"},
    "/v1/population": {"psgc", "level", "indicator", "q", "release_id", "limit", "offset"},
    "/v1/facilities/{facility_id}/assertions": {"attribute", "limit"},
}


def test_all_tool_paths_exist_in_the_openapi_contract():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = set(document["paths"])

    assert set(API_ROUTES.values()) <= paths
    assert set(DOWNLOAD_PATHS.values()) <= paths
    assert "/v1/schools/{facility_id}/enrollment" not in paths


def test_all_tool_query_arguments_exist_in_the_contract():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))

    for path, arguments in QUERY_ARGS.items():
        operation = document["paths"][path]["get"]
        declared = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter["in"] == "query"
        }
        assert arguments <= declared, f"{path} is missing {sorted(arguments - declared)}"


def test_tools_only_use_read_operations():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for path in set(API_ROUTES.values()) | set(DOWNLOAD_PATHS.values()):
        methods = set(document["paths"][path])
        assert methods == {"get"}, f"{path} exposes unexpected methods: {methods}"


def test_no_tool_path_exposes_ingestion_internals():
    for path in API_ROUTES.values():
        assert "quality" not in path
        assert "match-candidates" not in path
        assert "monitoring" not in path
        assert "source-checks" not in path
