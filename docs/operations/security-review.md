# Security and dependency review

**Review date:** 14 November 2026; real-data posture and CSP verification updated 15 November 2026.  
**Scope:** API, web frontend, public exports, dependency manifests, local deployment configuration.  
**Status:** Internal review completed; production security controls and an external penetration test are **not** complete. Production launch gates remain open.

This is a source and configuration review, not a certification, penetration test, or production readiness sign-off. The working database contains real records: **99,352 public facilities** from sources with a recorded publication decision and **128,939 non-public records**, including 83,218 DepEd EBEIS rows pending field-level review. The public boundary is enforced in code, but no formal legal, privacy, or external security review has been completed.

## 1. Assets and trust boundaries

| Asset | Exposure | Notes |
|---|---|---|
| Facility, geography, provenance, and quality data | Public read API | Read-only in this release; no write endpoints |
| Raw source files | Private object storage / local filesystem | Not served publicly |
| PostgreSQL/PostGIS | Private network | Compose port is published locally for development only |
| Ingest CLI | Operator-only | Not internet-facing |
| Web frontend | Public | Server-rendered Next.js plus MapLibre client |
| Bulk CSV/Parquet exports | Public, publication-gated | Only public and permitted-source rows |
| Credentials and configuration | Environment variables | `.env` is ignored; `.env.example` contains placeholders only |

The public trust boundary is the API/web edge. Database and ingestion credentials must never be exposed to browser code.

## 2. Method

- Manual review of API routing, middleware, error handling, query construction, CSV generation, and Next.js configuration.
- Verified the OpenAPI contract exposes only `GET` operations (`tests/test_api_contract.py::test_openapi_is_read_only`).
- Ran `pip-audit` against the Python environment and `pnpm audit` against the JavaScript workspace.
- Re-ran lint, type checks, production build, Python tests, and Playwright (including map canvas and security headers) after changes.

## 3. Findings and remediation

| ID | Severity | Finding | Status | Evidence / action |
|---|---|---|---|---|
| SEC-01 | Critical | `maplibre-gl` 5.24.1 was affected by an XSS sanitizer bypass in `DOM.sanitize()` via live `NamedNodeMap` removal (`GHSA-jrc7-96c5-q579`, vulnerable `<=6.4.0`). | **Fixed** | Upgraded to `maplibre-gl` 6.18.0; removed the v5 default-import assumption; production build and Playwright map-canvas tests pass |
| SEC-02 | Moderate | Dev-only `minimatch` 10.2.6 was affected by denial of service via globpart amplification (`GHSA-g3hv-75wg-m249`, vulnerable `>=7.0.0 <11.0.1`). | **Fixed** | Added a pnpm workspace override to `minimatch@11.0.1`; `pnpm audit` is clean and ESLint still passes |
| SEC-03 | Medium | The per-facility CSV export wrote source-controlled text without neutralizing spreadsheet formula prefixes (`=`, `+`, `-`, `@`). Bulk exports already did this. | **Fixed** | Centralized `sanitize_csv_cell`, applied it to both export paths, and added an integration test using a formula-shaped facility name while preserving numeric coordinates |
| SEC-04 | Low | A client-supplied `X-Request-ID` was reflected without validation, allowing arbitrary values and potential log injection. | **Fixed** | IDs must match `[A-Za-z0-9._:-]{8,128}`; otherwise the API generates a UUID. Contract test covers unsafe IDs |
| SEC-05 | Low | Pagination cursors had no length limit before Base64/JSON decoding. | **Fixed** | Cursors over 512 characters return `invalid_cursor`; integration test added |
| SEC-06 | Low | The in-process rate-limiter dictionary could grow without bound under many distinct client addresses. | **Mitigated** | Stale windows are pruned and tracked clients are capped at 20,000. This is still a single-process limiter, not a DDoS defense |
| SEC-07 | Medium | Rate limiting is per API process and keys on the socket peer address. Behind a proxy, all clients may share one address unless proxy handling is configured. | **Open — production** | Use an edge/WAF limiter and a documented trusted-proxy configuration before public launch |
| SEC-08 | Medium | The web app had no baseline browser security headers or script/style CSP. | **Fixed** | Added `X-Content-Type-Options`, `X-Frame-Options: DENY`, strict referrer policy, permissions policy, COOP, and disabled `X-Powered-By`. `src/proxy.ts` now issues a fresh nonce per document, uses `script-src 'self' 'nonce-…' 'strict-dynamic'` (no `unsafe-inline`), restricts `connect-src`/`img-src`/`worker-src` to the app, API, and configured basemap origins, and sets `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, and `frame-ancestors 'none'`. `style-src-attr 'unsafe-inline'` remains for MapLibre's inline style mutations; style elements still require the nonce. Playwright asserts nonce freshness, nonce coverage on every script, and no CSP violations on public pages or the MapLibre map |
| SEC-09 | Medium | No production TLS/HSTS, WAF, secret manager, or network policy exists because there is no production deployment. | **Open — deployment** | Terminate TLS at the platform, enable HSTS after HTTPS is verified, store credentials in a managed secret store, and restrict database/object-store access |
| SEC-10 | Low | No automated SBOM or continuous dependency monitoring beyond the new audit steps. | **Open** | CI now runs `pip-audit` and `pnpm audit --prod`; add scheduled advisory monitoring and an SBOM when a release process exists |
| SEC-11 | Low | Backups contain both public data and internal-only source records, including the DepEd EBEIS school-head names, and raw source objects may carry additional terms. | **Documented** | Backup and raw-store access must follow the same rights restrictions as the database; storage/access requirements are in the [backup runbook](backup-restore-runbook.md). No production backup store exists yet |
| SEC-12 | Informational | Public API documentation and OpenAPI are exposed without authentication. | **Accepted** | Intentional for a public read API; no secrets or write operations are exposed |

No SQL injection finding: all user-controlled filters are expressed through SQLAlchemy bound parameters. The only literal SQL is a fixed `SELECT 1` health check. No authentication/authorization finding applies to the current read-only public contract; ingestion and database access are operator-only.

## 4. Dependency audit evidence

Latest runs (files under [`evidence/2026-11-14-security-review/`](evidence/2026-11-14-security-review/)):

```text
uv run --with pip-audit pip-audit   -> No known vulnerabilities found
pnpm audit                          -> No known vulnerabilities found
```

`pip-audit` reports `philfacilities-api` and `philfacilities-ingest` as skipped because they are local workspace packages not published to PyPI. Their imports and runtime dependencies are still audited through the installed environment.

The CI workflow now runs both audits. A hosted green run has not been observed.

## 5. Controls confirmed

- Public API is read-only; no write verbs in the OpenAPI contract.
- Publication queries require `publication_status = public` and a source release with a recorded publication decision whose rights and publication states permit redistribution. Internal-only, blocked, quarantined, and review-pending evidence is excluded from detail, source evidence, statistics, and downloads.
- CORS is an explicit configured allowlist, not `*`.
- Error responses use a stable envelope and generic 500 message; stack traces are not returned.
- Access logging records method, path, status, duration, and request ID, but not query strings or credentials.
- CSV exports neutralize formula prefixes and preserve numeric values.
- Security headers are set by both the web app and the API; the web CSP uses a per-response nonce.
- Lockfiles are committed; Python installs use `--locked` and JavaScript installs use `--frozen-lockfile` in CI.
- `.env` is ignored; `.env.example` contains local placeholders only.

## 6. Residual risks and launch gates

Before any public production launch:

1. Deploy behind TLS with HSTS, a WAF/edge rate limiter, and a documented trusted-proxy setup.
2. Verify the nonce CSP against the deployed API and tile origins. Nonces require dynamic rendering, so the current web configuration deliberately disables static generation; confirm that trade-off against the hosting/CDN plan and keep `src/proxy.ts` paired with the root-layout `connection()` call.
3. Move database, object-store, and ingestion secrets into a managed secret store with rotation ownership.
4. Run an external penetration test and a dependency/SBOM review against the release candidate.
5. Complete the source-rights and personal-data review. Real data is published under recorded terms or the verified-public-availability policy in `docs/data-policy.md`; DepEd EBEIS school-head names remain private, and canonical DepEd rows remain internal pending field-level mapping and privacy review. No formal legal or privacy review has been completed.
6. Implement production monitoring and the incident runbook.
7. Re-run audits and record results in the release checklist.

Until these are complete, this review supports the current local/real-data deployment only. It does not establish production security acceptance or legal permission to publish any source.
