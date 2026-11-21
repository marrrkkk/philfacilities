# Testing and quality gates

A passing API test is not proof that the source data is correct. The suite has separate layers for parser behavior, pipeline idempotency, data integrity, identity resolution, rights, the API contract, and the web experience.

## 1. Layout

| Path | Coverage |
|---|---|
| `apps/ingest/tests/` | Adapter contract, parser/golden replay, registry integrity, pipeline idempotency, fusion, matching/merge, manifest, LGU inventory, source report, stats |
| `apps/mcp/tests/` | MCP client boundary, curated tool surface, tool/contract checks, stateless HTTP transport |
| `tests/` | API contract and integration, rights, identity matching, inclusion model, population/PSGC, release rollback, scheduling, discovery/scraper, storage integrity, source candidates/inventory, validation gates, pipeline hardening (acceptance floors, locks, replay, latest-release membership, manual-import governance), domain source tests |
| `tests/contract/` | OpenAPI and client-drift fixtures |
| `tests/data-quality/` | Data-quality invariants |
| `tests/integration/` | PostGIS integration fixtures |
| `apps/web/e2e/` | Playwright end-to-end, accessibility, responsive, CSP, keyboard tests |
| `conftest.py` | Test database setup/reset and application settings isolation |

## 2. Commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest --require-integration        # fail if integration tests cannot run
uv run pytest --require-integration -q --cov --cov-fail-under=60   # coverage floor

pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e

uv run python scripts/check_markdown_links.py
```

`just check` runs lint, typecheck, pytest, build, and the link check. `just test-required`
runs the suite with the integration guard that CI uses.

Mypy is deliberately scoped in `pyproject.toml` to the ingest core modules (`contracts`, `storage`, `replay`, and the dataset lock); widen the file list module by module rather than adding a whole-package baseline. CI runs the same command.

The coverage floor (`--cov-fail-under=60`) is measured on the full suite under Python 3.12, including the integration tests. It is a backstop against silent test loss, not a claim that parser and API behaviour is fully covered. Coverage measurement is unreliable with the Python 3.14/SQLAlchemy C-extension combination, so the 3.14 CI leg runs the same tests without `--cov`. Running the floor over the full suite also avoids a false pass caused by skipping the database-dependent tests.

Focused runs:

```bash
uv run pytest apps/ingest/tests/test_parsers.py -q
uv run pytest apps/ingest/tests/test_adapter_contract.py -q
uv run pytest tests/test_api_contract.py -q
uv run pytest apps/mcp/tests -q
uv run pytest tests/test_pipeline_reprocess.py -q
uv run pytest tests/test_pipeline_hardening.py tests/test_storage.py -q
uv run pytest -m "not integration"
```

## 3. Test database

Integration tests use a dedicated PostgreSQL/PostGIS database:

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
```

Default URL: `postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test`. Override with `PHILFACILITIES_TEST_DATABASE_URL`.

Safety rules enforced by `conftest.py`:

- the database name **must** end in `_test`;
- all application schemas are dropped and rebuilt at session start;
- `PHILFACILITIES_DATABASE_URL`, `DATABASE_URL`, `PHILFACILITIES_ENV=test`, and a temporary raw/report directory are set before application modules load;
- integration tests skip when the database is unavailable, so parser/unit tests remain runnable without Docker.

Never point the test URL at the working database.

### Integration guard

Locally, a missing test database skips integration tests so parsers and other unit
tests remain runnable. In CI that behaviour would be misleading: a failed database
service could produce a green build with every integration test skipped. Pass
`--require-integration` to make the missing database a hard failure. The same flag
also fails a run where a filter or marker typo deselects every integration test.

CI runs `pytest --require-integration` on Python 3.12 and 3.14. The workflow is
split into four required jobs plus a single `ci-ok` aggregate that branch
protection can target:

| Job | Checks | Python |
|---|---|---|
| `quality` | Ruff lint/format, mypy, Markdown links | 3.14 |
| `python-tests` | Full suite with the integration guard; coverage floor on 3.12 only | 3.12, 3.14 |
| `web` | Generated-client drift, ESLint, TypeScript, production build | Node 24 |
| `e2e` | Migrations, synthetic demo, Playwright functional/accessibility checks | 3.14 / Node 24 |

`tests/test_test_harness.py` verifies the flag's behaviour and asserts that the
workflow still passes it, uses a version matrix, gives every required job a
timeout, and keeps the `ci-ok` aggregate. Dependency audits are advisory and run
on a weekly schedule in `.github/workflows/dependencies.yml`, so a newly
published CVE cannot fail an unrelated pull request.

## 4. Markers

| Marker | Meaning |
|---|---|
| `integration` | Requires a live PostgreSQL/PostGIS database |
| `contract` | Checks the public API contract |
| `data_quality` | Validates source-data invariants |

Use `-m "not integration"` for a fast local pass.

## 5. What the layers prove

### Adapter and parser tests

- deterministic parse output and preserved `raw_payload`;
- schema-drift failure when required columns are missing or renamed;
- row references on validation issues;
- no invented coordinates, PSGC codes, or status values;
- locale-aware dates/numbers and null semantics (`NULL` is not zero/false/inactive);
- golden replay for critical extracted tables (`apps/ingest/tests/golden/`).

### Pipeline tests

- same checksum → `skipped_duplicate`; no second release or records;
- a parser-version change reprocesses the preserved release automatically and updates the recorded parser/schema versions;
- a failed new release is `failed`/`quarantined` and the previous published release remains public;
- a zero-row parse is always fatal and quarantined before canonical writes;
- a release below its acceptance floor is quarantined before canonical writes and records an `acceptance_rate_below_floor` quality issue;
- an unexpected apply error leaves a never-public release `failed`/`quarantined`, and a previously published release keeps serving;
- a failed reprocess of an already-published release keeps it `published`, skips staging so the last good records are untouched, and a retry is not misclassified as `skipped_duplicate`;
- an unexpected discovery exception is reported as `failed`, not as a controlled skip;
- a second worker for the same dataset fails fast with `IngestionLockError`;
- a killed run resumes the same release;
- `reprocess=True` rebuilds derived rows from a preserved artifact without duplicating unchanged links;
- `source replay` verifies the recorded SHA-256 and reprocesses the existing release; tampered bytes are rejected;
- replay validates the stored dataset's publisher and recovers EBEIS region / PhilHealth provider-category options instead of replaying every artifact with the catalogue defaults;
- release comparison accounts for added/removed/retained/changed records and links without mutation;
- release rollback restores the captured canonical state conservatively, including facility contacts;
- coordinate gap-fill resolves city names only from a non-synthetic geography release.

### Identity and fusion tests

- exact source IDs match deterministically;
- name-only similarity never auto-merges;
- same name in different LGUs stays separate;
- ambiguous pairs queue in `quality.match_candidates`;
- accepting is separate from merging;
- rejected candidates are not re-queued for the same algorithm version;
- pending resolution merges only a pair that still qualifies and terminally rejects stale, cross-type, conflicting and weak pairs with a reason;
- fully uppercase display names are title-cased at canonical creation and by the backfill, while abbreviations stay uppercase and `official_name` plus field assertions keep the source spelling;
- display-name backfill records one `display_name_normalized` change event per changed facility and is idempotent;
- merges move evidence and leave a `merged` tombstone plus change events;
- merge moves unique contacts, keeps a duplicate contact on the source tombstone instead of violating `uq_facility_contact_source`, and undo restores only the moved rows;
- public match-candidate responses omit reviewer name and note;
- fusion keeps every conflicting claim and marks `agreed`/`conflict`/`single_source` correctly;
- fusion ignores claims from restricted, blocked, or superseded releases;
- `agreed` requires two distinct agencies; records from one publisher stay `single_source`;
- an official claim outranks a more frequent community claim;
- explicit `--limit` facility IDs still respect the multi-source scope;
- `apply-fusions` writes only the safe attribute allowlist; clear-authority conflicts apply automatically, equal-authority conflicts stay derived-only, and single-source values only fill missing fields;
- invalid canonical values are rejected, and stale fusions are removed when their claims disappear.

### Rights and validation gates

- the rights vocabulary is explicit and conservative;
- `publicly_available_verified` is public-compatible;
- rights alone are insufficient without an approved/published gate;
- restricted/internal/quarantined evidence never appears in public outputs;
- a facility is current only while it belongs to its dataset's latest published release; a failed newer attempt does not displace the last good release;
- an internal-only release cannot rewrite a public facility's canonical fields, current location, profiles, or publication state, and its child rows stay read-gated;
- a manual import or publication decision that makes records public requires a recorded reviewer;
- ingestion failures post only failed rows to the configured alert webhook;
- filesystem and S3 raw stores reject tampered bytes or checksum metadata;
- PhilHealth repeated physical rows keep distinct source keys;
- the two-column annex is not parsed as provider rows.

### API tests

- OpenAPI contains the exact public read contract and is read-only;
- the committed OpenAPI document matches `app.openapi()`;
- error envelope, request IDs, validation errors, and spatial bounds;
- facility search, filters, cursor pagination, detail provenance, and domain endpoints;
- statistics agree with the facility inventory;
- publication-gated sources, releases, checks, monitoring, quality, and changes;
- nested and list accreditations from a restricted or blocked release never leak through a public facility;
- `/v1/monitoring` uses one latest row per dataset rather than loading complete history;
- CSV/Parquet export parity and multi-chunk lookups;
- CORS, rate limits, ETags, and download gating.

Contract tests run without a live database; integration tests need the test database.

### MCP tests

- the client accepts only public API paths, drops unset arguments while keeping
  `false`/`0`, preserves nulls, and maps API error envelopes to readable tool errors;
- transport timeouts and connection failures are sanitized, with no internal URL
  or stack trace reaching the model;
- the in-memory MCP client sees exactly the curated tool set, all marked read-only;
- tool calls return API payloads unchanged under the `result` envelope, including
  array responses from `/v1/sources` and `/v1/geographies`; provenance merges
  sources and field assertions, and invalid arguments fail schema validation;
- every tool path and query argument exists in the committed OpenAPI document, and
  no internal review endpoint is exposed;
- stateless HTTP serves `/healthz`, `/readyz` and a JSON-RPC handshake, and rejects
  unknown Host headers.

None of these tests needs the database or a live API; upstream calls use
`httpx.MockTransport`. See [MCP](mcp.md).

### Web tests

`apps/web/e2e/app.spec.ts` covers directory search/filters, facility profile, map selection, mobile filter sheet, source details, data dictionary, and error/empty states. It also checks:

- keyboard reachability, skip link, search submission, 3px focus ring, Escape-to-close with focus return;
- the `<html data-hydrated="true">` marker before interactive tests;
- axe accessibility on public pages;
- CSP nonce presence, nonce on every script, no `unsafe-inline` in `script-src`, no violations on public pages or the map;
- responsive screenshots at 390, 768, 1024, 1440, and 1920 px, plus a mobile viewport assertion;
- design-token regressions against the measured reference system;
- the directory remains usable if map tiles fail;
- low/unknown-precision markers do not imply precise locations.

## 6. Fixtures

```bash
uv run philfacilities-ingest generate-fixtures
```

Deterministic synthetic fixtures and their checksum manifest live in `database/fixtures/`. Fixtures are for tests and demos only; every synthetic facility, dataset, and release is labelled. The working database is real publication-approved data.

## 7. Data-quality checks

Quality is per attribute and source, not one opaque score. The suite and `/v1/quality` cover:

- required IDs and uniqueness within a release;
- conflicting names for the same ID;
- PSGC existence/hierarchy and preserved leading zeros;
- coordinate range and Philippines-bbox plausibility (flag, do not silently delete);
- precision/method distribution and mass-duplicate coordinates;
- missing-vs-zero semantics for beds, population, and dates;
- every public source-derived field links to a source record/release;
- publication date, reference period, retrieval time, and processing time remain distinct;
- blocked/internal evidence is excluded from public outputs;
- the last successful ingestion is shown accurately.

Current counts and open issues are exposed by `/v1/statistics`, `/v1/quality/summary`, and `/v1/coverage`; generated measured reports go to `var/reports/`. Do not copy volatile counts into this guide.

## 8. Performance

A local serial baseline is in `scripts/api_benchmark.py`:

```bash
uv run python scripts/api_benchmark.py
```

It records p50/p95 latency and response sizes for health, statistics, facility list/detail, a bounding-box query, and the source catalogue against a running API. It is a smoke benchmark, not a load test. Large ingestion workloads can be measured with `scripts/ingest_benchmark.py`; store JSON evidence under `docs/operations/evidence/`.

Known pre-launch gaps: unfiltered facility-list latency, bulk-export duration at current scale, and production caching. Do not treat a local benchmark as a production capacity claim.

## 9. Release gates

### Data release

- source release acquired and hashed;
- parser and schema-drift tests pass;
- validation thresholds pass;
- publication decision recorded under [data policy](data-policy.md);
- identity candidates reviewed;
- release notes and known limitations recorded.

### API release

- migrations applied to a fresh database and the test database;
- contract tests pass;
- no restricted fields exposed;
- OpenAPI regenerated and committed;
- source, provenance, and quality fields documented.

### Web release

- responsive and accessibility tests pass;
- data-freshness labels are truthful;
- empty/loading/error states work;
- reference design implementation audited;
- map attribution and precision warnings visible.
