"""Protocol-level tests: the tool surface and its data-integrity behaviour."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import Client
from philfacilities_mcp.client import ApiClient
from philfacilities_mcp.server import create_server
from philfacilities_mcp.settings import McpSettings

EXPECTED_TOOLS = {
    "search_facilities",
    "get_facility",
    "get_facility_provenance",
    "find_nearby_facilities",
    "search_geographies",
    "get_population",
    "get_sources",
    "get_coverage",
    "get_taxonomy",
    "get_download_links",
}

SETTINGS = McpSettings(api_base_url="http://api.test")


@asynccontextmanager
async def server_with(handler):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=SETTINGS.api_base_url,
    ) as http:
        yield create_server(settings=SETTINGS, api=ApiClient(SETTINGS, http_client=http))


def test_tool_surface_is_curated_and_read_only():
    async def run() -> None:
        async with (
            server_with(lambda _: httpx.Response(200, json={})) as server,
            Client(server) as client,
        ):
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} == EXPECTED_TOOLS
            assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools)
            assert client.instructions
            assert "null means unknown" in client.instructions
            assert "evidence of current operational status" in client.instructions

    asyncio.run(run())


def test_search_forwards_filters_and_returns_api_json_unchanged():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "fac-1",
                        "display_name": "Synthetic Demo School 01",
                        "is_synthetic": True,
                        "source_count": 1,
                        "location": {"latitude": None, "longitude": None, "precision": "unknown"},
                    }
                ],
                "total": 1,
                "has_more": False,
                "next_cursor": None,
                "limit": 20,
            },
        )

    async def run() -> None:
        async with server_with(handler) as server, Client(server) as client:
            result = await client.call_tool(
                "search_facilities",
                {"q": "demo", "province_code": "9901000000", "limit": 20},
            )
        assert seen["path"] == "/v1/facilities"
        assert seen["params"] == {"q": "demo", "province_code": "9901000000", "limit": "20"}
        payload = result.structured_content["result"]
        assert payload["items"][0]["is_synthetic"] is True
        assert payload["items"][0]["location"]["latitude"] is None
        assert payload["next_cursor"] is None

    asyncio.run(run())


def test_provenance_merges_sources_and_field_assertions():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        params = dict(request.url.params)
        if request.url.path.endswith("/sources"):
            return httpx.Response(200, json=[{"agency": "DepEd", "attribution_text": None}])
        assert params == {"attribute": "name", "limit": "25"}
        return httpx.Response(200, json=[{"attribute": "name", "raw_value": None}])

    async def run() -> None:
        async with server_with(handler) as server, Client(server) as client:
            result = await client.call_tool(
                "get_facility_provenance",
                {"facility_id": "fac-1", "attribute": "name", "limit": 25},
            )
        assert calls == [
            "/v1/facilities/fac-1/sources",
            "/v1/facilities/fac-1/assertions",
        ]
        payload = result.structured_content["result"]
        assert payload["facility_id"] == "fac-1"
        assert payload["sources"][0]["attribution_text"] is None
        assert payload["assertions"][0]["raw_value"] is None

    asyncio.run(run())


def test_api_not_found_is_an_anticipated_tool_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "code": "facility_not_found",
                "message": "No published facility exists with that ID.",
                "details": None,
                "request_id": "req-404",
            },
        )

    async def run() -> None:
        async with server_with(handler) as server, Client(server) as client:
            result = await client.call_tool("get_facility", {"facility_id": "missing"})
        assert result.is_error is True
        assert "facility_not_found" in result.content[0].text
        assert "req-404" in result.content[0].text

    asyncio.run(run())


def test_download_links_require_no_api_call():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("get_download_links must not call the API")

    async def run() -> None:
        async with server_with(handler) as server, Client(server) as client:
            result = await client.call_tool("get_download_links", {})
        downloads = result.structured_content["result"]["downloads"]
        assert len(downloads) == 4
        assert downloads["facilities_parquet"] == "/v1/downloads/facilities.parquet"

    asyncio.run(run())


@pytest.mark.parametrize(
    "tool,path,body",
    [
        ("get_sources", "/v1/sources", [{"id": "ds-1", "name": "DepEd"}]),
        ("search_geographies", "/v1/geographies", [{"psgc_code": "1300000000"}]),
    ],
)
def test_array_endpoints_keep_their_payload_under_result(tool, path, body):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=body)

    async def run() -> None:
        async with (
            server_with(handler) as server,
            Client(server) as client,
        ):
            result = await client.call_tool(tool, {})
        assert seen["path"] == path
        assert result.is_error is False
        assert result.structured_content["result"] == body

    asyncio.run(run())


def test_invalid_arguments_are_rejected_by_the_input_schema():
    async def run() -> None:
        async with (
            server_with(lambda _: httpx.Response(200, json={})) as server,
            Client(server) as client,
        ):
            result = await client.call_tool("search_facilities", {"limit": 0})
        assert result.is_error is True

    asyncio.run(run())
