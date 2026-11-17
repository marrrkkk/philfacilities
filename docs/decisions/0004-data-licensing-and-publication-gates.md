# 0004 — Separate code and data rights with publication gates

- **Status:** Accepted; amended by [0008](0008-publicly-available-data-inclusion.md) for verified, publicly available datasets with no explicit prohibition
- **Date:** 2026-11-14

## Context

An open-source code licence does not grant rights to redistribute government
source data. Access methods, FOI responses, and agency terms differ by dataset,
and some releases are restricted or unpublished.

## Decision

- License project code under Apache-2.0; treat source-data rights separately.
- Record the publisher, source URL, release, licence/terms status, redistribution
  permission, and decision date in `DATA-LICENSES.md` and the source register.
- Classify datasets with an explicit gate. `UNKNOWN` and `INTERNAL_ONLY` sources
  are not published; `DERIVED_FIELDS_ONLY` requires an explicit field list.
- Gate API downloads, publication, and public demos on the recorded decision.
- Synthetic fixtures are confined to tests. The working database now publishes
  only rights-cleared real sources; every synthetic record remains labelled as
  synthetic if a test fixture is loaded.

## Consequences

- A source can be ingested internally without becoming publishable.
- New sources and fields require a rights review before they appear publicly.
- Ingesting a source is not evidence that it may be republished; the published
  set currently comprises only the rights-cleared sources in `DATA-LICENSES.md`.
- Removing or restricting a source requires the incident procedure, not a silent
  data edit.

## Evidence

`DATA-LICENSES.md`, `docs/03-SOURCE-REGISTER.md`,
`docs/09-OPEN-SOURCE-GOVERNANCE.md`, and the publication-gate tests in
`tests/test_data_quality.py`.
