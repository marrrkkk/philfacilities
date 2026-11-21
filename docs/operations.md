# Operations

> **Purpose** — Developer-facing operating guide: configuration, database, jobs, monitoring, release/rollback, and launch gaps.
> **Audience** — Operators and agents deploying or maintaining an instance.
> **Runbooks** — [Source monitoring](operations/source-monitoring-runbook.md) · [Backup and restore](operations/backup-restore-runbook.md) · [Incident response](operations/incident-runbook.md) · [Security review](operations/security-review.md)
> **See also** — [Getting started](getting-started.md) · [Ingestion](ingestion.md) · [MCP](mcp.md)

## 1. Environments

| Environment | Database | Data | Purpose |
|---|---|---|---|
| `local` | Compose PostgreSQL/PostGIS (54329) | Rights-cleared real sources; synthetic fixtures only in tests | Development |
| `test` | Compose `test-db` (54330) | Synthetic fixtures; schema reset each session | Integration tests |
| `staging` | Managed/self-hosted PostGIS | Publication-approved data only | Pre-production verification |
| `production` | Managed/self-hosted PostGIS | Approved releases only | Public service |

Never place restricted FOI files or agreement-bound data in a public staging or production environment unless the agreement permits it.

## 2. Deployment units

| Service | Runtime | Boundary |
|---|---|---|
| `web` | Next.js Node runtime | Independent web deployment |
| `api` | FastAPI ASGI container | Independent API service |
| `mcp` | Python stdio process or Streamable HTTP ASGI service | Independent read-only adapter over `/v1`; no database access |
| `ingest` | Python CLI/job container | Scheduled/manual job; not internet-facing |
| PostgreSQL/PostGIS | Database service | Persistent managed or self-hosted |
| Object storage | S3-compatible | Private raw objects; approved public exports |
| Tiles (optional) | Martin or similar | Only if a self-hosted basemap is added |

The web app calls the API over HTTP; ingest writes the database and raw store; the MCP service calls the API over HTTP with no database credentials. No service reads another's internal files.

## 3. Configuration

`.env.example` lists names and safe placeholders. Never commit live credentials, tokens, signed agreements, or private source data. Use a deployment secret store and rotate credentials.

| Variable | Consumer | Notes |
|---|---|---|
| `DATABASE_URL` | Alembic | Migration connection |
| `PHILFACILITIES_DATABASE_URL` | API, ingest | Runtime connection |
| `PHILFACILITIES_TEST_DATABASE_URL` | pytest | Must end in `_test` |
| `PHILFACILITIES_RAW_STORE` | ingest | Default `var/raw` |
| `PHILFACILITIES_REPORT_DIR` | ingest | Default `var/reports` |
| `PHILFACILITIES_S3_*` | ingest | Optional S3-compatible raw store |
| `PHILFACILITIES_ALERT_WEBHOOK_URL` | ingest | Actionable check/ingestion/replay failure alerts |
| `API_BASE_URL` | web server | API origin for server components |
| `NEXT_PUBLIC_API_URL` | web browser | API origin inlined at build time |
| `NEXT_PUBLIC_SITE_URL` | web | Canonical site origin |
| `NEXT_PUBLIC_MAP_TILE_*` | web | Basemap template, attribution, max zoom |
| `PHILFACILITIES_CORS_ORIGINS` | API | Comma-separated allowed origins |
| `PHILFACILITIES_RATE_LIMIT_PER_MINUTE` | API | Anonymous limit |
| `PHILFACILITIES_MAX_PAGE_SIZE` | API | List cap |
| `PHILFACILITIES_MAX_BBOX_AREA_DEG2`, `MAX_NEARBY_RADIUS_M`, `MAX_MAP_FEATURES` | API | Spatial/map caps |
| `PHILFACILITIES_COVERAGE_STALE_AFTER_DAYS` | API | Coverage staleness threshold |
| `PHILFACILITIES_API_BASE_URL` | MCP | API origin; use the internal origin in production |
| `PHILFACILITIES_REQUEST_TIMEOUT_SECONDS` | MCP | Upstream timeout |
| `PHILFACILITIES_MCP_HOST` / `MCP_PORT` | MCP | HTTP bind address (stdio ignores) |
| `PHILFACILITIES_MCP_ALLOWED_HOSTS` / `ALLOWED_ORIGINS` | MCP | Required Host/Origin allowlists for hosted use |
| `PHILFACILITIES_MCP_FORWARDED_ALLOW_IPS` | MCP | Trusted proxy addresses |

The web app issues a fresh nonce CSP per document in `apps/web/src/proxy.ts`; the root layout awaits `connection()` so Next.js can attach it. The policy derives API origin from `NEXT_PUBLIC_API_URL` and tile origin from `NEXT_PUBLIC_MAP_TILE_URL` — re-check both after changing providers.

## 4. Database

- All schema changes go through Alembic in `apps/api/migrations/versions/`.
- Apply migrations before deploying a new API or ingest version; do not edit an already-applied migration in a released branch.
- Use separate roles for migrations, ingestion, API reads, and operations; the API role should be read-only for public endpoints.
- Keep private source tables out of public DB roles. Test restoration, not only backup creation.

```bash
DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
  uv run alembic -c apps/api/alembic.ini upgrade head
scripts/db_backup.sh
scripts/db_restore_verify.sh var/backups/<dump>
```

The tested local procedure, RPO/RTO targets, and production steps are in the [backup and restore runbook](operations/backup-restore-runbook.md). No production schedule, off-host retention, encryption, PITR, or backup alerting is configured in this checkout.

## 5. Raw storage

Content-addressed layout: `var/raw/<agency>/<dataset>/<release>/<sha256>-<filename>`. With S3 configured, the same abstraction stores objects in the bucket. Preserve the exact agency file/response, URL and retrieval time, HTTP metadata, source publication/reference date, SHA-256, terms/access classification, and parser version/release label.

Private ACL by default; do not public-host a raw file unless terms permit — publish derived fields and metadata instead. Filesystem writes are atomic and reads verify the manifest; S3 reads verify object `sha256` metadata. A mismatch raises `RawStoreIntegrityError`; the store is never repaired in place. Preserve failed evidence and reacquire from the source.

## 6. Scheduled jobs

`.github/workflows/source-checks.yml`:

| Job | Command | Schedule | Effect |
|---|---|---|---|
| Due-source checks | `philfacilities-ingest source check --due` | Daily 03:17 UTC | Appends `source.source_checks`; no download or publication |
| Approved refresh | `scripts/refresh_approved_sources.sh` | Weekly Sunday 04:17 UTC, or manual | Re-runs rights-cleared loaders; unchanged checksums skipped |
| Discovery probes | `philfacilities-ingest discover-sources` | Monthly | Probes discovery-only endpoints; uploads JSON evidence; registers/publishes nothing |

The workflow requires a `PHILFACILITIES_DATABASE_URL` secret and skips cleanly when absent. A successful check does **not** publish data; publication requires a new release, successful parse/validation, and a satisfied rights gate. See the [source monitoring runbook](operations/source-monitoring-runbook.md).

**Ingestion locks.** Each `source run` takes a session-level advisory lock for its dataset on a dedicated connection across preserve, parse, apply, and report. A second worker fails fast with `IngestionLockError`; different datasets can run concurrently. The lock is released with its connection, so a killed process leaves no permanent lock.

**Replay.** `uv run philfacilities-ingest source replay docs/operations/replay-manifest.example.json` is manifest-driven and never re-downloads. Bytes are SHA-256 verified, then reprocessed through current parsers with `reprocess=True`. A failure alerts and exits non-zero without altering the preserved artifact.

## 7. Monitoring signals

Production monitoring and paging are **not configured**. Use `scripts/smoke_check.sh` as a post-deploy/uptime check.

- **API** — uptime, error rate, p50/p95 latency, DB pool/query latency, 429 and 5xx rates. `scripts/api_benchmark.py` is a local regression signal, not a load test.
- **ETL** — last successful run per source, discovery/download failures, parser/schema drift, row-count anomalies, acceptance/rejection rates, quarantined releases, PSGC match rate, ambiguous matches, quality backlog, gate status.
- **Web/map** — page/client errors, API failures, tile availability, map response sizes, accessibility regressions.
- **MCP** — `/healthz`, `/readyz`, tool error rate, upstream 429/5xx. The server aggregates callers behind one IP: apply edge rate limiting to `/mcp` before public launch.

`philfacilities-ingest monitoring` and `/v1/monitoring` show the latest check per dataset. `source check --due` exits `2` for actionable failures and can POST to the alert webhook; duplicate skips and dry runs are not incidents. A quarantined release is an operational signal — inspect its `QualityIssue` rows (`release_empty`, `acceptance_rate_below_floor`, `parse_error`, `row_count_anomaly`) before fixing the parser, relaxing the floor with a reviewed registry change, or reacquiring.

## 8. Release and rollback

1. Run parser/validation tests and a dry run.
2. Ingest the new release; confirm counts, rates, parser/schema versions, and the gate.
3. Compare with the prior release: `philfacilities-ingest compare-releases ...`.
4. Record release notes and gaps: `release-manifest` / `release-notes`.
5. Confirm `/v1/statistics`, `/v1/coverage`, `/v1/monitoring`.
6. If withdrawal is needed, use `release-rollback` to restore captured canonical state; do not rewrite retained source records.

A failed or below-floor new release is quarantined while the previous stays public. A parser-version change reprocesses automatically; use `source replay` when the fix must come from preserved bytes without re-downloading.

## 9. Incident and correction

For a wrong, restricted, or withdrawn source: pause ingestion/publication for the dataset; identify affected releases and fields; block API/download/statistics/map exposure for the narrowest scope; preserve audit records where legally permitted or delete as required; publish a correction notice and update the rights/source record; rebuild dependent records and notify consumers if material; record the decision and date in `DATA-LICENSES.md` and the source catalog. The severity model and playbooks are in the [incident runbook](operations/incident-runbook.md); a publisher objection follows [takedown](data-policy.md).

## 10. Security

- Public read API only, no write endpoints; the MCP server is public and read-only with host/origin allowlists and no database credentials.
- Restricted source rows, personal data, credentials, SQL, and stack traces never appear in responses or logs.
- CSV exports neutralize spreadsheet-formula injection; CSP nonces, CORS allowlists, request IDs, rate limits, and bounded spatial queries are implemented.
- Dependency and container review: [security review](operations/security-review.md). External penetration testing, hosted-origin CSP verification, and formal legal/privacy review remain launch gates.

## 11. Launch gates

Not yet configured or verified in this checkout: hosted API/web deployment and production URL; production rate-limit policy and external monitoring/paging; production backup schedule, off-host retention, encryption, and PITR; licensed production basemap; hosted scheduled-run evidence and alert destination; external security and legal/privacy review; and query-plan/caching work for unfiltered facility-list latency and bulk exports.
