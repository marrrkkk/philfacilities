# Contributing to PhilFacilities

The full contributor guide is [`docs/contributing.md`](docs/contributing.md). Start there, along with [`docs/getting-started.md`](docs/getting-started.md) and [`docs/README.md`](docs/README.md).

## Ground rules

- **Do not invent source facts.** Verify the official source or terms before adding an endpoint, field, identifier, cadence, licence, or coverage claim.
- **Publish only after a documented rights decision.** Follow [`docs/data-policy.md`](docs/data-policy.md). Explicit restrictions, FOI/agreement conditions, and personal or sensitive data still control.
- **Preserve source truth.** Keep raw releases, original values, leading zeros, missing values, coordinate precision, and source identifiers. Missing is not zero, `false`, or inactive.
- **No silent merges.** Ambiguous matches go to review. Accepting a candidate is separate from merging it.
- **Keep the API ahead of the UI.** Regenerate the OpenAPI contract and TypeScript client when the API changes.
- **Never commit secrets or personal data.** See [`SECURITY.md`](SECURITY.md).

## Setup and checks

```bash
cp .env.example .env
just setup
just api
just web

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

Integration tests use the test database (`_test` suffix, default port `54330`). See [`docs/testing.md`](docs/testing.md).

Source changes must follow [`docs/adding-a-source.md`](docs/adding-a-source.md). API changes must follow [`docs/api.md`](docs/api.md). Visual changes must follow [`docs/design-system.md`](docs/design-system.md).

## Licensing and security

Application code is Apache-2.0. Source data is not covered by that licence; rights are recorded per dataset. Do not open a public issue for a vulnerability or for anything containing credentials, personal data, or restricted source material. Follow [`SECURITY.md`](SECURITY.md).
