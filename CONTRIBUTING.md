# Contributing to PhilFacilities

PhilFacilities is an open, source-linked registry of Philippine schools and health facilities. The
canonical data, provenance, API, and source connectors are the product; the directory and map are
clients. Contributions are welcome from data engineers, researchers, designers, and anyone who can
improve a source adapter or the public record.

Read [`AGENTS.md`](AGENTS.md), [`docs/13-AGENT-WORKFLOW.md`](docs/13-AGENT-WORKFLOW.md), and the
[tracker](planning/TRACKER.md) before starting. The tracker is the single execution checklist; do
not create a competing task list.

## Ground rules

- **Do not invent source facts.** Never add an endpoint, file, field, identifier, update cadence,
  or license unless the official source or terms have been inspected and recorded.
- **Do not publish official data without a rights decision.** Synthetic demonstration fixtures are
  safe to use and must stay visibly labelled. Real DepEd, DOH, PhilHealth, and PSA rows remain
  blocked until `DATA-LICENSES.md` records an approved publication scope.
- **Preserve source truth.** Keep raw releases, original values, leading zeros, missing values,
  coordinate precision, and source identifiers. Missing is not zero, false, or inactive.
- **No silent merges.** Ambiguous facility matches go to `quality.match_candidates` for human
  review. Accepting a candidate is separate from merging it.
- **Keep the API ahead of the UI.** The OpenAPI document is the contract; regenerate the TypeScript
  client when the API changes.
- **Never commit secrets or personal data.** Do not include credentials, signed agreements,
  learner/patient information, or private contact details. See [`SECURITY.md`](SECURITY.md).

## Local setup

Prerequisites: Docker with Compose, Node.js 22+ (24 tested), pnpm 12+, Python 3.12–3.14, and
[uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
just setup          # install dependencies, start PostgreSQL/PostGIS, apply migrations
just demo           # generate and load the synthetic demonstration dataset
```

Or run the underlying commands from the [README](README.md#local-development) without `just`.
Start the API and web app in separate terminals:

```bash
just api
just web
```

The API is at `http://127.0.0.1:8010`; the web app is at `http://127.0.0.1:3000`. The demo database
contains synthetic records only, and every synthetic facility, dataset, and release is labelled.

## Checks

Run the checks relevant to your change before opening a pull request. The full local gate is:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest

pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e
```

Integration tests use the dedicated test database:

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
```

The default test URL is
`postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test`; override
it with `PHILFACILITIES_TEST_DATABASE_URL`. The database name must end in `_test`.

With the API and web app running, `scripts/smoke_check.sh` verifies the public surfaces. The backup
and restore procedure is documented in
[`docs/operations/backup-restore-runbook.md`](docs/operations/backup-restore-runbook.md).

## Repository layout

- `apps/web` — Next.js App Router, TypeScript, shadcn/ui, Tailwind, MapLibre.
- `apps/api` — FastAPI, Pydantic, SQLAlchemy 2, Alembic migrations.
- `apps/ingest` — Python source adapters, fixtures, matching, and the ingestion CLI.
- `packages/api-client` — generated TypeScript client from `openapi.json`.
- `database/fixtures` — deterministic synthetic fixtures and their checksum manifest.
- `docs`, `planning`, `infra`, `scripts`, `tests` — plans, tracker, local infrastructure, operations,
  and cross-cutting tests.

The web app must not connect directly to PostgreSQL, and source files must not be parsed inside API
request handlers.

## Contribution workflow

1. Find or add the task in [`planning/TRACKER.md`](planning/TRACKER.md) and state its acceptance
   criteria.
2. Inspect the current implementation and record source/rights assumptions before editing.
3. Make the smallest complete vertical change. Avoid speculative abstractions and new
   infrastructure without a measured need.
4. Add or update tests for the changed behavior. Source changes need fixture-based parser tests,
   schema-drift coverage, and idempotency coverage where applicable.
5. Update the affected documentation and the tracker evidence row.
6. Run the checks above and include the commands and results in the pull request.

Pull requests must reference tracker IDs, describe data/rights impact, and list known limitations.
Changes to migrations, identity merges, data deletion, licensing, or public publication scope
require explicit review.

## Adding or changing a source adapter

Every source-adapter contribution must include:

- the official source URL and publisher;
- the acquisition method and any access restrictions or terms flow;
- a safe sample fixture, or a documented reason one cannot be redistributed;
- parser implementation and schema mapping;
- validation rules, required columns, and fail-closed schema-drift behavior;
- expected source fields, missingness semantics, and coordinate precision;
- license/terms status in [`DATA-LICENSES.md`](DATA-LICENSES.md);
- tests for parsing, duplicates, and repeated runs;
- an example ingestion report.

Do not use a third-party cleaned dataset as if it were the official source. Do not mark a source
`ACQUIRED` or `SCHEMA_VERIFIED` without the actual file/response and evidence in the repository.

## Schema and API changes

- Alembic migrations live in `apps/api/migrations/`. Every migration must be applied to a fresh
  database and the test database.
- Record architectural decisions in [`docs/decisions/`](docs/decisions/README.md) when changing
  service boundaries, identity, history, rights, coordinate precision, the basemap, or API
  compatibility.
- Update the public data dictionary and API page when a public field or endpoint changes.
- Regenerate the contract and client after API changes:

  ```bash
  just typegen
  ```

  Commit both `packages/api-client/openapi.json` and `packages/api-client/src/schema.ts`. CI checks
  that the committed contract matches `app.openapi()`.

## Design and accessibility

The visual system is measured from the BetterGov Fellowship reference and recorded in
[`docs/design-audit/reference-measurements.md`](docs/design-audit/reference-measurements.md). Do not
copy the reference site's layout, content, logo, or campaign graphics. Use the existing shadcn/
Tailwind tokens and keep the directory and map accessible by keyboard and screen reader. A map
result must always have a text/list alternative.

## Licensing

Application code is Apache-2.0. That license does not grant rights to agency source data;
redistribution rights are recorded per dataset in [`DATA-LICENSES.md`](DATA-LICENSES.md). By
contributing code, you agree that your contribution may be distributed under the repository's code
license. Do not contribute material you cannot license.

## Reporting security issues

Do not open a public issue for a vulnerability or for anything containing credentials, personal
data, or restricted source material. Follow [`SECURITY.md`](SECURITY.md).
