# AGENTS.md — PhilFacilities

## Mission

Build PhilFacilities as an open, source-linked Philippine facilities data platform. The canonical data, provenance, API, and source connectors are the core product; the directory and map are user-facing clients.

## Read before coding

Start with `README.md`, then `docs/13-AGENT-WORKFLOW.md`, `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`, the relevant design/architecture/data documents, and `planning/TRACKER.md`.

## Architecture

- Monorepo: `apps/web`, `apps/api`, `apps/ingest`, `packages/api-client`.
- Web: Next.js App Router, TypeScript, shadcn/ui, Tailwind CSS, MapLibre.
- API: FastAPI, Pydantic, SQLAlchemy 2, Alembic.
- ETL: Python, uv, Polars/DuckDB/PyArrow and source-specific parsers.
- Database: PostgreSQL + PostGIS.
- Raw source files: private S3-compatible object storage by default.
- OpenAPI is the contract; generate the TypeScript client from it.

## Design system — mandatory

The target visual reference is https://fellowship.bettergov.ph/.

Before production web implementation, reverse-engineer the live reference in a real browser: computed fonts and actual font files, color values, font scale/line heights, spacing, nav geometry, buttons, borders/radii/shadows, hover/focus states, and desktop/mobile menu behavior. Record measurements and evidence in `docs/design-audit/reference-measurements.md`. Convert the system into shadcn CSS variables and Tailwind tokens.

Reproduce the reference navigation's visual treatment and responsive behavior, but adapt navigation labels to PhilFacilities. **Do not copy the Fellowship site's layout, content, logo, campaign graphics, or fellowship information architecture.** Design a task-oriented searchable directory, map view, and facility profile experience.

Never guess tokens if browser inspection is unavailable; request screenshots or leave a clearly marked temporary neutral theme.

## Data integrity rules

- Preserve original source values and raw source releases.
- Record source URL, agency, dataset/release, source ID, reference period, publication date, retrieval time, checksum, and parser/schema version.
- Keep missing separate from zero/false/inactive.
- Preserve leading zeros in PSGC codes.
- Keep coordinate precision and method; do not imply building-level precision for centroid/geocoded points.
- Do not auto-merge ambiguous source records.
- Do not infer operational status from registry presence.
- Keep license/accreditation separate from real-time operational availability.
- Publish only after a documented rights decision under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`. A verified, publicly available dataset with no explicit prohibition may be published with reviewed institutional fields, provenance, attribution, and takedown-on-notice. Explicit restrictions, FOI/agreement conditions, and personal or sensitive data still control.
- Never fabricate official records; synthetic data must be marked synthetic.

## Execution discipline

- Work in small vertical slices.
- Reference tracker IDs in commits/PRs where practical.
- Update `planning/TRACKER.md` when status changes and include evidence.
- Add tests and update docs with each meaningful change.
- Run relevant checks before declaring completion.
- Avoid speculative abstractions and unnecessary infrastructure.
