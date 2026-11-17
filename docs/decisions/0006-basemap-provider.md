# 0006 — MapLibre renderer with a configurable, licensed basemap

- **Status:** Proposed for production; OpenStreetMap demo configuration in use
- **Date:** 2026-11-15

## Context

The map must remain a client of the public API, work without a vendor lock-in, and
show correct attribution. OpenStreetMap's public raster tile service is acceptable
for low-volume evaluation but is not a production SLA, and a licensed provider has
not been selected. Tile providers differ in URL templates, attribution text, and
maximum zoom.

## Decision

- Use MapLibre GL JS as the renderer, independent of any tile provider.
- Build the raster basemap from `NEXT_PUBLIC_MAP_TILE_URL`,
  `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION`, and optional
  `NEXT_PUBLIC_MAP_TILE_MAXZOOM`.
- Default to OpenStreetMap raster tiles **for the current local/demo deployment
  only**, with visible OpenStreetMap attribution; this is not a production
  tile-provider commitment.
- Keep attribution visible and accurate. If a custom tile URL is configured
  without attribution, render no attribution rather than borrowing
  OpenStreetMap's credit; deployments must treat that as a configuration error.
- Do not hardcode provider API keys in the web client. If a provider requires a
  secret, use its documented public-token or proxy mechanism and review the terms.
- Keep the accessible result list and the map-failure notice available when tiles
  fail.
- Select and record a production provider, licence, attribution, and usage limits
  before public launch.

## Consequences

- Switching providers does not require a code change, only a reviewed build-time
  configuration change.
- The demo's OSM dependency is explicit and must not be presented as a production
  commitment.
- The production provider and licence decision remains open.

## Evidence

`apps/web/src/lib/map-style.ts`, `apps/web/src/components/map/map-explorer.tsx`,
`apps/web/src/components/map/location-map.tsx`, `.env.example`, and the map tests
in `apps/web/e2e/app.spec.ts`.
