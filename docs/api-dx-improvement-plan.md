# API developer-experience improvement plan

> **Status** — Proposal, not yet accepted. No code changes are included.
> **Audience** — API maintainers, web/MCP client developers, reviewers.
> **Machine contract** — [`packages/api-client/openapi.json`](../packages/api-client/openapi.json) stays authoritative. This plan never proposes a second source of truth.
> **Evidence** — Measured against the running local API and working PostgreSQL database on 2026-11-21. Re-measure before each phase gate; do not copy volatile counts into prose.
> **See also** — [Public API](api.md) · [Data dictionary](data-dictionary.md) · [ADR 0007](decisions/0007-api-versioning-and-bulk-exports.md) · [Testing](testing.md)

## 0. Goal, non-goals, and success measures

**Goal.** Make the `/v1` API pleasant to build against without weakening the source-linked, rights-gated data model: fewer irrelevant fields in default responses, truthful signals about which fields are populated, one consistent detail shape, consistent errors, and discoverable category coverage.

**Non-goals.**

- No deletion of provenance, rights, or source evidence. Missing/null must stay distinct from zero, `false`, closed, or restricted ([Data policy](data-policy.md) rules 1–3, 6–9).
- No `/v2`, no breaking change to existing response shapes, parameter names, or status codes under `/v1` ([ADR 0007](decisions/0007-api-versioning-and-bulk-exports.md)).
- No new source acquisition, parser changes, or publication-gate changes. The source asymmetry described in §1.3 is a sourcing problem, not an API bug.
- No change to `taxonomy.py` or `rights.py` vocabularies; `/v1/taxonomy` remains the reference.

**Success measures (targets, to be confirmed at each phase gate).**

| Measure | Baseline (2026-11-21) | Target |
|---|---|---|
| Top-level keys on a facility detail response | 34 | ≤ 12 in `view=compact`; `view=full` unchanged |
| Detail payload size | 5.5–7.5 KB | ≤ 2.5 KB compact |
| 100-item facility list | 147.9 KiB | ≤ 75 KiB with a compact list option (Phase 3) |
| Developer can answer "is this field populated?" from the API | No | Yes, via `GET /v1/fields` |
| Error envelope documented = error envelope returned | No | Yes |
| Categories with a path to bulk export | 4 fixed files | All, via filtered generic download |

## 1. Evidence baseline

All numbers below were measured locally; timing figures are single-run observations, not p50/p95. Treat them as directional and capture repeatable numbers with `scripts/api_benchmark.py` in Phase 0.

### 1.1 Response weight

| Request | Size | Time |
|---|---|---|
| `GET /v1/facilities?limit=20` | 31.5 KiB | 627 ms |
| `GET /v1/facilities?limit=100` | 147.9 KiB | 1,103 ms |
| `GET /v1/facilities?type=school&limit=100` | 141.8 KiB | 600 ms |
| `GET /v1/facilities?type=library&limit=100` | 126.5 KiB | 1,394 ms |
| `GET /v1/facilities/map?bbox=120,14,121,15&zoom=10` | 12.3 KiB | 1,387 ms |
| `GET /v1/taxonomy` | 10.5 KiB | 73 ms |
| `GET /v1/facilities/{id}` | 5.5–7.5 KB, 34 keys, 9–11 empty | 66–134 ms |

`docs/api.md` §11 already records unfiltered list latency as a pre-launch gap; this plan makes it measurable and actionable.

### 1.2 Field usefulness (published records, n = 229,274)

| Field / collection | Non-null or populated | Share |
|---|---:|---:|
| `relationships[]` | 0 rows in the entire database | 0% |
| `school.resources[]` / `/schools/{id}/resources` | 0 rows in the entire database | 0% |
| `access_conditions` | 1,718 | 0.75% |
| `services[]` | 1,540 facilities | 0.67% |
| `contacts[]` | 3,175 facilities | 1.38% |
| `roles[]` | 2,589 facilities | 1.13% |
| `public_access_class` | 2,608 | 1.14% |
| `postal_code` (of 227,911 current locations) | 27,924 | 12.3% |
| `functions[]` | 40,839 facilities | 17.8% |
| `ownership_type` / `operator_type` | 127,414 / 117,989 | 55.6% / 51.5% |
| School profiles (of 142,387 schools) | 104,651 | 73.5% |
| Health profiles (of 78,516 health facilities) | 55,036 | 70.1% |
| `facility_kind = facility` | 227,188 | 99.1% |
| `official_name = display_name` | 169,589 | 74.0% |
| `publication_status`, `is_synthetic` | constant `public` / `false` | 100% constant |

Additional detail: in school profiles, `sector`, `school_management`, `division` and `district` are each ~45% filled; in health profiles, `licensing_status` is 27.8% filled. `source_count` is exactly `len(source_refs)` and `functions[]` on a summary duplicates `function_details[]` on detail.

**Conclusion.** The fields are not useless *as data* — provenance and null-preservation are the product. They are useless *in the default response* for most consumers. Fix presentation, not the data model.

### 1.3 Why it looks like "only schools and health"

- The API describes itself that way: `apps/api/philfacilities_api/main.py` `DESCRIPTION` says "an independent, source-linked registry of Philippine schools and health facilities".
- Only schools and health have dedicated list/detail endpoints, typed profiles, sub-resource endpoints, and bulk downloads. `utility` has a detail profile only; 13 other categories have no first-class surface.
- `/v1` index and the headline fields of `/v1/statistics` name schools and health, although `by_category` contains all 16 categories.
- The data really is concentrated: schools 106,527 (46.5%), health 70,582 (30.8%) — 77.2% of published records. Next are government offices 24,893, public spaces 10,120, transport 3,451.
- The cause is sourcing, not modeling: the strongest rights-cleared datasets are DepEd masterlists/EBEIS and DOH NHFR (e.g. 60,924-school masterlist, 44,799-facility NHFR). Government offices, libraries and public spaces largely arrive via OSM/HOT discovery layers, which cannot support authoritative domain profiles.

The fix is to tell the truth about 16 categories and make the generic API work well for them — not to invent typed profiles for categories without authoritative sources.

### 1.4 Error-envelope inconsistency

`docs/api.md` §8 and `docs/data-dictionary.md` §15 document `{"error": {"code", "message", "details", "request_id"}}`. The implementation in `middleware.py::install_error_handlers` returns a **flat** object `{"code", "message", "details", "request_id"}`, and `tests/test_api_contract.py::test_validation_errors_use_the_same_envelope` locks that flat shape in. `schemas.py::ErrorBody` models the nested, unused shape and is not referenced anywhere. Currently the code and tests agree and only the docs are wrong; decide deliberately (§4.3).

### 1.5 Working-tree constraint

At the time of writing, the checkout has uncommitted user changes, including `apps/api/philfacilities_api/main.py`, `middleware.py`, `apps/web/src/app/api/page.tsx`, `docs/api.md`, and a new `scalar_theme.py` (Scalar reference UI). The plan must be applied on top of that work, not over it. Re-read those files before implementing each phase; do not overwrite them from a stale base.

## 2. Design rules for every phase

1. **Additive only.** New query parameters, new optional response fields, new endpoints. No removals, no renames, no changed defaults under `/v1`.
2. **OpenAPI is the contract.** Every shape change requires `just openapi-export`, `just typegen`, and `uv run pytest tests/test_api_contract.py -q`. CI fails on drift.
3. **One gate.** Any new aggregate or endpoint must apply the same publication gate (`public_facility_index_filter()` for indexed reads, `public_source_record_condition()` for detail reads). Never compute statistics over internal or quarantined rows.
4. **One vocabulary.** Use `/v1/taxonomy` and `taxonomy.py`; never hardcode a second category list in docs, clients, or snapshots.
5. **Missing stays missing.** Do not turn absent values into `false`, `0`, `[]`-as-truth, or "closed". Do not infer operational status, ownership, or coordinates.
6. **Synthetic stays labelled.** Keep `is_synthetic` in bulk exports and any dataset where synthetic rows can appear; no silent filtering of labelled records.
7. **Tests + docs in the same change** as code ([Contributing](contributing.md)). Generated evidence goes to `var/reports/` or `docs/operations/evidence/` with a date, not into prose.
8. **Small vertical slices.** Each phase is independently shippable and reversible.

## 3. Phase 0 — Baseline and instrumentation

**Purpose:** make the claims in §1 reproducible and give later phases a regression gate.

### Tasks

1. Add `scripts/api_dx_audit.py` (read-only):
   - Connect with `PHILFACILITIES_DATABASE_URL`.
   - Emit per-field non-null/populated counts for public facilities, overall and grouped by `facility_type`, using the same gate as the API.
   - Emit list/detail payload sizes and timings against a running API if `--api` is passed.
   - Write `var/reports/api-dx-audit-<UTC timestamp>.json`; never write into `docs/`.
   - Reuse `public_facility_index_filter()` semantics; do not open a second gate implementation.
2. Capture the dated baseline:
   - Save one run as `docs/operations/evidence/2026-11-21-api-dx-baseline.json` (the testing guide already puts benchmark evidence in `docs/operations/evidence/`).
   - Record p50/p95 with `scripts/api_benchmark.py` rather than single-run timings.
3. Add a contract test that asserts the API index links to taxonomy, statistics, and any endpoint added later, so discovery cannot silently drift.

### Acceptance

- The audit script runs against the working DB without mutating it.
- Counts for at least `relationships`, `school.resources`, `public_access_class`, `contacts`, and `postal_code` match §1.2 within a documented tolerance.
- Evidence file is dated and contains the gate definition used.

## 4. Phase 1 — First shippable slice

Three independent items; ship in this order.

### 4.1 `GET /v1/fields` — field-coverage endpoint

**Problem solved:** a developer can currently only discover by trial and error that `relationships[]` is always empty and `public_access_class` is 1% populated.

**Design**

- New endpoint `GET /v1/fields`, tag `facilities` (or `system` if reviewers prefer), `response_model=FieldCoverageResponse`.
- New schemas in `apps/api/philfacilities_api/schemas.py`:

  ```text
  FieldCoverageEntry:
    field: str                 # canonical path, e.g. "location.postal_code", "school.sector"
    scope: Literal["summary","detail","profile_school","profile_health","profile_utility"]
    populated: int             # count of public facilities with a non-null / non-empty value
    total: int                 # eligible public facilities for that field's scope
    fill_ratio: float          # 0..1, computed server-side
    semantics: str             # short note: "null means unknown", "[] means no published rows"

  FieldCoverageResponse:
    as_of: datetime
    version: str               # schema/definition version, not data release version
    fields: list[FieldCoverageEntry]
    by_category: dict[str, list[FieldCoverageEntry]] | None = None
    caveats: list[str]
  ```

- Scope denominators must be explicit: `school.sector` is eligible only for public schools, `health.licensing_status` only for public health facilities, `location.postal_code` only for facilities with a current location. Do not divide by all facilities and mislead consumers.
- Counts are derived from the canonical tables behind the existing fields — never a hand-maintained list of "important" fields. Generate the field list from a single declarative mapping in one module (e.g. `services/field_coverage.py`) that maps schema path → table/column/join and scope. That mapping is the implementation detail, not a second public vocabulary.
- Use `conditional_json(request, payload, max_age=3600)` so repeated calls are cached and ETag-able. If a single aggregation query exceeds ~500 ms on the full dataset, replace it with a materialized view refreshed after publication; that is a migration and must be its own sub-slice with a rollback plan.
- Add `"fields": "/v1/fields"` to the `/v1` index in `main.py`.
- Document in [Data dictionary](data-dictionary.md) §1 ("Reading rules") and add the endpoint to [api.md](api.md) §4.

**Tests**

- Contract: endpoint exists in OpenAPI, read-only, consistent headers, `fields` link in `/v1`.
- Integration (`tests/`, fixture DB): build synthetic fixtures with known null patterns; assert `populated`, `total`, and `fill_ratio` exactly; assert no internal/restricted facility is counted; assert `by_category` denominators.
- ETag: second request with `If-None-Match` returns 304 (reuse the 304 framing test pattern).

**Acceptance:** coverage counts reconcile with the audit from Phase 0; response is ETag-cached; no restricted rows counted; docs and generated client updated.

### 4.2 `view=compact` for facility detail

**Problem solved:** 34 keys and 5–7.5 KB to render a card or resolve a link.

**Design**

- In `apps/api/philfacilities_api/api/facilities.py`, extend `get_facility`:

  ```text
  GET /v1/facilities/{facility_id}?view=full|compact    (default: full)
  ```

- Add `FacilityCompact` to `schemas.py` — the minimal identity/location set already produced by `build_summaries()`:

  ```text
  id, slug, display_name, facility_type, facility_subtype, inclusion_class,
  ownership, location{latitude,longitude,precision,address_text,psgc_code},
  geography{psgc_code, region_name, province_name, municipality_name},
  source_refs, updated_at
  ```

- Add `build_facility_compact()` in `services/detail.py`. It must call `build_summaries()` only; it must **not** call `build_facility_detail()` (that would keep the slow query cost). Project the summary into `FacilityCompact`.
- `view=compact` omits constant fields (`publication_status`, `is_synthetic`), typed profiles, all detail-only collections, and `quality`. `view=full` remains byte-for-byte unchanged.
- Later extension point (do not implement in this slice): `include=sources,assertions,domain` on `view=compact` for on-demand provenance, and the same `view` parameter on `/v1/schools/{id}` and `/v1/health-facilities/{id}`.
- Do **not** add `?fields=` arbitrary sparse fieldsets yet: they multiply the contract-test matrix and interact badly with generated clients. Revisit after `view=` proves usage.

**Tests**

- Contract: parameter appears in OpenAPI with both literals; both views share `id`/`display_name`; default response equals the pre-change snapshot (add a golden snapshot of key set and values).
- Integration: compact payload < 2.5 KB on a representative facility; no `sources`, `school`, `health`, `contacts`, `relationships` keys; full view still contains them; 404 behavior unchanged; publication gate still applied for both views; slug aliases still resolve.
- Web/MCP clients keep using the full view — no client changes required in this slice.

**Acceptance:** compact ≤ 12 keys and ≤ 2.5 KB; `view=full` golden snapshot unchanged; no new DB queries per request; docs and generated client updated.

### 4.3 Error envelope: decide and align

**Problem solved:** docs and generated client descriptions promise one shape, the API returns another.

**Recommended decision:** keep the **flat** shape for `/v1` compatibility (it is what every handler returns and what contract tests assert), and fix the documentation and the unused `ErrorBody` schema to match. Do not wrap in `{"error": ...}` inside `/v1`; that is a breaking change. If a nested envelope is desired for ergonomics, introduce it in `/v2` with both shapes during migration.

**Tasks**

1. Change `schemas.py::ErrorBody` to the flat shape and reference it in OpenAPI error responses (or delete it if reviewers prefer undocumented error bodies — but then say so in docs).
2. Fix [api.md](api.md) §8 and [data-dictionary.md](data-dictionary.md) §15 to show the flat envelope and list actual codes (`validation_error`, `invalid_bbox`, `facility_not_found`, `rate_limit_exceeded`, `internal_error`, …).
3. Strengthen `tests/test_api_contract.py`:
   - one parametrized test over 404, 400, 422, 429, 500 paths asserting exactly `code`, `message`, `details`, `request_id` and the `X-Request-ID` header;
   - assert the documented example in `docs/api.md` matches a real 422 response (parse the fenced JSON block) so prose cannot drift again.
4. Coordinate with the in-flight `middleware.py` edits rather than replacing the file.

**Acceptance:** docs, OpenAPI, tests, and runtime agree; no status code or body key changes for existing clients.

## 5. Phase 2 — Consistency and reach

Each item is independent; do not bundle them into a single large PR.

### 5.1 One detail shape across domain endpoints

- `/v1/schools/{id}` currently returns `{facility, resources}`; `/v1/health-facilities/{id}` returns `{facility, licenses, accreditations}`; `/v1/facilities/{id}` returns `FacilityDetail`.
- Add `?view=compact|full` and `?include=` to the domain endpoints, and have `full` return `FacilityDetail` with the typed profile and domain collections populated. Keep the existing wrapper keys for backwards compatibility under the current default; make the unified shape opt-in first (e.g. `?shape=detail`), then deprecate wrappers with notice.
- Mark `/v1/schools/{id}/resources` as currently empty in its OpenAPI description until a public resource observation source exists. Do not remove the endpoint in `/v1`.

**Tests:** contract for both shapes; integration that school/health detail and generic detail return identical classification fields; no restricted accreditations or licences leak.

### 5.2 Filtered bulk downloads for every category

- Extend `downloads_routes.py` so the generic `facilities.csv` / `facilities.parquet` accept the same filters as `GET /v1/facilities` (`type`, `subtype`, `psgc`, `region_code`, `province_code`, `municipality_code`, `source`, `has_coordinates`, `location_precision`, `reference_period_*`, `q` where indexed).
- Reuse `facility_conditions()` / `public_facility_index_filter()` rather than writing a second predicate. Keep keyset pagination, streaming, CSV injection neutralization, and the same publication gate.
- Do not add filters that force full-table sorts at national scale without a benchmark; reject or document any that regress export time.
- Update [api.md](api.md) §4 "Bulk downloads" and `docs/decisions/0007` consequences if the export surface materially changes.

**Tests:** CSV/Parquet parity with list endpoint counts for a filtered category; restricted rows absent; ordering stable; download gate unchanged.

### 5.3 Response aliases and naming consistency

Additive aliases only — never rename or remove:

| Inconsistent pair | Action |
|---|---|
| `display_name` vs map point `name` | Emit `name` as an alias of `display_name` in `FacilityMapPoint` and compact detail |
| `type` filter vs `facility_type` field | Accept `facility_type` as an additional query alias; keep `type` |
| `location.precision` vs map `precision` vs `location_precision` filter | Document one canonical path in the data dictionary; add `location_precision` alias to summary response only if client demand justifies it |
| `source_refs[].source_record_id` (string) vs profile `source_record_id` (UUID) | Document the difference explicitly; do not change either type in `/v1` |

**Tests:** aliases equal canonical values; OpenAPI documents both; generated TypeScript client compiles.

### 5.4 Null vs empty-collection semantics

- Decide and document one rule for `/v1`: `null` = no value supplied/established; `[]` = no publication-cleared rows exist for that collection (not "the facility has none").
- Add the explanation to `FieldCoverageEntry.semantics` and [Data dictionary](data-dictionary.md) §1.
- Do not convert existing `[]` to `null` in `/v1`; that is a breaking change. Consider it for `/v2`.

### 5.5 Category discovery without a second vocabulary

- Keep `/v1/taxonomy` as the only vocabulary source. Do **not** add `/v1/categories`.
- Surface the existing `/v1/statistics.by_category` counts in the `/v1` index response as a link and in Scalar/OpenAPI descriptions, so the first response a developer sees states that 16 categories exist.
- Update `main.py::DESCRIPTION` to "Philippine facilities across 16 categories (schools, health facilities, government offices, libraries, public spaces, …)" and link `/v1/taxonomy`.
- Update `docs/api.md` §11 "Known gaps" and the data-dictionary §16 coverage caveats to state the source asymmetry explicitly: authoritative profiles exist mainly for schools and health because those are the authoritative rights-cleared sources; other categories are largely discovery-layer records.

**Tests:** `test_health_and_index_are_public` extended to assert the new links and the corrected description text; Markdown link check.

## 6. Phase 3 — Documentation, performance, and polish

### 6.1 OpenAPI and Scalar reference quality

- Add realistic `examples` to each response schema in `schemas.py` (labelled synthetic; never copy a real facility identity). Include at least one example with nulls and empty collections so consumers see the missing-data convention.
- Add per-endpoint descriptions covering: publication gate, freshness (`updated_at` is a PhilFacilities edit time), coordinate precision warning, and low-coverage fields via the `/v1/fields` result.
- Add error examples for 400/422/404/429 using the flat envelope.
- Integrate with the in-flight Scalar theme work (`scalar_theme.py`) rather than introducing a second docs UI. Keep `/docs` and `/openapi.json` consistent.

### 6.2 Performance and caching

- Re-run `scripts/api_benchmark.py` after each phase; store dated evidence in `docs/operations/evidence/`.
- Optimize `build_summaries()` path used by lists: avoid repeated gate subqueries, verify `facility_source_links` / `facility_locations` indexes with `EXPLAIN ANALYZE`, and consider caching `conditional_json` for taxonomy, `/v1/fields`, and source catalogue responses.
- Consider `total=false` on list endpoints to skip the `count(*)` when clients only need pages. Additive parameter, default unchanged.
- Map clusters already avoid per-row heap lookups; keep the national-viewport bound. Benchmark any change to `max_map_points` / `max_map_clusters`.
- Add `X-RateLimit-Limit` / `X-RateLimit-Remaining` headers to rate-limited responses (additive) so clients can back off intelligently.

### 6.3 Honest endpoints and future typed profiles

- Document `/v1/schools/{id}/resources` as empty until a public observation source is ingested.
- Add typed profiles for other categories **only** when a rights-cleared authoritative source exists for them. The generic `facility_type` filter plus `function_details` and `roles` already express most cross-category facts; do not fabricate a profile to make the API look symmetric.

## 7. Verification workflow (every phase)

```bash
# focused
uv run pytest tests/test_api_contract.py -q
uv run pytest -m "not integration" -q

# full gates
uv run pytest --require-integration
uv run ruff check . && uv run ruff format --check .
uv run python scripts/check_markdown_links.py

# contract regeneration after ANY schema or route change
just openapi-export
just typegen
uv run pytest tests/test_api_contract.py -q

# client/web
pnpm lint && pnpm typecheck && pnpm build

# full local gate
just check
```

Integration tests must use the dedicated `_test` database (default port 54330); never point them at the working database. Contract tests run without a live DB.

## 8. Risks, mitigations, and rollback

| Risk | Mitigation |
|---|---|
| Breaking `/v1` clients | Additive-only params/fields; golden snapshot test for `view=full`; deprecation notice before any default change |
| OpenAPI / generated client drift | `just openapi-export` + `just typegen` in the same commit; contract test fails on drift |
| Coverage counts expose restricted data | Reuse the existing publication gate in the coverage query; integration test with internal fixture rows |
| Coverage query too slow on 229k rows | `conditional_json` caching; fall back to a refresh-after-publication materialized view (separate migration with rollback) |
| Misleading coverage denominators | Explicit `scope` and `total` on every field; group counts by category; caveats in response |
| Conflict with uncommitted Scalar/docs work | Re-read modified files before each phase; coordinate ownership of `main.py`, `middleware.py`, `docs/api.md` |
| Docs drift again | Contract test parses the documented error example; link check; docs update in the same PR as code |
| Performance regression from new aliases | Benchmark gate per phase; reject changes that regress p95 beyond an agreed threshold |

**Rollback.** Phases 1–3 are additive code/config changes: revert the commit and regenerate the OpenAPI document. The only item requiring a migration is the optional materialized view in §4.1; keep it as a separate, revertable migration.

## 9. Open decisions (resolve before implementation)

1. **Error envelope** — recommend keeping flat and fixing docs (§4.3); confirm with client owners.
2. **Endpoint name** — `/v1/fields` vs `/v1/statistics/fields`; recommend `/v1/fields` for discoverability, with a link from `/v1`.
3. **Default view** — keep `full` in `/v1` for compatibility; consider `compact` as default only in `/v2`.
4. **Coverage computation** — on-demand aggregation with caches vs materialized view; decide after Phase 0 measurement.
5. **Compact list** — extend `view=compact` to `/v1/facilities` list in Phase 3 only if Phase 1 shows payload reduction is needed and benchmarked.
6. **Download filters** — confirm which indexed filters are safe to expose; exclude `q` initially if it regresses export duration.

## 10. Suggested delivery order

1. **Phase 0** baseline script + evidence file.
2. **Phase 1.1** `GET /v1/fields` — highest information gain for least contract risk.
3. **Phase 1.3** error-envelope alignment — small, fixes a concrete docs/runtime contradiction.
4. **Phase 1.2** `view=compact` — biggest payload win, self-contained.
5. **Phase 2.5** description/index/docs correction — cheap positioning fix.
6. **Phase 2.2** filtered downloads — unblocks non-school/health categories.
7. **Phase 2.1 / 2.3 / 2.4** detail unification, aliases, null semantics.
8. **Phase 3** performance, examples, polish.

Each numbered item is one PR with tests, OpenAPI regeneration, and docs in the same change.
