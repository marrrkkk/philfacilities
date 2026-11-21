<p align="center">
  <img src="docs/assets/philfacilities-icon.svg" alt="PhilFacilities icon — a facility pin grounded on a registry baseline" width="96" height="96">
</p>

# PhilFacilities

[![CI](https://github.com/marrrkkk/philfacilities/actions/workflows/ci.yml/badge.svg)](https://github.com/marrrkkk/philfacilities/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

**An open, source-linked registry of Philippine schools, health facilities, public-service facilities, and community venues — exposed as reusable public data infrastructure.**

PhilFacilities acquires publicly available and permitted government and community datasets, preserves every original release, normalizes records without destroying source values, enforces a documented publication gate, and serves the result through a read-only API, searchable directory, map, bulk downloads, and an MCP server for AI clients. It is built for researchers, journalists, service designers, civic technologists, and developers who need attributable facility data rather than an unsourced point on a map.

> **Status:** real-data pipeline operational; coverage is partial and not nationwide-complete. Measured 18 November 2026: 273,369 canonical facilities, 85 registered datasets, 103 retained source releases. Synthetic records are absent from the working database. Live figures come from `/v1/statistics` and `/v1/coverage`; see [Current data state](#current-data-state) and [Known limitations](#known-limitations).

## Why it exists

Facility data in the Philippines is scattered across agency PDFs, directories, GIS layers, and FOI responses, often without stable identifiers, machine-readable formats, or reuse terms. PhilFacilities makes that data **findable, attributable, and safely reusable**:

- **Source-linked** — every published field traces back to an exact source record, release, checksum, and retrieval time.
- **Honest about uncertainty** — missing values stay missing; centroid and geocoded points are labelled; registry presence is never presented as "open now".
- **Rights-aware** — publication is gated in code by a recorded rights decision; restricted and personal data stay out of public outputs.
- **API-first** — the OpenAPI contract is the product; the directory, map, MCP server, and third-party clients all consume the same publication-gated `/v1` API.

## What you can do

- Search and filter 270k+ facilities by type, subtype, ownership, access, geography (PSGC), source, precision, and reference period.
- Retrieve field-level provenance, source evidence, and change history for any facility.
- Find facilities within a bounding box or near a point; map results fall back to count clusters at wide zoom levels.
- Download the full published dataset as CSV or Parquet.
- Query geography releases, PSA population observations, accreditations, coverage, monitoring, and quality signals.
- Ask AI clients about facilities and their provenance through a curated, read-only MCP tool surface.

## Quick start

### Use the API

The public read API requires no key. Start with the API index and statistics:

```bash
curl -s https://api.example.org/v1 | jq
curl -s https://api.example.org/v1/statistics | jq
curl -s 'https://api.example.org/v1/facilities?q=library&limit=5' | jq
```

> No hosted deployment URL is configured in this checkout. The examples above use a placeholder origin; run the API locally (below) or point `API_BASE_URL` at your own deployment. Interactive docs are at `/docs` and the machine-readable contract at `/openapi.json`.

### Run locally

Prerequisites: Docker with Compose, Python 3.12–3.14 + [uv](https://docs.astral.sh/uv/), Node.js 22+ (24 tested), and pnpm 12+. The lowercase `justfile` wraps the commands below; each is also a plain shell command.

```bash
cp .env.example .env
just setup                 # install dependencies, start PostgreSQL/PostGIS, apply migrations

# Load the rights-cleared real sources (skips the large DepEd EBEIS acquisition)
uv run philfacilities-ingest source run --group approved --exclude deped-ebeis

just api                   # FastAPI at http://127.0.0.1:8010  (docs at /docs)
just web                   # Next.js at http://127.0.0.1:3000
```

For a synthetic-only database instead, run `just demo`. Every synthetic record is labelled. See [Getting started](docs/getting-started.md) for prerequisites, ports, test-database setup, and troubleshooting.

## API at a glance

Base path `/v1`, JSON responses, read-only, no authentication for public reads. Cursor pagination for lists (`cursor`, `next_cursor`, `has_more`); `limit` defaults to 20 and is capped at 100.

```bash
# Search facilities
curl -s 'http://127.0.0.1:8010/v1/facilities?type=school&psgc=1300000000&limit=5' | jq

# One facility plus its source evidence
curl -s http://127.0.0.1:8010/v1/facilities/<uuid-or-slug> | jq
curl -s http://127.0.0.1:8010/v1/facilities/<uuid-or-slug>/sources | jq

# Spatial and bulk
curl -s 'http://127.0.0.1:8010/v1/facilities/nearby?lat=14.6&lon=120.98&radius_m=2000' | jq
curl -s http://127.0.0.1:8010/v1/downloads/facilities.csv -o facilities.csv
```

| Endpoint family | Examples |
|---|---|
| System | `GET /healthz`, `GET /v1`, `GET /v1/taxonomy` |
| Facilities | `GET /v1/facilities`, `/facilities/{id}`, `/facilities/{id}/sources`, `/facilities/{id}/assertions`, `/facilities/{id}/history`, `/facilities/within`, `/facilities/nearby`, `/facilities/map` |
| Schools & health | `GET /v1/schools`, `GET /v1/health-facilities`, `GET /v1/accreditations` |
| Geography & population | `GET /v1/geographies`, `/geography-releases`, `/geography-crosswalk`, `GET /v1/population` |
| Sources & monitoring | `GET /v1/sources`, `/source-releases`, `/source-checks`, `/monitoring`, `/coverage`, `/statistics`, `/changes`, `/quality/*` |
| Bulk downloads | `GET /v1/downloads/facilities.csv`, `facilities.parquet`, `schools.csv`, `health-facilities.csv` |

Full filter tables, error envelope, caching, and the publication boundary are in the [Public API guide](docs/api.md). The machine-readable contract is [`packages/api-client/openapi.json`](packages/api-client/openapi.json); a generated TypeScript client lives in `packages/api-client`. The [Data dictionary](docs/data-dictionary.md) documents every consumer-facing field.

Errors use a consistent envelope: `{ "error": { "code", "message", "details", "request_id" } }`. Every response carries `X-Request-ID` and `X-Response-Time-Ms`.

## MCP for AI clients

A read-only [MCP](docs/mcp.md) server calls the same publication-gated `/v1` API as the web app — no database credentials, no separate rights gate, no reshaped responses. Ten curated tools cover facility search and provenance, nearby search, geography, population, sources, coverage, taxonomy, and downloads.

```bash
just mcp        # stdio (requires just api)
just mcp-http   # Streamable HTTP at http://127.0.0.1:8011/mcp
just mcp-test   # tool, contract, and transport tests
```

Local client config:

```json
{
  "mcpServers": {
    "philfacilities": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/philfacilities", "philfacilities-mcp"],
      "env": { "PHILFACILITIES_API_BASE_URL": "http://127.0.0.1:8010" }
    }
  }
}
```

Hosted deployments need host/origin allowlists and edge rate limiting; see [MCP](docs/mcp.md) and [ADR 0009](docs/decisions/0009-mcp-server-boundary.md).

## Architecture

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

| Workspace | Responsibility |
|---|---|
| `apps/web` | Next.js App Router directory, map, and facility profiles; a read-only API client |
| `apps/api` | FastAPI read API, SQLAlchemy 2 models, Alembic migrations |
| `apps/ingest` | Acquisition, source adapters, validation, matching, fusion, publication gates, reports |
| `apps/mcp` | Read-only MCP adapter over `/v1` (stdio and Streamable HTTP) |
| `packages/api-client` | OpenAPI contract and generated TypeScript client |
| `database/`, `infra/` | Fixtures and local PostgreSQL/PostGIS Compose services |

The API is the contract: the web app consumes it through `packages/api-client`, and neither the web app nor the MCP server reads ingest internals or connects to PostgreSQL. See [Architecture](docs/architecture.md) and [Data model](docs/data-model.md).

## Current data state

Measured from the configured PostgreSQL/PostGIS database on 18 November 2026:

| Measure | Value |
|---|---|
| Canonical / public facilities | 273,369 / 273,369 |
| Facilities with coordinates | 155,230 (all `map_geocoded` or source-supplied) |
| Facilities without coordinates | 118,139 (searchable, never given invented points) |
| Registered datasets / retained releases | 85 / 103 |
| Published geographic units | 43,760 (BetterGov PSGC Q2 2024 mirror) |
| Population observations | 134,748 across 18 PSA 2024 Census regional releases |
| Health accreditations | 28,207 across 26 PhilHealth provider categories |

These describe processed source records, not the national facility universe. The source-by-source breakdown, including rights states and caveats, is in [Sources](docs/sources.md) and live at `/v1/sources` and `/v1/coverage`. No formal legal review has been completed; rights states record collected evidence and the enforced gate, not legal advice. See [Data policy](docs/data-policy.md) and [DATA-LICENSES.md](DATA-LICENSES.md).

## Data integrity and rights

1. **Source truth is preserved** — original files, values, identifiers, and releases are not overwritten.
2. **Every value is attributable** — agency, dataset, release, retrieval time, reference period, source record, and checksum are retained.
3. **Unknown is not zero or false** — missing coordinates, status, capacity, and dates stay unknown.
4. **No destructive merges** — exact identifiers link records; ambiguous candidates retain evidence.
5. **No misleading freshness** — source publication date, reference period, retrieval time, and processing time are separate.
6. **Rights are enforced in code** — verified public availability can support publication when no explicit prohibition applies; explicit restrictions, agreements, and privacy limits control.
7. **A map is not the only product** — every map result is discoverable through text search and list views.
8. **No invented coverage** — counts describe ingested records, not the national facility universe.

The full policy, including the eligibility checklist, rights states, and takedown process, is in [Data policy](docs/data-policy.md).

## Documentation

Start with the [documentation index](docs/README.md), or jump directly to:

1. [Getting started](docs/getting-started.md) — setup, running the stack, troubleshooting
2. [Architecture](docs/architecture.md) — services and boundaries
3. [Public API](docs/api.md) — developer-facing API usage
4. [Data model](docs/data-model.md) — schema, identity, provenance
5. [Data dictionary](docs/data-dictionary.md) — consumer-facing fields and vocabularies
6. [Ingestion](docs/ingestion.md) — how records become canonical
7. [Adding a source](docs/adding-a-source.md) — new source checklist
8. [Sources](docs/sources.md) — research register and access reality
9. [Data policy](docs/data-policy.md) — rights, privacy, publication
10. [Web app](docs/web.md) and [Design system](docs/design-system.md)
11. [MCP](docs/mcp.md) — AI client adapter
12. [Testing](docs/testing.md) and [Operations](docs/operations.md)
13. [Contributing](docs/contributing.md)
14. [Decisions](docs/decisions/README.md) — ADRs 0001–0009

Generated reports go to `var/reports/` and are not source-controlled. Regenerate them with `uv run python scripts/generate_data_reports.py` and `PHILFACILITIES_API_URL=http://127.0.0.1:8010 uv run python scripts/capture_api_examples.py`.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest --require-integration

pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e

uv run python scripts/check_markdown_links.py
```

`just check` runs lint, typecheck, pytest, build, and the link check. Integration tests use a dedicated database whose name must end in `_test` (default port 54330); start it with `docker compose -f infra/compose.yaml --profile test up -d test-db`. See [Testing](docs/testing.md).

## Known limitations

- Coverage is partial. There is no complete official national DepEd, PSA PSGC, or TESDA dataset in the public release; the BetterGov Q2 2024 PSGC mirror is a labelled supplement, not the latest official PSA release.
- Public coordinates are `map_geocoded` or source-supplied; there are no GPS-verified or field-verified public coordinates. 118,139 public facilities have no point and remain searchable only in text.
- OSM/HOT records are crowd-sourced map features, not official registries; ownership and operational status are unknown rather than inferred.
- A private provider listed by a regulator is never counted as government-owned; accreditation is not ownership or current operation.
- Hosted deployment, production rate-limit policy, external monitoring/paging, a licensed production basemap, backups/PITR, and external security/legal review remain external release gates. Unfiltered facility-list latency needs query-plan and caching work before launch.

## Contributing

Contributions are welcome. Read [Contributing](docs/contributing.md), [Getting started](docs/getting-started.md), and the guide for the area you are touching. Work in small vertical slices, add tests, update the relevant doc in the same change, and run the checks. Do not invent source facts or commit secrets, personal data, or restricted source rows. Report vulnerabilities privately per [SECURITY.md](SECURITY.md).

## License

Application code is **Apache-2.0** ([LICENSE](LICENSE), [NOTICE](NOTICE)). That licence does not grant rights to agency source data: source-data rights and publication decisions are recorded per dataset in [DATA-LICENSES.md](DATA-LICENSES.md) and [Sources](docs/sources.md). The inclusion policy is [Data policy](docs/data-policy.md). By contributing code, you agree it may be distributed under the repository's code licence.
