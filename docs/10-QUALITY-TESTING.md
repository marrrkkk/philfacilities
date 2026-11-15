# 10 — Quality, Testing, and Release Gates

## 1. Testing philosophy

A passing API test is not proof that the source data is correct. PhilFacilities needs separate tests for parser behavior, data integrity, entity resolution, provenance, API contracts, map performance, and user experience.

## 2. Ingestion tests

- Unit tests for CSV/XLSX/PDF parsers using synthetic or publication-approved fixtures.
- Golden-file tests for critical extracted table rows and column mappings.
- Schema drift tests: unexpected missing/renamed columns must fail closed.
- Idempotency tests: same file processed twice creates no duplicate release/record.
- Reprocessing tests: new parser version can reproduce normalized records from preserved raw input.
- Null semantics tests: blank, zero, unknown, not applicable, and false remain distinct.
- Date and number locale tests.
- Coordinate range and precision tests.
- Row count and duplicate source-ID anomaly thresholds.

Current ingestion and parser coverage:

- `tests/test_rights.py::test_philhealth_source_keys_keep_repeated_physical_rows_distinct` proves that identical provider text on the same PDF page still receives a distinct source-record key per physical row, so repeated rows cannot collapse.
- `tests/test_rights.py::test_rights_vocabulary_is_explicit_and_conservative` proves that `publicly_available_verified` is accepted and public-compatible while restricted and review-required states remain non-public.
- `tests/test_rights.py::test_public_availability_still_requires_an_approved_gate` proves that public availability alone does not bypass the publication gate.
- `tests/test_rights.py::test_philhealth_two_column_annex_is_not_parsed_as_providers` proves that the two-column expiry/sector annex is not counted as provider rows.
- `tests/test_pipeline_reprocess.py::test_reprocess_adds_rows_collapsed_by_an_older_key_scheme` runs the real ingestion pipeline twice: an older key scheme collapses four rows to one, then an explicit `reprocess=True` pass restores four distinct records, skips the one unchanged linked row, and preserves the retained record ID and facility link. The test is marked integration and uses synthetic fixture data only.
- `tests/test_pipeline_reprocess.py::test_failed_new_release_is_quarantined_and_keeps_previous_public_release` ingests a published release, then a second release whose parser raises. The new release is `failed`/`quarantined`, while the first release and its public facility remain published.
- `tests/test_pipeline_reprocess.py::test_repeated_ingestion_is_idempotent` proves the same checksum returns `skipped_duplicate` and does not create a second release or additional source records.
- `tests/test_pipeline_reprocess.py::test_release_comparison_reports_rows_and_links_without_mutation` compares two retained releases by source-record key, payload hash, and facility link, and verifies the accounting invariants.
- `tests/test_discovery.py` proves discovery probes record a successful HTTP 200, an access block, and a transport/TLS failure without registering or publishing anything.

## 3. Data quality checks

### Current measured state (15 November 2026)

- 92,422 canonical facilities; 61,806 pass the public gate; 30,616 are non-public, including the 5,055 DepEd EBEIS rows; 0 are synthetic.
- 44,751 public facilities have coordinates, all `map_geocoded`; 17,055 public facilities have no location.
- 14,216 located public facilities have no PSGC assignment.
- Open issues: `location_missing` 30,041; `duplicate_osm_id` 3,572; `missing_facility_name` 25; `coordinate_outside_philippines_bbox` 1.
- 4,802 unprovenanced Antenatal health profiles and 3 source-less public-status facilities were removed after an earlier parser pass; public-status and API-visible counts now agree.
- Residual artifacts from the same withdrawn parse were repaired on 2026-11-15: 3,178 facilities had `facility_subtype = 'EMCB-ANTE'` restored to the prior value recorded in their change events (3,103 Postpartum, 73 Transvaginal Ultrasound, 1 Clinical Laboratory, 1 INF/DISP), and 3,184 source-less change events (3,178 subtype updates plus six net-zero name toggles) were exported to the evidence directory and deleted. No source-less change events remain.
- The Antenatal PDF's first 6,562-row parse was withdrawn after review: the two-up PDF's expiry/sector annex (pages 121–240) had been counted as provider rows. The corrected parser reads 3,221 provider rows; no Antenatal records are published until a validated re-ingestion.
- Population: 134,748 observations across 43,768 PSGC codes and 18 releases; 43 zero values and 0 null values in the current snapshot.

### Identity

- required source IDs and uniqueness within release;
- duplicate source identifiers;
- conflicting facility names for same ID;
- unresolved/ambiguous cross-source matches.

### Geography

- PSGC code exists in the selected version;
- valid parent-child relationships;
- unmapped labels surfaced;
- code leading zeros preserved;
- historical geographic code changes retained.

### Coordinates

- valid lat/lon ranges;
- plausibility within Philippines area (flag only, don't silently delete);
- centroid and low-precision points identified;
- mass duplicate/default coordinates flagged;
- map display rules tested against precision category.

### Domain-specific

- school year present for enrollment/facility observations;
- counts nonnegative where appropriate;
- missing not converted to zero;
- bed count and accreditation expiry parse checks;
- PhilHealth category and sector code mappings have source evidence.

### Provenance

- every public source-derived field links to source record/release;
- publication date/reference period/retrieval time are distinct;
- all publicly exposed datasets pass publication rights gate;
- last successful ingestion shown accurately.

## 4. Entity resolution tests

Implemented in `tests/test_identity_matching.py` (PostGIS integration):

- exact source IDs match deterministically;
- name-only similarity never auto-merges;
- same name in different LGUs remains separate;
- source conflicts create review candidates;
- rejected candidates are not repeatedly suggested without new evidence;
- merge operations preserve full audit history;
- accepting a candidate is a separate decision from merging it;
- merges move source evidence and retire the duplicate as an internal `merged` tombstone;
- public match-candidate responses omit reviewer name and review note;
- a real `run_ingestion` call queues a candidate and an `info` quality issue through the
  ingestion-time hook while creating two separate public facilities, proving no implicit merge.

The queue tests seed two synthetic facilities in different agencies with the same normalized name,
PSGC unit, type, and address, exercise the real matcher, accept/reject, merge, and clean up all
seeded rows. They prove generation is idempotent and that a rejected candidate is not re-created on
a later scan. The ingestion-hook test uses a unique synthetic agency and release, invokes the real
`DOHNHFRAdapter` pipeline against an existing demo facility's name and PSGC, asserts the queued
candidate and quality issue, and removes every seeded row.

## 5. API tests

- Pydantic schema and response validation;
- pagination stability during updates;
- source/provenance response completeness;
- permission/publication gates, including exclusion of internal-only and blocked evidence;
- bounding-box and nearby spatial queries;
- maximum result and query complexity limits;
- error schema and status codes;
- OpenAPI compatibility, exact 39-path contract, and generated TypeScript client drift;
- rate-limit, CORS, ETag, and cache tests;
- bulk-export parity with the facility endpoints, including a forced multi-chunk lookup regression test.

## 6. Web tests

Implemented in `apps/web/e2e/app.spec.ts`:

- Playwright end-to-end tests for directory search, filters, facility profile, map selection, mobile filter sheet, source details, data dictionary, and error/empty states.
- Keyboard tests for the skip link, desktop nav reachability, keyboard search submission, the measured 3px focus ring, and Escape-to-close with focus return in the mobile menu. Interactive tests wait for the `<html data-hydrated="true">` marker from `hydration-marker.tsx`; without it, keystrokes typed before hydration are reconciled back to the input's `defaultValue` and silently lost, which makes the test race the client bundle instead of the feature.
- Accessibility checks with axe or equivalent on the public pages.
- Content Security Policy checks: a fresh nonce per response, a nonce on every script tag, no `unsafe-inline` in `script-src`, and no policy violations on public pages or the MapLibre map.
- Responsive screenshots at 390, 768, 1024, 1440, and 1920px in `docs/design-audit/implementation/`, plus an e2e assertion that every public page stays inside the mobile viewport.
- Design-token regression against the audited BetterGov reference system (fonts, header heights, square 40px controls, palette, responsive header breakpoint), not against its page layout.
- Directory remains usable if map tiles fail.
- Map markers with unknown/low precision do not imply precise locations.

## 7. Performance tests

A local serial baseline exists in [`scripts/api_benchmark.py`](../scripts/api_benchmark.py). It
records p50/p95 latency and response sizes for health, statistics, facility list/detail, a bounding
box query, and the source catalogue against a running API. It discovers a real public facility for
the detail sample and is explicitly a local smoke benchmark, not a load test.

Latest measured run against the real database after the statistics aggregation fix (5 samples,
loopback, 15 November 2026):

| Endpoint | p50 | p95 | Response bytes |
|---|---:|---:|---:|
| `/healthz` | 8 ms | 10 ms | 102 |
| `/v1/statistics` | 3,497 ms | 3,676 ms | 1,905 |
| `/v1/facilities?limit=20` | 2,608 ms | 2,825 ms | 17,911 |
| `/v1/facilities/{slug}` | 99 ms | 106 ms | 2,527 |
| `/v1/facilities/within` (500) | 496 ms | 646 ms | 382,910 |
| `/v1/sources` | 28 ms | 30 ms | 58,690 |

The statistics endpoint originally took about 13.7 s p50 because it repeated the rights-gated
source-evidence `EXISTS` across several aggregates and counted duplicate current-location rows. It
now reads the public facility set once and aggregates in Python, and migration
`0005_unique_current_location` enforces one current location per facility. Search no longer uses a
correlated per-facility `EXISTS`: it unions indexed ID branches for name, official name, source key,
address, and locality, with trigram indexes added by migration `0006_search_trigram_indexes`.
Measured search medians after warm-up are 252 ms for `Mulanay` (40 results), 638 ms for `Manila`
(832), 1,869 ms for `Bacolod` (140), and 88 ms for a no-match term. The unfiltered facility list
remains about 2.6 s p50, which is still too high for a production launch; query-plan optimization and caching
remain pre-launch work. Bulk exports took roughly 100 seconds locally at the earlier 83,769-row
benchmark, so production
exports should be pre-generated or cached rather than rebuilt per request. Evidence:
[`docs/operations/evidence/2026-11-15-real-api/api-benchmark-optimized.txt`](operations/evidence/2026-11-15-real-api/api-benchmark-optimized.txt),
the pre-fix baseline in
[`docs/operations/evidence/2026-11-15-real-api/api-benchmark.txt`](operations/evidence/2026-11-15-real-api/api-benchmark.txt),
the location-invariant repair in
[`docs/operations/evidence/2026-11-15-real-data-cleanup/location-invariant.txt`](operations/evidence/2026-11-15-real-data-cleanup/location-invariant.txt),
and [`docs/operations/evidence/2026-11-15-real-exports/exports.txt`](operations/evidence/2026-11-15-real-exports/exports.txt).

Set production targets after representative-scale measurements, but test:

- facility search query plans;
- index usage for PSGC and PostGIS queries;
- bounding box limits;
- pagination at large offsets/cursors;
- map marker response sizes;
- API p50/p95 latency on representative data;
- memory usage during XLSX/PDF processing;
- bulk export duration and memory safety.

## 8. Release gates

### Data release gate

- source release acquired and hashed;
- parser tests pass;
- validation thresholds pass;
- source publication decision recorded under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`;
- entity matching reviewed;
- release notes and known limitations published.

### API release gate

- migrations tested;
- contract tests pass;
- no restricted fields exposed;
- OpenAPI generated and versioned;
- source and data quality info included.

### Web release gate

- responsive and accessibility tests pass;
- data freshness labels truthful;
- empty/loading/error states work;
- reference design implementation audited;
- map attribution and precision warnings visible.
