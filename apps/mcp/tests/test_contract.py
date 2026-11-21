"""Tool calls must stay inside the committed public API contract."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from mcp import Client
from philfacilities_mcp.client import API_ROUTES, DOWNLOAD_PATHS, ApiClient
from philfacilities_mcp.server import create_server
from philfacilities_mcp.settings import McpSettings

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


def _tool_input_schema(name: str) -> dict:
    """Build the in-memory server and return one tool's JSON input schema."""

    async def run() -> dict:
        settings = McpSettings(api_base_url="http://api.test")
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
            base_url=settings.api_base_url,
        ) as http:
            server = create_server(settings=settings, api=ApiClient(settings, http_client=http))
            async with Client(server) as client:
                tools = (await client.list_tools()).tools
                return next(tool.input_schema for tool in tools if tool.name == name)

    return asyncio.run(run())


def test_location_precision_description_lists_every_contract_value():
    """The tool must not invent a second, stale copy of the precision vocabulary."""

    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parameters = document["paths"]["/v1/facilities"]["get"]["parameters"]
    parameter = next(p for p in parameters if p["name"] == "location_precision")
    enum = next(
        variant["enum"]
        for variant in parameter["schema"].get("anyOf", [parameter["schema"]])
        if "enum" in variant
    )

    description = _tool_input_schema("search_facilities")["properties"]["location_precision"][
        "description"
    ]
    assert all(value in description for value in enum), (
        f"location_precision description {description!r} is missing some of {enum}"
    )
