# Monitoring and incident response runbook

**Status:** Runbook and smoke-check tooling exist. Production monitoring, paging, and an on-call rotation are **not configured**. Tracker item `M7-07` remains `REVIEW`.

Related: [Deployment and operations](../11-DEPLOYMENT-OPERATIONS.md), [backup and restore](backup-restore-runbook.md), [security review](security-review.md).

## 1. Current signals

| Signal | Available today | Notes |
|---|---|---|
| API liveness and database reachability | `GET /healthz` | Returns `status`, `service`, `version`, `database`, `environment` |
| API request timing | `X-Response-Time-Ms` header and access log line | Logs method, path, status, duration, request ID; query strings are not logged |
| Request correlation | `X-Request-ID` response header | Client values are validated; unsafe values are replaced |
| Web availability | HTTP status of `/` | No external browser or uptime check is configured yet |
| Data/quality status | `/status` page and `/v1/quality/summary` | Human-readable, not a paging source |
| Ingestion outcomes | `philfacilities-ingest status`, JSON/Markdown reports under `var/reports/` | No scheduler or failure alerting |
| Backup outcome | `scripts/db_backup.sh` exit status and manifest | No scheduled job or missing-backup alert |
| Restore verification | `scripts/db_restore_verify.sh` report | Run manually or monthly; not scheduled |
| External smoke check | `scripts/smoke_check.sh` (`just smoke`) | Checks API health, statistics, and web homepage; returns non-zero on failure |

Run the smoke check after every deployment and from an external monitor once one is selected:

```bash
PHILFACILITIES_API_BASE_URL=https://api.example.org \
PHILFACILITIES_WEB_BASE_URL=https://www.example.org \
scripts/smoke_check.sh
```

## 2. Monitoring requirements before launch

These are requirements, not installed integrations. Choose a provider and record the choice in the tracker.

### API and web

- Uptime check every 60 seconds against `/healthz` and `/` from outside the hosting network.
- Alert after two consecutive failures or five minutes of failures.
- 5xx rate above 2% for five minutes; 429 rate above 20% for ten minutes.
- p95 API latency above 1,000 ms for ten minutes, or above 2,000 ms for five minutes.
- Database connection failures and pool saturation above 80%.
- TLS certificate expiry within 21 days.
- Web client error rate and failed map-tile requests, if the provider supports them.

### Ingestion and data

- No successful ingestion run for a source beyond its expected cadence.
- Ingestion run status `failed`, parser/schema-drift failure, or zero accepted rows.
- Sudden row-count change beyond an agreed threshold.
- Publication-gate regression: a dataset that was public becomes blocked, or vice versa.
- Quality-issue backlog growth and unresolved high-severity issues.
- Raw-source download failures and checksum mismatches.

### Database and backups

- Database disk usage above 80%, replication lag, and long-running queries.
- Missing daily backup, backup job failure, or backup older than the 24-hour RPO.
- Checksum mismatch, `pg_restore` failure, or failed monthly restore verification.
- Object-storage versioning/retention disabled for a protected source bucket.

### Security

- Authentication failures on operator systems (not the public read API).
- WAF/rate-limit spikes, anomalous export volume, and repeated invalid request IDs.
- Dependency advisory alerts from the CI audit or a scheduled scanner.
- Unexpected access to raw-source buckets or backup storage.

## 3. Severity levels

| Severity | Definition | Examples | Target response |
|---|---|---|---|
| SEV-1 | Public service unavailable, data loss, or confirmed exposure of restricted data | API/database down, corrupted restore, leaked credentials, restricted source published | Immediate; incident commander and data steward engaged |
| SEV-2 | Major degradation or wrong public data | 5xx above threshold, map unusable, incorrect facility records, failed daily backup | Within 30 minutes |
| SEV-3 | Limited impact or workaround exists | One filter broken, slow endpoint, single ingestion failure, stale non-critical release | Within one business day |
| SEV-4 | Minor or cosmetic | Layout issue, documentation error, non-blocking warning | Normal backlog |

When in doubt, start at the higher severity and downgrade after triage.

## 4. Roles

These roles must be assigned before launch; they are currently **TBD**.

- **Incident commander:** owns the timeline, decisions, and communication.
- **Database operator:** owns backups, restore, migrations, and database access.
- **Data steward:** decides whether source data is wrong, restricted, or withdrawn, and whether publication must stop.
- **Communications owner:** publishes status updates and corrections.
- **Scribe:** records timestamps, actions, evidence, and decisions.

One person may hold multiple roles in a small team, but the incident commander should not also be debugging alone on a SEV-1.

## 5. First 15 minutes

1. Acknowledge the alert and open an incident record with severity, start time, and affected surfaces.
2. Check `/healthz`, `scripts/smoke_check.sh`, and the hosting/database dashboards.
3. Determine whether the failure is web, API, database, ingestion, map tiles, or a data/publication issue.
4. Freeze risky changes: pause ingestion jobs and deployments if they could worsen the incident.
5. Preserve evidence: request IDs, logs, release IDs, checksums, and relevant database state. Do not delete logs or source records.
6. Assign the incident commander and notify the data steward for any data-correctness or rights issue.
7. Post an initial status update with impact and next update time.

## 6. Playbooks

### 6.1 API or web unavailable

1. Confirm from outside the hosting network; distinguish DNS/TLS from application failure.
2. Check `/healthz`:
   - `database: unavailable` → go to 6.2;
   - API unreachable → check process/container, recent deploy, and platform status;
   - web only → check the Next.js runtime and upstream API URL.
3. Roll back the most recent deployment if it correlates with the start time.
4. Verify with `scripts/smoke_check.sh` before declaring recovery.
5. Record the failure window and whether requests were dropped or served stale.

### 6.2 Database unavailable or degraded

1. Stop ingestion and writes; keep the API read-only or offline rather than serving partial data.
2. Check disk, connections, locks, and provider status. Do not restart blindly if corruption is possible.
3. If recovery requires a restore, follow [the backup runbook](backup-restore-runbook.md). Restore to a new database, validate counts and PostGIS, then switch the connection.
4. Confirm the `alembic_version` and application smoke checks before resuming traffic.
5. Record the data-loss window (time since the last verified backup) and notify consumers if material.

### 6.3 Bad or failed ingestion release

1. Pause further ingestion for the dataset.
2. Identify the release ID, checksum, parser version, and affected facilities from the ingestion report and source links.
3. If the release was published and is wrong, block the dataset at the publication gate and remove or mark affected public records only through the documented correction path. Preserve the raw release and audit history.
4. Do not delete source records to hide a bad release. Record what changed and why.
5. Re-run the corrected release, compare counts and quality issues, and republish only after review.
6. Notify API consumers if identifiers, coordinates, or facility status changed materially.

### 6.4 Source correction or withdrawal

1. Pause ingestion/publication for the affected dataset.
2. Determine the affected source releases and public fields.
3. Remove or mark the public export according to the source terms and the data steward's decision.
4. Preserve an internal audit record where legally permitted.
5. Publish a correction notice and update the source/status pages.
6. Rebuild dependent records and notify API consumers if material.

### 6.5 Suspected data exposure or credential leak

1. Treat as SEV-1. Do not discuss details in public channels.
2. Revoke exposed credentials and rotate database, object-store, and deployment secrets.
3. Identify the exposed data, time window, and recipients from logs and storage access records.
4. Preserve evidence and engage the data steward and legal/privacy owner.
5. Follow the applicable breach-notification requirement; do not publish speculation.
6. Add a regression control and document the incident in the post-incident review.

### 6.6 Backup or restore failure

1. Check the backup job output and manifest; confirm whether a dump exists and its checksum.
2. If the checksum fails, discard the copy and restore from another verified copy.
3. If `pg_restore` fails, check PostgreSQL/PostGIS versions, extensions, roles, and disk space.
4. If no verified backup exists within the RPO, treat as SEV-2 and escalate to the database operator.
5. Re-run verification and record the result. Do not mark the backup healthy without a successful restore check.

### 6.7 Map tile provider outage

1. Confirm the API and result list still work; the map must never be the only access path.
2. Keep the visible fallback notice and list available.
3. Check the tile provider status and attribution requirements.
4. If the outage is prolonged, switch to the approved fallback provider only if its terms and attribution are recorded.

## 7. Communication

Initial update template:

```text
[SEV-N] PhilFacilities incident — <short description>
Status: investigating | identified | monitoring | resolved
Impact: <who/what is affected>
Started: <UTC timestamp>
Current action: <one sentence>
Next update: <UTC timestamp>
```

Correction notice template for wrong public data:

```text
Correction: <dataset/facility scope>
What changed: <field/value and direction>
Affected releases: <release labels and dates>
Cause: <source correction/parser defect/operational error>
Action taken: <records corrected, exports regenerated, API consumers notified>
Verification: <tests/checks and timestamp>
```

Do not include personal data, credentials, or restricted source content in public updates.

## 8. Recovery and closure

- Confirm the smoke check, health endpoint, directory, facility profile, map, and a bulk export.
- Confirm the affected dataset's publication gate and quality status.
- Record start/end times, detection source, root cause, actions, data-loss window, and follow-up owners.
- Schedule a blameless post-incident review within five business days for SEV-1/SEV-2.
- Add regression tests or monitoring for the failure mode; update this runbook.

## 9. Known gaps

- No production monitoring provider, paging, or on-call rotation.
- No scheduled smoke check, backup job, or restore verification.
- No centralized log retention, tracing, or alert routing.
- No assigned incident roles.
- No external status page or subscriber notification list.
- No production deployment or TLS/WAF controls; see the [security review](security-review.md).
