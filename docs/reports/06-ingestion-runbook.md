# 06 — Ingestion and Recovery Runbook

**Status:** operational for the sources listed below.  
**Audience:** an operator with access to the repository, PostgreSQL/PostGIS, and the configured raw store.

This runbook describes what each connector actually does, how to run it, how to update a source, and how to recover from a failed acquisition or ingestion. It does not authorize publication of any source. Rights gates are enforced in code and described in `05-source-rights-report.md`.

## 1. Prerequisites

```bash
docker compose -f infra/compose.yaml up -d db
uv sync --locked
uv run alembic upgrade head
```

The default database is `postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities`. Override it with `PHILFACILITIES_DATABASE_URL`. Raw files are stored under `var/raw/` unless `PHILFACILITIES_RAW_STORE`, `PHILFACILITIES_S3_*`, or equivalent settings point at an S3-compatible store. Ingestion reports are written to `var/reports/`.

Check the CLI surface:

```bash
uv run philfacilities-ingest --help
```

## 2. Command reference

| Command | Purpose | Touches public data? |
|---|---|---|
| `check-sources [--source KEY]` | Probe registered source endpoints and append monitoring evidence. | No |
| `check-due-sources [--force]` | Run only checks whose recorded `next_check_at` is due; exit 2 on actionable failure. | No |
| `monitoring` | Print the latest check per dataset. | No |
| `compare-releases <dataset> [--from LABEL --to LABEL] [--json]` | Compare two retained releases by source-record key and facility link. Read-only. | No |
| `discover-sources [--target KEY] [--json] [--output PATH]` | Probe discovery-only official endpoints and write evidence. Never registers or publishes a dataset. | No |
| `load-psgc-bettergov` | Acquire and load the BetterGov Q2 2024 PSGC mirror as supplementary geography. | Geography only |
| `load-philhealth [--file NAME] [--reprocess]` | Acquire every current PhilHealth provider-category PDF, or named files, and ingest them. `--reprocess` reparses an already-published release after an explicit parser repair. | Yes, if the source gate permits |
| `load-osm [--domain health\|education]` | Acquire HOT/OSM GeoParquet extracts and ingest named features. | Yes, if the source gate permits |
| `load-population [--dataset ID]` | Acquire saved PSA 2024 Census population snapshots from BetterGov and store statistical observations. | Yes, observations are published with attribution |
| `load-deped-ebeis [--region ncr]` | Acquire a public EBEIS result set and store it `internal_only`. | No |
| `purge-synthetic` | Remove synthetic demonstration records and their derived rows. | Removes synthetic rows only |
| `load-real` | Run the documented real-data sequence end to end. | Yes, subject to gates |
| `status` | Show current database counts and source status. | No |

`load-real` supports `--skip-osm`, `--skip-philhealth`, `--skip-population`, `--skip-deped`, and `--purge/--no-purge`. Use the individual commands when diagnosing a failure; use `load-real` for a fresh environment.

## 3. Source-specific procedures

### 3.1 PSA PSGC (official)

- Official workbook: `https://psa.gov.ph/system/files/scd/PSGC-3Q-2026-Publication-Datafile.xlsx`
- Observed access: HTTP 403 behind Cloudflare on 14 and 15 November 2026.
- No connector publishes an official PSA workbook. Do not bypass the challenge.
- Human-assisted route: an authorized operator may download the workbook in a normal browser, place it in the raw store, and use the existing PSGC workbook adapter through `ingest-file` if the source gate is changed to permit it. A completed terms review is still required before publication.

### 3.2 BetterGov PSGC mirror (supplementary)

```bash
uv run philfacilities-ingest load-psgc-bettergov
```

- Fetches the documented BetterGov classification collections.
- Stores the JSON payload as an immutable release.
- Loads regions, provinces, HUC/ICC cities, municipalities, and barangays.
- HUC/ICC cities in the `provinces` collection are normalized to municipality level with the region as parent.
- Preserves PSGC codes as strings and records the Q2 2024 reference period.
- This is **not** the latest official PSA release. It is labelled as a BetterGov mirror in the API and reports.

If the endpoint changes, the command fails closed before loading. Record the new schema and update the parser; do not coerce unknown levels into a guessed geography.

### 3.3 PhilHealth accredited providers

```bash
# Inventory and load every current catalogue file
uv run philfacilities-ingest load-philhealth

# Retry one file
uv run philfacilities-ingest load-philhealth --file HOSP_093026.pdf

# Repair an already-published release with the current parser
uv run philfacilities-ingest load-philhealth --file GAMOT.pdf --reprocess
```

- Discovers the public accredited-provider index and parses category-specific PDF links.
- Preserves each PDF with a SHA-256 checksum and page/row references.
- Uses the category-independent identity key `philhealth:<normalized name>:<municipality>` so the same provider can carry multiple benefit-package accreditations without duplicate facilities.
- A 404, non-PDF response, or signature failure is recorded as a source check and does not overwrite the previous release.
- The index exposes 27 PDF links. Four links (`EMCB-ANTE`, `EMCB-LAB`, `EMCB-PPARTUM`, `EMCB-TVU`) sit inside malformed, unclosed HTML anchors; the catalogue parser retains them instead of silently dropping the categories. `MCP_073126.pdf` is linked but returned HTTP 404 and is recorded as a broken source.
- Retry a transient network failure by rerunning the same command. A release with the same checksum is resumed in place; a published checksum is skipped as a duplicate.
- `--reprocess` is only for an explicit parser repair. Before using it, confirm the live file still matches the release `sha256`; a changed file is a new release, not a reprocess. The command re-keys existing records by their preserved `page:row` reference, keeps record IDs and links, aborts if the parser no longer accounts for a stored row, and skips unchanged linked rows so canonical attributes are not churned. Newly recovered rows are added and linked. Verify `row_count_parsed = count(source.records)` and review the run report afterward. See `docs/operations/evidence/2026-11-15-philhealth-record-key-repair/` for a worked repair.

### 3.4 HOT/OSM health and education extracts

```bash
uv run philfacilities-ingest load-osm --domain health
uv run philfacilities-ingest load-osm --domain education
```

- Downloads the BetterGov-hosted HOT/OSM GeoParquet extract.
- Retains the full Parquet file, including unnamed features.
- Only named features become facility candidates.
- Coordinates are the bounding-box centre, recorded as `map_geocoded` with method `openstreetmap_bbox_center`. They are **not** official, GPS, verified, or building-level locations.
- `record_status` is `unknown`: a mapped feature is not evidence that a facility is open.
- Rights: ODbL, `approved_with_attribution`. Attribution is stored on the dataset and must remain visible in derived products.
- These records are explicitly labelled as a crowd-sourced, non-official registry.

Large education extracts take materially longer than health. Run them in the foreground or a supervised background job; do not start two writers against the same release.

### 3.5 PSA 2024 Census population (via BetterGov Statistics API)

```bash
# All 18 regional tables discovered as complete snapshots
uv run philfacilities-ingest load-population

# One table while diagnosing a failure
uv run philfacilities-ingest load-population --dataset 97ba6406111204e138a4
```

- Reads saved PSA OpenSTAT snapshots from the BetterGov Philippine Data Explorer; it never queries live PSA OpenSTAT.
- Fetches the dataset metadata, then paginates the `Geographic Location` and `Parameter` dictionaries, then queries bounded chunks of at most 1,000 geography codes (well under the API's 5,000-point and 64 KiB limits).
- Preserves the complete metadata, dictionaries, query rows, PSA table URL, BetterGov release identifier, and retrieval timestamp as one immutable JSON release per region.
- Stores one `stats.population_observations` row per source point. Missing values stay `NULL`; source status codes are retained in the source record.
- Values are persons or households as labelled. They are **not** facility capacity, service coverage, or a claim that a facility serves that population.
- The public endpoint is `GET /v1/population`. It exposes only observations whose dataset and release pass the publication gate and includes the PSA source URL, release, indicator, unit, and attribution.
- Rights: BetterGov's original material is CC BY-SA 4.0; PSA remains authoritative. The portal states its preview does not itself establish redistribution rights, so the register records this as a terms-based engineering decision, not a legal opinion.
- If a regional table is incomplete or its release changes, rerun the command. The same checksum is skipped; a changed snapshot is preserved as a new release and the previous published release remains intact.

### 3.6 DepEd EBEIS masterlist (internal only)

```bash
uv run philfacilities-ingest load-deped-ebeis --region ncr
```

- Fetches the public EBEIS result set for a verified region key.
- Stores the aggregated HTML payload and normalizes school rows.
- The result set includes school-head personal names and has no explicit reuse licence.
- The dataset is `restricted_non_redistributable` / `internal_only`. Public endpoints, downloads, source evidence, and statistics exclude it.
- Do not add the adapter output to a public export without a documented rights change and a privacy review.

The official DepEd Machine-Ready Files remain blocked by an HTTP 403 / human terms flow. No official enrollment, facilities, personnel, ICT, or WASH file has been acquired.

### 3.7 DOH NHFR / HFSRB (blocked)

- `https://nhfr.doh.gov.ph/VActivefacilitiesList` returned HTTP 403 behind Cloudflare.
- No DOH file has been acquired through an automated route.
- A normal browser download or permitted FOI route may be imported by an authorized operator, but a signed Data Release and Use Agreement and a publication decision are required first.
- Do not weaken the source gate to make a DOH file appear.

### 3.8 CHED and TESDA (not acquired)

- CHED HEIDA and the public HEI directory were investigated; the directory is reachable (HTTP 200) but no complete bulk export, documented public API, or reuse terms were verified.
- TESDA TVI is reachable (HTTP 200) but the source monitor classifies the response as an access challenge (`access_blocked`); no provider-level bulk export or reuse terms were verified.
- Neither source is a dependency of the current release, and neither is refreshed by the approved-source script.

### 3.9 Release comparison and recurring discovery

```bash
# Compare the two most recent retained releases for a dataset
uv run philfacilities-ingest compare-releases philhealth-gamot

# Pin both sides of the comparison and emit JSON
uv run philfacilities-ingest compare-releases philhealth-gamot \
  --from GAMOT_093026 --to GAMOT_123126 --json

# Probe discovery-only sources without registering or publishing them
uv run philfacilities-ingest discover-sources --target open-data-ph
uv run philfacilities-ingest discover-sources \
  --output var/reports/discovery-$(date -u +%Y%m%dT%H%M%SZ).json
```

- `compare-releases` matches retained source records by `source_record_key` and compares their raw-payload hashes and facility links. It reports added, removed, retained, and changed-payload counts plus bounded samples. It never mutates a release, facility, or link.
- If no labels are supplied, the two most recent releases by retrieval time are compared. Supplying only one label is rejected rather than guessing the other side.
- `discover-sources` probes the configured discovery-only targets (DOH HFSRB, PSA classification API, TESDA assessment centers, GeoRiskPH/HazardHunterPH, PHIVOLCS, PAGASA, DENR-MGB, Open Data Philippines, and additional agency homepages). It records HTTP/blocker/TLS results and never accepts terms, registers a dataset, downloads a bulk file, or bypasses an access control.
- The monthly workflow runs `discover-sources` and uploads the JSON artifact. A registered source is still monitored through `check-due-sources`; discovery probes are not a substitute for that ledger.

## 4. What happens during ingestion

1. The source adapter validates the response signature/MIME type.
2. The raw file is preserved with a content-addressed name and SHA-256 checksum.
3. A source check records the HTTP result.
4. The release is created or resumed. Existing releases are never overwritten.
5. The parser produces normalized rows and validation issues.
6. Accepted rows are written to source records, facilities, domain tables, locations, and source links.
7. The publication gate is evaluated from the dataset and release rights state.
8. The run and a JSON/Markdown report are written to `var/reports/`.
9. The previous published release remains intact if parsing or validation fails.

## 5. Failure recovery

| Symptom | Action |
|---|---|
| HTTP 403 / Cloudflare / CAPTCHA | Record the blocker with `check-sources`. Do not retry through a bypass. Use a human-assisted route only after authorization. |
| HTTP 404 on one PhilHealth category | Keep the check evidence; the other categories continue. Do not invent a replacement URL. |
| DNS / connection reset | Rerun the command. The same checksum is resumed, not duplicated. |
| Schema drift / parse error | Inspect the preserved raw file and the report. Update the adapter and bump its parser version. Do not coerce missing columns. |
| Validation rejects | Inspect `quality.issues` and the report. Fix the parser or quarantine the release. Never relax a fatal check merely to increase acceptance. |
| New release fails parse or validation | The new release is set to `quarantined`; the previous published release remains `published` and keeps serving the API. Inspect the run report and `quality.issues`, correct the parser/source, and ingest a new release. Do not delete the failed release or force it public. |
| Duplicate source row | The pipeline keeps the first row and records `duplicate_source_row`; verify whether the source file genuinely repeats a row. |
| Parser key collision / missing rows | Compare `row_count_parsed` with `count(source.records)` for the release. If the parser key omitted a row discriminator, bump the parser version, add a regression test, and rerun the named file with `--reprocess`. Confirm that record IDs and links survive, that no stored row is orphaned, and that no duplicate quality issues were created. Do not delete and re-ingest a published release to hide the discrepancy. |
| Process killed mid-run | Rerun the same command. The release is set back to `processing` and its records are updated in place; a failed release is not published. |
| Bulk export HTTP 500 / bind-parameter error | The loader chunks facility-ID lookups below PostgreSQL's bind-parameter limit. Verify the running API includes the chunking fix and that the export is not timing out at a proxy; the 83,769-facility CSV is about 31 MB. |
| Wrong publication state | Correct the dataset/release rights evidence first. Do not update `core.facilities.publication_status` by hand to bypass the gate. |

## 6. Verification after an update

```bash
uv run philfacilities-ingest status
uv run philfacilities-ingest monitoring
uv run pytest
curl -s http://127.0.0.1:8010/v1/statistics | jq
curl -s http://127.0.0.1:8010/v1/sources | jq
```

Regenerate the measured reports:

```bash
uv run python scripts/generate_data_reports.py
```

Then verify the public boundary:

- `/v1/facilities` must not return records linked only to blocked or internal-only sources.
- `/v1/downloads/facilities.csv` and `.parquet` must apply the same filter.
- `/v1/facilities/{id}/sources` must omit non-public source evidence.
- The web directory and map must show the real record counts and the current caveats.

## 7. Scheduling and alerting

The check schedule is data-driven: every successful or failed check writes a
`next_check_at` derived from the source's declared update pattern. Use
`check-due-sources` from a cron/systemd timer or the deployment scheduler. It
does not re-check every source on every run.

```cron
# Example only: run every hour; the command decides which sources are due.
17 * * * * cd /srv/philfacilities && /usr/bin/uv run philfacilities-ingest check-due-sources >> /var/log/philfacilities/checks.log 2>&1
```

The command exits `2` when a check needs operator action (`request_failed`,
`check_failed`, `schema_changed`, `source_error`, or `http_error`). Known access
blocks (`access_blocked`, `not_found`) and HTTP 304 responses remain recorded in
the ledger without generating a fresh incident on every run.

Set `PHILFACILITIES_ALERT_WEBHOOK_URL` to receive a JSON POST containing the
command, timestamp, and actionable failures. No alert channel is configured by
default; the exit status is always available to the scheduler.

| Source | Suggested check |
|---|---|
| PSA PSGC | weekly |
| DepEd | monthly |
| DOH NHFR | weekly |
| PhilHealth | weekly |
| BetterGov PSGC / PSA population | weekly |
| OSM health/education | monthly |
| CHED / TESDA | monthly discovery only |

These are monitoring suggestions, not claims about agency release schedules. A successful check does not publish data; it only appends evidence. Publication still requires a new release, a successful parse/validation, and a satisfied rights gate.

## 8. Evidence locations

- Source access evidence: `docs/operations/evidence/2026-11-15-source-access/`
- Ingestion reports: `var/reports/`
- Preservation layout: `var/raw/<agency>/<dataset>/<release>/<checksum>-<filename>`
- Database monitoring: `source.source_checks`, `source.ingestion_runs`
- Generated required reports: `docs/reports/`
