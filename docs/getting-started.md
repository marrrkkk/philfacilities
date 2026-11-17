# Getting started

This guide takes a fresh checkout to a working API, web app, and real-data local database.

## 1. Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12–3.14 |
| [uv](https://docs.astral.sh/uv/) | current |
| Node.js | 22+ (24 tested) |
| pnpm | 12+ |
| Docker + Compose | current |
| `just` (optional) | any recent version |

The repository is a uv workspace (`apps/api`, `apps/ingest`) and a pnpm workspace (`apps/web`, `packages/api-client`).

## 2. Install dependencies

```bash
cp .env.example .env
uv sync --all-packages
pnpm install
```

`uv sync --all-packages` installs both Python applications and the root dev tools. `pnpm install` installs the web app and API client.

## 3. Start PostgreSQL/PostGIS

```bash
docker compose -f infra/compose.yaml up -d db
```

The development database listens on `localhost:54329` with user/password/database `philfacilities`. The optional test database uses port `54330`:

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
```

Optional S3-compatible raw storage (MinIO) is available under the `storage` profile:

```bash
docker compose -f infra/compose.yaml --profile storage up -d minio
```

## 4. Apply the schema

```bash
DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
  uv run alembic -c apps/api/alembic.ini upgrade head
```

Alembic reads `DATABASE_URL`. The API and ingest applications read `PHILFACILITIES_DATABASE_URL`; `.env.example` sets both. If you export only one, export the prefixed one for the apps and pass `DATABASE_URL` to Alembic as shown.

## 5. Load real sources

The working database is loaded from rights-cleared real sources. Start with the approved group, excluding the large DepEd EBEIS acquisition:

```bash
uv run philfacilities-ingest source run --group approved --exclude deped-ebeis
uv run philfacilities-ingest status
```

This loads BetterGov PSGC, PSA 2024 Census population, PhilHealth PDFs, OSM health/education/public-service extracts, and the additional published directories. It records source checks, preserves raw artifacts under `var/raw/`, writes reports under `var/reports/`, and applies the publication gate.

Load sources selectively when iterating:

```bash
uv run philfacilities-ingest source run bettergov-psgc
uv run philfacilities-ingest source run bettergov-population
uv run philfacilities-ingest source run philhealth
uv run philfacilities-ingest source run osm-health
uv run philfacilities-ingest source run osm-education
```

DepEd EBEIS is deliberately separate. Its source release is approved for institution-level publication with school-head names withheld, while canonical rows stay `internal` pending field-level mapping and privacy review:

```bash
uv run philfacilities-ingest source run deped-ebeis --region ncr
```

List, inspect, and validate sources:

```bash
uv run philfacilities-ingest source list
uv run philfacilities-ingest source validate philhealth --fixture var/raw/philhealth/<release>/<file>.pdf
uv run philfacilities-ingest source run philhealth --dry-run
```

A dry run acquires and validates but does not write canonical or staging rows.

## 6. Run the API

```bash
PHILFACILITIES_DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
  uv run uvicorn philfacilities_api.main:app --host 127.0.0.1 --port 8010 --reload
```

- API: `http://127.0.0.1:8010`
- OpenAPI: `http://127.0.0.1:8010/openapi.json`
- Interactive docs: `http://127.0.0.1:8010/docs`
- Health: `http://127.0.0.1:8010/healthz`

## 7. Run the web app

In a separate terminal:

```bash
pnpm --filter @philfacilities/web dev
```

Open `http://127.0.0.1:3000`.

The web app reads `API_BASE_URL` on the server and `NEXT_PUBLIC_API_URL` in the browser; both default to `http://127.0.0.1:8010`. `NEXT_PUBLIC_*` values are inlined at build time, so set them before `pnpm build` in a deployed environment.

Basemap variables:

```bash
NEXT_PUBLIC_MAP_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png
NEXT_PUBLIC_MAP_TILE_ATTRIBUTION=© Example Maps
NEXT_PUBLIC_MAP_TILE_MAXZOOM=20
```

The local default is attributed OpenStreetMap raster tiles. Set a licensed production provider before launch; see [ADR 0006](decisions/0006-basemap-provider.md).

## 8. Verify the stack

```bash
uv run philfacilities-ingest status
uv run philfacilities-ingest monitoring
curl -s http://127.0.0.1:8010/v1/statistics | jq
curl -s http://127.0.0.1:8010/v1/sources | jq
scripts/smoke_check.sh
```

`status` prints canonical, synthetic, dataset, and release counts plus recent ingestion runs. `monitoring` prints the latest check per dataset.

## 9. Run the checks

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

With `just`:

```bash
just check
```

Integration tests require the test database (`docker compose ... --profile test up -d test-db`). The suite resets the test schema and refuses to run unless the database name ends in `_test`. See [testing](testing.md).

## 10. Common tasks

| Task | Command |
|---|---|
| Regenerate OpenAPI + TypeScript client | `just typegen` (runs `just openapi-export` first) |
| Generate deterministic fixtures | `uv run philfacilities-ingest generate-fixtures` |
| Load the synthetic demo | `uv run philfacilities-ingest demo load --reset` |
| Remove synthetic records | `uv run philfacilities-ingest purge-synthetic` |
| Back up the database | `scripts/db_backup.sh` |
| Verify a restore | `scripts/db_restore_verify.sh <dump>` |
| Benchmark API endpoints | `uv run python scripts/api_benchmark.py` |
| Generate measured reports | `uv run python scripts/generate_data_reports.py` |
| Capture API examples | `PHILFACILITIES_API_URL=http://127.0.0.1:8010 uv run python scripts/capture_api_examples.py` |
| Capture responsive screenshots | `pnpm --filter @philfacilities/web capture:responsive` |

Generated reports go to `var/reports/`; generated raw files go to `var/raw/`. Both are gitignored.

## 11. Troubleshooting

**`source run` writes nothing / reports `skipped_duplicate`.** The release checksum matches a retained release. That is expected. Use `--reprocess` only when a parser or key-scheme change requires rebuilding derived rows from the preserved artifact.

**API returns empty lists.** Check `uv run philfacilities-ingest status` and `monitoring`. A dataset may be loaded but blocked by rights/publication state. Inspect `/v1/sources` for `redistribution_status` and `publication_status`.

**Integration tests are skipped.** The test database is not reachable. Start it with the `test` profile and confirm port `54330`.

**`psycopg` cannot connect.** The API/ingest apps read `PHILFACILITIES_DATABASE_URL`, not `DATABASE_URL`. Alembic reads `DATABASE_URL`. Set both or pass the variable inline.

**Map tiles fail.** The directory must still work without tiles. Check `NEXT_PUBLIC_MAP_TILE_URL` and the CSP `connect-src`/`img-src` origins derived in `apps/web/src/proxy.ts`.
