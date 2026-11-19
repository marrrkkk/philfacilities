# Data dictionary

**Version:** 2.0 — 18 November 2026
**API contract:** OpenAPI 3 at `/openapi.json`; interactive docs at `/docs`
**Bulk data:** `/v1/downloads/facilities.csv`, `facilities.parquet`, `schools.csv`, `health-facilities.csv`

This dictionary describes the values a consumer sees through the public API, bulk downloads, and facility profiles. It is descriptive; the OpenAPI document is the machine-readable contract for types and required fields, and `apps/api/philfacilities_api/taxonomy.py` is the source of truth for controlled vocabularies.

The public API is read-only. Records that fail the publication gate are absent: they are not returned with `null` fields, a redacted name, or a "private" marker.

## 1. Reading rules

1. **`null` means unknown or not supplied.** It does not mean zero, `false`, inactive, closed, or not applicable. An empty enrollment count is not `0`; an absent bed count is not `0`.
2. **A source publication date is not a retrieval date.** `source_published_at`, the reference period, `retrieved_at`, and `processed_at` are separate facts.
3. **`updated_at` is a PhilFacilities edit time.** It is not an agency's update time and does not imply that the facility changed in the real world.
4. **Codes are strings.** PSGC codes preserve leading zeros. Do not parse them as integers.
5. **Coordinates are WGS 84 (EPSG:4326) and may be approximate.** Always read `location.precision` before presenting a point as a building location.
6. **Registry presence is not operational status.** `active_in_registry` means the facility appears in a source registry. It does not prove the facility is open, staffed, licensed, or accepting patients today.
7. **One canonical facility can have several source records.** Source evidence is additive; it is not proof that the sources agree.
8. **Synthetic records are labelled.** `is_synthetic: true` means the record is generated for demonstration and testing. It is not an official government record. The working database contains no synthetic facilities.
9. **Source labels describe provenance, not authority.** OSM/HOT records are crowd-sourced map features. A PhilHealth accreditation confirms a time-bound benefit-package relationship, not a current service guarantee. BetterGov PSGC and population snapshots are supplementary mirrors, not the latest official PSA releases.
10. **Rights are separate from the code licence.** The repository is Apache-2.0; the data is not. Each dataset carries its own redistribution state and publication gate.

## 2. Canonical facility

Endpoint: `GET /v1/facilities/{facility_id}` (UUID or public slug)
List: `GET /v1/facilities`
Bulk: `GET /v1/downloads/facilities.csv`, `GET /v1/downloads/facilities.parquet`

Summary fields are returned by the list, map, and nearby endpoints. Detail adds the fields marked **detail only**.

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Stable PhilFacilities identifier. Not derived from a name or agency ID |
| `slug` | string or null | Human-readable URL identifier. Not an identity key |
| `display_name` | string | Name used for display. May be a normalized source value |
| `official_name` | string or null | **Detail only.** Name recorded as official by a source, when one exists |
| `facility_type` | controlled string | Broad category. See §3.1 |
| `facility_subtype` | string or null | Category-specific subtype. See §3.1 |
| `facility_kind` | controlled string | What the record represents. See §3.2 |
| `inclusion_class` | controlled string | Why the record qualifies for the registry. See §3.3 |
| `ownership` | `government`, `private`, or `unknown` | Broad source-reported ownership. `unknown` is not assumed to be public |
| `ownership_type` | controlled string | Specific owner type. See §3.4 |
| `operator_type` | controlled string | Specific operator type when a source states it. Ownership and operation are separate |
| `public_access_class` | controlled string | Conditions of entry. See §3.5 |
| `access_conditions` | string or null | **Detail only.** Source-stated access condition. Null does not imply unrestricted access |
| `record_status` | controlled string | Registry status. See §3.6 |
| `publication_status` | string | `public` or `internal`. Only public records appear in public responses |
| `is_synthetic` | boolean | True for generated demonstration records |
| `functions` | string array | Function codes recorded for the facility |
| `location` | object | Current location evidence. See §4 |
| `geography` | object | Resolved PSGC hierarchy from the selected geography release |
| `source_count` | integer | Number of linked source records that support this record |
| `updated_at` | timestamp | When PhilFacilities last changed the canonical record |
| `created_at` | timestamp | **Detail only.** When PhilFacilities created the canonical record |
| `school` | object or null | **Detail only.** Typed school profile. See §9 |
| `health` | object or null | **Detail only.** Typed health profile. See §10 |
| `accreditations` | array | **Detail only.** Dated accreditation rows |
| `contacts` | array | **Detail only.** Source-linked institutional contact channels. See §4.1 |
| `function_details` | array | **Detail only.** Function code plus source value, validity, capacity, and designation |
| `services` | array | **Detail only.** Service codes and names with validity |
| `roles` | array | **Detail only.** Owner, operator, manager, host, regulator, accreditor, and other roles |
| `relationships` | array | **Detail only.** Located-within, shared-site, hosted-at, parent, successor, replaced-by |
| `sources` | array | **Detail only.** Publication-cleared source evidence. See §5 |
| `quality` | object | **Detail only.** Identity status, precision, warnings, source count |

The per-facility CSV export is `GET /v1/facilities/{facility_id}/export.csv`. It is intentionally excluded from the OpenAPI schema and returns a small flat row: `id`, `display_name`, `facility_type`, `ownership`, `psgc_code`, `latitude`, `longitude`, `precision`, `synthetic`, `updated_at`. Use the bulk download for analytic work.

The bulk facility CSV and Parquet include the summary classification fields (`official_name`, `facility_kind`, `inclusion_class`, `ownership_type`, `operator_type`, `public_access_class`) and `postal_code`. Contacts are detail-only because a facility can have several source-linked channels of the same type.

## 3. Controlled vocabularies

`GET /v1/taxonomy` returns every controlled code below with a display label, plus the category-to-subtype mapping and contact types. It is the reference for clients; do not hardcode a second copy of the vocabulary.

### 3.1 Facility type and subtype

`facility_type` is one of:

```text
school, health_facility, government_office, community_facility,
emergency_facility, library, museum, social_welfare_facility,
public_market, transport_facility, utility_facility,
environmental_monitoring, public_space, cultural_facility,
agricultural_facility, justice_facility, housing_service,
other_qualifying_facility
```

`facility_subtype` values are category-specific. Examples: `PUBLIC_ELEMENTARY_SCHOOL`, `PUBLIC_SECONDARY_SCHOOL`, `PRIVATE_SCHOOL`, `HIGHER_EDUCATION_INSTITUTION`; `HOSPITAL`, `RURAL_HEALTH_UNIT`, `BARANGAY_HEALTH_STATION`, `CLINIC`; `BARANGAY_HALL`, `CITY_MUNICIPAL_HALL`, `NATIONAL_AGENCY_OFFICE`; `FIRE_STATION`, `POLICE_STATION`, `EVACUATION_CENTER`; `REGIONAL_LIBRARY`, `MUNICIPAL_LIBRARY`; `PUBLIC_MARKET`, `PUBLIC_SLAUGHTERHOUSE`. The full mapping is `CATEGORY_SUBTYPES` in `apps/api/philfacilities_api/taxonomy.py`.

A null subtype means the source did not establish one. Do not infer a subtype from a name. A facility with several compatible uses is represented by functions and relationships, not by inventing a new subtype.

For health facilities, `facility_subtype` is a controlled class: `HOSPITAL`, `INFIRMARY`, `RURAL_HEALTH_UNIT`, `BARANGAY_HEALTH_STATION`, `CLINIC`, `LABORATORY`, `DIALYSIS_CENTER`, `BIRTHING_HOME`, `PHARMACY`, or `OTHER_HEALTH_FACILITY`. A hospital service level (`LEVEL 1`), a PhilHealth benefit package (`GAMOT Package Providers`, `Postpartum`) or a profession (`dentist`) is not a facility class and must not be stored there; the raw label remains on `health.profiles.facility_category` and the source record. An unrecognised health label stays unmapped for review rather than being silently cleared.

For schools, raw map tags such as `school`, `kindergarten`, `university` and `college` are folded into `OTHER_SCHOOL` or `HIGHER_EDUCATION_INSTITUTION`. A tag that belongs to another category (`PUBLIC_LIBRARY`, `LOCAL_GOVERNMENT_OFFICE`, `SPORTS_COMPLEX`) is cleared rather than carried on a school. The pass does not infer a public/private sector or an elementary/secondary level from the name; those remain null unless an official source states them.

### 3.2 Facility kind

| Value | Meaning |
|---|---|
| `facility` | A named facility or service location. The default |
| `site` | A campus, compound, or landholding that can host facilities |
| `building` | A specific building |
| `facility_unit` | A counter, office, or service unit inside a host facility |
| `infrastructure_asset` | A physical asset such as a plant or station |
| `project` | A project record, not an operating facility |

A project is not an operating facility. A facility unit is not a separate building.

### 3.3 Inclusion class

| Value | Public? | Meaning |
|---|---|---|
| `GOVERNMENT_FACILITY` | Yes | Owned, operated, or mandated as a government facility |
| `PRIVATE_PUBLIC_SERVICE_PROVIDER` | Yes | Private or non-government provider of a meaningful public service, identified by an authoritative record |
| `PUBLIC_ACCESS_VENUE` | Yes | Civic, community, cultural, recreation, market, transport, or similar venue with an authoritative public function |
| `DISCOVERY_CANDIDATE` | Yes | A record whose ownership or qualifying class is not established by the source; published as unclassified, never as government-owned or privately owned |

Inclusion class is not a statement that the facility is open, licensed, or government-owned. A government regulator or publisher does not make a private provider a government facility.

### 3.4 Ownership and operator type

`ownership` is the legacy broad flag: `government`, `private`, or `unknown`.

`ownership_type` and `operator_type` share the same vocabulary:

| Group | Values |
|---|---|
| Public | `NATIONAL_GOVERNMENT`, `LOCAL_GOVERNMENT`, `GOCC`, `PUBLIC_EDUCATIONAL_INSTITUTION`, `OTHER_PUBLIC_BODY`, `GOVERNMENT_UNSPECIFIED` |
| Private | `PRIVATE_CORPORATE`, `PRIVATE_INDIVIDUAL_OR_PARTNERSHIP`, `NGO_NON_PROFIT`, `COOPERATIVE`, `RELIGIOUS_FAITH_BASED`, `PUBLIC_PRIVATE_JOINT`, `PRIVATE_UNSPECIFIED` |
| Unknown | `UNKNOWN` |

`GOVERNMENT_UNSPECIFIED` and `PRIVATE_UNSPECIFIED` are not placeholders for a guess; they record a source-stated broad class without a finer type. `PUBLIC_PRIVATE_JOINT` is not collapsed into either side. Ownership and operation can differ: a government-owned building may be operated by a private entity, and vice versa.

The DOH NHFR publishes an ownership sub-classification (`Local Government Unit`, `National Government`, `Single Proprietorship`, `Corporation`, …). `refine-health-ownership` applies it only within the existing government or private major class, refining `GOVERNMENT_UNSPECIFIED` / `PRIVATE_UNSPECIFIED` or an unknown value. It never changes a facility from government to private (or back) and never overwrites a more specific type established by another official source. The NHFR subclassification and DOH facility code remain on the health profile as evidence.

### 3.5 Public access class

| Value | Meaning |
|---|---|
| `PUBLIC_FREE` | Open to the general public at no charge |
| `PUBLIC_PAID_OR_CONDITIONAL` | Open to the public with a fee or stated condition |
| `SERVICE_USERS_ONLY` | Restricted to people using the facility's service |
| `APPOINTMENT_ONLY` | Entry requires an appointment |
| `MEMBERS_STUDENTS_ONLY` | Restricted to members or enrolled students |
| `STAFF_ONLY` | Not open to the public |
| `RESTRICTED` | Access is limited for another source-stated reason |
| `UNKNOWN` | No access class established. Not the same as open |

### 3.6 Record status and publication status

| `record_status` | Meaning |
|---|---|
| `active_in_registry` | Present in a source registry. Not proof of current operation |
| `inactive_in_registry` | Source marks the record inactive |
| `unknown` | Source does not state a status |
| `under_review` | Identity or evidence is under review |
| `merged` | Retired into another canonical facility. Detail is internal |

`publication_status` is `public` or `internal`. A merged record keeps an internal tombstone and never appears in a public response.

### 3.7 Coverage scope

Source-level coverage describes the source's scope, not a claim that every facility in that area is present.

| Value | Meaning |
|---|---|
| `NATIONAL_OFFICIAL_INVENTORY` | Official national inventory |
| `NATIONAL_PARTIAL` | National in ambition but incomplete |
| `REGIONAL` | One or more regions |
| `PARTICIPATING_LGUS` | Only LGUs that participate in the source |
| `SELECTED_LGUS` | A selected set of LGUs |
| `SINGLE_LGU` | One LGU |
| `DIRECTORY_SUBSET` | A directory subset, not a census |
| `DISCOVERY_LAYER` | Crowd-sourced or discovery layer |
| `UNKNOWN_COVERAGE` | Scope not established |

### 3.8 Roles and relationships

Role types: `OWNER`, `OPERATOR`, `MANAGER`, `HOST`, `LANDLORD`, `FUNDER`, `REGULATOR`, `LICENSOR`, `ACCREDITOR`, `RECOGNITION_AUTHORITY`, `AFFILIATOR`.

Relationship types: `LOCATED_WITHIN`, `SHARED_SITE`, `HOSTED_AT`, `PARENT_OF`, `SUCCESSOR_OF`, `REPLACED_BY`.

A regulator, licensor, accreditor, or funder is not an owner or operator. A recognition authority is not proof of operation.

### 3.9 Function codes

Function codes describe what a place is for. They are not service guarantees. Current codes:

```text
GOVERNMENT_ADMINISTRATION, PUBLIC_SERVICE_COUNTER, BARANGAY_HALL,
CITY_MUNICIPAL_HALL, PROVINCIAL_CAPITOL, COMMUNITY_ASSEMBLY,
MULTIPURPOSE_HALL, COVERED_COURT, SPORTS_RECREATION, PUBLIC_SPACE,
PUBLIC_LIBRARY, MUSEUM, ARCHIVE, CULTURAL_HERITAGE, EDUCATION,
TRAINING, HEALTHCARE, SOCIAL_WELFARE, RESIDENTIAL_CARE, PUBLIC_MARKET,
SLAUGHTERHOUSE, FOOD_SAFETY, POSTAL_SERVICE, TAX_ADMINISTRATION,
BUSINESS_ADVISORY, SOCIAL_SECURITY_SERVICE, LICENSING_SERVICE,
FIRE_RESPONSE, POLICE_SERVICE, EMERGENCY_RESPONSE, EVACUATION_SITE,
RELIEF_DISTRIBUTION, DRRM_COORDINATION, AIR_TRANSPORT, SEA_TRANSPORT,
FISH_PORT, LAND_TRANSPORT, WATER_SERVICE, WASTEWATER_SERVICE,
SOLID_WASTE_SERVICE, POWER_SERVICE, ENVIRONMENTAL_MONITORING,
AGRICULTURAL_SERVICE, FISHERIES_SERVICE, JUSTICE_SERVICE, LEGAL_AID,
HOUSING_SERVICE, OTHER_PUBLIC_SERVICE
```

## 4. Location and coordinate precision

| `location.precision` | Meaning |
|---|---|
| `gps_verified` | Independently verified GPS point |
| `field_verified` | Verified on the ground; the method may not be GPS |
| `source_gps` | GPS coordinates supplied by the source |
| `map_geocoded` | Coordinates derived by geocoding an address or from a map link |
| `barangay_centroid` | Area-level point for a barangay, not a building |
| `unknown` | Coordinates may exist, but no precision was supplied |

Additional location fields:

| Field | Meaning |
|---|---|
| `latitude`, `longitude` | Signed decimal degrees. Both are present or both are null |
| `method` | Source method string, when supplied |
| `address_text` | Source address text, not a normalized postal address |
| `postal_code` | Source-supplied postal code, when present. Never derived from PSGC or a geocoder |
| `psgc_code` | PSGC unit used for the location evidence. A string with leading zeros |
| `review_status` | `source_supplied` or another recorded review state |

A postal code is a source claim, not a normalized mailing address. Do not infer one from the PSGC hierarchy. A missing code means the source did not supply one; it is not an empty string or a zero.

A `psgc_code` can be source-supplied or derived. Derived values keep their evidence as an `AttributeAssertion`: source code/name resolution uses `psgc-resolution-v1`, while point-in-polygon map containment uses `psgc-spatial-v1`. By default a map-derived value fills a missing code, or replaces a code only with a more specific descendant; same-level and different-branch map conflicts are reported for review rather than silently overwritten. With the map-authoritative workflow (`--prefer-map`), the containing map unit replaces same-level or different-branch source codes; the original source claim remains in its assertion, and a map result that is less specific than the source code is not downgraded. A location outside every resolved OSM boundary remains unknown. The OSM boundary layer is internal reference geometry, not an official PSA boundary release.

Do not render a `barangay_centroid` or `map_geocoded` point as an exact facility pin. A map must keep a text result list available when tiles fail. Never invent coordinates for a record that has none.

### 4.1 Contacts

`contacts[]` is detail-only. Each row is one institutional channel supplied by one source record:

| Field | Meaning |
|---|---|
| `contact_type` | `phone`, `email`, `website`, `opening_hours`, or `other` |
| `value` | Source value, preserved as text |
| `label` | Optional source or adapter label, such as a branch line |
| `source_field` | Original source column or field name |
| `source_record_id` | Preserved source record that supplied the value |
| `valid_from`, `valid_to` | Source validity interval, when stated |
| `review_status` | Review state, normally `source_supplied` |

The API does not choose one phone number as the facility's truth. Several sources may publish the same channel, and conflicting values remain separate. A null or absent contact means the source did not supply one; it does not mean the facility has no phone or email.

Only institutional channels are published. Named staff contacts, personal mobile numbers, personal email addresses, and contact-person fields stay out of the public record. Accreditation phone, email, street address, and municipality are exposed inside `accreditations[]`, not copied into general facility contacts, because they describe that accreditation row.

`geography` resolves the PSGC code against the selected geography release and exposes `psgc_code`, `psgc_release`, the region, province, municipality, and barangay codes and names, and `urban_rural`. `urban_rural` is the PSGC barangay class normalised to `urban` or `rural`; a blank or `-` source value stays null. It describes the barangay, not the facility's catchment or an inferred settlement type. A missing name means the code did not resolve in that release; it is not a zero-length place.

## 5. Provenance and source releases

Source evidence: `GET /v1/facilities/{facility_id}/sources`
Field claims: `GET /v1/facilities/{facility_id}/assertions?attribute=`
Catalogue: `GET /v1/sources`, `GET /v1/sources/{source_id}`, `GET /v1/source-releases?dataset=`, `GET /v1/source-checks?dataset=`, `GET /v1/monitoring`

Each source evidence row describes one original record:

| Field | Meaning |
|---|---|
| `id` | PhilFacilities evidence identifier |
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
| `rights_status` | Dataset redistribution state at response time |
| `publication_status` | Dataset publication gate at response time |
| `license_identifier`, `attribution_text` | Recorded licence and attribution |
| `is_synthetic` | Whether the source dataset is synthetic |

Field-level assertions answer "which exact source record supplied this value?". They are returned only for facilities the caller may already see and only for rights-cleared, published releases. One field can have several claims; a conflict is evidence, not an automatic merge.

| Assertion field | Meaning |
|---|---|
| `attribute` | Canonical attribute claimed, for example `display_name`, `ownership`, `location.precision`, `function_code`, `school.offers_shs` |
| `source_field` | Original source column or field when recorded |
| `raw_value` | Value as supplied by the source; not normalized |
| `normalized_value` | Value after parser normalization |
| `transformation_version` | Parser or backfill version that produced the claim |
| `review_status` | Review state, normally `source_supplied`; `derived` for a deterministic crosswalk, hierarchy resolution, or map-boundary containment |
| `asserted_at` | When PhilFacilities stored the claim |
| `source` | The same source-evidence object returned by `/sources` |

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

`GET /v1/source-checks` is the append-only check ledger. `GET /v1/monitoring` returns the latest check per dataset, plus the latest release and next check time. A failed check is an access or freshness signal, not proof that the source data is wrong or that a facility closed.

### Redistribution status

| Value | Meaning | Public? |
|---|---|---|
| `approved_public_redistribution` | An explicit licence or terms instrument permits the recorded public redistribution scope | Yes |
| `approved_with_attribution` | An explicit licence, terms statement, government-work/public-interest basis, or other recorded instrument permits publication with attribution or conditions | Yes |
| `publicly_available_verified` | The exact release is publicly available and verified; no explicit prohibition was found; reviewed fields only, with provenance, attribution, and takedown-on-notice | Yes |
| `unknown` | No rights review has completed | No |
| `review_required` | Access, terms, or intended reuse remains unresolved | No |
| `restricted_non_redistributable` | Redistribution is prohibited, agreement-bound, or unresolved in a way that keeps the release internal | No |
| `denied` | The rights holder refused the recorded use | No |
| `expired` | A previously recorded permission is no longer valid | No |

Legacy spellings (`allowed`, `allowed_with_conditions`, `permission_required`, `restricted`, and `not_applicable`) are normalized for older fixtures. Current datasets use the states above. `publicly_available_verified` does not claim public domain and does not bypass the release publication gate. The existence of an API endpoint is not a grant of data rights. See [data policy](data-policy.md).

## 6. Coverage, statistics, and freshness

Statistics: `GET /v1/statistics`
Coverage: `GET /v1/coverage`

`/v1/statistics` reports published records only: facility totals, school and health counts, coordinate counts, precision distribution, region counts, inclusion-class, ownership-type, category, and access-class distributions, and the number of retained source releases.

`/v1/coverage` adds source-level context:

| Field | Meaning |
|---|---|
| `registry_records`, `published_records` | All canonical records in the registry and records currently visible publicly |
| `by_inclusion_class`, `by_category`, `by_subtype`, `by_ownership_type`, `by_access_class` | Public facility counts, each with `facility_count`, `published_count`, and `with_coordinates` |
| `by_region` | Counts by PSGC region prefix. Records without a resolved location remain outside this breakdown |
| `by_lgu_coverage` | Number of datasets at national, regional, participating-LGU, selected-LGU, and unknown scope, with dataset slugs |
| `source_coverage` | One row per dataset: coverage scope, latest release, reference period, retrieval time, parsed row count, publication state, rights status, freshness in days, and a stale flag |
| `coverage_stale_after_days` | Configured freshness threshold. The default is 365 days |
| `stale_source_count` | Number of datasets whose latest release is older than the threshold |
| `caveats` | Explicit limitations; the counts are not a real-world census |

Freshness is measured from `reference_period_end`, then `source_published_at`, then `retrieved_at`, in that order. Re-downloading an old directory does not make its information current. A stale flag is a prompt to recheck the source, not proof that a facility changed or closed.

`/v1/coverage` reports `registry_records` including internal candidates, while all breakdowns and `published_records` cover only publication-cleared records. The difference is not a hidden backlog of publishable facilities.

## 7. Identity matching and unmerged candidates

Preferred identity evidence, strongest first:

1. Exact source-specific stable ID from the same agency/source system.
2. Explicit official crosswalk or shared identifier.
3. Exact normalized name + same PSGC unit + compatible type, with address evidence.
4. Similar name + locality + address evidence, which produces a candidate only.
5. Conflicting IDs or distant coordinates, which remain unmerged and are retried automatically.

The deterministic matcher uses normalized names (case-folded, punctuation collapsed), the current PSGC unit, compatible facility type/subtype, and different source agencies. It creates candidates and merges only the exact normalized name + same PSGC + exact address rule. Everything less certain stays unmerged with its evidence and is retried when a newer release or stronger signal arrives; no human approval gate exists.

Endpoint: `GET /v1/quality/match-candidates?status=pending`
Detail: `GET /v1/quality/match-candidates/{candidate_id}`

| Field | Meaning |
|---|---|
| `candidate_key` | SHA-256 key for algorithm version + source record + proposed facility |
| `match_status` | `pending`, `accepted`, `rejected`, or `merged` |
| `match_method` | `exact_normalized_name_psgc_type` or `exact_normalized_name_geo` |
| `algorithm_version` | Matcher version. A new version may generate new candidates |
| `match_confidence` | Informational score; never an automatic-merge threshold |
| `source_record_id` | Source record being evaluated |
| `source_facility_id`, `source_facility_name` | Facility currently holding that source record |
| `candidate_facility_id`, `candidate_facility_name` | Proposed surviving facility |
| `source_agency_code`, `candidate_agency_code` | Agencies on each side |
| `evidence` | Normalized name, PSGC, type, address match, distance, snapshots, algorithm |
| `reviewed_at` | When a reviewer decided |
| `resolution` | Merge audit: moved record counts/IDs and facility snapshots |

The routine path is automatic: exact normalized name + same PSGC + exact address may be merged, and every less certain candidate stays `pending` with its evidence and is retried when new evidence arrives. `pending` is not a human approval queue. The explicit accept/reject/merge CLI commands exist for operator investigation and audit; they are not required before publication. Rejected candidates are retained so the same pair is not queued again for the same algorithm version. A merge retires the source facility into the candidate facility; the retired facility remains an internal `merged` tombstone, and change events preserve the audit.

## 8. Geography and PSGC releases

Endpoints: `GET /v1/geographies`, `GET /v1/geographies/{psgc_code}`, `GET /v1/geographies/{psgc_code}/facilities`, `GET /v1/geography-releases`, `GET /v1/geography-crosswalk?from_release=&to_release=`

| Field | Meaning |
|---|---|
| `psgc_code` | String code, leading zeros preserved |
| `geographic_level` | `region`, `province`, `municipality`, or `barangay` |
| `name` | Name in the selected geography release |
| `parent_psgc_code` | Parent code in the same release |
| `urban_rural` | Barangay PSGC class: `U` or `R` in the source unit; `urban_rural` on facility geography is normalised to `urban`/`rural` and stays null for `-` or blank |
| `release_label`, `reference_date` | Geography release identity and date |
| `is_synthetic` | Whether the release is synthetic |

A PSGC code is release-scoped. Names are not unique keys. When a code is renamed or its hierarchy changes, the crosswalk records `renamed`, `recoded`, `split`, `merged`, or `abolished` evidence. Do not assume a code means the same thing across every release.

The current release is the BetterGov Q2 2024 mirror (`PSGC-Q2-2024-BETTERGOV`), explicitly labelled as supplementary and not the latest official PSA release. The official PSA PSGC route remains skipped with a controlled machine-readable reason and automatic retry; the mirror stays labelled as a supplement.

## 9. School domain

Endpoints: `GET /v1/schools`, `GET /v1/schools/{facility_id}`, `GET /v1/schools/{facility_id}/enrollment`, `GET /v1/schools/{facility_id}/resources`
Bulk: `GET /v1/downloads/schools.csv`

| Field | Meaning |
|---|---|
| `deped_school_id` | DepEd school identifier, preserved as text |
| `sector` | Normalized school sector: `public`, `private`, or `suc_luc`; null when no source states it. The raw source value is preserved in the source record. |
| `school_management` | Source school-management class, such as `deped_managed`, `local_government`, or `sectarian` |
| `division` | DepEd schools division from the SY 2020-2021 masterlist |
| `district` | DepEd district from the SY 2020-2021 masterlist |
| `legislative_district` | Legislative district printed in the SY 2020-2021 masterlist |
| `settlement_type` | Source settlement class: `urban`, `partially_urban`, or `rural` |
| `offering_classification` | Combined offering category exactly as published, such as `purely_es` or `jhs_with_shs` |
| `offers_es`, `offers_jhs`, `offers_shs` | Whether the source says the school offers each level |
| `reference_school_year` | School year the profile describes |
| `enrollment_total` | Latest total when a matching observation exists; otherwise null |
| `enrollment[]` | Dated observations by school year, grade level, and sex |
| `resources[]` | Dated ICT/WASH/resource observations with numeric or text values |

Boolean school offerings are tri-state: `true`, `false`, or `null` for unknown. Do not treat null as `false`. Enrollment observations remain separate rows so historical years are not overwritten.

The SY 2020-2021 DepEd Masterlist supplies explicit sector evidence for 60,924 exact six-digit BEIS IDs. Its `Public` rows map to `ownership=government`, `ownership_type=GOVERNMENT_UNSPECIFIED`, `inclusion_class=GOVERNMENT_FACILITY`; `Private` rows map to `ownership=private`, `ownership_type=PRIVATE_UNSPECIFIED`, `inclusion_class=PRIVATE_PUBLIC_SERVICE_PROVIDER`; and `SUCs/LUCs` rows map to `ownership=government`, `ownership_type=PUBLIC_EDUCATIONAL_INSTITUTION`, `inclusion_class=GOVERNMENT_FACILITY`. The release is enrichment-only: it fills unknown values by exact BEIS ID and never renames a facility, replaces a school profile's established values, or downgrades an established classification.

BetterGov Open Data Portal dataset 41 republishes the same masterlist as a CC BY 4.0 CSV. It adds the school division, district, legislative district, settlement type, management class, and combined offering classification that are clipped or absent in the PDF. It is a second enrichment-only release keyed by the same six-digit BEIS ID. It never creates an unmatched school. Derived offering booleans are set only from the explicit combined categories; unknown categories stay null.

Most currently published schools come from the HOT/OSM education extract. They are crowd-sourced map features, not DepEd records: `deped_school_id`, `sector`, `school_management`, and the offering flags are normally null, and enrollment/resources endpoints return an empty list unless a public observation exists. DepEd EBEIS rows are published with institution-level fields, and school-head names are withheld. Of the 83,218 EBEIS IDs, 60,924 carry sector, management, division, district, legislative-district, settlement, and offering values from the 2020 masterlist; 11,614 newer six-digit IDs, 9,579 seven-digit private-school variants, and 1,101 five-digit IDs remain unknown. Do not interpret an OSM school as an official DepEd school.

## 10. Health domain

Endpoints: `GET /v1/health-facilities`, `GET /v1/health-facilities/{facility_id}`, `GET /v1/health-facilities/{facility_id}/licenses`, `GET /v1/health-facilities/{facility_id}/accreditations`, `GET /v1/accreditations`
Bulk: `GET /v1/downloads/health-facilities.csv`

| Field | Meaning |
|---|---|
| `doh_facility_id` | DOH source identifier, preserved as text |
| `facility_major_type` | NHFR major classification, such as Health Facility or Health Related Facility |
| `facility_type_detail` | NHFR facility type exactly as published, such as Hospital or Rural Health Unit |
| `facility_category` | Source category retained from the establishing release, not a normalized service capability |
| `ownership_subclassification` | NHFR ownership sub-classification, such as Local Government Unit or Corporation |
| `licensing_status` | NHFR licensing status: With License, Without License, or null when the source is blank |
| `bed_capacity` | Source bed count. Zero is a real source value; null is unknown |
| `licenses[]` | Time-bounded health licences with issuing authority and source status |
| `accreditations[]` | Time-bounded PhilHealth or other accreditation rows |

Licences and accreditations are many-to-many and time-bounded. An accreditation record is not a real-time guarantee that a service is available or reimbursable. `valid_until` may be null when the source does not supply it.

The public health set combines several sources: the DOH National Health Facility Registry (September 2026 snapshot, 44,799 facilities), HOT/OSM health features, an NHA GeoServer DOH health-facility layer, PhilHealth accreditation evidence linked where identity and location match, local-government health-centre directories, and other published health directories. The NHFR release is enrichment-only: it matches an existing facility by exact DOH facility code, fills only missing profile fields, and creates a new official facility only when the code is not present. It never renames an established facility or replaces an established classification. NHFR registry presence is not proof of current operation, and a blank licensing status stays null. PhilHealth rows describe time-bound benefit-package accreditation, not facility ownership or licensing. An OSM health feature is crowd-sourced and may be inactive, renamed, or misplaced.

### Accreditation records

`GET /v1/accreditations` supports `facility_id`, `q`, `provider_category`, `authority`, `sector_code`, `source_status`, `psgc`, `region_code`, `municipality_code`, `valid_on`, `limit`, and `offset`.

| Field | Meaning |
|---|---|
| `authority` | Accrediting body, normally PhilHealth |
| `provider_category` | Accredited provider category |
| `benefit_package` | Benefit package or service the accreditation covers |
| `accreditation_category` | Source category |
| `bed_count` | Source bed count for that accreditation, when stated |
| `sector_code` | Source sector code |
| `source_status` | Source-stated status |
| `valid_from`, `valid_until` | Validity interval. Either may be null |
| `telephone`, `email` | Contact channels stated on that accreditation row |
| `street_address`, `municipality` | Address stated on that accreditation row |
| `source_as_of`, `page_reference` | Source snapshot date and page reference |

`valid_on` filters to an accreditation valid on that date. The interval is not proof of current operation, staffing, or service availability. Accreditation contact and address fields are time-bound to the accreditation; they are not copied into the facility's general contacts.

## 11. Utility domain

The utility profile is exposed on the facility detail response as `utility`, for a facility whose `facility_type` is `utility_facility`. It is populated by the DOE existing-power-plant lists.

| Field | Meaning |
|---|---|
| `doe_facility_code` | DOE facility code, preserved as text |
| `resource_type` | Source resource label, such as Coal or Geothermal |
| `technology_type` | Source technology, such as Circulating Fluidized Bed (CFB) Coal |
| `connection_type` | Grid-connected or off-grid, as stated by the source list |
| `grid` | Source grid label: Luzon, Visayas, Mindanao, or off-grid |
| `owner_type` | DOE owner class, such as NPC or NON-NPC/IPP. Not a legal-ownership determination |
| `contract_type` | Source contract type when stated |
| `installed_mw`, `dependable_mw` | Source capacity ratings in megawatts; null when the source is blank |
| `number_of_units` | Source unit count |
| `date_commissioned` | Source commissioning date, preserved as text |

Capacity is a registry rating, not metered output. Inclusion in the DOE list is not evidence that a plant is currently operating. The profile does not replace the facility's function record, which carries the `POWER_SERVICE` designation and installed-capacity value asserted by the same release.

## 12. Population

Endpoint: `GET /v1/population?psgc=&level=&indicator=&q=&release_id=&limit=&offset=`

One row per published PSA 2024 Census observation.

| Field | Meaning |
|---|---|
| `psgc_code` | Geography code for the observation |
| `geographic_level`, `geographic_name` | Level and name from the linked geography release |
| `indicator_code`, `indicator_label` | Indicator identity |
| `value`, `unit` | Observed value and unit. Null is missing, not zero |
| `reference_date`, `reference_period` | Census reference date or period |
| `dimensions` | Additional source dimensions |
| `source_url`, `source_updated_at` | PSA/BetterGov source evidence |
| `retrieved_at` | When PhilFacilities acquired the snapshot |
| `release_id`, `release_label`, `dataset_slug` | Source release identity |
| `attribution_text` | Required attribution |

A population count is never facility capacity or service coverage.

## 13. Quality issues and status

Endpoints: `GET /v1/quality/summary`, `GET /v1/quality/issues`, `GET /healthz`, `GET /v1`

| `quality` field | Meaning |
|---|---|
| `identity_status` | `source_linked` when at least one source record is linked, otherwise `unverified` |
| `location_precision` | Current location precision |
| `warnings` | `no_coordinates`, `low_precision_location`, `synthetic_record`, `no_source_evidence` |
| `source_count` | Linked source records |

| Quality issue field | Meaning |
|---|---|
| `issue_code` | Stable code such as `parse_error`, `row_count_anomaly`, `policy_excluded`, `unresolved_source_record`, or `cross_source_match_candidate` |
| `severity` | `info`, `warning`, or `error` |
| `message` | Human-readable explanation |
| `details` | Structured evidence; shape depends on `issue_code` |
| `status` | `open` or `resolved` |
| `created_at`, `resolved_at` | Issue lifecycle timestamps |

Quality counts are measured from records. They are not an editorial trust score, and a clean quality summary does not prove the source is correct.

## 14. Change history

Endpoint: `GET /v1/facilities/{facility_id}/history`, feed `GET /v1/changes?since=&limit=&cursor=`

| Field | Meaning |
|---|---|
| `change_type` | `facility_created`, `attribute_updated`, `facility_merged_into`, `facility_merged_from`, `facility_merge_undone`, or another recorded event |
| `attribute_name` | Field changed, when the event is field-level |
| `old_value`, `new_value` | JSON values before and after. Either may be null |
| `source_record_id` | Evidence that caused the change, when applicable |
| `changed_at` | When PhilFacilities recorded the change |
| `changed_by` | Ingest parser version or review actor |

History is append-oriented. A correction creates a new event; it does not rewrite earlier evidence. `/v1/changes` is a global feed over public facilities and uses cursor pagination.

## 15. Pagination, errors, and caching

- Facility, school, and health lists are cursor-paginated: send `cursor`, read `next_cursor` and `has_more`. Cursors are opaque and capped in length.
- Reference tables (geographies, accreditations, population, source checks, source releases, quality issues, match candidates) use `limit` and `offset`.
- `limit` has a server-side maximum. Spatial bounding boxes and nearby radii are also capped.
- Errors use `{ "error": { "code", "message", "details", "request_id" } }`. `request_id` also appears in the `X-Request-ID` response header.
- Conditional JSON responses expose `ETag`; request timing is in `X-Response-Time-Ms`.
- CORS is restricted to configured web origins. There is no authentication for public reads, and no write or review action is exposed.

Full endpoint and filter reference: [API](api.md).

## 16. Current coverage caveats

Measured 18 November 2026: 273,369 canonical facilities, all public, 155,230 public with coordinates, 118,139 without. These counts change as sources are added or reviewed.

- Coverage counts describe processed source records, not the real-world facility universe. None of these counts establishes nationwide completeness.
- OSM/HOT facilities are crowd-sourced map features, not official DepEd, DOH, DILG, or LGU registries. Their coordinates are often bounding-box centres (`map_geocoded`) and their operational status is unknown.
- DepEd EBEIS rows without an exact SY 2020-2021 Masterlist match remain `DISCOVERY_CANDIDATE`/unclassified because the EBEIS result set has no reliable per-row sector field. The 60,924 exact matches now carry `ownership`, `ownership_type`, `inclusion_class`, and `school.sector` from the masterlist. Only institution-level fields are published; school-head names stay in the private source store.
- The BetterGov PSGC Q2 2024 snapshot is supplementary and not the latest official PSA release. PSA 2024 Census values come from saved BetterGov/OpenSTAT snapshots, not live PSA data.
- The NHA GeoServer DOH layer and PhilHealth accreditations are partial alternates for blocked official DOH sources, not replacements or completeness claims.
- LGU directories cover only the named city or municipality. Absence from them is not evidence that a facility does not exist.
- Source rights are separate from the Apache-2.0 code licence. No formal legal review has been completed; rights states record terms evidence and the enforced technical gate.
- Official PSA PSGC, DepEd Machine-Ready Files, DOH HFSRB licensed facilities, and other blocked sources remain blocked until access and reuse evidence exists. The DOH NHFR is published from a preserved official-export mirror with a pinned checksum; the official site still returns a Cloudflare challenge.
- Backups, monitoring, TLS/WAF, and external security review are not production-configured in this checkout; the map uses attributed demo tiles until a licensed provider is selected. See [operations](operations.md).

For the current source-by-source state, use `GET /v1/sources`, `GET /v1/monitoring`, and [Sources](sources.md). This dictionary does not freeze a source list that changes with every release.

## 17. Related documents

- [Data model](data-model.md) — canonical tables, provenance, constraints
- [API](api.md) — every endpoint and filter
- [Data policy](data-policy.md) — rights, privacy, publication gate
- [Sources](sources.md) — source register and acquisition state
- [Ingestion](ingestion.md) — how records become canonical
- [Testing](testing.md) — contract and data tests
