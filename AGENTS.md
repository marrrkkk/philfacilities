# AGENTS.md — PhilFacilities

Short operating brief for agents and automated contributors. The complete documentation for developers and agents is [`docs/README.md`](docs/README.md). Read it before changing anything, then follow only the route that matches your task.

## Mission

Build PhilFacilities as an open, source-linked registry of Philippine facilities. The canonical data, provenance, API, and source connectors are the product; the directory and map are read-only clients of that data.

## Read before you change anything

Open [`docs/README.md`](docs/README.md), then follow the relevant route:

| Task | Read |
|---|---|
| Local setup, running the stack, commands | [Getting started](docs/getting-started.md) |
| API shape, endpoints, public fields | [API](docs/api.md) → [Data dictionary](docs/data-dictionary.md) |
| Schema, constraints, migrations | [Data model](docs/data-model.md) |
| Adding or fixing a source | [Adding a source](docs/adding-a-source.md) → [Ingestion](docs/ingestion.md) → [Sources](docs/sources.md) |
| Rights, privacy, publication | [Data policy](docs/data-policy.md) |
| Web UI, map, profiles | [Web app](docs/web.md) → [Design system](docs/design-system.md) |
| Tests and quality gates | [Testing](docs/testing.md) |
| Deployment, backups, incidents | [Operations](docs/operations.md) → [`docs/operations/`](docs/operations/) |
| MCP adapter | [MCP](docs/mcp.md) |
| Contribution workflow | [Contributing](docs/contributing.md) |

Decisions are in [`docs/decisions/`](docs/decisions/); dated operational evidence is in [`docs/operations/evidence/`](docs/operations/evidence/).

## Non-negotiable rules

Rationale and enforcement live in the linked documents — do not guess.

1. Preserve source values and raw releases; never overwrite source truth. ([Data model](docs/data-model.md), [Ingestion](docs/ingestion.md))
2. Publish only after a recorded rights decision. Explicit restrictions, agreements, and personal data still control. ([Data policy](docs/data-policy.md))
3. Keep missing separate from zero, `false`, inactive, or closed. ([Data dictionary](docs/data-dictionary.md))
4. Preserve leading zeros in PSGC codes; keep coordinate precision and method with every point. ([Data dictionary](docs/data-dictionary.md))
5. Do not auto-merge ambiguous records; name similarity alone is never identity. ([Data model](docs/data-model.md))
6. Registry presence, licensure, or accreditation is not operational status. ([Data policy](docs/data-policy.md))
7. Never fabricate official records; label synthetic data as synthetic. ([Testing](docs/testing.md))
8. OpenAPI is the API contract; `taxonomy.py` and `rights.py` own vocabularies and rights states. Do not create a second source of truth. ([API](docs/api.md))

## Commands

Every command is a plain shell command; `just` recipes only wrap them. Full setup and troubleshooting: [Getting started](docs/getting-started.md). Verification: [Testing](docs/testing.md).

```bash
just setup
just api          # 127.0.0.1:8010
just web          # 127.0.0.1:3000
just mcp          # stdio; requires just api
just mcp-http     # 127.0.0.1:8011
just check
uv run pytest --require-integration
```

Integration tests require a dedicated database whose name ends in `_test` (default port 54330). Generated reports belong in `var/reports/`, not `docs/`.

## Working style

- Work in small vertical slices; add tests and update the relevant doc in the same change.
- Inspect the authoritative source before editing — never guess tokens, vocabularies, or source facts.
- Run the relevant checks before declaring completion. Avoid speculative abstractions.
- If code and prose disagree, fix both in the same change.
