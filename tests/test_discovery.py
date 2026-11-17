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


def test_run_source_reports_unexpected_discovery_errors_as_failures(monkeypatch):
    from philfacilities_ingest import source_runner
    from philfacilities_ingest.config import IngestSettings

    class BrokenConnector:
        def discover(self, _ctx):
            raise RuntimeError("connector exploded")

    class RecordingSession:
        def __init__(self):
            self.rolled_back = 0

        def rollback(self):
            self.rolled_back += 1

    monkeypatch.setattr(source_runner, "get_connector", lambda _key: BrokenConnector())

    session = RecordingSession()
    outcomes = source_runner.run_source(
        session=session,
        settings=IngestSettings(),
        key="philhealth",
        acquirer=object(),
    )

    assert len(outcomes) == 1
    payload = outcomes[0].to_dict()
    assert payload["status"] == "failed"
    assert "skip" not in payload
    assert "connector exploded" in payload["error"]
    assert session.rolled_back == 1
