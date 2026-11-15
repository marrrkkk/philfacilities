# PhilFacilities data dictionary

**Version:** 1.1 — 15 November 2026  
**API contract:** OpenAPI 3 at `/openapi.json`; interactive docs at `/docs`  
**Publication status:** real records with a recorded publication decision are published for PhilHealth accreditations,
HOT/OSM health and education features, the BetterGov PSGC Q2 2024 mirror, and PSA 2024 Census
population snapshots obtained through BetterGov. Official PSA PSGC, DepEd Machine-Ready Files, DOH
NHFR/HFSRB, CHED, and TESDA data remain blocked or internal-only. The working database contains
**0 synthetic facilities**.

This dictionary describes the fields a consumer sees through the API, bulk downloads, and facility
profiles. It is descriptive: the OpenAPI document is the machine-readable contract for types and
required fields.

## 1. Reading rules

1. **`null` means unknown or not supplied.** It does not mean zero, `false`, inactive, closed, or
   not applicable. An empty enrollment count is not `0`; an absent bed count is not `0`.
2. **A source publication date is not a retrieval date.** `source_published_at`, the reference
   period, `retrieved_at`, and `processed_at` are separate facts.
3. **`updated_at` is a PhilFacilities edit time.** It is not an agency's update time and does not
   imply that the facility changed in the real world.
4. **Codes are strings.** PSGC codes preserve leading zeros. Do not parse them as integers.
5. **Coordinates are WGS 84 (EPSG:4326) and may be approximate.** Always read
   `location.precision` before presenting a point as a building location.
6. **Registry presence is not operational status.** `active_in_registry` means the facility
   appears in a source registry. It does not prove the facility is open, staffed, or licensed today.
7. **One canonical facility can have several source records.** Source evidence is additive; it is
   not proof that the sources agree.
8. **Synthetic records are labelled.** `is_synthetic: true` means the record is generated for
   demonstration and testing. It is not an official government record. The working production
   database has no synthetic facilities, so public responses report `synthetic: 0`.
9. **Source labels describe provenance, not authority.** OSM/HOT facilities are crowd-sourced map
   features. A PhilHealth accreditation confirms a benefit-package relationship, not a current
   service guarantee. BetterGov PSGC and population snapshots are supplementary mirrors, not the
   latest official PSA releases.

## 2. Canonical facility

Endpoint: `GET /v1/facilities/{id-or-slug}`  
Bulk: `GET /v1/downloads/facilities.csv`, `GET /v1/downloads/facilities.parquet`

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Stable PhilFacilities identifier. Not derived from a name or agency ID |
| `slug` | string or null | Human-readable URL identifier. Not an identity key |
| `display_name` | string | Name used for display. May be a normalized source value |
| `official_name` | string or null | Name recorded as official by a source, when one exists |
| `facility_type` | `school` or `health_facility` | Broad domain. A facility is not both in this release |
| `facility_subtype` | string or null | Source or normalized subtype. Controlled values vary by domain |
| `ownership` | `government`, `private`, or `unknown` | Source-reported ownership. `unknown` is not assumed to be public |
| `record_status` | controlled string | Registry status: `active_in_registry`, `inactive_in_registry`, `unknown`, `under_review`, or `merged` |
| `publication_status` | string | `public` records appear in the public API. `internal` records do not |
| `is_synthetic` | boolean | True for generated demonstration records |
| `created_at` | timestamp | When PhilFacilities created the canonical record |
| `updated_at` | timestamp | When PhilFacilities last changed the canonical record |
| `source_count` | integer | Number of linked source records that support this record |
| `location` | object | Current location evidence, or all-null values with `precision: "unknown"` |
| `geography` | object | Resolved PSGC hierarchy from the selected geography release |
| `quality` | object | Identity, precision, warnings, and source count |

## 3. Location and coordinate precision

| `location.precision` | Meaning |
|---|---|
| `gps_verified` | Independently verified GPS point |
| `field_verified` | Verified on the ground, method may not be GPS |
| `source_gps` | GPS coordinates supplied by the source |
| `map_geocoded` | Coordinates derived by geocoding an address |
| `barangay_centroid` | Area-level point for a barangay, not a building |
| `unknown` | Coordinates may exist, but no precision was supplied |

Additional fields:

| Field | Meaning |
|---|---|
| `latitude`, `longitude` | Signed decimal degrees. Both are present or both are null |
| `method` | Source method string, when supplied |
| `address_text` | Source address text, not a normalized postal address |
| `psgc_code` | PSGC unit used for the location evidence. A string with leading zeros |
| `review_status` | `source_supplied` or another recorded review state |

Do not render a `barangay_centroid` or `map_geocoded` point as an exact facility pin. A map must
keep a text result list available when tiles fail.

## 4. Provenance and source releases

Endpoint: `GET /v1/facilities/{id-or-slug}/sources`  
Catalogue: `GET /v1/sources`, `GET /v1/source-releases?dataset=`

Each source evidence row describes one original record:

| Field | Meaning |
|---|---|
| `agency`, `agency_code` | Publishing agency and short code |
| `dataset`, `dataset_slug` | Dataset name and stable slug |
| `release_id`, `release_label` | Specific source release used |
| `source_record_id` | Agency record key, preserved as text |
| `source_record_uuid` | PhilFacilities identifier for the preserved source row |
| `row_reference` | Row number or PDF page reference in the source file |
| `source_published_at` | When the agency published the release, if known |
| `reference_period_start`, `reference_period_end` | Period the data describes |
| `retrieved_at` | When PhilFacilities acquired the file |
| `processed_at` | When ETL finished processing the file |
| `match_method` | How the source record was linked to the canonical facility |
| `match_status` | Status of that link |
| `match_confidence` | Numeric confidence for the recorded link method |
| `is_synthetic` | Whether the source dataset is synthetic |

Release fields add:

| Field | Meaning |
|---|---|
| `sha256` | Checksum of the exact preserved file |
| `file_format`, `file_size_bytes` | Preserved object metadata |
| `row_count_parsed` | Rows successfully parsed, not rows in the real world |
| `ingestion_status` | `published`, `failed`, `skipped_duplicate`, or another run state |
| `terms_review_status` | Source-terms review state. `synthetic_demo` for fixtures |
| `parser_version` | Parser/schema version that produced the records |
| `redistribution_status` | Whether publication is permitted |

### Redistribution status

| Value | Meaning |
|---|---|
| `unknown` | No rights review has been completed. Do not republish |
| `review_required` | Access or reuse terms are unresolved; the source remains blocked |
| `restricted_non_redistributable` | Redistribution is prohibited or unresolved |
| `approved_public_redistribution` | Terms permit the recorded public redistribution scope |
| `approved_with_attribution` | Publication is allowed with the recorded attribution and conditions |
| `publicly_available_verified` | Exact release verified and publicly available; no explicit prohibition found; reviewed institutional fields only, with provenance, attribution, and takedown-on-notice |
| `denied` | A rights holder refused the recorded use |
| `expired` | A previously recorded permission has expired |

Legacy spellings (`allowed`, `allowed_with_conditions`, `permission_required`, `restricted`, and
`not_applicable`) are accepted by the shared vocabulary for older fixtures, but current datasets use
the states above. `publicly_available_verified` is a public-compatible state under
[`14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md); it
does not claim public domain and does not bypass the release publication gate. A download endpoint
returns only public facilities linked to a source release whose rights and publication states permit
redistribution. The existence of an API endpoint is not a grant of data rights.

### Current published and excluded sources

| Source | State | Notes |
|---|---|---|
| PhilHealth accredited healthcare facilities | `approved_with_attribution` / `published` | 25 provider-category PDFs, 24,986 accreditations, 13,546 linked facilities. Time-bound and benefit-package-specific |
| HOT/OSM health facilities | `approved_with_attribution` / `published` | 17,410 linked facilities. Crowd-sourced; coordinates are bbox centres (`map_geocoded`) |
| HOT/OSM education facilities | `approved_with_attribution` / `published` | 52,824 linked facilities. Crowd-sourced; not a DepEd masterlist |
| BetterGov PSGC Q2 2024 mirror | `approved_with_attribution` / `published` | 43,760 units; supplementary snapshot, not the latest official PSA release |
| PSA 2024 Census population via BetterGov | `approved_with_attribution` / `published` | 134,748 observations across 18 regional releases |
| DepEd EBEIS NCR | `approved_with_attribution` / source release `published`; canonical rows `internal` | 5,055 records. Current release published for institution-level fields with attribution; school-head names withheld. Canonical rows await field-level mapping/privacy review. |
| NLP public libraries | `approved_with_attribution` / `published` | 1,752 institution-level rows; personal librarian contacts withheld |
| NMP museums | `approved_with_attribution` / `published` | NMP-run regional, area, and site museums; directory subset |
| BIR RDOs | `approved_with_attribution` / `published` | RAO 006-2025; 128 RDO rows and 19 region headings; local OCR |
| PHLPost locator | `approved_with_attribution` / `published` | 1,272 factual locator facilities; copyright notice recorded; earlier release retained internally |
| DSWD CRCF | `approved_with_attribution` / `published` | 76 institutional facilities; no coordinates or operational status inferred |
| NMIS NARIS | `approved_with_attribution` / `published` | 357 accredited establishments; factual fields only; many operators private |
| Official PSA PSGC, DepEd Machine-Ready Files, DOH NHFR/HFSRB, CHED, TESDA | `review_required` / `blocked` | No publication until a verified release and a recorded publication decision exist |

## 5. Identity matching and the review queue

Preferred identity evidence, strongest first:

1. Exact source-specific stable ID from the same agency/source system.
2. Explicit official crosswalk or shared identifier.
3. Exact normalized name + same PSGC unit + compatible type, with address evidence.
4. Similar name + locality + address evidence, which produces a candidate only.
5. Conflicting IDs or distant coordinates, which require human review.

The deterministic matcher uses normalized names (case-folded, punctuation collapsed), the current
PSGC unit, compatible facility type/subtype, and different source agencies. It only creates a
candidate. It never merges facilities automatically.

Endpoint: `GET /v1/quality/match-candidates?status=pending`  
Detail: `GET /v1/quality/match-candidates/{candidate_id}`

| Field | Meaning |
|---|---|
| `candidate_key` | SHA-256 key for algorithm version + source record + proposed facility |
| `match_status` | `pending`, `accepted`, `rejected`, or `merged` |
| `match_method` | `exact_normalized_name_psgc_type` |
| `algorithm_version` | Matcher version. A new version may generate new candidates |
| `match_confidence` | Informational score; never an automatic-merge threshold |
| `source_record_id` | Source record being evaluated |
| `source_facility_id`, `source_facility_name` | Facility currently holding that source record |
| `candidate_facility_id`, `candidate_facility_name` | Proposed surviving facility |
| `source_agency_code`, `candidate_agency_code` | Agencies on each side |
| `evidence` | Normalized name, PSGC, type, address match, distance, snapshots, algorithm |
| `reviewed_at` | When a reviewer decided |
| `resolution` | Merge audit: moved record counts/IDs and facility snapshots |

Review decisions are applied by an operator through the ingestion CLI, not through the public
read-only API. Rejected candidates are retained so the same pair is not queued again for the same
algorithm version. Accepting a candidate records the decision; merging is a separate explicit
command that retires the source facility into the candidate facility. The retired facility remains
an internal `merged` tombstone, and change events preserve the merge audit.

## 6. Geography and PSGC releases

Endpoints: `GET /v1/geographies`, `GET /v1/geographies/{psgc_code}`,
`GET /v1/geography-releases`, `GET /v1/geography-crosswalk?from_release=&to_release=`

| Field | Meaning |
|---|---|
| `psgc_code` | String code, leading zeros preserved |
| `geographic_level` | `region`, `province`, `municipality`, or `barangay` |
| `name` | Name in the selected geography release |
| `parent_psgc_code` | Parent code in the same release |
| `release_label`, `reference_date` | Geography release identity and date |
| `is_synthetic` | Whether the release is synthetic |

A PSGC code is release-scoped. Names are not unique keys. When a code is renamed or its hierarchy
changes, the crosswalk records `renamed`, `recoded`, `split`, `merged`, or `abolished` evidence.
Do not assume a code means the same thing across every release.

## 7. School domain

Endpoints: `GET /v1/schools`, `GET /v1/schools/{id-or-slug}`,
`GET /v1/schools/{id-or-slug}/enrollment`, `GET /v1/schools/{id-or-slug}/resources`

| Field | Meaning |
|---|---|
| `deped_school_id` | DepEd school identifier, preserved as text |
| `sector` | Source sector value |
| `school_management` | Source management value |
| `annex_status` | Source annex status |
| `offers_es`, `offers_jhs`, `offers_shs` | Whether the source says the school offers each level |
| `reference_school_year` | School year the profile describes |
| `enrollment_total` | Latest total when a matching observation exists; otherwise null |
| `enrollment[]` | Dated observations by school year, grade level, and sex |
| `resources[]` | Dated ICT/WASH/resource observations with numeric or text values |

Boolean school offerings are tri-state: `true`, `false`, or `null` for unknown. Do not treat null
as `false`. Enrollment observations remain separate rows so historical years are not overwritten.

The currently published school facilities come from the HOT/OSM education extract. They are
crowd-sourced map features, not DepEd records: `deped_school_id`, `sector`, `school_management`, and
the offering flags are normally null, and enrollment/resources endpoints return an empty list unless
a public observation exists. The canonical DepEd EBEIS NCR rows remain `internal` and never appear in
these responses; their current source release is published only for institution-level fields. Do not
interpret an OSM school as an official DepEd school.

## 8. Health domain

Endpoints: `GET /v1/health-facilities`, `GET /v1/health-facilities/{id-or-slug}`,
`GET /v1/health-facilities/{id-or-slug}/licenses`,
`GET /v1/health-facilities/{id-or-slug}/accreditations`

| Field | Meaning |
|---|---|
| `doh_facility_id` | DOH source identifier, preserved as text |
| `facility_category` | Source category, not a normalized service capability |
| `service_capability_level` | Source capability string when supplied |
| `bed_capacity` | Source bed count. Null is unknown, not zero |
| `licenses[]` | Time-bounded health licences with issuing authority and source status |
| `accreditations[]` | Time-bounded PhilHealth or other accreditation rows |

Licences and accreditations are many-to-many and time-bounded. An accreditation record is not a
real-time guarantee that a service is available or reimbursable. `valid_until` may be null when
the source does not supply it.

The currently published health facilities come from the HOT/OSM health extract, with PhilHealth
accreditation evidence linked where names and locations match. `doh_facility_id`, bed capacity, and
DOH licences are normally null because no DOH NHFR/HFSRB source is published. PhilHealth rows
describe time-bound benefit-package accreditation, not facility ownership or licensing. An OSM
health feature is crowd-sourced and may be inactive, renamed, or misplaced.

## 9. Quality issues and status

Endpoints: `GET /v1/quality/summary`, `GET /v1/quality/issues`

| Field | Meaning |
|---|---|
| `issue_code` | Stable code such as `location_missing` or `cross_source_match_candidate` |
| `severity` | `info`, `warning`, or `error` |
| `message` | Human-readable explanation |
| `details` | Structured evidence; shape depends on `issue_code` |
| `status` | `open` or `resolved` |
| `created_at`, `resolved_at` | Issue lifecycle timestamps |

Quality counts are measured from records. They are not an editorial trust score, and a clean
quality summary does not prove the source is correct.

## 10. Change history

Endpoint: `GET /v1/facilities/{id-or-slug}/history`, feed `GET /v1/changes?since=`

| Field | Meaning |
|---|---|
| `change_type` | `facility_created`, `attribute_updated`, `facility_merged_into`, `facility_merged_from`, or another recorded event |
| `attribute_name` | Field changed, when the event is field-level |
| `old_value`, `new_value` | JSON values before and after. Either may be null |
| `source_record_id` | Evidence that caused the change, when applicable |
| `changed_at` | When PhilFacilities recorded the change |
| `changed_by` | Ingest parser version or review actor |

History is append-oriented. A correction creates a new event; it does not rewrite earlier evidence.

## 11. Pagination, errors, and caching

- Facility lists are cursor-paginated: send `cursor`, read `next_cursor` and `has_more`. Cursors are
  opaque and capped in length.
- `limit` has a server-side maximum. Spatial bounding boxes and nearby radii are also capped.
- Errors use `{ "code", "message", "details", "request_id" }`. `request_id` also appears in the
  `X-Request-ID` response header.
- Conditional JSON responses expose `ETag`; request timing is in `X-Response-Time-Ms`.
- CORS is restricted to configured web origins. There is no authentication for public reads in this
  release, but writes and review actions are not exposed.

## 12. Caveats

- Coverage counts describe processed source records, not the real-world facility universe. Of
  92,422 canonical facilities, 61,806 are public, 30,616 are non-public (including the 5,055
  DepEd EBEIS rows), and 44,751 public facilities have coordinates. None of these counts establishes nationwide
  completeness.
- OSM/HOT facilities are crowd-sourced map features, not official DepEd or DOH registries. Their
  coordinates are bounding-box centres (`map_geocoded`) and their operational status is unknown.
- The BetterGov PSGC Q2 2024 snapshot is supplementary and not the latest official PSA release.
  PSA 2024 Census values come from saved BetterGov/OpenSTAT snapshots, not live PSA data.
- Source rights are separate from the Apache-2.0 code licence. No formal legal review has been
  completed; the rights states record terms evidence and the enforced technical gate.
- Official PSA PSGC, DepEd Machine-Ready Files, DOH NHFR/HFSRB, CHED, and TESDA publication remains
  blocked until access and reuse evidence exists.
- Production backups, monitoring, TLS/WAF, and external security review are not configured; see the
  operations runbooks. The map uses attributed OpenStreetMap demo tiles; a licensed production tile
  provider is not selected.

## 13. Related documents

- [Data model](04-DATA-MODEL.md)
- [Source register](03-SOURCE-REGISTER.md)
- [Public API](06-PUBLIC-API.md)
- [Ingestion and ETL](05-INGESTION-ETL.md)
- [Quality and testing](10-QUALITY-TESTING.md)
- [Backup and restore runbook](operations/backup-restore-runbook.md)
