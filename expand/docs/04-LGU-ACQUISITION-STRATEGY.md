# 04 — LGU Facility and Local Provider Acquisition Strategy

## 1. Why LGUs are the critical source class

A meaningful share of qualifying facilities are locally owned, operated, managed, hosted, regulated or recorded by LGUs and their partner organizations. Local acquisition must cover government facilities and relevant private/non-government providers where the LGU holds authoritative records:

- barangay halls;
- city/municipal halls and satellite offices;
- multipurpose halls and civic centres;
- covered courts and sports complexes;
- plazas, parks, playgrounds, and open spaces;
- public markets and slaughterhouses;
- local health stations and social-welfare centres;
- evacuation centres and DRRM facilities;
- local libraries, terminals, water/sanitation sites, and other community assets.

There is no verified single national machine-readable inventory covering these facility types. DILG has said public markets are primarily within LGU jurisdiction. DILG has identified public-facility types in MC 2025-037, but that circular is not an inventory.

Republic Act 7160, Section 524 says each LGU shall periodically inventory infrastructure and other community facilities. Use that as a basis for asking LGUs for their existing inventories. Do not state that Section 524 requires those inventories to be published as open data or that a standard national schema already exists.

## 2. Acquisition channels

Use these channels in order of preference:

1. Official LGU open-data portal or downloadable dataset.
2. Official LGU department page with a machine-readable directory.
3. Official LGU Geoportal / GIS layer with metadata and permitted downloads.
4. Official LGU annual investment plan, CLUP, CDP, LDRRMP, DRRM plan, asset registry, or facility inventory where the facility list is explicit.
5. Public FOI request to the responsible agency/LGU, with a narrowly scoped data specification.
6. Direct LGU data-sharing request or voluntary contributor submission.
7. Manual research from official source pages, held in quarantine until field-level source and rights review.

Do not use third-party directories, Google Maps listings, or OpenStreetMap as the authoritative source for a government facility. They can identify candidate places for verification, not certify identity, ownership, operation, or public status.

## 3. LGU onboarding model

Create a repeatable process for each LGU:

1. Select target LGU and identify data custodian(s): City/Municipal Planning and Development Office, General Services Office/Property Office, Engineering Office, DRRMO, Market Office, Parks/Environment Office, Health Office, Barangay Affairs, or relevant department.
2. Search the LGU website for an inventory, GIS map, list of facilities, open-data page, CLUP/CDP, LDRRMP, annual report, or department directory.
3. Request the current inventory and previous versions if available.
4. Request existing identifiers and the administrative/geographic codes used.
5. Request whether each record is owned, operated, maintained, leased, or merely designated by the LGU.
6. Request the facility's operational status and the effective date of that status, if held.
7. Request coordinates and how they were collected, if available.
8. Review data terms and any confidentiality/security exclusions.
9. Import into source-specific staging, validate, and create match candidates.
10. Send the LGU a preview or discrepancy report when a contact channel exists.
11. Publish only records with a valid source basis and approved rights.

## 4. Standard LGU inventory template

Ask the LGU to provide records in CSV/XLSX or a GIS format such as GeoJSON, shapefile, or geopackage. Do not insist that an LGU create new data if it already has a usable inventory.

The implemented intake template is [`templates/lgu-inventory-template.csv`](../templates/lgu-inventory-template.csv), documented in [`14-LGU-INVENTORY-TEMPLATE.md`](14-LGU-INVENTORY-TEMPLATE.md). Validate a submission without importing it:

```bash
uv run philfacilities-ingest validate-lgu-inventory path/to/lgu-inventory.csv \
  --output var/reports/lgu-inventory-validation.json
```

The template uses controlled taxonomy values rather than free-text facility types, rejects personal/security columns, preserves 10-digit PSGC codes, and requires a source/reference date for every row.

Recommended fields:

| Field | Description | Required? |
|---|---|---|
| `lgu_facility_id` | Existing LGU identifier | Strongly preferred |
| `facility_name` | Official/local facility name | Yes |
| `facility_type` | Source's own type or subtype | Yes |
| `facility_subtype` | More specific source category | If available |
| `barangay` | Barangay name | Yes where known |
| `municipality_city` | City/municipality | Yes |
| `province` | Province | Yes where applicable |
| `region` | Region | If held |
| `street_address` | Street/landmark/address details | If held |
| `latitude` / `longitude` | Coordinates | If held |
| `coordinate_method` | GPS, survey, geocoding, centroid, unknown | If held |
| `owner` | Legal/public owner | If known |
| `operator` | Entity operating the facility | If known |
| `manager` | Entity maintaining/managing it | If known |
| `funding_source` | Funding relationship, if documented | If known |
| `facility_functions` | Other functions/designations | If known |
| `status` | Source-reported operational/lifecycle status | If held |
| `status_as_of` | Date the status is valid | If held |
| `capacity` | Facility-specific capacity and unit | If held |
| `date_established` | Opening/establishment date | If held |
| `last_inspected` | Latest inspection date | If held |
| `source_document` | Inventory file, page, sheet, URL | Yes |
| `source_reference_date` | Date or reporting period | Yes if available |

Capacity must be typed: seats, persons, beds, stalls, square metres, vehicles, classrooms, or other defined units. Never mix unlike capacity measures.

## 5. FOI request strategy

Do not file broad requests asking for “all public facilities” without specifying fields, categories, geography, period, and acceptable formats. Broad requests are harder to answer and may be denied as unclear or overly broad.

Recommended sequence:

- Request the most recent inventory already held by the LGU.
- Ask for CSV/XLSX or geospatial format if available.
- Ask for the inventory date and custodian department.
- Ask for existing identifiers, addresses, coordinates, owner/operator, and status.
- Ask which fields are restricted and whether a public-use/redacted version can be provided.
- Ask whether the LGU has earlier inventories so PhilFacilities can preserve history.

Use [10-ACQUISITION-REQUEST-TEMPLATES.md](10-ACQUISITION-REQUEST-TEMPLATES.md) as the starting point. Adapt the request to each LGU and avoid asking for personal information or sensitive security details.

## 6. Pilot strategy

Start with a small, diverse pilot rather than attempting to harvest all 1,600+ LGUs at once.

Suggested pilot selection criteria:

- one highly urbanized city;
- one component city;
- one municipality;
- one geographically remote/island LGU;
- one LGU already publishing GIS/open-data resources;
- one LGU with active DRRM-PULSE participation.

Pilot category coverage:

- barangay halls;
- city/municipal/barangay government offices;
- multipurpose halls and covered courts;
- public markets;
- parks/plazas;
- evacuation centres and DRRM resources.

The objective is to validate the inventory template, data quality rules, and contribution workflow—not to make statistical claims about national coverage.

## 7. Local data contribution portal or workflow

The existing application may later expose a controlled LGU contribution workflow. Do not make public user-submitted records authoritative automatically.

Suggested workflow:

`Draft submission → LGU/source identity check → schema validation → geography validation → duplicate match review → publication decision → approval → public release`

The publication decision follows the root [data inclusion and publication policy](../../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md). A verified public LGU release with no explicit prohibition may be published with reviewed institutional fields; an explicit restriction, ordinance condition, or personal/security limit still controls.

A contributor should be able to submit a new facility, update a current record, or report that a facility is closed/renamed/relocated. The submission must remain a proposed change until reviewed.

Record who submitted it, the organization/authority represented, supporting document, review status, and final decision. Provide an audit trail.

## 8. Avoiding false national coverage claims

Track LGU coverage explicitly:

- `NOT_CONTACTED`
- `SOURCE_DISCOVERY`
- `REQUEST_SENT`
- `DATA_RECEIVED`
- `SCHEMA_REVIEWED`
- `RIGHTS_REVIEWED`
- `PARTIALLY_PUBLISHED`
- `PUBLISHED`
- `DECLINED`
- `NO_DATA_HELD`
- `FOLLOW_UP_REQUIRED`

For each category and LGU, show the source date and the kind of evidence. “No public market record acquired” must never be displayed as “No public market exists.”

## 9. Research-backed source leads and important negative findings

The following resources should be checked as real acquisition channels. They are not interchangeable and do not constitute a complete national LGU facility registry. Re-test them during implementation and record the exact release/access evidence in `docs/03-SOURCE-REGISTER.md`.

### DILG DRRM-PULSE — participating LGU facilities

- Portal: https://drrm.ncr.dilg.gov.ph/
- Methodology: https://drrm.ncr.dilg.gov.ph/about
- Map: https://drrm.ncr.dilg.gov.ph/map
- Participating LGUs: https://drrm.ncr.dilg.gov.ph/lgus

The portal describes LGU-entered information that DILG field officers validate before publication. Its facility categories include evacuation centres, command centres, warehouses, barangay halls, health centres, fire stations and police stations, along with DRRM resources. The research snapshot showed participating-LGU coverage in DILG-NCR, not nationwide coverage. Inspect actual map/profile records and ask DILG-NCR for an authorized bulk export/API and redistribution terms. Do not scrape around access controls or imply nationwide completeness.

### DILG Subaybayan — evacuation-centre projects

- Portal: https://subaybayan.dilg.gov.ph/
- DILG FOI explanation: https://www.foi.gov.ph/agencies/dilg/updated-list-of-evacuation-center-in-the-philippines/

A DILG FOI response directs users to Projects → LGU Infrastructure Monitoring and Evaluation – 20% Development Fund (LIME 20), filtered by project type “Evacuation Center”, status and year. This is a project source, not proof that each completed project is currently an operating evacuation centre. Model it as a project/asset lead and link to a physical facility only after identity and operational status are independently established. The portal returned access restrictions in the research pass; test through normal authorized access.

### Barangay halls and public markets — no central list verified

- Barangay-hall FOI response: https://www.foi.gov.ph/agencies/dilg/list-of-barangay-halls/
- DILG barangay masterlist: https://dilg.gov.ph/page/Masterlist-of-Barangays/77
- Public-market FOI response: https://www.foi.gov.ph/agencies/dilg/list-of-public-markets-in-the-philippines-dilg-905479402880/
- DILG LGU directory: https://lgu201.dilg.gov.ph/

DILG's barangay masterlist is a geography/administrative reference, not a barangay-hall location inventory. The FOI response referred requesters to NAMRIA for possible hall addresses/coordinates. DILG's public-market responses say primary information is held by LGUs; no central national public-market masterlist was verified. Do not fabricate one from the barangay list. Acquire each inventory from the LGU/official GIS owner.

### Evacuation-centre custodian conflict

- DILG limited NCR inventory response: https://www.foi.gov.ph/agencies/dilg/lists-of-existing-evacuation-centers/
- DILG no-consolidated-file response: https://www.foi.gov.ph/agencies/dilg/updated-master-list-of-evacuation-center-in-the-philippines-dilg-902947380736/
- OCD response: https://www.foi.gov.ph/agencies/ocd/updated-list-of-evacuation-center-in-the-philippines-ocd-397929143969/

DILG previously supplied an NCR-only list and referred nationwide details to OCD/NDRRMC. A subsequent OCD FOI response said it did not have the requested updated list and referred requesters back to DILG/LGUs. Preserve this as an unresolved custody gap. The practical acquisition path is a combination of participating DILG-PULSE LGUs, Subaybayan project records, and direct LGU inventories, each labelled by source and coverage.

### Other official LGU acquisition routes

- DILG Masterlist of Barangays and LGU201 can identify LGUs and contact routes, not the facilities themselves.
- City/municipal planning offices may hold CLUP, CDP, land-use maps, development-infrastructure inventories and facility lists.
- General Services/Property Offices may hold government asset registers; ask for location, owner, operator, status and inventory date, while respecting security exclusions.
- Engineering Offices may hold public building, covered court, market, park and infrastructure records.
- DRRM Offices may hold evacuation-centre designation, capacity and inspection records.
- Market Offices, Parks Offices, Health Offices, Social Welfare Offices and Barangay Affairs units may be the actual custodians for their own facility classes.

### Legal basis

Republic Act 7160 (Local Government Code), particularly Sections 17 and 524, is useful for defining devolved services/facility types and asking for existing periodic LGU infrastructure/community-facility inventories: https://lawphil.net/statutes/repacts/ra1991/ra_7160_1991.html. Section 524 is an acquisition basis, not proof that every LGU has a standardized, digitized, public inventory or that the inventory is automatically open for redistribution.

### Pilot strategy adjustment

Add at least one DILG-PULSE participating LGU to the pilot cohort if its data can be lawfully reused, then select additional LGUs with independently published GIS/open-data resources. Keep the first pilot focused on actual inventories for barangay halls, multipurpose halls, covered courts, public markets, parks/plazas and evacuation centres. Measure each category's completeness separately.



## 10. Private and non-government facilities in LGU inventories

LGU acquisition is not limited to LGU-owned assets. Some local inventories may identify privately owned or operated facilities that serve a documented public/community function, participate in an official programme, or are subject to a relevant local licence/accreditation. Examples may include private public markets, private water/wastewater facilities, private community sports venues formally designated for public use, private social-welfare providers, and private facilities used as designated evacuation sites.

Request and preserve the relationship for each record: legal owner, operator, manager/maintainer, host/landlord, funder, regulator/accreditor, public-service function, public-access conditions, and effective dates. Do not infer ownership from the fact that an LGU lists, funds, regulates, accredits, leases or uses the location.

Do not use the LGU inventory request to collect every private business or building. A private facility must satisfy the inclusion test in `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`. Ordinary shops, restaurants, homes, malls and office buildings remain excluded unless a specific qualifying service unit or public designation is documented. A government service counter hosted in a private building should normally be modelled as a facility unit linked to a host site, not as proof that the entire host property is a public facility.

When the LGU reports a private provider, ask for the authoritative source/ordinance/licence/accreditation or designation and the exact fields that may be publicly redistributed. Keep private-provider counts separate from LGU-owned/operated facility counts.
