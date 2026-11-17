"""Scheduling and alerting units for automated source monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = [pytest.mark.integration]


def test_due_source_keys_respect_recorded_next_check(db_session):
    from philfacilities_api.models import SourceCheck
    from philfacilities_ingest.sources.registry import (
        REAL_SOURCES,
        due_source_keys,
        monitored_dataset,
    )

    key = "philhealth"
    dataset = monitored_dataset(db_session, REAL_SOURCES[key])
    now = datetime.now(UTC)
    db_session.add(
        SourceCheck(
            dataset_id=dataset.id,
            checked_at=now,
            status="ok",
            url=REAL_SOURCES[key].source_url,
            next_check_at=now + timedelta(days=7),
        )
    )
    db_session.flush()
    try:
        assert key not in due_source_keys(db_session, keys=[key], now=now)
        assert key in due_source_keys(db_session, keys=[key], now=now, force=True)
        assert key in due_source_keys(db_session, keys=[key], now=now + timedelta(days=8))
    finally:
        db_session.rollback()


def test_update_discovery_modes_are_source_specific():
    from philfacilities_ingest.sources.registry import (
        REAL_SOURCES,
        detect_new_release,
        update_discovery_mode,
    )

    assert update_discovery_mode(REAL_SOURCES["ppa"]) == "file_checksum"
    assert update_discovery_mode(REAL_SOURCES["dti-negosyo"]) == "payload_checksum"
    assert update_discovery_mode(REAL_SOURCES["deped-machine-ready"]) == "manual"
    assert update_discovery_mode(REAL_SOURCES["pagasa-aws"]) == "observations_only"

    assert detect_new_release("file_checksum", "a" * 64, "b" * 64) is True
    assert detect_new_release("payload_checksum", "a" * 64, "a" * 64) is False
    assert detect_new_release("manual", "a" * 64, "b" * 64) is None
    assert detect_new_release("observations_only", "a" * 64, "b" * 64) is None
    assert detect_new_release("file_checksum", None, "b" * 64) is None


def test_source_review_reports_every_registered_source(db_session):
    from philfacilities_ingest.sources.registry import REAL_SOURCES, source_review_rows

    rows = source_review_rows(db_session, days=30)
    assert len(rows) == len(REAL_SOURCES)
    by_key = {row["source_key"]: row for row in rows}
    assert by_key["ppa"]["access_method"] == "public_pdf"
    assert by_key["ppa"]["rights"]
    assert by_key["ppa"]["publication_status"]
    assert isinstance(by_key["ppa"]["review_due"], bool)


def test_actionable_failures_exclude_known_blocks():
    from philfacilities_ingest.acquisition import actionable_failures

    results = {
        "blocked": {"status": "access_blocked"},
        "broken": {"status": "not_found"},
        "unchanged": {"status": "not_modified"},
        "changed": {"status": "schema_changed"},
        "failed": {"status": "request_failed"},
    }
    assert set(actionable_failures(results)) == {"changed", "failed"}


def test_failure_alert_requires_a_webhook_and_sends_actionable_checks(monkeypatch):
    from philfacilities_ingest import acquisition

    sent: list[dict] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url, *, json, timeout):
        sent.append({"url": url, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(acquisition.httpx, "post", fake_post)
    settings = acquisition.IngestSettings(alert_webhook_url="https://alerts.example.invalid/hook")
    results = {"philhealth": {"status": "schema_changed", "error": "header changed"}}
    assert acquisition.send_failure_alert(settings, results, command="source check --due")
    assert sent[0]["url"] == "https://alerts.example.invalid/hook"
    assert sent[0]["json"]["failures"]["philhealth"]["status"] == "schema_changed"

    no_webhook = acquisition.IngestSettings(alert_webhook_url=None)
    assert not acquisition.send_failure_alert(no_webhook, results, command="source check --due")
    assert not acquisition.send_failure_alert(
        settings, {"x": {"status": "access_blocked"}}, command="x"
    )
