# Web app

> **Implementation** — `apps/web/`
> **Stack** — Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui primitives, MapLibre GL JS
> **Data source** — the public API only, through `packages/api-client`
> **See also** — [Public API](api.md) · [Design system](design-system.md) · [Data dictionary](data-dictionary.md)

The web app is a client of the canonical API. It never connects to PostgreSQL and never imports ingest internals.

## 1. Routes

| Route | Purpose |
|---|---|
| `/` | Landing page with search, measured coverage, entry points, and provenance explanation |
| `/directory` | Searchable, filterable facility list with cursor pagination and a map link |
| `/map` | Map-first discovery with filters, result-list fallback, and precision-aware markers |
| `/facilities/[id]` | Canonical profile: classification, location, typed details, source evidence, assertions, history, warnings |
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
- `API_BASE_URL` is used server-side; `NEXT_PUBLIC_API_URL` is used by browser components and inlined at build time.
- Live facility data uses `cache: "no-store"`. Reference data (administrative units, source register) may use short `revalidate` windows (30–300 seconds). Never cache facility data indefinitely.
- Live data pages use `export const dynamic = "force-dynamic"` so counts, status, and provenance are not frozen at build time.
- A 404 from a detail endpoint maps to `notFound()`. Other failures surface an error state; they do not render invented fallback data.
- The browser map calls `/v1/facilities/map` directly; server components use the internal API origin.
- All API types come from `@philfacilities/api-client/schema`. Do not redeclare response shapes by hand.
- Category, subtype, inclusion, ownership, operator, kind, access, and contact labels come from `GET /v1/taxonomy`, mapped in `apps/web/src/lib/taxonomy.ts`. Do not add a second hardcoded vocabulary.

```text
browser → Next.js server component → lib/api.ts → FastAPI /v1
browser → MapLibre → /v1/facilities/map → FastAPI /v1
```

## 3. Directory

`apps/web/src/app/directory/page.tsx` reads every filter from the URL, so results are linkable and reloadable. It sends the same filter vocabulary as the API: query, type, subtype, inclusion class, ownership, ownership type, operator type, access class, facility kind, function, PSGC levels, source, coordinate presence, precision, reference period, and update time.

- Results count and active filters are visible above the list; pagination uses the API cursor, not an offset.
- A record without coordinates still appears in text search, labelled rather than hidden.
- Each result shows compact registry identifiers from `source_refs` (e.g. `CHED 04131`, `DepEd 427036`, `OSM way/156623883`) so same-named facilities stay distinguishable.
- Search is debounced (~350 ms): typing aborts stale requests and replaces only the count, cards, pagination, filter chip, and map link. The URL stays shareable via `history.replaceState`. Other filter controls still submit a GET request.
- Geography options load hierarchically (region → province → municipality → barangay); a bookmarked child code resolves directly. Barangays are loaded only for the selected city/municipality.
- Subtype options are grouped under taxonomy category; selecting a category must not silently keep an incompatible subtype.

When adding a filter: add it to the API query builder first with an API test; then the directory and map pages; preserve it in map/list links; add a Playwright assertion if it changes visible results.

## 4. Map

`apps/web/src/components/map/map-explorer.tsx` is a client component; the map page passes initial URL filter values.

- Basemap config lives in `apps/web/src/lib/map-style.ts`. MapLibre's worker is copied by `scripts/copy-maplibre-worker.mjs`; `configureMapLibreWorker()` must run before creating a map.
- Viewport queries to `/v1/facilities/map` are debounced and abort stale requests. Points are returned up to 500; above that the server returns count clusters, so wide views always draw markers. Selecting a cluster zooms in; selecting a marker opens the facility card.
- Bounds queries to `/v1/facilities/within` are debounced and capped (`MAX_MAP_FEATURES`); responses report truncation.
- Every filter is kept in the URL and sent to the bounds query. Changing a parent geography clears dependent selections. The directory's map link drops only `has_coordinates=false`.
- Markers reflect recorded precision — do not render a `barangay_centroid` or `unknown` point as a building-level pin.
- The result list is a full text alternative, not an afterthought: in points mode it lists every facility; in cluster mode it lists every count circle. The directory must remain usable if tiles fail; provider attribution stays visible.

```bash
NEXT_PUBLIC_MAP_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png
NEXT_PUBLIC_MAP_TILE_ATTRIBUTION=© Example Maps
NEXT_PUBLIC_MAP_TILE_MAXZOOM=20
```

The local default is attributed OpenStreetMap raster tiles; use a licensed provider before launch — [ADR 0006](decisions/0006-basemap-provider.md).

## 5. Facility profile

The profile joins four API calls: facility detail, typed school/health detail, change history, and attribute assertions. Each optional call degrades independently. It presents, in order: identity/classification badges; address and geography; synthetic/quality warnings; registry classification; roles and services; location and precision with a map only when coordinates and known precision exist; typed school or health information; licences and accreditations with validity; source evidence; assertions and history; correction route.

Rules: never imply operational status from registry presence, licensure, or accreditation; never infer government ownership from a government publisher; show precision and method next to the map; keep `updated_at` distinct from source dates; never expose reviewer names/notes, personal contacts, or restricted source evidence.

## 6. Data and source pages

`/data` lists every dataset with agency, latest release, reference period, parsed rows, redistribution status, publication status, and synthetic labelling. `/data/[dataset]` shows metadata, rights basis, attribution, personal-data status, release history, SHA-256, and gaps. Describe actual state: if no release exists, say so; do not render a download link for a dataset that has not passed the publication gate.

## 7. Styling and components

- Global tokens and base styles: `apps/web/src/app/globals.css`.
- UI primitives: `apps/web/src/components/ui/`.
- Use `container-page`, `eyebrow`, `rule-label`, and token utilities rather than new hardcoded palettes.
- Keep square corners (`--radius-*: 0`) and borders/rules instead of drop shadows.
- The global header is `SiteHeader`; do not replace it with a dashboard sidebar.
- New interactive primitives must keep accessible behavior (focus, labels, Escape, focus return).

See [Design system](design-system.md) for measured values and the change procedure.

## 8. Security and rendering constraints

- CSP is generated per request in `apps/web/src/proxy.ts` with a fresh nonce; the root layout awaits `connection()` so Next.js can attach it.
- Do not add a second CSP header in `next.config.ts`; multiple policies combine and can block nonce-bearing scripts.
- The policy allows only configured API, tile, and HMR origins; re-check after changing either provider.
- Security headers (`nosniff`, `DENY` framing, referrer and permissions policies) are in `next.config.ts`.
- The app accepts no user-generated content and writes nothing to the API; there are no authentication or mutation flows.

## 9. Accessibility and responsiveness

Target WCAG 2.2 AA: skip link, landmarks, meaningful headings, page titles; visible `3px` focus ring with `3px` offset; mobile menu with `aria-expanded`/`aria-controls`, Escape to close, and focus return; keyboard-operable map filters and selection; no colour-only status; `prefers-reduced-motion` respected. Check layouts at 390, 768, 1024, 1440, and 1920 px.

The E2E suite asserts the hydration marker (`<html data-hydrated="true">`) before typing into controlled inputs. Keep it — it prevents flaky tests.

## 10. Tests

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e
pnpm --filter @philfacilities/web capture:responsive
pnpm --filter @philfacilities/web check:responsive
```

`apps/web/e2e/app.spec.ts` covers search, filters, profiles, map/list behaviour, mobile navigation, accessibility (axe), CSP nonce, keyboard focus, responsive capture, and precision labels. E2E defaults to the real local database; CI overrides fixture names/IDs for its synthetic demo.

## 11. Environment

| Variable | Consumer | Notes |
|---|---|---|
| `API_BASE_URL` | Server components | Internal API origin |
| `NEXT_PUBLIC_API_URL` | Browser/map, CSP | Inlined at build time; set before building |
| `NEXT_PUBLIC_SITE_URL` | Metadata/links | Canonical public origin |
| `NEXT_PUBLIC_MAP_TILE_URL` | Map, CSP | Tile template |
| `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION` | Map | Required with a custom provider |
| `NEXT_PUBLIC_MAP_TILE_MAXZOOM` | Map | Optional max zoom |

## 12. Common changes

| Change | Start here |
|---|---|
| Add a filter | API query → directory page → map page → E2E |
| Add a facility field | API schema → OpenAPI/client → profile/card → dictionary |
| Change map behaviour | `components/map/`, `lib/map-style.ts`, CSP origins |
| Change navigation | `components/site-header.tsx` + responsive tests |
| Change visual tokens | `app/globals.css`, then [Design system](design-system.md) |
| Add a page | `app/<route>/page.tsx`, breadcrumbs, metadata, nav |
| Fix an API error state | `lib/api.ts`, the route's `try/catch`, shared `Alert` |
