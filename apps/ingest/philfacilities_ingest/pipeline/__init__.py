"""Ingestion pipeline package.

The public entry points stay importable from ``philfacilities_ingest.pipeline``
so existing callers do not change. Internally the package is split by
responsibility: release lifecycle, staging, canonical writes, reference-data
writers, the runner, registered statistics, and shared primitives.
"""

from __future__ import annotations

from .canonical import (
    _apply_candidate,
    _flush_new_facilities,
    _maybe_flag_cross_source,
)
from .common import (
    APPLY_FLUSH_BATCH_SIZE,
    IngestResult,
    build_engine,
    session_factory,
)
from .geography import _read_raw, run_geography_ingestion, run_psgc_ingestion
from .locking import IngestionLockError, dataset_ingestion_lock, ingestion_lock_key
from .release import (
    _dataset_is_public,
    _existing_release,
    _record_issues,
    _resolve_open_issues,
    _write_report,
    ensure_source,
)
from .runner import run_ingestion
from .staging import (
    _reconcile_source_record_keys,
    row_count_anomaly,
    stage_source_records,
)
from .stats import DEFAULT_COUNTERS, STAGES, IngestStats, StageTimings

__all__ = [
    "APPLY_FLUSH_BATCH_SIZE",
    "DEFAULT_COUNTERS",
    "STAGES",
    "IngestResult",
    "IngestStats",
    "IngestionLockError",
    "StageTimings",
    "_apply_candidate",
    "_dataset_is_public",
    "_existing_release",
    "_flush_new_facilities",
    "_maybe_flag_cross_source",
    "_read_raw",
    "_reconcile_source_record_keys",
    "_record_issues",
    "_resolve_open_issues",
    "_write_report",
    "build_engine",
    "dataset_ingestion_lock",
    "ensure_source",
    "ingestion_lock_key",
    "row_count_anomaly",
    "run_geography_ingestion",
    "run_ingestion",
    "run_psgc_ingestion",
    "session_factory",
    "stage_source_records",
]
