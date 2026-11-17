# 08 — Ownership-Inclusive All-Facilities Rollout Roadmap

## 1. Planning assumption

The core PhilFacilities platform has already been implemented. This roadmap is for expanding its data scope and operational coverage. Do not repeat completed frontend, map, API, repository, or deployment work unless the wider taxonomy requires a specific compatibility adjustment.

The roadmap is evidence-driven. Category priority depends on source acquisition, actual schema, data rights, coverage, and public value—not only the perceived importance of a facility type.

## 2. Rollout strategy

### Wave 0 — Generalize the existing registry for all facilities

**Goal:** Ensure the current application can represent qualifying government facilities, private public-service providers and public-access venues as first-class records in one registry.

Tasks:
- audit current facility schema and identify school/health assumptions;
- adopt the approved top-level taxonomy, inclusion classes and subtype dictionary;
- separate inclusion class, owner/operator/manager/host/funder/regulator/accreditor and public access;
- support multiple functions per physical facility;
- support sites, compounds, buildings, and facility units;
- add source-level and LGU-level coverage states;
- verify old school/hospital records remain compatible;
- keep current UI layout but make filters/navigation category-driven.

**Exit:** Existing records still work and the model can represent a barangay hall, covered court, private hospital, private school, accredited provider, public market, fire station, library, hosted service counter and evacuation centre without schema hacks or ownership confusion.

### Wave 1 — Add reachable official government and private-provider directories

Prioritize resources for which individual government or private-provider records or specific official files were identified, while requiring fresh acquisition and rights checks:

1. National Library of the Philippines public-libraries directory (December 2025 PDF; acquire and inspect latest official file; minimize personal contact fields).
2. DSWD CRCF directory and dated Standards Bureau lists; distinguish DSWD-operated, LGU-accredited, and private-accredited entities.
3. National Museum regional/area/site museum directory; verify operator/status of each site.
4. BIR RDO directory (RAO 006-2025 plus Citizen's Charter addresses); recheck for changes after publication.
5. DTI Negosyo Center locator; inspect actual records and host/operator relationships, not just the advertised 1,400+ count.
6. PHLPost post-office locator; distinguish post offices from hosted service counters.
7. PRC regional offices and offsite service centres; identify private/LGU host locations.
8. ECCD Council NCDC records; do not confuse the NCDC count with all public/private/LGU CDCs.
9. BFP logistical/station records after attachment scope and publication conditions are checked.
10. Geoportal layers only after metadata, date, owner, CRS, download and rights checks.
11. Continue DepEd, DOH, PhilHealth and PSA/PSGC pipelines under their source-specific publication decisions.

Do not publish any layer or PDF merely because it can be viewed. Conversely, a verified public release with no explicit prohibition may be published under the root [data inclusion and publication policy](../../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md). Record attribution and the publication basis; explicit restrictions still control.

**Exit:** At least two additional facility categories have genuine acquired, schema-inspected, publication-approved source data in the registry; where source records include both public and private providers, both are represented with distinct inclusion/ownership values.

### Wave 2 — Emergency, DRRM, and public safety facilities

Sources:
- DILG DRRM-PULSE participating-LGU facilities;
- OCD/NDRRMC and LGU DRRM evacuation-centre inventories;
- BFP fire stations;
- PNP police stations/precincts;
- fire hydrants where a current authoritative dataset exists.

Tasks:
- inspect DILG-PULSE public data and lawful export path;
- obtain current evacuation-centre inventories from OCD/NDRRMC and/or LGUs;
- seek a nationwide or regional BFP station list and determine volunteer brigade gaps;
- request official PNP station/precinct data from PNP/PROs;
- validate safety/security exclusions;
- distinguish an evacuation-centre designation from the physical hall/school/building itself.

**Exit:** Emergency/DRRM facilities are represented with explicit source coverage. No national-completeness claim unless the source supports it.

### Wave 3 — LGU community facilities

Categories:
- barangay halls;
- city/municipal/provincial halls and satellite service offices;
- multipurpose halls and civic centres;
- covered courts, gymnasiums, sports complexes;
- plazas, parks, open spaces, playgrounds;
- public markets, slaughterhouses, and municipal economic facilities.

Tasks:
- launch LGU source discovery and pilot;
- request existing Section 524 community-facility inventories;
- onboard a diverse pilot LGU cohort;
- ingest official LGU directories/GeoJSON/shapefiles/Excel files;
- add local data contribution and review workflow;
- build per-LGU and per-category coverage reporting.

**Exit:** Repeatable acquisition/validation exists for local inventories and at least one pilot cohort is published with clear local coverage limits.

### Wave 4 — Social welfare, culture, and knowledge (government and qualifying private/non-profit providers)

Categories:
- DSWD/LGU residential care facilities and social welfare centres;
- senior citizens centres;
- public libraries and branches;
- museums, archives, cultural centres, heritage facilities.

Sources:
- DSWD Standards Bureau and CRCF pages;
- National Library of the Philippines;
- NCCA/NHCP and LGU culture offices after source verification.

**Exit:** Source dates, government/private classification, accreditation/affiliation status, and location confidence are exposed.

### Wave 5 — Utilities, transport, environment, and agriculture (government and regulated private facilities)

Categories:
- water treatment/pumping/wastewater and sanitation facilities;
- solid-waste and materials-recovery facilities;
- public airports, ports, transport terminals;
- environmental field stations, protected-area facilities, nurseries;
- agriculture/fisheries extension centres, hatcheries, laboratories, public fish ports.

Sources:
- LWUA, MWSS, NWRB, LGU water/sanitation offices;
- DOTr, PPA, CAAP, MARINA, LGU transport offices;
- DENR/MGB/BMB/FMB/EMB;
- DA/BFAR/NMIS/NFA and LGUs.

**Exit:** Facility-level records and permissions are verified. Utility organizations, service territories, linear networks, and physical sites remain different entities.

### Wave 6 — Justice, correctional, and other specialized facilities

Investigate courthouses, public prosecution offices, jails, correctional institutions, and specialized national facilities. Conduct disclosure and security review before adding any precise location or attribute. Exclude sensitive operational details.

**Exit:** Only publicly appropriate, source-authorized fields are published.

### Additional resource leads identified in the research baseline

The expanded source register identifies additional directly useful resources: DILG DRRM-PULSE (participating LGU DRRM facilities); Subaybayan LIME 20 evacuation-centre project records; ECCD NCDC material; DSWD CRCF/accreditation directories; NLP public libraries; National Museum sites; BIR RDOs; DTI Negosyo Centres; PHLPost post offices; PRC regional/offsite centres; PPA ports; CAAP aerodromes; PFDA fish ports; NMIS NARIS; EMB air-quality monitoring stations; BMB PAIS; NHA MAPS; and per-layer Geoportal candidates. See `docs/03-SOURCE-REGISTER.md` and `docs/11-VERIFIED-SOURCE-DISCOVERY.md` for exact URLs and caveats.

These are source leads at different evidence grades, not a declaration that all have been acquired or approved. The registry is ownership-inclusive: regulated/accredited private providers are eligible when they meet the inclusion policy, while their records remain distinguishable from government facilities. For example, DRRM-PULSE covers participating LGUs; Subaybayan is project data; NMIS lists include private establishments; and old Geoportal layers may not be suitable as current records.

## 3. Priority scoring

Score each candidate dataset from 1–5 across:

- public usefulness (25%);
- source authority/reliability (20%);
- acquisition feasibility (20%);
- national or multi-LGU coverage potential (15%);
- freshness/update potential (10%);
- legal/publication clarity (10%).

Do not let a high public-value score override an inaccessible source or an explicit restriction. A verified public release with no explicit prohibition is not a hard blocker: record the `publicly_available_verified` decision, attribution and field limits. An unresolved access control, agreement, or genuinely unclear release remains a blocker until verified.

## 4. Recommended acquisition order

| Rank | Dataset/source | Reason |
|---:|---|---|
| 1 | Existing DepEd/DOH/PhilHealth/PSGC source pipelines | Retain already-built domain coverage and include both public and private records where source-backed |
| 2 | National Library public libraries directory | A concrete official directory with identifiers, types, addresses, and status |
| 3 | DSWD CRCF and LGU-accredited centre lists | Actual public facility directory with dated releases and facility details |
| 4 | Geoportal fire/government-office/market/police/health layers | Multiple facility categories in one spatial catalogue; layer-level age/rights checks required |
| 5 | BFP fire-station/logistical dataset | FOI-delivered report exists; coverage and volunteer-station gap must be documented |
| 6 | DILG DRRM-PULSE | Validated facilities for participating LGUs; useful evacuation/command/warehouse sources |
| 7 | Local LGU inventories for halls/courts/markets/parks | Essential to all-facility scope; no central national list verified |
| 8 | OCD/NDRRMC evacuation centres | High value, but current authoritative dataset access must be confirmed |
| 9 | PNP station data | Official nationwide bulk source not verified; direct request/source discovery needed |
| 10 | Utility, transport, environment, agriculture facility datasets | Expand after source discovery and schema/rights checks |

## 5. Release strategy

Use rolling releases rather than waiting for every category to be nationally complete.

Each release should publish:
- facility categories included;
- sources and source-release dates;
- geographic coverage;
- category-level record counts;
- data-quality summary;
- known exclusions/gaps;
- rights/attribution statements;
- API/data schema version.

A category can be published for selected LGUs while clearly labeled `SELECTED_LGUS` or `PARTICIPATING_LGUS`. Never hide limited coverage behind a nationwide map.

## 6. Success measures

Measure progress by:

- number of facility categories with approved source records;
- number of LGUs with source-backed records by category;
- percentage of records with source IDs;
- percentage of records with valid PSGC mapping;
- location-quality distribution;
- percentage with source reference dates;
- cross-source duplicate/match quality;
- share of sources with automatic update discovery;
- share of releases processed without manual row-level intervention;
- number of published source snapshots and historical changes;
- number of downstream API users where measurable.

Do not use raw total pin count as the primary success metric.


## 7. Ownership-inclusive rollout rule

No rollout wave is restricted to government ownership. When an authoritative source lists both government and private facilities, investigate and ingest both classes where they meet the product inclusion policy and rights conditions. Keep provider-specific sources such as PhilHealth, DOH/HFSRB, DepEd, CHED, TESDA, DSWD and NMIS in the same canonical registry, with private facilities tagged `PRIVATE_PUBLIC_SERVICE_PROVIDER`. Do not let a category wave become “complete” merely because government records were acquired if a significant private-provider population is part of that category and the source makes it accessible. Report the uncovered portion.

The acquisition order is based on evidence, source accessibility, rights and data quality—not a rule that public facilities are in-scope and private facilities are optional.
