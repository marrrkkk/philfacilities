# 0003 — Append-only source releases and explicit change history

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

Source publications, retrieval times, and canonical changes are distinct events.
Overwriting a source value loses the evidence needed to explain a public record,
and treating retrieval time as the source's reference period misleads users.

## Decision

- Preserve original source releases and raw files; reprocessing a release is
  idempotent and does not duplicate releases or source records.
- Keep canonical current-state projections separate from source evidence.
- Record material canonical changes in `history.facility_change_events` with the
  old value, new value, source evidence, and change time.
- Keep `source_published_at`, `reference_period`, `retrieved_at`, and
  PhilFacilities `updated_at` as distinct fields with distinct meanings.
- Version geography through dated PSGC releases and expose an explicit crosswalk
  instead of mutating codes in place.
- Retain source releases only as source terms permit; document any retention
  limitation and the reacquisition path.

## Consequences

- History and provenance queries are part of the public contract.
- Reprocessing is safe to retry, but schema changes need a new parser/schema
  version rather than silent reinterpretation.
- A canonical update never implies that the agency changed the source; UI and API
  copy must keep the dates distinct.

## Evidence

`docs/data-model.md`, `docs/ingestion.md`,
`tests/test_psgc_releases.py`, and the idempotency test in
`tests/test_api_integration.py`.
