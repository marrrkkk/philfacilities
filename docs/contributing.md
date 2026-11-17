# Contributing

PhilFacilities is an open, source-linked registry of Philippine facilities. The canonical data, provenance, API, and source connectors are the product; the directory and map are clients. Contributions are welcome from data engineers, researchers, designers, and anyone who can improve a source adapter, a test, or the public record.

Read [Getting started](getting-started.md) before your first change, then the document for the area you are touching. [AGENTS.md](../AGENTS.md) is the short operating brief for automated agents.

## 1. Ground rules

- **Do not invent source facts.** Never add an endpoint, file, field, identifier, update cadence, licence, or coverage claim unless the official source or terms were inspected and recorded.
- **Publish only after a documented rights decision.** Follow [Data policy](data-policy.md). A verified, publicly available dataset with no explicit prohibition may be published with reviewed institutional fields and recorded provenance; explicit restrictions, FOI/agreement conditions, and personal or sensitive data still control.
- **Preserve source truth.** Keep raw releases, original values, leading zeros, missing values, coordinate precision, and source identifiers. Missing is not zero, `false`, or inactive.
- **No silent merges.** Ambiguous facility matches remain `quality.match_candidates` rows with their evidence, unmerged and retried automatically. Only the exact normalized name + same PSGC + exact address rule may merge; there is no human approval queue.
- **Keep the API ahead of the UI.** The OpenAPI document is the contract. Regenerate the TypeScript client when the API changes.
- **Never commit secrets or personal data.** Do not include credentials, signed agreements, learner/patient information, private contact details, or restricted source rows. See [SECURITY.md](../SECURITY.md).

## 2. Set up

```bash
cp .env.example .env
just setup          # install dependencies, start PostgreSQL/PostGIS, apply migrations
```

Start the API and web app in separate terminals:

```bash
just api
just web
```

The API is at `http://127.0.0.1:8010`; the web app is at `http://127.0.0.1:3000`.

For a synthetic-only database:

```bash
just demo
```

Every synthetic facility, dataset, and release is labelled. Do not present synthetic records as official data.

For real sources with recorded publication decisions:

```bash
uv run philfacilities-ingest source run --group approved --exclude deped-ebeis
uv run philfacilities-ingest status
```

See [Getting started](getting-started.md) for prerequisites, ports, test-database setup, and troubleshooting.

## 3. Workflow

1. **Describe the problem.** For a bug, include the observed and expected behavior. For a source, include the official URL, access reality, and rights state. For a feature, state the user need and the smallest complete change.
2. **Inspect before editing.** Read the relevant source of truth: `openapi.json` for API shape, `taxonomy.py`/`rights.py` for vocabularies, models and migrations for schema, the pipeline for ingestion behavior, and the design audit for visual values.
3. **Make a small vertical slice.** Change one behavior end to end. Avoid speculative abstractions and unnecessary infrastructure.
4. **Add tests.** Cover the changed behavior at the lowest useful layer. Source changes need fixture-based parser tests, schema-drift coverage, and repeated-run/idempotency coverage where applicable.
5. **Update documentation.** Change the relevant page in `docs/` in the same change. Update [Sources](sources.md) for source-state changes and [Data dictionary](data-dictionary.md) for consumer-visible fields.
6. **Run the checks.** Use the section below. Include commands and results in the pull request.
7. **Open a pull request.** Describe the data/rights impact and known limitations. Link the issue where one exists.

No tracker file is required. The pull request, issue, and code are the record.

## 4. Checks

Run the checks relevant to your change. The full local gate is:

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

Or:

```bash
just check
```

Integration tests use the dedicated test database:

```bash
docker compose -f infra/compose.yaml --profile test up -d test-db
PHILFACILITIES_TEST_DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test uv run pytest
```

The database name must end in `_test`. The default test port is `54330`.

With the API and web app running, `scripts/smoke_check.sh` verifies the public surfaces. See [Testing](testing.md) for the test layers and fixture rules.

## 5. API and schema changes

- The OpenAPI document is generated from the FastAPI app. After changing a schema or route:

  ```bash
  just openapi-export
  just typegen
  uv run pytest tests/test_api_contract.py -q
  ```

- Commit both `packages/api-client/openapi.json` and `packages/api-client/src/schema.ts`. CI fails if the committed contract differs from `app.openapi()`.
- Alembic migrations live in `apps/api/migrations/versions/`. Apply a new migration to a fresh database and the test database. Do not edit an already-applied migration in a released branch.
- Record an ADR in [`decisions/`](decisions/) when changing service boundaries, identity, history, rights, coordinate precision, the basemap, or API compatibility.
- Update [API](api.md) and [Data dictionary](data-dictionary.md) when a public field, endpoint, filter, or vocabulary changes.
- Do not expose restricted source evidence through a new endpoint. Apply the same publication gate and add a test for the negative case.
- New filters must be added to the API first, then the directory/map pages, with the URL state preserved and an E2E assertion for visible behavior.

## 6. Source adapter changes

Every source-adapter contribution must include:

- the official source URL and publisher;
- the acquisition method and any access restrictions or terms flow;
- a safe sample fixture, or a documented reason one cannot be redistributed;
- parser implementation and schema mapping;
- validation rules, required columns, and fail-closed schema-drift behavior;
- expected source fields, missingness semantics, and coordinate precision;
- licence/terms status and the publication basis recorded in the source definition;
- tests for parsing, duplicates, and repeated runs;
- an example ingestion report or reproduction command.

Use [Adding a source](adding-a-source.md) as the checklist and [Ingestion](ingestion.md) for pipeline mechanics. Do not use a third-party cleaned dataset as if it were the official source. Do not mark a source acquired or schema-verified without the actual file/response and evidence.

## 7. Web and design changes

- Re-inspect the live reference in a real browser before changing a value that depends on it. Record new measurements in [`design-audit/reference-measurements.md`](design-audit/reference-measurements.md).
- Change tokens in `apps/web/src/app/globals.css`, not ad hoc component colours.
- Keep square corners, rules instead of shadows, the global header, and the measured focus ring.
- Keep the directory usable without JavaScript-heavy interactions and keep a text/list alternative for every map result.
- Do not copy the reference site's layout, content, logo, or campaign graphics.
- Run the responsive capture and E2E checks after a visual or navigation change.

See [Web app](web.md) and [Design system](design-system.md).

## 8. Data corrections

If a published record is wrong, report the facility ID or URL, the field, the observed value, the correct value, and an official source or evidence link. Do not send personal data, patient/learner information, or restricted source rows through a public issue.

A correction is not applied by editing a database row by hand. Add or update the source evidence and parser, re-run the source, and preserve the change event. If the source itself is wrong, record the discrepancy rather than overwriting the source value.

## 9. Review expectations

A pull request is ready for review when:

- the change is scoped and the description states the user or data problem;
- tests fail without the change and pass with it;
- the relevant checks pass, or failures are explained;
- documentation and [Sources](sources.md) are updated where needed;
- the publication gate and personal-data boundary are unchanged or explicitly reviewed;
- no secrets, restricted rows, or generated reports are committed.

Changes to migrations, identity merges, data deletion, licensing, or public publication scope require explicit maintainer review. Do not merge your own change to those areas without a second review.

## 10. Licensing

Application code is Apache-2.0. That licence does not grant rights to agency source data; redistribution rights and the publication basis are recorded per dataset. A verified, publicly available dataset with no explicit prohibition may be published under [Data policy](data-policy.md). By contributing code, you agree that your contribution may be distributed under the repository's code licence. Do not contribute material you cannot license.

## 11. Security

Do not open a public issue for a vulnerability or for anything containing credentials, personal data, or restricted source material. Follow [SECURITY.md](../SECURITY.md).
