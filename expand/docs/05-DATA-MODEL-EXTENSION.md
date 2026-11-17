# 05 — Data Model Extension for All Qualifying Facilities

## 1. Objective

Extend the existing implemented data model so it can represent all qualifying government and private facilities in one registry, without rebuilding the platform or forcing every source into school/hospital-specific structures. Private providers must be first-class records with explicit inclusion classes and ownership/operator relationships.

Inspect the current schema first. Reuse compatible tables and add migrations. Do not discard existing school and health data. Preserve API compatibility where possible; document any breaking contract change.

## 2. Core entity concepts

### 2.1 Facility

The canonical identity of a qualifying physical facility or facility unit, regardless of ownership. It is not the same as an agency, project, contract, building, or asset.

### 2.2 Site / compound

A parcel or geographic site that may contain multiple buildings or facility units. Example: a municipal hall complex.

### 2.3 Building

A physical structure. One building may host multiple services or facility functions. The available source may identify only a site or institution, so do not invent building detail.

### 2.4 Facility unit

A distinct operational or administrative unit within a site/building. Example: a public library branch inside a civic centre.

### 2.5 Function

The purpose/designation of a place. Example: an LGU multipurpose hall that also serves as an evacuation centre.

### 2.6 Service

A specific service delivered at a facility. Only publish services directly supported by authoritative records.

### 2.7 Infrastructure asset

A related but separate physical asset such as a bridge, road segment, drainage facility, flood-control structure, water network, or power line. It can relate to a facility but should not be counted as a facility by default.

## 3. Suggested logical model

Reuse existing table names where equivalent structures already exist. These are logical responsibilities, not a command to create duplicate tables.

| Entity/table | Responsibility |
|---|---|
| `facilities` | Canonical identity, display name, category, subtype, lifecycle status, inclusion class |
| `facility_sites` | Physical site/compound and site-level geometry/address |
| `facility_buildings` | Buildings within a site when separately identified |
| `facility_units` | Distinct facility/service units within sites/buildings |
| `facility_functions` | Many-to-many facility/function designations with validity periods |
| `facility_services` | Source-backed services offered at a facility |
| `facility_relationships` | Parent/child, located-within, co-located, shared-site, replacement/successor links |
| `facility_ownership` | Owner, ownership type, legal basis, validity dates, source |
| `facility_roles` | Owner/operator/manager/host/funder/regulator/licensor/accreditor relationships with source and effective dates |
| `facility_access` | Public access class, conditions, fees/restrictions where published, source and validity dates |
| `facility_operation` | Operator/manager, dates, source |
| `facility_access` | Public access class and conditions, source |
| `facility_locations` | Point/geometry, coordinate reference, precision, method, source |
| `facility_geographies` | Versioned PSGC assignments and original source geography |
| `facility_source_records` | Links canonical entities to source-specific records |
| `source_assertions` | Field-level claim/value from an exact source record/release |
| `facility_domain_attributes` | Typed school/health/DRRM/library/market/etc. domain attributes |
| `facility_accreditations` | Licenses, accreditations, permits and package-specific statuses |
| `facility_status_events` | Dated status/condition changes with evidence |
| `facility_change_events` | Auditable change history |
| `source_datasets` | Agency/dataset catalogue |
| `source_releases` | Immutable release metadata |
| `ingestion_runs` | Acquisition, parse, validation, publish logs |
| `data_quality_issues` | Field/record/release-level quality issues |
| `facility_match_candidates` | Cross-source matching candidates, evidence, score, review |
| `publication_decisions` | Rights and approval gate at dataset/release/field scope |

## 4. Important modeling rules

### 4.1 Separate owner, operator, manager, funder, regulator, and accreditor

Do not represent these roles with one agency field. A hospital may be privately owned and operated, licensed by DOH and accredited by PhilHealth; a public hospital may be owned by an LGU, operated by a hospital board, funded by multiple programmes, licensed by DOH and accredited by PhilHealth. These roles must not be conflated.

Use a role relationship with entity ID, role type, effective dates, and source evidence.

### 4.2 Multi-use facilities

A single physical record can have multiple functions:

- `BARANGAY_HALL`
- `COMMUNITY_ASSEMBLY`
- `EVACUATION_SITE`
- `RELIEF_DISTRIBUTION`

The designation should carry its own source, effective date, end date, capacity and status when supplied. Do not duplicate the physical facility just because a second agency uses a different type label.

### 4.3 Same site, separate facilities

A school and a covered court inside one campus may be two facility units on one site. Keep separate IDs if they are independently identified and operationally distinct. Use `located_within` or `shared_site` relationships.

### 4.4 Agency source records remain immutable

Keep original source IDs, original labels, original values, source release, sheet/page/row reference, and source URL. Normalized values must not replace the original values.

### 4.5 Temporal values

Store:

- source publication date;
- source observation/reference date;
- effective-from/effective-to dates where supplied;
- retrieval date;
- ingestion date;
- public release date.

Do not derive unknown dates from the download date.

### 4.6 Geometry

Support points, polygons, and lines separately. A park, campus, market compound, or government property may be polygonal. If only a point is available, do not invent a boundary. Preserve the source CRS and transformation history.

### 4.7 Capacity

Capacity requires a measure type and unit. Do not flatten 100 beds, 500 persons, 30 stalls, and 20 classrooms into one generic number.

### 4.8 Status

Keep operational/lifecycle status separate from legal license or accreditation status. Preserve the source status vocabulary.

## 5. Facility category extensions

Add typed/validated domain extensions only when an acquired source provides actual fields.

| Domain | Example source-supported attributes |
|---|---|
| Governance office | office/agency, office type, service counter, office hours if published |
| Community hall | hall type, capacity, covered/open status, designated functions |
| Education | school/institution ID, education levels, enrollment, facilities, school year |
| Health | NHFR ID, facility type, beds, service capability, license and validity |
| Emergency/DRRM | station/centre type, resource role, evacuation designation, capacity, validation status |
| Social welfare | centre type, residential/centre-based, accreditation, services, source date |
| Sports/recreation | court/gym/complex type, dimensions/capacity if published, management body |
| Public space | park/plaza/playground type, area/boundary if published, accessibility attributes if sourced |
| Library/culture | library ID, library type, affiliation/status, address, collections only if sourced |
| Public market | market type, LGU operator, address, building/stall data if published |
| Utilities | facility type, utility owner/operator, service area, capacity/plant type if published |
| Transport | airport/port/terminal identifier, operator, facility class, status |
| Environment/agriculture | facility type, protected-area/agency relationship, public service role |
| Corrections/justice | facility class, responsible public body, only non-sensitive public attributes |

## 6. Stable IDs and merge safety

Generate a stable internal ID for each canonical facility. Do not encode mutable name, location, category, or source row number into the ID.

A source record may be attached to a canonical facility only when a deterministic identifier or sufficiently strong reviewable evidence exists.

Store the match decision:

- `match_method`
- `match_confidence`
- `evidence_fields`
- `source_record_ids`
- `review_status`
- `reviewer/decision metadata` where applicable

Ambiguous matches remain separate until reviewed. Never silently merge solely by name similarity.

## 7. API compatibility implications

The existing API should gain generic facility fields and category-specific extension objects. Keep current school/health response fields compatible if feasible. Add normalized `category`, `subtype`, `functions`, `inclusion_class`, `ownership`, `operator`, `manager`, `host`, `regulator`, `accreditor`, `public_access`, `location_quality`, `source_records`, and `data_quality` fields. Support filters and counts by inclusion class and ownership.

Do not expose every raw agency column in the default facility response. Provide source-specific record/provenance endpoints or downloadable datasets for the full original schema when rights permit.


## 8. Ownership-inclusive registry fields and invariants

Every published facility must carry an `inclusion_class`:

- `GOVERNMENT_FACILITY`
- `PRIVATE_PUBLIC_SERVICE_PROVIDER`
- `PUBLIC_ACCESS_VENUE`

Use `DISCOVERY_CANDIDATE` only in internal staging/quarantine; it is not a public class. These classes live in the same `facilities` registry and public API. They must not become separate databases that duplicate records.

Also track independently:

- `ownership_type` and owner entity (government, private corporate, private individual/partnership, NGO/non-profit, cooperative, religious/non-profit, joint, unknown);
- `operator_type` and operator entity;
- manager/maintainer;
- host/landlord/site owner;
- funder/project sponsor;
- regulator/licensor/accreditor and the scope of its relationship;
- `public_access_class` and access conditions.

A private facility listed by DOH, PhilHealth, DepEd, CHED, TESDA, DSWD, NMIS, PPA, CAAP or another regulator may be included as a private provider when it satisfies the inclusion policy and rights checks. It must never be counted as government-owned merely because a government agency regulates or accredits it.

API aggregates must distinguish government facilities, private public-service providers, public-access venues and unknown ownership. A combined count must be labelled as all qualifying registry records, not as government facilities.

For hosted service points, model the government/private service unit and its host site/building separately. Do not create a facility record for the whole mall, office tower or campus unless the host itself independently qualifies under the inclusion policy.
