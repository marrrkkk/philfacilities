#!/usr/bin/env python
"""Replay preserved source artifacts through the ingestion stages.

The harness measures the three acceptance workloads without touching the live
database unless ``--full-write`` is supplied:

* ``ebeis``      — preserved DepEd EBEIS masterlist HTML pages
* ``osm``        — preserved HOT/OSM GeoParquet layers
* ``philhealth`` — preserved PhilHealth provider-category PDFs

Default mode is a read-only replay of ``parse -> validate -> normalize``.  It
records per-stage wall time, source/candidate counts, and peak RSS.  Full-write
mode additionally runs the canonical apply path against a scratch database and
records SQL statement counts.

Examples::

    uv run python scripts/ingest_benchmark.py --workload ebeis --json
    uv run python scripts/ingest_benchmark.py --workload osm --json
    uv run python scripts/ingest_benchmark.py --workload philhealth --json
    uv run python scripts/ingest_benchmark.py --workload ebeis --full-write \
        --database-url postgresql+psycopg://.../philfacilities_bench --migrate

Safety: full-write mode refuses any database whose name does not end in
``_bench`` or ``_test``.  It never truncates a database; start from a fresh
scratch database for a true first-load baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import resource
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_ROOTS = (ROOT / "var" / "raw", ROOT / "apps" / "ingest" / "var" / "raw")
OUTPUT_DIR = ROOT / "docs" / "operations" / "evidence" / "2026-11-16-ingest-performance"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _peak_rss_mb() -> float:
    """Return process peak RSS in MiB (Linux reports KiB via ru_maxrss)."""

    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)


def _database_name(url: str) -> str:
    return urlparse(url.replace("+psycopg", "")).path.lstrip("/")


def _scratch_database(url: str) -> None:
    name = _database_name(url)
    if not name.endswith(("_bench", "_test")):
        raise SystemExit(
            "Refusing a destructive benchmark database: the name must end with "
            f"'_bench' or '_test' (got {name!r})."
        )


@dataclass
class WorkloadFile:
    path: Path
    source_key: str
    adapter_factory: Callable[[Any], Any]
    release_label: str
    dataset_slug: str | None = None
    dataset_name: str | None = None
    layer: str | None = None
    domain: str | None = None


@dataclass
class FileResult:
    path: str
    filename: str
    status: str
    bytes: int
    parsed_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    candidates: int = 0
    issues: int = 0
    warnings: int = 0
    parse_ms: float = 0.0
    validate_ms: float = 0.0
    normalize_ms: float = 0.0
    full_write_ms: float = 0.0
    total_ms: float = 0.0
    peak_rss_mb: float = 0.0
    sql_statements: int = 0
    sql_time_ms: float = 0.0
    fingerprint: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _parse_fingerprint(parsed: Any, candidates: list[Any]) -> str:
    """Hash the source-record keys and normalized candidate identity.

    Two parser versions are output-equivalent when this fingerprint matches:
    the same rows produce the same source keys and the same number/identity of
    normalized candidates. Raw timestamps and UUIDs are excluded.
    """

    import hashlib

    payload = {
        "source_record_keys": sorted(row.source_record_key for row in parsed.rows),
        "candidate_keys": sorted(candidate.source_record_key for candidate in candidates),
        "candidates": len(candidates),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _discover(workload: str, input_path: Path | None) -> list[Path]:
    suffixes = {"ebeis": "*.html", "osm": "*.parquet", "philhealth": "*.pdf"}[workload]
    if input_path is not None:
        if input_path.is_file():
            return [input_path]
        if not input_path.is_dir():
            raise SystemExit(f"Input path does not exist: {input_path}")
        roots = [input_path]
    else:
        roots = [root for root in DEFAULT_RAW_ROOTS if root.exists()]
    files: list[Path] = []
    for root in roots:
        files.extend(root.rglob(suffixes))
    if workload == "ebeis":
        files = [path for path in files if "ebeis" in path.name.lower()]
    elif workload == "osm":
        # The PBF-derived Parquet is a different schema and is benchmarked
        # separately; the acceptance workload is the HOT/OSM GeoParquet layers.
        files = [path for path in files if "pbf" not in path.name.lower() and "/osm/" in str(path)]
    elif workload == "philhealth":
        # Synthetic fixture PDFs are not part of the acquisition baseline, and
        # other agencies' PDFs must not be misread by the PhilHealth parser.
        files = [
            path
            for path in files
            if "philhealth" in str(path).lower() and "synthetic" not in path.name.lower()
        ]
    return _latest_release_per_group(sorted(set(files)), workload)


_EBEIS_NAME = re.compile(
    r"deped-ebeis-masterlist-(?P<region>.+)-(?P<date>\d{4}-\d{2}-\d{2})\.html$",
    re.IGNORECASE,
)
_CHECKSUM_PREFIX = re.compile(r"^[0-9a-f]{16}-", re.IGNORECASE)
_FULL_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_PHILHEALTH_DATE = re.compile(r"_(\d{2})(\d{2})(\d{2})(?:\.[^.]+)?$")


def _release_group(path: Path, workload: str) -> str:
    """Return the dataset identity a preserved artifact belongs to."""

    name = _CHECKSUM_PREFIX.sub("", path.name)
    if workload == "ebeis":
        match = _EBEIS_NAME.match(name)
        if match:
            return match.group("region").lower()
    elif workload == "osm":
        return name.rsplit(".", 1)[0].lower()
    elif workload == "philhealth":
        return name.lower()
    return name.lower()


def _release_date(path: Path, workload: str) -> str:
    """Return a sortable release date from the path or filename."""

    dates = _FULL_DATE.findall(str(path))
    if dates:
        return max(dates)
    if workload == "philhealth":
        match = _PHILHEALTH_DATE.search(path.name)
        if match:
            month, day, year = match.groups()
            return f"20{year}-{month}-{day}"
    return ""


def _latest_release_per_group(files: list[Path], workload: str) -> list[Path]:
    """Keep one current artifact per dataset.

    Preserved raw storage is append-only, so an acquisition history contains
    older snapshots of the same region or OSM layer.  A first-load benchmark
    must replay the current release once, not every historical copy.  Without
    this filter two stale NCR pages are applied after the current NCR release
    and measure the update path instead of the first-load path.
    """

    latest: dict[str, tuple[str, str, Path]] = {}
    for path in files:
        group = _release_group(path, workload)
        candidate = (_release_date(path, workload), str(path), path)
        current = latest.get(group)
        if current is None or candidate[:2] > current[:2]:
            latest[group] = candidate
    return sorted((entry[2] for entry in latest.values()), key=lambda path: path.name.lower())


def _release_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _build_spec(workload: str, path: Path, run_token: str):

    from philfacilities_ingest.sources.registry import REAL_SOURCES, source_spec

    content = _read(path)
    if workload == "ebeis":
        source = REAL_SOURCES["deped-ebeis"]
        return (
            source_spec(
                source,
                release_label=f"BENCH-EBEIS-{path.stem.upper()}-{run_token}",
                filename=path.name,
                content=content,
                retrieved_at=_utc_now(),
                enqueue_cross_source_matches=False,
                notes="Benchmark replay of a preserved EBEIS masterlist page.",
            ),
            None,
        )
    if workload == "osm":
        key, layer = _osm_identity(path.name)
        source = REAL_SOURCES[key]
        return (
            source_spec(
                source,
                release_label=f"BENCH-OSM-{path.stem.upper()}-{run_token}",
                filename=path.name,
                content=content,
                retrieved_at=_utc_now(),
                enqueue_cross_source_matches=False,
                notes="Benchmark replay of a preserved HOT/OSM GeoParquet layer.",
            ),
            layer,
        )
    if workload == "philhealth":
        stem = path.name.split("-", 1)[-1].rsplit(".", 1)[0]
        slug = "".join(character if character.isalnum() else "-" for character in stem.lower())
        slug = "-".join(part for part in slug.split("-") if part) or "provider"
        source = REAL_SOURCES["philhealth"]
        return (
            source_spec(
                source,
                dataset_slug=f"philhealth-{slug}",
                dataset_name=f"PhilHealth — {stem}",
                release_label=f"BENCH-PHILHEALTH-{stem.upper()}-{run_token}",
                filename=path.name,
                content=content,
                retrieved_at=_utc_now(),
                reference_period_start=datetime.now(UTC).date(),
                reference_period_end=datetime.now(UTC).date(),
                enqueue_cross_source_matches=False,
                notes="Benchmark replay of a preserved PhilHealth provider PDF.",
            ),
            None,
        )
    raise ValueError(f"Unknown workload {workload!r}")


def _osm_identity(filename: str) -> tuple[str, str | None]:
    lower = filename.lower()
    if "health" in lower:
        return "osm-health", "health"
    if "education" in lower:
        return "osm-education", "education"
    layer_map = {
        "points_of_interest": ("osm-points-of-interest", "points-of-interest"),
        "airports": ("osm-airports", "airports"),
        "sea_ports": ("osm-sea-ports", "sea-ports"),
        "railways": ("osm-railways", "railways"),
    }
    for marker, (key, layer) in layer_map.items():
        if marker in lower:
            return key, layer
    return "osm-points-of-interest", "points-of-interest"


def _make_adapter(workload: str, spec, layer: str | None):
    if workload == "ebeis":
        from philfacilities_ingest.sources.deped_ebeis import DepEdEBEISAdapter

        return DepEdEBEISAdapter(spec)
    if workload == "osm":
        if layer in {"health", "education"}:
            from philfacilities_ingest.sources.bettergov import OSMParquetAdapter

            return OSMParquetAdapter(spec, facility_domain=layer)
        from philfacilities_ingest.sources.osm_facilities import OsmFacilityLayerAdapter

        return OsmFacilityLayerAdapter(spec, layer=layer or "points-of-interest")
    if workload == "philhealth":
        from philfacilities_ingest.sources.philhealth import PhilHealthPdfAdapter

        return PhilHealthPdfAdapter(spec, provider_category=_philhealth_category(spec.filename))
    raise ValueError(f"Unknown workload {workload!r}")


def _philhealth_category(filename: str) -> str:
    stem = filename.split("-", 1)[-1].rsplit(".", 1)[0].upper()
    token = stem.split("_", 1)[0]
    categories = {
        "HOSP": "Hospital",
        "EMCB-LAB": "Laboratory",
        "EMCB-TVU": "Laboratory",
        "EMCB-PUTZ": "Laboratory",
        "EMCB-ANTE": "Laboratory",
        "EMCB-PPARTUM": "Laboratory",
        "OPTO": "Optical",
        "DENTAL": "Dental",
        "CIU": "Clinic",
        "ASC": "Ambulatory Surgical Clinic",
        "AMBU": "Ambulance",
        "CHIBP": "Clinic",
        "DATRC": "Treatment and Rehabilitation Center",
        "SAM": "Specialized Ambulatory",
        "YAKAP": "Primary Care",
        "GAMOT": "Pharmacy",
        "DOTS": "Tuberculosis DOTS",
        "FDC": "Pharmacy",
        "FP": "Family Planning",
        "MCC": "Medical Care",
        "OMP": "Medical",
        "ABPP": "Pharmacy",
        "CTF": "Cataract",
        "COVIDLAB": "Laboratory",
        "OHAT": "Occupational Health",
        "PPA": "Port",
        "PORT": "Port",
    }
    return categories.get(token, "Hospital")


def _timed(adapter, spec) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    parsed = adapter.parse(spec)
    parse_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    validation = adapter.validate(parsed)
    validate_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    candidates = adapter.normalize(parsed)
    normalize_ms = (time.perf_counter() - started) * 1000.0

    return {
        "parsed": parsed,
        "validation": validation,
        "candidates": candidates,
        "parse_ms": round(parse_ms, 3),
        "validate_ms": round(validate_ms, 3),
        "normalize_ms": round(normalize_ms, 3),
    }, parse_ms + validate_ms + normalize_ms


def _run_read_only(workload: str, files: list[Path], run_token: str) -> dict[str, Any]:
    results: list[FileResult] = []
    started = time.perf_counter()
    for path in files:
        result = FileResult(
            path=str(path),
            filename=path.name,
            status="ok",
            bytes=path.stat().st_size,
            peak_rss_mb=_peak_rss_mb(),
        )
        before = _peak_rss_mb()
        try:
            spec, layer = _build_spec(workload, path, run_token)
            adapter = _make_adapter(workload, spec, layer)
            measured, elapsed_ms = _timed(adapter, spec)
        except Exception as exc:
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            result.peak_rss_mb = _peak_rss_mb()
            results.append(result)
            print(f"  ! {path.name}: {result.error}", file=sys.stderr)
            continue
        parsed = measured["parsed"]
        validation = measured["validation"]
        candidates = measured["candidates"]
        result.parsed_rows = len(parsed.rows)
        result.accepted_rows = validation.accepted_rows
        result.rejected_rows = validation.rejected_rows
        result.candidates = len(candidates)
        result.issues = len(validation.issues)
        result.warnings = len(parsed.warnings)
        result.parse_ms = measured["parse_ms"]
        result.validate_ms = measured["validate_ms"]
        result.normalize_ms = measured["normalize_ms"]
        result.fingerprint = _parse_fingerprint(parsed, candidates)
        result.total_ms = round(elapsed_ms, 3)
        result.peak_rss_mb = max(before, _peak_rss_mb())
        results.append(result)
        print(
            f"  {path.name}: {result.parsed_rows:,} rows, {result.candidates:,} candidates, "
            f"{result.total_ms:,.1f} ms",
            file=sys.stderr,
        )

    wall_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return _aggregate("read_only", workload, results, wall_ms)


def _aggregate(
    mode: str, workload: str, results: list[FileResult], wall_ms: float
) -> dict[str, Any]:
    successful_statuses = {"ok", "published", "skipped_duplicate"}
    ok = [result for result in results if result.status in successful_statuses]
    parsed_rows = sum(result.parsed_rows for result in ok)
    candidates = sum(result.candidates for result in ok)
    parse_ms = round(sum(result.parse_ms for result in ok), 3)
    validate_ms = round(sum(result.validate_ms for result in ok), 3)
    normalize_ms = round(sum(result.normalize_ms for result in ok), 3)
    stage_ms = parse_ms + validate_ms + normalize_ms
    return {
        "workload": workload,
        "mode": mode,
        "generated_at": _iso(_utc_now()),
        "files": [result.__dict__ for result in results],
        "aggregate": {
            "files": len(results),
            "failed_files": len(results) - len(ok),
            "parsed_rows": parsed_rows,
            "accepted_rows": sum(result.accepted_rows for result in ok),
            "rejected_rows": sum(result.rejected_rows for result in ok),
            "candidates": candidates,
            "issues": sum(result.issues for result in ok),
            "parse_ms": parse_ms,
            "validate_ms": validate_ms,
            "normalize_ms": normalize_ms,
            "stage_ms": round(stage_ms, 3),
            "wall_ms": wall_ms,
            "rows_per_second": round(parsed_rows / (wall_ms / 1000.0), 2) if wall_ms else None,
            "peak_rss_mb": max((result.peak_rss_mb for result in results), default=_peak_rss_mb()),
            "sql_statements": sum(result.sql_statements for result in results),
            "sql_time_ms": round(sum(result.sql_time_ms for result in results), 3),
        },
    }


def _prepare_database(url: str) -> None:
    _scratch_database(url)
    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    finally:
        engine.dispose()

    from alembic import command
    from alembic.config import Config

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _run_full_write(
    workload: str,
    files: list[Path],
    run_token: str,
    database_url: str,
    raw_store: Path,
    report_dir: Path,
    reprocess: bool,
) -> dict[str, Any]:
    from philfacilities_ingest.config import IngestSettings
    from philfacilities_ingest.pipeline import run_ingestion
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    settings = IngestSettings(
        database_url=database_url,
        raw_store=raw_store,
        report_dir=report_dir,
    )
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    statement = {"count": 0, "seconds": 0.0, "started": 0.0}

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement_text, parameters, context, executemany):
        statement["started"] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement_text, parameters, context, executemany):
        statement["count"] += 1
        statement["seconds"] += time.perf_counter() - statement["started"]

    results: list[FileResult] = []
    started = time.perf_counter()
    for path in files:
        before_statements = statement["count"]
        before_sql_seconds = statement["seconds"]
        result = FileResult(
            path=str(path),
            filename=path.name,
            status="ok",
            bytes=path.stat().st_size,
            peak_rss_mb=_peak_rss_mb(),
        )
        try:
            spec, layer = _build_spec(workload, path, run_token)
            adapter = _make_adapter(workload, spec, layer)
            file_started = time.perf_counter()
            with session_factory() as session:
                outcome = run_ingestion(
                    spec=spec,
                    adapter=adapter,
                    session=session,
                    settings=settings,
                    reprocess=reprocess,
                )
            result.full_write_ms = round((time.perf_counter() - file_started) * 1000.0, 3)
            result.status = outcome.status
            result.parsed_rows = int(outcome.stats.get("parsed_rows") or 0)
            result.accepted_rows = int(outcome.stats.get("accepted_rows") or 0)
            result.rejected_rows = int(outcome.stats.get("rejected_rows") or 0)
            result.candidates = int(outcome.stats.get("normalized_candidates") or 0)
            result.issues = len(outcome.issues)
            timings = outcome.stats.get("timings_ms") or {}
            result.parse_ms = float(timings.get("parse_ms") or 0.0)
            result.validate_ms = float(timings.get("validate_ms") or 0.0)
            result.normalize_ms = float(timings.get("normalize_ms") or 0.0)
            result.total_ms = float(outcome.stats.get("total_ms") or result.full_write_ms)
            result.extra = {
                "release_id": outcome.release_id,
                "facilities_created": outcome.stats.get("facilities_created"),
                "facilities_updated": outcome.stats.get("facilities_updated"),
                "reprocess_skipped_unchanged": outcome.stats.get("reprocess_skipped_unchanged"),
                "timings_ms": timings,
                "rows_per_second": outcome.stats.get("rows_per_second"),
            }
        except Exception as exc:
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            print(f"  ! {path.name}: {result.error}", file=sys.stderr)
        result.sql_statements = statement["count"] - before_statements
        result.sql_time_ms = round((statement["seconds"] - before_sql_seconds) * 1000.0, 3)
        result.peak_rss_mb = _peak_rss_mb()
        results.append(result)
        print(
            f"  {path.name}: {result.status}, {result.parsed_rows:,} rows, "
            f"{result.full_write_ms:,.1f} ms, {result.sql_statements:,} SQL",
            file=sys.stderr,
        )

    engine.dispose()
    wall_ms = round((time.perf_counter() - started) * 1000.0, 3)
    aggregate = _aggregate("full_write", workload, results, wall_ms)
    aggregate["aggregate"]["sql_statements"] = sum(result.sql_statements for result in results)
    aggregate["aggregate"]["sql_time_ms"] = round(sum(result.sql_time_ms for result in results), 3)
    aggregate["database"] = _database_name(database_url)
    aggregate["reprocess"] = reprocess
    return aggregate


def _write_output(payload: dict[str, Any], output: Path | None) -> Path:
    output = output or OUTPUT_DIR / f"{payload['workload']}-{payload['mode']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return output


def _print_summary(payload: dict[str, Any], output: Path) -> None:
    aggregate = payload["aggregate"]
    print(
        f"{payload['workload']} ({payload['mode']}): "
        f"{aggregate['files']} files, {aggregate['parsed_rows']:,} rows, "
        f"{aggregate['candidates']:,} candidates, {aggregate['wall_ms']:,.0f} ms, "
        f"{aggregate['rows_per_second'] or 0:,.1f} rows/s, "
        f"peak {aggregate['peak_rss_mb']:,.1f} MiB"
    )
    print(f"evidence: {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=("ebeis", "osm", "philhealth", "all"), default="all")
    parser.add_argument("--input", type=Path, help="File or directory of preserved artifacts.")
    parser.add_argument("--json", action="store_true", help="Print the JSON payload only.")
    parser.add_argument("--output", type=Path, help="Write JSON evidence to this path.")
    parser.add_argument("--full-write", action="store_true", help="Run the canonical apply path.")
    parser.add_argument("--database-url", help="Scratch database URL for --full-write.")
    parser.add_argument("--migrate", action="store_true", help="Create/upgrade the scratch schema.")
    parser.add_argument(
        "--reprocess", action="store_true", help="Force reprocess of existing releases."
    )
    parser.add_argument(
        "--raw-store", type=Path, default=Path("/tmp/opencode/philfacilities-bench/raw")
    )
    parser.add_argument(
        "--report-dir", type=Path, default=Path("/tmp/opencode/philfacilities-bench/reports")
    )
    parser.add_argument("--limit", type=int, help="Only process the first N files.")
    parser.add_argument(
        "--release-token",
        help=(
            "Pin the release label token. Use the same token for a first write and "
            "its reprocess run so the second invocation reprocesses the same release."
        ),
    )
    args = parser.parse_args(argv)

    workloads = ("ebeis", "osm", "philhealth") if args.workload == "all" else (args.workload,)
    if args.full_write and not args.database_url:
        parser.error("--full-write requires --database-url")
    if args.full_write and args.database_url:
        _scratch_database(args.database_url)
        if args.migrate:
            _prepare_database(args.database_url)

    payloads: list[dict[str, Any]] = []
    for workload in workloads:
        files = _discover(workload, args.input if args.workload != "all" else None)
        if args.limit:
            files = files[: args.limit]
        if not files:
            print(f"No preserved {workload} artifacts found.", file=sys.stderr)
            continue
        print(f"→ {workload}: {len(files)} file(s)", file=sys.stderr)
        run_token = args.release_token or _release_token()
        if args.full_write:
            assert args.database_url is not None
            payload = _run_full_write(
                workload,
                files,
                run_token,
                args.database_url,
                args.raw_store,
                args.report_dir,
                args.reprocess,
            )
        else:
            payload = _run_read_only(workload, files, run_token)
        payloads.append(payload)
        if args.json and len(workloads) == 1:
            continue
        if not args.json:
            _print_summary(payload, _write_output(payload, args.output))

    if args.json:
        if len(payloads) == 1:
            print(json.dumps(payloads[0], indent=2, default=str))
        else:
            print(json.dumps(payloads, indent=2, default=str))
    elif len(payloads) > 1:
        combined = _write_output({"workloads": payloads}, args.output or OUTPUT_DIR / "all.json")
        print(f"combined evidence: {combined}")
    return 0 if all(payload["aggregate"]["failed_files"] == 0 for payload in payloads) else 1


if __name__ == "__main__":
    raise SystemExit(main())
