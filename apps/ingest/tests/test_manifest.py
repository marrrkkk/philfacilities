"""Release-manifest tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from philfacilities_ingest.cli import app
from philfacilities_ingest.manifest import _canonical_json, build_release_manifest
from typer.testing import CliRunner


def test_manifest_is_deterministic_and_checksummed(db_session):
    generated_at = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    manifest = build_release_manifest(db_session, generated_at=generated_at)

    payload = {key: value for key, value in manifest.items() if key != "checksum"}
    expected = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    assert manifest["manifest_version"] == "1.0"
    assert manifest["generated_at"] == generated_at
    assert manifest["checksum"] == expected
    assert manifest["totals"]["published_facilities"] == 22
    assert manifest["totals"]["datasets_included"] >= 1
    assert isinstance(manifest["excluded_datasets"], list)
    assert all(entry["reason"] for entry in manifest["excluded_datasets"])
    assert all(
        entry["publication_status"] == "published" and entry["source_release"]
        for entry in manifest["datasets"]
    )


def test_release_manifest_cli_writes_a_checksummed_file(db_session, tmp_path):
    output = tmp_path / "release-manifest.json"

    result = CliRunner().invoke(app, ["release-manifest", "--output", str(output)])

    assert result.exit_code == 0, result.output
    written = json.loads(output.read_text())
    assert written["checksum"]
    payload = {key: value for key, value in written.items() if key != "checksum"}
    assert (
        written["checksum"] == hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    )
    assert written["totals"]["published_facilities"] == 22
