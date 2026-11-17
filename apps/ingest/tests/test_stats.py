"""Unit tests for ingestion statistics and stage timing."""

from __future__ import annotations

import json

from philfacilities_ingest.pipeline.stats import DEFAULT_COUNTERS, IngestStats


def test_stats_start_with_isolated_counters() -> None:
    first = IngestStats()
    second = IngestStats()
    first["precision"]["source_gps"] = 1
    assert second["precision"] == {}
    assert set(DEFAULT_COUNTERS) <= set(first)


def test_stage_timings_accumulate_and_finish() -> None:
    stats = IngestStats()
    stats["parsed_rows"] = 100

    with stats.stage("parse"):
        pass
    stats.start_stage("apply_candidates")
    stats.stop_stage("apply_candidates")
    stats.finish()

    timings = stats["timings_ms"]
    assert timings["parse_ms"] >= 0
    assert timings["apply_candidates_ms"] >= 0
    assert stats["total_ms"] >= timings["parse_ms"]
    assert stats["rows_per_second"] is not None
    assert stats["apply_rows_per_second"] is not None
    json.dumps(stats)  # must remain JSON serializable for JSONB and reports


def test_stage_cannot_be_closed_twice() -> None:
    stats = IngestStats()
    stats.start_stage("parse")
    stats.stop_stage("parse")
    try:
        stats.stop_stage("parse")
    except ValueError as exc:
        assert "was not started" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("closing an unopened stage must fail")
