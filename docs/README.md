# PhilFacilities documentation

> **Audience** — Developers, contributors, and AI agents working on or with PhilFacilities.
> **Purpose** — Explain how the system works and how to change it safely.
> **Agent brief** — [`../AGENTS.md`](../AGENTS.md) is the short operating brief; this index is the full map.
> **Product** — An open, source-linked registry of Philippine schools, health facilities, public-service facilities, and community venues. The canonical data, provenance, API, and source connectors are the product; the directory and map are clients.

Start with the route that matches your task, then follow the links. Each document states its own authoritative sources so humans and agents know what to trust.

## Start here

| If you are… | Read |
|---|---|
| New to the repository | [Getting started](getting-started.md) → [Architecture](architecture.md) |
| Building against the API | [Public API](api.md) → [Data dictionary](data-dictionary.md) |
| Changing the API or contract | [Public API](api.md) → [Data model](data-model.md) → [Testing](testing.md) |
| Working on the web app | [Web app](web.md) → [Design system](design-system.md) |
| Adding or fixing a source | [Adding a source](adding-a-source.md) → [Ingestion](ingestion.md) → [Sources](sources.md) |
| Reviewing rights or privacy | [Data policy](data-policy.md) → [Data dictionary](data-dictionary.md) |
| Consuming data through AI tools | [MCP](mcp.md) → [Public API](api.md) |
| Operating a deployment | [Operations](operations.md) → runbooks in [`operations/`](operations/) |
| Contributing a change | [Contributing](contributing.md) → [Testing](testing.md) |

## Document map

| Document | Covers |
|---|---|
| [Getting started](getting-started.md) | Prerequisites, local setup, database, seed/real ingestion, running API and web app, common tasks, troubleshooting |
| [Architecture](architecture.md) | Services, boundaries, request/data flow, repository map, where to change what |
| [Public API](api.md) | Developer-facing usage: base URL, quickstart, endpoint families, filters, pagination, errors, downloads, contract workflow |
| [Data model](data-model.md) | Canonical tables, provenance, identity, temporal model, constraints, migrations |
| [Data dictionary](data-dictionary.md) | Consumer-facing fields, controlled vocabularies, null semantics, precision, rights states |
| [Ingestion](ingestion.md) | Source registry, acquisition, parsing, validation, matching, fusion, release/publication pipeline |
| [Adding a source](adding-a-source.md) | End-to-end checklist and patterns for a new source adapter |
| [Sources](sources.md) | Research register of candidate and active sources, evidence labels, access reality |
| [Data policy](data-policy.md) | Inclusion, ownership, rights, privacy, publication gate, takedown, review evidence |
| [Web app](web.md) | Routes, data flow, directory, map, profile, security, accessibility, common changes |
| [Design system](design-system.md) | Measured reference values, fonts, colour, geometry, components, change procedure |
| [MCP](mcp.md) | Read-only MCP adapter: transports, curated tools, client setup, caveats, operations |
| [Testing](testing.md) | Test layers, fixtures, commands, contract checks, E2E, CI, verification checklist |
| [Operations](operations.md) | Runtime configuration, migrations, backups, monitoring, incidents, security, launch gaps |
| [Contributing](contributing.md) | Branch/commit/PR workflow, review expectations, documentation duties |

Retained evidence and decisions:

| Path | Contents |
|---|---|
| [`decisions/`](decisions/) | Architecture decision records (ADRs) 0001–0009 |
| [`operations/`](operations/) | Backup/restore, incident, and security-review runbooks plus dated evidence |
| [`design-audit/`](design-audit/) | Live-reference measurements, screenshots, and implementation captures |
| [`../data.md`](../data.md) | Source-discovery, pipeline-adjustment, and full-rebuild brief |
| [`../packages/api-client/openapi.json`](../packages/api-client/openapi.json) | Committed OpenAPI contract |

## What is canonical

When documents disagree, these sources win:

1. **API shape:** `packages/api-client/openapi.json`, generated from the FastAPI app. Contract tests fail if it drifts.
2. **Controlled vocabularies:** `apps/api/philfacilities_api/taxonomy.py` for facility categories, inclusion classes, ownership, access, roles, and functions; `apps/api/philfacilities_api/rights.py` for rights and publication states.
3. **Database shape:** `apps/api/philfacilities_api/models.py` and Alembic migrations under `apps/api/migrations/versions/`.
4. **Ingestion behavior:** the pipeline under `apps/ingest/philfacilities_ingest/pipeline/` and source adapters under `apps/ingest/philfacilities_ingest/sources/`.
5. **Source research state:** [sources](sources.md) plus machine-readable files under `data/sources/`; live state comes from `/v1/sources` and `/v1/monitoring`.
6. **Design values:** `docs/design-audit/reference-measurements.md` for measured values; `apps/web/src/app/globals.css` for implemented tokens.

These documents describe those sources. If code and prose disagree, fix both in the same change.

## Repository map

```text
apps/web/                  Next.js App Router client (directory, map, profiles, data pages)
apps/api/                  FastAPI read API, SQLAlchemy models, Alembic migrations
apps/ingest/               Acquisition, source adapters, validation, matching, fusion, reports
apps/mcp/                  Read-only MCP adapter over the public API (stdio and Streamable HTTP)
packages/api-client/       OpenAPI contract and generated TypeScript client
database/fixtures/         Deterministic synthetic fixtures and checksum manifest
data/sources/              Candidate index, probe ledger, Geoportal layer index
docs/                      This documentation set, ADRs, runbooks, evidence, design audit
infra/                     Local PostgreSQL/PostGIS Compose services
scripts/                   Repository checks, backups, benchmarks, report capture
tests/                     Cross-cutting API contract and integration tests
var/reports/               Generated reports (not source-controlled)
var/raw/                   Preserved raw source releases (not source-controlled)
```

## Architecture at a glance

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

- The web app reads the public API through `packages/api-client`; it never connects to PostgreSQL and never imports ingest internals.
- The MCP server is another read-only client of the public API. It has no database credentials, no second copy of the publication gate, and no reshaped response schemas.
- The API is read-only and applies one publication gate to every public response.
- Ingestion may store restricted records, but they stay internal and are excluded from public endpoints and bulk exports.
- Raw source releases are preserved with checksums and release metadata. Source values, nulls, and identifiers are not overwritten by normalization.

See [Architecture](architecture.md) for boundaries and [Data model](data-model.md) for the schema.

## Data-integrity invariants

These are the product's non-negotiables. Backing policy and code are linked where relevant.

1. Preserve original source values, identifiers, and raw releases. ([Ingestion](ingestion.md))
2. Record agency, dataset, release, source record, reference period, publication date, retrieval time, checksum, and parser/schema version. ([Data model](data-model.md))
3. Keep missing separate from zero, `false`, inactive, or closed. ([Data dictionary](data-dictionary.md))
4. Preserve leading zeros in PSGC and other codes; codes are strings. ([Data dictionary](data-dictionary.md))
5. Keep coordinate precision and method with the point; never imply building-level precision for a centroid or geocoded point.
6. Never auto-merge ambiguous records. Candidates require evidence and review. ([Data model](data-model.md))
7. Never infer operational status from registry presence, licensure, or accreditation. ([Data policy](data-policy.md))
8. Keep rights/accreditation separate from real-time operational availability.
9. Publish only after a recorded rights decision; explicit restrictions and privacy limits control. ([Data policy](data-policy.md))
10. Never fabricate official records. Synthetic data must be labelled synthetic. ([Testing](testing.md))

## Conventions

- Paths are relative to the repository root unless stated otherwise.
- Commands assume `uv`, `pnpm`, and Docker Compose are installed; see [Getting started](getting-started.md). The lowercase `justfile` wraps common commands, but every recipe maps to a plain command.
- `PHILFACILITIES_` is the environment prefix for API, ingest, and MCP settings. Alembic reads `DATABASE_URL` directly.
- Python 3.12–3.14; Node.js 22+ (24 tested); pnpm 12+; PostgreSQL 17 + PostGIS 3.5.
- Every meaningful change includes tests and a documentation update.
- Generated reports belong in `var/reports/` and raw releases in `var/raw/`, not in `docs/`.
- Do not add a second source of truth for API types, vocabularies, rights states, or design tokens.

## Maintaining this documentation

- Update the relevant document in the same change as the code.
- Keep links relative and working: `uv run python scripts/check_markdown_links.py`.
- Move detail into the focused document rather than growing this index.
- Remove stale claims instead of appending caveats; volatile counts belong in `/v1/statistics` and generated reports, not in prose.
- `docs/sources.md` is machine-parsed — preserve its section headings and row format; see [Sources](sources.md).
