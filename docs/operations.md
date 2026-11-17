# Operations

This is the developer-facing operating guide. Detailed procedures live in `docs/operations/`:

- [Source monitoring and refresh](operations/source-monitoring-runbook.md)
- [Database backup and restore](operations/backup-restore-runbook.md)
- [Incident response](operations/incident-runbook.md)
- [Security review](operations/security-review.md)

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
| `ingest` | Python CLI/job container | Scheduled/manual job; not internet-facing |
| PostgreSQL/PostGIS | Database service | Persistent managed or self-hosted |
| Object storage | S3-compatible | Private raw objects; approved public exports |
| Tiles (optional) | Martin or similar | Only if a self-hosted basemap is added |

The web app calls the API over HTTP. The ingest app writes the database and raw store. No service reads another service's internal files.

## 3. Configuration

`.env.example` lists names and safe placeholders. Never commit live credentials, tokens, signed agreements, or private source data.

| Variable | Consumer | Notes |
|---|---|---|
| `DATABASE_URL` | Alembic | Migration connection |
| `PHILFACILITIES_DATABASE_URL` | API, ingest | Runtime connection (pydantic `PHILFACILITIES_` prefix) |
| `PHILFACILITIES_TEST_DATABASE_URL` | pytest | Must end in `_test` |
| `PHILFACILITIES_RAW_STORE` | ingest | Default `var/raw` |
| `PHILFACILITIES_REPORT_DIR` | ingest | Default `var/reports` |
| `PHILFACILITIES_S3_*` | ingest | Optional S3-compatible raw store |
| `PHILFACILITIES_ALERT_WEBHOOK_URL` | ingest | Optional actionable check, ingestion, and replay failure alert |
| `API_BASE_URL` | web server | API origin for server components |
| `NEXT_PUBLIC_API_URL` | web browser | API origin inlined at build time |
| `NEXT_PUBLIC_SITE_URL` | web | Canonical site origin |
| `NEXT_PUBLIC_MAP_TILE_URL` | web | Basemap tile template |
| `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION` | web | Required with a custom tile URL |
| `NEXT_PUBLIC_MAP_TILE_MAXZOOM` | web | Optional max zoom |
| `PHILFACILITIES_CORS_ORIGINS` | API | Comma-separated allowed origins |
| `PHILFACILITIES_RATE_LIMIT_PER_MINUTE` | API | Anonymous limit |
| `PHILFACILITIES_MAX_PAGE_SIZE` | API | List cap |
| `PHILFACILITIES_MAX_BBOX_AREA_DEG2` | API | Spatial cap |
| `PHILFACILITIES_MAX_NEARBY_RADIUS_M` | API | Radius cap |
| `PHILFACILITIES_MAX_MAP_FEATURES` | API | Map cap |
| `PHILFACILITIES_COVERAGE_STALE_AFTER_DAYS` | API | Coverage staleness threshold |

Use a deployment secret store for database and object-store credentials. Rotate credentials and record ownership.

The web app issues a fresh nonce CSP per document in `apps/web/src/proxy.ts`. The root layout awaits `connection()` so Next.js can attach the nonce; keep those changes together. The policy derives the API origin from `NEXT_PUBLIC_API_URL` and the tile origin from `NEXT_PUBLIC_MAP_TILE_URL`; re-check both after changing providers.

## 4. Database

- All schema changes go through Alembic in `apps/api/migrations/versions/`.
- Apply migrations before deploying a new API or ingest version.
- Use separate roles for migrations, ingestion, API reads, and operations. The API role should be read-only for public endpoints.
- Keep private source tables out of public DB roles.
- Test restoration, not only backup creation.

Local commands:

```bash
DATABASE_URL=postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities \
  uv run alembic -c apps/api/alembic.ini upgrade head
scripts/db_backup.sh
scripts/db_restore_verify.sh var/backups/<dump>
```

The tested local procedure, RPO/RTO targets, and production steps are in the [backup and restore runbook](operations/backup-restore-runbook.md). As of this checkout, no production schedule, off-host retention, encryption, PITR, or backup alerting is configured.

## 5. Raw storage

Content-addressed layout:

```text
var/raw/<agency>/<dataset>/<release>/<sha256>-<filename>
```

With S3 configured, the same abstraction stores objects under the configured bucket. Preserve:

- exact agency file/response;
- source URL and retrieval time;
- HTTP metadata;
- source publication/reference date;
- SHA-256;
- terms/access classification;
- parser version and release label.

Private ACL by default. Do not public-host a raw file unless the source terms permit it; publish derived facility fields and metadata instead.

Filesystem writes are atomic (temporary file, `fsync`, `os.replace`). Reads verify the manifest SHA-256; S3 reads verify the object's `sha256` metadata. A mismatch raises `RawStoreIntegrityError` and the store is never repaired in place. Preserve the failed evidence and reacquire from the source rather than overwriting the object.

## 6. Scheduled jobs

`.github/workflows/source-checks.yml`:

| Job | Command | Schedule | Effect |
|---|---|---|---|
| Due-source checks | `philfacilities-ingest source check --due` | Daily 03:17 UTC | Appends `source.source_checks`; no download or publication |
| Approved refresh | `scripts/refresh_approved_sources.sh` | Weekly Sunday 04:17 UTC, or manual | Re-runs rights-cleared loaders; unchanged checksums skipped |
| Discovery probes | `philfacilities-ingest discover-sources` | Monthly | Probes discovery-only endpoints; uploads JSON evidence; registers/publishes nothing |

The workflow requires a `PHILFACILITIES_DATABASE_URL` repository/environment secret and skips cleanly when absent. A cron/systemd alternative, failure semantics, and triage steps are in the [source monitoring runbook](operations/source-monitoring-runbook.md).

A successful check does **not** publish data. Publication requires a new release, successful parse/validation, and a satisfied rights gate.

### Ingestion locks

Each `source run` takes a PostgreSQL session-level advisory lock for its dataset on a dedicated connection and holds it across preserve, parse, apply, and report. A second worker for the same dataset fails fast with `IngestionLockError` instead of interleaving canonical writes; retry after the first run finishes. The lock is released with its connection, so a killed process does not leave a permanent lock. Different datasets can run concurrently. Geography and population writers take the same lock, and `source replay` obtains it through the writer it invokes.

### Replay

```bash
uv run philfacilities-ingest source replay docs/operations/replay-manifest.example.json
```

Replay is manifest-driven and never re-downloads. Each entry names a stored `release_id` or `raw_object_uri`; bytes are SHA-256 verified, then reprocessed through the current connector/adapter with `reprocess=True`. Use it after a parser or schema fix, or to verify that preserved bytes still produce the current derived rows. A replay failure alerts and exits non-zero; it does not alter the preserved artifact.

## 7. Monitoring signals

Production monitoring and paging are **not configured**. Use `scripts/smoke_check.sh` as a post-deploy/uptime check.

**API:** uptime, error rate, p50/p95 latency, DB pool/query latency, 429 rate, 5xx rate. `scripts/api_benchmark.py` is a local regression signal, not a load test.

**ETL:** last successful run per source, discovery/download failures, parser/schema drift, row-count anomalies, acceptance/rejection rates, quarantined releases, PSGC match rate, duplicate/ambiguous matches, quality backlog, publication-gate status.

**Web/map:** page load and client errors, API failures, tile availability, map response sizes, accessibility regressions.

`philfacilities-ingest monitoring` and `/v1/monitoring` show the latest check per dataset. `source check --due` exits `2` for actionable failures and can POST JSON to `PHILFACILITIES_ALERT_WEBHOOK_URL` when configured. `source run` and `source replay` also POST a failure summary for rows whose status is `failed`; duplicate skips and dry-run validations are not incidents.

A quarantined release is an operational signal, not a publication. Inspect the run report and the release's `QualityIssue` rows (`release_empty`, `acceptance_rate_below_floor`, `parse_error`, `row_count_anomaly`) before deciding whether to fix the parser, relax the release floor with a reviewed registry change, or reacquire the source.

## 8. Release and rollback

1. Run parser/validation tests and a dry run.
2. Ingest the new release; confirm the report counts, acceptance/rejection rates, parser/schema versions, and publication gate.
3. Compare with the prior release: `philfacilities-ingest compare-releases ...`.
4. Record release notes and known gaps: `release-manifest` / `release-notes`.
5. Confirm `/v1/statistics`, `/v1/coverage`, and `/v1/monitoring`.
6. If a release must be withdrawn, use `release-rollback` to restore the captured canonical state; do not rewrite retained source records.

A failed or below-floor new release is quarantined and the previous published release remains public. A parser-version change reprocesses the existing release automatically; use `source replay` when the fix must be applied from preserved bytes without re-downloading.

## 9. Incident and correction

For a wrong, restricted, or withdrawn source:

1. pause ingestion/publication for the affected dataset;
2. identify affected releases and public fields;
3. block API/download/statistics/map exposure for the narrowest scope;
4. preserve audit records where legally permitted, or delete as required;
5. publish a correction notice and update the rights/source record;
6. rebuild dependent records and notify API consumers if material;
7. record the decision and date in `DATA-LICENSES.md` and the source catalog.

The full severity model and playbooks are in the [incident runbook](operations/incident-runbook.md). A publisher objection follows the takedown process in [data policy](data-policy.md).

## 10. Security

- Public read API only; no write endpoints.
- Restricted source rows, personal data, credentials, SQL, and stack traces never appear in responses or logs.
- CSV exports neutralize spreadsheet-formula injection.
- CSP nonces, CORS allowlists, request IDs, rate limits, and bounded spatial queries are implemented.
- Dependency and container review: see [security review](operations/security-review.md).
- An external penetration test, hosted-origin CSP verification, and formal legal/privacy review remain launch gates.

## 11. Launch gates

Not yet configured or verified in this checkout:

- hosted API/web deployment and a published production URL;
- production rate-limit policy and external monitoring/paging;
- production backup schedule, off-host retention, encryption, and PITR;
- licensed production basemap;
- hosted scheduled run evidence and alert destination;
- external security and legal/privacy review;
- query-plan/caching work for unfiltered facility-list latency and bulk exports.
