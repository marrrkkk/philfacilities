# PhilFacilities — Ownership-Inclusive All-Facilities Expansion Tracker

**Tracker scope:** Data/product expansion from the existing school/health-focused implementation to all qualifying facility categories, regardless of ownership, including government facilities, private public-service providers and documented public-access venues.  
**Last updated:** 15 November 2026.  
**Important:** The existing platform foundation is assumed implemented. This tracker does not include rebuilding the website, map, API, database infrastructure, monorepo, CI/CD, or design system.

## Status legend

- `NOT STARTED` — no implementation/evidence yet.
- `IN PROGRESS` — active work with concrete partial evidence.
- `REVIEW` — implementation/evidence exists and needs acceptance.
- `BLOCKED` — source access, rights, or another dependency blocks progress.
- `DEFERRED` — intentionally postponed.
- `DONE` — acceptance criteria met and evidence linked.

## Expansion principles

- A URL discovery is not an acquisition.
- A source file is not automatically publishable.
- A parser is not a completed ingestion until it has run against an actual authorized source release.
- A map layer is not a complete national inventory.
- A source record missing from a later release does not prove facility closure.
- National completeness must never be claimed without a defensible denominator and source coverage.

## Milestone summary

| Milestone | Description | Initial status | Exit condition |
|---|---|---|---|
| AF0 | Scope/taxonomy generalization | DONE | Facility kind, inclusion class, ownership/operator type and public-access class are implemented; taxonomy and role semantics documented |
| AF1 | Source discovery and rights register | IN PROGRESS | Candidates classified with evidence, access method, coverage and rights state; discovery continues for unverified sources |
| AF2 | National agency source expansion | IN PROGRESS | DSWD CRCF, NLP, NMP, BIR, PHLPost and NMIS NARIS published; DepEd EBEIS source release published with canonical rows internal |
| AF3 | GIS/Geoportal layer integrations | NOT STARTED | Selected layers validated and published only under layer-specific terms |
| AF4 | LGU facility inventory acquisition | NOT STARTED | LGU inventory template, pilot cohort and repeatable intake process operational |
| AF5 | Emergency and public-safety facilities | NOT STARTED | Validated evacuation/fire/police source coverage with safety restrictions |
| AF6 | Additional facility sectors | IN PROGRESS | PPA ports published (574 rows); utilities, environment and other categories remain source-dependent |
| AF7 | Coverage, quality and public transparency | NOT STARTED | Coverage/status/source freshness reporting works across categories |
| AF8 | Ongoing release operations | NOT STARTED | New source releases detected, validated, versioned and safely published |

## AF0 — Generalize the existing registry

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF0-01 | Audit current data model for school/health-only assumptions | DONE | Existing repository | `core.facilities` carries `facility_kind`, `inclusion_class`, `ownership_type`, `operator_type`, `public_access_class` and `access_conditions`; roles, functions and services are separate tables |
| AF0-02 | Adopt top-level facility taxonomy and stable subtype codes | DONE | AF0-01 | `apps/api/philfacilities_api/taxonomy.py` defines facility kinds, inclusion classes, ownership and operator types; API filters expose them |
| AF0-03 | Separate category, subtype, function and service | DONE | AF0-02 | `facility_kind`/`facility_type`/`facility_subtype` are distinct from `core.facility_functions` and `core.facility_services` |
| AF0-04 | Confirm site/building/facility-unit relationships | DONE | AF0-01 | `core.facility_relationships` stores typed links; `facility_kind` distinguishes site, building, facility unit, infrastructure asset and project |
| AF0-05 | Separate inclusion class, ownership/operator/manager/host/funder/regulator/accreditor/access | DONE | AF0-01 | `core.facility_roles` stores typed role relationships; ownership, operator and public-access fields are separate |
| AF0-06 | Preserve existing DepEd/DOH/PhilHealth functionality | DONE | AF0-01 to AF0-05 | Regression suite passes; prior records remain addressable |
| AF0-07 | Add source-specific coverage state to category/geography | IN PROGRESS | AF0-02 | Partial/participating/selected coverage represented correctly |

## AF1 — Source discovery, access, and rights

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF1-01 | Import all candidates from `docs/03-SOURCE-REGISTER.md` into source registry | NOT STARTED | Existing source registry | Every source has source ID, custodian, URL and initial state |
| AF1-02 | Verify DILG DRRM-PULSE data/export mechanism and terms | DONE | None | Public `/api/facilities.geojson` returned exactly one validated command-centre feature regardless of query parameters; `/api/map-layers.geojson` returned an empty collection; map/LGU pages inspected. Feed is not a usable bulk inventory and emergency coordinates require security review. `PUBLIC FEED INSPECTED — NOT USABLE FOR BULK INGEST`; no bulk request or bypass. Evidence: `docs/03-SOURCE-REGISTER.md` §6A, `/tmp/opencode/drrm.geojson`. |
| AF1-03 | Verify DSWD CRCF directory and Standards Bureau download files | DONE | Publication decision | Official CRCF directory acquired; 76 institution-level facilities published with attribution; Standards Bureau dated lists remain discovery targets |
| AF1-04 | Acquire NLP December 2025 public-libraries directory | DONE | Publication decision | Official PDF acquired; 1,752 institution-level rows parsed; personal librarian contacts withheld. Evidence: `DATA-LICENSES.md`, `expand/DATA-RIGHTS-REGISTER.md`. |
| AF1-05 | Obtain BFP August 2025 logistical report attachment and inspect schema | NOT STARTED | FOI attachment access | Original file, metadata, exact station fields, coverage and rights status |
| AF1-06 | Inspect Geoportal Data Inventory and candidate layer metadata | NOT STARTED | None | Layer matrix with owner, date, CRS, coverage, download and restriction status |
| AF1-07 | Review Geoportal download/reuse conditions per candidate layer | NOT STARTED | AF1-06 | Per-layer rights decision in `DATA-RIGHTS-REGISTER.md` |
| AF1-08 | Verify DPWH DO 247 s.2024 building inventory process and public dataset availability | NOT STARTED | None | Forms mapped; inventory availability/pending request status documented |
| AF1-09 | Check DPWH public-building FOI request status / locate current inventory | NOT STARTED | FOI portal | Official response/file or documented no-data/denial |
| AF1-10 | Verify official PNP public-station source and disclosure limits | NOT STARTED | None | Official list/API/FOI route identified; third-party lists excluded as authority |
| AF1-11 | Verify OCD/NDRRMC evacuation-centre inventory source and coverage | NOT STARTED | None | Custodian, format, coverage, terms and update process documented |
| AF1-12 | Verify LGU source channels and sample local inventories | NOT STARTED | AF1-01 | Pilot source matrix for selected LGUs |
| AF1-13 | Verify additional agency sources: transport, utilities, environment, agriculture, justice | NOT STARTED | AF1-01 | Each candidate classified as real source, discovery-only or no data located |
| AF1-14 | Complete source-by-source publication decisions for any proposed public release | IN PROGRESS | Source acquisition | Documented decision for each dataset/release/field, including `PUBLICLY_AVAILABLE_VERIFIED` where applicable |

## AF1B — Expanded official source discovery (15 Nov 2026 research pass)

These tasks extend AF1. They are intentionally `NOT STARTED` because the source pages/FOI records were identified but the agent still needs to re-test reachability, acquire the actual records, inspect schemas and decide rights. Do not mark a task complete based only on the link being present.

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF1-15 | Inspect ECCD Council NCDC list, CDC profile forms and latest annual-report/MIS references | NOT STARTED | None | Exact source files/fields, release date, coverage, ownership distinctions and rights recorded |
| AF1-16 | Acquire National Museum regional/area/site museum directory | DONE | Publication decision | Official directory acquired; NMP-run site subset published with attribution; operator/status caveats retained. |
| AF1-17 | Inspect BIR RAO 006-2025 and Citizen's Charter office directory | DONE | Publication decision | RAO acquired; image-only PDF processed with local OCR; 128 RDO rows and 19 region headings published with OCR evidence retained. |
| AF1-18 | Test DTI Negosyo Center locator records and data payload | DONE | Terms review | Public `regions-overview` and `by-region` JSON endpoints verified; 1,427 unique active records across 17 regions; terms reviewed; ownership/operator/host not stated; contact fields withheld. Evidence: `apps/ingest/philfacilities_ingest/sources/dti_negosyo.py`, release `DTI-NEGOSYO-2026-11-15`. |
| AF1-19 | Inspect PHLPost post-office locator records | DONE | Publication decision | Actual post-office locator records acquired; 1,272 factual locator facilities published with attribution; an earlier review-required release is retained internally. |
| AF1-20 | Inspect PRC office/offsite-service-centre directory and locator | NOT STARTED | Rights review | Actual locations, contacts/hours, service-centre type and host/operator documented |
| AF1-21 | Parse PPA official ports list and 2026 statistics manual | DONE | Rights review | 22-page PDF acquired; 574 rows parsed with region/PMO/base-port/TMO/other-government/private hierarchy and RORO/NON-RORO marks; 0 validation issues or duplicate keys; 303 government and 271 private rows; standalone MICT note preserved as evidence. Evidence: `apps/ingest/philfacilities_ingest/sources/ppa.py`, release `PPA-PORT-LIST-2026-11-15`. |
| AF1-22 | Inspect CAAP Area Centers and current aerodrome information | NOT STARTED | Rights review | Current airport/aerodrome identifiers, coordinates and owner/operator validated |
| AF1-23 | Obtain current PFDA regional/municipal fish-port inventory | NOT STARTED | PFDA source request | Actual facility records, transfer/co-management status, coordinates and rights established |
| AF1-24 | Test NMIS NARIS directory and dated slaughterhouse lists | DONE | Publication decision | NARIS directory acquired; 357 establishments published with factual fields only; 362 listed rows collapse to 357 unique LTOs; page currently behind a WAF/TLS failure |
| AF1-25 | Inspect EMB air-quality monitoring station inventories and regional downloads | NOT STARTED | Rights review | Station metadata/coordinates and observations separated; regional coverage disclosed |
| AF1-26 | Inspect BMB PAIS protected-area layers and download conditions | NOT STARTED | Layer-specific terms | Polygon/context layer metadata, date, owner and terms captured; not counted as facility points |
| AF1-27 | Inspect NHA MAPS layer catalogue and exact downloadable resources | NOT STARTED | Layer-specific terms | Each candidate layer classified as facility/site/project/parcel; personal occupancy data excluded |
| AF1-28 | Audit Geoportal candidate layers individually: fire, government office, market, police, health, DTI, airport and port | NOT STARTED | AF1-06 | Exact layer metadata, owner, vintage, CRS, downloadable data, coverage and rights per layer |
| AF1-29 | Inspect Open Data Philippines catalogue/API for facility datasets | NOT STARTED | None | Dataset IDs and original publishers traced; API/authentication/terms tested; catalogue not mistaken for owner |
| AF1-30 | Investigate NAMRIA base-map, administrative boundary and facility-related products | NOT STARTED | None | Exact product, format, scale, release, access, attribution and redistribution terms recorded |
| AF1-31 | Investigate airport, port and maritime facility sources across DOTr, PPA, CAAP and MARINA | NOT STARTED | AF1-13 | Owner/operator and public facility vs route/service distinctions established |
| AF1-32 | Investigate public-library and cultural-site additions through NLP, National Museum, NCCA and LGUs | NOT STARTED | AF1-04, AF1-16 | Actual individual site records and source/rights evidence acquired |
| AF1-33 | Investigate DSWD/ECCD centre lists and classify DSWD-owned, LGU-operated, NGO/private and workplace centres | NOT STARTED | AF1-03, AF1-15 | Each record's owner/operator/accreditation status distinguishable |
| AF1-34 | Resolve evacuation-centre custodian conflict across DILG, OCD/NDRRMC and LGUs | NOT STARTED | AF1-11 | Current written response/source from each relevant custodian; unresolved negative findings preserved |
| AF1-35 | Discover public building/community asset inventories under RA 7160 §524 and DPWH DO 247 s.2024 | NOT STARTED | AF1-08, AF1-12 | Actual inventory files or documented custodian responses; do not infer a central public database |
| AF1-36 | Search for public-service offices and branches of SSS, GSIS, Pag-IBIG, LTO, PhilHealth and other agencies | NOT STARTED | None | Official office locators/charters inspected; operator/host and current address verified |
| AF1-37 | Search all remaining taxonomy categories for official datasets and regional/LGU sources | NOT STARTED | AF1-01 | Category-by-category search log with positive and negative evidence |

## AF2 — National agency facility source integrations

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF2-01 | DSWD CRCF directory parser/import | DONE | AF1-03, publication decision | 76 records parsed and published; institutional name, field office and postal address only; no coordinates or operational status inferred |
| AF2-02 | DSWD Standards Bureau dated list importer | NOT STARTED | AF1-03, publication decision | Dated releases retained; accreditation effective date preserved |
| AF2-03 | NLP public-library PDF parser/import | DONE | AF1-04, publication decision | 1,752 records parsed with page/source provenance; institution-level fields published, personal librarian contacts withheld. |
| AF2-04 | BFP station report parser/import | NOT STARTED | AF1-05, rights approval | Actual station list parsed; volunteer-brigade gap retained |
| AF2-05 | BFP regional official directory adapters where justified | NOT STARTED | AF1-05 | Source-specific regional listings parsed with retrieval/source date |
| AF2-06 | Add further PhilHealth provider categories | NOT STARTED | Existing parser, rights approval | Category-specific source data/fields/expiry and facility matches verified |
| AF2-07 | CHED institution data acquisition when source is verified | DONE | Official bulk/API source and rights | Public HEIDA directory acquired: 18 regional directories, 280 pages, 2,716 rows, 2,711 unique institutions after 5 duplicate rows; 0 coordinates. Release `CHED-HEIDA-2026-11-15`, SHA-256 `abe2884...ee334`; 527 public educational institutions, 159 local-government colleges/universities, 868 NGO/non-profit, 616 private corporate, 418 religious/faith-based; 123 unknown/CHED-supervised rows internal. Evidence: `apps/ingest/philfacilities_ingest/sources/ched_heida.py`, `tests/test_parsers.py`, `/v1/coverage`. |
| AF2-08 | TESDA provider/assessment-centre data acquisition when source is verified | DEFERRED | Official bulk/API source and rights | Actual provider records and identifiers acquired |

## AF2B — Additional national directories and public-service locations

Only implement these after the corresponding AF1 source is acquired, schema-inspected, and rights-approved. The existence of the directory alone is not an ingestion acceptance criterion.

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF2-09 | Ingest ECCD NCDC records from verified official release | NOT STARTED | AF1-15, rights | Actual NCDC records, source dates and facility ownership/operator fields |
| AF2-10 | Ingest National Museum sites | DONE | AF1-16, publication decision | NMP-run site records ingested with official source links and operator caveats; directory subset only. |
| AF2-11 | Ingest BIR RDO/office locations | DONE | AF1-17, publication decision | 128 RDO rows and 19 region headings ingested from RAO 006-2025 with OCR evidence; no addresses or coordinates inferred. |
| AF2-12 | Ingest DTI Negosyo Centres | DONE | AF1-18, rights | 1,427 active center records published as government service units (`NEGOSYO_CENTER`, `facility_unit`) with `GOVERNMENT_UNSPECIFIED` ownership/operator. Postal addresses and geographic labels only; phone/email withheld; no coordinates or host-building classification. Evidence: release `DTI-NEGOSYO-2026-11-15`, `/v1/coverage`. |
| AF2-13 | Ingest PHLPost offices/service locations | DONE | AF1-19, publication decision | 1,272 locator facilities published with hosted-counter distinctions and attribution; earlier release retained internally. |
| AF2-14 | Ingest PRC regional/offsite centres | NOT STARTED | AF1-20, rights | Verified operating locations and hosted-site semantics |
| AF2-15 | Ingest PPA port records | DONE | AF1-21, rights | 574 port records published: 303 government facilities and 271 private public-service providers. PPA-managed base ports/TMO/OTP entries use `GOCC`, other government ports use `GOVERNMENT_UNSPECIFIED`, and private ports use `PRIVATE_UNSPECIFIED` with no inferred owner/operator. Hierarchy, RORO marks and remarks are retained in source evidence; no coordinates or operational status inferred. Evidence: release `PPA-PORT-LIST-2026-11-15`, `/v1/coverage`. |
| AF2-16 | Ingest CAAP aerodrome records | NOT STARTED | AF1-22, rights | Current aerodrome records, identifiers and actual operators |
| AF2-17 | Ingest PFDA fish-port facilities | NOT STARTED | AF1-23, rights | Current fish-port records and transfer/co-management history |
| AF2-18 | Ingest eligible NMIS regulated establishments in the unified registry | DONE | AF1-24, publication decision | 357 establishments published with factual fields; private operators classified as `PRIVATE_PUBLIC_SERVICE_PROVIDER`; never counted as government-owned; a licence is not treated as proof of current operation |
| AF2-19 | Ingest EMB monitoring stations as environmental assets | NOT STARTED | AF1-25, rights | Station metadata/coordinates with observation-feed relation and region coverage |
| AF2-20 | Ingest other verified public facility directories discovered by AF1-37 | NOT STARTED | AF1-37, publication decision | Source-specific parser, schema tests, publication decision and provenance complete |
| AF2-21 | Ingest DepEd EBEIS institution-level records with personal fields withheld | IN PROGRESS | Field-level mapping/privacy review | 5,055 records retained; current source release `approved_with_attribution`/`published`; canonical rows still `internal` pending field-level mapping and privacy review |

## AF3 — Geoportal and geospatial facility layers

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF3-01 | Build Geoportal layer metadata inventory | NOT STARTED | AF1-06 | Layer name, owner, date, CRS, geometry, metadata and terms saved |
| AF3-02 | Test download/feature access for fire station layer | NOT STARTED | AF3-01, rights | Actual vector data acquired or limitation documented |
| AF3-03 | Test government offices/public office layers | NOT STARTED | AF3-01, rights | Source vintage/coverage assessed; no outdated data presented as current |
| AF3-04 | Test market place layer | NOT STARTED | AF3-01, rights | Data date and LGU coverage verified; older layer flagged |
| AF3-05 | Test police precinct/station layer | NOT STARTED | AF3-01, rights | Source owner and permitted use verified |
| AF3-06 | Test hospital/health facility layer | NOT STARTED | AF3-01, rights | Records compared against DOH/PhilHealth; duplicates/conflicts reported |
| AF3-07 | Test DTI/Negosyo/shared-service facility layers | NOT STARTED | AF3-01, rights | Determine eligibility and assign government/private-provider/public-access class in the same registry |
| AF3-08 | Test DOTr national airport/nautical port layers | NOT STARTED | AF3-01, rights | Owner/operator and current official list verified |
| AF3-09 | Implement per-layer source metadata and geometry validation | NOT STARTED | AF3-01 to AF3-08 | Source CRS, data date and precision appear in provenance |

## AF4 — Local-government acquisition programme

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF4-01 | Prepare LGU inventory request and import template | NOT STARTED | Scope/taxonomy | Template and FOI request templates reviewed |
| AF4-02 | Select pilot LGU cohort | NOT STARTED | AF4-01 | Diverse cohort and contact/source map documented |
| AF4-03 | Acquire first LGU Section 524/community facility inventory | NOT STARTED | AF4-02 | Actual authorized file and custodian metadata received |
| AF4-04 | Add barangay halls and government offices | NOT STARTED | Official LGU source | Source-backed records published for pilot coverage |
| AF4-05 | Add multipurpose halls, civic centres and covered courts | NOT STARTED | Official LGU source | Multi-use functions and shared sites modeled correctly |
| AF4-06 | Add parks, plazas, playgrounds and open spaces | NOT STARTED | Official LGU/GIS source | Geometry and owner/operator status verified |
| AF4-07 | Add public markets and slaughterhouses | NOT STARTED | Official LGU source | Government/private ownership and inclusion classes validated; eligible private facilities included |
| AF4-08 | Add local libraries, community centres and welfare facilities | NOT STARTED | Official LGU source | Records matched to national directories where available |
| AF4-09 | Implement LGU submission/review workflow if justified | NOT STARTED | Pilot lessons | Submissions remain proposals until validated and approved |
| AF4-10 | Add per-LGU and per-category coverage dashboard/data report | NOT STARTED | AF4-03 onwards | Coverage state is evidence-based and does not imply missing = nonexistent |

## AF5 — Emergency and public safety facilities

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF5-01 | Acquire DILG-PULSE public participating-LGU facility data | BLOCKED | AF1-02, rights | Public facility feed returned exactly one validated command-centre feature; map-layer endpoint empty. No broader validated export, written terms or emergency-coordinate security review exists, so no bulk ingest is claimed. |
| AF5-02 | Acquire current evacuation-centre inventories from OCD/NDRRMC/LGUs | NOT STARTED | AF1-11, rights | Facility designation, capacity unit, status and source date retained |
| AF5-03 | Acquire official BFP fire-station data | NOT STARTED | AF1-05, AF2-04 | Station records published with coverage gaps documented |
| AF5-04 | Acquire official PNP public station directory | NOT STARTED | AF1-10, rights | Official source records only; security review passed |
| AF5-05 | Add emergency functions to multi-use halls/schools | NOT STARTED | AF4 and AF5 datasets | Designation relationship is dated and sourced |
| AF5-06 | Add public safety/source security review checklist | NOT STARTED | AF5-01 to AF5-05 | No sensitive security attributes are exposed |

## AF6 — Other public-service sectors

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF6-01 | Public transport facilities (ports/airports/terminals) | NOT STARTED | Official DOTr/PPA/CAAP sources | Operator and source coverage verified |
| AF6-02 | Water/wastewater/sanitation facilities | NOT STARTED | LWUA/MWSS/NWRB/LGU sources | Entity directories separated from physical facility records |
| AF6-03 | Solid waste/MRF/landfill facilities | NOT STARTED | DENR/LGU sources | Actual site records/operating status source-backed |
| AF6-04 | Agriculture/fisheries facilities | NOT STARTED | DA/BFAR/NMIS/NFA sources | Facility-level records acquired, not just licensed private operators |
| AF6-05 | Environmental/protected-area facilities | NOT STARTED | DENR bureaus/Geoportal | Facility identity distinct from protected-area polygon |
| AF6-06 | Justice/corrections facilities | DEFERRED | Official public records and security review | Only approved public fields/locations released |
| AF6-07 | Other discovered qualifying facility categories (government/private) | NOT STARTED | Source discovery | Inclusion decision and schema mapping approved |

## AF7 — Quality, coverage, and trust

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF7-01 | Implement category/subtype coverage metrics | NOT STARTED | AF0, source releases | Metrics reflect known source universe only |
| AF7-02 | Implement LGU coverage status | NOT STARTED | AF4 | Participating/selected/national/unknown states visible |
| AF7-03 | Implement source-date/freshness reporting | NOT STARTED | Release metadata | Source reference date separated from retrieval date |
| AF7-04 | Implement field-level provenance in facility profiles/API | NOT STARTED | Data model | Claims link to source release/record |
| AF7-05 | Implement location-precision display/filter | NOT STARTED | Geometry quality | Centroids are visibly approximate |
| AF7-06 | Implement facility match review/merge audit | NOT STARTED | Identity matching | False merges can be rejected and undone |
| AF7-07 | Implement public correction proposal workflow | DEFERRED | Governance design | Corrections reviewed before publication |

## AF8 — Ongoing release operations

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF8-01 | Publish multi-source release manifest | DONE | Source release records | `release-manifest` CLI builds a checksummed JSON manifest from published datasets/releases: exact release labels, source and reference dates, rights/publication/coverage states, counts, linked facilities, coordinates, attribution and known gaps. Excluded/blocked datasets are listed with reasons. Tests: `apps/ingest/tests/test_manifest.py`. Evidence: `apps/ingest/philfacilities_ingest/manifest.py`, `docs/reports/08-release-manifest.json`. |
| AF8-02 | Add source update discovery by source mode | NOT STARTED | Acquisition framework | New release detection works for approved sources |
| AF8-03 | Add schema drift and unusual count alerts | NOT STARTED | Source parsers | Invalid release quarantines safely |
| AF8-04 | Add atomic publication/rollback for multi-source release | NOT STARTED | Release manifest | Previous valid release recoverable |
| AF8-05 | Add monthly source register review | NOT STARTED | Source inventory | Stale links/terms/access methods rechecked |
| AF8-06 | Publish coverage and quality release notes | NOT STARTED | AF7 | Public changelog reports data gaps and limitations |

## Current research evidence (not implementation completion)

| Source | Discovery evidence | Current implementation status |
|---|---|---|
| DILG DRRM-PULSE | Public methodology/map/LGU directory; validates participating-LGU submissions. Facility GeoJSON returned one command-centre feature; map-layer GeoJSON was empty | INSPECTED; not usable for bulk ingest; rights/security review outstanding |
| DPWH NGOB inventory | 2024 order and inventory forms exist | DISCOVERED; national data file not acquired |
| Philippine Geoportal | Facility-related layers catalogued; per-layer restrictions and dates need review | DISCOVERED; layer data not yet validated for publication |
| DSWD CRCF | Public directory and dated Standards Bureau lists | DISCOVERED; source file/reuse decision pending |
| NLP public libraries | Official December 2025 PDF directory identified; June 2025 PDF schema inspected | ACQUIRED; 1,752 institution-level rows published with attribution |
| National Museum sites | Official regional/area/site museum directory inspected | ACQUIRED; NMP-run site subset published with attribution |
| BIR RDOs | RAO 006-2025 image-only PDF inspected; local OCR applied | ACQUIRED; 128 RDO rows and 19 region headings published with OCR evidence |
| PHLPost post offices | Public locator table inspected | ACQUIRED; 1,272 factual locator facilities published, earlier release retained internally |
| DepEd EBEIS NCR | Public result set acquired; 5,055 rows | ACQUIRED; current release published for institution-level fields, canonical rows internal pending field-level review |
| BFP fire stations | 2025 FOI response links a logistical report and fire stats; volunteer stations missing from delivered data | DISCOVERED; attachment/schema/rights to verify |
| LGU public markets | DILG says LGUs have primary jurisdiction; QC example lists public markets | DISCOVERED; local connector pilot required |
| Barangay halls | DILG FOI response points to barangay masterlist, but not a hall-specific national coordinate list | DISCOVERED; need LGU/NAMRIA acquisition |

## Work log

Append each completed task with date, tracker IDs, branch/PR/commit, source release, evidence, tests, and outcome.

| Date | IDs | Work/evidence | Outcome/blocker |
|---|---|---|---|
| 2026-11-15 | AF1 research baseline | Official source register researched for all-facilities scope | Source discoveries documented; no implementation completion claimed |
| 2026-11-15 | AF1-47 | Added the data inclusion and publication policy, ADR 0008, `PUBLICLY_AVAILABLE_VERIFIED`, API rights-gate tests and a code/data `NOTICE` | Verified public availability with no explicit prohibition can support publication; explicit restrictions still control |
| 2026-11-15 | AF1-21, AF2-15, AF6-01 | Added and ran the PPA port-list adapter against the 22-page official PDF; registered release `PPA-PORT-LIST-2026-11-15`; documented rights basis and hierarchy caveats | 574 port records published: 303 government and 271 private providers; 0 validation issues, 0 duplicate keys; 0 coordinates; PPA list retained as directory subset |
| 2026-11-15 | AF1-18, AF2-12 | Added and ran the DTI Negosyo Center adapter against the public `regions-overview` and `by-region` JSON endpoints; registered release `DTI-NEGOSYO-2026-11-15`; documented terms, contact withholding and host/ownership caveats | 1,427 active center records across 17 regions published as government service units; 0 validation issues, 0 duplicate keys; phone/email withheld; no coordinates, ownership, operator, host, hours or access inferred |
| 2026-11-15 | AF1-39, AF2-07 | Added and ran the CHED HEIDA public-directory adapter; read 18 regional directories and 280 pages; registered release `CHED-HEIDA-2026-11-15` under `PUBLICLY_AVAILABLE_VERIFIED` with attribution and takedown-on-notice | 2,716 rows parsed, 2,711 unique institutions published after 5 duplicate rows; 0 coordinates; 527 public educational institutions, 159 LGU colleges/universities, 868 NGO/non-profit, 616 private corporate, 418 religious/faith-based; 123 unknown/CHED-supervised rows internal. No campus-level or operational-status claim. |
| 2026-11-15 | AF1-02, AF5-01 | Inspected DILG DRRM-PULSE public facility/map-layer endpoints and supporting pages | Public facility feed returned one validated command-centre feature regardless of query parameters; map-layer endpoint empty. Not a usable bulk inventory; bulk ingest remains blocked pending a broader validated export, written terms and emergency-coordinate security review. |

## Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-11-15 | PhilFacilities includes qualifying facilities of all major categories, not just schools/hospitals | User confirmed broader scope |
| 2026-11-15 | Scope expanded to qualifying private public-service providers and public-access venues in the same registry | Keep ownership/inclusion classes distinct; do not count private providers as government facilities |
| 2026-11-15 | Multi-use functions attach to one physical facility | Avoid duplicate facility records |
| 2026-11-15 | LGU inventories are a first-class acquisition channel | Many community facilities are locally managed and no national public inventory is verified |
| 2026-11-15 | Core stack and app implementation are out of scope for this expansion plan | User confirmed the application is already built |
| 2026-11-15 | A verified, publicly available dataset with no explicit prohibition may be published with reviewed institutional fields, provenance, attribution and takedown-on-notice | The absence of an explicit licence is not an automatic bar; explicit restrictions, agreements, personal data and sensitive details still control. Decision recorded in `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md` and ADR 0008. |


## v3.0 scope update — ownership-inclusive coverage

The tracker now covers all qualifying facilities regardless of ownership. Government facilities, private public-service providers and public-access venues must be represented in the same canonical registry and public API, with separate inclusion-class and ownership filters/counts. It does not include every private business or building. Follow [`expand/docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`](../docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md).

### Required scope tasks

- [x] AF0-08: Add inclusion-class taxonomy (`GOVERNMENT_FACILITY`, `PRIVATE_PUBLIC_SERVICE_PROVIDER`, `PUBLIC_ACCESS_VENUE`, internal-only `DISCOVERY_CANDIDATE`) to the existing model/API. Evidence: `apps/api/philfacilities_api/taxonomy.py`, `core.facilities.inclusion_class`.
- [x] AF0-09: Separate ownership, operator, manager, host, funder, regulator, accreditor and public-access fields; backfill only where source evidence exists. Evidence: `core.facilities` ownership/operator/public-access fields and `core.facility_roles`.
- [x] AF0-10: Ensure private providers are first-class searchable/map/API records, but separated in filters, metrics and exports from government-facility counts. Evidence: `tests/test_inclusion_model.py`.
- [ ] AF0-11: Define and test exclusions for ordinary businesses, retail buildings, malls, factories, warehouses, residences and unrelated company records.
- [ ] AF1-38: Audit DepEd source releases for both public and private schools, and document coverage/rights separately.
- [x] AF1-39: Investigate private HEI facility-level records through CHED; verify campus vs institution identity. Evidence: public HEIDA directory acquired; institutional type supplies ownership evidence; 1,902 private institutions published as `PRIVATE_PUBLIC_SERVICE_PROVIDER`; the directory does not expose campus-level records, so institution identity is retained without inventing campuses.
- [x] AF1-40: Investigate all available private DOH-licensed and PhilHealth-accredited facility categories; preserve licence/accreditation scope and expiry. Evidence: 25 published PhilHealth categories with validity dates; `DATA-LICENSES.md`.
- [ ] AF1-41: Investigate private TESDA-registered TVIs and assessment centres using authorized provider-level records, not regional aggregate counts.
- [ ] AF1-42: Investigate DSWD-accredited private/NGO social-welfare providers; minimize personal/resident data.
- [ ] AF1-43: Review private port, airport, utility, meat/agriculture, culture and recreation facility sources for eligibility and owner/operator accuracy.
- [x] AF1-44: Add tests proving a private provider is never reported as government-owned solely because a public agency licenses/accredits it. Evidence: `tests/test_inclusion_pipeline.py::test_private_accreditation_never_implies_government_ownership`.
- [x] AF1-45: Add API and map tests for inclusion-class filters and separate government/private/public-access aggregates. Evidence: `tests/test_inclusion_model.py`.
- [x] AF1-46: Add hosted service-point relationships so a government counter inside a private building does not cause the host property to be misclassified. Evidence: `tests/test_inclusion_pipeline.py::test_hosted_government_counter_keeps_its_own_class_and_host_role`.
- [x] AF1-47: Adopt the root data inclusion and publication policy (`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`), add `PUBLICLY_AVAILABLE_VERIFIED`, and enforce it in the API rights gate.
- [ ] AF1-48: Complete field-level mapping and privacy review for the published DepEd EBEIS source release so canonical rows can leave `internal`; keep personal fields withheld. PHLPost canonical publication is complete.
