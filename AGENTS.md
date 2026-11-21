# AGENTS.md — PhilFacilities

## Mission

Build PhilFacilities as an open, source-linked Philippine facilities data platform. The canonical data, provenance, API, and source connectors are the core product; the directory and map are user-facing clients.

## Read before coding

Start with `README.md`, then `docs/README.md`. Read only the route that matches the task:

| Task | Documents |
|---|---|
| Local setup | `docs/getting-started.md` |
| API / contract | `docs/api.md`, `docs/data-model.md`, `docs/testing.md` |
| MCP server | `docs/mcp.md`, `docs/api.md`, `docs/decisions/0009-mcp-server-boundary.md` |
| Web / UI | `docs/web.md`, `docs/design-system.md` |
| Ingestion / source | `docs/ingestion.md`, `docs/adding-a-source.md`, `docs/sources.md` |
| Rights / privacy | `docs/data-policy.md`, `docs/data-dictionary.md` |
| Operations | `docs/operations.md`, `docs/operations/` |

## Architecture

- Monorepo: `apps/web`, `apps/api`, `apps/ingest`, `apps/mcp`, `packages/api-client`.
- Web: Next.js App Router, TypeScript, shadcn/ui, Tailwind CSS, MapLibre.
- API: FastAPI, Pydantic, SQLAlchemy 2, Alembic.
- ETL: Python, uv, Polars/DuckDB/PyArrow and source-specific parsers.
- Database: PostgreSQL + PostGIS.
- Raw source files: private S3-compatible object storage by default.
- OpenAPI is the contract; generate the TypeScript client from it.
- MCP is a read-only adapter over the public `/v1` API: no DB credentials, no imported API internals, no duplicate vocabularies or rights states.
- `apps/api/philfacilities_api/taxonomy.py` owns controlled vocabularies; `rights.py` owns rights/publication states.

## Commands

```bash
just setup                 # install, start DB, migrate
just api                   # FastAPI on 127.0.0.1:8010
just web                   # Next.js on 127.0.0.1:3000
just mcp                   # MCP stdio server (needs the API running)
just mcp-http              # MCP Streamable HTTP on 127.0.0.1:8011
just mcp-test              # MCP tool, contract and transport tests
just demo                  # synthetic demo data
uv run philfacilities-ingest source run --group approved

uv run ruff check .
uv run ruff format --check .
uv run pytest
pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e
uv run python scripts/check_markdown_links.py
```

Use the dedicated test database (`_test` suffix, default port `54330`) for integration tests.

## Design system — mandatory

The visual reference is https://fellowship.bettergov.ph/. Re-inspect it in a real browser before changing values that depend on it, and record measurements in `docs/design-audit/reference-measurements.md`. Apply the measured system through shadcn CSS variables and Tailwind tokens in `apps/web`.

Reproduce the reference navigation's visual treatment and responsive behavior, but adapt labels to PhilFacilities. **Do not copy the Fellowship site's layout, content, logo, campaign graphics, or fellowship information architecture.** Design a task-oriented searchable directory, map view, and facility profile experience. Never guess tokens; request screenshots or leave a clearly marked temporary neutral theme.

## Data integrity rules

- Preserve original source values and raw source releases.
- Record source URL, agency, dataset/release, source ID, reference period, publication date, retrieval time, checksum, and parser/schema version.
- Keep missing separate from zero/false/inactive.
- Preserve leading zeros in PSGC codes.
- Keep coordinate precision and method; do not imply building-level precision for centroid/geocoded points.
- Do not auto-merge ambiguous source records.
- Do not infer operational status from registry presence.
- Keep licence/accreditation separate from real-time operational availability.
- Publish only after a documented rights decision under `docs/data-policy.md`. A verified, publicly available dataset with no explicit prohibition may be published with reviewed institutional fields, provenance, attribution, and takedown-on-notice. Explicit restrictions, FOI/agreement conditions, and personal or sensitive data still control.
- Never fabricate official records; synthetic data must be marked synthetic.

## Execution discipline

- Work in small vertical slices.
- Add tests and update docs with each meaningful change.
- Run relevant checks before declaring completion.
- Avoid speculative abstractions and unnecessary infrastructure.
- Generated reports go to `var/reports/`, not `docs/`.
- Do not add a second source of truth for API types, vocabularies, rights states, or design tokens.
