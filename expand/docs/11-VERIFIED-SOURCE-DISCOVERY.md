# 11 — Verified Source Discovery and Research Protocol

**Purpose:** Require the implementation/research agent to continue finding government facility resources beyond the current source register, while preventing guessed datasets, fake API claims, or unsupported coverage assertions.

## 1. Research objective

The source register is a researched starting point, not a closed list. The agent must discover additional resources across national agencies, GOCCs, LGUs, government GIS portals, FOI disclosures, official reports, and public-facing directories.

Research should cover government facilities, private/non-government public-service providers, and documented public-access venues. Research should answer:

1. Which facility categories and public/private provider networks does the source agency publish, regulate, license, accredit, operate or inventory?
2. Which official dataset, directory, map, API, report, or inventory actually contains individual facilities?
3. Can the actual records be acquired through an authorized route?
4. What are the actual source columns/fields and identifiers?
5. What geographic coverage and reference date do they contain?
6. Does the record identify ownership, operator, host/landlord, regulator, funder, or merely accreditation? Does it identify a government facility, private public-service provider, public-access venue, or only a discovery candidate?
7. Can PhilFacilities retain, transform, and publicly redistribute the record or permitted fields?
8. Is there a repeatable update mechanism?
9. What is missing, stale, restricted, or not verifiable?

## 2. Search strategy

Use multiple search patterns for each facility type and agency, not just the agency homepage:

- `site:agency.gov.ph facility type list`
- `site:agency.gov.ph directory facility locations`
- `site:agency.gov.ph dataset CSV XLSX SHP GeoJSON`
- `site:agency.gov.ph annual report facility inventory`
- `site:agency.gov.ph map GIS layer facility`
- `site:foi.gov.ph agency facility inventory`
- `site:geoportal.gov.ph facility layer`
- official circulars, Citizen's Charters, annual reports, GIS catalogues and data dictionaries.

Search exact terms in both English and agency/local terminology (e.g. evacuation centre/evacuation center, day care/child development centre, RHU, BHS, multipurpose hall, public market, satellite office, service centre).

Inspect links from the page to the actual file or record list. Do not stop at the top-level page.

## 3. Required evidence steps

For every candidate source:

### Step A — Official identity

- Identify the original agency or public body that owns/publishes the information.
- Record the agency, official page title, direct URL, and date checked.
- Determine whether the page is official or a third-party republisher.

### Step B — Actual record evidence

At least one of the following is required before calling it a data source:

- an actual official file was retrieved and inspected;
- an official public directory visibly contains individual records;
- an official API returned actual records;
- an official GIS layer exposes metadata and usable geometry/attributes;
- an FOI response explicitly supplied or confirms a specific dataset/attachment/access route.

A policy statement, source homepage, news article, project announcement, or map screenshot alone is not a dataset.

### Step C — Reachability test

Record:

- HTTP status/result or normal browser outcome;
- access method;
- file/response content type;
- whether the response is actual data or an HTML error/login/Cloudflare page;
- authentication/token requirements;
- CAPTCHA or human download flow;
- file size and SHA-256 if acquired;
- date/time tested.

Never bypass Cloudflare, CAPTCHA, authentication, human terms acceptance, or access controls. A normal authorised browser download is an acceptable human bootstrap method.

### Step D — Schema inspection

When actual data is obtained, record:

- file name and release;
- sheet/table names;
- exact original column names;
- inferred and declared types;
- row count;
- identifier uniqueness;
- missing values;
- duplicate counts;
- coordinates and coordinate provenance;
- geographic granularity;
- publication/reference period;
- source update date if supplied.

Do not copy columns from a third-party cleaned derivative and label them as official source fields.

### Step E — Ownership and facility semantics

Determine whether each record represents:

- a government-owned facility;
- a government-operated location in a leased/private building;
- an LGU-owned facility operated by a third party;
- a private provider accredited or licensed by government;
- a project or asset under construction;
- a geographic site/landholding/polygon;
- a service/route/system rather than a physical facility.

Keep owner, operator, manager, regulator, accreditor, funder and host/landlord distinct. Do not infer ownership from funding, accreditation, public use, or regulation.

### Step F — Rights review

Record separate decisions for:

- access;
- download;
- storage/retention;
- transformation;
- derived fields;
- public redistribution/API;
- when no explicit licence exists: the exact public route, verified release, and absence of an explicit prohibition;
- required attribution;
- personal/sensitive fields;
- deletion/expiry requirements.

If an explicit restriction applies, set `RESTRICTED_NON_REDISTRIBUTABLE`/`APPROVED_INTERNAL_USE` and block public release. If the position is genuinely unclear or the release has not been verified, set `RIGHTS_UNKNOWN`/`REVIEW_REQUIRED` and block public release. A verified, publicly available release with no explicit prohibition may be set to `PUBLICLY_AVAILABLE_VERIFIED` under the root [data inclusion and publication policy](../../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md), provided only reviewed institutional fields are published and provenance, attribution, and a takedown route are recorded.

### Step G — Freshness and coverage

Check the release date, reference date, and previous release(s). Establish whether the records are nationwide, regional, LGU-submitted, participating LGUs, a specific district, or a subset. Do not infer national completeness from a national-looking page.

## 4. Resource grades

Use these explicit grades in the source register:

| Grade | Meaning | Can be used in public API? |
|---|---|---|
| A — Official file acquired and schema inspected | Raw official file acquired, exact schema and record count known | Only after a publication decision and quality approval |
| B — Official API records tested | Real responses obtained and schema inspected | Only after API/publication decision and quality approval |
| C — Official directory records inspected | Individual records visible, bulk route not yet verified | Not until acquisition and a publication decision are recorded |
| D — Official FOI route or attachment identified | Agency disclosed or supplied data through FOI | Only within FOI/agreement terms |
| E — Official GIS catalogue/layer candidate | Layer listed; download/terms/metadata not fully established | No, until layer-level validation |
| F — Agency/source discovery target | Likely custodian but no usable records proven | No |

Keep resource grade separate from rights status and operational status. A high evidence grade does not by itself authorize publication; a low grade cannot be upgraded by the absence of a licence.

## 5. Continue discovery beyond the current register

The agent must research every facility family in `02-FACILITY-TAXONOMY.md`, including at least:

- central/local government offices and satellite service locations;
- barangay halls and local community centres;
- multipurpose halls, covered courts, civic centres and sports complexes;
- parks, plazas, playgrounds and public open spaces;
- public markets, slaughterhouses, cemeteries and municipal enterprises;
- schools, child development centres, universities and training centres;
- hospitals, RHUs, BHS, clinics and specialty centres;
- libraries, museums, archives and cultural centres;
- evacuation centres, DRRM offices, fire stations and police stations;
- social welfare and residential care facilities;
- ports, airports, ferry/transport terminals and service stations;
- public water, wastewater, waste-management and utility facilities;
- environmental monitoring stations, protected-area visitor/management facilities, nurseries and research stations;
- public agriculture/fisheries post-harvest facilities, fish ports, warehouses and laboratories;
- courthouses, jails and correctional facilities, subject to security limits;
- other government-owned/operated public-service facilities identified during research.

Search agency-specific custodians, attached agencies, GOCCs, regional offices, local offices, LGU GIS pages, annual reports, public FOI records and Geoportal layers.

## 6. Prioritize high-value resources

Prioritize candidates using:

1. Officialness and authority of source.
2. Individual facility-level records (not just aggregate counts).
3. National or multi-LGU coverage.
4. Stable source identifiers.
5. Useful location/address/coordinates.
6. Recent reference date and repeatable updates.
7. Access method realistically usable by an independent project.
8. Storage/transformation/redistribution rights.
9. Clear ownership/operator semantics.
10. Public value and category gap in the existing registry.

A source with an old but downloadable layer may be less useful than a current city-level official inventory. State this tradeoff explicitly.

## 7. Discovery report format

For every newly discovered source, append this record:

```yaml
source_id: agency.dataset
agency: Original public publisher
resource_name: Exact source title
official_url: https://...
source_type: api | file | directory | gis_layer | report | foi | lgu_inventory
resource_grade: A | B | C | D | E | F
access_result: success | partial | blocked | browser_only | request_required | unknown
access_method: ...
release_date: ...
reference_period: ...
coverage: national | regional | selected_lgus | single_lgu | unknown
record_count: null
schema_status: uninspected | inspected
fields_verified: []
rights_status: unknown
publication_status: blocked
ownership_semantics: ...
update_mechanism: ...
limitations: []
next_action: ...
last_checked_at: 2026-11-15
```

Use the current date when executing future research; the example date is a schema example.

## 8. Negative research results are valuable

When a custodian says a list is not held, a dataset is not available, only a subset is held, or an API does not exist:

- retain the official response URL;
- record the date and exact scope;
- record the referred custodian;
- record what the agency does hold, if any;
- do not continue asserting that the agency has the dataset;
- redirect acquisition to the cited custodian or the LGU level.

Examples already found include DILG responses for public markets, barangay halls and evacuation centres. These negative findings are part of the source register, not disposable research notes.

## 9. No unverified claims

Do not:

- invent an endpoint or response schema;
- claim a downloadable national dataset from an agency homepage;
- claim an API because a site is interactive;
- treat a PDF list as automatically current;
- treat a 2003 Geoportal layer as current;
- treat an FOI request status as successful data delivery;
- infer all facility attributes from one source;
- claim national completeness without a universe/denominator;
- put private licensed/accredited entities in government-facility counts;
- publish personal, sensitive, or security-relevant attributes unnecessarily.

## 10. Required ongoing output

Keep `docs/03-SOURCE-REGISTER.md`, `DATA-RIGHTS-REGISTER.md`, `planning/TRACKER.md`, and this research log synchronized.

Every research session must report:

- sources newly discovered;
- sources whose actual records were tested;
- files/API responses acquired;
- exact fields/row counts inspected;
- access blockers and negative findings;
- rights questions remaining;
- next high-value source targets.

Do not mark the source discovery milestone complete while unresearched facility categories remain. The register should grow as real evidence is found, not as speculative agency names are added.


## 8. Private facility source discovery

The agent must actively search for authoritative private-provider datasets alongside government asset inventories. Include private facilities where government agencies publish facility-level records as regulator/licensor/accreditor or where a reliable public authority lists the facility for a relevant service. Priority families include private schools, higher-education institutions, health facilities, PhilHealth-accredited providers, registered TVET providers, accredited social-welfare centres, regulated utilities, ports/airports/terminals, licensed food/agriculture facilities, and private/non-profit public cultural/community venues.

For every private-provider source, verify the exact facility-level record, regulatory/provider relationship, validity/status field, source date, geography, owner/operator if available, and permitted public fields. A company registration, general business permit, map listing or accreditation at organization level is insufficient unless it ties to an identifiable qualifying physical facility.

Do not treat all businesses, malls, restaurants, offices, factories, warehouses or buildings as facilities. A private host building may be represented as a host/site only when necessary to locate a separately qualifying service unit. Apply the binding inclusion policy in `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`.
