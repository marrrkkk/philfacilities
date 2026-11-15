"""Discovery probes record reachability without mutating the source register."""

from __future__ import annotations

import httpx
from philfacilities_ingest.acquisition import HttpAcquirer
from philfacilities_ingest.discovery import DiscoveryTarget, probe_discovery_targets


def _target(key: str, url: str) -> DiscoveryTarget:
    return DiscoveryTarget(
        key=key,
        agency="Example agency",
        dataset="Example dataset",
        url=url,
        note="Test-only discovery target.",
    )


def _client(handler) -> HttpAcquirer:
    return HttpAcquirer(transport=httpx.MockTransport(handler), retries=1)


def test_discovery_probe_records_success_and_access_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"<html>official page</html>",
            )
        return httpx.Response(
            403,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html>access blocked</html>",
        )

    results = probe_discovery_targets(
        [
            _target("ok", "https://example.test/ok"),
            _target("blocked", "https://example.test/blocked"),
        ],
        acquirer=_client(handler),
    )

    assert [row["status"] for row in results] == ["ok", "access_blocked"]
    assert results[0]["http_status"] == 200
    assert results[0]["blocker_page"] is False
    assert results[1]["http_status"] == 403
    assert results[1]["blocker_page"] is True
    assert results[1]["error"] is None


def test_discovery_probe_records_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("TLS verification failed", request=request)

    results = probe_discovery_targets(
        [_target("tls", "https://example.test/tls")],
        acquirer=_client(handler),
    )

    assert results[0]["status"] == "request_failed"
    assert results[0]["http_status"] is None
    assert results[0]["blocker_page"] is False
    assert "TLS verification failed" in results[0]["error"]
