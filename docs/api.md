# Public API

**Implementation:** `apps/api/philfacilities_api/`
**Contract:** `packages/api-client/openapi.json` (committed, 42 documented paths); generated client in `packages/api-client/src/schema.ts`.
**Interactive docs:** `/docs` and `/openapi.json` when the API is running.

The API is a standalone product. The web app, bulk exports, and third-party clients consume the same `/v1` contract. It is read-only and requires no key for public read endpoints.

## 1. Run it

```bash
PHILFACILITIES_DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
  uv run uvicorn philfacilities_api.main:app --host 127.0.0.1 --port 8010 --reload
```

Environment variables (prefix `PHILFACILITIES_`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local Compose URL | SQLAlchemy/psycopg URL |
| `ENV` | `local` | Environment label returned by `/healthz` |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed origins |
| `RATE_LIMIT_PER_MINUTE` | `120` | Anonymous per-client limit |
| `MAX_PAGE_SIZE` | `100` | Facility list page cap |
| `DEFAULT_PAGE_SIZE` | `20` | Default list page size |
| `MAX_BBOX_AREA_DEG2` | `25.0` | Bounding-box area cap |
| `MAX_NEARBY_RADIUS_M` | `50000` | Nearby radius cap |
| `MAX_MAP_FEATURES` | `500` | Map result cap |
| `COVERAGE_STALE_AFTER_DAYS` | `365` | Staleness threshold for coverage |

## 2. Publication boundary

Every public response applies the same gate:

1. the canonical facility has `publication_status = 'public'`;
2. it links to a source release whose dataset `redistribution_status` is in `PUBLIC_RIGHTS` (`approved_public_redistribution`, `approved_with_attribution`, or `publicly_available_verified`);
3. the dataset and release `publication_status` are `approved` or `published`;
4. the link belongs to the dataset's **latest published release** (newest `retrieved_at`). A facility dropped by a newer successful release stops being current; a failed or quarantined newer attempt does not displace the last good release.

Restricted, internal-only, quarantined, blocked, and review-pending source records are excluded from detail pages, source evidence, assertions, school/health observations, statistics, search, map results, and bulk exports. This is a read-side gate in addition to the write-side guard: an internal release may store evidence against a public facility, but it cannot rewrite the public canonical fields or surface its child rows. Synthetic records are labelled `is_synthetic: true` and are not present in the working database. See [data policy](data-policy.md).

## 3. Endpoint families

All paths below are relative to the server root.

### System

```http
GET /healthz
GET /v1
GET /v1/taxonomy
```

`/healthz` checks a database connection and returns `ok` or `degraded`. `/v1` returns the API index.

`/v1/taxonomy` returns the controlled codes and display labels for facility categories and subtypes, ownership and operator types, access classes, record statuses, facility kinds, inclusion classes, and contact types. It is static for an API release and cached for 24 hours, so clients do not need to reproduce the vocabulary or guess labels.

### Facilities

```http
GET /v1/facilities
GET /v1/facilities/within?bbox=min_lon,min_lat,max_lon,max_lat
GET /v1/facilities/map?bbox=min_lon,min_lat,max_lon,max_lat&zoom=...
GET /v1/facilities/nearby?lat=...&lon=...&radius_m=...
GET /v1/facilities/{facility_id}
GET /v1/facilities/{facility_id}/sources
GET /v1/facilities/{facility_id}/assertions?attribute=...
GET /v1/facilities/{facility_id}/accreditations
GET /v1/facilities/{facility_id}/history
GET /v1/facilities/{facility_id}/export.csv   (not in OpenAPI)
```

`{facility_id}` accepts a UUID or a public slug. A merged facility's slug is an alias: it resolves to the surviving facility so old links keep working. Detail endpoints return `404 facility_not_found` for a non-public or unknown facility.

`/v1/facilities/map` is the browser map's viewport endpoint. It returns only the fields needed to draw and label a marker: `id`, `slug`, `name`, `facility_type`, `inclusion_class`, `precision`, `latitude`, and `longitude`. While the viewport contains at most 500 published facilities it returns `mode=points`; above that threshold it returns `mode=clusters` with grid-cell count circles, average coordinates, and a human-readable label. The viewport is never rejected for being wide: a national or multi-region view returns a bounded set of large count circles rather than failing. `total` is the number of mapped records represented by the response. Use `/v1/facilities/within` only when full `FacilitySummary` rows are required; it keeps the older 25°² viewport limit.

`/sources` returns the publication-cleared source records behind the facility. `/assertions` returns the exact source claims behind canonical fields; use `attribute=` to narrow to one field (for example `location.precision`). A field may have multiple claims; the endpoint does not pick a winner or erase a disagreement. `/history` returns canonical change events.

Detail responses include `location.postal_code` when the source supplied one, and `contacts[]` for source-linked institutional phone, email, website, and opening-hours channels. Contacts keep their `source_record_id` and `source_field`; the API does not select one source's phone number as the national truth. Accreditation phone, email, street address, and municipality stay inside `accreditations[]` because they describe a time-bounded accreditation row, not necessarily the facility's current general contact details. A school detail carries `school`; a health facility carries `health`; a power plant carries `utility` with DOE resource, grid, capacity, unit and commissioning fields. Each profile is null when no public source record supplies it.

The per-facility CSV export returns a small flat row and is hidden from the OpenAPI schema, so it does not appear in generated clients. It applies the same publication gate as the JSON detail. Use `/v1/downloads/facilities.csv` for bulk analysis.

### Schools

```http
GET /v1/schools
GET /v1/schools/{facility_id}
GET /v1/schools/{facility_id}/enrollment?school_year=...
GET /v1/schools/{facility_id}/resources?school_year=...
```

The school list is always filtered to `facility_type=school`. It accepts `q`, `ownership`, `psgc`, `region_code`, `province_code`, `municipality_code`, `source`, `has_coordinates`, `location_precision`, `reference_period_start`, `reference_period_end`, `limit`, and `cursor`. It does not accept `type`, `subtype`, `inclusion_class`, `ownership_type`, `operator_type`, `public_access_class`, `facility_kind`, `function`, `barangay_code`, or `updated_since`; use `/v1/facilities?type=school` for the full filter set.

### Health

```http
GET /v1/health-facilities
GET /v1/health-facilities/{facility_id}
GET /v1/health-facilities/{facility_id}/licenses
GET /v1/health-facilities/{facility_id}/accreditations
GET /v1/accreditations
```

The health-facility list is always filtered to `facility_type=health_facility` and accepts the same subset as the school list. Use `/v1/facilities?type=health_facility` for the full filter set.

`/v1/accreditations` supports `facility_id`, `q`, `provider_category`, `authority`, `sector_code`, `source_status`, `psgc`, `region_code`, `municipality_code`, `valid_on`, `limit`, and `offset`. Accreditation is time-bounded and category-specific; it is not a claim of current operation or government ownership. Every accreditation row, including nested rows on facility/health detail, is gated by the same public source-record predicate as other child evidence: an accreditation from a restricted dataset or a blocked/unpublished release is omitted even when the parent facility is public through another source.

### Geography

```http
GET /v1/geographies?release=...&level=...&parent=...&q=...
GET /v1/geographies/{psgc_code}
GET /v1/geographies/{psgc_code}/facilities
GET /v1/geography-releases
GET /v1/geography-crosswalk?from_release=...&to_release=...
```

PSGC codes are strings. The current release is the BetterGov Q2 2024 mirror (`PSGC-Q2-2024-BETTERGOV`), explicitly labelled as supplementary and not the latest official PSA release.

### Population

```http
GET /v1/population?psgc=...&level=...&indicator=...&q=...&release_id=...&limit=...&offset=...
```

One row per published PSA 2024 Census observation, with indicator label, unit, value, reference date/period, dimensions, PSA source URL, BetterGov release, dataset slug, and attribution. Missing source values remain `null`. A population count is never facility capacity or service coverage.

### Sources, monitoring, quality, statistics

```http
GET /v1/sources
GET /v1/sources/{source_id}
GET /v1/source-releases?dataset=...
GET /v1/source-checks?dataset=...&limit=...
GET /v1/monitoring
GET /v1/quality/summary
GET /v1/quality/issues?status=open&severity=...
GET /v1/quality/match-candidates?status=pending
GET /v1/quality/match-candidates/{candidate_id}
GET /v1/coverage
GET /v1/statistics
GET /v1/changes?since=...&limit=...&cursor=...
```

`/v1/source-checks` is the append-only check ledger; `/v1/monitoring` is the latest check per dataset, plus the latest ingestion run's status, duration, acceptance/rejection rates, and the latest release label. A quarantined release shows its failed run rather than disappearing from the dashboard. The dashboard reads one latest row per dataset (a `DISTINCT ON (dataset_id)` query) instead of loading complete check, release, and run history. Match-candidate endpoints are read-only and expose the deterministic method, algorithm version, confidence, evidence, facility names/slugs, review time, and merge resolution. Reviewer names and review notes remain internal.

`/v1/coverage` reports category/subtype counts, inclusion-class and ownership distributions, region counts, and per-dataset rights, reference period, retrieval date, parsed row count, freshness in days, and a stale flag. Staleness is derived from the source reference/publication date, not the download time; “stale” means “recheck the source”, not “the facility closed”.

### Downloads

```http
GET /v1/downloads/facilities.csv
GET /v1/downloads/facilities.parquet
GET /v1/downloads/schools.csv
GET /v1/downloads/health-facilities.csv
```

Downloads use the same publication gate as JSON endpoints. CSV cells are neutralized against spreadsheet-formula injection. Facility downloads include the summary classification fields (`official_name`, `facility_kind`, `inclusion_class`, `ownership_type`, `operator_type`, `public_access_class`) and `postal_code`, so bulk consumers do not have to reconstruct them from nested or detail-only JSON. Use downloads for full-dataset work; do not page through the list API to recreate them.

## 4. Facility filters

`/v1/facilities` accepts the full filter set below. `/v1/facilities/within` and `/v1/facilities/nearby` accept the same filters except `has_coordinates`, plus their required spatial parameters; they return a capped map result set and do not use cursors. `/v1/schools` and `/v1/health-facilities` accept only the subset listed in their sections above.

| Parameter | Values / meaning |
|---|---|
| `type` | `school`, `health_facility`, `government_office`, `community_facility`, `emergency_facility`, `library`, `museum`, `social_welfare_facility`, `public_market`, `transport_facility`, `utility_facility`, `environmental_monitoring`, `public_space`, `cultural_facility`, `agricultural_facility`, `justice_facility`, `housing_service`, `other_qualifying_facility` |
| `subtype` | Normalized subtype code |
| `inclusion_class` | `GOVERNMENT_FACILITY`, `PRIVATE_PUBLIC_SERVICE_PROVIDER`, `PUBLIC_ACCESS_VENUE`, `DISCOVERY_CANDIDATE` |
| `ownership` | Broad legacy flag: `government`, `private`, `unknown` |
| `ownership_type`, `operator_type` | Detailed vocabularies (national government, local government, GOCC, public educational institution, other public body, government unspecified, private corporate, private individual/partnership, NGO/non-profit, cooperative, religious/faith-based, public-private joint, private unspecified, unknown) |
| `public_access_class` | `PUBLIC_FREE`, `PUBLIC_PAID_OR_CONDITIONAL`, `SERVICE_USERS_ONLY`, `APPOINTMENT_ONLY`, `MEMBERS_STUDENTS_ONLY`, `STAFF_ONLY`, `RESTRICTED`, `UNKNOWN` |
| `facility_kind` | `facility`, `site`, `building`, `facility_unit`, `infrastructure_asset`, `project` |
| `function` | Function code, e.g. `EVACUATION_SITE` |
| `q` | Name, official name, source key, address, or locality text |
| `psgc`, `region_code`, `province_code`, `municipality_code`, `barangay_code` | Hierarchical PSGC filters |
| `source` | Agency short code |
| `has_coordinates` | `true` / `false` |
| `location_precision` | `gps_verified`, `field_verified`, `source_gps`, `map_geocoded`, `barangay_centroid`, `unknown` |
| `reference_period_start`, `reference_period_end` | `YYYY-MM-DD`; matches a facility with a rights-cleared release whose reference period overlaps the interval. Either boundary may be supplied alone; a release with no recorded boundary does not match. |
| `updated_since` | ISO-8601 timestamp; canonical update time, not source publication time |
| `limit`, `cursor` | Page size and opaque cursor |

`/within` additionally requires `bbox` (max area 25 deg²) and accepts `limit` only; `/nearby` requires `lat`, `lon`, `radius_m` (max 50 km), and accepts `limit`.

## 5. Pagination

- **Cursor pagination** for facility, school, health-facility, and change lists: stable ordering by `updated_at DESC, id DESC`; opaque cursor; `next_cursor` and `has_more`; `total` is included.
- **Offset pagination** for bounded reference tables: geographies, accreditations, population, source checks, source releases, quality issues, and match candidates.
- `limit` defaults to 20 and is capped at `MAX_PAGE_SIZE` (100).

## 6. Search

Search is an uncorrelated `UNION` of indexed branches for name, official name, source key, address, and locality. Locality matching uses PSGC level prefixes (region 2, province 5, municipality 7, barangay 10) so a code at one level matches its descendants. Trigram indexes support the text branches (migration `0006_search_trigram_indexes`). Search normalization tolerates common punctuation and spacing while preserving official spelling in the response; it does not alter identity matching.

## 7. Errors

Errors use a JSON envelope:

```json
{
  "error": {
    "code": "invalid_bbox",
    "message": "bbox must be min_lon,min_lat,max_lon,max_lat",
    "details": null,
    "request_id": "..."
  }
}
```

Status codes: `400` invalid filters, `404` unknown/non-public facility, `422` validation error, `429` rate limit, `500` unexpected error, `503` temporary unavailability. SQL, file paths, credentials, private source content, and stack traces are never exposed.

Every response carries `X-Request-ID` and `X-Response-Time-Ms`; untrusted inbound request IDs are replaced.

## 8. Caching, CORS, and rate limits

- JSON responses support ETag/Last-Modified conditional requests where implemented.
- CORS allows the configured web origins, `GET`/`HEAD`/`OPTIONS`, and exposes `ETag`, `X-Request-ID`, `X-Response-Time-Ms`. Credentials are not combined with a wildcard.
- Anonymous per-client rate limiting is applied. No public CDN or external cache is configured in this checkout.
- Stable geography, source catalogue, and facility detail responses are cache-friendly; bulk downloads should be pre-generated or cached rather than rebuilt per request.

## 9. Contract workflow

The OpenAPI document is the contract:

```bash
just openapi-export                 # regenerate packages/api-client/openapi.json
just typegen                        # regenerate the TypeScript client
uv run pytest tests/test_api_contract.py -q
```

CI fails when the committed `openapi.json` differs from `app.openapi()`. Contract tests also assert that the API is read-only, that the error envelope is consistent, that spatial bounds are enforced, and that `/healthz` and `/v1` are public.

When changing a public field or endpoint:

1. update the Pydantic schema and route;
2. add or update an API test;
3. regenerate the OpenAPI document and TypeScript client;
4. update [data dictionary](data-dictionary.md) and this page;
5. confirm the publication gate still excludes restricted evidence.

## 10. Known launch gaps

Hosted deployment URL, production rate-limit policy, external monitoring/paging, and formal legal review are not configured in this checkout. Unfiltered facility-list latency is still too high for a production launch; query-plan optimization and caching remain pre-launch work. See [operations](operations.md).
