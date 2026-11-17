# 12 — Implementation Roadmap

This roadmap is ordered by dependency and acceptance gates, not by calendar promises. Status reflects the implementation on 15 November 2026.

## Phase 0 — Project foundation and design audit — DONE (hosted CI observation open)

Deliverables:

- Repository initialized as a monorepo.
- `AGENTS.md`, contributing/license files, and connected docs in place.
- Python `uv` and TypeScript `pnpm` workspace configured.
- Docker Compose with PostgreSQL/PostGIS.
- CI baseline for lint, type check, tests, migrations.
- BetterGov Fellowship visual system audited in a real browser and translated into shadcn/Tailwind tokens.

Exit gate: reproducible local setup; measured design tokens and screenshots; architecture decisions recorded. Hosted Actions observation remains open.

## Phase 1 — Source acquisition and rights validation — IN PROGRESS

Acquired and published with recorded rights:

- PhilHealth 26 provider-category releases: 28,207 accreditations.
- HOT/OSM health and education GeoParquet: 70,234 linked facilities.
- BetterGov PSGC Q2 2024 mirror: 43,760 geographic units.
- PSA 2024 Census population via BetterGov: 134,748 observations.
- NLP public-library directory: 1,752 institution-level rows.
- NMP regional/area/site museums: official directory subset.
- BIR Revenue Region and RDO list: 128 RDO rows and 19 region headings.

Acquired; source release published for institution-level fields, canonical rows internal:

- DepEd EBEIS NCR: 5,055 school rows. The current source release applies the institution-level publication decision; school-head names are withheld. Canonical facility rows remain `internal` pending field-level mapping and privacy review.

Blocked or unverified:

- Official PSA PSGC workbook/API (HTTP 403 / token required).
- DepEd Machine-Ready Files (HTTP 403 / human terms flow).
- DOH NHFR/HFSRB (HTTP 403; agreement not reviewed).
- CHED and TESDA bulk releases (no verified bulk export or public API).
- Hazard layers and additional agency facility releases (no verified release).

Exit gate: at least one school dataset and one healthcare source are schema-verified and publication scope is approved. The healthcare and OSM sides are met; official school data is acquired, its source release is published for institution-level fields, and canonical-row publication still requires field-level mapping and privacy review.

## Phase 2 — Canonical data model and geography — DONE

Deliverables:

- PostgreSQL/PostGIS schemas and migrations.
- Versioned PSGC hierarchy and release crosswalk.
- Canonical facility records and source-record links.
- Source-release, raw-record, provenance, and ingestion-run models.
- Coordinate precision and data-quality issue models.
- Deterministic test fixtures separate from production data.

Exit gate: unit and migration tests pass; same source file loads idempotently; an old PSGC release remains queryable.

## Phase 3 — Ingestion pipelines — DONE for accessible sources

Deliverables:

- BetterGov PSGC ingestion with a real Q2 2024 release.
- PhilHealth PDF parser and 26 published categories.
- HOT/OSM GeoParquet ingestion with bbox-centre precision.
- PSA 2024 Census population connector.
- DepEd EBEIS internal-only ingestion.
- Repeatable source-release reports, checksums, and immutable raw storage.
- Duplicate and cross-source match-candidate queue.

Blocked parsers: official DepEd Machine-Ready files and DOH NHFR. Their adapters are fixture-tested only and are not presented as real coverage.

Exit gate: end-to-end ingestion of a representative release for each approved source; no silent parser failures; quality report produced. Met for the published sources.

## Phase 4 — Public API v1 — DONE

Deliverables:

- Facilities search/detail endpoints.
- School/health domain endpoints for approved records.
- Accreditation, population, geography, source/provenance, history, monitoring, and source-check endpoints.
- Spatial bounding-box/nearby queries.
- Bulk CSV/Parquet exports behind the publication gate.
- OpenAPI (39 paths) and generated TypeScript client.
- Rate limits, response limits, structured errors, and CORS.

Exit gate: contract tests, pagination tests, privacy/rights review, and API documentation. All engineering gates are met; formal legal review is not.

## Phase 5 — Web directory and facility profiles — DONE

Deliverables:

- BetterGov reference design translated to tokens and shadcn/ui.
- Product-specific header navigation.
- Landing/search entry with real measured statistics.
- Directory page, filters, result list, empty/loading/error states.
- Facility detail pages with source records, reference periods, quality warnings, and history.
- Responsive and accessible behavior.

Exit gate: Playwright flows pass; data is not presented as live/current when source periods are old; screen reader and keyboard checks pass.

## Phase 6 — Interactive map — REVIEW

Deliverables:

- MapLibre integration and configurable tile source.
- Bounding-box API query.
- Marker clustering and selected facility panel.
- Desktop split view and mobile map/list behavior.
- Precision-aware map rendering.
- Attribution and map failure fallback.

Open: a licensed production basemap provider. The current OSM raster default is attributed but is not a production tile decision.

Exit gate: map loads only publishable coordinates; low-precision points are clearly represented; text directory remains usable if tiles fail. Met technically; provider gate open.

## Phase 7 — Public release and operational hardening — IN PROGRESS

Deliverables:

- Dataset/source catalogue.
- Bulk CSV/Parquet exports where permitted.
- Data quality and source freshness status page.
- Restore-tested backups.
- Monitoring and incident runbooks.
- Source-check scheduling and rights-cleared refresh script.
- Security review and dependency audit.
- Public contribution guide and issue templates.

Open gates:

- Hosted CI and hosted scheduled-run observation.
- Production monitoring, paging, and alert destination.
- Production backups, off-host retention, encryption, and PITR.
- Licensed production basemap.
- External penetration test and deployed-origin CSP verification.
- Formal legal review of source publication decisions.
- Query-performance optimization for statistics and facility lists; pre-generated bulk exports.

Exit gate: all source publication gates pass, operational metrics are monitored, and release notes clearly state coverage and limitations. Not yet met.

## Phase 8 — Expansion — DEFERRED

Candidate sources/features:

- CHED institution data after a permitted machine-readable source is verified.
- TESDA provider/assessment-centre data after bulk access/schema validation.
- Further PhilHealth provider categories.
- Facility corrections and public review process.
- School Access Index and Health Access Index, with methodology review.
- Facility hazard exposure and infrastructure project crosswalks.
- Additional agency facility data (DILG, BFP, PNP, BJMP, DSWD, DPWH, NAMRIA, NHA, NLP, LWUA, DOTr, DICT).

Each expansion requires source acquisition, terms review, schema design, and quality metrics before frontend work. No expansion source is a dependency of the current release.
