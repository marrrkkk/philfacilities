# Architecture

> **Purpose** — Describe the services, their boundaries, the data flow, and where to change what.
> **Audience** — Developers and agents making cross-cutting changes.
> **Authoritative sources** — the code under `apps/` and `packages/`; decisions in [`decisions/`](decisions/).
> **See also** — [Getting started](getting-started.md) · [Data model](data-model.md) · [Public API](api.md) · [Ingestion](ingestion.md)

## 1. System shape

PhilFacilities is a monorepo with independently deployable services:

```text
official source or permitted API
        ↓
source check / discovery
        ↓
conditional acquisition + SHA-256 + immutable raw store
        ↓
source-specific parser + validation (fail closed)
        ↓
canonical facility, domain observations, geography, provenance
        ↓
rights/publication gate
        ↓
PostgreSQL/PostGIS → FastAPI → directory, map, downloads, MCP, third-party clients
```

The canonical data, provenance, API, and source connectors are the product. The directory and map are clients.

## 2. Repository map

| Path | Responsibility |
|---|---|
| `apps/api` | FastAPI read API, SQLAlchemy models, Alembic migrations, API tests |
| `apps/ingest` | Acquisition, source registry/catalog, connectors, adapters, pipeline, matching, fusion, reports, CLI |
| `apps/web` | Next.js App Router directory, map, facility profiles, data/source pages |
| `apps/mcp` | Read-only MCP adapter over `/v1` for AI clients (stdio and Streamable HTTP) |
| `packages/api-client` | OpenAPI document and generated TypeScript client |
| `database/fixtures` | Deterministic synthetic fixtures and checksum manifest |
| `data/sources` | Candidate index, probe ledger, Geoportal layer index |
| `infra` | PostgreSQL/PostGIS (and optional MinIO) Compose services |
| `scripts` | Backups, smoke checks, benchmarks, report generation, link checks |
| `tests` | Cross-cutting contract, integration, rollback, and source-inventory tests |
| `docs` | These guides, ADRs, operations runbooks/evidence, design audit |

## 3. Service boundaries

### API (`apps/api`)

- Read-only HTTP API under `/v1`; OpenAPI is the contract.
- SQLAlchemy 2 models and PostGIS queries; no ingestion logic in request handlers.
- Applies the publication gate to every public query, detail response, statistic, and export.
- Owns public response schemas and the error envelope.

Key modules: `main.py` (app, middleware, health), `api/` (route families), `services/` (facility queries and publication filters), `rights.py` (rights vocabulary), `taxonomy.py` (public vocabularies), `schemas.py` (response models), `models.py` (schema). See [Public API](api.md).

### Ingest (`apps/ingest`)

- `sources/registry_data.py` + `sources/catalog.py` — the single source registry and connector catalog.
- `sources/connectors/` — acquisition: URLs, paging, conditional requests, signatures, PDF indexes, OSM layers.
- `sources/<source>.py` — adapters that only `parse → validate → normalize`.
- `pipeline/` — release preservation, staging, canonical writes, geography, stats, run reporting.
- `source_runner.py` — generic `run_source`, `validate_source`, `run_selection`.
- `acquisition.py`, `storage.py`, `validators.py`, `matching.py`, `fusion.py`, `release_rollback.py` — shared machinery.
- `cli.py` and `commands/` — Typer apps and command bodies grouped by domain.

No source-specific branch belongs in `pipeline/`; new sources register metadata and a connector. See [Ingestion](ingestion.md).

### Web (`apps/web`)

- Next.js App Router with server components for data fetching.
- Consumes the API through `packages/api-client`; never connects to PostgreSQL.
- MapLibre for the map; the directory remains usable without map tiles.
- Design tokens derive from the measured reference; see [Design system](design-system.md).

### API client (`packages/api-client`)

Generated from `openapi.json`. Do not hand-edit `src/schema.ts`; regenerate with `just typegen`.

### MCP (`apps/mcp`)

- Read-only MCP server with a curated set of task-named tools, not an endpoint dump.
- Calls the public `/v1` API over HTTP only: no database credentials, no imports of `philfacilities_api`, no arbitrary URLs, no second copy of the publication gate.
- Passes API payloads through unchanged so nulls, `is_synthetic`, precision, rights, and source evidence survive. Contract tests check tool paths and arguments against the committed OpenAPI document.
- stdio for local clients; stateless Streamable HTTP at `/mcp` for hosted clients. See [MCP](mcp.md) and [ADR 0009](decisions/0009-mcp-server-boundary.md).

## 4. Data ownership

| Store | Owner | Notes |
|---|---|---|
| PostgreSQL/PostGIS | API + ingest | Canonical and source schemas; the API reads, ingest writes |
| Raw object store | ingest | Content-addressed files; filesystem or S3-compatible |
| OpenAPI document | API | Committed contract; generated client follows it |
| Source registry | ingest | Code-defined source metadata and rights, not a database table |
| Rights register | repository | `DATA-LICENSES.md` plus dataset rows in `source.datasets` |

Ingest may read the API's models/migrations package but must not import API request code. The web app must not read ingest internals.

## 5. Publication boundary

Public exposure requires all of:

1. `core.facilities.publication_status = 'public'`;
2. a source link to a release whose dataset `redistribution_status` is in `PUBLIC_RIGHTS`;
3. dataset and release `publication_status` in `approved`/`published`;
4. the link belongs to the dataset's latest published release.

The gate is implemented once in `apps/api/philfacilities_api/rights.py` and used by facility queries, detail, source evidence, statistics, coverage, and downloads. See [Data policy](data-policy.md) and [Public API](api.md).

## 6. Environments

| Environment | Database | Data | Purpose |
|---|---|---|---|
| `local` | Compose PostgreSQL/PostGIS on port 54329 | Rights-cleared real sources; synthetic fixtures only in tests | Development |
| `test` | Compose `test-db` on port 54330 | Synthetic fixtures; schema reset between runs | Integration tests |
| `staging` | Managed/self-hosted PostGIS | Publication-approved data only | Pre-production verification |
| `production` | Managed/self-hosted PostGIS | Approved releases only | Public service |

Never use restricted FOI files or agreement-bound data in a public staging or production environment unless the agreement permits it. The working local database contains real publication-approved data; it is not a synthetic demo.

## 7. Runtime dependencies

- Python 3.12–3.14; uv workspace with `philfacilities-api`, `philfacilities-ingest`, `philfacilities-mcp` (and `philfacilities-mcp-http`).
- Node.js 22+ (24 tested), pnpm 12+.
- PostgreSQL 17 + PostGIS 3.5.
- Optional S3-compatible object storage (MinIO profile in Compose).
- MapLibre GL JS with a configurable basemap; the demo uses attributed OpenStreetMap raster tiles.

## 8. Where to change what

| Change | Start here |
|---|---|
| New source | [Adding a source](adding-a-source.md) |
| Parser/validation bug | `apps/ingest/philfacilities_ingest/sources/<source>.py`, then `source validate` |
| Pipeline lifecycle | `apps/ingest/philfacilities_ingest/pipeline/` |
| New public field/endpoint | `apps/api/philfacilities_api/`, migration, OpenAPI, client, data dictionary |
| Identity matching | `matching.py`, `aggregation.py`, `quality.match_candidates`, API review endpoints |
| Attribute conflicts | `fusion.py`, `core.facility_attribute_fusions` |
| Rights/publication | `rights.py`, dataset/release rows, [Data policy](data-policy.md) |
| Web route or component | `apps/web/src/app/`, `apps/web/src/components/` |
| MCP tool or transport | `apps/mcp/philfacilities_mcp/tools/`, `server.py`, `http.py`, [MCP](mcp.md) |
| Visual token | `apps/web/src/app/globals.css`, [Design system](design-system.md) |
| Deployment/backup/monitoring | [Operations](operations.md), `docs/operations/` |
| Architecture decision | New ADR in `docs/decisions/` |

## 9. Decisions

Architecture decisions are recorded in [ADRs](decisions/README.md): monorepo boundaries, canonical identity, temporal releases, data rights, coordinate precision, basemap, API versioning, publicly available data inclusion, and the public-API-only MCP boundary. Add a new ADR rather than rewriting an accepted one; mark supersession explicitly.
