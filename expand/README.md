# PhilFacilities — All Qualifying Facilities Expansion Plan

> **A national, source-linked registry of qualifying facilities across the Philippines, regardless of ownership: government facilities, private public-service providers, and documented public-access venues.**

**Plan version:** 3.0 — ownership-inclusive facility scope  
**Research baseline:** 15 November 2026  
**Purpose:** Expand an already-built PhilFacilities application into an all-facilities data platform.  
**Implementation assumption:** The core website, map, API, database, repository, design system and deployment architecture already exist. This plan is not a rebuild plan.

## Start here

Read the connected documents in this order:

1. [Product scope and principles](docs/01-PRODUCT-SCOPE.md)
2. [Facility taxonomy](docs/02-FACILITY-TAXONOMY.md)
3. [Inclusion and ownership policy](docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md) — binding criteria for qualifying government and private facilities.
4. [Government and provider source register](docs/03-SOURCE-REGISTER.md) — official sources for government facilities and authoritative directories of qualifying private providers, plus portals, FOI disclosures, GIS layers and discovery targets.
5. [LGU facility acquisition strategy](docs/04-LGU-ACQUISITION-STRATEGY.md)
6. [Data model extension](docs/05-DATA-MODEL-EXTENSION.md)
7. [Ingestion and versioned release operations](docs/06-INGESTION-AND-RELEASES.md)
8. [Coverage and data quality](docs/07-COVERAGE-AND-QUALITY.md)
9. [Rollout roadmap](docs/08-ROLLOUT-ROADMAP.md)
10. [Data governance and rights](docs/09-DATA-GOVERNANCE.md)
11. [Data inclusion and publication policy](../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md) — canonical rule for verified, publicly available sources.
12. [Acquisition request templates](docs/10-ACQUISITION-REQUEST-TEMPLATES.md)
13. [Verified source discovery protocol](docs/11-VERIFIED-SOURCE-DISCOVERY.md) — mandatory research method for finding and validating more resources.
14. [Implementation tracker](planning/TRACKER.md)
15. [Source rights register](DATA-RIGHTS-REGISTER.md)
16. [Agent instructions](AGENTS.md)
17. [Changelog](CHANGELOG.md)

## Product decision — ownership-inclusive scope

PhilFacilities is **not limited to government-owned facilities**. It is a single national registry of all *qualifying* facilities, regardless of ownership or operator. It includes government facilities, private/non-government providers of public or essential services, and documented public-access civic/community venues.

This is not a census of every building or business. A private facility qualifies only when it has a meaningful education, healthcare, social-welfare, emergency, transport, utility, cultural, community, regulated-provider or comparable public-interest role supported by an authoritative source. Ordinary shops, restaurants, offices, malls, factories, warehouses and homes are excluded by default.

Use one canonical registry and API with explicit inclusion classes: `GOVERNMENT_FACILITY`, `PRIVATE_PUBLIC_SERVICE_PROVIDER`, and `PUBLIC_ACCESS_VENUE`. Keep an internal-only `DISCOVERY_CANDIDATE` class for unverified records. Publish separate government/private/venue counts; never call the combined total “government facilities”.

A single physical site can have multiple functions. A barangay multipurpose hall also designated as an evacuation centre is one physical facility with multiple functions, not two duplicate places. A private mall hosting a PRC service counter is a host site plus a distinct public-service unit; the mall is not automatically included.

The platform must distinguish:

- physical facility vs. site/compound vs. building vs. facility unit vs. infrastructure asset vs. project;
- owner vs. operator vs. manager vs. host/landlord vs. funder vs. regulator/accreditor;
- government facility vs. private public-service provider vs. public-access venue;
- public-access conditions vs. ownership;
- facility existence vs. operational status vs. licence/accreditation vs. service availability;
- exact/field-verified coordinate vs. map-geocoded coordinate vs. barangay centroid.

See [the binding inclusion and ownership policy](docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md).

## Source inventory evidence baseline — v2.1/v2.2 research

The source register now contains a broader set of directly linked official resources and the actual limits found during research:

- **DILG DRRM-PULSE:** live public map and participating-LGU directory; map categories include evacuation centres, command centres, warehouses, barangay halls, health centres, fire stations and police stations. The portal says LGU-entered records are validated by DILG field officers. This is participating-LGU coverage, not a national masterlist. [Portal](https://drrm.ncr.dilg.gov.ph/) · [Methodology](https://drrm.ncr.dilg.gov.ph/about) · [Map](https://drrm.ncr.dilg.gov.ph/map)
- **DILG Subaybayan:** a DILG FOI response (12 Feb 2026) points to the LIME 20 project list filtered by project type “Evacuation Center”, status and year. This is project data, not a complete list of all operating evacuation centres. Another DILG response says it has no consolidated master file with requested coordinates/PSGC. [FOI response](https://www.foi.gov.ph/agencies/dilg/updated-list-of-evacuation-center-in-the-philippines/)
- **LGU inventory basis:** RA 7160 §17 describes local basic services/facilities and §524 requires periodic inventory of infrastructure and other community facilities. It does not create a national open API. DILG has said public markets are primarily held by LGUs; barangay-hall FOI response did not provide hall coordinates. [Local Government Code](https://lawphil.net/statutes/repacts/ra1991/ra_7160_1991.html) · [Public markets FOI](https://www.foi.gov.ph/agencies/dilg/list-of-public-markets-in-the-philippines-dilg-905479402880/) · [Barangay halls FOI](https://www.foi.gov.ph/agencies/dilg/list-of-barangay-halls/)
- **ECCD Council:** 2023 annual-report annex has NCDC project locations; the Council reports 1,057 NCDCs established as of 31 Dec 2025. Its resource page exposes child-development-centre profile forms. This is not proof of a complete CDC national bulk export. [NCDC](https://eccdcouncil.gov.ph/ncdc/) · [NCDC list](https://eccdcouncil.gov.ph/wp-content/uploads/2024/10/AR-2023-051024-2_compressed.pdf) · [Resources/forms](https://eccdcouncil.gov.ph/resources/)
- **National Library:** official public-libraries directory PDFs. The January 2025 file exposes library ID, region, type, name, address, status and affiliation date, along with personal librarian contact fields that must be minimized. [January 2025 PDF](https://web.nlp.gov.ph/wp-content/uploads/2025/02/Directory-of-Affiliated-Public-Libraries-in-the-Philippines-As-of-January-2025-Rhodora-Valdez.pdf) · [December 2025 PDF](https://web.nlp.gov.ph/wp-content/uploads/2026/01/OFFICIAL-Integrated-Directory-of-Public-Libraries-as-of-December-2025.pdf)
- **DSWD:** public directory of 77 DSWD-operated CRCFs and dated Standards Bureau lists for LGU-accredited centres, senior citizens centres and private providers. Ownership categories must remain separate. [CRCF directory](https://www.dswd.gov.ph/crcf/) · [Standards Bureau](https://standards.dswd.gov.ph/directories-3/)
- **National Museum:** official page lists regional, area and site museums and links individual locations. [Museum directory](https://www.nationalmuseum.gov.ph/our-museums/regional-area-and-site-museums/)
- **PHLPost:** public post-office locator exposes province, post-office name, address and services. Some service points are hosted inside malls, LGU buildings or other premises. [Post Office Locator](https://phlpost.gov.ph/post-office-locator/)
- **PRC:** official regional-office and offsite service-centre pages/map list office and service locations, contacts and hours. Some centres are hosted in private malls/LGU sites. [Office and service-centre directory](https://www.prc.gov.ph/prc-offices-and-offsite-service-centers-contact-information) · [Interactive map](https://www.prc.gov.ph/InteractiveMap-v2-37.html)
- **BIR:** RAO 006-2025 lists revenue regions and RDO numbers/names/jurisdictions; the 2025 Citizen's Charter contains office addresses and contact information. [RAO 006-2025](https://bir-cdn.bir.gov.ph/BIR/pdf/RAO%20No.%206-2025.pdf) · [Citizen's Charter](https://bir-cdn.bir.gov.ph/BIR/pdf/BIR%20Citizen%27s%20Charter%20%282025-Edition%29.pdf)
- **DTI:** official Negosyo Center finder advertises 1,400+ centres and searchable city/province filters; no public bulk API was verified. [Locator](https://negosyocenter.dti.gov.ph/)
- **PPA:** official list of ports covered in PPA statistics includes port names, RORO/non-RORO classifications and remarks; other PPA pages list PMOs and private ports. Separate government, authority-managed and private ports. [List of ports](https://www.ppa.com.ph/sites/default/files/List%20of%20Ports%20covered%20in%20PPA%20Statistics.pdf) · [PPA](https://ppa.com.ph/)
- **CAAP:** official Area Centers page lists airports by area centre and aerodrome summaries. Verify actual operator/owner for each airport; CAAP oversight does not establish ownership. [Area Centers](https://www.caap.gov.ph/area-centers/)
- **PFDA:** official quality-system documentation identifies a regional fish-port network and municipal fish-port programme, including LGU co-management/turnover. [PFDA source](https://www.pfda.gov.ph/images/ISO_/CO/QMS/PFDA_QMS_2023_09.pdf)
- **NMIS:** live NARIS public list/map showed 362 accredited meat establishments with LTO numbers, types and addresses. These are licensed establishments and include private operators; qualifying facility-level records may be included as private public-service providers, not as government facilities. [NARIS](https://naris.nmis.gov.ph/)
- **DENR-EMB:** official air-quality pages list monitoring-station locations and dated downloadable regional reports. Monitoring sites are public environmental assets, not necessarily walk-in service facilities. [National monitoring](https://air.emb.gov.ph/ambient-air-quality-monitoring/) · [NCR stations](https://ncr.emb.gov.ph/realtimeairmonitoring/)
- **BMB PAIS:** official protected-area dashboard and GIS information; its own disclaimer says data may not reflect real-time conditions during update/validation. Use protected-area polygons as site context, not individual facility records. [PAIS](https://pais.bmb.gov.ph/index.php)
- **NHA MAPS:** official map portal includes NHA project sites/lots, occupancy verification, landholdings and other agency layers. These are not automatically public facility records. [NHA MAPS](https://maps.nha.gov.ph/)
- **Philippine Geoportal:** catalogue includes potentially useful fire-station, government-office, public-office, market-place, police-station, health, DTI/Negosyo Center, airport and port layers. Several are old (e.g. 2003). Each layer needs separate metadata, download, owner and rights verification. [Geoportal](https://geoportal.gov.ph/) · [Data inventory](https://www.geoportal.gov.ph/gpresources/GP_DataInventory.pdf)

## Research baseline and evidence discipline

All new resources in the source register are labelled by actual evidence level and caveats. The agent must continue discovering more resources and re-test live endpoints during implementation. Do not infer that an agency homepage or source catalogue proves that an actual usable dataset exists.

The required research protocol is in [docs/11-VERIFIED-SOURCE-DISCOVERY.md](docs/11-VERIFIED-SOURCE-DISCOVERY.md). It defines evidence grades, record inspection, rights review, source freshness and required research outputs.

## Publication basis

A public directory is not a blanket licence, and the absence of an explicit licence is not by itself a prohibition. Under the root [data inclusion and publication policy](../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md), a source may be published when:

- the exact release is acquired through an open public route and its records/schema are inspected;
- no explicit terms prohibit the intended reuse;
- only reviewed institutional, non-personal fields are exposed;
- provenance, attribution, the publication basis, and a takedown-on-notice route are recorded.

`PUBLICLY_AVAILABLE_VERIFIED` records that decision. It is not a claim of public domain. Explicit restrictions, access controls, FOI/agreement conditions, and personal or security-sensitive data still control, and the release-level publication gate is still enforced in the API.

## What success looks like

A citizen can find a barangay hall, covered court, public market, fire station, evacuation centre, school, public hospital, public library, government office, park, port, public post office or other eligible public facility. A developer can access the same record through a documented API. Each record states its source, scope, owner/operator, date, location precision and known limitations.

**The goal is broad, evidence-backed coverage—not an inflated map pin count.**


## Expanded resource coverage in v2.2

The source inventory and tracker now include additional official resource leads beyond the initial DILG/DepEd/DOH/PhilHealth/PSA sources: ECCD Council NCDCs and CDC profile resources; DSWD CRCFs and accreditation directories; National Museum site museums; BIR RDOs; DTI Negosyo Centres and shared-service facility candidates; PHLPost offices; PRC regional/offsite service centres; PPA ports; CAAP aerodromes; PFDA regional/municipal fish ports; NMIS NARIS regulated establishments; EMB monitoring stations; BMB protected-area context; NHA map layers; Geoportal facility layers; Open Data Philippines catalogue discovery; NAMRIA geographic resources; and additional DILG/LGU FOI evidence.

The register distinguishes actual official file/directory evidence from FOI routes, project data, GIS catalogue candidates, and discovery-only sources. Some records represent private regulated providers, hosted service counters, environmental assets, projects or geographic areas. Apply the inclusion policy and keep ownership, operator, host, facility, asset and project semantics separate.

The agent is required to keep researching beyond this inventory, category by category, and to add only sources supported by actual evidence. The current list is extensive but is not claimed to be exhaustive or wholly acquired. See `docs/11-VERIFIED-SOURCE-DISCOVERY.md`.


## Version 3.0 scope correction

The registry is now ownership-inclusive. Qualifying private schools, healthcare providers, regulated social-welfare facilities, private public-service transport/utility facilities, and documented civic venues are first-class records in the same registry/API. They retain separate inclusion classes and ownership/operator relationships, so they are never counted as government-owned. “All facilities” means all qualifying facility types, not every building, business or private property. The exact inclusion test is in `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`.
