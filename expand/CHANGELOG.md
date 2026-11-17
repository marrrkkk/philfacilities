# Planning Bundle Changelog

## 3.2 — 16 November 2026

- Added the PhilHealth Directory of Offices release `PHILHEALTH-OFFICES-2026-11-15`: 293 offices (185 facility, 108 facility unit) across 19 regional groups published with name, source category, region grouping and postal address; telephone, e-mail and schedule fields withheld.
- Added the Quezon City LGU directory release `QC-LGU-DIRECTORY-2026-11-16`: 68 barangay health centres and 40 barangay halls published from official LGU pages, with personal contact fields withheld and non-hall/non-health pages retained privately.
- Added the Quezon City Places release `QC-LGU-PLACES-2026-11-16`: Kamuning Market, Quezon Memorial Circle, QC Elevated Promenade, Ninoy Aquino Parks and Wildlife Center and La Mesa Eco Park published from the official visitor directory; 23 QCPL library pages excluded after an NLP duplicate cross-check.
- Re-ingested the PhilHealth Antenatal category with `philhealth-pdf-1.2.0` after fixing retried-release snapshot idempotency: 3,221 rows and accreditations, ending at page 120; the earlier 6,562-row annex double-count remains withdrawn. Total PhilHealth coverage is now 26 categories / 28,207 accreditations.
- Made Antenatal accreditation-only for subtype purposes and restored 3,178 prior facility subtypes from release snapshots, so a benefit-package row cannot overwrite the physical facility classification.
- Added release-scoped facility snapshots, automatic pre-mutation capture, and the conservative `release-rollback` CLI with dry-run, later-release/later-evidence/post-release-change refusal paths, and raw-evidence retention.
- Added the Cainta, Rizal municipal health-centre release `CAINTA-HEALTH-2026-11-16`: 28 labelled RHU/BHS facilities published from the official landing page and six RHU pages; three unlabelled entries retained privately.
- Added the Pasay City health-centre release `PASAY-HEALTH-2026-11-16`: 13 health centres and the Doña Marta Lying-In Clinic published from the official health-care programme page; telephone numbers withheld.
- Added the Mandaluyong City barangay directory release `MANDALUYONG-LGU-2026-11-16`: 27 barangay government offices published from the official table, including one covered-court multi-use record; telephone numbers and chairperson names withheld.
- Updated the source register, rights register, tracker, and root README with the new releases, publication decisions, counts and evidence.

## 3.1 — 15 November 2026

- Added the root data inclusion and publication policy: a verified, publicly available source with no explicit prohibition may be published with reviewed institutional fields, provenance, attribution and takedown-on-notice.
- Added the `PUBLICLY_AVAILABLE_VERIFIED` rights state and linked it to the enforced API publication gate.
- Confirmed that explicit restrictions, access-controlled/FOI/agreement-bound data, and personal or sensitive data remain excluded or restricted.
- Updated the rights register for DepEd EBEIS, NLP, NMP, BIR and PHLPost, and removed duplicate/stale rows.
- Aligned governance, discovery, acquisition, ingestion, coverage, rollout and tracker documents with the new publication basis.

## 2.2 — 15 November 2026

- Expanded the official resource inventory with DILG DRRM-PULSE and Subaybayan, DILG FOI limitations, ECCD Council NCDCs, National Museum sites, BIR RDOs, DTI Negosyo Centres, PHLPost, PRC, PPA, CAAP, PFDA fish ports, NMIS NARIS, EMB monitoring stations, BMB PAIS, NHA MAPS, additional Geoportal layers, Open Data Philippines and NAMRIA discovery resources.
- Added evidence-grade and source verification requirements so official files, directories, FOI routes, portals, GIS candidates and discovery-only targets are not conflated.
- Expanded the source-rights register with blocked publication status for newly identified resources.
- Added AF1B research tasks and AF2B integration tasks for the additional source families.
- Expanded LGU acquisition strategy with DILG-PULSE, Subaybayan, hall/market FOI limitations and the evacuation-centre custodian conflict.
- Updated rollout roadmap to prioritize verifiable public-service directories while preserving owner/operator/host and private-provider distinctions.


## 2.0 — 15 November 2026

- Reframed PhilFacilities as an all-government-facilities registry.
- Added a broad facility taxonomy and multi-use facility rules.
- Added DILG DRRM-PULSE, DILG/RA 7160 LGU inventory basis, DPWH national-government-building inventory, Geoportal layers, BFP fire stations, DSWD CRCFs, NLP public libraries, NHA map resources, and further sector discovery sources.
- Added a dedicated LGU inventory acquisition programme for barangay halls, multipurpose halls, covered courts, parks, plazas, public markets, and local community facilities.
- Added the distinction between facilities, sites, buildings, facility units, functions, services, infrastructure assets, and projects.
- Added source-specific coverage and quality requirements.
- Added an all-facilities rollout tracker; removed the assumption that the application/stack should be rebuilt.

## 1.0 baseline

The earlier plan focused on schools and healthcare facilities as initial categories. That baseline is superseded for product scope by version 2.0, while its technical architecture and design decisions remain the implementation baseline unless the repository audit identifies a concrete need to change them.


## 3.0 — 15 November 2026

- Expanded PhilFacilities from an all-government-facilities registry to an ownership-inclusive registry of all **qualifying** facilities: government facilities, private public-service providers and documented public-access venues.
- Made qualifying private facilities first-class records in the same canonical registry, API and map, with explicit inclusion-class/ownership filters and separate counts.
- Added binding inclusion criteria and clear exclusions: this is not a census of every building, business, mall, shop, factory, warehouse or home.
- Expanded taxonomy examples to cover private schools, HEIs, hospitals, clinics, social-welfare providers, TVIs, regulated transport/utilities and eligible public-access venues.
- Strengthened owner/operator/manager/host/funder/regulator/accreditor/public-access modeling and co-located service-unit relationships.
- Updated the source register, rights register, LGU acquisition strategy, data model, quality rules, rollout roadmap, acquisition templates, agent instructions and tracker to follow the ownership-inclusive scope.
