# Ingestion

**Implementation:** `apps/ingest/philfacilities_ingest/`
**Authority for source metadata:** `sources/registry.py` + `sources/catalog.py`
**Authority for publication:** [data policy](data-policy.md)

Ingestion is a first-class product component. It is reproducible, observable, source-aware, and safe to rerun. A failed download, schema change, or validation failure must never replace the last good public release.

```text
discover → acquire → preserve → parse → validate → normalize
        → resolve → publication gate → report
```

## 1. Design rules

- **Acquisition and parsing are separate.** A connector owns discovery and acquisition; an adapter owns `parse → validate → normalize`. An adapter never downloads and never invents a missing value.
- **The catalogue is data-driven.** A source is declared once in `sources/registry.py` and wired once in `sources/catalog.py`. The CLI, runner, checks, and scheduled jobs read that catalogue. Do not add a `load-<source>` command or a source-specific branch to `pipeline/`.
- **Raw source truth is immutable.** Every acquired artifact is preserved with a SHA-256 before parsing. Original column names and values stay in `source.records.raw_payload`.
- **Validation fails closed.** Missing required columns, unreadable files, and shape changes raise; they do not produce a guessed release. An empty parse or a release below its acceptance floor is quarantined before canonical writes.
- **One writer per dataset.** A PostgreSQL session-level advisory lock covers the whole preserve/parse/apply/report lifecycle. A second worker fails fast instead of interleaving canonical writes.
- **Internal evidence cannot rewrite a public profile.** Assertions and child rows from an internal-only release are stored for audit but read-gated; they may not change a public facility's canonical identity, current location, profiles, or publication state.
- **Publication is not an ingestion side effect.** A record becomes public only when the dataset rights state, dataset gate, and release gate all pass. See [data policy](data-policy.md).
- **Ambiguity is preserved.** Matching produces review candidates; it never merges on name similarity. Conflicting field claims are retained, not overwritten.

## 2. Module map

| Module | Responsibility |
|---|---|
| `acquisition.py` | Bounded HTTP requests, conditional headers, retries/backoff, response classification, signature checks, source-check ledger helpers |
| `storage.py` | Content-addressed raw store; filesystem and S3-compatible backends |
| `contracts.py` | `ReleaseSpec`, `ParsedRelease`, `FacilityCandidate`, `ValidationResult`, adapter protocol |
| `sources/definitions.py` | `SourceDefinition`, `AgencyRef`, `DatasetRef`, `RightsDecision`, `AccessSpec`, `CheckSpec` |
| `sources/registry.py` | `REAL_SOURCES`: keys, URLs, access/rights metadata, rights basis, attribution |
| `sources/catalog.py` | `SOURCES` and `CONNECTORS`: the single acquisition catalogue |
| `sources/connectors/` | Reusable acquisition shapes: single file, PhilHealth index, OSM Parquet/PBF, EBEIS paging, geography/population |
| `sources/<source>.py` | Source-specific parsing, validation, normalization |
| `source_runner.py` | Generic `run_source`, `validate_source`, `run_selection` |
| `replay.py` | Manifest-driven replay of preserved raw releases through current parsers |
| `pipeline/release.py` | Source/release lifecycle, duplicate detection, run reports, source metadata |
| `pipeline/locking.py` | Per-dataset PostgreSQL advisory lock |
| `pipeline/staging.py` | Source-record staging and row-count anomaly checks |
| `pipeline/canonical.py` | Canonical facility writes, source links, locations, assertions, quality issues |
| `pipeline/geography.py` | PSGC releases and administrative units |
| `pipeline/stats.py` | Population observations |
| `pipeline/runner.py` | The single facility-release orchestration path |
| `validators.py` | Shared coordinate, PSGC-shape, required-field, duplicate-key checks |
| `matching.py` | Deterministic identity candidates; never auto-merges |
| `fusion.py` | Attribute assertions/fusions and safe allowlisted application |
| `release_rollback.py` | Pre-release canonical snapshots and conservative rollback |
| `cli.py` | Typer command tree |

## 3. The release lifecycle

1. `SourceDefinition.release_spec()` combines the reviewed registry metadata with the acquired artifact.
2. The runner takes the dataset's advisory lock, then the raw store writes `var/raw/<agency>/<dataset>/<release>/<sha256-prefix>-<filename>` plus a manifest, or the equivalent S3 object. Writes are atomic (temporary file, fsync, rename).
3. The release row is created or reused. A dataset + SHA-256 pair is unique.
4. An unchanged, already-published checksum returns `skipped_duplicate`; counts do not change. If the adapter's `parser_version` differs from the stored value, the release is reprocessed automatically. A release whose latest run failed is retried instead of skipped, even without `--reprocess`, because a failed reprocess deliberately leaves the release published.
5. The adapter parses, validates, and normalizes. A parse/validation failure, an empty parse, or an acceptance rate below the release floor marks the release `failed` and quarantines it; the previously published release stays published.
6. Staging writes source records with row/page references.
7. Canonical writes create or link facilities, locations, domain observations, assertions, and quality issues. Write-side gating prevents an internal-only release from rewriting an already public facility; its assertions and child rows remain read-gated.
8. The publication gate is evaluated from the dataset and release rights state, not from file reachability.
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

# Fresh reachability evidence and rebuild pack
uv run philfacilities-ingest probe-sources
uv run philfacilities-ingest fill-locations-from-osm --apply --report var/reports/rebuild/osm-location-fills.json
uv run philfacilities-ingest rebuild-report

# Validate without canonical writes
uv run philfacilities-ingest source validate philhealth --fixture var/raw/.../file.pdf
uv run philfacilities-ingest source run philhealth --dry-run

# Controlled import of a preserved artifact
uv run philfacilities-ingest source run bir --input var/raw/bir/.../rao-006-2025.pdf

# Replay preserved releases through the current parsers
uv run philfacilities-ingest source replay docs/operations/replay-manifest.example.json
```

`source run` exits non-zero if any selected source fails. Select sources by key or by `--group approved|skipped`; `--exclude` repeats. `--dry-run` acquires and validates but does not write canonical or staging rows. `--input` is limited to one source key. `--enqueue-matches` opts one release into cross-source candidate matching; the explicit matcher command is preferred.

`source replay` never re-downloads a source. Each manifest entry names a stored `release_id` or a `raw_object_uri`; bytes are verified against the recorded SHA-256, then passed through the current connector and adapter with `reprocess=True`. A replay therefore updates parser-derived state without creating a duplicate release or changing the preserved bytes. Example: `docs/operations/replay-manifest.example.json`.

For a stored `release_id`, replay validates the dataset's publisher rather than requiring the catalogue's default slug. Multi-dataset connectors keep their per-dataset context: the EBEIS region is recovered from `deped-ebeis-masterlist-<region>`, the PhilHealth provider category from the stored `PhilHealth — <category>` dataset name, and the acquired release is written back into the stored dataset slug/name. Explicit `options` in the manifest still take precedence.

Manual imports (`ingest-file`) require `--reviewer` whenever the supplied rights state may publish records. The reviewer and `--review-note` are recorded on the publication gate, and the command never invents a rights decision.

Source-specific options are generic runner options, not separate commands: `--region` (EBEIS), `--file` and `--provider-category` (PhilHealth), `--dataset` (BetterGov population), `--pbf-path`/`--extract-out` (OSM PBF).

## 5. Source groups and access

| Group | Meaning |
|---|---|
| `approved` | Automated acquisition with a recorded rights/publication decision |
| `skipped` | No automatic public route; the run returns `status=skipped` with a machine-readable reason, detail, official alternate route and next automatic retry |

A skipped source is still listed, checked where possible and retried automatically. It is not deleted and does not disappear from the catalogue because it cannot be published. There is no `manual` or `blocked` group and no human approval queue. The controlled reasons are defined once in `skip_reasons.py`: `HTTP_403`, `HTTP_404`, `HTTP_429`, `HTTP_5XX`, `WAF_CHALLENGE`, `LOGIN_REQUIRED`, `AGREEMENT_REQUIRED`, `FOI_REQUIRED`, `CAPTCHA_REQUIRED`, `HUMAN_ACCESS_REQUIRED`, `TLS_FAILURE`, `DNS_FAILURE`, `TRANSFER_FAILED`, `EXPLICIT_RESTRICTION`, `PRIVACY_RESTRICTION`, `NO_PUBLIC_RELEASE` and `UNVERIFIED_PUBLISHER`.

A release that does not parse or validate remains a `failed` run and is quarantined; that is not a skip. The raw artifact stays in the raw store, the previous published release stays current, and the failure is reported.

## 6. Storage layers

### Raw layer

Exact agency file/response plus source URL, retrieval time, HTTP metadata, source publication/reference date, SHA-256, access/terms classification, parser version, and release label.

```text
var/raw/<agency>/<dataset>/<release>/<sha256-prefix>-<filename>
```

With S3 configured (`PHILFACILITIES_S3_BUCKET`), the same abstraction stores objects under the bucket. Raw objects are private by default; publish derived facility fields and metadata rather than re-hosting a source file unless its terms permit re-hosting.

Filesystem writes are atomic (temporary file, `fsync`, `os.replace`), and reads verify the manifest/SHA-256 before returning bytes. S3 reads verify the object's `sha256` metadata. A mismatch raises `RawStoreIntegrityError`; the store is never silently repaired in place.

### Staging

Source-specific records with original values and row/page references. A source record belongs to exactly one release and at most one canonical facility.

### Canonical

Facilities, locations, functions, services, roles, relationships, domain observations, geography references, attribute assertions/fusions, quality issues, and change events. See [data model](data-model.md).

## 7. Validation

Shared helpers live in `validators.py`:

- `coordinate_in_philippines` / `coordinate_issue` — plausibility box only; preserve the original precision and method.
- `psgc_shape_issue` — decimal shape and leading zeros.
- `missing_required_fields` — absent or empty required fields.
- `duplicate_values` — repeated source keys before canonical storage.

Each adapter still owns its schema checks. Check headings/columns inside `parse()` and fail with a message naming the missing fields. Unexpected missing or renamed columns must never be silently coerced.

Validation should cover:

- file/schema/signature shape and required fields;
- required source IDs and names;
- duplicate source rows and conflicting values;
- PSGC existence/hierarchy where a mapping is claimed;
- coordinate ranges, bbox plausibility, and precision;
- null-vs-zero semantics;
- domain constraints (nonnegative counts, parsed dates, retained reference periods).

An implausible coordinate is retained with a warning and a quality issue; it is not silently deleted or "corrected".

### Address-only and PSGC-only locations

A source row that publishes an address or PSGC code but no coordinate is stored as the current `FacilityLocation` with null geometry and null latitude/longitude. The address, postal code, PSGC code and source/provenance are retained. A location is treated as absent only when the source supplies no location evidence at all. No point is invented, and an address-only claim never displaces a coordinate-bearing location.

When a facility has no current point, `fill-locations-from-osm` may add a deterministic OSM gap-fill: exact normalized name plus the same city/municipality, a unique OSM candidate, and a point inside the Philippine plausibility box. The accepted point is stored with `precision=map_geocoded`, `method=openstreetmap_match`, `review_status=community_fallback`, the OSM id/snapshot and ODbL attribution. It never overwrites an official coordinate, and ambiguous candidates remain unlocated. The fill report records matched, ambiguous and unmatched counts.

### Release acceptance floor

A release-level policy catches broad schema drift that row-level checks miss. The defaults are `minimum_acceptance_rate = 0.90` and `minimum_acceptance_rows = 20`:

- the row floor avoids failing a tiny release (a handful of offices) on one legitimately malformed row;
- once the release has at least the row floor, the accepted-row share must meet the rate floor;
- an empty parse is always fatal, because a zero-row snapshot would otherwise displace the last good release;
- a failed release is quarantined before any canonical write, and a `QualityIssue` (`acceptance_rate_below_floor` or `release_empty`) is recorded.

Sources may override the policy in `sources/registry.py` when their verified row counts justify a different floor.

## 8. Identity resolution

Deterministic matching only, in this order:

1. exact source-specific stable ID within the same source system;
2. explicit official crosswalk or shared identifier;
3. exact normalized name + current PSGC unit + compatible subtype + different source agency;
4. similar name + locality + address evidence → candidate only;
5. conflicting IDs or distant coordinates → unmerged candidate, retained and retried automatically.

```bash
uv run philfacilities-ingest match-candidates-generate
uv run philfacilities-ingest match-candidates --status pending
uv run philfacilities-ingest match-candidates-accept <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-reject <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-merge <id> --reviewer <name> --note "..."
```

Accepting is separate from merging. A merge is transactional, moves evidence, retires the duplicate as a `merged` tombstone, and writes change events. Contacts move with the facility; a contact that duplicates the target's `(contact_type, value, source_record)` stays on the source tombstone so `uq_facility_contact_source` is never violated, and the merge resolution records the retained count. Undo restores only the contacts that actually moved. Rejected candidates are retained so the same pair is not re-queued for the same algorithm version.

## 9. Field-level fusion

Sources disagree about attributes even when they describe the same facility. `fusion.py` writes one derived value per facility/attribute plus every competing claim in `core.facility_attribute_fusions`.

- Only claims from the dataset's latest published, rights-cleared release participate in fusion. A restricted, blocked, superseded, or otherwise non-public claim cannot select or corroborate a canonical value; synthetic demo datasets retain their demo behaviour.
- Empty/missing claims are ignored, not treated as zero or false.
- Ranking is authority-first: `source.datasets.authority_level` (`official`, `community`, `synthetic`, `unknown`) plus coverage scope, then independent support, then recency. Raw claim frequency does not outrank an official source.
- `agreed` requires the same normalized value from at least two distinct agencies. Multiple records from one publisher are `single_source`, not independent corroboration.
- Disagreements become `conflict`; the preferred claim is the derived value and every alternative remains in `alternatives` with its source records, agencies and releases.
- A single claim stays `single_source` and is never presented as cross-source agreement.
- `--apply` writes the safe fields `facility_subtype`, `ownership`, `ownership_type`, `operator_type`, `public_access_class`, and `record_status`. Cross-agency agreements and conflicts with a clear authority winner are applied automatically. An equal-authority conflict stays derived-only rather than overwriting the canonical row on an arbitrary tie-break. A single-source value only fills a missing or unknown canonical field. Names and curatorial fields are not overwritten.
- Recomputation removes fusion rows whose claims no longer exist. Merges and release rollbacks invalidate affected rows so a stale selection cannot be applied later.

```bash
uv run philfacilities-ingest fuse-attributes
uv run philfacilities-ingest fuse-attributes --all --apply
uv run philfacilities-ingest fusion-report --status conflict
uv run philfacilities-ingest fusion-report --json
```

Fusion is fully automatic; there is no review queue or review command. `fusion-report --json` reports status counts, unresolved equal-authority conflicts and samples. Every applied change is recorded as an `attribute_fused` change event with the algorithm version and supporting source record, while the raw claims and all alternatives remain unchanged.

`auto-merge-duplicates` is narrower: exact normalized name + compatible type, plus either exact address in the same PSGC (`confidence >= 0.900`) or an exact-name geo match at `<= 25 m` with official-side evidence. It is a dry run unless `--apply` is passed; 25–50 m matches remain pending.

## 10. Idempotency and failure behaviour

| Situation | Result |
|---|---|
| Same checksum already published, same parser version | `skipped_duplicate`; no new release or rows |
| Same checksum, new parser version | Automatic reprocess; parser/schema versions and derived rows updated |
| Changed file | New immutable release; previous release retained |
| Empty parse | Release `failed`/`quarantined`; previous published release stays public |
| Acceptance rate below the release floor | Release `failed`/`quarantined`; no canonical write from that release |
| Parse/validation failure on a new release | Release `failed`/`quarantined`; previous published release stays public |
| Unexpected error during apply | Release `failed`; a never-public release becomes `quarantined`, a previously published release keeps serving |
| Failure on a previously published release | Release keeps `published`; the run records the failure |
| Second worker for the same dataset | Fails fast with `IngestionLockError`; retry after the first run finishes |
| Killed run | Resumes the same release on retry; the advisory lock is released with the connection |
| `--reprocess` | Rebuilds derived rows from the preserved artifact; does not duplicate unchanged links |
| `source replay` | Verifies the preserved SHA-256 and reprocesses the existing release through the current parser |

A failed reprocess of a release that is already public keeps the release row and its last good source records exactly as they were: validation issues are recorded, staging is skipped, and the release stays `published` so the public snapshot remains visible. A later retry is not classified as `skipped_duplicate`.

An unexpected exception during discovery is a `failed` run, not a controlled skip. Only explicit `SkippedRelease` decisions are recorded with a skip reason, so connector bugs remain actionable in alerts and monitoring.

`fill-locations-from-osm` resolves city names only from the latest non-synthetic geography release. Synthetic demo geography is never used to geocode real facilities; if no real release exists, resolution stays unresolved.

## 11. Reports and monitoring

Every run records source/dataset/release, discovery URL, retrieval time, checksum, source publication and reference dates, parser/schema versions, input/parsed/accepted/rejected counts, acceptance/rejection rates, duplicates, null rates, PSGC match rate, coordinate precision distribution, match candidates, validation failures, and the publication result.

Reports are written under `var/reports/`; `status` summarizes canonical/synthetic/dataset/release counts and recent runs. `compare-releases` is a read-only comparison of two retained releases by source-record key, payload hash, and facility link.

The rebuild evidence pack lives under `var/reports/rebuild/`. `probe-sources` writes a fresh dated text ledger plus `probe-ledger.jsonl`; `rebuild-report` writes every data.md section 11.1 file from the database, retained releases, merged inventory and OSM fill report. It writes `UNKNOWN`/`NOT_VERIFIED` rather than guessing and never treats OSM coverage as official coverage.

Source checks append to `source.source_checks` and record `ok`, `not_modified`, `access_blocked`, `not_found`, `schema_changed`, or `request_failed`, with `next_check_at`. `source check --due` exits `2` for actionable failures and can POST to `PHILFACILITIES_ALERT_WEBHOOK_URL` when configured. `source run` and `source replay` also post a failure summary for rows whose status is `failed`; a duplicate skip or a dry-run validation is not an incident. A successful check does **not** publish data.

```bash
uv run philfacilities-ingest source check philhealth
uv run philfacilities-ingest source check --due
```

Operator procedures: [source monitoring](operations/source-monitoring-runbook.md), [operations](operations.md).

## 12. Adding a source

Follow [adding a source](adding-a-source.md). No CLI or pipeline edit is required: register metadata, add an adapter, register the connector, add a fixture and tests, then validate, dry-run, and load.
