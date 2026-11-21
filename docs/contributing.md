# Contributing

> **Purpose** — The contribution workflow, review expectations, and documentation duties.
> **Start here** — [Getting started](getting-started.md) for setup, then the guide for the area you are touching. [`../AGENTS.md`](../AGENTS.md) is the short operating brief for automated agents.
> **See also** — [Testing](testing.md) · [Data policy](data-policy.md) · [`SECURITY.md`](../SECURITY.md)

PhilFacilities is an open, source-linked registry of Philippine facilities. The canonical data, provenance, API, and source connectors are the product; the directory and map are clients. Contributions are welcome from data engineers, researchers, designers, and anyone who can improve a source adapter, a test, or the public record.

## 1. Ground rules

- **Do not invent source facts.** Never add an endpoint, file, field, identifier, cadence, licence, or coverage claim unless the official source or terms were inspected and recorded.
- **Publish only after a documented rights decision.** Follow [Data policy](data-policy.md). Explicit restrictions, FOI/agreement conditions, and personal or sensitive data still control.
- **Preserve source truth.** Keep raw releases, original values, leading zeros, missing values, coordinate precision, and source identifiers. Missing is not zero, `false`, or inactive.
- **No silent merges.** Ambiguous matches remain `quality.match_candidates` rows with their evidence. Accepting a candidate is separate from merging it.
- **Keep the API ahead of the UI.** The OpenAPI document is the contract; regenerate the TypeScript client when the API changes.
- **Never commit secrets or personal data.** Do not include credentials, signed agreements, learner/patient information, private contacts, or restricted source rows. See [`SECURITY.md`](../SECURITY.md).

## 2. Set up

```bash
cp .env.example .env
just setup          # install dependencies, start PostgreSQL/PostGIS, apply migrations
just api            # 127.0.0.1:8010
just web            # 127.0.0.1:3000  (separate terminal)
```

For a synthetic-only database, `just demo` loads labelled demo data. For real sources with recorded publication decisions:

```bash
uv run philfacilities-ingest source run --group approved --exclude deped-ebeis
uv run philfacilities-ingest status
```

See [Getting started](getting-started.md) for prerequisites, ports, test-database setup, and troubleshooting.

## 3. Workflow

1. **Describe the problem.** For a bug, give observed and expected behavior; for a source, the official URL, access reality, and rights state; for a feature, the user need and smallest complete change.
2. **Inspect before editing.** Read the relevant source of truth: `openapi.json` for API shape, `taxonomy.py`/`rights.py` for vocabularies, models/migrations for schema, the pipeline for ingestion behavior, the design audit for visual values.
3. **Make a small vertical slice.** Change one behavior end to end; avoid speculative abstractions and unnecessary infrastructure.
4. **Add tests.** Cover the changed behavior at the lowest useful layer. Source changes need fixture-based parser tests, schema-drift coverage, and idempotency coverage where applicable.
5. **Update documentation.** Change the relevant guide in `docs/` in the same change. Update [Sources](sources.md) for source-state changes and [Data dictionary](data-dictionary.md) for consumer-visible fields.
6. **Run the checks.** Include commands and results in the pull request.
7. **Open a pull request.** Describe the data/rights impact and known limitations. Link the issue where one exists.

No tracker file is required. The pull request, issue, and code are the record.

## 4. Checks

The full local gate:

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

Or `just check`. Integration tests use the dedicated test database (`_test` suffix, default port 54330):

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
PHILFACILITIES_TEST_DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test uv run pytest
```

With the API and web app running, `scripts/smoke_check.sh` verifies the public surfaces. See [Testing](testing.md) for test layers and fixture rules.

## 5. API and schema changes

- The OpenAPI document is generated from the FastAPI app. After changing a schema or route:

  ```bash
  just openapi-export
  just typegen
  uv run pytest tests/test_api_contract.py -q
  ```

- Commit both `packages/api-client/openapi.json` and `packages/api-client/src/schema.ts`; CI fails if the committed contract differs from `app.openapi()`.
- Alembic migrations live in `apps/api/migrations/versions/`; apply to a fresh database and the test database. Do not edit an already-applied migration in a released branch.
- Record an ADR in [`decisions/`](decisions/) when changing service boundaries, identity, history, rights, coordinate precision, the basemap, or API compatibility.
- Update [Public API](api.md) and [Data dictionary](data-dictionary.md) when a public field, endpoint, filter, or vocabulary changes.
- Do not expose restricted source evidence through a new endpoint. Apply the same gate and add a negative-case test.
- Add new filters to the API first, then directory/map pages, preserving URL state with an E2E assertion.

## 6. Source adapter changes

Every adapter contribution includes: official URL and publisher; acquisition method and restrictions; a safe sample fixture (or why one cannot be redistributed); parser and schema mapping; validation rules and fail-closed drift behavior; expected fields, missingness, and coordinate precision; licence/terms status and publication basis; tests for parsing, duplicates, and repeated runs; and an example report or reproduction command. Use [Adding a source](adding-a-source.md) as the checklist and [Ingestion](ingestion.md) for mechanics. Do not use a third-party cleaned dataset as if it were the official source.

## 7. Web and design changes

- Re-inspect the live reference in a real browser before changing a value that depends on it; record new measurements in [`design-audit/reference-measurements.md`](design-audit/reference-measurements.md).
- Change tokens in `apps/web/src/app/globals.css`, not ad hoc component colours.
- Keep square corners, rules instead of shadows, the global header, and the measured focus ring; keep the directory usable without heavy JavaScript and a text alternative for every map result.
- Do not copy the reference site's layout, content, logo, or campaign graphics. Run responsive capture and E2E checks after a visual or navigation change.

See [Web app](web.md) and [Design system](design-system.md).

## 8. Data corrections

If a published record is wrong, report the facility ID or URL, the field, observed and correct values, and an official evidence link. Do not send personal data, patient/learner information, or restricted source rows through a public issue. A correction is not a hand edit to a database row: add or update source evidence and the parser, re-run the source, and preserve the change event. If the source itself is wrong, record the discrepancy rather than overwriting the source value.

## 9. Review expectations

A pull request is ready for review when the change is scoped and states the problem; tests fail without it and pass with it; relevant checks pass or failures are explained; documentation and [Sources](sources.md) are updated where needed; the gate and personal-data boundary are unchanged or explicitly reviewed; and no secrets, restricted rows, or generated reports are committed.

Changes to migrations, identity merges, data deletion, licensing, or public publication scope require explicit maintainer review and a second reviewer. Do not merge your own change to those areas.

## 10. Licensing and security

Application code is Apache-2.0. That licence does not grant rights to agency source data; redistribution rights and publication basis are recorded per dataset. By contributing code, you agree it may be distributed under the repository's code licence; do not contribute material you cannot license. Report vulnerabilities privately per [`SECURITY.md`](../SECURITY.md), never in a public issue.
