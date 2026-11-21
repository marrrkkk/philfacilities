"""Unit tests for the API client boundary."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from philfacilities_mcp.client import ApiClient
from philfacilities_mcp.settings import McpSettings

SETTINGS = McpSettings(api_base_url="http://api.test", request_timeout_seconds=0.1)


def make_client(handler) -> ApiClient:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=SETTINGS.api_base_url,
    )
    return ApiClient(SETTINGS, http_client=http)


def test_get_forwards_params_and_preserves_nulls():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "abc",
                        "is_synthetic": False,
                        "source_count": 0,
                        "location": {"latitude": None, "precision": "unknown"},
                    }
                ]
            },
        )

    async def run() -> None:
        api = make_client(handler)
        result = await api.get("/v1/facilities", {"q": "school", "limit": 0, "cursor": None})

        assert seen["path"] == "/v1/facilities"
        assert seen["params"] == {"q": "school", "limit": "0"}
        assert result["items"][0]["location"]["latitude"] is None
        assert result["items"][0]["is_synthetic"] is False
        assert result["items"][0]["source_count"] == 0

    asyncio.run(run())


def test_api_error_envelope_becomes_a_readable_tool_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "code": "facility_not_found",
                "message": "No published facility exists with that ID.",
                "details": None,
                "request_id": "req-123",
            },
        )

    async def run() -> None:
        with pytest.raises(ToolError, match="facility_not_found") as caught:
            await make_client(handler).get("/v1/facilities/missing")
        text = str(caught.value)
        assert "No published facility exists" in text
        assert "req-123" in text

    asyncio.run(run())


@pytest.mark.parametrize(
    "exc,expected",
    [
        (httpx.TimeoutException("timed out connecting to http://secret.internal"), "timed out"),
        (httpx.ConnectError("connection failed at http://secret.internal"), "unavailable"),
    ],
)
def test_transport_failures_are_sanitized(exc: Exception, expected: str):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    async def run() -> None:
        with pytest.raises(ToolError) as caught:
            await make_client(handler).get("/v1/facilities")
        text = str(caught.value)
        assert expected in text
        assert "secret.internal" not in text

    asyncio.run(run())


def test_paths_outside_the_public_contract_are_rejected():
    async def run() -> None:
        with pytest.raises(ToolError, match="not exposed"):
            await make_client(lambda _: httpx.Response(200)).get("/v1/quality/match-candidates")

    asyncio.run(run())
