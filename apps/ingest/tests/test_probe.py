"""Fresh probe ledger: one request per URL, failures preserved."""

from __future__ import annotations

import json

import httpx
from philfacilities_ingest.probe import (
    ProbeTarget,
    collect_targets,
    probe_targets,
)
from philfacilities_ingest.source_inventory import parse_probes


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_probe_writes_rich_and_text_ledgers(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/missing":
            return httpx.Response(404, text="not found", headers={"content-type": "text/html"})
        if request.url.path == "/blocked":
            return httpx.Response(403, text="Access denied", headers={"content-type": "text/html"})
        if request.url.path == "/challenge":
            return httpx.Response(
                200,
                text="<html><title>Just a moment...</title>cf-chl-</html>",
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200, text="ok", headers={"content-type": "text/plain", "content-length": "2"}
        )

    targets = [
        ProbeTarget(key="ok.source", url="https://example.gov.ph/ok"),
        ProbeTarget(key="missing.source", url="https://example.gov.ph/missing"),
        ProbeTarget(key="blocked.source", url="https://example.gov.ph/blocked"),
        ProbeTarget(key="challenge.source", url="https://example.gov.ph/challenge"),
    ]
    summary = probe_targets(
        targets,
        output_dir=tmp_path,
        delay_seconds=0,
        client=_client(handler),
    )
    assert summary["targets"] == 4
    assert summary["by_outcome"] == {
        "HTTP_200": 1,
        "HTTP_403": 1,
        "HTTP_404": 1,
        "WAF_CHALLENGE": 1,
    }

    rows = [
        json.loads(line)
        for line in (tmp_path / "probe-ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 4
    by_key = {row["key"]: row for row in rows}
    assert by_key["missing.source"]["skip_reason"] == "HTTP_404"
    assert by_key["blocked.source"]["challenge_detected"] is True
    assert by_key["challenge.source"]["challenge_detected"] is True
    assert by_key["ok.source"]["skip_reason"] is None

    text_path = summary["text_ledger"]
    observations = parse_probes(text_path)
    assert len(observations) == 4
    assert {observation.status_code for observation in observations} == {200, 403, 404}


def test_transport_failure_is_kept_not_hidden(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    summary = probe_targets(
        [ProbeTarget(key="dns.source", url="https://does-not-resolve.example/")],
        output_dir=tmp_path,
        delay_seconds=0,
        client=_client(handler),
    )
    assert summary["by_outcome"] == {"TRANSPORT_ERROR": 1}
    row = json.loads((tmp_path / "probe-ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["skip_reason"] == "NO_PUBLIC_RELEASE"
    assert row["error"]
    assert "TRANSPORT_ERROR" in (tmp_path / summary["text_ledger"].rsplit("/", 1)[-1]).read_text(
        encoding="utf-8"
    )


def test_probe_preserves_prior_ledgers(tmp_path):
    (tmp_path / "probe-ledger.jsonl").write_text('{"old": true}\n', encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    summary = probe_targets(
        [ProbeTarget(key="ok.source", url="https://example.gov.ph/ok")],
        output_dir=tmp_path,
        delay_seconds=0,
        client=_client(handler),
    )
    backups = list(tmp_path.glob("probe-ledger-*.jsonl"))
    assert any('"old": true' in path.read_text(encoding="utf-8") for path in backups)
    assert summary["text_ledger"].endswith(".txt")
    assert (tmp_path / "probe-ledger.jsonl").exists()


def test_collect_targets_deduplicates_registered_and_candidate_urls():
    targets = collect_targets(include_candidates=True, include_register=True)
    urls = [target.url for target in targets]
    assert len(urls) == len(set(urls))
    assert any(target.origin == "registered" for target in targets)
    assert any(target.origin == "candidate" for target in targets)
    assert all(target.key for target in targets)
