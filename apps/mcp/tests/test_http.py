"""Streamable HTTP transport and operational endpoints."""

from __future__ import annotations

import httpx
from philfacilities_mcp.client import ApiClient
from philfacilities_mcp.http import create_http_app
from philfacilities_mcp.settings import McpSettings
from starlette.testclient import TestClient

SETTINGS = McpSettings(
    api_base_url="http://api.test",
    mcp_host="testserver",
    mcp_allowed_hosts="testserver",
)

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2026-07-28",
        "capabilities": {},
        "clientInfo": {"name": "contract-test", "version": "1.0"},
    },
}


def app_with(handler) -> TestClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=SETTINGS.api_base_url)
    api = ApiClient(SETTINGS, http_client=http)
    return TestClient(create_http_app(settings=SETTINGS, api=api))


def test_health_endpoint():
    with app_with(lambda _: httpx.Response(200, json={})) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "philfacilities-mcp"


def test_ready_endpoint_reflects_api_health():
    with app_with(lambda _: httpx.Response(200, json={"status": "ok", "database": "ok"})) as client:
        response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_ready_endpoint_fails_closed_when_api_is_unreachable():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"code": "unavailable", "message": "down"})

    with app_with(handler) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_stateless_json_rpc_handshake_and_tool_listing():
    with app_with(lambda _: httpx.Response(200, json={})) as client:
        initialized = client.post("/mcp", json=INITIALIZE)
        assert initialized.status_code == 200, initialized.text
        payload = initialized.json()
        assert payload["result"]["serverInfo"]["name"] == "philfacilities"

        listed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200, listed.text
        names = {tool["name"] for tool in listed.json()["result"]["tools"]}
        assert "search_facilities" in names
        assert "get_coverage" in names


def test_unknown_host_is_rejected():
    with app_with(lambda _: httpx.Response(200, json={})) as client:
        response = client.post("/mcp", json=INITIALIZE, headers={"host": "evil.example"})
    assert response.status_code == 421


def test_custom_streamable_path_supports_mounting_under_a_prefix():
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
        base_url=SETTINGS.api_base_url,
    )
    api = ApiClient(SETTINGS, http_client=http)
    http_app = create_http_app(settings=SETTINGS, api=api, streamable_http_path="/")
    with TestClient(http_app) as client:
        response = client.post("/", json=INITIALIZE)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "philfacilities"
