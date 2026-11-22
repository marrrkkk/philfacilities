# Ingestion

> **Implementation** — `apps/ingest/philfacilities_ingest/`
> **Authority for source metadata** — `sources/registry_data.py` + `sources/catalog.py`
> **Authority for publication** — [Data policy](data-policy.md)
> **See also** — [Adding a source](adding-a-source.md) · [Data model](data-model.md) · [Sources](sources.md)

Ingestion is a first-class product component. It is reproducible, observable, source-aware, and safe to rerun. A failed download, schema change, or validation failure must never replace the last good public release.

```text
discover → acquire → preserve → parse → validate → normalize
        → resolve → publication gate → report
```

## 1. Design rules

- **Acquisition and parsing are separate.** A connector owns discovery and acquisition; an adapter owns `parse → validate → normalize`. An adapter never downloads and never invents a missing value.
- **The catalogue is data-driven.** A source is declared once in `sources/registry_data.py` and wired once in `sources/catalog.py`. The CLI, runner, checks, and scheduled jobs read that catalogue. Do not add a `load-<source>` command or a source-specific branch to `pipeline/`.
- **Raw source truth is immutable.** Every acquired artifact is preserved with a SHA-256 before parsing. Original column names and values stay in `source.records.raw_payload`.
- **Validation fails closed.** Missing required columns, unreadable files, and shape changes raise; they do not produce a guessed release. An empty parse or a release below its acceptance floor is quarantined before canonical writes.
- **One writer per dataset.** A session-level PostgreSQL advisory lock covers the whole preserve/parse/apply/report lifecycle; a second worker fails fast instead of interleaving canonical writes.
- **Internal evidence cannot rewrite a public profile.** Assertions and child rows from an internal-only release are stored for audit but read-gated; they may not change a public facility's canonical identity, current location, profiles, or publication state.
- **Publication is not an ingestion side effect.** A record becomes public only when the dataset rights state, dataset gate, and release gate all pass.
- **Ambiguity is preserved.** Matching produces review candidates; it never merges on name similarity. Conflicting field claims are retained, not overwritten.

## 2. Module map

| Module | Responsibility |
|---|---|
| `acquisition.py` | Bounded HTTP requests, conditional headers, retries/backoff, response classification, signature checks, source-check ledger |
| `storage.py` | Content-addressed raw store; filesystem and S3-compatible backends |
| `contracts.py` | `ReleaseSpec`, `ParsedRelease`, `FacilityCandidate`, `ValidationResult`, adapter protocol |
| `sources/definitions.py` | `SourceDefinition`, `AgencyRef`, `DatasetRef`, `RightsDecision`, `AccessSpec`, `CheckSpec` |
| `sources/registry_data.py` | `REAL_SOURCES`: keys, URLs, access/rights metadata, rights basis, attribution |
| `sources/registry.py` | Publication decisions, source checks, acquisition helpers; re-exports registry data |
| `sources/catalog.py` | `SOURCES` and `CONNECTORS`: the single acquisition catalogue |
| `sources/connectors/` | Reusable acquisition shapes: single file, PhilHealth index, OSM Parquet/PBF, EBEIS paging, geography/population |
| `sources/<source>.py` | Source-specific parsing, validation, normalization |
| `source_runner.py` | Generic `run_source`, `validate_source`, `run_selection` |
| `replay.py` | Manifest-driven replay of preserved raw releases through current parsers |
| `pipeline/release.py` | Source/release lifecycle, duplicate detection, run reports |
| `pipeline/locking.py` | Per-dataset PostgreSQL advisory lock |
| `pipeline/staging.py` | Source-record staging and row-count anomaly checks |
| `pipeline/canonical.py` | Canonical facility writes, source links, locations, assertions, quality issues |
| `pipeline/geography.py` | PSGC releases and administrative units |
| `osm_boundaries.py`, `psgc_spatial_fill.py` | OSM boundary preservation and point-in-polygon PSGC fill/refinement |
| `pipeline/stats.py` | Population observations |
| `pipeline/runner.py` | The single facility-release orchestration path |
| `validators.py` | Shared coordinate, PSGC-shape, required-field, duplicate-key checks |
| `identity.py`, `matching.py`, `aggregation.py` | Name folding, deterministic candidates, whole-registry clustering |
| `fusion.py` | Attribute assertions/fusions and safe allowlisted application |
| `release_rollback.py` | Pre-release snapshots and conservative rollback |
| `cli.py`, `commands/` | Typer apps, ordered command registration, command bodies by domain |

## 3. The release lifecycle

1. `SourceDefinition.release_spec()` combines reviewed registry metadata with the acquired artifact.
2. The runner takes the dataset's advisory lock, then the raw store writes `var/raw/<agency>/<dataset>/<release>/<sha256-prefix>-<filename>` plus a manifest (or the S3 equivalent). Writes are atomic (temporary file, fsync, rename).
3. The release row is created or reused; `(dataset_id, sha256)` is unique.
4. An unchanged already-published checksum returns `skipped_duplicate`. A new `parser_version` triggers automatic reprocessing; a failed reprocess is retried rather than skipped even without `--reprocess`.
5. The adapter parses, validates, and normalizes. A parse/validation failure, empty parse, or acceptance below the floor marks the release `failed` and quarantines it; the previous published release stays public.
6. Staging writes source records with row/page references.
7. Canonical writes create or link facilities, locations, observations, assertions, and quality issues. Write-side gating prevents an internal-only release from rewriting an already public facility.
8. The publication gate is evaluated from dataset and release rights state, not file reachability.
9. The run report records counts, issues, checksum, parser/schema versions, acceptance/rejection rates, and the gate result.

Re-running a killed command resumes the same release rather than creating a duplicate. Use `--reprocess` only when a parser, schema, or key-scheme change requires rebuilding derived rows from the preserved artifact; a parser-version change does this automatically.

## 4. Commands

```bash
# Catalogue and status
uv run philfacilities-ingest source list
uv run philfacilities-ingest status
uv run philfacilities-ingest monitoring

# Acquire and load
uv run philfacilities-ingest source run philhealth
uv run philfacilities-ingest source run --group approved
uv run philfacilities-ingest source run deped-ebeis --region ncr

# Validate without canonical writes
uv run philfacilities-ingest source validate philhealth --fixture var/raw/.../file.pdf
uv run philfacilities-ingest source run philhealth --dry-run

# Controlled import of a preserved artifact
uv run philfacilities-ingest source run bir --input var/raw/bir/.../rao-006-2025.pdf

# Replay preserved releases through current parsers
uv run philfacilities-ingest source replay docs/operations/replay-manifest.example.json

# Fresh access evidence and rebuild pack
uv run philfacilities-ingest probe-sources
uv run philfacilities-ingest rebuild-report
```

`source run` exits non-zero if any selected source fails. Select by key or `--group approved|skipped`; `--exclude` repeats. `--dry-run` acquires and validates but writes no canonical or staging rows. `--input` is limited to one source key. Source-specific options are generic runner options: `--region` (EBEIS), `--file`/`--provider-category` (PhilHealth), `--dataset` (BetterGov population), `--pbf-path`/`--extract-out` (OSM PBF).

`source replay` never re-downloads: each manifest entry names a stored `release_id` or `raw_object_uri`, bytes are verified against the recorded SHA-256, then passed through the current connector and adapter with `reprocess=True`. See `docs/operations/replay-manifest.example.json`. Manual imports (`ingest-file`) require `--reviewer` when the supplied rights state may publish records; the command never invents a rights decision.

Location helpers fill missing geography without guessing: `fill-locations-from-osm` adds a labelled `map_geocoded` community point only on an exact name + city match with a unique OSM candidate; `fill-location-psgc` resolves a missing PSGC code from linked source payloads; `import-osm-boundaries` preserves OSM polygons; `fill-location-psgc-from-map` uses point-in-polygon containment. Every accepted value is written as a source-linked `AttributeAssertion` and each command is an idempotent dry run until `--apply`.

## 5. Source groups and access

| Group | Meaning |
|---|---|
| `approved` | Automated acquisition with a recorded rights/publication decision |
| `skipped` | No automatic public route; returns `status=skipped` with a reason, detail, official alternate route, and next automatic retry |

A skipped source is still listed, checked where possible, and retried automatically. It is not deleted or placed in a human queue. Controlled reasons live in `skip_reasons.py`: `HTTP_403`, `HTTP_404`, `HTTP_429`, `HTTP_5XX`, `WAF_CHALLENGE`, `LOGIN_REQUIRED`, `AGREEMENT_REQUIRED`, `FOI_REQUIRED`, `CAPTCHA_REQUIRED`, `HUMAN_ACCESS_REQUIRED`, `TLS_FAILURE`, `DNS_FAILURE`, `TRANSFER_FAILED`, `EXPLICIT_RESTRICTION`, `PRIVACY_RESTRICTION`, `NO_PUBLIC_RELEASE`, `UNVERIFIED_PUBLISHER`.

A release that does not parse or validate remains a `failed` run and is quarantined; that is not a skip. The raw artifact stays in the store, the previous published release stays current, and the failure is reported. An unexpected discovery exception is a `failed` run, not a controlled skip, so connector bugs stay actionable.

## 6. Storage layers

> **Hosted read model.** The Heroku database is a derived, public-only
> projection built by `scripts/build_public_projection.py`, never an ingestion
> target. `just publish` copies public facilities, current locations, profiles,
> global lookups and slim source evidence into a scratch database, dumps it with
> a manifest, and a GitHub workflow installs it. Assertions, raw payloads,
> internal rows and change history stay in the authoritative database. See
> [Hosting](operations/hosting-heroku-vercel.md#free-tier-quota-constraint-important).

### Raw layer

Exact agency file/response plus URL, retrieval time, HTTP metadata, source publication/reference date, SHA-256, access/terms classification, parser version, and release label:

```text
var/raw/<agency>/<dataset>/<release>/<sha256-prefix>-<filename>
```

With `PHILFACILITIES_S3_BUCKET` configured, the same abstraction stores objects in the bucket. Raw objects are private by default; publish derived fields and metadata rather than re-hosting a source file unless its terms permit. Filesystem writes are atomic and reads verify the manifest; a checksum mismatch raises `RawStoreIntegrityError` and the store is never silently repaired.

### Staging

Source-specific records with original values and row/page references. A source record belongs to exactly one release and at most one canonical facility.

### Canonical

Facilities, locations, functions, services, roles, relationships, domain observations, geography references, assertions/fusions, quality issues, and change events. See [Data model](data-model.md).

## 7. Validation

Shared helpers in `validators.py`: `coordinate_in_philippines` / `coordinate_issue` (plausibility box only), `psgc_shape_issue` (decimal shape and leading zeros), `missing_required_fields`, and `duplicate_values`. Each adapter owns its own schema checks inside `parse()` and raises on missing/renamed columns. Validation covers file/schema shape, required IDs and names, duplicate rows, PSGC existence/hierarchy, coordinate ranges and precision, null-vs-zero semantics, and domain constraints. An implausible coordinate is retained with a warning and a quality issue — never silently deleted or "corrected".

A source row with an address or PSGC code but no coordinate is stored as the current location with null geometry. No point is invented, and an address-only claim never displaces a coordinate-bearing location.

**Release acceptance floor.** Defaults: `minimum_acceptance_rate = 0.90`, `minimum_acceptance_rows = 20`. The row floor avoids failing a tiny release on one malformed row; above the floor the accepted share must meet the rate floor; an empty parse is always fatal. A failed release is quarantined before any canonical write with a `release_empty` or `acceptance_rate_below_floor` quality issue. Sources may override the floor in `registry_data.py` with a recorded justification.

## 8. Identity resolution

One canonical facility represents one real-world facility; source rows stay attached as evidence and a duplicate is retired as an internal `merged` tombstone, never deleted. Evidence ranking:

1. exact source-specific stable ID within the same source system;
2. explicit official crosswalk or shared identifier;
3. exact normalized name + current PSGC unit + compatible subtype + different agency;
4. independent agreement of name, place, and coordinates → candidate only;
5. conflicting IDs or distant coordinates → unmerged candidate.

Names are folded for comparison only (case, punctuation, connector order, `St.`/`Saint`, legal forms, school-type abbreviations); the fold never rewrites a source value. Subtype labels are compared as families, not raw strings. `aggregation.py` groups candidates and merges a cluster only when every pair is auto-eligible and at least one strong bridge exists (shared official ID, same barangay, shared address token, or points within 250 m). Exact name + same city alone is normally not enough; a cross-type pair becomes review-only (`cross_type: true`).

```bash
uv run philfacilities-ingest consolidate-facilities                 # dry run
uv run philfacilities-ingest consolidate-facilities --apply --limit 100
uv run philfacilities-ingest match-candidates-generate
uv run philfacilities-ingest match-candidates --status pending
uv run philfacilities-ingest match-candidates-resolve               # dry run
uv run philfacilities-ingest match-candidates-resolve --apply
uv run philfacilities-ingest match-candidates-accept <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-reject <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-merge <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-undo-merge <id> --reviewer <name> --note "..."
```

For a large backlog, `--commit-every N` and `--defer-fusion` keep completed work and rebuild fusion once. Do not run two write passes at once. Accepting is separate from merging; undo refuses when moved evidence has changed. A merged slug remains an alias to the survivor. Other passes: `normalize-display-names`, `normalize-facility-slugs`, `consolidate-numeric-slugs`, `normalize-health-subtypes`, `refine-health-ownership`, `normalize-school-subtypes` (dry run first, then `--apply`).

## 9. Field-level fusion

`fusion.py` writes one derived value per facility/attribute plus every competing claim in `core.facility_attribute_fusions`:

- Only claims from the dataset's latest published, rights-cleared release participate.
- Empty/missing claims are ignored, not treated as zero or false.
- Ranking is authority-first (`authority_level`, then coverage scope), then independent support, then recency. Raw frequency does not outrank an official source.
- `agreed` requires the same normalized value from at least two distinct agencies; one publisher's records stay `single_source`.
- Disagreements become `conflict` with the preferred claim as derived value and all alternatives retained.
- `--apply` writes only the safe allowlist: `facility_subtype`, `ownership`, `ownership_type`, `operator_type`, `public_access_class`, `record_status`. Equal-authority conflicts stay derived-only; a single-source value only fills a missing field. Names are never overwritten.
- Recomputation removes stale rows; merges and rollbacks invalidate affected rows. Fusion is fully automatic — there is no review queue.

```bash
uv run philfacilities-ingest fuse-attributes
uv run philfacilities-ingest fuse-attributes --all --apply
uv run philfacilities-ingest fusion-report --status conflict
uv run philfacilities-ingest fusion-report --json
```

### Enrichment-only and link-only releases

An adapter may set `FacilityCandidate.enrichment_only=True` when rows add evidence to an existing facility rather than identify it. The pipeline then matches by stable agency entity ID (or an exact DOH code on a health profile), records source links/assertions/events as usual, fills only null/placeholder canonical and profile fields, never updates `display_name`, and may create a missing typed profile. The DepEd SY 2020-2021 Masterlist and DOH NHFR use this mode.

`link_only=True` is for stale or community-compiled snapshots that must never add registry records: the row links by exact entity ID and is stored as evidence, while an unmatched ID becomes an `unmatched_link_only_row` quality issue. The OSM 2019 MaPaaralan point table uses this mode.

## 10. Idempotency and failure behaviour

| Situation | Result |
|---|---|
| Same checksum already published, same parser | `skipped_duplicate`; no new release or rows |
| Same checksum, new parser version | Automatic reprocess; versions and derived rows updated |
| Changed file | New immutable release; previous retained |
| Empty parse / below floor / validation failure | Release `failed`/`quarantined`; previous published release stays public |
| Unexpected error during apply | Release `failed`; never-public becomes `quarantined`, previously published keeps serving |
| Failure on a previously published release | Release keeps `published`; run records the failure |
| Second worker for the same dataset | `IngestionLockError`; retry after the first finishes |
| Killed run | Resumes the same release on retry |
| `--reprocess` / `--force-reapply` | Rebuild derived rows; `--force-reapply` re-applies even unchanged payloads for new child tables |
| `source replay` | Verifies SHA-256 and reprocesses the existing release |

`--reprocess` skips unchanged already-linked rows so replay cannot churn canonical names. Use `--force-reapply` when adding a new derived table, then review the affected release — it can let a competing source change an established value.

## 11. Reports and monitoring

Every run records source/dataset/release, discovery URL, retrieval time, checksum, source publication and reference dates, parser/schema versions, input/parsed/accepted/rejected counts, rates, duplicates, null rates, PSGC match rate, coordinate precision distribution, match candidates, validation failures, and the publication result. Reports go to `var/reports/`; `status` summarises counts and recent runs; `compare-releases` is a read-only comparison. The rebuild evidence pack lives under `var/reports/rebuild/`.

Source checks append to `source.source_checks` with `ok`, `not_modified`, `access_blocked`, `not_found`, `schema_changed`, or `request_failed` and a `next_check_at`. `source check --due` exits `2` for actionable failures and can POST to `PHILFACILITIES_ALERT_WEBHOOK_URL`. A successful check does **not** publish data.

```bash
uv run philfacilities-ingest source check philhealth
uv run philfacilities-ingest source check --due
```

Operator procedures: [source monitoring](operations/source-monitoring-runbook.md), [Operations](operations.md).
