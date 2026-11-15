## Summary

<!-- What changed, and why? Keep this focused on one vertical slice. -->

## Tracker / issue

<!-- Reference tracker IDs, e.g. M5-03, and any issue links. -->

## Changes

<!-- Bullet the implementation, docs, migrations, and fixture changes. -->

## Data and rights impact

<!--
State whether this adds/changes a source, field, publication scope, export, identity merge,
or personal-data surface. Say "No new source data" when true. Official data remains blocked
until DATA-LICENSES.md records an approved scope.
-->

## Verification

<!-- Paste the commands run and their outcomes. -->

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
pnpm lint
pnpm typecheck
pnpm build
```

<!-- Add pnpm --filter @philfacilities/web test:e2e, smoke, backup/restore, or source-specific checks when relevant. -->

## Checklist

- [ ] The change is scoped and matches the tracker's acceptance criteria.
- [ ] Tests cover the changed behavior, including schema-drift/idempotency where relevant.
- [ ] Documentation and tracker evidence are updated.
- [ ] No secrets, personal data, restricted raw files, or signed agreements are included.
- [ ] Synthetic fixtures remain labelled and no official data is presented as published without a rights decision.
- [ ] The OpenAPI contract/client is regenerated if the API changed.
- [ ] The map still has a keyboard-accessible text result list, if the map changed.
- [ ] Known blockers and limitations are stated below.

## Known limitations / follow-up

<!-- If nothing is outstanding, say so. Do not hide blocked source/rights or operational work. -->
