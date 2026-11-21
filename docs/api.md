# Public API

> **Audience** — Developers building against the API, and agents answering questions with it.
> **Purpose** — Explain how to consume the public `/v1` API: where it lives, what it returns, and how to read it correctly.
> **Machine contract** — [`packages/api-client/openapi.json`](../packages/api-client/openapi.json) (generated from the FastAPI app); generated TypeScript client in `packages/api-client/src/schema.ts`. Interactive Scalar reference at `/docs`, rendered from that same contract; raw contract at `/openapi.json`.
> **See also** — [Data dictionary](data-dictionary.md) for every field · [Data policy](data-policy.md) for why records may be absent · [MCP](mcp.md) for the AI-client adapter

The API is a standalone product. The web app, bulk exports, MCP server, and third-party clients consume the same `/v1` contract. It is **read-only**, versioned under `/v1`, and requires **no key** for public read endpoints.

## 1. Quickstart

No installation needed to call a running instance:

```bash
# Point this at your deployment, or http://127.0.0.1:8010 for a local instance
export API=http://127.0.0.1:8010

curl -s "$API/v1" | jq                                  # API index
curl -s "$API/v1/statistics" | jq                       # published-record counts
curl -s "$API/v1/taxonomy" | jq                         # controlled codes and labels
curl -s "$API/v1/facilities?q=library&limit=5" | jq     # first search results
```

A facility detail response is the entry point to provenance:

```bash
ID=$(curl -s "$API/v1/facilities?q=manila&limit=1" | jq -r '.items[0].id')
curl -s "$API/v1/facilities/$ID" | jq
curl -s "$API/v1/facilities/$ID/sources" | jq
curl -s "$API/v1/facilities/$ID/assertions" | jq
```

`{facility_id}` accepts a UUID or a public slug. A merged facility's slug is an alias that resolves to the surviving facility, so old links keep working. Unknown or non-public facilities return `404 facility_not_found`.

To run the API yourself, follow [Getting started](getting-started.md).

## 2. Running your own instance

Start it with:

```bash
PHILFACILITIES_DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
  uv run uvicorn philfacilities_api.main:app --host 127.0.0.1 --port 8010 --reload
```

Settings use the `PHILFACILITIES_` prefix. Defaults are safe for local development.

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
| `COVERAGE_STALE_AFTER_DAYS` | `365` | Coverage staleness threshold |

See [Operations](operations.md) for the full configuration surface.

## 3. Publication boundary — what you will not see

Every public response applies the same gate:

1. the canonical facility has `publication_status = 'public'`;
2. it links to a source release whose dataset `redistribution_status` is in `PUBLIC_RIGHTS` (`approved_public_redistribution`, `approved_with_attribution`, or `publicly_available_verified`);
3. the dataset and release `publication_status` are `approved` or `published`;
4. the link belongs to the dataset's **latest published release** (newest `retrieved_at`). A facility dropped by a newer successful release stops being current; a failed or quarantined newer attempt does not displace the last good release.

Restricted, internal-only, quarantined, blocked, and review-pending source records are excluded from detail pages, source evidence, assertions, school/health observations, statistics, search, map results, and bulk exports. This is a read-side gate in addition to the write-side guard: an internal release may store evidence against a public facility, but it cannot rewrite public canonical fields or surface its child rows.

**Practical consequence:** an absent record is an access-control or rights outcome, not a bug. Diagnose it with `/v1/sources`, `/v1/source-releases`, and `/v1/monitoring` rather than assuming missing data. Synthetic records carry `is_synthetic: true` and are absent from the working database. See [Data policy](data-policy.md).

## 4. Endpoint reference

All paths are relative to the server root. Query parameters are documented in the [OpenAPI contract](../packages/api-client/openapi.json).

### System

```http
GET /healthz
GET /v1
GET /v1/taxonomy
GET /v1/fields?by_category=true
```

`/healthz` checks a database connection and returns `ok` or `degraded`. `/v1/taxonomy` returns controlled codes and display labels for facility categories and subtypes, ownership and operator types, access classes, record statuses, facility kinds, inclusion classes, and contact types. It is static for an API release and cached for 24 hours — use it instead of hardcoding a vocabulary.

`/v1/fields` answers "is this field actually populated?" from the API instead of trial and error. Each entry has a canonical `field` path, a `scope`, a `populated` count, an eligible `total`, a server-computed `fill_ratio`, and `semantics`. Scope denominators are explicit: `school.sector` counts only public schools, `health.licensing_status` only public health facilities, `location.postal_code` only facilities with a current location. Counts use the same publication gate as the directory and are ETag-cached for one hour. `by_category=true` adds per-category denominators. Counts are served from the `stats.api_field_coverage` materialized view created by migration `0026_api_field_coverage_mv` and refreshed after each successful publication; databases without that migration fall back to the set-based on-demand computation. The view is read-only and independent of canonical tables: downgrading 0026 drops its unique index and the view, and the endpoint keeps working via the fallback. Denominators and field paths still come from the single declarative mapping in `services/field_coverage.py`. The `/v1` index links to both `/v1/fields` and `/v1/statistics#by_category`, which reports published counts for all 16 taxonomy categories.

### Facilities

```http
GET /v1/facilities
GET /v1/facilities/within?bbox=min_lon,min_lat,max_lon,max_lat
GET /v1/facilities/map?bbox=min_lon,min_lat,max_lon,max_lat&zoom=...
GET /v1/facilities/nearby?lat=...&lon=...&radius_m=...
GET /v1/facilities/{facility_id}?view=full|compact
GET /v1/facilities/{facility_id}/sources
GET /v1/facilities/{facility_id}/assertions?attribute=...
GET /v1/facilities/{facility_id}/accreditations
GET /v1/facilities/{facility_id}/history
GET /v1/facilities/{facility_id}/export.csv
```

`view=full` is the default and is unchanged: 34 keys including profiles, collections, sources, and quality. `view=compact` returns a 12-key identity and location card (`id`, `name`, `slug`, `display_name`, `facility_type`, `facility_subtype`, `inclusion_class`, `ownership`, `location`, `geography`, `source_refs`, `updated_at`) built only from the summary projection. `name` is an alias of `display_name`, matching the map point field. Constant fields (`publication_status`, `is_synthetic`), typed profiles, detail-only collections, and quality are omitted from the compact view; 404 behaviour and the publication gate are identical for both views. Web and MCP clients keep using the full view.

`/sources` returns the publication-cleared source records behind the facility. `/assertions` returns the exact source claims behind canonical fields; use `attribute=` (for example `location.precision`) to narrow. A field may have multiple claims; the endpoint does not pick a winner or erase a disagreement. `/history` returns canonical change events.

`/v1/facilities?view=compact` returns the same page, gate, and cursors with twelve-key cards instead of full summaries — useful when a list is only rendered as cards. The list card replaces `source_refs[]` with a `source_count` integer so a 100-item page fits the 75 KiB DX target; compact *detail* keeps full `source_refs[]`. `view=full` (the default) is unchanged, and `total=false` can be combined with either view.

`/v1/facilities/map` is the browser map's viewport endpoint. It returns only marker fields (`id`, `slug`, `name`, `facility_type`, `inclusion_class`, `precision`, `latitude`, `longitude`). While the viewport has at most 500 published facilities it returns `mode=points`; above that it returns `mode=clusters` with grid-cell count circles and labels. Wide and national views return bounded count circles rather than failing. Use `/within` only when full `FacilitySummary` rows are needed; it keeps the 25°² viewport limit.

Every `FacilitySummary` carries `source_refs[]` — agency code, dataset slug, and source record key — so you can tell apart same-named facilities from different registries without fetching `/sources` for every card. Full provenance stays on `/sources`.

Detail responses add typed profiles: `school` for schools, `health` for health facilities, `utility` (DOE resource, grid, capacity, unit and commissioning fields) for power plants; each is null when no public source supplies it. They also include `postal_code` and source-linked institutional `contacts[]`. Accreditation contact and address fields stay inside `accreditations[]` because they describe a time-bounded accreditation row, not necessarily the facility's current general contact.

`/export.csv` returns a small flat row and is hidden from OpenAPI so it does not appear in generated clients. For analysis, use bulk downloads instead.

### Schools

```http
GET /v1/schools
GET /v1/schools/{facility_id}?shape=wrapper|detail&view=full|compact&include=sources,assertions,domain
GET /v1/schools/{facility_id}/resources?school_year=...
```

Always filtered to `facility_type=school`. The detail endpoint keeps its historical `{facility, resources}` wrapper by default. `shape=detail` opts in to the unified `FacilityDetail` shape used by `/v1/facilities/{id}`; `view=compact` returns the twelve-key card, and `include=` attaches only the requested `sources`, `assertions`, or `domain` sections to a compact card (unrequested sections are absent, not null); `assertions` is capped at 200 rows — use `/v1/facilities/{facility_id}/assertions` for the complete claim set. `/resources` is currently empty in the working database until a rights-cleared resource-observation source is ingested; the endpoint stays in `/v1` for compatibility. Accepts `q`, `ownership`, `psgc`, `region_code`, `province_code`, `municipality_code`, `source`, `has_coordinates`, `location_precision`, `reference_period_start`, `reference_period_end`, `limit`, and `cursor`. For the full filter set use `/v1/facilities?type=school`.

### Health

```http
GET /v1/health-facilities
GET /v1/health-facilities/{facility_id}?shape=wrapper|detail&view=full|compact&include=sources,assertions,domain
GET /v1/health-facilities/{facility_id}/licenses
GET /v1/health-facilities/{facility_id}/accreditations
GET /v1/accreditations
```

The health detail endpoint keeps its historical `{facility, licenses, accreditations}` wrapper by default and supports the same `shape`, `view`, and `include` opt-ins as schools. `shape=detail` returns the unified `FacilityDetail` (which already includes gated accreditations); licences remain on this endpoint and `/licenses`. No restricted licence or accreditation row is returned by any shape.

The health list is filtered to `facility_type=health_facility` and accepts the same subset as schools. `/v1/accreditations` supports `facility_id`, `q`, `provider_category`, `authority`, `sector_code`, `source_status`, `psgc`, `region_code`, `municipality_code`, `valid_on`, `limit`, and `offset`. Accreditation is time-bounded and category-specific; it is not a claim of current operation or government ownership, and every row is gated by the same public-source predicate.

### Geography and population

```http
GET /v1/geographies?release=...&level=...&parent=...&q=...
GET /v1/geographies/{psgc_code}
GET /v1/geographies/{psgc_code}/facilities
GET /v1/geography-releases
GET /v1/geography-crosswalk?from_release=...&to_release=...
GET /v1/population?psgc=...&level=...&indicator=...&release_id=...&limit=...&offset=...
```

PSGC codes are strings with leading zeros. The current geography release is the BetterGov Q2 2024 mirror (`PSGC-Q2-2024-BETTERGOV`), explicitly labelled supplementary and not the latest official PSA release. Population rows are saved PSA 2024 Census observations with indicator, unit, value, reference period, dimensions, source URL, and attribution; a population count is never facility capacity.

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

`/source-checks` is the append-only check ledger; `/monitoring` is the latest check per dataset plus the latest run's status, duration, acceptance/rejection rates, and release label. A quarantined release shows its failed run rather than disappearing. `/coverage` reports category, inclusion, ownership, and region counts plus per-dataset rights, reference period, retrieval date, parsed rows, and a freshness flag — "stale" means "recheck the source", not "the facility closed". Match-candidate endpoints are read-only and omit reviewer names and notes.

### Bulk downloads

```http
GET /v1/downloads/facilities.csv
GET /v1/downloads/facilities.parquet
GET /v1/downloads/schools.csv
GET /v1/downloads/health-facilities.csv
```

The generic `facilities.csv` and `facilities.parquet` accept the same filters as `/v1/facilities` (including the `facility_type` alias for `type`), so all 16 categories have a path to a filtered bulk export without a new fixed file. The dedicated `schools.csv` and `health-facilities.csv` remain unchanged. Downloads apply the same publication gate as JSON endpoints. CSV cells are neutralized against spreadsheet-formula injection. Facility downloads include summary classification fields (`official_name`, `facility_kind`, `inclusion_class`, `ownership_type`, `operator_type`, `public_access_class`) and `postal_code`, so you do not have to reconstruct them from nested JSON. Use downloads for full-dataset work; do not page through the list API to recreate them. Exports are keyset-paginated and streamed so a national dataset does not have to be materialised in memory.

## 5. Facility filters

`/v1/facilities` accepts the full set below. `/within` and `/nearby` accept the same filters except `has_coordinates`, plus their required spatial parameters. `/schools` and `/health-facilities` accept only the subset named in their sections.

| Parameter | Values / meaning |
|---|---|
| `type` (alias `facility_type`) | Any code from `/v1/taxonomy`: `school`, `health_facility`, `government_office`, `community_facility`, `emergency_facility`, `library`, `museum`, `social_welfare_facility`, `public_market`, `transport_facility`, `utility_facility`, `environmental_monitoring`, `public_space`, `cultural_facility`, `agricultural_facility`, `justice_facility`, `housing_service`, `other_qualifying_facility`. Both names are accepted and equivalent; neither is removed. |
| `subtype` | Normalized subtype code |
| `inclusion_class` | `GOVERNMENT_FACILITY`, `PRIVATE_PUBLIC_SERVICE_PROVIDER`, `PUBLIC_ACCESS_VENUE`, `DISCOVERY_CANDIDATE` |
| `ownership` | Broad legacy flag: `government`, `private`, `unknown` |
| `ownership_type`, `operator_type` | Detailed vocabularies; see [Data dictionary](data-dictionary.md) |
| `public_access_class` | `PUBLIC_FREE`, `PUBLIC_PAID_OR_CONDITIONAL`, `SERVICE_USERS_ONLY`, `APPOINTMENT_ONLY`, `MEMBERS_STUDENTS_ONLY`, `STAFF_ONLY`, `RESTRICTED`, `UNKNOWN` |
| `facility_kind` | `facility`, `site`, `building`, `facility_unit`, `infrastructure_asset`, `project` |
| `function` | Function code, e.g. `EVACUATION_SITE` |
| `q` | Name, official name, source key, address, or locality text |
| `psgc`, `region_code`, `province_code`, `municipality_code`, `barangay_code` | Hierarchical PSGC filters |
| `source` | Agency short code |
| `has_coordinates` | `true` / `false` |
| `location_precision` | `gps_verified`, `field_verified`, `source_gps`, `map_geocoded`, `barangay_centroid`, `unknown` |
| `reference_period_start`, `reference_period_end` | `YYYY-MM-DD`; matches a facility with a rights-cleared release whose reference period overlaps the interval |
| `updated_since` | ISO-8601 timestamp; PhilFacilities change time, not source publication time |
| `limit`, `cursor` | Page size and opaque cursor |

`/within` requires `bbox` (max 25 deg²) and accepts `limit` only; `/nearby` requires `lat`, `lon`, `radius_m` (max 50 km) and accepts `limit`.

## 6. Pagination and search

- **Cursor pagination** for facility, school, health-facility, and change lists: stable ordering by `updated_at DESC, id DESC`; opaque cursor; `next_cursor` and `has_more`; `total` included. Add `total=false` to skip the count query when only pages are needed; `total` then comes back as `null` while page sizes, cursors, and ordering stay identical.
- **Offset pagination** for bounded reference tables: geographies, accreditations, population, source checks, source releases, quality issues, match candidates.
- `limit` defaults to 20 and is capped at `MAX_PAGE_SIZE` (100).

Search is an uncorrelated `UNION` of indexed branches for name, official name, source key, address, and locality. Locality matching uses PSGC level prefixes (region 2, province 5, municipality 7, barangay 10) so a code at one level matches descendants. Trigram indexes support text branches. Normalization tolerates punctuation and spacing while preserving official spelling in the response; it does not alter identity matching.

## 7. Reading results responsibly

- `null` means unknown or not supplied — never zero, `false`, inactive, or closed. An absent bed count is not `0`. An empty collection `[]` means no publication-cleared rows exist for that collection; it does **not** assert that the facility has none. `null` and `[]` are not interchangeable, and neither is converted in `/v1`. `GET /v1/fields` states the rule per field.
- Source publication date, reference period, `retrieved_at`, and `processed_at` are separate facts; `updated_at` is a PhilFacilities edit time, not an agency update time.
- PSGC codes are strings; do not parse them as integers.
- Coordinates are WGS 84 (EPSG:4326) and often approximate. Read `location.precision` before presenting a point as a building location; do not render a `barangay_centroid` or `map_geocoded` point as an exact pin.
- Registry presence, licensure, or accreditation does not establish current operation. Ownership and operation are separate fields; a regulator listing a private provider does not make it government-owned.
- `source_refs[]` identifies registries; full provenance is on `/sources`. An `agreed` fusion value requires two distinct agencies; a single-source value stays `single_source`.
- Coverage is partial and must not be presented as national completeness. Keep attribution and caveats with any figure you report.

The full field-level rules are in the [Data dictionary](data-dictionary.md).

## 8. Errors

Errors use a **flat** JSON envelope — there is no outer `error` key. The same four keys appear on every error status, and the flat `ErrorBody` schema in the OpenAPI contract describes them:

```json
{
  "code": "validation_error",
  "message": "One or more query parameters are invalid.",
  "details": [],
  "request_id": "..."
}
```

`details` is `null` when there is no structured context, a list of field issues for `validation_error`, and an object with limits for rate/bounds errors. Codes you will see include `validation_error`, `invalid_bbox`, `bbox_too_large`, `radius_too_large`, `invalid_reference_period`, `facility_not_found`, `school_not_found`, `health_facility_not_found`, `not_found`, `method_not_allowed`, `no_downloadable_data`, `rate_limit_exceeded`, `http_error`, and `internal_error`.

Status codes: `400` invalid filters, `404` unknown/non-public facility, `422` validation error, `429` rate limit, `500` unexpected error, `503` temporary unavailability. SQL, file paths, credentials, private source content, and stack traces are never exposed. Every response carries `X-Request-ID` and `X-Response-Time-Ms`; untrusted inbound request IDs are replaced. Rate-limited responses also carry `Retry-After` and `X-RateLimit-*` headers.

## 9. Caching, CORS, and rate limits

- JSON responses support ETag/Last-Modified conditional requests where implemented.
- CORS allows configured web origins, `GET`/`HEAD`/`OPTIONS`, and exposes `ETag`, `X-Request-ID`, `X-Response-Time-Ms`. Credentials are never combined with a wildcard.
- Anonymous per-client rate limiting is applied; no public CDN or external cache is configured in this checkout. Rate-limited responses carry `Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining` so clients can back off intelligently; the two `X-RateLimit-*` headers are exposed to browser clients through CORS.
- Stable geography, source catalogue, and facility detail responses are cache-friendly. Bulk downloads should be pre-generated or cached upstream rather than rebuilt per request.

## 10. Generated client and contract workflow

For TypeScript consumers, use `@philfacilities/api-client/schema` instead of redeclaring response shapes. Regenerate after an API change:

```bash
just openapi-export                 # regenerate packages/api-client/openapi.json
just typegen                        # regenerate the TypeScript client
uv run pytest tests/test_api_contract.py -q
```

CI fails when the committed `openapi.json` differs from `app.openapi()`. Contract tests also assert the API is read-only, the error envelope is consistent, spatial bounds are enforced, and `/healthz` and `/v1` are public.

When changing a public field or endpoint:

1. update the Pydantic schema and route;
2. add or update an API test;
3. regenerate the OpenAPI document and TypeScript client;
4. update [Data dictionary](data-dictionary.md) and this page;
5. confirm the publication gate still excludes restricted evidence.

See [Contributing](contributing.md) for the full workflow and [ADR 0007](decisions/0007-api-versioning-and-bulk-exports.md) for versioning decisions.

## 11. Known gaps

Hosted deployment URL, production rate-limit policy, external monitoring/paging, and formal legal review are not configured in this checkout. Unfiltered facility-list latency is still too high for a production launch; query-plan optimization and caching remain pre-launch work. See [Operations](operations.md).

The API covers 16 categories, but the data and typed profiles are asymmetric. Authoritative profiles exist mainly for schools and health facilities because the strongest rights-cleared datasets are DepEd masterlists/EBEIS and DOH NHFR. Government offices, libraries, and public spaces arrive largely through OSM/HOT discovery layers, which cannot support authoritative domain profiles. Other categories are represented by the generic facility endpoints, `facility_type`, `function_details`, and `roles`; the API does not fabricate typed profiles to look symmetric. Use `/v1/statistics#by_category` and `/v1/fields` for the current distribution and coverage rather than inferring completeness from the dedicated endpoints. Dated before/after measurements are in [`2026-11-21-api-dx-baseline.json`](operations/evidence/2026-11-21-api-dx-baseline.json), [`2026-11-21-api-dx-after.json`](operations/evidence/2026-11-21-api-dx-after.json), and the per-phase gates in [`2026-11-21-api-dx-phase-gates.json`](operations/evidence/2026-11-21-api-dx-phase-gates.json).
