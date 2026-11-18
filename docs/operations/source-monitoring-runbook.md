# Source Monitoring and Scheduled Refresh Runbook

**Status:** implemented and locally exercised; a hosted scheduled run has not been observed.  
**Audience:** an operator responsible for source checks, approved refreshes, and failure triage.

## 1. What is automated

The ingestion application already contains the source registry, conditional HTTP checks,
checksums, immutable raw storage, validation, publication gates, and per-release reports.
Scheduling is deliberately thin:

| Job | Command | Frequency in `.github/workflows/source-checks.yml` | Effect |
|---|---|---|---|
| Due-source checks | `philfacilities-ingest source check --due` | Daily at 03:17 UTC | Appends `source.source_checks`; no data is downloaded or published. |
| Approved refresh | `scripts/refresh_approved_sources.sh` | Weekly on Sunday at 04:17 UTC, or manual dispatch | Re-runs only rights-cleared loaders; unchanged checksums are skipped. |

The check schedule is data-driven. Each check writes a `next_check_at` derived from the
source's declared update pattern, so a daily workflow does not re-probe every source every
day. Known access blocks and HTTP 304 responses are recorded without creating a fresh
incident on each run.

Blocked sources are **not** refreshed automatically:

- Official PSA PSGC workbook: blocked by a Cloudflare challenge.
- DepEd Machine-Ready Files: blocked by a human terms/download flow.
- DepEd EBEIS: the current source release is published for institution-level fields with personal fields withheld.
- DOH NHFR: the official site is blocked by Cloudflare, but a checksum-pinned preserved export is approved for enrichment and new-facility publication. Refresh only from a verified preserved artifact.
- DOH HFSRB licensed facilities: blocked by Cloudflare; licensing semantics and reuse terms are not established.
- CHED/TESDA: no verified bulk release or documented public API.

An operator must not enable an approved-refresh job for a source until its rights and
publication state permit it. A verified, publicly available source with no explicit
prohibition may qualify under `publicly_available_verified`; see
[`docs/data-policy.md`](../data-policy.md).
Never bypass a CAPTCHA, Cloudflare challenge, login, or agreement, and never accept an
agreement on another person's behalf.

## 2. One-time configuration

1. Apply the schema and load the initial data. See `06-ingestion-runbook.md`.
2. Create a database role that can read and write the `source`, `core`, `geo`, `school`,
   `health`, `quality`, `history`, and `stats` schemas. Prefer a dedicated scheduler role
   over a superuser.
3. Configure `PHILFACILITIES_DATABASE_URL` as a GitHub Actions repository or environment
   secret. Add `PHILFACILITIES_ALERT_WEBHOOK_URL` if a JSON alert webhook is available.
4. If raw files should go to S3-compatible storage, configure the `PHILFACILITIES_S3_*`
   settings as secrets and grant the runner network access to the bucket.
5. Run the workflow manually once with `refresh_approved=false` and inspect the
   `monitoring` output. Then run a manual refresh only after confirming the source rights
   state.

The workflow skips both jobs with a clear message when the database secret is absent. It
does not silently use a demo or local database.

## 3. Manual commands

```bash
# Probe every registered source and append evidence.
uv run philfacilities-ingest source check

# Run only checks whose next_check_at is due.
uv run philfacilities-ingest source check --due

# Force a check for selected sources while diagnosing.
uv run philfacilities-ingest source check --due --source psa-psgc --source doh-nhfr --force

# Inspect the latest check per dataset.
uv run philfacilities-ingest monitoring

# Refresh only rights-cleared sources (idempotent).
scripts/refresh_approved_sources.sh

# Confirm measured totals and release state.
uv run philfacilities-ingest status
```

`source check --due` exits `2` when a result needs operator action:
`request_failed`, `check_failed`, `schema_changed`, `source_error`, or `http_error`.
Access blocks (`access_blocked`, `not_found`) and `not_modified` remain recorded without
causing a per-run incident.

## 4. Cron or systemd alternative

If GitHub Actions is not used, run the same commands from a host with network and database
access.

```cron
# Daily due checks.
17 3 * * * cd /srv/philfacilities && /usr/bin/uv run philfacilities-ingest source check --due >> /var/log/philfacilities/checks.log 2>&1

# Weekly rights-cleared refresh.
17 4 * * 0 cd /srv/philfacilities && scripts/refresh_approved_sources.sh >> /var/log/philfacilities/refresh.log 2>&1
```

A systemd timer can wrap the same commands. Set `PHILFACILITIES_DATABASE_URL` in an
environment file with `0600` permissions; do not put credentials in the unit file. Route
stderr to the monitoring system and alert on a non-zero exit status other than the
documented `2` triage signal.

## 5. Failure handling

| Signal | Meaning | Action |
|---|---|---|
| `access_blocked` with HTTP 403 | Cloudflare, WAF, or authentication challenge | Record it; do not retry through a bypass. Use an authorized browser/FOI route and review terms before changing the gate. |
| `not_found` | Published link changed or was removed | Keep the last release and check whether the agency published a replacement. Do not invent a URL. |
| `schema_changed` | Parser required columns or signatures did not match | Inspect the preserved raw file and release report. Update the adapter and parser version; never coerce missing columns. |
| `source_error` / `request_failed` | Network, TLS, timeout, or malformed response | Rerun; confirm DNS/TLS and the source status page. A failed refresh does not replace the published release. |
| Validation rejects | Rows failed required checks | Inspect `quality.issues` and the report. Fix the parser or quarantine the release; do not relax a fatal check to increase acceptance. |
| `ingestion_failed` | The run stopped before publication | Re-run the idempotent loader. Existing published releases remain intact. |
| Alert webhook fails | The check result is still in the database | Use `monitoring` and the workflow exit status; fix the webhook separately. |

## 6. Verification and evidence

After a refresh, verify the public boundary:

```bash
uv run philfacilities-ingest status
uv run philfacilities-ingest monitoring
curl -fsS http://127.0.0.1:8010/healthz
curl -fsS http://127.0.0.1:8010/v1/statistics
curl -fsS http://127.0.0.1:8010/v1/sources
curl -fsS http://127.0.0.1:8010/v1/source-checks?limit=10
```

Then confirm:

- new releases have a SHA-256 checksum and a preserved raw object;
- blocked datasets remain read-gated and expose no public facilities;
- downloads and facility details apply the same publication gate;
- the previous published release remains when a new one fails validation.

Regenerate the measured reports after a material refresh:

```bash
uv run python scripts/generate_data_reports.py
```

## 7. Current limitations

- The workflow has not been observed running on GitHub because this checkout has no
  remote and no hosted database secret.
- The scheduler does not accept agreements, solve CAPTCHAs, or rotate credentials.
- There is no paging/on-call provider; the webhook and workflow exit status are the only
  alert channels.
- The approved-refresh job still relies on the source-specific loaders. Adding a new
  source requires a parser, validation, rights evidence, and tests before it can be added
  to the refresh script.
