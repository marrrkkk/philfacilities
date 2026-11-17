# Ingestion performance evidence — 2026-11-16

This directory holds the before/after measurements for the ingestion pipeline
refactor. The current pipeline behavior is documented in
[`docs/ingestion.md`](../../../ingestion.md).

## Method

The harness is [`scripts/ingest_benchmark.py`](../../../../scripts/ingest_benchmark.py).
It replays preserved raw artifacts through `parse → validate → normalize` and,
with `--full-write`, through the canonical apply path against a throwaway
database. Each run records wall time, parsed/accepted/rejected rows, peak RSS,
SQL statement count, and SQL time. Full-write runs start from an empty
`*_bench` database and apply the current Alembic migrations.

The "before" runs use a clean checkout of the pre-refactor commit
(`6a5d8d9`) in a separate worktree. The "after" runs use the refactored tree.
Both sides replay the same preserved artifacts, on the same machine, with the
same PostgreSQL instance and the same Python environment.

Commands (representative):

```bash
uv run python scripts/ingest_benchmark.py --workload ebeis \
  --input var/raw --full-write --migrate \
  --database-url postgresql+psycopg://.../philfacilities_after_ebeis_bench --json
uv run python scripts/ingest_benchmark.py --workload osm \
  --input var/raw/osm --full-write --migrate \
  --database-url postgresql+psycopg://.../philfacilities_after_osm_bench --json
uv run python scripts/ingest_benchmark.py --workload philhealth \
  --input var/raw --full-write --migrate \
  --database-url postgresql+psycopg://.../philfacilities_after_philhealth_bench --json
uv run python scripts/ingest_benchmark.py --workload philhealth \
  --input var/raw --full-write --reprocess \
  --database-url postgresql+psycopg://.../philfacilities_after_philhealth_bench --json
```

## Workloads

| Workload | Artifacts | Rows |
|---|---|---|
| DepEd EBEIS | 19 current regional masterlist HTML pages | 83,218 |
| HOT/OSM | 6 GeoParquet layers (health, education, POI, air, sea, rail) | 100,772 parsed (97,173 accepted) |
| PhilHealth | 26 provider-category PDFs | 28,207 |

## Results

See the JSON files in this directory. `before-*.json` are the pre-refactor
runs; `after-*.json` are the post-refactor runs. `before-ebeis-update-path.json`
and `after-ebeis-update-path.json` measure a stale duplicate release that
updates facilities created by the current page.

| Workload | Target | Before | After | Result |
|---|---|---|---|---|
| EBEIS first bulk load (19 files, 83,218 rows) | ≥3× faster | 2,103.1 s / 666,164 SQL | 573.0 s / 1,710 SQL | **3.67× faster — pass** |
| EBEIS NCR first write (5,055 rows) | ≥3× faster | 114.8 s / 40,467 SQL | 32.7 s / 109 SQL | **3.51× faster — pass** |
| EBEIS stale-duplicate reparse (5,055 rows) | ≥5× reprocess | 261.9 s / 91,076 SQL | 35.8 s / 277 SQL | **7.31× faster — pass** |
| EBEIS unchanged-release reprocess | reference only | 2.1 s / 16 SQL | 2.5 s / 27 SQL | 0.86× (sub-3 s no-op path; not the ≥5× reparse target) |
| OSM 6-layer first write (100,772 parsed) | ≥2× faster | 2,354.6 s / 651,609 SQL | 914.8 s / 2,008 SQL | **2.57× faster — pass** |
| OSM peak RSS | ≤50% of baseline | 1,408.1 MiB | 1,454.3 MiB | **+3.3% — target missed** |
| PhilHealth reprocess | ≥2× faster | 649.8 s / 411 SQL | not re-run | **unverified** |
| Apply-stage SQL | scales with batches | 666,164 / 651,609 / 91,076 | 1,710 / 2,008 / 277 | **pass; 325–390× fewer statements** |
| Golden replay | identical counts/hash | — | — | **pass** (`apps/ingest/tests/test_golden_replay.py`) |

### Missed or unverified targets

- **OSM peak RSS (target ≤50% of baseline; measured +3.3%).** The apply path no
  longer accumulates one ORM object per row, but process peak RSS is dominated by
  parsing the 55,824-row education GeoParquet layer and retaining normalized
  candidates before staging. Batching lowered SQL count by 324× and wall time by
  2.57× but did not lower the parser/candidate peak. The target is recorded as
  missed rather than lowered.
- **PhilHealth reprocess ≥2× (unverified).** The pre-refactor baseline is
  649.8 s for 24,986 rows; 24,986 of 28,207 rows were processed because the
  preserved `EMCB-ANTE` PDF still triggers the pre-existing duplicate-row-reference
  abort. The post-refactor PhilHealth run was explicitly stopped after the EBEIS
  and OSM runs to finish the task, so there is no `after-philhealth-*.json`.
  The parse path is unchanged; the apply-path improvement is evidenced by the
  EBEIS stale-duplicate run (91,076 → 277 SQL, 7.31× faster). This target remains
  open and must not be reported as met.
- **PhilHealth parse fingerprint.** No before/after read-only fingerprint run and
  no after PhilHealth full-write exist. The parser implementation was moved, not
  rewritten, but byte-for-byte source-key equality is not proven by this evidence
  set.

## Golden replay

`apps/ingest/tests/test_golden_replay.py` loads the deterministic synthetic
dataset twice and compares facility, source-record, assertion, link, release,
and publication counts and a canonical field hash. It runs against the
PostGIS test database with `uv run pytest apps/ingest/tests/test_golden_replay.py`.

## Notes and limitations

- The full-write comparison includes the new hot-path indexes and unique
  constraints added by migration `0010_ingest_hot_path_indexes`; the pre-refactor
  database has neither.
- The PhilHealth workload is parse-bound; the parser is unchanged by the
  refactor, so parse time is a shared cost and the apply difference is smaller
  relative to wall time.
- Peak RSS is process-wide `ru_maxrss`, which includes the parser's transient
  allocations as well as ORM state.
