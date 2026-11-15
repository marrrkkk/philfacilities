# 13 — Coding Agent Workflow and Constraints

## 1. Required reading

Before implementing or changing architecture, read:

- `README.md`
- `AGENTS.md`
- `docs/01-PROJECT-CHARTER.md`
- `docs/02-ARCHITECTURE.md`
- `docs/03-SOURCE-REGISTER.md`
- `docs/04-DATA-MODEL.md`
- `docs/05-INGESTION-ETL.md`
- `docs/06-PUBLIC-API.md`
- `docs/07-WEB-PRODUCT-UX.md`
- `docs/08-REFERENCE-DESIGN-SYSTEM.md`
- `planning/TRACKER.md`

Read only the detailed documents relevant to the task after that initial baseline.

## 2. Working method

For each task:

1. Locate its tracker ID.
2. Inspect the current repository and existing implementation before editing.
3. State assumptions and identify source/rights dependencies.
4. Make the smallest complete vertical change.
5. Add tests and update relevant docs.
6. Run relevant tests/lint/type checks.
7. Update tracker status and evidence.
8. Summarize what changed, tests run, known gaps, and next dependency.

Do not perform a large rewrite or scaffold every future feature in one change.

## 3. Source/data rules

- Never invent a source endpoint, source field, file, record, identifier, update cadence, or license.
- Do not mark a source as acquired unless the raw file/response and checksum exist in the active environment.
- Do not mark schema verified without inspecting the actual source file/response.
- Never convert missing to zero or missing status to inactive.
- Never auto-merge ambiguous facilities.
- Never expose restricted DOH/DepEd data or signed agreements.
- Synthetic fixtures must be visibly labeled and must not look like real government records.
- Do not use third-party derived files as if they were official source files.

## 4. Design system rules

Before implementing production screens, complete `docs/08-REFERENCE-DESIGN-SYSTEM.md`'s browser inspection and token audit.

- Use shadcn/ui and Tailwind CSS.
- Extract actual fonts, colors, type scale, sizes, spacing, border/radius/shadow, header geometry, navigation states, and responsive behavior from https://fellowship.bettergov.ph/.
- Record measured values and screenshots in `docs/design-audit/`.
- Translate measurements into shadcn CSS variables and Tailwind tokens.
- Recreate the header/navigation visual treatment; adapt labels and actions for PhilFacilities.
- Do not copy the Fellowship page layout or its branded assets/content.
- Do not guess design tokens when the reference cannot be inspected. Ask for reference screenshots or use a clearly marked temporary neutral theme.
- Build a directory/map application layout, not a long editorial fellowship landing page.

## 5. Architecture rules

- Preserve monorepo boundaries: `apps/web`, `apps/api`, `apps/ingest`.
- Do not make Next.js connect directly to PostgreSQL.
- Do not parse government files inside API request handlers.
- Use OpenAPI as the web/API contract and regenerate the TypeScript client.
- Use PostgreSQL/PostGIS for canonical facility and spatial data.
- Keep raw source storage separate from normalized canonical tables.
- Avoid new infrastructure unless supported by measured need.

## 6. Definition of done

A task is complete only when:

- acceptance criteria pass;
- tests exist and pass;
- docs are updated;
- source/rights assumptions are recorded;
- no fake production data is introduced;
- tracker records evidence and remaining limitations.
