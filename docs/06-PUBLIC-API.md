# 06 — Public API

**Status:** versioned read API implemented and serving publication-approved real data.  
**Contract:** `packages/api-client/openapi.json` (39 paths), generated client in `packages/api-client/src/schema.ts`.  
**Live example snapshot:** `docs/reports/07-real-api-examples.md`.

## 1. API objectives

The API is a standalone public product. It provides stable identifiers, filters, provenance, time-aware source data, and predictable pagination. The website is only one client.

- Base path: `/v1` behind a documented domain.
- Format: JSON by default; CSV/Parquet for permitted bulk data.
- Authentication: no key for basic public read endpoints. Rate limits are applied; keys are introduced only when needed for abuse control or quotas.
- Documentation: FastAPI OpenAPI at `/openapi.json` and `/docs`, plus `docs/DATA-DICTIONARY.md`.
- CORS: configured for the public website and documented origins; credentials are not combined with an unrestricted wildcard.

## 2. Publication boundary

Every public endpoint applies the same gate:

1. the canonical facility must have `publication_status = public`;
2. it must link to a source release whose dataset rights are in the public set (`approved_public_redistribution`, `approved_with_attribution`, or `publicly_available_verified`);
3. the dataset and release publication states must be `approved` or `published`.

Synthetic records are allowed only when explicitly labelled synthetic in a non-production environment. The working database currently has **0 synthetic facilities**. DepEd EBEIS NCR has 5,055 retained records. Its current source release is `published` for institution-level fields, but canonical facility rows remain `internal`/`DISCOVERY_CANDIDATE` pending field-level mapping and privacy review; school-head names are never public. `publicly_available_verified` is a public-compatible state for verified, publicly available datasets with no explicit prohibition; it does not bypass the publication gate.

## 3. Endpoint families

### Service and index

```http
GET /healthz
GET /v1
```

### Facilities

```http
GET /v1/facilities
GET /v1/facilities/{facility_id}
GET /v1/facilities/{facility_id}/sources
GET /v1/facilities/{facility_id}/assertions
GET /v1/facilities/{facility_id}/history
GET /v1/facilities/{facility_id}/accreditations
```

Filters for `/v1/facilities`:

- `type=school|health_facility`
- `ownership=government|private|unknown`
- `psgc`, `region_code`, `province_code`, `municipality_code`, `barangay_code`
- `source=<agency short code>`
- `has_coordinates=true|false`
- `location_precision=gps_verified|field_verified|source_gps|map_geocoded|barangay_centroid|unknown`
- `reference_period_start=YYYY-MM-DD&reference_period_end=YYYY-MM-DD` — matches facilities with at least one rights-cleared source release whose reference period overlaps the interval. Either boundary may be supplied alone; a release with no recorded boundary does not match.
- `updated_since=<ISO-8601>`
- `q=<search text>`
- `limit`, `cursor`

The same geographic, source, location, and reference-period filters apply to
`/v1/facilities/within`, `/v1/facilities/nearby`, `/v1/schools`, and
`/v1/health-facilities`.

`GET /v1/facilities/{facility_id}/assertions` returns the exact source claims behind
canonical fields after the same publication gate as `/sources`: the facility must be
public and the contributing dataset/release must be rights-cleared and published. Use
`attribute=` to narrow to one field (for example `location.precision`). A field can have
multiple claims from different sources; the endpoint does not pick a winner or erase a
disagreement.

`GET /v1/coverage` reports category/subtype counts, inclusion-class and ownership
distributions, region counts, and per-dataset rights, reference period, retrieval date,
parsed row count, freshness in days, and a stale flag. The default stale threshold is
365 days and is returned in `coverage_stale_after_days`. Freshness is derived from the
source reference/publication date, not from the download time. Stale means “recheck the
source”, not “the facility closed”.

### Domain-specific

```http
GET /v1/schools
GET /v1/schools/{facility_id}
GET /v1/schools/{facility_id}/enrollment
GET /v1/schools/{facility_id}/resources
GET /v1/health-facilities
GET /v1/health-facilities/{facility_id}
GET /v1/health-facilities/{facility_id}/licenses
GET /v1/health-facilities/{facility_id}/accreditations
GET /v1/accreditations
```

`GET /v1/accreditations` is the top-level accreditation search. It supports `facility_id`, `q`, `provider_category`, `authority`, `sector_code`, `source_status`, `psgc`, `region_code`, `municipality_code`, `valid_on`, `limit`, and `offset`. Each item retains the provider category, benefit package, accreditation category, bed count when supplied, sector code, validity dates, page/row reference, source record ID, and the public facility link.

Current real coverage: **28,207 accreditations** across **26 PhilHealth provider categories**, linked to **13,546 facilities (13,545 public)**.

### Geography

```http
GET /v1/geographies
GET /v1/geographies/{psgc_code}
GET /v1/geographies/{psgc_code}/facilities
GET /v1/geography-releases
GET /v1/geography-crosswalk?from_release=...&to_release=...
```

PSGC codes are strings. The current release is the BetterGov Q2 2024 mirror (`PSGC-Q2-2024-BETTERGOV`, 43,760 units), explicitly labelled as supplementary and not the latest official PSA release.

### Map and spatial queries

```http
GET /v1/facilities/within?bbox=min_lon,min_lat,max_lon,max_lat
GET /v1/facilities/nearby?lat=...&lon=...&radius_m=...
```

Both endpoints accept the shared facility filters and enforce bounded areas, result limits, valid coordinates, and precision filters. A map viewport is not allowed to become an unbounded table scan.

### Population statistics

```http
GET /v1/population
```

Supports `psgc`, `level`, `indicator`, `q`, `release_id`, `limit`, and `offset`. Returns one row per published PSA 2024 Census observation with indicator label, unit, value, reference date/period, dimensions, PSA source URL, BetterGov release, dataset slug, and attribution. Missing source values remain `null`; a population count is never presented as facility capacity or service coverage.

Current real coverage: **134,748 observations** across **18 regional releases**.

### Sources, monitoring, and quality

```http
GET /v1/sources
GET /v1/sources/{source_id}
GET /v1/source-releases
GET /v1/source-checks
GET /v1/monitoring
GET /v1/quality/summary
GET /v1/quality/issues
GET /v1/quality/match-candidates?status=pending
GET /v1/quality/match-candidates/{candidate_id}
GET /v1/changes?since=<ISO-8601>
GET /v1/statistics
```

`/v1/source-checks` is the append-only check ledger; `/v1/monitoring` is the latest check per dataset, including access state, HTTP status, next check time, and publication/rights state. The match-candidate endpoints are read-only and expose the deterministic method, algorithm version, confidence, evidence, facility names/slugs, review time, and merge resolution. Reviewer names and review notes remain internal.

### Downloads

```http
GET /v1/downloads/facilities.csv
GET /v1/downloads/facilities.parquet
GET /v1/downloads/schools.csv
GET /v1/downloads/health-facilities.csv
```

Downloads use the same publication gate as the JSON endpoints. The working database has **61,806 public facilities**. At the earlier 83,769-row benchmark, CSV was about **31 MB** and Parquet about **6.3 MB**; re-measure after the current release. CSV cells are neutralized against spreadsheet-formula injection. Restricted, internal-only, and review-pending sources never enter an export. A dataset with `publicly_available_verified` enters an export only after its release gate is approved or published and its fields have passed the policy review.

## 4. Pagination

- Cursor pagination for facility lists: stable ordering, opaque cursor, documented maximum limit, `next_cursor`, and `has_more`.
- Offset pagination for bounded reference tables such as geographies, accreditations, population, source checks, and quality issues.
- Bulk downloads are the supported path for full-dataset use; clients must not page through 83,000 records to recreate them.

## 5. Response contract

A facility response includes:

- canonical `id` and `slug`;
- display and official name;
- type/subtype;
- ownership or `unknown`;
- administrative geography with PSGC code and release;
- location and precision/method;
- domain-specific profile data;
- source records and source release dates;
- quality warnings;
- timestamps.

`updated_at` means the canonical record changed. It is not the agency's publication date. `source_published_at`, `reference_period`, `retrieved_at`, and `processed_at` are separate fields.

A real response shape is captured in `docs/reports/07-real-api-examples.md`; it is not a synthetic fixture.

## 6. Error model

Errors use a consistent JSON envelope with:

- `code` (stable machine-readable value);
- `message` (short human-readable explanation);
- `details` (field-level validation details when safe);
- `request_id`.

Appropriate status codes: 400 invalid filters, 404 unknown canonical ID, 422 validation error, 429 rate limit, 500 unexpected error, 503 temporary service unavailability.

SQL, file paths, credentials, private source content, and stack traces are not exposed. A large export that exceeds a bind-parameter limit is a server defect; the current implementation chunks facility-ID lookups and has a multi-chunk regression test.

## 7. Search

Search is an uncorrelated `UNION` of indexed ID branches for name, official name, source key, address, and locality. Locality matching uses PSGC level prefixes (region 2, province 5, municipality 7, barangay 10) so a code at one level matches its descendants. Search normalization is tolerant of common punctuation and spacing while preserving official spelling in the response. Trigram indexes support the text branches (migration `0006_search_trigram_indexes`), and search normalization does not alter identity matching.

## 8. Caching and rate limits

- Conditional JSON responses support ETags/Last-Modified where implemented.
- Anonymous rate limits are applied per client.
- Bulk downloads are more efficient than paging the facility API.
- Stable geography, source catalogue, and facility detail responses are cache-friendly.
- No public CDN or external caching layer is configured in this checkout.

## 9. API compatibility

- `/v1` remains backward compatible.
- Optional fields may be added without breaking existing response shapes.
- Fields are deprecated with notice and migration notes.
- OpenAPI snapshots and contract tests are maintained.
- The TypeScript client is generated from the released OpenAPI document, and CI fails when the committed contract and `app.openapi()` drift.

## 10. Launch gate

- [x] OpenAPI schema generated, reviewed, and drift-tested.
- [x] Public endpoints contain no private/restricted data; internal-only evidence is excluded; public-availability publication follows `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.
- [x] Pagination, spatial limits, and large-export chunking tested.
- [x] Provenance, quality, population, and monitoring fields documented.
- [x] CORS, rate limits, error responses, and download gating tested.
- [x] Response examples use publication-approved real data.
- [x] Versioning and change policy documented.
- [ ] Hosted deployment URL, production rate-limit policy, external monitoring, and formal legal review.
