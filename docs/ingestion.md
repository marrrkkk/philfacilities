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
| `osm_boundaries.py` | Preserve OSM administrative boundary polygons and resolve their `ref`/name to the current PSGC release |
| `psgc_spatial_fill.py` | Point-in-polygon PSGC fill/refinement for coordinate-bearing current locations |
| `pipeline/stats.py` | Population observations |
| `pipeline/runner.py` | The single facility-release orchestration path |
| `validators.py` | Shared coordinate, PSGC-shape, required-field, duplicate-key checks |
| `identity.py` | Pure name folding, name keys, address tokens, PSGC helpers for identity evidence |
| `matching.py` | Deterministic identity candidates, reviewed merges, EBEIS prefixed-ID merges, undo |
| `aggregation.py` | Whole-registry evidence clustering, strong-bridge auto-merge, location promotion |
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
uv run philfacilities-ingest fill-location-psgc --apply --report var/reports/rebuild/psgc-location-fills.json
uv run philfacilities-ingest import-osm-boundaries --apply --report var/reports/rebuild/osm-boundaries.json
uv run philfacilities-ingest fill-location-psgc-from-map --prefer-map --apply --report var/reports/rebuild/map-psgc-location-fills.json
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

`fill-location-psgc` resolves a missing current-location PSGC code from the location's own linked source payload, then from other linked records. It accepts an exact code from the current release, the release's `correspondence_code` for a legacy 9-digit code, or an exact normalized administrative-name hierarchy. Name matches require a unique candidate; a same-level conflict stays unresolved. A stale region or province label does not invalidate a deeper city/barangay code after a PSGC reorganization, and an independent city wins over its geographic province; a conflicting city-level name drops back to the city rather than guessing the barangay. A non-null `FacilityLocation.psgc_code` is never overwritten. Each accepted value is written with a source-linked `AttributeAssertion` (`attribute_name=psgc_code`, `review_status=derived`, `transformation_version=psgc-resolution-v1`) and the command is idempotent. Without `--apply` it is a dry run; `--report` writes the per-location evidence and method counts to JSON.

`import-osm-boundaries` extracts administrative boundary polygons from the same preserved Geofabrik PBF snapshot used for the OSM facility extract. The filtered Parquet artifact and its JSON sidecar (source URL, SHA-256, retrieval time, parser version, counts) are the reproducible release; `geo.osm_admin_boundaries` is derived from it. Boundaries resolve by an exact current PSGC `ref`, a legacy `correspondence_code`, or an exact normalized name under a spatially containing parent. Unresolved, ambiguous or level-incompatible boundaries keep a null `psgc_code` and are not used for facility resolution.

`fill-location-psgc-from-map` intersects coordinate-bearing current locations with the resolved boundary layer. It takes the deepest unambiguous containing unit and verifies that every other containing boundary is its ancestor; inconsistent overlaps are skipped. A null code is filled. `--refine` upgrades a non-null code only when the map unit is a descendant of the current code, so a source municipality can become its barangay but a same-level or different-branch value is never replaced. `--prefer-map` makes the map point authoritative for the administrative location: it refines as above and also replaces same-level or different-branch source codes, including a source code that is absent from the current geography release. The original source claim remains in its source-linked `AttributeAssertion`; the override only changes which claim the location uses. A map result that is less specific than the source code (`current_more_specific`) is not downgraded, and points with no deterministic containing unit, inconsistent overlaps or a missing source record are left unchanged. Every write is a source-linked `AttributeAssertion` with `transformation_version=psgc-spatial-v1` and `review_status=derived`; without `--apply` the command is a dry run and reruns are idempotent.

### Release acceptance floor

A release-level policy catches broad schema drift that row-level checks miss. The defaults are `minimum_acceptance_rate = 0.90` and `minimum_acceptance_rows = 20`:

- the row floor avoids failing a tiny release (a handful of offices) on one legitimately malformed row;
- once the release has at least the row floor, the accepted-row share must meet the rate floor;
- an empty parse is always fatal, because a zero-row snapshot would otherwise displace the last good release;
- a failed release is quarantined before any canonical write, and a `QualityIssue` (`acceptance_rate_below_floor` or `release_empty`) is recorded.

Sources may override the policy in `sources/registry.py` when their verified row counts justify a different floor.

## 8. Identity resolution

One canonical facility represents one real-world facility. Directory, map, and detail views all read that record; source rows stay attached as evidence. A duplicate is retired as an internal `merged` tombstone, never deleted.

Evidence is ranked, strongest first:

1. exact source-specific stable ID within the same source system;
2. explicit official crosswalk or shared identifier;
3. exact normalized name + current PSGC unit + compatible subtype + different source agency;
4. independent agreement of name, city/barangay/address, and coordinates → candidate only;
5. conflicting IDs or distant coordinates → unmerged candidate, retained for the resolution pass.

Names are folded for comparison only: case, punctuation, whitespace, HTML-encoded ampersands (`&amp;`, `&AMP;`, `&#38;`), connector order (`X Hospital and Maternity` vs `X Maternity Hospital`), `St.`/`Saint`/`Sta.`/`Sto.`, and optional legal forms such as `Inc.` and `Corporation`. School names additionally expand uppercase school-type abbreviations (`ES`, `IS`, `NHS`, `SHS`, `SPED`, …). The comparison fold never rewrites a source value. Canonical `display_name` casing is handled by the separate pass below; `official_name`, the raw source payload and the field assertions keep the source spelling. A name match alone never merges two records: two different places can share a name.

Subtype labels come from independent agency vocabularies and are compared as families, not raw strings. OSM `college`, CHED `HIGHER_EDUCATION_INSTITUTION` and DepEd `OTHER_SCHOOL` can describe one school; `elementary school` and `college` cannot. A vague label such as `school` or `other …` carries no level information and never blocks a pair by itself. City is taken from the location PSGC, or resolved from the address by preferring an explicit city/municipality segment, so a trailing province name that matches another city (`Lucena City, Quezon`) does not erase the city. Subtype families and address-derived city codes are identity evidence only; the stored subtype, address and PSGC claims are never rewritten.

Aggregation (`aggregation.py`) groups candidate pairs by facility type + name key. Groups of up to 64 rows are compared exhaustively; larger groups are bucketed by city and by a ~1.1 km coordinate cell plus its eight neighbours, so two sources that assign the same site to different cities still compare when their points are close. A cluster is merged only when every pair inside it is auto-eligible and at least one pair is a strong bridge — a shared official ID, the same barangay, a shared address token, or points within 250 m. The clique may omit a conflicting record rather than letting it block the confirmed duplicates around it. Exact name plus the same city alone is normally not enough. An exception bridges an address-only official row to a mapped community row: the name must be exact and specific, identifiers and places must not conflict, the community row must carry the point, and the official's published address claims (every assertion, not only the truncated current address text) must independently name the mapped city or share a street token. The bridge is rejected when one official row could confirm two mapped points more than 250 m apart, so distinct branches with one name stay separate.

A differing barangay is normally a conflict: two branches of one agency can sit near a boundary, and the barangay is independent administrative evidence. The exception is a map-derived location. If the names are exactly equal and specific, both points are within 50 m, and at least one side is `map_geocoded` or `barangay_centroid`, a differing barangay is treated as boundary noise rather than proof of two places. Two independently surveyed (`source_gps`, `surveyed`, `field_verified`) points that disagree still stay separate. The source coordinates and PSGC claims are never rewritten by this rule.

The OSM education layer has a narrower map-feature exception. One named institution is often mapped twice: an `amenity=school|university|college` polygon and a gate or building with the same name, whose bbox centres can be up to 100 m apart. Such a pair is auto-eligible only when both current points are map-derived, both records come from `osm-education-facilities`, the barangay agrees, the name is exact and specific, no identifiers or places conflict, and at least one source row carries an institution `amenity` tag. Other community layers keep the tighter 50 m same-agency rule: distinct branches of a chain can be a few dozen metres apart in one barangay, and their same-name pairs remain review candidates instead of being merged. Generic building names with no institution tag also keep the 50 m rule.

Free-text address differences also block a merge only when both addresses carry street-level evidence and no street token matches. A locality-only description such as `Lucena City, Quezon` is less precise than a street address, not a competing one, and a specific matching name at a point within 50 m outranks the difference.

Facility type is normally a hard boundary. A same-name pair within 50 m whose types differ is never merged automatically. When one side is official and the other is not, both names are specific and non-generic, and there are no conflicting identifiers or places, the pair becomes a pending candidate with `cross_type: true` for a reviewer. This is how a health-facility registry row and a co-located social-welfare map row for the same named institution reach review instead of becoming two public facilities. If the reviewer confirms they describe one site, `match-candidates-merge --allow-facility-type-mismatch` performs the explicit cross-type merge; the surviving facility keeps its own type and the retired record remains an internal tombstone.

The surviving record is chosen deterministically: official source first, then the most official identifiers, then the most source links, then the oldest record. After the merge the most precise documented location becomes current; the previous current location is closed as history rather than discarded, and `resolution["location_promotion"]` records the change. Pairs without a strong bridge are not auto-merged; non-automatic pairs that still share a name and city stay as pending candidates until the resolution pass.

`match-candidates-resolve` re-evaluates every pending pair against current evidence instead of trusting the evidence captured when it was queued. It merges a pair only when it still meets the automatic consolidation rule and the candidate target is the preferred survivor. Stale pairs, cross-type pairs, conflicting identifiers or places, and weak same-city pairs are rejected with a recorded reason. Rejection is terminal: the same pair is not queued again for the same algorithm version. A pair that involves a facility which is not public stays pending, because publication is a separate gate. Run the command in dry-run mode first to inspect `by_reason` and the examples.

```bash
uv run philfacilities-ingest consolidate-facilities                 # dry run
uv run philfacilities-ingest consolidate-facilities --apply --limit 100
uv run philfacilities-ingest consolidate-facilities --facility-type school --apply --limit 20000 --commit-every 500 --defer-fusion
uv run philfacilities-ingest merge-deped-prefixed-ids               # dry run
uv run philfacilities-ingest merge-deped-prefixed-ids --apply --limit 100
uv run philfacilities-ingest match-candidates-generate
uv run philfacilities-ingest match-candidates --status pending
uv run philfacilities-ingest match-candidates-resolve               # dry run
uv run philfacilities-ingest match-candidates-resolve --apply
uv run philfacilities-ingest match-candidates-accept <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-reject <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-merge <id> --reviewer <name> --note "..."
uv run philfacilities-ingest match-candidates-undo-merge <id> --reviewer <name> --note "..."
```

`--facility-type` limits the pass to one type. For a large backlog, `--commit-every N` commits roughly every N merges so an interrupted run keeps its completed work, and `--defer-fusion` skips the per-merge fusion invalidation and rebuilds derived rows once at the end of the run. The final pass covers both survivors and retired duplicates, so stale fusion rows on tombstones are removed. Do not run two write passes at once; the merge locks and the shared database do not benefit from parallel writers.

Accepting is separate from merging. A merge is transactional, moves evidence, retires the duplicate as a `merged` tombstone, and writes change events. Contacts move with the facility; a contact that duplicates the target's `(contact_type, value, source_record)` stays on the source tombstone so `uq_facility_contact_source` is never violated, and the merge resolution records the retained count. School and utility profiles behave the same way when the survivor already holds the same official code: the duplicate profile stays on the tombstone as evidence. Undo restores only the rows that actually moved. Rejected candidates are retained so the same pair is not re-queued for the same algorithm version.

The merge resolution stores the undo data: facility snapshots before and after, moved counts and IDs per child table, and the previous current-location state. Undo refuses rather than guesses when moved evidence has changed since the merge. A merged facility keeps its slug as an alias: `GET /v1/facilities/<old-slug>` resolves to the survivor and the web profile redirects to the canonical URL. UUIDs never change.

The EBEIS masterlist can list the same school under its official six-digit BEIS ID and a seven-digit level-prefixed variant (for example `403263` and `1403263`). The prefixed ID is treated as an alias only when the six-digit base row exists in the same release and the school-name keys match. The six-digit facility is the target; the prefixed row is kept as source evidence. Each twin merge is recorded as an accepted `deped_prefixed_school_id` candidate (`confidence 0.999`, reviewer `system:deped-prefixed-id`), and a merged profile backfill is recorded in `resolution["profile_backfill"]` so undo can reverse it or refuse if a later edit changed the value. Adapters mark prefixed rows `enrichment_only=True`, so the canonical row is always applied first.

`auto-merge-duplicates` is the older, narrower rule (exact normalized name plus a precise address/coordinate match). Use `consolidate-facilities` for whole-registry aggregation; it applies the strong-bridge and strong-edge clique rules above.

### Display-name casing

Some agency exports publish every facility name in capitals. The pipeline title-cases the canonical `display_name` at creation and update, and `normalize-display-names` applies the same rule to existing rows. Only fully uppercase names are changed; a mixed-case name keeps the spelling chosen by its source. Known abbreviations (`ES`, `IS`, `NHS`, `SHS`, `SPED`, `RHU`, `BHS`, `DOH`, `NCR`, …), Roman numerals, ordinals, single letters, alphanumeric codes (`R8`, `K12`) and consonant-only initialisms stay uppercase; ordinary words are title-cased and connectors such as `of`, `and`, `de` and `ng` are lowercased inside the name.

The source spelling is never lost. `official_name`, the raw source payload, `attribute_assertions.raw_value` and the source record are unchanged, so the profile can still show exactly what the agency published. A replacement character (`�`) already present in a source value is retained as-is; the pass changes casing only and never guesses the missing byte. The fusion pass never writes `display_name`; name changes are a separate canonical or backfill step.

Every backfilled row writes a `display_name_normalized` change event with the old and new value and `changed_by = system:display-name-normalization`. The pass is idempotent, includes merged tombstones so an undo restores a readable name, and supports batched commits.

```bash
uv run philfacilities-ingest normalize-display-names                 # dry run
uv run philfacilities-ingest normalize-display-names --apply --commit-every 5000
```

### Public slug normalization

Early bulk ingestion appended the reporting agency to every public slug (`-osm`, `-doh`, `-nha`, `-philhealth`). That identifies the dataset that first reported a place, not the facility. `normalize-facility-slugs` removes any known source suffix from a current facility slug and keeps the previous value in `core.facility_slug_aliases`, so old bookmarks, exports and API links still resolve to the same facility. Every rename writes a `facility_slug_normalized` change event. A genuine collision gets a numeric suffix (`-2`, `-3`); merged tombstones keep their slug because it is the redirect key.

```bash
uv run philfacilities-ingest normalize-facility-slugs --facility-type health_facility
uv run philfacilities-ingest normalize-facility-slugs --facility-type health_facility --apply --commit-every 5000
uv run philfacilities-ingest consolidate-numeric-slugs
uv run philfacilities-ingest consolidate-numeric-slugs --apply --commit-every 500
```

Run the pass per facility type after consolidation; each type can be verified independently, and `--commit-every` keeps completed renames if a large pass is interrupted.

`consolidate-numeric-slugs` handles the other slug artefact. Identically named rows received `-2`, `-3` … suffixes before consolidation; after a merge the survivor can keep the numbered slug while a merged tombstone holds the clean one, so the clean URL redirects. The pass transfers the clean base slug to the survivor only when the tombstone's `facility_merged_into` event confirms it owns that evidence, keeps the old numbered slug as a bookmark alias, and moves the tombstone to an internal `merged-…` slug. Genuine same-name facilities that remain separate are never renamed.

### Health classification cleanup

Two official evidence gaps can be repaired without re-running a release:

- `normalize-health-subtypes` maps raw health labels to the controlled `facility_subtype` vocabulary. A physical class (`Clinical Laboratory`, `Yakap Clinics`) is mapped; a hospital service level (`LEVEL 1`), a benefit package (`GAMOT Package Providers`, `Postpartum`) or a profession (`dentist`) is cleared from `facility_subtype` because it is not a facility class. An ambiguous label that does not establish one class (`INF/DISP`, a truncated `centre`) is also cleared rather than guessed from the facility name. The raw label remains on `health.profiles.facility_category` and the source record. Unrecognised labels are reported as `unmapped` and left unchanged rather than silently discarded.
- `refine-health-ownership` applies the DOH NHFR ownership sub-classification (`Local Government Unit`, `Single Proprietorship`, `Corporation`, …) to the specific `ownership_type`. It only refines a broad `GOVERNMENT_UNSPECIFIED` / `PRIVATE_UNSPECIFIED` / unknown value and never crosses the source's government/private major class; a conflicting major class is skipped and reported.

```bash
uv run philfacilities-ingest normalize-health-subtypes            # dry run
uv run philfacilities-ingest refine-health-ownership              # dry run
```

Health subtype families treat clinic, rural health unit and barangay health station as one outpatient service family, hospital and infirmary as inpatient, and laboratory and pharmacy as separate classes. An OSM `clinic` and a DOH `RURAL_HEALTH_UNIT` can therefore describe one facility, while a hospital is never merged with a clinic on a name match alone.

### School classification cleanup

OpenStreetMap education layers publish raw map tags (`school`, `university`, `kindergarten`) as the subtype. They also contribute school features whose tag belongs to another category (`PUBLIC_LIBRARY`, `LOCAL_GOVERNMENT_OFFICE`, `SPORTS_COMPLEX`) because the same place was imported through more than one layer. `normalize-school-subtypes` maps tags that establish a school class and clears foreign or non-school tags. It never guesses a school level from the facility name and never changes the facility type; the raw tag remains on the source record.

```bash
uv run philfacilities-ingest normalize-school-subtypes            # dry run
uv run philfacilities-ingest normalize-school-subtypes --apply
```

An unrecognised label is reported as `unmapped` and left unchanged. The same classifier runs inside the OSM education adapter, so a re-ingested release writes the controlled subtype directly.

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

### Enrichment-only releases

An adapter may set `FacilityCandidate.enrichment_only=True` when its rows add evidence to an existing facility rather than identify it. The pipeline then:

- matches by the adapter's stable agency entity ID (`source_entity_id`), never by name;
- may also match a health row by an exact DOH facility code already stored on another agency's health profile, so a second official health source links to the established facility instead of creating a duplicate; the link is recorded as `exact_doh_facility_code` with the matched code in its evidence;
- records source links, attribute assertions, release snapshots, and change events as usual;
- fills canonical `ownership`, `ownership_type`, `inclusion_class`, `facility_subtype`, and similar fields only when the current value is null/empty/`unknown`/`UNKNOWN`/`DISCOVERY_CANDIDATE`;
- never updates `display_name`;
- creates a missing school, health, or utility profile, but fills only missing or placeholder profile attributes and never changes an existing profile's `source_record_id`. A utility profile is keyed by facility and DOE facility code, so replaying the same release updates the same row.

The DepEd SY 2020-2021 Masterlist uses this mode to add sector evidence to 60,924 exact BEIS IDs without creating or renaming facilities. The DOH National Health Facility Registry uses the same mode for 29,779 existing DOH codes and creates new official facilities for its 15,020 unmatched codes. A contradictory non-placeholder value cannot downgrade an established classification. The NHFR load does not auto-merge by name or barangay; an official row without a matching DOH code becomes a new facility, and any same-name collision stays available for the separate match-candidate review workflow.

An adapter may also set `FacilityCandidate.link_only=True` for a stale or community-compiled snapshot that must never add registry records. The pipeline links by exact agency entity ID and stores the row as source evidence, but an unmatched ID is recorded as an `unmatched_link_only_row` quality issue instead of creating a facility. The OSMPH 2019 MaPaaralan point table uses this mode: it fills a missing school point and never creates, renames or reclassifies a school, because its IDs predate later closures, splits and renames. When a coordinate-only enrichment row becomes the current location for an address-only facility, the established address text is carried onto the new current row so the point does not erase the address; the prior location row remains as history.

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
| `--force-reapply` | Reapplies every parsed row even when its raw payload is unchanged; implies `--reprocess` |
| `source replay` | Verifies the preserved SHA-256 and reprocesses the existing release through the current parser |

`--reprocess` deliberately skips unchanged, already-linked rows so a replay cannot churn canonical names or classifications. When a new derived table is added (for example, the DOE utility profile), use `--force-reapply` to run those rows through the current parser and write the missing child records. This is an explicit operator decision: it re-asserts canonical fields and can let a competing source change an established value, so review the affected release and report afterwards. Re-running the same release without the flag returns to the normal unchanged-row skip.

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
