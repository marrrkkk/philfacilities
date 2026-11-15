# 0001 — Monorepo with independently deployable services

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

The web client, public API, and ingestion jobs share a data contract and change
together, but they have different runtimes, scaling profiles, and release risks.
The project also needs to stay approachable for open-source contributors.

## Decision

Use one repository with independently deployable applications:

- `apps/web` — Next.js App Router, TypeScript, shadcn/ui, Tailwind, MapLibre.
- `apps/api` — FastAPI, Pydantic, SQLAlchemy, Alembic.
- `apps/ingest` — Python source adapters and scheduled ETL.
- `packages/api-client` — OpenAPI document and generated TypeScript client.
- `infra/compose.yaml` — local PostgreSQL/PostGIS and test database.

pnpm manages the JavaScript workspace; uv manages the Python workspace. The API
contract is the boundary: the web app consumes the generated client rather than
importing API code.

## Consequences

- Contract changes are made once and regenerated for the client.
- Web, API, and ingestion deploy and scale separately; the repository is not a
  monolithic runtime.
- Contributors need both Node and Python toolchains.
- Cross-cutting changes still require coordinated review across workspace
  packages.

## Evidence

`pnpm-workspace.yaml`, `pyproject.toml`, `apps/*`, `packages/api-client`, and
[02 — Architecture](../02-ARCHITECTURE.md).
