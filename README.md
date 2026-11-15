# PhilFacilities

> **An open, source-linked registry of Philippine schools and health facilities, built as reusable public data infrastructure.**

**Status date:** 15 November 2026  
**Implementation state:** real-data pipeline operational; coverage is partial and not nationwide-complete. Synthetic records are absent from the working production database.

PhilFacilities acquires publicly available and permitted data, preserves every original release, normalizes records without destroying source values, enforces source-rights publication gates, and exposes the result through a versioned read API, searchable directory, map, and bulk downloads.

## Current data state

Measured from the configured PostgreSQL/PostGIS database on 15 November 2026:

| Measure | Actual state |
|---|---|
| Canonical facilities | **92,422** |
| Public facilities | **61,806** (API-gated) |
| Non-public facilities | **30,616** (DepEd internal, blocked, review-pending, or otherwise not publication-approved) |
| Synthetic facilities in the working database | **0** |
| Registered datasets | **44** |
| Retained source releases | **55** |
| Published geographic units | **43,760** (BetterGov PSGC Q2 2024 mirror) |
| Published population observations | **134,748** across 18 PSA 2024 Census regional releases |
| Published health accreditations | **24,986** across 25 PhilHealth provider categories |
| Public facilities with coordinates | **44,751**, all `map_geocoded` |
| Public facilities without coordinates | **17,055** (kept in text search; never given invented coordinates) |

These counts describe processed source records, not the complete national facility universe. OSM/HOT records are crowd-sourced map features, not official DOH or DepEd registries. The DepEd EBEIS NCR extract contains school-head names; the current source release is approved for institution-level publication with those names withheld, while the canonical DepEd facility records remain `internal`/`DISCOVERY_CANDIDATE` pending field-level mapping and privacy review. See [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md).

### Published sources

| Source | Data used | Rights/publication state | Caveat |
|---|---|---|---|
| PhilHealth accredited healthcare facilities | 25 provider-category PDFs, 24,986 accreditations | `approved_with_attribution` / `published` | Accreditation is benefit-package-specific and time-bound; one linked PDF (`MCP_073126.pdf`) returns HTTP 404; one acquired Antenatal release is retained but blocked after review (see below). |
| HOT/OSM health extract | 17,421 source records; 17,410 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; coordinates are bounding-box centres (`map_geocoded`); operational status unknown. |
| HOT/OSM education extract | 52,839 source records; 52,824 linked facilities | `approved_with_attribution` (ODbL) / `published` | Crowd-sourced; not a DepEd masterlist; same coordinate/status caveats. |
| BetterGov PSGC Q2 2024 mirror | 43,760 geographic units | `approved_with_attribution` (CC BY-SA 4.0) / `published` | Supplementary snapshot; **not** the latest official PSA release. Codes are stored as strings with leading zeros. |
| PSA 2024 Census population via BetterGov | 134,748 observations; 18 regional releases | `approved_with_attribution` (CC BY-SA 4.0 compilation) / `published` | Saved PSA OpenSTAT snapshots, not live PSA data; counts are persons/households as labelled, never facility capacity. |
| NLP public-library directory | Official December 2025 PDF; 1,752 rows | `approved_with_attribution` / `published` | Institutional library fields only; named librarian contacts withheld. |
| NMP regional, area and site museums | Official directory subset | `approved_with_attribution` / `published` | NMP-run sites only; not a census of all Philippine museums. |
| BIR Revenue District Offices | RAO No. 006-2025; 128 RDO rows and 19 region headings | `approved_with_attribution` / `published`; 124 linked facilities | Image-only PDF processed with local OCR; office/jurisdiction list, not addresses or coordinates. |
| DSWD Centers and Residential Care Facilities | Official CRCF directory; 76 facilities | `approved_with_attribution` / `published` | Institutional name, field office and postal address only; no coordinates, admission rules, or inferred operational status. |
| NMIS NARIS accredited meat establishments | Public accreditation directory; 357 facilities | `approved_with_attribution` / `published` | Factual establishment name, LTO number, type and postal address. Many operators are private; a licence is not proof of current operation. Recheck currently returns a WAF/TLS failure, so the verified 15 November 2026 artifact is the release of record. |
| PHLPost post-office locator | Public locator table; 1,272 facilities | `approved_with_attribution` / `published` | Factual locator fields only, with attribution and takedown-on-notice; the page's copyright notice is recorded. |

### Internal-only and blocked sources

| Source | State | Why |
|---|---|---|
| DepEd EBEIS school masterlist (NCR) | `approved_with_attribution` / release `published`; canonical facilities `internal` | Public result set. The current source release is approved for institution-level publication with attribution and a recorded takedown route, and withholds school-head names. The canonical facility rows remain `internal`/`DISCOVERY_CANDIDATE` until field-level mapping and privacy review; 5,055 rows are retained. |
| Official PSA PSGC workbook/API data | `review_required` / `blocked` | Workbook and page return HTTP 403 behind Cloudflare; the classification index returns 200 but collection endpoints require a token. No bypass attempted. |
| DepEd Machine-Ready Files | `review_required` / `blocked` | HTTP 403 and a human download/terms flow that was not completed. |
| DOH NHFR and HFSRB licensed facilities | `review_required` / `blocked` | HTTP 403 behind Cloudflare; applicable data-use agreement has not been reviewed or accepted. |
| CHED HEIDA | `review_required` / `blocked` | Public directory reachable (HTTP 200), but no verified bulk export or documented public API. A verified public release with no explicit prohibition can be published under `publicly_available_verified`. |
| TESDA TVI | `review_required` / `blocked` | Directory page reachable, but the monitor classifies the response as an access challenge; no verified provider-level bulk release. |
| Hazard and additional agency sources | `unknown` / `blocked` | Discovery only; no verified layer or facility release acquired. |

No formal legal review has been completed for any source. Rights states record the collected terms/source evidence and the enforced technical gate; they are not legal advice. The governing policy is [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md). The exact probe results are in [`docs/operations/evidence/2026-11-15-source-access/source-probes-2026-11-15.txt`](docs/operations/evidence/2026-11-15-source-access/source-probes-2026-11-15.txt).

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

Live examples captured from the running API are in [`docs/reports/07-real-api-examples.md`](docs/reports/07-real-api-examples.md). The contract is [`packages/api-client/openapi.json`](packages/api-client/openapi.json), with generated types in [`packages/api-client/src/schema.ts`](packages/api-client/src/schema.ts).

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

3. Load the real sources that have recorded publication decisions. This purges any synthetic demo records, records source checks, and loads BetterGov PSGC, PSA 2024 Census population, PhilHealth PDFs, OSM health/education extracts, and the additional published directories.

   ```bash
   uv run philfacilities-ingest load-real --skip-deped
   uv run philfacilities-ingest status
   ```

   The OSM education file is large. To load sources selectively:

   ```bash
   uv run philfacilities-ingest load-psgc-bettergov
   uv run philfacilities-ingest load-population
   uv run philfacilities-ingest load-philhealth
   uv run philfacilities-ingest load-osm --domain health
   uv run philfacilities-ingest load-osm --domain education
   ```

   DepEd EBEIS is deliberately separate. Its current source release is approved for institution-level publication with personal fields withheld, while the canonical rows remain `internal` pending field-level mapping and privacy review:

   ```bash
   uv run philfacilities-ingest load-deped-ebeis --region ncr
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

## Scheduled maintenance

`.github/workflows/source-checks.yml` runs due-source checks daily and, weekly or on manual
dispatch, refreshes only sources with a recorded publication decision through
`scripts/refresh_approved_sources.sh`. A monthly job runs `discover-sources`, which probes
discovery-only official endpoints and uploads JSON evidence without registering or publishing a
dataset. Loaders skip unchanged checksums and never overwrite a retained release. Blocked and
internal-only sources are not refreshed automatically.

The workflow requires a `PHILFACILITIES_DATABASE_URL` repository/environment secret and skips
cleanly when it is absent. A cron/systemd alternative, failure semantics, and triage steps are in
[`docs/operations/source-monitoring-runbook.md`](docs/operations/source-monitoring-runbook.md).

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
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

Regenerate the measured reports after a material data change:

```bash
uv run python scripts/generate_data_reports.py
PHILFACILITIES_API_URL=http://127.0.0.1:8010 uv run python scripts/capture_api_examples.py
```

## Documentation

Start with:

1. [Project charter](docs/01-PROJECT-CHARTER.md)
2. [Architecture](docs/02-ARCHITECTURE.md)
3. [Source register](docs/03-SOURCE-REGISTER.md)
4. [Data model](docs/04-DATA-MODEL.md)
5. [Ingestion and ETL](docs/05-INGESTION-ETL.md)
6. [Public API](docs/06-PUBLIC-API.md)
7. [Data dictionary](docs/DATA-DICTIONARY.md)
8. [Web product and UX](docs/07-WEB-PRODUCT-UX.md)
9. [Quality and testing](docs/10-QUALITY-TESTING.md)
10. [Deployment and operations](docs/11-DEPLOYMENT-OPERATIONS.md)
11. [Source monitoring runbook](docs/operations/source-monitoring-runbook.md)
12. [Data inclusion and publication policy](docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md)
13. [Tracker](planning/TRACKER.md)

Required data reports are under [`docs/reports/`](docs/reports/):

- `01-source-directory.md`
- `02-acquisition-report.md`
- `03-schema-report.md`
- `04-data-quality-report.md`
- `05-source-rights-report.md`
- `06-ingestion-runbook.md`
- `07-real-api-examples.md`

## Known limitations

- Coverage is partial. There is no complete official DepEd, DOH, PSA PSGC, CHED, or TESDA dataset in the public release.
- No official PSA PSGC workbook has been acquired; the BetterGov Q2 2024 mirror is a labelled supplement, not a substitute for the latest official release.
- Public coordinates are all OSM bounding-box centres. There are no GPS-verified or field-verified public coordinates.
- 17,055 public facilities have no current coordinates and remain searchable without map placement.
- 14,216 located public facilities lack a PSGC assignment; no geography was guessed.
- OSM duplicate identifiers and missing names are reported as open quality issues rather than silently merged or dropped.
- The Antenatal PhilHealth PDF is retained but blocked. Its first successful parse recorded 6,562 rows, then a post-ingestion review found that the two-up PDF's expiry/sector annex (pages 121–240) had been counted as provider rows. All derived records were withdrawn, 3,178 facilities were restored from the parse's `EMCB-ANTE` subtype to their recorded prior values, and 3,184 source-less history events were exported and removed; the corrected parser re-reads 3,221 provider rows, and the release awaits validated re-ingestion. The linked Birthing Homes PDF returns HTTP 404. Neither gap is filled with invented data.
- Hosted CI, a hosted scheduled run, production monitoring/paging, a licensed production basemap, production backups/PITR, and external security/legal review remain external release gates.

## License

Application code is Apache-2.0. Data rights vary by source and are recorded in [`DATA-LICENSES.md`](DATA-LICENSES.md); the code licence does not license source data. The data-inclusion policy is in [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md), and the code/data separation is restated in [`NOTICE`](NOTICE).
