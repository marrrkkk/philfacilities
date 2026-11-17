# 0002 — Canonical facility identity and reviewed source links

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

A school or health facility can appear in several agency releases with different
IDs, spellings, and addresses. Names alone are not reliable identifiers, and an
incorrect merge silently corrupts provenance and public answers.

## Decision

- Every canonical facility gets a stable PhilFacilities UUID that is not derived
  from a name or source ID.
- One canonical facility may link to many source records; every published facility
  must retain source evidence.
- Exact source-ID matches may link records deterministically.
- Ambiguous candidates are written to `quality.match_candidates` for named human
  review. They are never merged automatically, and rejected pairs are retained.
- Accepting a candidate is a separate step from merging it. A merge moves evidence
  to the surviving facility and leaves the retired facility as a `merged`
  tombstone with `facility_merged_into` / `facility_merged_from` change events.

## Consequences

- Duplicate facilities may remain visible until review; that is preferred to a
  silent merge.
- Reviewer identity and notes stay internal; public responses expose the method,
  confidence, evidence, and resolution only.
- Matching algorithm changes require a new version so previously rejected pairs
  can be reconsidered deliberately.

## Evidence

`docs/data-model.md`, `apps/ingest/philfacilities_ingest/matching.py`,
`tests/test_identity_matching.py`, and `tests/test_api_integration.py`.
