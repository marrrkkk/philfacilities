"""The MCP adapter is served by the API process without a second service."""

from __future__ import annotations

from fastapi.testclient import TestClient
from philfacilities_api.main import app

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2026-07-28",
        "capabilities": {},
        "clientInfo": {"name": "mount-test", "version": "1.0"},
    },
}


def mounted_client() -> TestClient:
    # The default MCP Host allowlist accepts 127.0.0.1:*, so use that origin.
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_mcp_is_reachable_from_the_api_app():
    with mounted_client() as client:
        response = client.post("/mcp", json=INITIALIZE)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "philfacilities"


def test_api_health_route_is_not_shadowed_by_the_mount():
    with mounted_client() as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "philfacilities-api"


def test_unknown_path_keeps_the_api_error_envelope():
    with mounted_client() as client:
        response = client.get("/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_mcp_host_validation_still_applies_when_mounted():
    with mounted_client() as client:
        response = client.post("/mcp", json=INITIALIZE, headers={"host": "evil.example"})
    assert response.status_code == 421
