# 0005 — Preserve coordinate precision; never auto-merge

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

Agency files mix GPS points, geocoded addresses, barangay centroids, and missing
coordinates. A point on a map can look more precise than its evidence, and two
records with distant coordinates are unlikely to be the same facility.

## Decision

- Store source-supplied precision and method with each location; do not upgrade
  precision during normalization.
- Keep missing coordinates as missing. Never convert them to `(0, 0)` or infer a
  location from an address without recording the method and precision.
- Use the precision enum `gps_verified`, `field_verified`, `source_gps`,
  `map_geocoded`, `barangay_centroid`, `unknown`.
- Render low-precision locations as area-level context, not building pins, and
  keep the text location available when the map fails.
- Reject out-of-range and partial coordinates through validation and report them
  as quality issues.
- Require human review for conflicting IDs or implausibly distant coordinates;
  never merge on name similarity or proximity alone.

## Consequences

- Some facilities intentionally have no map point.
- Distance and map products must state their precision basis.
- Coordinate validation changes can create quality issues rather than silently
  correcting values.

## Evidence

`docs/04-DATA-MODEL.md`, `apps/ingest/philfacilities_ingest/pipeline.py`,
`apps/web/src/components/map/location-map.tsx`, and coordinate tests in
`tests/test_api_integration.py` and `tests/test_data_quality.py`.
