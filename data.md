# PhilFacilities — Complete Government Data Integration, Automated ETL, and Real Data Implementation

## 1. Objective

Transform PhilFacilities from its current synthetic-data implementation into a genuinely functioning, automatically maintained Philippine public facilities data platform.

The project must acquire real data from Philippine government agencies, preserve original source records, normalize different agency schemas, reconcile facility identities, maintain geographic references, track historical changes, validate data quality, and expose permitted records through the existing public API and web application.

This is not simply an API integration task.

**Build the complete data acquisition and management infrastructure that allows PhilFacilities to continuously collect, process, maintain, and publish Philippine public-facility information.**

The project should become a reliable public data resource for:

- Citizens looking for schools, hospitals, clinics, and other public facilities.
- Developers building applications using Philippine facility data.
- Researchers and academic institutions.
- NGOs and civil-society organizations.
- Journalists and public-interest investigators.
- Local government units.
- Disaster-preparedness and public-service organizations.
- Other Philippine civic-tech projects.

The primary product is the underlying data infrastructure. The directory and interactive map are applications built on top of it.

## 2. Existing project context

PhilFacilities already has an implemented application and architecture.

Inspect the actual repository before changing anything.

### Technology stack

- Monorepo.
- Next.js App Router, React, TypeScript, Tailwind CSS, and shadcn/ui.
- MapLibre GL JS.
- FastAPI and Python.
- PostgreSQL and PostGIS.
- SQLAlchemy 2 and Alembic.
- Polars, DuckDB, PyArrow, OpenPyXL, and appropriate document/geospatial processing libraries.
- Docker Compose.
- pnpm and uv workspaces.
- GitHub Actions.
- S3-compatible object storage where appropriate.

### Existing application

There is already a public directory, map, API, database, data model, and implementation tracker.

Do not rebuild working components unnecessarily.

The current production-facing application still uses synthetic records or previously prepared sample records. These must be replaced by legitimate, acquired, processed, and approved government data.

### Current data-source blockers

| Source | Current blocker |
|---|---|
| PSA PSGC | Official Q3 2026 workbook returned HTTP 403 behind Cloudflare. No original official workbook has been acquired. |
| DepEd | Official Machine-Ready Files require a human download and terms/feedback flow. Original school masterlist and enrollment files have not yet been acquired. |
| DOH NHFR | Public export returned HTTP 403. FOI disclosures establish availability of CSV/Excel and shapefile files, but applicable access and data-use conditions need review. |
| PhilHealth | Hospital accreditation PDF was previously parsed locally: 75 pages and 1,934 rows. Rights and republication have not been approved. |
| Rights approval | M1-12 remains in progress and M1-13 remains blocked. No complete source-by-source redistribution approval exists. |
| CHED | Public HEI directory exists; complete permitted bulk export or public API has not been verified. |
| TESDA | Public training-provider directories and statistics exist; complete permitted bulk export or public API has not been verified. |

Do not assume these blockers have disappeared. Recheck the current underlying sources.

---

# 3. Complete source inventory

This section defines the initial government data sources to investigate and integrate.

**Do not restrict implementation to these sources.** Discover additional official datasets and source systems wherever useful.

For each source, establish actual accessibility, actual fields, acquisition method, and reuse rights.

The links below identify known official sources, not a guarantee that every individual file or endpoint is currently accessible.

## 3.1 Primary facility registries

These provide the actual identities and characteristics of facilities.

### A. Department of Education — DepEd

**Official source links**

1. Machine-Ready Files:
   https://www.deped.gov.ph/machine-ready-files/

2. EBEIS School Masterlist:
   https://ebeis.deped.gov.ph/beis/reports_info/masterlist

3. DepEd Project Bukas:
   https://projectbukas.deped.gov.ph/

**Datasets to acquire**

| Dataset | Expected contents | Priority |
|---|---|---|
| School Masterlist / School Characteristics | School identities, school IDs, classifications, location and geographic attributes | Critical |
| School Enrollment | Historical enrollment by school and school year | Critical |
| School Facilities | Buildings, classrooms and school infrastructure | High |
| School Personnel | Teachers, school heads and personnel information | High |
| ICT Facilities | Computers, connectivity, and ICT resources | High |
| WASH and Utilities | Water, sanitation, toilets and utilities | High |
| Learner Data | Published school-level or aggregate learner information | Medium |
| Assessment Data | Official CRLA, ELLNA and NAT publications | Medium |

The current official Machine-Ready Files page advertises enrollment files from SY2017–18 through SY2024–25, school facilities, ICT, learner data, personnel, and WASH/utility information. It also lists assessment resources, including CRLA 2025–26.

Verify the latest releases again before acquisition.

**Important rules**

- Obtain original official files.
- Inspect every spreadsheet and sheet name.
- Discover exact original field names.
- Preserve original DepEd school IDs.
- Keep reference school years.
- Do not confuse school-year statistics with calendar-year statistics.
- Do not infer school coordinates from administrative geography.
- Review DepEd's applicable data terms and fair-use policy.
- Do not use third-party cleaned data as a substitute for the original official release.

### B. Department of Health — DOH

**Official source links**

1. National Health Facility Registry:
   https://nhfr.doh.gov.ph/VActivefacilitiesList

2. Health Facilities and Services Regulatory Bureau:
   https://hfsrb.doh.gov.ph/

3. List of Licensed Health Facilities:
   https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/

4. Official DOH website:
   https://doh.gov.ph/

**Datasets to acquire**

| Dataset | Expected contents | Priority |
|---|---|---|
| National Health Facility Registry | Hospitals, clinics, infirmaries, health centers and other registered facilities | Critical |
| Licensed Health Facilities | Official facility licensing and regulatory records | Critical |
| Hospital and Health Facility Mapping | Facility locations and geographic records, where obtainable | Critical |
| Facility Licensing Information | License or registration number, status and validity | High |
| Hospital Characteristics | Bed capacity, service capability and classification, where provided | High |

**Fields to investigate**

- Official facility ID.
- Facility name.
- Facility type.
- Facility subtype.
- Ownership.
- Hospital category and service capability.
- Bed capacity.
- License number.
- Licensing status.
- Validity period.
- Region.
- Province.
- Municipality/city.
- Barangay.
- Street address.
- Postal code.
- Telephone.
- Email.
- Latitude and longitude.
- Coordinate collection method.
- Other source-provided attributes.

Do not assume all fields are present in every NHFR export.

**Important access and rights rules**

Previous DOH FOI responses establish that downloadable CSV, Excel, and shapefile records have been provided.

Some releases required a signed Data Release and Use Agreement.

Investigate those existing disclosures and the exact agreement applicable to each dataset.

Do not bypass Cloudflare.

Do not assume an FOI response or a successful download authorizes unrestricted public redistribution.

### C. PhilHealth

**Official source links**

1. Accredited Healthcare Facilities:
   https://www.philhealth.gov.ph/partners/providers/facilities/accredited/

2. Status of Accreditation:
   https://www.philhealth.gov.ph/partners/providers/facilities/status.php

3. Official PhilHealth website:
   https://www.philhealth.gov.ph/

**Acquire and investigate all available provider categories.**

The official accredited-health-facility directory includes:

| Provider category | Priority |
|---|---|
| Hospitals and Infirmaries / Dispensaries | Critical |
| Freestanding Dialysis Clinics | High |
| Birthing Homes Providers | High |
| Maternity Care Providers | High |
| YAKAP Clinics | High |
| GAMOT Package Providers | High |
| Cancer Screening Test Providers | High |
| Cancer Treatment Facilities | High |
| Animal Bite Package Providers | High |
| TB-DOTS Centers | High |
| Drug Abuse Treatment and Rehabilitation Centers | High |
| DOH-Designated HIV Treatment Hubs | High |
| COVID-19 Testing Laboratories | Medium |
| Community Isolation Units | Medium |
| COVID-19 Home Isolation Benefit Package Providers | Medium |
| Family Planning Providers | High |
| Outpatient Malaria Package Providers | Medium |
| Oral Health Benefit Package Providers | High |
| Optometry Benefit Package Providers | High |
| Severe Acute Malnutrition Package Providers | High |
| Ambulatory Surgical Clinics | High |
| Ambulance Service Providers | High |
| Clinical Laboratories | High |
| Pelvic Ultrasound Providers | Medium |
| Postpartum Providers | Medium |
| Antenatal Providers | Medium |
| Transvaginal Ultrasound Providers | Medium |

Investigate whether the website currently exposes additional categories.

**Fields to extract where available**

- Facility name.
- Provider identifier.
- Provider category.
- Benefit package.
- Accreditation category or hospital level.
- Bed count.
- Government/private classification.
- Street address.
- Municipality.
- Telephone.
- Email.
- Accreditation expiry.
- Source publication or reporting date.

Some files are PDF documents rather than CSV or Excel. Implement category-specific parsers.

**Existing project work**

A PhilHealth hospital PDF has already been parsed locally:

- 75 pages.
- 1,934 extracted rows.
- Rights review incomplete.
- Parsed data remains unpublished.

Inspect the existing implementation and reuse its work.

Do not unnecessarily duplicate the download or parser.

Preserve source page references and the original provider text.

### D. Commission on Higher Education — CHED

**Official source links**

1. HEIDA:
   https://heida.ched.gov.ph/

2. Public HEI Directory:
   https://heida.ched.gov.ph/hei-directory

3. CHED official website:
   https://ched.gov.ph/

**Data to investigate**

- Higher education institution masterlist.
- HEI name.
- Institution identifiers.
- Ownership.
- Institution classification.
- Address.
- Region and geographic assignment.
- Available contact information.
- Institutional status.
- Recognized campuses and branches.
- Degree programmes and other publicly available programme information.

Investigate available downloadable files and official data access mechanisms.

CHED advertises public HEI directory functionality. Its HEIDA v2 announcement lists comprehensive API support as an upcoming feature. Do not invent a public API or claim that a bulk export exists without verifying it.

Do not make CHED a dependency for the first release.

### E. Technical Education and Skills Development Authority — TESDA

**Official source links**

1. TESDA Training Institutions directory:
   https://www.tesda.gov.ph/TVI

2. Assessment Centers:
   https://www.tesda.gov.ph/AssessmentCenters

3. TVET Statistics:
   https://www.tesda.gov.ph/About/TESDA/53

4. TESDA official website:
   https://www.tesda.gov.ph/

5. T2MIS:
   Discover its official access path through TESDA.

**Data to investigate**

- Registered training institutions.
- Training institution name and identifier.
- Location and address.
- Registered programmes.
- Qualifications.
- Training-provider relationships.
- Assessment centers.
- Approved programmes and their status.
- Enrollment and graduate statistics.
- Assessment and certification statistics.

**Important distinction**

TESDA's TVET statistics are not equivalent to a national facility masterlist.

A regional provider count cannot be converted into individual facility records.

Investigate the provider search system, T2MIS, and official downloadable lists for actual provider-level records.

Do not scrape restricted administrative systems.

---

## 3.2 Official geographic and administrative data

### A. PSA — Philippine Standard Geographic Code

**Official sources**

1. PSA PSGC page:
   https://psa.gov.ph/classification/psgc

2. Q3 2026 workbook:
   https://psa.gov.ph/system/files/scd/PSGC-3Q-2026-Publication-Datafile.xlsx

3. Official classification API guide:
   https://psa.gov.ph/classifications-api/access-guide

4. PSGC API base:
   https://classification.psa.gov.ph/psgc

**Required data**

- Regions.
- Provinces.
- Highly urbanized cities.
- Independent component cities.
- Component cities.
- Municipalities.
- Barangays.
- PSGC identifiers.
- Geographic hierarchy.
- Geographic name changes.
- Correspondence codes.
- Classification attributes.
- Historical code releases.

Preserve geographic codes as strings.

Implement versioned geographical records.

Do not overwrite previous PSGC releases.

**Current blocker**

The Q3 2026 workbook download previously returned HTTP 403 behind Cloudflare.

Investigate the current official API, alternative official publication locations, and authorized file acquisition options.

Implement a human-assisted workbook import if automated retrieval is unavailable.

Never bypass source protections.

### B. BetterGov Classification API

https://statistics.bettergov.ph/classification

API documentation:
https://statistics.bettergov.ph/api

**Available reference systems to investigate**

- PSGC.
- PSIC.
- PSOC.
- PCOICOP.
- PCPC.
- PSCC.
- PSCED.
- PSCCS.
- PTSCS.

The classification service documents public JSON endpoints for geographic and other classifications.

Use it as supplementary reference data and as a cross-check against official PSA releases.

Its saved versions are not necessarily the latest PSA releases.

Do not replace direct PSA ingestion with this service.

### C. Third-party PSGC API

https://psgc.billyjamesramos.com/docs

Useful endpoints to investigate:

- `/api/v1/meta`
- `/api/v1/regions`
- `/api/v1/provinces`
- Other documented geographic levels.

This is an independent third-party implementation.

Use it for comparison and validation only.

Never label it as an official PSA source.

---

## 3.3 Official population and statistical enrichment

These sources enrich the facility registry with demographics and statistical context. They are not facility registries.

### A. Philippine Statistics Authority — OpenSTAT

Official website:
https://openstat.psa.gov.ph/

API documentation:
https://openstat.psa.gov.ph/API-Documentation

Data access:
https://psa.gov.ph/how-acquire-data-psa

Investigate:

- Population.
- Census counts.
- Population by geographic level.
- Age and sex distributions.
- Household statistics.
- Poverty indicators.
- Education statistics.
- Health statistics.
- Labour and employment.
- Income and expenditure.
- Other statistics useful for facility-access analysis.

Preserve indicator definitions, units, reference periods, geographic disaggregation and original table IDs.

Do not claim that a national statistic supplies barangay-level detail unless the actual table supports it.

### B. PSA Census of Population

https://psa.gov.ph/

Find and verify the official 2024 Census of Population files and related geographic population tables.

Investigate the availability of:

- National population.
- Regional population.
- Provincial population.
- City and municipal population.
- Barangay-level counts, where officially released.
- Household counts.
- Other released demographic dimensions.

The population database should retain the census reference date and data release.

### C. BetterGov Philippine Statistics API

https://statistics.bettergov.ph/api

Base API:
https://statistics.bettergov.ph/api/v1

Documented routes include:

- `/coverage`
- `/topics`
- `/datasets`
- `/datasets/{id}`
- `/datasets/{id}/values`
- `/datasets/{id}/query`

Use it for supplementary PSA-derived statistics, not as the facility registry.

Investigate relevant geographic, demographic, education, health, poverty, labour and population datasets.

Build a source-to-indicator inventory before integrating any statistics.

Preserve PSA source table IDs and BetterGov snapshot metadata.

The API serves saved PSA OpenSTAT snapshots, not live PSA data.

---

## 3.4 Government open-data discovery sources

These are important for discovering further facility datasets and officially released records.

### A. Open Data Philippines

https://data.gov.ph/

Investigate:

- Dataset catalogue.
- Government publisher directory.
- Search functionality.
- Available dataset downloads.
- Dataset metadata.
- Original agency links.
- Available data formats.
- API documentation and access requirements.

A publicly listed dataset must not automatically be considered reusable.

Always identify its original government publisher.

### B. BetterGov Open Data Portal

Investigate the official public project and its dataset catalogue through:

https://github.com/bettergovph

Look for:

- Government facility datasets.
- Geographic references.
- Previously ingested public datasets.
- Original agency data.
- Source documents.
- Publicly available machine-readable records.

Avoid duplicating existing normalized datasets unless additional coverage, provenance, historical information or quality improvements are provided.

### C. Government open-data sources discovered through agency websites

Search for downloadable CSV, XLSX, JSON, XML, PDF, ZIP and shapefile resources.

Inspect the actual files rather than relying on agency descriptions alone.

---

## 3.5 Hazard, spatial and environmental enrichment sources

These are not primary facility-identity sources. They should be integrated as separate enrichment datasets after the facility registry is established.

### A. GeoRisk Philippines

Official source:
https://georisk.gov.ph/

Data and Methods:
https://georisk.gov.ph/geoanalytics/data-and-methods

HazardHunterPH:
https://hazardhunter.georisk.gov.ph/

Investigate:

- Existing school exposure layers.
- Existing health-facility exposure layers.
- Population exposure.
- Administrative boundaries.
- Hazard datasets.
- Geographic layer versions.
- Official source agencies behind individual layers.
- Public access and reuse conditions.

GeoRiskPH documents DepEd and DOH as sources of school and health-facility exposure information.

Treat these as supplementary reference layers and possible cross-validation inputs, not automatically as authoritative facility records.

### B. PHIVOLCS

Maps Portal:
https://maps.phivolcs.dost.gov.ph/

Official website:
https://www.phivolcs.dost.gov.ph/

Investigate:

- Earthquake catalogue.
- Volcano and seismic hazard layers.
- Fault information.
- Liquefaction.
- Ground shaking.
- Earthquake-induced landslide.
- Volcanic hazards.
- Other available geospatial products.

Use these datasets only where they provide a clear facility-enrichment use case.

Preserve attribution, map layer version and applicable reuse restrictions.

### C. PAGASA

Climate platform:
https://climgridph.pagasa.dost.gov.ph/climapv2/

Official website:
https://www.pagasa.dost.gov.ph/

Investigate:

- Historical climate datasets.
- Climate normals.
- Climate projections.
- Rainfall.
- Temperature.
- Wind.
- Storm surge.
- Other relevant hazard information.

Investigate download procedures, request requirements and reuse conditions.

### D. DENR — Mines and Geosciences Bureau

Official website:
https://mgb.gov.ph/

Investigate:

- Flood susceptibility.
- Rain-induced landslide susceptibility.
- Geohazard maps.
- Other officially available hazard layers.

Determine which datasets can be downloaded, whether they have GIS formats, and how their release dates and coordinate systems are documented.

**Important:** Do not implement hazard exposure calculations in the initial core registry unless the underlying layer is actually obtained and its use permissions are established.

---

## 3.6 Additional government facility sources to discover

Do not limit PhilFacilities to schools and healthcare institutions indefinitely.

Investigate these agencies for additional public-facility datasets.

These are discovery targets, not claims that a nationwide downloadable dataset or API already exists.

| Agency | Potential facility records |
|---|---|
| DILG | LGU offices, local government facilities, barangay references |
| Bureau of Fire Protection | Fire stations and other emergency-response facilities |
| Philippine National Police | Police stations and public safety facilities |
| BJMP | City and municipal jails and detention facilities |
| Bureau of Corrections | Correctional institutions |
| DSWD | Residential care facilities, social welfare institutions and service centers |
| DPWH | Roads, bridges, engineering offices and public infrastructure |
| DENR | Protected areas and environmental facilities |
| NAMRIA | Official geographic and cartographic data |
| NHA | Public housing and housing project locations |
| National Library of the Philippines | Public library facilities and related directories |
| National Commission for Culture and the Arts | Cultural facilities where relevant |
| Local Water Utilities Administration | Water districts and service-area information |
| MWSS | Water utility infrastructure and service-area information |
| Department of Transportation / LTFRB | Transport terminals, routes and transport facilities where available |
| Department of Information and Communications Technology | Public digital-service and community connectivity facilities where published |

For each agency, discover:

- Official data portal.
- Official source URL.
- Public directory.
- Dataset downloads.
- API documentation.
- Geographic coverage.
- Source identifiers.
- Available fields.
- Data freshness.
- Terms and conditions.

Only integrate datasets that genuinely improve the platform.

Do not turn PhilFacilities into an indiscriminate collector of unrelated government information.

---

# 4. Required source-by-source research

Before implementing new connectors, create a complete source inventory.

For every source listed above, establish:

| Field | Required investigation |
|---|---|
| Source ID | Stable internal name |
| Agency | Original government data publisher |
| Dataset | Exact dataset name |
| Official URL | Direct source link |
| Access type | API, JSON, CSV, XLSX, PDF, ZIP, shapefile, HTML, FOI, or manual |
| Reachability | Actual tested result, with timestamp |
| Authentication | None, token, account, session, or formal request |
| Acquisition procedure | Exact steps required to obtain the data |
| Dataset version | Latest source release successfully discovered |
| Reference period | Year, school year, quarter, or effective date |
| Format | Actual file format |
| Record count | Actual number of source records, if acquired |
| Schema | Actual column names and data types |
| Geography | Actual available geographic resolution |
| Coordinates | Presence, source and precision |
| Update pattern | Actual known release history |
| Historical availability | Older source releases |
| Data rights | Applicable use terms and agreements |
| Storage rights | Permission to retain original records |
| Processing rights | Permission to transform and normalize |
| Redistribution rights | Permission to expose records through the public API |
| Status | Proposed, discovered, accessible, acquired, validated, approved, published |

Do not mark a source as verified simply because its official homepage loads.

Do not mark a dataset acquired unless its actual file or API records have been obtained and inspected.

Do not invent endpoints, fields or record counts.

If a source is inaccessible, document the exact error and the alternative legitimate access route.

Save real evidence in the project's source documentation.

---

# 5. Source acquisition architecture

Implement a reusable source acquisition framework for all agency integrations.

The system must support:

- Public API ingestion.
- Authenticated API ingestion.
- Public file downloads.
- Official HTML directory extraction, where permitted.
- CSV parsing.
- Excel parsing.
- PDF extraction.
- Shapefile/GeoJSON ingestion.
- Human-assisted initial file acquisition.
- Historical source release imports.

Create source-specific connectors that implement a shared framework.

Every connector should be independent and testable.

An illustrative organization:

```text
apps/
  ingest/
    sources/
      psa/
        psgc/
        openstat/
      deped/
        school_masterlist/
        enrollment/
        facilities/
        personnel/
        ict/
        wash/
      doh/
        nhfr/
        licensed_facilities/
        facility_mapping/
      philhealth/
        hospitals/
        dialysis/
        maternity/
        yakap/
        other_providers/
      ched/
        hei_directory/
      tesda/
        providers/
        assessment_centers/
        tvet_statistics/
      georisk/
      phivolcs/
      pagasa/
      denr_mgb/
      discovery/
```

Adapt the actual location to the current repository structure.

Do not create an empty connector for every possible source just to make the directory look complete.

Implement functional connectors in priority order.

---

# 6. Automated source discovery and downloading

Automation is a primary project requirement.

The system should discover new government releases and ingest them automatically wherever authorized.

## 6.1 Release discovery

Implement the appropriate discovery mechanism per source:

- Official API metadata.
- Official release feeds.
- HTML page links.
- Published file indexes.
- HTTP headers.
- File checksums.
- Official publication dates.
- Documented download endpoints.

A source may require a custom discovery implementation.

Do not assume every agency follows the same publishing pattern.

## 6.2 Automated download

Where permitted, support:

- Scheduled checking.
- Conditional HTTP requests.
- `ETag`.
- `Last-Modified`.
- SHA-256 checksums.
- HTTP retry logic.
- Exponential backoff.
- `Retry-After`.
- File signature checks.
- MIME type checks.
- Download integrity checks.
- Changed-file detection.
- Release deduplication.

If a source returns HTTP 403, authentication errors or CAPTCHA requirements, record the blocker.

Never circumvent Cloudflare, access controls, CAPTCHA, human acceptance, or licensing requirements.

A normal browser download performed by an authorized operator should be importable through the same ingestion pipeline.

**Once the initial authorized data has been acquired, automate every subsequent operation that the source's permitted access method allows.**

## 6.3 Scheduling

Configure source checks according to actual publishing behavior.

Suggested initial monitoring:

| Source | Suggested discovery frequency |
|---|---|
| PSA PSGC | Weekly |
| DepEd | Monthly |
| DOH NHFR | Weekly |
| PhilHealth | Weekly |
| CHED | Monthly |
| TESDA | Monthly |
| PSA OpenSTAT | Weekly |
| GeoRiskPH | Monthly |
| PAGASA | Monthly |
| PHIVOLCS | Weekly |
| DENR-MGB | Monthly |

These are proposed check frequencies, not claims about agency release schedules.

Use configuration rather than hardcoding schedules.

Do not download unchanged large files repeatedly.

Do not publish a dataset simply because a new file was detected.

---

# 7. Data storage and historical releases

Preserve original government data separately from normalized records.

Recommended flow:

```text
Official source
      |
      v
Source discovery
      |
      v
Authorized acquisition
      |
      v
Immutable raw files
      |
      v
Source-specific parser
      |
      v
Staging database
      |
      v
Validation
      |
      v
Normalization
      |
      v
Entity resolution
      |
      v
Historical data model
      |
      v
Publication permission check
      |
      v
Public PostgreSQL/PostGIS database
      |
      v
FastAPI
      |
      v
Directory / Map / External API users
```

Each original source release should retain:

- Agency.
- Dataset.
- Source URL.
- Original filename.
- File format.
- File checksum.
- Retrieval timestamp.
- Source publication date, when known.
- Reference period.
- Release identifier.
- Original row count.
- Parsed row count.
- Accepted and rejected counts.
- Schema version.
- Rights status.
- Ingestion run ID.

Never overwrite historical source files.

A new source release must create a traceable version.

---

# 8. Normalization and facility identity

Maintain a canonical facility model, but do not flatten every agency's information into one massive table.

## Shared facility data

- Canonical PhilFacilities ID.
- Official facility name.
- Normalized display name.
- Facility type.
- Facility subtype.
- Ownership, when established by the source.
- Address.
- PSGC geographic relationship.
- Coordinates and precision.
- Source records.
- Data quality.
- Historical versions.

## School-specific information

- DepEd school ID.
- School classification.
- School management type.
- Education levels.
- Enrollment by reference school year.
- Personnel by reference period.
- School buildings and classrooms.
- ICT facilities.
- WASH and utilities.

## Healthcare-specific information

- DOH facility ID.
- Facility type.
- Hospital classification.
- Bed capacity.
- Licensing information.
- PhilHealth provider identifiers.
- Benefit-package categories.
- Accreditation status.
- Source-reported validity dates.

## Geography

Maintain versioned:

- Regions.
- Provinces.
- Cities.
- Municipalities.
- Barangays.

Use PSA PSGC codes as the primary geographic reference when an official source release is available.

Keep previous geographic classifications for historical records.

Preserve each original agency's location text and codes alongside normalized geography.

## Entity resolution

Implement deterministic matching using:

1. Exact official IDs.
2. Exact normalized names and geography.
3. Address similarity.
4. Telephone comparison.
5. Coordinate comparison where precision is reliable.
6. Manual review for ambiguous cases.

Never automatically merge different facilities based only on a similar name.

Keep matching confidence, evidence, and review history.

Do not use AI or LLM output as the authoritative basis of facility identity.

---

# 9. Data quality and reliability

PhilFacilities must expose the quality of the source information, not pretend that all government records are perfectly accurate.

Implement field-level provenance.

Distinguish:

- Officially listed.
- Cross-source matched.
- Independently checked.
- Field verified.
- Map geocoded.
- Barangay centroid.
- Unknown.
- Needs verification.

Coordinate precision and identity confidence must be separate.

For every source release, produce:

- Total records.
- Valid records.
- Rejected records.
- Duplicate source IDs.
- Missing facility IDs.
- Missing geographic assignments.
- Unmatched PSGC codes.
- Missing coordinates.
- Coordinate precision distribution.
- Invalid coordinate counts.
- Conflicting source attributes.
- Ambiguous facility matches.
- Rights and publication status.

Historical reference periods must be visible.

Do not represent an old school facilities dataset as current merely because it was downloaded today.

Missing information must remain null, not be filled with estimated or invented values.

---

# 10. Licensing and publication controls

Rights approval must be an enforced technical requirement.

For each dataset, distinguish:

- Access permission.
- Download permission.
- Storage permission.
- Transformation permission.
- Derived-data rights.
- Public redistribution permission.
- Attribution requirements.
- Retention restrictions.
- Personal-information restrictions.

Implement these rights states:

- `unknown`
- `review_required`
- `approved_public_redistribution`
- `approved_with_attribution`
- `restricted_non_redistributable`
- `denied`
- `expired`

Implement these publication states:

- `blocked`
- `internal_only`
- `quarantined`
- `approved`
- `published`

The public API must not expose records from a source whose rights do not explicitly permit publication.

Support dataset-level and source-release-level approvals where necessary.

Never automatically accept an agreement, submit an application in a person's name, or claim that a legal review is complete without evidence.

Update `DATA-LICENSES.md` with the documented status of every source.

---

# 11. Public API integration

The existing API must serve approved real data.

Maintain stable versioned endpoints.

Required endpoints should include:

```http
GET /v1/facilities
GET /v1/facilities/{id}
GET /v1/facilities/{id}/sources
GET /v1/facilities/{id}/history
GET /v1/facilities/nearby

GET /v1/schools
GET /v1/health-facilities

GET /v1/geographies
GET /v1/geographies/{psgc}/facilities

GET /v1/accreditations
GET /v1/sources
GET /v1/source-releases
GET /v1/changes
GET /v1/statistics

GET /v1/downloads/facilities.csv
GET /v1/downloads/facilities.parquet
```

Add filtering, pagination, geographic search, data-quality filters, source filters and reference-period filters.

Return source provenance and data freshness.

Support PostGIS bounding-box and proximity queries.

Do not expose restricted source attributes.

Maintain API documentation through OpenAPI.

Update the generated TypeScript API client if necessary.

---

# 12. Website and map integration

Keep the existing Next.js directory and MapLibre experience.

Replace synthetic results with actual approved API records.

The directory must distinguish facility types, ownership, sources, reference periods and data-quality warnings.

Facility profiles must expose the relevant source records.

The map must use actual coordinates with documented precision.

- Verified coordinates may be displayed as facility locations.
- Map-derived positions must be labeled accordingly.
- Barangay centroids must be visually distinguished from precise facility locations.
- Facilities without coordinates must still appear in directory searches.
- Never fabricate coordinates simply to place every facility on the map.

Keep the current design system and UI implementation.

Do not spend time redesigning the website while actual data ingestion is still incomplete.

---

# 13. Additional enrichment projects

Once the primary registries work, investigate these opportunities.

They should not block the initial school and healthcare release.

### Population and access

Connect PSA demographic records to facilities.

Possible future indicators:

- Population per facility.
- Population per facility type.
- Facility counts by municipality.
- Facility distribution by geography.
- Rural and urban facility availability.
- Population-to-bed ratios where supporting data exists.

Do not label simple population ratios as service accessibility or actual healthcare capacity.

### Education analysis

Use DepEd records to derive:

- School distribution.
- Enrollment trends.
- Teacher-to-learner ratios, where definitions allow.
- Classroom-to-learner ratios.
- School infrastructure coverage.

### Healthcare analysis

Use DOH and PhilHealth records to derive:

- Facility distribution.
- Bed counts.
- Accredited-provider distribution.
- Provider-package coverage.
- Population-to-facility ratios.

### Hazard and environmental exposure

Investigate GeoRiskPH, HazardHunterPH, PAGASA, PHIVOLCS, and DENR-MGB.

Possible future integrations:

- Flood exposure.
- Landslide exposure.
- Earthquake hazard.
- Storm surge.
- Severe wind.
- Climate information.

Do not expose a derived hazard indicator as an official engineering assessment.

Preserve the source layer version, coordinate reference system, and calculation methodology.

---

# 14. Monitoring and automation dashboard

Implement a source-monitoring mechanism.

For every source, show:

- Agency.
- Dataset.
- Official source URL.
- Access method.
- Last checked date.
- Last successful acquisition.
- Last successful ingestion.
- Latest discovered release.
- Latest published release.
- Current schema version.
- Latest record count.
- Rights status.
- Publication status.
- Ingestion status.
- Current warnings and errors.
- Next scheduled check.

Possible states:

- `healthy`
- `update_available`
- `ingestion_running`
- `ingestion_failed`
- `access_blocked`
- `awaiting_human_download`
- `awaiting_rights_review`
- `schema_changed`
- `stale`
- `restricted`

When a source is inaccessible, preserve the previous successful release.

When a new source fails validation, quarantine it and keep the old published dataset.

Provide actionable failure messages and notifications.

---

# 15. New source discovery must continue

The listed sources are the initial research inventory, not a restriction.

Implement a recurring source discovery process that identifies additional relevant government datasets.

Prioritize sources that can increase actual facility coverage or improve the reliability of existing records.

Investigate other agencies, public datasets, and official data portals.

For a newly discovered source:

1. Record its original agency.
2. Establish what data actually exists.
3. Test its reachability.
4. Obtain the actual schema.
5. Determine its geographic coverage.
6. Identify the source identifiers.
7. Test whether historical records exist.
8. Investigate its update pattern.
9. Review its data rights.
10. Determine whether it belongs in PhilFacilities.

Do not add a source just because an interesting dataset exists.

It must contribute useful facility records or defensible enrichment.

Do not invent an API for a source that only provides reports or a website.

---

# 16. Implementation milestones

Preserve existing completed milestones and tracker IDs.

Update the project tracker rather than creating a disconnected task list.

## M1 — Source inventory and acquisition

- [ ] Verify PSA official PSGC acquisition.
- [ ] Verify DepEd school masterlist acquisition.
- [ ] Verify DepEd enrollment acquisition.
- [ ] Verify DepEd facilities, personnel, ICT, and WASH acquisition.
- [ ] Verify DOH NHFR acquisition.
- [ ] Verify DOH licensed-facility data acquisition.
- [ ] Review PhilHealth source files and parser.
- [ ] Complete source-by-source rights evaluation.
- [ ] Investigate CHED and TESDA bulk access.
- [ ] Discover additional government facility sources.

## M2 — Acquisition infrastructure

- [ ] Build common source adapter framework.
- [ ] Build source registry.
- [ ] Build release discovery.
- [ ] Build automatic downloader for permitted sources.
- [ ] Build human-assisted import.
- [ ] Implement checksum verification.
- [ ] Implement immutable raw storage.
- [ ] Implement acquisition logs.
- [ ] Implement update monitoring.

## M3 — Source parsers

- [ ] PSA PSGC.
- [ ] DepEd school masterlist.
- [ ] DepEd enrollment.
- [ ] DepEd facilities.
- [ ] DepEd personnel.
- [ ] DepEd ICT.
- [ ] DepEd WASH.
- [ ] DOH NHFR.
- [ ] DOH licensing data.
- [ ] PhilHealth hospitals.
- [ ] PhilHealth other provider categories.

## M4 — Canonical data and history

- [ ] PSGC normalization.
- [ ] Canonical facility IDs.
- [ ] Original source ID preservation.
- [ ] Source-specific domain schemas.
- [ ] Historical source releases.
- [ ] Historical facility versions.
- [ ] Facility deduplication.
- [ ] Cross-agency entity matching.
- [ ] Coordinate provenance.

## M5 — Quality and rights controls

- [ ] Schema validation.
- [ ] Record-level validation.
- [ ] Geographic validation.
- [ ] Coordinate quality analysis.
- [ ] Source-to-database reconciliation.
- [ ] Legal publication gates.
- [ ] Quarantine and approval workflow.
- [ ] Data-quality reports.

## M6 — API and web integration

- [ ] Remove synthetic production data.
- [ ] Connect directory to actual records.
- [ ] Connect map to acquired coordinates.
- [ ] Show data sources and reference periods.
- [ ] Show source freshness and quality warnings.
- [ ] Add geographic filters.
- [ ] Add real public statistics.
- [ ] Add bulk data downloads.

## M7 — Production automation

- [ ] Configure scheduled source discovery.
- [ ] Configure authorized automatic updates.
- [ ] Configure source failure notifications.
- [ ] Implement historical release comparison.
- [ ] Implement ingestion recovery.
- [ ] Implement automated regression tests.
- [ ] Verify repeated ingestion is idempotent.
- [ ] Verify database backup and restoration.

---

# 17. Required final deliverables

Do not finish with only implemented code.

Produce these reports:

### 1. Complete government data source directory

List every discovered source with its official URL, dataset, access method, actual reachability, fields, geographic coverage, update information and rights status.

### 2. Acquisition report

For each acquired source:

- Actual source file.
- Actual release.
- Format.
- File size.
- Checksum.
- Actual record count.
- Reference period.
- Access procedure.
- Success/failure evidence.

### 3. Schema report

For every real dataset:

- Original sheet names.
- Original column names.
- Data types.
- Mapping to normalized columns.
- Missing-value statistics.
- Unique identifiers.
- Duplicate counts.

### 4. Data quality report

Report accepted, rejected, missing, duplicate, unmatched and invalid records.

For coordinates, provide precision breakdowns.

For cross-source matching, provide matched, unmatched and ambiguous counts.

### 5. Source-rights report

Show the actual legal and publication status for each dataset and release.

### 6. Ingestion documentation

Explain how each connector works, how to run it, how to update the data and how to recover from failures.

### 7. Real API examples

Provide actual approved response samples with real source provenance.

Never label synthetic fixture output as real government data.

### 8. Updated implementation tracker

Update existing milestone IDs and add newly discovered tasks.

Mark work complete only after its acceptance criteria have been satisfied.

---

# 18. Acceptance criteria

The implementation is successful when:

1. Synthetic production data is removed.
2. Actual original government source files or authorized API data have been acquired.
3. The complete source directory is documented.
4. All available source connectors are automated where permitted.
5. Human-assisted initial acquisition works where required.
6. Source releases are preserved immutably.
7. Original identifiers and provenance are retained.
8. Geographic normalization works.
9. Facility identities can be matched without destructive false merges.
10. Historical records are retained.
11. Data quality is measured and reported.
12. Redistribution permissions are enforced.
13. The public API returns only approved actual records.
14. The directory and map use the real published dataset.
15. Automatic source discovery and update monitoring work.
16. Failed ingestion does not corrupt an existing public release.
17. The documentation and tracker match the actual implementation.

**Do not claim complete nationwide coverage simply because the initial source files have been ingested. Report actual record counts and geographic coverage.**

# 19. Execution instructions for the coding agent

Work incrementally, but prioritize completing the end-to-end real-data pipeline rather than polishing isolated scripts.

First audit the existing repository and local files.

Check whether the already downloaded PhilHealth PDF, parsed rows, and any other source artifacts are still present.

Do not download files that are already available and validated.

Next, complete the official source acquisition and rights assessment. Implement a human-assisted import path wherever automated access is not permitted.

Then build the shared ingestion framework, source adapters, data normalization, quality validation, history, and publication controls.

Prioritize:

1. PSA PSGC.
2. DepEd.
3. DOH.
4. PhilHealth.

Continue investigating CHED, TESDA, GeoRiskPH and additional public facility sources without making them dependencies of the initial release.

Do not spend the entire implementation effort trying to overcome one HTTP 403 response.

Never circumvent access controls or accept agreements on the user's behalf.

Do not claim an API, field, dataset, or legal permission exists without evidence.

Keep the existing product functional while replacing synthetic data.

Keep the tracker current.

**Final objective: Build PhilFacilities as an automatically maintained, source-transparent and legally publishable Philippine public facilities data infrastructure platform, with a directory, map, and reusable public API.**