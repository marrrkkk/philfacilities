"""Typed ingestion statistics with per-stage timings.

The ingestion report and ``IngestionRun.stats`` payload used to be an open
dictionary.  This module keeps the dictionary shape that reports and existing
callers rely on, but adds a small typed layer for stage timing so every run
records where its wall time went.

Stages are recorder-based rather than nested: a stage can be started and
stopped around a block without re-indenting the surrounding code, and the same
API is available as a context manager.

Timing semantics:

* A stage's duration is the sum of its recorded intervals.
* ``total_ms`` is wall time from stats creation until :meth:`IngestStats.finish`.
* ``report_ms`` is recorded after the report file has been written, so the
  report file itself contains every stage except the final report write.  The
  database run row receives the complete timing set because it is committed
  after the report finishes.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

# Stage names used by the ingestion runner and the benchmark harness.  Keeping
# them in one place prevents the report, the run row, and the benchmark from
# drifting apart.
STAGES = (
    "fetch",
    "release",
    "parse",
    "validate",
    "normalize",
    "stage_records",
    "apply_candidates",
    "report",
)

DEFAULT_COUNTERS: dict[str, Any] = {
    "input_rows": 0,
    "parsed_rows": 0,
    "normalized_candidates": 0,
    "accepted_rows": 0,
    "rejected_rows": 0,
    "duplicate_source_ids": 0,
    "facilities_created": 0,
    "facilities_updated": 0,
    "unresolved": 0,
    "excluded_rows": 0,
    "with_coordinates": 0,
    "address_only_locations": 0,
    "precision": {},
    "psgc_provided": 0,
    "psgc_matched": 0,
    "enrollment_observations": 0,
    "resource_observations": 0,
    "licenses": 0,
    "accreditations": 0,
    "functions": 0,
    "services": 0,
    "roles": 0,
    "contacts": 0,
    "candidate_matches": 0,
    "reprocess_skipped_unchanged": 0,
}


@dataclass
class StageTimings:
    """Accumulated wall-clock duration per named stage."""

    durations: dict[str, float] = field(default_factory=dict)

    def add(self, stage: str, seconds: float) -> None:
        self.durations[stage] = self.durations.get(stage, 0.0) + seconds

    def as_ms(self) -> dict[str, float]:
        return {
            f"{stage}_ms": round(seconds * 1000.0, 3) for stage, seconds in self.durations.items()
        }


class IngestStats(dict[str, Any]):
    """Dictionary-compatible ingestion counters plus stage timings.

    Subclassing ``dict`` keeps the existing report serialization, JSONB
    storage, and every ``stats["counter"]`` access working unchanged.  New code
    should use :meth:`stage`, :meth:`start_stage`, and :meth:`stop_stage`
    instead of measuring time by hand.
    """

    def __init__(self, **initial: Any) -> None:
        super().__init__({**copy.deepcopy(DEFAULT_COUNTERS), **initial})
        self._started_at = time.perf_counter()
        self._timings = StageTimings()
        self._open_stages: dict[str, float] = {}
        self["timings_ms"] = {}

    def start_stage(self, stage: str) -> None:
        if stage in self._open_stages:
            raise ValueError(f"Stage {stage!r} is already open.")
        self._open_stages[stage] = time.perf_counter()

    def stop_stage(self, stage: str) -> float:
        started = self._open_stages.pop(stage, None)
        if started is None:
            raise ValueError(f"Stage {stage!r} was not started.")
        elapsed = time.perf_counter() - started
        self._timings.add(stage, elapsed)
        self["timings_ms"] = self._timings.as_ms()
        return elapsed

    @contextmanager
    def stage(self, stage: str) -> Iterator[None]:
        self.start_stage(stage)
        try:
            yield
        finally:
            self.stop_stage(stage)

    def finish(self) -> IngestStats:
        """Compute total wall time and derived throughput values."""

        elapsed = time.perf_counter() - self._started_at
        self["timings_ms"] = self._timings.as_ms()
        self["total_ms"] = round(elapsed * 1000.0, 3)
        parsed_rows = int(self.get("parsed_rows") or 0)
        apply_seconds = self._timings.durations.get("apply_candidates", 0.0)
        self["rows_per_second"] = (
            round(parsed_rows / elapsed, 2) if elapsed > 0 and parsed_rows else None
        )
        self["apply_rows_per_second"] = (
            round(parsed_rows / apply_seconds, 2) if apply_seconds > 0 and parsed_rows else None
        )
        return self

    def snapshot(self) -> dict[str, Any]:
        """Return a plain dictionary suitable for JSONB and JSON reports."""

        return dict(self)
