# Testing and quality gates

> **Purpose** — Describe the test layers, commands, fixtures, contract checks, and CI gates.
> **Audience** — Contributors adding or changing behavior, and agents verifying a change.
> **See also** — [Contributing](contributing.md) · [Getting started](getting-started.md) · [Public API](api.md)

A passing API test is not proof that source data is correct. The suite has separate layers for parser behavior, pipeline idempotency, data integrity, identity resolution, rights, the API contract, and the web experience.

## 1. Layout

| Path | Coverage |
|---|---|
| `apps/ingest/tests/` | Adapter contract, parser/golden replay, registry integrity, pipeline idempotency, fusion, matching/merge, manifest, LGU inventory, source report, stats |
| `apps/mcp/tests/` | MCP client boundary, curated tool surface, tool/contract checks, stateless HTTP transport |
| `tests/` | API contract and integration, rights, identity matching, inclusion model, population/PSGC, release rollback, scheduling, discovery/scraper, storage integrity, source candidates/inventory, validation gates, pipeline hardening, domain source tests |
| `tests/contract/`, `tests/data-quality/`, `tests/integration/` | OpenAPI/client drift fixtures, data-quality invariants, PostGIS fixtures |
| `apps/web/e2e/` | Playwright end-to-end, accessibility, responsive, CSP, keyboard tests |
| `conftest.py` | Test database setup/reset and application settings isolation |

## 2. Commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest --require-integration
uv run pytest --require-integration -q --cov --cov-fail-under=60

pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e

uv run python scripts/check_markdown_links.py
```

`just check` runs lint, typecheck, pytest, build, and the link check; `just test-required` runs the suite with the integration guard CI uses. Mypy is deliberately scoped in `pyproject.toml` to four ingest core modules (`contracts.py`, `storage.py`, `replay.py`, `pipeline/locking.py`); widen it module by module. The coverage floor (60%) is measured on the full suite under Python 3.12 including integration tests; the 3.14 leg runs without `--cov` because coverage is unreliable with the SQLAlchemy C-extension.

Focused runs:

```bash
uv run pytest apps/ingest/tests/test_parsers.py -q
uv run pytest apps/ingest/tests/test_adapter_contract.py -q
uv run pytest tests/test_api_contract.py -q
uv run pytest apps/mcp/tests -q
uv run pytest tests/test_pipeline_reprocess.py -q
uv run pytest -m "not integration"
```

## 3. Test database

Integration tests use a dedicated PostgreSQL/PostGIS database:

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
```

Default URL: `postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test`; override with `PHILFACILITIES_TEST_DATABASE_URL`. `conftest.py` enforces that the name ends in `_test`, drops and rebuilds all schemas at session start, and isolates settings before application modules load. Integration tests skip when the database is unavailable so parser/unit tests stay runnable without Docker. Never point the test URL at the working database.

**Integration guard.** A missing database would otherwise produce a green build with every integration test skipped. `--require-integration` makes it a hard failure and also fails when a filter typo deselects every integration test.

CI runs `pytest --require-integration` on Python 3.12 and 3.14 in four required jobs plus a single `ci-ok` aggregate that branch protection targets:

| Job | Checks | Python |
|---|---|---|
| `quality` | Ruff lint/format, mypy, Markdown links | 3.14 |
| `python-tests` | Full suite with integration guard; coverage floor on 3.12 only | 3.12, 3.14 |
| `web` | Generated-client drift, ESLint, TypeScript, production build | Node 24 |
| `e2e` | Migrations, synthetic demo, Playwright functional/accessibility checks | 3.14 / Node 24 |

`tests/test_test_harness.py` verifies the flag and workflow invariants. Dependency audits are advisory and run weekly in `.github/workflows/dependencies.yml`.

## 4. Markers

| Marker | Meaning |
|---|---|
| `integration` | Requires a live PostgreSQL/PostGIS database |
| `contract` | Checks the public API contract |
| `data_quality` | Validates source-data invariants |

Use `-m "not integration"` for a fast local pass.

## 5. What the layers prove

- **Adapter/parser tests** — deterministic output and preserved `raw_payload`; schema-drift failure on missing/renamed columns; row references on issues; no invented coordinates, PSGC codes, or status; locale-aware dates/numbers and null semantics; golden replay for critical tables.
- **Pipeline tests** — unchanged checksum → skip; parser-version change reprocesses; failed/empty/below-floor new releases are quarantined while the previous release stays public; failed reprocess of a published release keeps it published; discovery exceptions are `failed`, not skips; second worker fails fast; killed runs resume; replay verifies SHA-256 and recovers stored dataset context; rollback restores canonical state including contacts.
- **Identity and fusion tests** — exact IDs match deterministically; name-only similarity never auto-merges; same name in different LGUs stays separate; ambiguous pairs queue; accepting is separate from merging; rejected pairs are not re-queued; pending resolution merges only still-qualifying pairs; merges move evidence and leave a `merged` tombstone; unique-contact and undo rules hold; fusion keeps conflicts, requires two distinct agencies for `agreed`, lets official claims outrank frequent community ones, and applies only the safe allowlist.
- **Rights and validation gates** — explicit vocabulary; `publicly_available_verified` public-compatible; rights alone insufficient without an approved gate; restricted/internal/quarantined evidence never appears publicly; latest-release membership; internal releases cannot rewrite public facilities; manual publication requires a reviewer; alerts post only failed rows; raw stores reject tampered bytes.
- **API tests** — OpenAPI matches `app.openapi()` and is read-only; error envelope, request IDs, spatial bounds; search/filters/pagination/provenance/domain endpoints; statistics agree with inventory; restricted accreditations never leak; monitoring uses one latest row per dataset; CSV/Parquet parity; CORS, rate limits, ETags, download gating.
- **MCP tests** — client allowlist, null preservation, sanitized errors; curated read-only tools; payload passthrough under `result`; every tool path/argument exists in OpenAPI; stateless HTTP and host validation. None needs a database or live API.
- **Web tests** — directory search/filters, profile, map selection, mobile navigation, source/data pages, error/empty states; keyboard reachability, skip link, 3px focus ring, Escape-to-close with focus return; hydration marker before interactive tests; axe on public pages; CSP nonce on every script with no `unsafe-inline`; responsive screenshots; design-token regressions; directory usable with tiles failing; low-precision markers do not imply precise locations.

Contract tests run without a live database; integration tests need the test database.

## 6. Fixtures

```bash
uv run philfacilities-ingest generate-fixtures
```

Deterministic synthetic fixtures and their checksum manifest live in `database/fixtures/`. They are for tests and demos only; every synthetic facility, dataset, and release is labelled. The working database is real publication-approved data.

## 7. Data-quality checks

Quality is per attribute and source, not one opaque score. Suite and `/v1/quality` cover required IDs and within-release uniqueness; conflicting names per ID; PSGC existence/hierarchy and preserved leading zeros; coordinate plausibility (flag, do not silently delete); precision/method distribution and mass-duplicate coordinates; missing-vs-zero for beds/population/dates; source-record linkage for every public field; distinct publication/reference/retrieval/processing times; exclusion of blocked/internal evidence; and accurate last-successful-ingestion reporting.

Current counts and open issues come from `/v1/statistics`, `/v1/quality/summary`, and `/v1/coverage`; generated reports go to `var/reports/`. Do not copy volatile counts into documentation.

## 8. Performance

`scripts/api_benchmark.py` records p50/p95 latency and response sizes for health, statistics, facility list/detail, a bbox query, and the source catalogue against a running API — a smoke benchmark, not a load test. `scripts/ingest_benchmark.py` measures large ingestion workloads; store JSON evidence under `docs/operations/evidence/`. Known pre-launch gaps: unfiltered facility-list latency, bulk-export duration, and production caching.

## 9. Release gates

- **Data release** — source acquired and hashed; parser/schema-drift tests pass; validation thresholds pass; publication decision recorded; identity candidates reviewed; release notes and limitations recorded.
- **API release** — migrations applied to fresh and test databases; contract tests pass; no restricted fields exposed; OpenAPI regenerated and committed; source/provenance/quality fields documented.
- **Web release** — responsive and accessibility tests pass; freshness labels truthful; empty/loading/error states work; reference implementation audited; map attribution and precision warnings visible.
