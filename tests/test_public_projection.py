"""Unit tests for the hosted public-projection build and verification path."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from scripts import build_public_projection as build
from scripts import verify_public_projection as verify


def test_database_url_helpers() -> None:
    url = "postgresql+psycopg://user:pass@localhost:54329/philfacilities"
    assert (
        build.normalise_database_url(url) == "postgresql://user:pass@localhost:54329/philfacilities"
    )
    assert build.admin_database_url(url) == "postgresql://user:pass@localhost:54329/postgres"
    assert build.scratch_database_url(url, "scratch_test") == (
        "postgresql://user:pass@localhost:54329/scratch_test"
    )


def test_projection_contains_evidence_and_excludes_provenance() -> None:
    assert "source.records" in build.TABLE_ORDER
    assert "source.facility_source_links" in build.TABLE_ORDER
    assert "core.facility_locations" in build.TABLE_ORDER
    for table in build.OMITTED_TABLES:
        assert table not in build.TABLE_ORDER


def test_public_filters() -> None:
    assert build.table_filter("core.facilities") == "src.publication_status = 'public'"
    assert "is_current IS TRUE" in (build.table_filter("core.facility_locations") or "")
    assert "publication_status = 'public'" in (build.table_filter("school.profiles") or "")
    assert build.table_filter("source.agencies") is None


def test_dump_includes_all_migration_schemas() -> None:
    command = build._dump_command("scratch_test")
    assert "--schema" in command
    assert "history" in command
    assert "core" in command


def test_record_reference_query_is_set_based() -> None:
    query = build.record_reference_query("src.id")
    assert "publication_status = 'public'" in query
    assert "stats.population_observations" in query
    assert "JOIN referenced r ON r.id = src.id" in query
    assert query.count("UNION") == len(build.RECORD_REFERENCE_TABLES) - 1


def test_select_expression_strips_provenance() -> None:
    assert build.select_expression("source.records", "raw_payload") == "'{}'::jsonb"
    assert build.select_expression("source.records", "id") == 'src."id"'
    assert build.select_expression("source.facility_source_links", "evidence") == "NULL"
    assert build.select_expression("source.facility_source_links", "match_status") == (
        'src."match_status"'
    )


def test_manifest_counts_and_checksum(tmp_path: Any) -> None:
    dump = tmp_path / "public-test.dump"
    dump.write_bytes(b"public projection bytes")
    manifest = build.build_manifest(
        source_db="philfacilities",
        revision="0026_api_field_coverage_mv",
        dump_path=dump,
        counts={"core.facilities": 229274},
        by_category={"school": 120000},
        postgres_version="18.4",
    )
    assert manifest["sha256"] == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert manifest["bytes"] == len(dump.read_bytes())
    assert manifest["counts"]["core.facilities"] == 229274
    assert manifest["source_revision"] == "0026_api_field_coverage_mv"


def test_checksum_verification(tmp_path: Any) -> None:
    dump = tmp_path / "public-test.dump"
    dump.write_bytes(b"abc")
    manifest = {"sha256": hashlib.sha256(b"abc").hexdigest()}
    assert verify.verify_checksum(dump, manifest) == []
    assert verify.verify_checksum(dump, {"sha256": "bad"}) != []


def _manifest() -> dict:
    return {
        "format_version": 1,
        "counts": {"core.facilities": 2},
    }


def _ok(path: str) -> tuple[int, dict[str, Any], float]:
    if path == "/healthz":
        return 200, {"status": "ok", "database": "ok"}, 0.01
    if path == "/v1/statistics":
        return 200, {"by_category": {"school": 1, "health_facility": 1}}, 0.02
    if path == "/v1/facilities?limit=1":
        return 200, {"items": [{"id": "facility-1", "slug": "one"}]}, 0.02
    if path == "/v1/facilities/facility-1":
        return 200, {"id": "facility-1"}, 0.02
    if path == "/v1/fields":
        return 200, {"fields": []}, 0.05
    if path == "/mcp/readyz":
        return 200, {"status": "ok"}, 0.01
    raise AssertionError(f"unexpected path {path}")


def test_check_api_passes_for_healthy_projection() -> None:
    assert verify.check_api(manifest=_manifest(), get=_ok) == []


def test_check_api_catches_detail_404() -> None:
    def get(path: str) -> tuple[int, dict[str, Any], float]:
        if path == "/v1/facilities/facility-1":
            return 404, {}, 0.02
        return _ok(path)

    failures = verify.check_api(manifest=_manifest(), get=get)
    assert any("facility detail returned 404" in failure for failure in failures)


def test_check_api_catches_count_drift() -> None:
    def get(path: str) -> tuple[int, dict[str, Any], float]:
        if path == "/v1/statistics":
            return 200, {"by_category": {"school": 1}}, 0.02
        return _ok(path)

    failures = verify.check_api(manifest=_manifest(), get=get)
    assert any("!= manifest" in failure for failure in failures)


def test_check_api_catches_slow_fields() -> None:
    def get(path: str) -> tuple[int, dict[str, Any], float]:
        if path == "/v1/fields":
            return 200, {}, 25.0
        return _ok(path)

    failures = verify.check_api(manifest=_manifest(), get=get)
    assert any("/v1/fields took" in failure for failure in failures)


def test_manifest_file_is_valid_json(tmp_path: Any) -> None:
    manifest = _manifest()
    path = tmp_path / "public-test.manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == manifest
