# Web app

**Implementation:** `apps/web/`
**Stack:** Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui primitives, MapLibre GL JS
**Data source:** the public API only, through `packages/api-client`

The web app is a client of the canonical API. It never connects to PostgreSQL and never imports ingest internals.

## 1. Routes

| Route | Purpose |
|---|---|
| `/` | Landing page with search, measured coverage, entry points, and provenance explanation |
| `/directory` | Searchable, filterable facility list with cursor pagination and a map link |
| `/map` | Map-first discovery with filters, result list fallback, and precision-aware markers |
| `/facilities/[id]` | Canonical profile: classification, location, typed school/health details, source evidence, assertions, history, quality warnings |
| `/data` | Dataset catalogue with release, rights, publication, and quality state |
| `/data/[dataset]` | Dataset metadata and release history |
| `/data/dictionary` | Field definitions, null semantics, precision, provenance, match statuses |
| `/sources` | Agency/source register and freshness state |
| `/api` | API overview and endpoint guidance |
| `/about` | Mission, governance, contribution, and correction routes |
| `/status` | Service and ingestion status measured from the API |
| `/error`, `/not-found`, `/loading` | Shared error, 404, and loading states |

Route files live in `apps/web/src/app/`; reusable components in `apps/web/src/components/`.

## 2. Rendering and data flow

- Server components fetch from the API in `apps/web/src/lib/api.ts`.
- `API_BASE_URL` is used server-side. `NEXT_PUBLIC_API_URL` is used by browser components and inlined at build time.
- Live data pages use `export const dynamic = "force-dynamic"` so counts, status, and provenance are not frozen at build time.
- Reference and detail data may use short `revalidate` windows (30–300 seconds). Do not cache facility or status data indefinitely.
- A 404 from a detail endpoint maps to `notFound()`. Other API failures surface an error state; they do not render invented fallback data.
- The browser map calls `/v1/facilities/within` directly with `NEXT_PUBLIC_API_URL`; server components use the internal API origin.
- All API types come from `@philfacilities/api-client/schema`. Do not redeclare response shapes by hand.

```text
browser → Next.js server component → lib/api.ts → FastAPI /v1
browser → MapLibre → /v1/facilities/within → FastAPI /v1
```

## 3. Directory

`apps/web/src/app/directory/page.tsx` reads every filter from the URL, so search results are linkable and reloadable. It sends the same filter vocabulary as the API: query, type, subtype, inclusion class, ownership, ownership type, operator type, access class, facility kind, function, PSGC levels, source, coordinate presence, precision, reference period, and update time.

- The results count and active filters are visible above the list.
- Pagination uses the API cursor, not an offset.
- A missing coordinate record still appears in text search; it is labelled rather than hidden.
- Filter controls are plain form elements with labels; the mobile filter panel must remain keyboard-operable.
- Search is also available from the header and landing page through `SearchForm`, which submits a GET request to `/directory`.

When adding a filter:

1. add it to the API query builder first and cover it in an API test;
2. add the parameter to the directory and map pages;
3. preserve it in the map/list links;
4. add it to the Playwright test set if it changes visible results.

## 4. Map

`apps/web/src/components/map/map-explorer.tsx` is a client component. The map page passes initial filter values from the URL.

- The basemap is configured in `apps/web/src/lib/map-style.ts`.
- MapLibre's worker is copied to `public/vendor/maplibre-gl` by `scripts/copy-maplibre-worker.mjs`; `configureMapLibreWorker()` must run before creating a map.
- Bounds queries are debounced and capped (`MAX_MAP_FEATURES`); the response reports truncation.
- Markers must reflect recorded precision. Do not render a `barangay_centroid` or `unknown` point as a building-level pin.
- The result list is a full text alternative, not a fallback afterthought. Keyboard and screen-reader users must be able to reach every map result.
- The directory must remain usable if tiles fail. Map failure is not a page failure.
- Attribution from the tile provider must remain visible.

Basemap environment variables:

```bash
NEXT_PUBLIC_MAP_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png
NEXT_PUBLIC_MAP_TILE_ATTRIBUTION=© Example Maps
NEXT_PUBLIC_MAP_TILE_MAXZOOM=20
```

The local default is attributed OpenStreetMap raster tiles. Set a licensed production provider before launch; see [ADR 0006](decisions/0006-basemap-provider.md).

## 5. Facility profile

The profile joins four API calls: facility detail, typed school/health detail, change history, and attribute assertions. Each optional call degrades independently; a missing history or assertion list does not hide the facility.

The page presents, in order:

1. identity and classification badges;
2. address and administrative geography;
3. synthetic/quality warnings;
4. registry classification (inclusion, ownership, operator, access, functions, status);
5. roles and services when present;
6. location and precision, with a map only when coordinates and a known precision exist;
7. typed school or health information;
8. licences and accreditations with validity;
9. source records and provenance;
10. field-level assertions and canonical history;
11. correction/reporting route.

Rules:

- Never imply operational status from registry presence, licensure, or accreditation.
- Never infer government ownership from a government publisher or regulator.
- Show coordinate precision and method next to the map.
- Keep `updated_at` (PhilFacilities change time) distinct from source publication and reference dates.
- Do not expose reviewer names, reviewer notes, personal contact fields, or restricted source evidence.

## 6. Data and source pages

`/data` lists every dataset with agency, latest release, reference period, parsed rows, redistribution status, publication status, and synthetic labelling. `/data/[dataset]` shows metadata, rights basis, attribution, personal-data status, release history, SHA-256, and gaps.

These pages must describe the actual dataset state. If no release exists, say so. If rights are unresolved, say so. Do not render a download link for a dataset that has not passed the publication gate.

## 7. Styling and components

- Global tokens and base styles: `apps/web/src/app/globals.css`.
- UI primitives: `apps/web/src/components/ui/`.
- Use `container-page`, `eyebrow`, `rule-label`, and the existing token utilities rather than new hardcoded palettes.
- Keep square corners. The design system sets `--radius-*` to `0`.
- Use borders and rules rather than drop shadows.
- The global header is `SiteHeader`; do not replace it with a dashboard sidebar.
- New interactive primitives should keep accessible behavior (focus, labels, Escape handling, focus return) even when restyled.

See [design system](design-system.md) for measured values and the change procedure.

## 8. Security and rendering constraints

- CSP is generated per request in `apps/web/src/proxy.ts` with a fresh nonce. The root layout awaits `connection()` so Next.js can attach the nonce to framework and page scripts.
- Do not add a second CSP header in `next.config.ts`; multiple policies combine and can block nonce-bearing scripts.
- The policy allows only the configured API, tile, and development HMR origins. Re-check it after changing either provider.
- Security headers (`nosniff`, `DENY` framing, referrer policy, permissions policy) are set in `next.config.ts`.
- The app does not accept user-generated content or write to the API. There are no authentication or mutation flows.

## 9. Accessibility and responsiveness

Target WCAG 2.2 AA.

- Skip link, landmark structure, meaningful headings, and page titles.
- Visible `3px` focus ring with `3px` offset.
- Mobile navigation: Menu/Close button with `aria-expanded`, `aria-controls`, Escape to close, and focus return.
- Map filters and result selection must be keyboard-operable.
- Do not use color alone for precision, quality, or status.
- Respect `prefers-reduced-motion`.
- Check layouts at 390, 768, 1024, 1440, and 1920 px.

The E2E suite asserts the hydration marker (`<html data-hydrated="true">`) before typing into controlled inputs. Keep the marker: it prevents flaky tests caused by typing before hydration.

## 10. Tests

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e
pnpm --filter @philfacilities/web capture:responsive
pnpm --filter @philfacilities/web check:responsive
```

`apps/web/e2e/app.spec.ts` covers search, filters, profiles, map/list behaviour, mobile navigation, accessibility (axe), CSP nonce presence, keyboard focus, responsive capture, and precision labels. E2E defaults target the real local database; CI overrides the fixture names and IDs for its synthetic demo environment.

## 11. Environment

| Variable | Consumer | Notes |
|---|---|---|
| `API_BASE_URL` | Server components | Internal API origin |
| `NEXT_PUBLIC_API_URL` | Browser/map, CSP | Inlined at build time; set before building |
| `NEXT_PUBLIC_SITE_URL` | Metadata/links | Canonical public origin |
| `NEXT_PUBLIC_MAP_TILE_URL` | Map, CSP | Tile template |
| `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION` | Map | Required with a custom tile provider |
| `NEXT_PUBLIC_MAP_TILE_MAXZOOM` | Map | Optional max zoom |

## 12. Common changes

| Change | Start here |
|---|---|
| Add a filter | API query, directory page, map page, E2E |
| Add a facility field | API schema → OpenAPI/client → profile or card → dictionary |
| Change map behavior | `components/map/`, `lib/map-style.ts`, CSP origins |
| Change navigation | `components/site-header.tsx` + responsive tests |
| Change visual tokens | `app/globals.css`, then [design system](design-system.md) verification |
| Add a page | `app/<route>/page.tsx`, breadcrumbs, metadata, nav if top-level |
| Fix an API error state | `lib/api.ts`, the route's `try/catch`, shared `Alert` |
