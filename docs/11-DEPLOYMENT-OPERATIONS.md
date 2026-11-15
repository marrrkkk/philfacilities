# 11 — Deployment and Operations

## 1. Environment model

Maintain three environments:

- `local`: Docker Compose, PostgreSQL/PostGIS, the configured real rights-cleared sources, and deterministic test fixtures used only by the test suite.
- `staging`: non-public or clearly labeled deployment using publication-approved data only.
- `production`: public web/API and approved data releases.

Never use restricted FOI files in a public staging or production environment unless their agreement permits it.

## 2. Deployment units

| Service | Runtime | Deployment boundary |
|---|---|---|
| `web` | Next.js Node runtime | Independent web deployment |
| `api` | FastAPI ASGI container | Independent API container/service |
| `ingest` | Python CLI/job container | Scheduled/manual job; not internet-facing |
| PostgreSQL/PostGIS | Database service | Persistent managed or self-hosted DB |
| Object storage | S3-compatible | Private raw objects; public approved exports |
| Optional tiles | Martin or similar | Separate only if added later |

## 3. Local development

Docker Compose should provide:

- PostgreSQL with PostGIS enabled;
- optional local S3-compatible object storage (e.g. MinIO) only if needed for realistic tests;
- API and web dev services may run on the host through `just` commands or in containers;
- production-like local data is loaded from rights-cleared sources; synthetic fixtures are confined to automated tests and are labelled.

Expected root commands:

```bash
just setup          # install dependencies, start PostgreSQL/PostGIS, apply migrations
just format         # format Python sources with ruff
just test           # Python unit, contract, integration, and data-quality tests
just lint           # ruff check/format check plus web ESLint
just typecheck      # web TypeScript
just db-up
just db-migrate
just fixtures       # regenerate deterministic test fixtures (test/demo use only)
just demo           # load the synthetic demo dataset; never run against a real-data database
just api            # FastAPI on 127.0.0.1:8010
just web            # Next.js on 127.0.0.1:3000
just openapi-export # refresh packages/api-client/openapi.json
just typegen        # export OpenAPI, then regenerate the TypeScript client
just smoke
just backup-db
just restore-verify
```

Implement commands as they become available; do not document a command as working before it exists.
The real-data CLI is documented in `uv run philfacilities-ingest --help`. `load-real` performs the
rights-cleared acquisition sequence; individual `load-psgc-bettergov`, `load-population`,
`load-philhealth`, `load-osm`, and `load-deped-ebeis` commands are available for diagnosis.
Official PSA, DepEd Machine-Ready, and DOH acquisition remains blocked under M1.

## 4. Configuration and secrets

- `.env.example` contains names and safe placeholders only.
- Never commit live credentials, tokens, signed data-use agreements, or private source data.
- Separate read-only public source URLs from secrets required for official API access.
- Use deployment secret stores for DB credentials, object-store credentials, and API tokens.
- Rotate credentials and document ownership.
- The current internal security and dependency review, including fixed vulnerabilities and residual production controls, is in the [security review](operations/security-review.md).
- The basemap is configured with `NEXT_PUBLIC_MAP_TILE_URL`, `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION`, and optional `NEXT_PUBLIC_MAP_TILE_MAXZOOM`. They are inlined at web build time. Set both the URL and attribution to a licensed provider before launch; a custom URL without attribution is a configuration error. See [ADR 0006](decisions/0006-basemap-provider.md).
- `apps/web/src/proxy.ts` issues a fresh nonce CSP for every document. The root layout awaits `connection()` so pages are dynamically rendered and Next.js can attach the nonce; keep those two changes together. The policy derives the browser API origin from `NEXT_PUBLIC_API_URL` and the tile origin from `NEXT_PUBLIC_MAP_TILE_URL`, so verify both after changing providers. A deployed-origin CSP check and an external penetration test remain launch gates.

## 5. Database operations

- Use migrations for all schema changes.
- Automated daily backup at minimum once public data is operational; confirm point-in-time recovery capability with provider.
- Test restoration, not only backup creation. The tested local procedure and the production restore steps are in [the database backup and restore runbook](operations/backup-restore-runbook.md).
- Use a separate DB role for ingestion, API read, migrations, and operations.
- API role should be read-only for public endpoints.
- Keep private raw/source tables inaccessible from public DB roles.

## 6. Object storage

Suggested key pattern:

```text
raw/{agency}/{dataset}/{release_id}/{original_filename}
processed/{dataset}/{release_id}/{schema_version}/...
exports/{dataset}/{release_id}/...
```

Apply private ACL by default. Publish a curated export only after rights and quality review. Store SHA-256 and a source manifest beside each object.

## 7. Monitoring

Production monitoring and paging are **not configured**. The current signals, alert thresholds, severity levels, and response playbooks are in the [monitoring and incident response runbook](operations/incident-runbook.md). Use `scripts/smoke_check.sh` (or `just smoke`) as the external post-deploy/uptime check.

Source checks are registered and due-date driven. `.github/workflows/source-checks.yml` runs daily
and refreshes only rights-cleared sources weekly or on manual dispatch; it skips cleanly when
`PHILFACILITIES_DATABASE_URL` is absent. No hosted run, alert destination, paging rotation, or
production scheduler has been observed. See the
[source monitoring runbook](operations/source-monitoring-runbook.md).

### API

- uptime and error rate;
- p50/p95 latency;
- database connection pool and query latency;
- rate-limit events;
- 5xx and 429 rates.

A local baseline against the real database is available from `scripts/api_benchmark.py` (`just benchmark-api`). Use it to detect obvious regressions before deployment; it is not a production load test. The current statistics and facility-list latency are too high for launch; see the measured table in [`docs/10-QUALITY-TESTING.md`](10-QUALITY-TESTING.md). Bulk exports of 83,769 rows take roughly 100 seconds locally, so production should pre-generate or cache them.

### ETL

- last successful run per source;
- file discovery and download failures;
- parser failures/schema drift;
- row-count changes;
- PSGC match rate;
- duplicate/ambiguous match counts;
- quality issue backlog;
- publication-gate status.

### Web/map

- page load and client error monitoring;
- API failures;
- tile provider availability;
- map query response sizes;
- accessibility regressions.

## 8. Backups and recovery

- PostgreSQL backups with restoration exercises. See [the backup and restore runbook](operations/backup-restore-runbook.md) for the tested commands, evidence, RPO/RTO targets, production restore steps, and current limitations.
- **Current status:** the local Compose backup/restore procedure is tested; no production schedule, off-host retention, encryption, PITR, or alerting is configured. The working database now contains real publication-approved data, so production backup/retention review is a launch gate.
- Object storage versioning or immutable retention for allowed raw sources.
- Database migrations reversible where practical; destructive changes require backup and explicit plan.
- Rebuild derived tables from preserved raw data when terms allow.
- If raw retention is restricted, document the limitation and reacquisition process.

## 9. Cost control

Start with a modest PostgreSQL/PostGIS deployment, one small API instance, static/managed web hosting, and scheduled short-lived ingestion jobs. Keep large exports in object storage. Avoid always-on workflow infrastructure until needed. Measure storage, egress, database CPU, map tile usage, and scheduled job duration.

## 10. Incident and source correction procedure

The full severity model, roles, playbooks, communication templates, and closure checklist are in the [monitoring and incident response runbook](operations/incident-runbook.md). Summary:

If a source is wrong, restricted, or withdrawn:

1. Pause ingestion/publication for affected dataset.
2. Determine affected source releases and public fields.
3. Remove or mark the public export according to terms and policy.
4. Preserve an internal audit record where legally permitted.
5. Publish a correction notice and update source status.
6. Rebuild dependent records and notify API consumers if material.
