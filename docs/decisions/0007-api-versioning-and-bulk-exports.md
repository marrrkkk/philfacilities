# 0007 — Stable `/v1` contract and gated bulk exports

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

The API is a standalone public product, not a private backend for the website.
Third-party clients need stable shapes, predictable pagination, and downloadable
data, while source rights and dataset size limit what can be published.

## Decision

- Serve the public contract under `/v1`; keep it backward compatible.
- Add optional fields without breaking existing response shapes. Deprecate fields
  with notice and migration notes.
- Treat OpenAPI as the contract: export `packages/api-client/openapi.json`,
  generate `schema.ts`, and keep contract tests in the release checks.
- Use opaque cursor pagination for facility and change feeds, with a documented
  maximum page size and bounded spatial queries.
- Return a consistent error envelope with a stable code, message, details, and
  request ID; do not expose SQL, paths, credentials, or stack traces.
- Apply transparent rate limits and CORS settings; no API key is required for
  basic public reads in the initial release.
- Publish CSV/Parquet downloads only for datasets that pass the source-specific
  publication gate. A download must never expose a restricted source.

## Consequences

- Every API change requires a contract diff, client regeneration, and tests.
- Bulk exports can lag the API while a source's rights are unresolved. The
  exports contain only public-compatible records whose release gate is approved
  or published (83,769 facilities when this decision was recorded); restricted
  and internal-only sources never enter a download.
- Breaking changes require a new version rather than an in-place edit.

## Evidence

`docs/06-PUBLIC-API.md`, `packages/api-client/openapi.json`,
`packages/api-client/src/schema.ts`, `tests/test_api_contract.py`, and
`tests/test_api_integration.py`.
