# PhilFacilities — Master Implementation Tracker

**Status:** Real-data pipeline operational with partial, source-limited coverage. Rights-cleared sources are published; official PSA, DepEd, DOH, CHED, and TESDA acquisition remains blocked or unverified. No nationwide-completeness claim is made.  
**Last updated:** 15 November 2026.

This is the single source of truth for execution status. Update this file when work begins, is blocked, or meets acceptance criteria. A checked box means the evidence exists — not merely that code was drafted.

## Status legend

- `NOT STARTED` — no implementation work completed.
- `IN PROGRESS` — active work with an owner/branch or concrete partial evidence.
- `BLOCKED` — waiting on source access, legal clarification, credentials, or another prerequisite.
- `REVIEW` — implementation exists and awaits review/acceptance.
- `DONE` — acceptance criteria met and evidence linked.
- `DEFERRED` — intentionally postponed with a reason.

## Current milestone summary

| Milestone | Status | Exit condition |
|---|---|---|
| M0 — Repository and design audit | REVIEW | Monorepo baseline, CI, reference design measurements |
| M1 — Source acquisition and rights | IN PROGRESS | Rights-cleared sources published; official PSA/DepEd/DOH/CHED/TESDA access remains blocked |
| M2 — Canonical model and geography | DONE | Migrations, PSGC history, source/provenance model |
| M3 — ETL and quality | DONE | Repeatable real-source pipelines, quality issues, and reports |
| M4 — Public API v1 | DONE | 39-path contract-tested read API and generated client |
| M5 — Directory and facility pages | DONE | Searchable, accessible web directory on public real data |
| M6 — Map experience | REVIEW | Precision-aware map and list fallback; production basemap provider still open |
| M7 — Public release readiness | IN PROGRESS | Rights-cleared data published; operations/legal/security gates remain open |
| M8 — Source expansion | DEFERRED | CHED/TESDA and other domains after source validation |
| M9 — Real-data integration and automation | IN PROGRESS | Real sources acquired, published, monitored, and documented |

## Current measured state (15 November 2026)

| Measure | Actual state | Evidence |
|---|---|---|
| Canonical facilities | **88,824** | `philfacilities-ingest status`; database query |
| Public facilities | **83,769** | Publication-gate query; three source-less public-status rows were removed on 15 Nov 2026 |
| Internal-only facilities | **5,055** DepEd EBEIS NCR records | `source.datasets.publication_status = internal_only` |
| Synthetic facilities in working DB | **0** | Database query |
| Registered datasets | **38** | `source.datasets` |
| Retained source releases | **47** | `source.releases` |
| Source checks | **90** | `source.source_checks` |
| Published geographic units | **43,760** BetterGov PSGC Q2 2024 | `geo.administrative_units` |
| Published population observations | **134,748** across 18 regional releases | `stats.population_observations` |
| Published PhilHealth accreditations | **24,986** across 25 provider categories | `health.accreditations` |
| Public facilities with coordinates | **70,223**, all `map_geocoded` | `core.facility_locations` |
| Public facilities without coordinates | **13,546** | Quality query; no coordinates invented |
| Located public facilities without PSGC | **14,216** | Quality query; no geography guessed |
| Open quality issues | `location_missing` 30,041; `duplicate_osm_id` 3,572; `missing_facility_name` 25; `coordinate_outside_philippines_bbox` 1 | `quality.issues` |
| OpenAPI paths | **39** | `packages/api-client/openapi.json` |
| Python tests | **80 passing** | `uv run pytest` |
| Current-location invariant | **70,223 current rows / 70,223 facilities** | Unique partial index `uq_core_facility_locations_current`; migration `0005_unique_current_location` |

These counts describe processed source records. They are not the complete national facility universe.

## M0 — Repository and design audit

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M0-01 | Initialize monorepo and root documentation | DONE | None | `apps/`, `packages/`, `docs/`, root `README.md`, `AGENTS.md`, `DATA-LICENSES.md`; all plan links resolve |
| M0-02 | Configure pnpm workspace for web/client | DONE | M0-01 | `pnpm-lock.yaml`; `pnpm install --frozen-lockfile` completes |
| M0-03 | Configure uv project/workspace for API and ingest | DONE | M0-01 | `uv.lock`; `uv sync --locked` completes; shared `philfacilities-api` dependency |
| M0-04 | Add root `justfile` commands | DONE | M0-02, M0-03 | `justfile` parses under `just` 1.x via `uvx --from rust-just just --list`; `setup`, `format`, `db-migrate`, and `openapi-export` routes executed |
| M0-05 | Add Docker Compose PostgreSQL/PostGIS | DONE | M0-01 | `infra/compose.yaml`; PostGIS 17-3.5 on 54329 and test DB on 54330; Alembic baseline applied |
| M0-06 | Add CI for lint, typecheck, tests, migrations | REVIEW | M0-02, M0-03 | `.github/workflows/ci.yml` covers ruff, pytest with PostGIS, pnpm lint/typecheck/build, and Playwright; `actionlint` and `docker compose config` pass locally. Hosted GitHub Actions observation remains the only open gate |
| M0-07 | Inspect BetterGov Fellowship website at desktop/mobile widths | DONE | Browser access | Chromium/Playwright audit at 1440/1024/768/390; screenshots in `docs/design-audit/reference/` |
| M0-08 | Extract fonts, colors, typography, spacing, nav states | DONE | M0-07 | `docs/design-audit/reference-measurements.md` records computed fonts, palette, 68px/60px header, 40px controls, nav behavior |
| M0-09 | Translate measured design into shadcn/Tailwind tokens | DONE | M0-08 | `apps/web/src/app/globals.css`, Tailwind theme, square radii, measured blue/sun/ink/wash/rule/focus tokens |
| M0-10 | Build responsive PhilFacilities header | DONE | M0-09 | `site-header.tsx`; Playwright mobile-menu test passes; axe serious/critical checks pass |

## M1 — Source acquisition and rights

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M1-01 | Acquire official Q3 2026 PSGC workbook | BLOCKED | None | Public download returned HTTP 403 behind Cloudflare on 14 and 15 Nov 2026. Evidence: `docs/operations/evidence/2026-11-15-source-access/psgc.txt`; no official file acquired |
| M1-02 | Inspect PSGC workbook sheets/headers/codes | BLOCKED | M1-01 | No official workbook to inspect; BetterGov Q2 2024 mirror supplies real geography instead (M9-03) |
| M1-03 | Acquire official DepEd school masterlist | BLOCKED | Human download/terms flow | Machine-Ready Files returned HTTP 403; no official workbook acquired |
| M1-04 | Inspect DepEd masterlist schema | BLOCKED | M1-03 | No official schema available; adapter remains fixture-tested |
| M1-05 | Acquire DepEd enrollment file(s) | BLOCKED | Official terms | Not acquired |
| M1-06 | Inspect DepEd enrollment schema/reference years | BLOCKED | M1-05 | Not inspected; synthetic year-dimensioned fixture covers parser behavior |
| M1-07 | Test DOH NHFR public export path | BLOCKED | None | `https://nhfr.doh.gov.ph/VActivefacilitiesList` returned HTTP 403 from Cloudflare; no export acquired. Evidence: `docs/operations/evidence/2026-11-14-source-access/doh-nhfr.txt` |
| M1-08 | Obtain/review DOH CSV/Excel and agreement | BLOCKED | M1-07 | Data Release and Use Agreement review not completed |
| M1-09 | Inspect DOH export and shapefile schema | BLOCKED | M1-08 | Not inspected; synthetic CSV fixture covers parser behavior |
| M1-10 | Inventory PhilHealth accredited-provider files | DONE | Public index | 27 provider-category PDF links inventoried from the public index; date basis recorded per file. Evidence: `docs/operations/evidence/2026-11-15-source-access/philhealth-inventory.txt` |
| M1-11 | Parse/inspect PhilHealth hospital PDF sample | DONE | M1-10 | Real 30 Sep 2026 hospital/infirmary PDF parsed with page/row references; official-layout regression fixture added |
| M1-12 | Complete source rights register | DONE | All registered sources | `DATA-LICENSES.md` and `docs/reports/05-source-rights-report.md` record rights, publication, personal-data, and evidence status for all 38 datasets. No formal legal review is claimed |
| M1-13 | Decide which sources/fields can be publicly redistributed | IN PROGRESS | M1-12 | Published: PhilHealth PDFs, HOT/OSM extracts, BetterGov PSGC mirror, PSA 2024 Census population via BetterGov. Blocked or internal: official PSA/DepEd/DOH/CHED/TESDA. External legal review remains open |
| M1-14 | Acquire BetterGov PSGC Q2 2024 mirror | DONE | BetterGov public API | 43,760 units from 18 regional collections; codes preserved as strings; labelled as a supplementary snapshot, not official PSA |
| M1-15 | Acquire PSA 2024 Census population via BetterGov | DONE | BetterGov public API | 134,748 observations from 18 saved regional tables; source URLs and release metadata retained |
| M1-16 | Acquire HOT/OSM health and education extracts | DONE | Public GeoParquet | 17,421 health and 52,839 education source records; ODbL attribution retained |
| M1-17 | Acquire DepEd EBEIS NCR result set | DONE | Public form | 5,055 school rows retained `internal_only`; contains school-head names and has no explicit reuse licence |
| M1-18 | Investigate CHED, TESDA, hazard, and additional agencies | DONE | Discovery only | Actual probe results recorded; no facility export or reuse permission claimed. See `docs/03-SOURCE-REGISTER.md` |

## M2 — Data model and geography

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M2-01 | Create DB schema boundaries | DONE | M0-05 | Alembic `0001_baseline` plus `0002_match_candidates`; `source`, `core`, `geo`, `school`, `health`, `quality`, `history` schemas |
| M2-02 | Implement agency/dataset/release tables | DONE | M2-01 | Models and source-catalogue integration tests expose agency, dataset, gate, release, checksum, and terms |
| M2-03 | Implement raw source record/provenance tables | DONE | M2-02 | `SourceRecord`, assertions, source links; publication tests prove public facility provenance |
| M2-04 | Implement canonical facility/source-link tables | DONE | M2-03 | Facility plus many source links; no automatic ambiguous merge path; exact-ID matching only |
| M2-05 | Implement versioned PSGC tables/crosswalk | DONE | M1-14, M2-01 | `GeographicRelease`, `AdministrativeUnit`, release-scoped uniqueness, crosswalk endpoint; real Q2 2024 release plus tests |
| M2-06 | Implement location and precision model | DONE | M2-04 | Precision enum, PostGIS geometry, current-location uniqueness, missing-coordinate tests |
| M2-07 | Implement school domain tables | DONE | M2-04 | School profile, enrollment observations by school year, resource observations; parser and API tests |
| M2-08 | Implement health/license/accreditation tables | DONE | M2-04 | Health profile, dated licenses, accreditations with category, bed count, validity, page reference |
| M2-09 | Implement change events and quality issues | DONE | M2-04 | `FacilityChangeEvent`, `QualityIssue`, history feed, explainable issues tied to releases/records |
| M2-10 | Add spatial indexes and query tests | DONE | M2-06 | GiST/source indexes in migration; bbox, nearby, precision, and bounded-area tests |
| M2-11 | Add statistical observation tables | DONE | M2-01 | `stats.population_observations` with indicator, unit, reference period, dimensions, source URL, release linkage |

## M3 — Ingestion and quality

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M3-01 | Define source adapter contract | DONE | M2-02 | `contracts.py` parse/validate/normalize protocol; parser tests for all adapters |
| M3-02 | Build PSGC ingestion | DONE | M1-14, M2-05 | Real BetterGov Q2 2024 ingestion through the raw store; leading-zero preservation; official PSA workbook remains blocked (M1-01) |
| M3-03 | Build DepEd master parser | DONE | M1-17, M2-07 | EBEIS NCR parser loads 5,055 internal-only rows; Machine-Ready adapter remains fixture-tested because official access is blocked |
| M3-04 | Build DepEd enrollment parser | DONE | M1-06, M2-07 | Fixture observations loaded with school-year dimension; no official enrollment file acquired |
| M3-05 | Build DepEd facilities/ICT/WASH parsers | DONE | Source schema inspected | Synthetic resource workbook adapter covers facility/resources/WASH observations and schema-drift behavior; official schema remains blocked |
| M3-06 | Build PhilHealth PDF parser | DONE | M1-10, M1-12 | 25 categories parsed and published; 24,986 accreditations with page/row references after the `philhealth-pdf-1.2.0` row-key repair recovered 229 rows collapsed by the earlier key scheme; Antenatal release retained but blocked after its annex-double-counting parse was withdrawn |
| M3-07 | Build DOH parser (only if permitted) | DONE | M1-09, M1-13 | Synthetic CSV adapter validates beds, coordinates, licenses, and rejects negative values; no real DOH data published |
| M3-08 | Implement idempotent release processing | DONE | M3-02 to M3-07 | Repeated loads keep counts stable, deduplicate checksums, and record `skipped_duplicate` runs. Regression: `tests/test_pipeline_reprocess.py::test_repeated_ingestion_is_idempotent` |
| M3-09 | Implement deterministic identity matching | DONE | M3 source parsers | `quality.match_candidates` plus matcher, CLI queue generation/review/merge, read-only API, and tests: idempotent generation, rejection retention, same-agency/subtype guards, accepted-before-merge guard, evidence migration, merge tombstone, change events |
| M3-10 | Implement coordinate validation/reporting | DONE | M3 source parsers | Range/partial-coordinate validation, precision distribution, `location_missing` and `location_precision_unknown` issues; current counts in `docs/reports/04-data-quality-report.md` |
| M3-11 | Build ingestion run report and source freshness status | DONE | M3-08 | JSON reports under `var/reports/`; run summary in quality API; status command and page distinguish dates |
| M3-12 | Add schema drift and source anomaly alerts | DONE | M3-11 | Required-column failures and validation issues fail closed; tests cover drift |
| M3-13 | Build BetterGov population connector | DONE | BetterGov API | 18 regional snapshots preserved immutably; missing values stay null; observations published only through the gate |
| M3-14 | Build HOT/OSM GeoParquet connector | DONE | Public extract | Named features normalized; bbox-centre coordinates recorded as `map_geocoded`; unnamed features retained in raw, not invented as facilities |
| M3-15 | Register real source probes and monitoring | DONE | Source register | `check-sources`, `check-due-sources`, `monitoring`, `/v1/monitoring`, `/v1/source-checks`; 90 checks recorded |
| M3-16 | Enforce publication gates on real datasets | DONE | M1-13 | Public queries require `publication_status = public` and a rights-cleared, approved/published release; internal/blocked evidence is excluded from detail, exports, statistics, and sources |

## M4 — Public API v1

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M4-01 | Create FastAPI app and API versioning | DONE | M2 | `/healthz`, `/v1` routers, `/docs`, `/openapi.json`; contract tests |
| M4-02 | Implement facilities list/detail | DONE | M3 published records | Cursor pagination, filters, reference-period overlap filters, detail with provenance/quality/history; integration tests on real DB |
| M4-03 | Implement geography endpoints | DONE | M3-02 | Release list/detail, units by level/parent, release-aware crosswalk; tests |
| M4-04 | Implement school endpoints | DONE | M3-03 to M3-05 | School list/detail, enrollment/resources, reference periods; tests |
| M4-05 | Implement health/accreditation endpoints | DONE | M3-06/07 | Health list/detail, licenses, accreditations preserving category/expiry; tests |
| M4-06 | Implement provenance/source endpoints | DONE | M2-03 | `/sources`, `/source-releases`, facility source evidence; tests |
| M4-07 | Implement history/change endpoints | DONE | M2-09 | Facility history and global change feed; tests |
| M4-08 | Implement bounding-box/nearby endpoints | DONE | M2-10 | `/within` and `/nearby` with area/radius limits, precision filtering, reference-period overlap, and shared facility filters |
| M4-09 | Generate OpenAPI and TypeScript client | DONE | M4-01 to M4-13 | 39-path `packages/api-client/openapi.json`, generated `schema.ts`; drift test and CI diff gate |
| M4-10 | Add rate limits, CORS, errors, caching | DONE | M4 endpoints | Middleware, structured error envelope, conditional JSON, CORS settings; contract tests |
| M4-11 | Add a local API latency baseline | REVIEW | M4-01 | `scripts/api_benchmark.py` now records real-data latency: statistics p50 3,497 ms after consolidation, facility list 2,608 ms, detail 99 ms, bbox 496 ms. Statistics was 13,685 ms before the fix. Facility-list and export optimization remain pre-launch work. Evidence: `docs/operations/evidence/2026-11-15-real-api/api-benchmark-optimized.txt` |
| M4-12 | Add top-level accreditation search | DONE | M4-05 | `/v1/accreditations` with category, facility, validity, rights-gated source linkage, filters, pagination; integration tests |
| M4-13 | Add population, monitoring, and source-check endpoints | DONE | M3-13, M3-15 | `/v1/population`, `/v1/monitoring`, `/v1/source-checks`; contract and integration tests |
| M4-14 | Capture real API examples | DONE | Real DB + running API | `docs/reports/07-real-api-examples.md` captured from `127.0.0.1:8010` with public real records only |

## M5 — Directory and profiles

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M5-01 | Implement global header/navigation | DONE | M0-10 | Measured blue header, yellow active rule, mobile menu; Playwright navigation test |
| M5-02 | Implement homepage/search entry | DONE | M4-09 | Homepage reads measured real statistics and caveats; search; e2e axe pass |
| M5-03 | Implement directory filters and result list | DONE | M4-02 | Type/ownership/precision/region/province/municipality/barangay/source-agency/search/updated-since/reference-period filters, active chips, URL state, cursor pagination, map links |
| M5-04 | Implement facility profile page | DONE | M4-02, M4-06 | Provenance, quality, change history, school/health details, map; e2e test |
| M5-05 | Implement source/dataset catalogue | DONE | M4-06 | `/data`, `/data/[dataset]`, `/sources` show rights, releases, geography-release fallback; browser-tested |
| M5-06 | Implement loading/error/empty states | DONE | M5-02 to M5-05 | Accessible `role="status"` loading state, `error.tsx`, `not-found.tsx`, empty-state copy |
| M5-07 | Accessibility and responsive pass | DONE | M5 core pages | Axe serious/critical clean on public pages; keyboard, focus, viewport, and responsive screenshot checks; no formal full-WCAG certification claimed |
| M5-08 | Verify directory and profiles against real database | DONE | M9-08 | Homepage/statistics, directory, source catalogue, and profiles read the real API; no synthetic disclosure remains when synthetic count is zero |

## M6 — Map

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M6-01 | Select permitted basemap/tile provider | BLOCKED | M0/M5 | MapLibre style reads `NEXT_PUBLIC_MAP_TILE_URL`, `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION`, and optional `NEXT_PUBLIC_MAP_TILE_MAXZOOM`; OSM raster tiles remain the attributed demo default. No licensed production provider selected. See `docs/decisions/0006-basemap-provider.md` |
| M6-02 | Integrate MapLibre | DONE | M4-08 | `map-explorer.tsx`, `location-map.tsx`; versioned worker copied and configured; renders with attribution |
| M6-03 | Implement viewport queries and debounce | DONE | M4-08 | Debounced viewport loads pass active filters to `/v1/facilities/within`; bounded API limits |
| M6-04 | Implement marker clustering | DONE | M6-02 | Clustered GeoJSON source, cluster expansion, counts |
| M6-05 | Implement selected facility panel | DONE | M5-04, M6-02 | Marker click and list selection share the selected panel |
| M6-06 | Implement low-precision location treatment | DONE | M3-10 | Lower opacity/smaller markers, area-level language, precision labels, no precise-pin claim |
| M6-07 | Mobile map/list sheet | DONE | M6-02 to M6-06 | Mobile map/list tabs; Playwright mobile test switches to list |
| M6-08 | Add map failure fallback to directory | DONE | M6 | Tile-error notice renders on mobile and desktop; text results remain available; Playwright blocks tile requests and asserts the notice |

## M7 — Public release readiness

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M7-01 | Complete data publication review | IN PROGRESS | M1-13, M3 | Rights-cleared PhilHealth, OSM, BetterGov PSGC, and PSA population datasets are published. Official PSA/DepEd/DOH/CHED/TESDA publication remains blocked. No formal legal review |
| M7-02 | Publish API docs and data dictionary | DONE | M4 | `/api`, OpenAPI docs, `docs/DATA-DICTIONARY.md`, public `/data/dictionary`; missing-value semantics, precision, provenance, redistribution, identity review, caveats |
| M7-03 | Publish bulk exports where permitted | DONE | M7-01 | CSV/Parquet exports are publication-gated; verified against the real database: CSV 83,769 rows (31 MB), Parquet 83,769 rows (6.3 MB). Evidence: `docs/operations/evidence/2026-11-15-real-exports/exports.txt` |
| M7-04 | Add data quality/status pages | DONE | M3-11 | `/status`, quality summary, issue counts, run summaries, caveats |
| M7-05 | Configure production backups and test restore | REVIEW | deployment | `scripts/db_backup.sh` and `scripts/db_restore_verify.sh`; local Compose backup and scratch restore passed at real-data scale on 15 Nov 2026: 90.7 MB dump, 197 TOC entries, 15/15 checks (88,824 facilities, 235,049 source records, 47 releases). Evidence: `docs/operations/evidence/2026-11-15-backup-restore/real-scale/`. Production schedule, retention, off-host copy, encryption, PITR, and alerting are not configured |
| M7-06 | Security/dependency review | REVIEW | release candidate | `docs/operations/security-review.md`; MapLibre XSS advisory fixed, CSV injection, request IDs, cursor limits, rate limiter, CSP nonce; `pip-audit` and `pnpm audit` clean. External pen test, production WAF/TLS/secret manager, and deployed-origin CSP verification remain open |
| M7-07 | Add monitoring and incident runbook | REVIEW | deployment | `docs/operations/incident-runbook.md`, `docs/operations/source-monitoring-runbook.md`, `scripts/smoke_check.sh`; API access logs include request ID, path, status, duration. No monitoring provider, paging, on-call rotation, or hosted scheduled-run observation |
| M7-08 | Prepare public launch/release notes | BLOCKED | all gates | Release blocked by remaining source-access, legal, and operations gaps |
| M7-09 | Publish contribution guide, issue/PR templates, and security route | DONE | M0-01, M7-06 | `CONTRIBUTING.md`, `SECURITY.md`, issue forms, PR template; no invented contact address or source claim |
| M7-10 | Implement historical release comparison | DONE | M3-08 | `philfacilities-ingest compare-releases <dataset> [--from LABEL --to LABEL] [--json]` compares retained source records by key and payload hash plus facility links, without mutation. Regression: `tests/test_pipeline_reprocess.py::test_release_comparison_reports_rows_and_links_without_mutation` |
| M7-11 | Quarantine failed ingestion without hiding a published release | DONE | M3-08 | A new parse/validation failure is `failed`/`quarantined`; a previously published release keeps `publication_status=published`. Regression: `tests/test_pipeline_reprocess.py::test_failed_new_release_is_quarantined_and_keeps_previous_public_release` |
| M7-12 | Probe discovery-only sources on a recurring schedule | DONE | M1-18 | `discover-sources` CLI records HTTP/blocker/TLS results for 25 discovery-only official targets without registering, accepting terms, downloading bulk files, or publishing; monthly workflow uploads JSON evidence. Tests: `tests/test_discovery.py` |

## M8 — Later expansion

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M8-01 | CHED institution source acquisition | DEFERRED | Official export/terms | HEIDA directory reachable (HTTP 200); no verified bulk export, public API, or reuse terms |
| M8-02 | TESDA provider source acquisition | DEFERRED | Official export/terms | Directory page reachable but monitor records `access_blocked`; no provider-level bulk export or reuse terms |
| M8-03 | Additional PhilHealth provider categories | DEFERRED | M1-10 | All 25 currently published categories loaded; a new category requires index/parser review |
| M8-04 | Public correction workflow | DEFERRED | M5 | Reviewed moderation/audit flow not built |
| M8-05 | Health Access Index | DEFERRED | Facility coverage + defensible population/travel methodology | Methodology not reviewed |
| M8-06 | School Access Index | DEFERRED | School/learner data + defensible access/capacity methodology | Methodology not reviewed |
| M8-07 | Hazard exposure module | DEFERRED | Valid facility coordinates + hazard source terms | No hazard layer acquired; GeoRiskPH TLS and PHIVOLCS map TLS failures; DENR-MGB 403 |
| M8-08 | Infrastructure project crosswalk | DEFERRED | BetterGov/agency project source terms | Auditable relationship data not built |
| M8-09 | Additional agency facility discovery | DEFERRED | Source access | DILG/BFP/PNP/BJMP/DSWD/DPWH/NAMRIA/NHA/NLP/LWUA/DOTr/DICT probes recorded; no verified facility export or reuse permission |

## M9 — Real-data integration and automation

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| M9-01 | Re-probe every registered source with recorded evidence | DONE | None | 38 datasets probed on 15 Nov 2026; exact statuses in `docs/operations/evidence/2026-11-15-source-access/source-probes-2026-11-15.txt` and `docs/reports/01-source-directory.md` |
| M9-02 | Apply publication gates to real sources | DONE | M1-13 | Only `approved_with_attribution` datasets with approved/published releases are public; internal/blocked records excluded from all public surfaces |
| M9-03 | Load BetterGov PSGC Q2 2024 mirror | DONE | M1-14 | 43,760 units; raw JSON preserved; geography release `PSGC-Q2-2024-BETTERGOV` |
| M9-04 | Load PSA 2024 Census population snapshots | DONE | M1-15 | 134,748 observations; 18 releases; `/v1/population` exposes source URL, indicator, unit, and attribution |
| M9-05 | Load PhilHealth provider categories | DONE | M1-10 | 25 published categories, 24,986 accreditations, 13,546 linked facilities; one Antenatal release retained but blocked after its annex-double-counting parse was withdrawn; one linked PDF returns 404 |
| M9-06 | Load OSM health and education facilities | DONE | M1-16 | 17,410 health and 52,824 education linked facilities; all coordinates `map_geocoded`; crowd-sourced label retained |
| M9-07 | Load DepEd EBEIS NCR internal-only | DONE | M1-17 | 5,055 internal records; excluded from public API, exports, statistics, and source evidence |
| M9-08 | Remove synthetic production records | DONE | M9-03 to M9-07 | Working database synthetic count is 0; `/v1/statistics` reports `synthetic: 0` |
| M9-09 | Expose real data through the API and web app | DONE | M9-03 to M9-08 | 39 paths; real statistics, directory, profile, map, and downloads verified against the configured database |
| M9-10 | Add due-source checks and append-only monitoring | DONE | M3-15 | `check-due-sources` uses `next_check_at`; monitoring endpoints expose latest checks and statuses |
| M9-11 | Schedule checks and rights-cleared refreshes | REVIEW | M9-10 | `.github/workflows/source-checks.yml` daily checks, weekly/manual refresh; `scripts/refresh_approved_sources.sh`; hosted run not observed |
| M9-12 | Produce all required reports | DONE | M9-01 to M9-11 | `docs/reports/01`–`07` generated from the configured database and live API |
| M9-13 | Fix bulk-export scaling | DONE | M7-03 | Location and source-evidence lookups chunk facility IDs below PostgreSQL's bind-parameter limit; regression test forces multi-chunk loading; real exports verified |
| M9-14 | Triage OSM duplicate IDs and missing names | IN PROGRESS | M9-06 | 3,572 `duplicate_osm_id` and 25 `missing_facility_name` issues remain visible; no silent merge or deletion |
| M9-15 | Increase PSGC linkage for OSM facilities | IN PROGRESS | M9-03, M9-06 | 14,216 located public facilities lack PSGC; no geography guessed from coordinates or names |
| M9-16 | Align data dictionary, rights register, runbooks, and tracker | DONE | M9-12 | `README.md`, `DATA-LICENSES.md`, `docs/03`–`12`, `docs/DATA-DICTIONARY.md`, reports 01–07, and this tracker now describe the measured real-data state, source limits, and open launch gates |
| M9-17 | Enforce one current location and correct statistics inflation | DONE | M9-08, M4-01 | Migration `0005_unique_current_location` retired 11 duplicate current rows and added a partial unique index. `/v1/statistics` now reports 83,769 public facilities and 70,223 located facilities, matching the canonical tables. Regression test covers the invariant. Evidence: `docs/operations/evidence/2026-11-15-real-data-cleanup/location-invariant.txt` |
| M9-18 | Re-check migrations on a fresh database | DONE | M2-01, M9-17 | A scratch PostgreSQL/PostGIS database upgraded from no revision through the then-current head, and every pytest session now drops the schemas and upgrades an empty database to `head` (currently `0006_search_trigram_indexes`) before loading fixtures |
| M9-19 | Reconcile the Antenatal release and its residual derived artifacts | DONE | M3-06, M9-05 | Release now records the historical 6,562-row parse as `withdrawn`/`blocked`, the run explains the annex double-count, the dataset is blocked, and the corrected parser re-reads 3,221 provider rows. Residual repair: 3,178 facilities restored from `EMCB-ANTE` to their recorded prior subtypes and 3,184 source-less history events exported/deleted; 0 `EMCB-ANTE` facilities and 0 source-less events remain. Zero Antenatal records remain published. Evidence: `docs/operations/evidence/2026-11-15-real-data-cleanup/` |
| M9-20 | Repair the PhilHealth source-record key collision and reprocess affected releases | DONE | M3-06, M9-05 | Parser `1.1.0` hashed name + municipality + expiry + page but not the physical row number, collapsing 229 rows across GAMOT (204), FDC (19), YAKAP (4), and HOSP (2). Parser `1.2.0` includes the row number, an explicit `--reprocess` path re-keys records in place without changing record IDs, and unchanged linked rows are skipped so a reparse cannot churn canonical attributes. All four releases now have `row_count_parsed = source.records`; 235,049 records, 24,986 accreditations, and 100,275 source links; 0 artifact history events and 0 duplicate per-record issues. Evidence: `docs/operations/evidence/2026-11-15-philhealth-record-key-repair/` |
| M9-21 | Complete the final data.md acceptance audit | DONE | M9-01 to M9-20 | Verified 38 datasets, 47 releases, 90 source checks, 88,824 facilities (83,769 public / 5,055 internal / 0 synthetic), 235,049 source records, 24,986 accreditations, 100,275 source links, 70,223 current locations, 100,304 history events, 134,748 population observations, 39 OpenAPI paths, and 80 passing tests; live smoke and web pages pass. Evidence: `docs/operations/evidence/2026-11-15-final/validation.txt` |
| M9-22 | Add reference-period filtering to public facility searches | DONE | M4-02, M4-04, M4-08, M5-03 | Inclusive overlap filters on `/v1/facilities`, `/within`, `/nearby`, `/schools`, and `/health-facilities`, wired through directory, pagination, map links, and map viewport queries; invalid ranges return `invalid_reference_period`. Live evidence: same-day 2026-09-30 returns 9,883; from 2026-10-01 returns 0; reversed range returns 400. Evidence: `docs/operations/evidence/2026-11-15-final/validation.txt` |
| M9-23 | Replace correlated facility search with indexed branches | DONE | M4-02, M9-17 | Search is an uncorrelated `UNION` over name, official name, source key, address, and PSGC-level locality branches. Migration `0006_search_trigram_indexes` adds trigram indexes; model indexes cover the text and locality columns. Measured medians: Mulanay 252 ms (40), Manila 638 ms (832), Bacolod 1,869 ms (140), no-match 88 ms. Evidence: `docs/operations/evidence/2026-11-15-final/validation.txt` |

## Active work log

Append entries here. Every entry should include date, tracker IDs, branch/PR/commit if applicable, tests, and evidence.

| Date | IDs | Work / evidence | Outcome / blocker |
|---|---|---|---|
| 2026-11-14 | Planning baseline | Connected plan documents created; no implementation claimed | Ready for repository initialization |
| 2026-11-14 | M0-01–M0-10 | Monorepo, workspaces, Compose/PostGIS, measured design tokens, responsive header; design evidence in `docs/design-audit/` | M0 in REVIEW pending a hosted CI run |
| 2026-11-14 | M2-01–M2-10 | PostGIS schema and Alembic baseline; provenance, source links, geography releases, school/health domain, history, quality, spatial indexes | M2 DONE |
| 2026-11-14 | M3-01–M3-12 | Synthetic fixtures; adapters for PSGC/DepEd/DOH/PhilHealth; idempotent load; reports; quality issues; schema-drift tests | Real-source acquisition still blocked under M1 |
| 2026-11-14 | M4-01–M4-10 | FastAPI read API, OpenAPI contract, generated TypeScript client, rate limits/CORS/errors | Contract and integration tests pass |
| 2026-11-14 | M5-01–M5-07 | Directory, map, facility profiles, data/source catalogue, API/status pages, loading/error states | Playwright and axe checks pass |
| 2026-11-14 | M6-02–M6-08 | MapLibre clustering, selection, precision treatment, mobile tabs, list fallback, attribution | M6-01 basemap provider remains BLOCKED |
| 2026-11-14 | M1-01–M1-13 | Source access attempts and rights register: PSGC 403, PhilHealth sample checksum, DepEd/DOH unacquired | No official data published at that point |
| 2026-11-14 | M7-05 | Backup/restore tooling and scratch restore verification | Local procedure tested; production controls open |
| 2026-11-14 | M7-06, M7-07 | Internal security/dependency review, CSP, smoke check, incident runbook | REVIEW pending production controls and external testing |
| 2026-11-14 | M3-09 | Deterministic identity matching, review queue, merge workflow, API, tests | DONE; no automatic merges |
| 2026-11-15 | M3-02, M3-08 | Corrected synthetic barangay code shape and S3 raw-store read path | DONE; idempotent |
| 2026-11-15 | M4-02, M4-08, M5-03, M6-03 | Locality/address/source-ID search; expanded directory filters; filter-preserving pagination and map queries | DONE |
| 2026-11-15 | M5-06, M6-02 | Fixed MapLibre worker under Next.js/Turbopack; accessible loading state | DONE |
| 2026-11-15 | M7-05, M7-07 | Refreshed backup/restore and smoke checks after demo reload | Local procedure verified; production controls open |
| 2026-11-15 | M0, M4, M5, M6, M7 | Full local verification of synthetic MVP: ruff, pytest, pnpm, Playwright, smoke, restore | Historical baseline only |
| 2026-11-15 | M6-01, M0-01 | Configurable basemap provider; ADRs 0001–0007 | Production tile provider remains BLOCKED |
| 2026-11-15 | M0-06, M4-09 | Contract-drift test comparing committed OpenAPI with `app.openapi()`; CI regeneration check | OpenAPI/client cannot silently drift |
| 2026-11-15 | M7-09 | Contribution guide, security route, issue/PR templates, working dev recipes | DONE |
| 2026-11-15 | M1-10–M1-12 | PhilHealth inventory and parser work; real hospital PDF parsed with page references | Publication gated until rights decision |
| 2026-11-15 | M5-07, M0-06 | Mobile overflow fix, hydration marker, responsive screenshot audit, CSP nonce checks | DONE |
| 2026-11-15 | M4-11 | Local read-API latency baseline | REVIEW; baseline predates real-data load |
| 2026-11-15 | M1-14, M9-03 | Loaded BetterGov PSGC Q2 2024 mirror: 43,760 units | Published as supplementary geography |
| 2026-11-15 | M1-15, M3-13, M9-04 | Loaded 18 PSA 2024 Census population snapshots: 134,748 observations | Published with attribution; not live PSA data |
| 2026-11-15 | M1-16, M3-14, M9-05, M9-06 | Loaded 25 PhilHealth PDFs (24,757 accreditations) and HOT/OSM health/education extracts (70,234 linked facilities) | Published with attribution and coordinate caveats |
| 2026-11-15 | M1-17, M9-07 | Loaded DepEd EBEIS NCR: 5,055 school rows | `internal_only`; excluded from public surfaces |
| 2026-11-15 | M9-08 | Purged synthetic production records | 88,824 canonical facilities, 0 synthetic |
| 2026-11-15 | M9-08, M9-14 | Removed 4,802 unprovenanced Antenatal health profiles and 3 source-less public facilities (`P`, `G`, `SEC`) left by an earlier parser pass; regenerated reports 01–05 | Public-status and API-visible counts now agree at 83,769 |
| 2026-11-15 | M9-01, M9-10 | Re-probed all sources; 86 checks recorded; added monitoring endpoints and due-source scheduler commands | Blockers documented; no bypass attempted |
| 2026-11-15 | M9-09, M4-12, M4-13 | Added `/v1/accreditations`, `/v1/population`, `/v1/monitoring`, `/v1/source-checks`; regenerated 39-path OpenAPI/client | Real API verified on `127.0.0.1:8010` |
| 2026-11-15 | M9-12, M4-14 | Regenerated reports 01–05 and captured live API examples | `docs/reports/01`–`07` reflect real public data |
| 2026-11-15 | M9-11, M7-07 | Added scheduled source-check workflow, rights-cleared refresh script, and monitoring runbook | REVIEW; no hosted run or alert channel configured |
| 2026-11-15 | M9-13, M7-03 | Fixed bulk exports failing on large `IN` lists by chunking location and evidence queries; added multi-chunk regression test | Real CSV 83,769 rows / 31 MB; Parquet 83,769 rows / 6.3 MB |
| 2026-11-15 | M4-11, M9-17 | Consolidated `/v1/statistics` aggregation and enforced one current location per facility; migration `0005_unique_current_location` retired 11 duplicate current rows | Statistics p50 13,685 ms → 3,497 ms; counts now 83,769 public / 70,223 located; 70 Python tests passing |
| 2026-11-15 | M9-18, M7-07 | Re-ran migrations on a scratch database through `0005`; raised the smoke-check timeout to cover the measured statistics latency | Fresh migration path verified; smoke check passes against real data; production monitoring still open |
| 2026-11-15 | M9-16 | Rewrote tracker from synthetic-MVP status to measured real-data status and aligned the data dictionary, security review, backup runbook, decisions, and deployment docs | Documentation matches the working database; no claim of nationwide coverage or legal review |
| 2026-11-15 | M3-06, M9-05, M9-19 | Reconciled the Antenatal release: recorded the historical 6,562-row parse as `withdrawn`/`blocked`, documented the expiry/sector annex double-count, blocked the dataset, and bumped the corrected parser to `philhealth-pdf-1.2.0` (3,221 provider rows on re-parse) | Zero Antenatal records remain published; reports 01–05 and 07 regenerated; 70 tests, ruff, pnpm lint/typecheck/build, smoke, and web pages verified |
| 2026-11-15 | M9-19, M9-08 | Repaired residual withdrawn-parse artifacts: restored 3,178 `EMCB-ANTE` facility subtypes from their recorded prior values, exported and deleted 3,184 source-less history events (3,178 subtype updates and six net-zero name toggles), and corrected the public no-coordinate count to 13,546 | 0 `EMCB-ANTE` facilities, 0 source-less history events, 0 public facilities without provenance; reports 01–05 and 07 regenerated |
| 2026-11-15 | M9-12, M9-16 | Completed the final deliverable audit: report 01 now lists discovery-only sources (DOH HFSRB, PSA API, TESDA assessment centers, hazard agencies, Open Data PH); report 03 adds normalized field mappings, duplicate-key counts, and the no-spreadsheet note; report 04 adds matched/unmatched/ambiguous and cross-agency identity counts; report 02 excludes healthy `not_modified` checks from failures | Reports match the measured database; 71 tests, ruff, pnpm lint/typecheck/build, smoke, and web pages verified |
| 2026-11-15 | M3-06, M9-05, M9-20 | Found and repaired the `philhealth-pdf-1.1.0` source-record key collision: the key omitted the physical row number, silently collapsing 229 rows across GAMOT (204), FDC (19), YAKAP (4), and HOSP (2). Added an explicit `--reprocess` path that re-keys existing records by preserved page/row reference (record IDs and links retained), skips unchanged linked rows, and refuses to orphan stored records. Reprocessed the four releases; exported and reverted 5,387 re-application attribute changes and 10,566 duplicate `location_missing` issues created by the first pass | 235,049 source records, 24,986 accreditations, 100,275 links; facilities unchanged at 88,824; 0 artifact history events; 0 duplicate per-record issues; 30,041 open `location_missing`; reports 01–05 regenerated; 75 tests pass |
| 2026-11-15 | M7-05 | Re-ran the backup and scratch-restore verification against the current real-data database | 90.7 MB dump, 197 TOC entries, 15/15 checks (88,824 facilities, 235,049 source records, 47 releases); production retention/PITR still open. Evidence: `docs/operations/evidence/2026-11-15-backup-restore/real-scale/` |
| 2026-11-15 | M7-10, M7-11, M7-12 | Added read-only `compare-releases`, quarantined failed new releases while preserving the published release, and added recurring `discover-sources` probes with a monthly workflow | 80 tests pass; no hosted scheduled run observed |
| 2026-11-15 | M9-21 | Completed the data.md acceptance audit against the working database and live API; recorded actual counts, public/private boundary, backup result, and remaining blockers | 38 datasets, 47 releases, 88,824 facilities / 83,769 public, 24,986 accreditations, 39 OpenAPI paths, 80 tests; no hosted, legal, or nationwide claim. Evidence: `docs/operations/evidence/2026-11-15-final/validation.txt` |
| 2026-11-15 | M9-22, M4-02, M4-04, M4-08, M5-03 | Added inclusive reference-period overlap filters to all public facility search endpoints and wired them through directory chips, pagination, map links, and map viewport queries | Live same-day filter returns 9,883; later start returns 0; reversed range returns 400 `invalid_reference_period`; API tests cover school/health matches, zero matches, and invalid ranges |
| 2026-11-15 | M9-23, M4-02, M9-17 | Replaced correlated search `EXISTS` with an uncorrelated indexed `UNION` over name, official name, source key, address, and locality branches; added migration `0006_search_trigram_indexes` and model indexes | Medians: Mulanay 252 ms, Manila 638 ms, Bacolod 1,869 ms, no-match 88 ms; full suite and live smoke pass |
| 2026-11-15 | M9-21, M9-22, M9-23 | Re-ran the final acceptance verification after the reference-period and search changes: 80 pytest tests, 47 Playwright passes with 5 intentional skips, 32 responsive checks, 89 Markdown links, 39 OpenAPI paths, and real-data smoke | Evidence refreshed at `docs/operations/evidence/2026-11-15-final/validation.txt`; the earlier synthetic-MVP report is archived alongside it |

## Decision log

| Date | Decision | Rationale | Revisit when |
|---|---|---|---|
| 2026-11-14 | Monorepo with independently deployable web/API/ingest apps | Shared contracts/docs; easier open-source contribution | Separate maintainers/releases justify extraction |
| 2026-11-14 | FastAPI + PostgreSQL/PostGIS + Next.js/shadcn/Tailwind + MapLibre | Python for ETL, spatial DB, typed API, accessible UI, open map renderer | Measured requirements contradict choice |
| 2026-11-14 | Reference BetterGov Fellowship visual system, not its layout | User requirement; product needs directory/map UX | Reference site changes; re-audit before major redesign |
| 2026-11-15 | Publish only rights-cleared sources; block the rest in code | Viewability is not permission to redistribute | A source's terms/access evidence changes and is reviewed |
| 2026-11-15 | Publish PhilHealth PDFs, HOT/OSM extracts, BetterGov PSGC, and PSA population via BetterGov | Each has recorded attribution or open-licence evidence and an enforced gate | Source terms change or a formal legal review disagrees |
| 2026-11-15 | Keep DepEd EBEIS internal-only | Contains school-head personal names and has no explicit reuse licence | DepEd terms and a privacy review permit publication |
| 2026-11-15 | Treat OSM records as crowd-sourced map features, not an official registry | OSM is not DOH/DepEd and coordinates are bbox centres | Official facility registries become accessible |
| 2026-11-15 | Do not infer PSGC or coordinates for unmatched records | Fabricated geography would misrepresent precision and coverage | An official crosswalk or source coordinate is acquired |
| 2026-11-14 | Exact source-ID matching only; ambiguous matches are queued, never auto-merged | No silent merges; deterministic evidence creates review candidates | New matching evidence or algorithm version requires re-review |
| 2026-11-14 | Use logical `pg_dump`/`pg_restore` for the tested backup path | Works with Compose and any PostgreSQL 17/PostGIS target; verifiable without provider-specific tooling | Production provider selects managed PITR/snapshot strategy |
| 2026-11-14 | Do not publish the synthetic-MVP checkout in that pass | The initial pass had no commit, remote, or green hosted run | Superseded on 2026-11-15 by the public-repository decision below |
| 2026-11-15 | Publish the code, documentation, and non-restricted evidence in a public GitHub repository | The project is an open, source-linked platform; raw restricted source files, database dumps, `.env` files, and generated build artifacts remain excluded by `.gitignore` | A source term, privacy review, or security finding requires private handling |
