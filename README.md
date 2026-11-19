# PhilFacilities

> **An open, source-linked registry of Philippine schools, health facilities, public-service facilities and community venues, built as reusable public data infrastructure.**

**Status date:** 18 November 2026  
**Implementation state:** real-data pipeline operational; coverage is partial and not nationwide-complete. Synthetic records are absent from the working production database.

PhilFacilities acquires publicly available and permitted data, preserves every original release, normalizes records without destroying source values, enforces source-rights publication gates, and exposes the result through a versioned read API, searchable directory, map, and bulk downloads.

## Current data state

Measured from the configured PostgreSQL/PostGIS database on 18 November 2026:

| Measure | Actual state |
|---|---|
| Canonical facilities | **273,369** |
| Public facilities | **273,369** (API-gated) |
| Non-public facilities | **0** |
| Synthetic facilities in the working database | **0** |
| Registered datasets | **85** |
| Retained source releases | **103** |
| Published geographic units | **43,760** (BetterGov PSGC Q2 2024 mirror) |
| Published population observations | **134,748** across 18 PSA 2024 Census regional releases |
| Published health accreditations | **28,207** across 26 PhilHealth provider categories |
| Fused attribute claims | **417,461** (0 agreed, 97,507 conflict, 319,954 single-source) |
| Public facilities with coordinates | **155,230**, all `map_geocoded` or source-supplied |
| Public facilities without coordinates | **118,139** (kept in text search; never given invented coordinates) |

The fused-attribute table is an internal derived layer, not a public API surface. Its last completed rebuild predates the DepEd Masterlist and NHFR enrichment releases, so the fused count is lower than the assertion count those releases added. These counts describe processed source records, not the complete national facility universe. OSM/HOT records are crowd-sourced map features, not official DOH or DepEd registries. The DOH September 2026 NHFR snapshot is the official health-facility registry and supplies institutional fields for 44,799 DOH codes; OSM-only health features without a DOH code remain crowd-sourced and unclassified. The DepEd EBEIS extract contains school-head names; the current source releases are approved for institution-level publication with those names withheld. The SY 2020-2021 Masterlist now supplies sector/ownership evidence for 60,924 exact BEIS IDs; the remaining EBEIS rows stay unclassified because EBEIS has no reliable per-row sector field. See [`docs/data-policy.md`](docs/data-policy.md).

### Published sources

| Source | Data used | Rights/publication state | Caveat |
|---|---|---|---|
| PhilHealth accredited healthcare facilities | 26 provider-category PDFs, 28,207 accreditations | `approved_with_attribution` / `published` | Accreditation is benefit-package-specific and time-bound; one linked PDF (`MCP_073126.pdf`) returns HTTP 404. The previously blocked Antenatal release was re-ingested with the corrected parser (3,221 rows; no annex double-count). |
| HOT/OSM health extract | 18,545 source records; 18,426 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; coordinates are bounding-box centres (`map_geocoded`); operational status unknown. |
| HOT/OSM education extract | 57,303 source records; 56,469 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; not a DepEd masterlist; same coordinate/status caveats. |
| HOT/OSM bulk PBF extract | 51,549 source records; 51,538 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced map features across categories; ownership and operational status are not inferred. |
| DepEd EBEIS school masterlist (19 regional result sets) | 83,218 records; 60,924 now sector- and administration-enriched | `approved_with_attribution` / releases `published` | Public result sets. Institution-level fields are published with attribution and a recorded takedown route; school-head names stay in the private source store. Rows without an exact SY 2020-2021 Masterlist match remain `DISCOVERY_CANDIDATE`. |
| DepEd Masterlist of Schools, SY 2020-2021 | Official 544-page PDF; 60,924 rows; enrichment-only | `approved_with_attribution` / `published` | Fills missing `ownership`, `ownership_type`, `inclusion_class`, and `school.sector` by exact six-digit BEIS ID. DepEd returns HTTP 403 to automated clients; the preserved Wayback copy (SHA-256 `461a96d3…`) is the release artifact. Does not create or rename facilities and only replaces placeholder classifications; 7-digit private-school variants remain unknown because no official crosswalk exists. |
| DepEd Masterlist SY 2020-2021 — tabular detail (BetterGov dataset 41) | CC BY 4.0 CSV; 60,924 rows; enrichment-only | `approved_with_attribution` / `published` | Fills missing `school.school_management`, `division`, `district`, `legislative_district`, `settlement_type`, `offering_classification`, and derived offering flags by exact BEIS ID. BetterGov attributes the work to DepEd and states CC BY 4.0; the CSV SHA-256 is pinned. Never creates, renames, or reclassifies a facility; unknown offering categories stay null. |
| DepEd Project Bukas enrollment, SY 2024-2025 | 60,129 school IDs; 1,418,514 enrollment observations; enrichment-only | `approved_with_attribution` / `published` | School-level enrollment by grade/strand and sex, plus sector, management and offering flags. `deped.gov.ph` returns HTTP 403 to automated clients; the preserved Wayback ZIP (SHA-256 `fd5dd74a…`) is the release artifact. Zeroes are kept only for levels the school reports as offered, and positive counts survive a conflicting offering flag. Enrollment is a reference-period observation, not current headcount. |
| DepEd Senior High School layer via CHED GIS | 7,886 features; enrichment-only; 1,770 current mapped points | `approved_with_attribution` / `published` | Exact six-digit BEIS ID matching. Supplies school/management/offering fields and a `map_geocoded` point, never a building-level or surveyed location. G11/G12 enrollment columns are deliberately excluded because Project Bukas owns enrollment observations. |
| DepEd MaPaaralan 2019 via OpenStreetMap Philippines | 44,848 rows; 40,082 usable points; link-only | `approved_with_attribution` / `published` | Community-compiled 2019 snapshot of DepEd school points; 35,909 current mapped points. Fills a missing point only, never creates, renames or reclassifies a school. Unmatched or stale six-digit IDs stay as source evidence with a recorded issue. |
| DOH National Health Facility Registry, September 2026 | Official XLSX export; 44,799 facilities; enrichment-only | `approved_with_attribution` / `published` | DOH facility code, major/detail type, ownership sub-classification, PSGC codes, licensing status and bed capacity. The official site returns HTTP 403 to automated clients; the preserved public copy of the same export (SHA-256 `470c967d…`) is the release artifact. 29,779 exact DOH codes fill only missing profile values; 15,020 unmatched official facilities are added. Never renames or reclassifies an established facility. Contact, street/building address and facility-head fields are discarded. Registry presence is not current operating status. |
| CHED HEIDA higher-education directory | 2,716 institution records; 2,711 linked facilities | `publicly_available_verified` / `published` | Public directory; institution-level fields only; no coordinates or PSGC codes. Contact and institutional-head fields are withheld, and institutional types that do not establish ownership are published as unclassified. |
| BetterGov PSGC Q2 2024 mirror | 43,760 geographic units | `approved_with_attribution` (CC BY-SA 4.0) / `published` | Supplementary snapshot; **not** the latest official PSA release. Codes are stored as strings with leading zeros. |
| PSA 2024 Census population via BetterGov | 134,748 observations; 18 regional releases | `approved_with_attribution` (CC BY-SA 4.0 compilation) / `published` | Saved PSA OpenSTAT snapshots, not live PSA data; counts are persons/households as labelled, never facility capacity. |
| NLP public-library directory | Official December 2025 PDF; 1,752 rows | `approved_with_attribution` / `published` | Institutional library fields only; named librarian contacts withheld. |
| NMP regional, area and site museums | Official directory subset | `approved_with_attribution` / `published` | NMP-run sites only; not a census of all Philippine museums. |
| BIR Revenue District Offices | RAO No. 006-2025; 128 RDO rows and 19 region headings | `approved_with_attribution` / `published`; 124 linked facilities | Image-only PDF processed with local OCR; office/jurisdiction list, not addresses or coordinates. |
| DSWD Centers and Residential Care Facilities | Official CRCF directory; 76 facilities | `approved_with_attribution` / `published` | Institutional name, field office and postal address only; no coordinates, admission rules, or inferred operational status. |
| NMIS NARIS accredited meat establishments | Public accreditation directory; 357 facilities | `approved_with_attribution` / `published` | Factual establishment name, LTO number, type and postal address. Many operators are private; a licence is not proof of current operation. Recheck currently returns a WAF/TLS failure, so the verified 15 November 2026 artifact is the release of record. |
| PHLPost post-office locator | Public locator table; 1,272 facilities | `approved_with_attribution` / `published` | Factual locator fields only, with attribution and takedown-on-notice; the page's copyright notice is recorded. |
| PhilHealth Directory of Offices | Official office directory; 293 offices | `approved_with_attribution` / `published` | 19 regional-office groups, including LHIOs, express centres, service desks, business centres, satellite/branch offices and one-stop shops. Name, source category, region grouping and postal address only; telephone, e-mail and schedule text withheld. 261 carry a printed postal address; none carry coordinates. |
| Quezon City LGU directories | Official health-centre and barangay directories; 108 facilities (68 barangay health centres, 40 barangay halls) | `approved_with_attribution` / `published` | Quezon City only. 39 barangay halls carry `map_geocoded` coordinates from LGU-published Google Maps links; health centres have postal addresses only. 7 health offices, 5 COVID-19 swab-testing pages, 1 HOPE page and 102 barangay pages without explicit hall evidence were retained privately and excluded. Phone, e-mail and personal-name fields withheld. |
| Quezon City Places directory | Official visitor directory; 5 facilities (1 public market, 4 parks/open spaces) | `approved_with_attribution` / `published` | Quezon City only. 3 of 5 carry `map_geocoded` coordinates from LGU-published Google Maps links. 23 QCPL library pages were not re-ingested because NLP already publishes 22 QCPL records; 37 museum, church, commercial, campus and monument pages are outside scope. Phone, e-mail, contact-person and social fields withheld. |
| Mandaluyong City barangay directory | Official barangay table; 27 facilities (26 barangay offices, 1 covered-court multi-use record) | `approved_with_attribution` / `published` | Mandaluyong City only. The source publishes an office address, not a barangay-hall classification, so no hall subtype is inferred. One address explicitly names a covered court and is modelled with barangay-office and covered-court functions. No coordinates; telephone numbers and chairperson names withheld. |
| Cainta municipal health-centre directory | Official landing page and six RHU pages; 28 facilities (5 RHUs, 23 barangay health stations) | `approved_with_attribution` / `published` | Cainta, Rizal only. Only records explicitly labelled `(RHU)` or `(BHS)` are published; RHU 5's two unlabelled health centres and the One Cainta satellite health station are retained privately and excluded. The source states 28 health centres, matching the 28 labelled records. No coordinates; contact and personal fields withheld. |
| Pasay City health-centre directory | Official health-care programme page; 14 facilities (13 health centres, 1 lying-in clinic) | `approved_with_attribution` / `published` | Pasay City only. Health centres are published as `OTHER_HEALTH_FACILITY` because the source does not state RHU/BHS level. The lying-in clinic is a separate `CLINIC` with co-location evidence, not merged into the Doña Marta health centre. No coordinates; telephone numbers withheld. |
| HOT/OSM public-service POIs | 25,580 parsed, 25,579 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced map features with unknown ownership; published as `DISCOVERY_CANDIDATE`/unclassified. Not an official government-office or service registry. |
| HOT/OSM airports, heliports and terminals | 297 parsed, 296 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; not a CAAP aerodrome register. Operator, ownership and operational status are not inferred. |
| HOT/OSM sea ports and ferry terminals | 912 parsed, 912 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; not a PPA or MARINA port inventory. PPA's official port list remains the authoritative identity source. |
| HOT/OSM railway stations | 151 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; line/operator and operational status are not inferred beyond source tags. |
| DOE existing power plants | 4 grid releases; 661 parsed, 661 linked facilities | `approved_with_attribution` / `published` | Luzon, Visayas and Mindanao lists are September 2026; off-grid is April 2026. Capacity and status are source-stated, never inferred. |
| NHA GeoServer DOH health-facility layer | 31,016 health facilities | `approved_with_attribution` / `published` | A partial spatial alternate to the DOH NHFR registry export; it adds coordinates and independent evidence, but is not the registry or a completeness claim. |
| NHA landholdings | 169 land/site records | `approved_with_attribution` / `published` | Landholding records only. 946 NHA housing-project records were excluded because they are projects, not facilities; no occupancy or personal data acquired. |
| LRTA Lines 1–2 stations | 33 stations derived from official station-distance tables | `approved_with_attribution` / `published` | Station set derived from the official distance tables; no coordinates added where the source did not provide them. |
| MRT-3 stations | 13 stations from the official station page | `approved_with_attribution` / `published` | Official station page only; no inferred geolocation or operational-status claim. |
| PRC regional offices | 16 offices from the official locator | `approved_with_attribution` / `published` | Regional offices only; offsite service centres absent from the inspected locator. Contact and personal fields withheld. |
| BuCor OPPF operating prison/penal facilities | 7 official records | `approved_with_attribution` / `published` | Only the public institutional fields from the official OPPF list; no security-sensitive operational detail added. |

### Blocked sources

| Source | State | Why |
|---|---|---|
| Official PSA PSGC workbook/API data | `review_required` / `blocked` | Workbook and page return HTTP 403 behind Cloudflare; the classification index returns 200 but collection endpoints require a token. No bypass attempted. |
| DepEd Machine-Ready Files | `review_required` / `blocked` | HTTP 403 and a human download/terms flow that was not completed. |
| DOH HFSRB licensed facilities | `review_required` / `blocked` | HTTP 403; licensing semantics and reuse terms are not established. The broader NHFR registry is published separately from a preserved export. |
| TESDA TVI | `review_required` / `blocked` | Directory page reachable, but the monitor classifies the response as an access challenge; no verified provider-level bulk release. |
| Hazard and additional agency sources | `unknown` / `blocked` | Discovery only; no verified layer or facility release acquired. |

No formal legal review has been completed for any source. Rights states record the collected terms/source evidence and the enforced technical gate; they are not legal advice. The governing policy is [`docs/data-policy.md`](docs/data-policy.md). The exact probe results are in [`docs/operations/evidence/2026-11-15-source-access/source-probes-2026-11-15.txt`](docs/operations/evidence/2026-11-15-source-access/source-probes-2026-11-15.txt).

## Architecture

Monorepo with independently deployable applications:

- `apps/web` — Next.js App Router, TypeScript, shadcn/ui, Tailwind CSS, MapLibre GL JS.
- `apps/api` — FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL/PostGIS reads.
- `apps/ingest` — Python acquisition, source adapters, validation, matching, publication gates, reports.
- `packages/api-client` — TypeScript client generated from the committed OpenAPI contract.
- `database/`, `infra/` — migrations and local PostgreSQL/PostGIS Compose services.

The API is the contract. The web app consumes it through `packages/api-client`; the ingestion pipeline and the web app do not read each other's internals.

```text
official source or permitted API
        ↓
source check / discovery
        ↓
conditional acquisition + SHA-256 + immutable raw store
        ↓
source-specific parser + validation (fail closed)
        ↓
canonical facility, domain observation, geography, provenance
        ↓
rights/publication gate
        ↓
PostgreSQL/PostGIS → FastAPI → directory, map, downloads, third-party clients
```

## API

The public read API is versioned under `/v1`. Important endpoints:

```http
GET /v1/facilities
GET /v1/facilities/{id}
GET /v1/facilities/{id}/sources
GET /v1/facilities/{id}/history
GET /v1/facilities/within?bbox=...
GET /v1/facilities/nearby?lat=...&lon=...&radius_m=...
GET /v1/schools
GET /v1/health-facilities
GET /v1/accreditations
GET /v1/geographies
GET /v1/geographies/{psgc}/facilities
GET /v1/sources
GET /v1/source-releases
GET /v1/source-checks
GET /v1/monitoring
GET /v1/changes
GET /v1/statistics
GET /v1/population
GET /v1/downloads/facilities.csv
GET /v1/downloads/facilities.parquet
GET /v1/downloads/schools.csv
GET /v1/downloads/health-facilities.csv
```

Every public response applies the same publication gate: a facility is exposed only when its canonical flag is public **and** it links to a source release whose dataset rights and publication states permit redistribution. Restricted, internal-only, quarantined, and blocked source records are excluded from detail pages, source evidence, statistics, and bulk exports.

Live examples captured from the running API can be regenerated with `scripts/capture_api_examples.py`; the generated report is written under `var/reports/` and is not source-controlled. The contract is [`packages/api-client/openapi.json`](packages/api-client/openapi.json), with generated types in [`packages/api-client/src/schema.ts`](packages/api-client/src/schema.ts). See [`docs/api.md`](docs/api.md) for the endpoint reference.

## Data-integrity rules

1. **Source truth is preserved.** Original files, values, identifiers, and releases are not overwritten.
2. **Every value is attributable.** Agency, dataset, release, retrieval time, reference period, source record, and checksum are retained.
3. **Unknown is not zero or false.** Missing coordinates, status, capacity, and dates remain null/unknown.
4. **No destructive merges.** Exact identifiers link records; ambiguous candidates require review and retain evidence.
5. **No misleading freshness.** Source publication date, reference period, retrieval time, and processing time are separate.
6. **Rights are enforced in code.** Verified public availability can support publication when no explicit prohibition applies; explicit restrictions, privacy limits, and agreements control.
7. **A map is not the only product.** Every map result is also discoverable through text search and list views.
8. **No invented coverage.** Counts describe ingested records, not the national facility universe.

## Local development

Prerequisites: Docker with Compose, Node.js 22+ (24 tested), pnpm 12+, Python 3.12–3.14, and [uv](https://docs.astral.sh/uv/). A root `justfile` wraps common commands, but each command works without `just`.

1. Install dependencies and start PostgreSQL/PostGIS.

   ```bash
   uv sync --all-packages
   pnpm install
   cp .env.example .env
   docker compose -f infra/compose.yaml up -d db
   ```

2. Apply the schema.

   ```bash
   DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
     uv run alembic -c apps/api/alembic.ini upgrade head
   ```

3. Load the real sources that have recorded publication decisions. This purges any synthetic demo records, records source checks, and loads BetterGov PSGC, PSA 2024 Census population, PhilHealth PDFs, OSM health, education and public-service extracts, and the additional published directories.

   ```bash
   uv run philfacilities-ingest source run --group approved
   uv run philfacilities-ingest status
   ```

   The OSM education file is large. To load sources selectively:

   ```bash
   uv run philfacilities-ingest source run bettergov-psgc
   uv run philfacilities-ingest source run bettergov-population
   uv run philfacilities-ingest source run philhealth
   uv run philfacilities-ingest source run osm-health
   uv run philfacilities-ingest source run osm-education
   uv run philfacilities-ingest source run doh-nhfr
   ```

   DepEd EBEIS is deliberately separate. Its source release is published for institution-level fields with personal fields withheld, and its canonical rows are published as unclassified records pending field-level mapping:

   ```bash
   uv run philfacilities-ingest source run deped-ebeis --region ncr
   ```

4. Start the API and web app in separate terminals.

   ```bash
   PHILFACILITIES_DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
     uv run uvicorn philfacilities_api.main:app --host 127.0.0.1 --port 8010 --reload
   pnpm --filter @philfacilities/web dev
   ```

   Open `http://127.0.0.1:3000`. The API is at `http://127.0.0.1:8010`, with docs at `/docs` and the contract at `/openapi.json`.

   The web app reads `API_BASE_URL` on the server and `NEXT_PUBLIC_API_URL` in the browser. Both default to `http://127.0.0.1:8010`. The demo basemap uses attributed OpenStreetMap raster tiles; set a licensed production provider before launch (see [`docs/decisions/0006-basemap-provider.md`](docs/decisions/0006-basemap-provider.md)).

5. Inspect provenance and monitoring.

   ```bash
   uv run philfacilities-ingest status
   uv run philfacilities-ingest monitoring
   curl -s http://127.0.0.1:8010/v1/statistics | jq
   curl -s http://127.0.0.1:8010/v1/sources | jq
   ```

## Source research and acquisition tooling

The source registers are working research indexes, not approved datasets. Validate the
normalized candidates and rebuild the merged inventory with:

```bash
uv run philfacilities-ingest source-candidates --json
uv run philfacilities-ingest source-inventory
```

`source-inventory` writes `var/reports/source-inventory.json` and
`var/reports/source-inventory.csv`. It merges the Markdown register, the candidate registry and
the dated probe ledgers, and fails on duplicate IDs, invalid taxonomy/state values or malformed
URLs. The JSON preserves per-source provenance and every probe outcome, including HTTP 403, DNS
failures and TLS failures. Core rows use the data.md 25-field schema; the original register access
state is preserved as `access_state_raw`, while the core `access_state` is `OPEN` or `SKIPPED`.
Skipped rows carry `skip_reason`, `skip_detail`, `alternate_route` and `next_retry_at`.

For the full rebuild evidence pack:

```bash
uv run philfacilities-ingest probe-sources
uv run philfacilities-ingest source-inventory \
  --json-output var/reports/rebuild/source-inventory.json \
  --csv-output var/reports/rebuild/source-inventory.csv
uv run philfacilities-ingest source-report --output-dir var/reports/rebuild
uv run philfacilities-ingest source run --group approved
uv run philfacilities-ingest fuse-attributes --apply
uv run philfacilities-ingest match-candidates-generate
uv run philfacilities-ingest fill-locations-from-osm --apply \
  --report var/reports/rebuild/osm-location-fills.json
uv run philfacilities-ingest rebuild-report
```

`probe-sources` performs one unauthenticated GET per registered/candidate URL with a truthful user
agent and per-host delay, caps the response body, and records failures without retrying or bypassing
access controls. `rebuild-report` writes every file in data.md section 11.1 under
`var/reports/rebuild/`. OSM coordinates are a labelled `map_geocoded` community fallback, never an
official coordinate.

For public directory pages, the async crawler provides bounded concurrency, per-host pacing,
`robots.txt` checks, conditional-fetch-friendly request metadata, retries for transient failures,
size/page limits, link discovery and HTML table extraction:

```bash
uv run philfacilities-ingest crawl \
  --url https://lrta.gov.ph/distance-between-stations/ \
  --max-pages 1 --max-depth 0 --rps 1 \
  --output var/crawl/example.jsonl --tables-dir var/crawl/tables
```

The crawler never solves or bypasses a Cloudflare/WAF challenge, CAPTCHA, login, paywall or
licence gate. A challenge or HTTP 403 is recorded as `blocked` and left for an authorized
operator. Live 16 Nov 2026 evidence, including an `robots.txt` refusal, is in
`docs/operations/evidence/2026-11-16-acquisition-toolkit/`.

## Scheduled maintenance

`.github/workflows/source-checks.yml` runs due-source checks daily and, weekly or on manual
dispatch, refreshes only sources with a recorded publication decision through
`scripts/refresh_approved_sources.sh`. A monthly job runs `discover-sources`, which probes
discovery-only official endpoints and uploads JSON evidence without registering or publishing a
dataset. Loaders skip unchanged checksums and never overwrite a retained release. Blocked sources
are not refreshed automatically.

The workflow requires a `PHILFACILITIES_DATABASE_URL` repository/environment secret and skips
cleanly when it is absent. A cron/systemd alternative, failure semantics, and triage steps are in
[`docs/operations/source-monitoring-runbook.md`](docs/operations/source-monitoring-runbook.md).

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest

pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e

uv run python scripts/check_markdown_links.py
```

Integration tests require the test database:

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
```

The default test URL is `postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test`. The database name must end in `_test` because fixtures reset the schema. The test suite uses deterministic synthetic fixtures; that does not make the working database synthetic.

## Documentation

Start with [`docs/README.md`](docs/README.md), or jump directly to:

1. [Getting started](docs/getting-started.md)
2. [Architecture](docs/architecture.md)
3. [Data model](docs/data-model.md)
4. [Data dictionary](docs/data-dictionary.md)
5. [Ingestion](docs/ingestion.md)
6. [Adding a source](docs/adding-a-source.md)
7. [Sources](docs/sources.md)
8. [Public API](docs/api.md)
9. [Web app](docs/web.md)
10. [Design system](docs/design-system.md)
11. [Data policy](docs/data-policy.md)
12. [Testing](docs/testing.md)
13. [Operations](docs/operations.md)
14. [Contributing](docs/contributing.md)

Generated reports are written to `var/reports/` and are not source-controlled. Regenerate them with:

```bash
uv run python scripts/generate_data_reports.py
PHILFACILITIES_API_URL=http://127.0.0.1:8010 uv run python scripts/capture_api_examples.py
```

## Known limitations

- Coverage is partial. CHED HEIDA institution records are published under `publicly_available_verified`. The DOH NHFR September 2026 snapshot covers 44,799 DOH-coded facilities, but registry presence is not operating status and OSM-only health features remain outside it. There is no complete official DepEd, PSA PSGC, or TESDA dataset in the public release; CHED coverage is `NATIONAL_PARTIAL` and not campus-level.
- No official PSA PSGC workbook has been acquired; the BetterGov Q2 2024 mirror is a labelled supplement, not a substitute for the latest official release.
- Public coordinates are `map_geocoded` or source-supplied; there are no GPS-verified or field-verified public coordinates.
- 118,139 public facilities have no current coordinates and remain searchable without map placement.
- 196 located public facilities lack a PSGC assignment; no geography was guessed.
- No accessible national bulk list has been verified for fire stations, police stations, public markets, evacuation centres, barangay halls, or general government offices. Those types are covered mainly by crowd-sourced OSM features, whose ownership and operational status remain unknown rather than inferred.
- OSM duplicate identifiers and missing names are reported as open quality issues rather than silently merged or dropped.
- The Antenatal PhilHealth PDF was re-ingested with the corrected parser. Its first parse had recorded 6,562 rows because the two-up PDF's expiry/sector annex (pages 121–240) was counted as provider rows; that release was withdrawn and its derived records removed. The corrected `philhealth-pdf-1.2.0` parser reads 3,221 provider rows, stops at page 120, and produced 3,221 accreditations for 3,178 existing facilities. Evidence: `docs/operations/evidence/2026-11-16-philhealth-antenatal-reingestion/`. The linked Birthing Homes PDF still returns HTTP 404 and is not replaced with invented data.
- Hosted CI, a hosted scheduled run, production monitoring/paging, a licensed production basemap, production backups/PITR, and external security/legal review remain external release gates.

## License

Application code is Apache-2.0. Data rights vary by source and are recorded in [`DATA-LICENSES.md`](DATA-LICENSES.md); the code licence does not license source data. The data-inclusion policy is in [`docs/data-policy.md`](docs/data-policy.md), and the code/data separation is restated in [`NOTICE`](NOTICE).
