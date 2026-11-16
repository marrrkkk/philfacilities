# 05 — Ingestion and ETL

**Status:** implemented for the sources that are accessible and have a documented publication decision. Official PSA, DepEd Machine-Ready, and DOH acquisition remain blocked. Verified, publicly available sources with no explicit prohibition may be published under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.  
**Current working database:** 228,291 canonical facilities, 99,352 public, 128,939 non-public (including 83,218 DepEd EBEIS rows), 121,651 with a current location, 0 synthetic.

The ingestion system is a first-class product component. It is reproducible, observable, source-aware, and safe to rerun. Every pipeline follows:

`discover → acquire → preserve → parse → validate → normalize → resolve → publish gate → report`

A failed download, schema change, or validation failure must never replace the last good public release.

## 1. Implemented adapter contract

Connectors live under `apps/ingest/philfacilities_ingest/sources/`. The shared pieces are:

- `acquisition.py` — bounded HTTP acquisition, conditional requests, retries/backoff, signature and MIME checks.
- `storage.py` — content-addressed immutable raw store with SHA-256; filesystem and S3-compatible backends.
- `contracts.py` — typed parse/normalize contract used by the pipelines.
- `pipeline.py` — release creation/resume, validation issues, source records, canonical facility linking, publication gate, run reports.
- `registry.py` — source keys, official URLs, access method, check functions.
- `bettergov.py`, `bettergov_stats.py`, `philhealth.py`, `psgc.py`, `deped.py`, `deped_ebeis.py`, `doh.py` — source-specific acquisition and parsing.
- `matching.py` — deterministic review-candidate generation; never auto-merges.

The pipeline supports public JSON APIs, public file downloads, PDF extraction, GeoParquet, HTML result sets, and human-assisted file import through `ingest-file`.

## 2. Source-by-source implementation

### 2.1 BetterGov PSGC Q2 2024 mirror

```bash
uv run philfacilities-ingest load-psgc-bettergov
```

- Reads the documented BetterGov classification collections.
- Preserves each JSON payload as one immutable geographic release (`PSGC-Q2-2024-BETTERGOV`).
- Loads 43,760 regions, provinces, HUC/ICC cities, municipalities, and barangays.
- HUC/ICC cities returned in the `provinces` collection are normalized to municipality level with the region as parent.
- PSGC codes are stored as strings; leading zeros are preserved.
- Reference date is 2024-06-30. The dataset is labelled as a supplementary BetterGov mirror, **not** the latest official PSA release.
- If the endpoint or schema changes, the command fails closed. Unknown levels are not coerced into a guessed geography.

The official PSA workbook is still HTTP 403 behind Cloudflare, and the PSA classification collection endpoints require a token. No bypass is attempted; the official source remains blocked under M1-01.

### 2.2 PSA 2024 Census population via BetterGov

```bash
uv run philfacilities-ingest load-population
uv run philfacilities-ingest load-population --dataset 97ba6406111204e138a4
```

- Reads saved PSA OpenSTAT snapshots from the BetterGov Philippine Data Explorer; it does not query live PSA OpenSTAT.
- Discovers and loads 18 regional tables.
- Fetches dataset metadata and paginates the `Geographic Location` and `Parameter` dictionaries, then queries bounded chunks of at most 1,000 geography codes.
- Preserves the complete metadata, dictionaries, query rows, PSA table URL, BetterGov release identifier, and retrieval timestamp as one immutable JSON release per region.
- Stores one `stats.population_observations` row per source point; missing values stay `NULL`, and source status codes are retained in the source record.
- Current coverage: 134,748 observations.
- Values are persons or households as labelled. They are not facility capacity, service coverage, or a claim that a facility serves that population.
- Rights: BetterGov original material is CC BY-SA 4.0; PSA remains authoritative. This is a terms-based engineering decision, not a legal opinion.

Public endpoint: `GET /v1/population`, limited to observations whose dataset and release pass the publication gate, with source URL, release, indicator, unit, and attribution.

### 2.3 PhilHealth accredited providers

```bash
uv run philfacilities-ingest load-philhealth
uv run philfacilities-ingest load-philhealth --file HOSP_093026.pdf
```

- Discovers the public accredited-provider index and parses category-specific PDF links, including four links inside malformed, unclosed HTML anchors.
- The index exposes 27 links. 26 categories are published; the Antenatal release was re-ingested with the corrected parser after its first 6,562-row parse counted the two-up PDF's expiry/sector annex as provider rows (3,221 rows, ending at page 120); `MCP_073126.pdf` is linked but returns HTTP 404 and is recorded as a broken source.
- Preserves each PDF with a SHA-256 checksum and page/row references.
- Uses the category-independent identity key `philhealth:<normalized name>:<municipality>` so one provider can carry multiple benefit-package accreditations without duplicate facilities.
- Current coverage: 28,207 accreditations across 26 categories, linked to 13,546 facilities (13,545 public).
- A 404, non-PDF response, or signature failure is recorded as a source check and does not overwrite the previous release.
- Raw PDFs and parsed rows are published only because the dataset's rights state is `approved_with_attribution`; attribution remains on the dataset.

### 2.4 HOT/OSM health and education extracts

```bash
uv run philfacilities-ingest load-osm --domain health
uv run philfacilities-ingest load-osm --domain education
```

- Downloads the BetterGov-hosted HOT/OSM GeoParquet extracts.
- Retains the full Parquet file, including unnamed features.
- Only named features become facility candidates.
- Coordinates are the bounding-box centre, recorded as `map_geocoded` with method `openstreetmap_bbox_center`. They are **not** official, GPS, verified, or building-level locations.
- `record_status` is `unknown`: a mapped feature is not evidence that a facility is open.
- Current coverage: 17,410 health and 52,824 education linked facilities.
- Rights: ODbL, `approved_with_attribution`. Attribution is stored on the dataset and must remain visible in derived products.
- These records are explicitly labelled as crowd-sourced, non-official map features.
- Open quality issues (`duplicate_osm_id`, `missing_facility_name`) remain visible instead of being silently merged or deleted.

### 2.5 DepEd EBEIS regional result sets (institution-level publication approved)

```bash
uv run philfacilities-ingest load-deped-ebeis --region ncr
```

- Fetches the public EBEIS result set for a verified region key.
- The first page establishes the result count. Remaining pages are fetched by a
  small bounded thread pool (4 workers) with one shared 0.4-second start-spacing
  pacer, so the form is not hit in bursts. Pages are still consumed in order:
  a changed table header stops acquisition before any later chunk is requested.
- `--region all` acquires all 19 verified region keys; the 16 November 2026 pass stored 83,218 school rows.
- The result set includes school-head personal names. Those names stay in the private raw store and are not published.
- The dataset is `approved_with_attribution`. The re-ingested 15 November 2026 release is `published` for institution-level fields; the earlier `restricted_non_redistributable` release is retained. Canonical facility rows remain `internal` pending field-level mapping and privacy review.
- Do not add personal fields to a public export. A field-level privacy review is required for any new field.

### 2.6 Public directories with no explicit licence

- The National Library of the Philippines public-library directory, National Museum site-museum directory, PHLPost locator, and BIR office list are public sources with recorded publication decisions.
- Institutional fields are published with attribution; personal and unnecessary contact fields are withheld.
- A source with no explicit licence may be published under `publicly_available_verified` only after the exact release is verified, no explicit prohibition is found, and the evidence record is complete. See `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.

### 2.7 Official DepEd Machine-Ready Files (blocked)

- The Machine-Ready Files page returned HTTP 403 and requires a human download/terms flow.
- No official enrollment, facilities, personnel, ICT, or WASH file has been acquired.
- The adapters remain fixture-tested and must not be presented as real DepEd coverage.

### 2.8 DOH NHFR / HFSRB (blocked)

- `https://nhfr.doh.gov.ph/VActivefacilitiesList` returned HTTP 403 behind Cloudflare.
- No DOH file has been acquired through an automated route.
- A normal browser download or permitted FOI route may be imported by an authorized operator, but a signed Data Release and Use Agreement and a publication decision are required first.
- The source gate must not be weakened to make a DOH file appear.

### 2.9 CHED, TESDA, hazard, and additional agencies

- CHED HEIDA directory is reachable but no verified bulk export or documented public API has been acquired.
- TESDA TVI is reachable but the monitor records an access challenge; no verified provider-level bulk release has been acquired.
- GeoRiskPH has a local TLS validation failure, PHIVOLCS maps portal has a TLS failure, and DENR-MGB returns HTTP 403. No hazard layer has been acquired.
- DILG, BFP, PNP, BJMP, DSWD, DPWH, NAMRIA, NHA, LWUA, DOTr/LTFRB, DICT, and Open Data Philippines were probed for discovery. No facility release has been verified or published from those probes.
- A future verified, publicly available release may be published under the policy, but access-controlled or agreement-bound sources remain blocked.
- None of these is a dependency of the current release.

## 3. Raw and staging storage

Raw layer:

- exact agency file/response;
- source URL and retrieval timestamp;
- HTTP metadata when available;
- source publication/reference date;
- SHA-256;
- terms/access classification;
- parser version and release label.

Layout: `var/raw/<agency>/<dataset>/<release>/<checksum>-<filename>`, or the configured S3-compatible store. A previous release remains readable through the same raw-store abstraction, including when only an `s3://` URI exists.

Staging/canonical layers:

- source-specific records with original values and row/page references;
- canonical facilities and source links;
- date-bounded domain observations;
- geography references;
- attribute assertions;
- quality issues and change events.

No canonical merge happens during parsing. Ambiguous records remain separate until a reviewer accepts and explicitly merges a candidate.

## 4. Idempotency and atomic publication

- A release is identified by dataset + source release hash/label.
- An unchanged checksum is skipped as a duplicate; counts do not change.
- A changed file becomes a new immutable release; previous releases are retained.
- A failed release stays unpublished; the previous published release remains public. A new failed release is marked `quarantined`; a previously published release keeps its `published` state so a failed re-ingestion cannot hide working data.
- Re-running a killed command resumes the same release instead of creating a duplicate.
- Publication is evaluated from the dataset and release rights state after validation, under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.
- `compare-releases` compares two retained releases by stable source-record key, payload hash, and facility link without mutating either release.

## 5. Validation checks

### File and schema

- expected extension, PDF signature, GeoParquet/JSON/HTML shape;
- expected required fields and header aliases;
- no silent coercion of missing columns;
- row-count anomalies and parse failures fail closed.

### Identity

- required source IDs/names;
- duplicate source rows are retained as issues, not silently rewritten;
- same source ID with conflicting values is surfaced;
- source identifiers and original values are preserved.

### Geography

- PSGC codes exist in the selected release when a mapping is claimed;
- parent-child hierarchy is valid;
- leading zeros are preserved;
- unmatched geography remains `NULL` rather than guessed.

### Coordinates

- latitude/longitude ranges;
- Philippines bounding-box plausibility (flag, do not silently delete);
- coordinate precision/method preserved;
- OSM bbox centres are `map_geocoded`, never `gps_verified`;
- missing coordinates remain missing.

### Domain

- bed counts nonnegative and source semantics documented;
- accreditation expiry parsed with source locale;
- enrollment counts nonnegative; missing differs from zero;
- reference school year retained;
- population values retain indicator, unit, reference date, and source status.

## 6. Entity resolution

Deterministic matching only:

- exact source IDs;
- exact normalized name + current PSGC unit + compatible type/subtype + different source agency;
- explicit reviewer acceptance before any merge.

Implementation: `philfacilities_ingest.matching` writes `quality.match_candidates` rows with a SHA-256 `candidate_key`. It does not merge.

```bash
uv run philfacilities-ingest match-candidates-generate
uv run philfacilities-ingest match-candidates --status pending
uv run philfacilities-ingest match-candidates-accept <candidate-id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-reject <candidate-id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-merge <candidate-id> --reviewer <name> --note "..."
```

A rejected candidate is retained, so the same record/candidate pair is not queued again for the same algorithm version. A merge is transactional, moves source evidence, retires the duplicate as a `merged` tombstone, and writes a change event. Reviewer names and notes are not exposed publicly.

### Field-level fusion

Merging identities is not enough: sources often disagree about the same
attribute. `philfacilities_ingest.fusion` materialises one derived value per
facility/attribute plus every competing value and its provenance in
`core.facility_attribute_fusions`. Source records are never rewritten.

- Empty/missing claims are ignored rather than treated as zero or false.
- Identical normalized claims become `agreed`.
- Disagreeing claims become `conflict`; the preferred claim is retained as the
  derived value and all alternatives remain in the `alternatives` JSON payload.
- A single-source claim remains `single_source` and is not presented as
  cross-source agreement.
- `apply_fusions` only writes agreed/single-source values for the safe fields
  `facility_subtype`, `ownership`, `ownership_type`, `operator_type`,
  `public_access_class` and `record_status`. Names and other curatorial fields
  are not overwritten.

```bash
uv run philfacilities-ingest fuse-attributes            # facilities linked to >1 source
uv run philfacilities-ingest fuse-attributes --all      # include single-source facilities
uv run philfacilities-ingest apply-fusions --dry-run
uv run philfacilities-ingest apply-fusions
uv run philfacilities-ingest fusion-report --json
```

`auto-merge-duplicates` consolidates only candidates that already met the exact
normalized-name + compatible-type test and either share the same PSGC with an
exact address (`confidence >= 0.900`) or are geo-name matches at `<=25 m` with
an exact name and official-side evidence. Candidates between 25 m and 50 m
remain pending for human review; the command never merges them automatically.

```bash
uv run philfacilities-ingest auto-merge-duplicates --dry-run
uv run philfacilities-ingest auto-merge-duplicates --apply
```

## 7. Scheduling and source freshness

The schedule is data-driven. Every source check writes `next_check_at`; `check-due-sources` runs only sources that are due.

- Daily: due-source checks through `.github/workflows/source-checks.yml` or an equivalent cron/systemd timer.
- Monthly: `discover-sources` probes discovery-only official endpoints and uploads JSON evidence; it does not register a dataset, accept terms, download bulk files, or publish.
- Weekly/manual: `scripts/refresh_approved_sources.sh` refreshes the sources enumerated in that script (currently BetterGov PSGC, PSA population, PhilHealth, and OSM health/education).
- Blocked and internal-only sources are never refreshed automatically.
- A successful check does not publish data. It only appends monitoring evidence. Publication still requires a new release, successful parsing/validation, and a satisfied rights gate.
- No hosted scheduled run or alert channel has been observed; the workflow skips cleanly when `PHILFACILITIES_DATABASE_URL` is absent.

The operator procedure, failure semantics, and triage steps are in [`docs/reports/06-ingestion-runbook.md`](reports/06-ingestion-runbook.md) and [`docs/operations/source-monitoring-runbook.md`](operations/source-monitoring-runbook.md).

## 8. Ingestion run report

Every run records:

- source/dataset/release;
- discovery URL;
- retrieved time;
- checksum;
- source publication/reference date;
- parser and schema version;
- input/parsed/accepted/rejected row counts;
- duplicate source rows;
- null/missing-field rates;
- PSGC match rate where applicable;
- coordinate precision distribution;
- candidate/unresolved facility matches;
- validation failures;
- terms/publication gate;
- publish result.

Reports are written under `var/reports/` and summarized by `philfacilities-ingest status` and `/v1/quality/summary`.

## 9. Monitoring and alerts

`check-sources`, `check-due-sources`, and the append-only `source.source_checks` ledger record:

- access state (`ok`, `not_modified`, `access_blocked`, `not_found`, `schema_changed`, `request_failed`);
- HTTP status and observed timestamp;
- next check time;
- actionable failure status.

`/v1/source-checks` exposes the ledger; `/v1/monitoring` exposes the latest check per dataset. `check-due-sources` exits `2` for actionable failures and can POST a JSON alert when `PHILFACILITIES_ALERT_WEBHOOK_URL` is configured. No monitoring provider, paging rotation, or production alert destination is configured in this checkout.

Alert conditions include source unavailability, a changed file URL, checksum changes without a release label, schema drift, implausible row-count changes, parser success-rate drops, PSGC match-rate regressions, coordinate-quality regressions, and an unsatisfied publication gate.

A failed ingestion must not silently leave the public dataset looking current. The last successful release and check date remain visible.

`compare-releases` is the read-only historical comparison for operators. It reports source records added, removed, retained, and changed-payload, plus facility-link additions and removals, for two releases of one dataset. `discover-sources` records reachability for sources that are not yet registered datasets; its output is evidence for the source register, not a publication decision.
