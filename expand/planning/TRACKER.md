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
| AF3 | GIS/Geoportal layer integrations | IN PROGRESS | Catalogue inventory complete; no layer has permitted vector access or layer-specific reuse terms, so no layer is published |
| AF4 | LGU facility inventory acquisition | IN PROGRESS | LGU inventory template, pilot cohort and repeatable intake process operational |
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
| AF1-01 | Import all candidates from `docs/03-SOURCE-REGISTER.md` into source registry | DONE | Existing source registry | `expand/source-candidates.json` normalizes 42 candidates (41 register rows plus the examined NHA WFS layer) with source ID, custodian, title, official URLs, evidence/access/rights/coverage states, priority, next action, tracker IDs and verification date. `philfacilities-ingest source-candidates` validates it; `tests/test_source_candidates.py` covers required fields, duplicate IDs, URL shape, state vocabularies and conservative publication consistency. The JSON is intentionally separate from `source.datasets`: a candidate is not an acquired or publishable dataset. |
| AF1-02 | Verify DILG DRRM-PULSE data/export mechanism and terms | DONE | None | Public `/api/facilities.geojson` returned exactly one validated command-centre feature regardless of query parameters; `/api/map-layers.geojson` returned an empty collection; map/LGU pages inspected. Feed is not a usable bulk inventory and emergency coordinates require security review. `PUBLIC FEED INSPECTED — NOT USABLE FOR BULK INGEST`; no bulk request or bypass. Evidence: `docs/03-SOURCE-REGISTER.md` §6A, `/tmp/opencode/drrm.geojson`. |
| AF1-03 | Verify DSWD CRCF directory and Standards Bureau download files | DONE | Publication decision | Official CRCF directory acquired; 76 institution-level facilities published with attribution; Standards Bureau dated lists remain discovery targets |
| AF1-04 | Acquire NLP December 2025 public-libraries directory | DONE | Publication decision | Official PDF acquired; 1,752 institution-level rows parsed; personal librarian contacts withheld. Evidence: `DATA-LICENSES.md`, `expand/DATA-RIGHTS-REGISTER.md`. |
| AF1-05 | Obtain BFP August 2025 logistical report attachment and inspect schema | NOT STARTED | FOI attachment access | Original file, metadata, exact station fields, coverage and rights status |
| AF1-06 | Inspect Geoportal Data Inventory and candidate layer metadata | DONE | None | Acquired the public catalogue response (HTTP 200, 1,887,823 bytes, 3,532 leaf entries, 54 agency nodes), grouped it into 3,490 unique layer names, and built a 20-layer candidate matrix. The catalogue supplies agency/title/tags/download flags but no date, CRS, feature count, schema, coverage or licence for most entries; that absence is recorded rather than guessed. Evidence: `expand/data/geoportal-layers.csv`, `expand/docs/GEOPORTAL-LAYER-INVENTORY.md`. |
| AF1-07 | Review Geoportal download/reuse conditions per candidate layer | DONE | AF1-06 | No candidate layer has layer-level reuse terms. WFS access returned 401; the permitted bulk-download route requires a name/email form; `getlayerdetails` returned 404 for five rechecked layers. Every candidate is therefore `REVIEW_REQUIRED`; none is publishable. Evidence: `expand/docs/GEOPORTAL-LAYER-INVENTORY.md`; source candidate `geoportal.facility_layers`. |
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
| AF1-28 | Audit Geoportal candidate layers individually: fire, government office, market, police, health, DTI, airport and port | DONE | AF1-06 | 20 candidates assessed individually: BFP offices, 2003 fire hydrants/government offices/markets/supermarkets, shared MMDA `landmark_point10k` styles, undated health facilities, DTI/Negosyo Center/SSF, TESDA offices and NCR TVET providers, PNR stations, airports/control stations, nautical/PPA ports and DA fish ports. Old, regional, shared-style and derivative layers are distinguished from current authoritative datasets. Evidence: the layer matrix in `expand/docs/GEOPORTAL-LAYER-INVENTORY.md`. |
| AF1-29 | Inspect Open Data Philippines catalogue/API for facility datasets | NOT STARTED | None | Dataset IDs and original publishers traced; API/authentication/terms tested; catalogue not mistaken for owner |
| AF1-30 | Investigate NAMRIA base-map, administrative boundary and facility-related products | NOT STARTED | None | Exact product, format, scale, release, access, attribution and redistribution terms recorded |
| AF1-31 | Investigate airport, port and maritime facility sources across DOTr, PPA, CAAP and MARINA | NOT STARTED | AF1-13 | Owner/operator and public facility vs route/service distinctions established |
| AF1-32 | Investigate public-library and cultural-site additions through NLP, National Museum, NCCA and LGUs | NOT STARTED | AF1-04, AF1-16 | Actual individual site records and source/rights evidence acquired |
| AF1-33 | Investigate DSWD/ECCD centre lists and classify DSWD-owned, LGU-operated, NGO/private and workplace centres | NOT STARTED | AF1-03, AF1-15 | Each record's owner/operator/accreditation status distinguishable |
| AF1-34 | Resolve evacuation-centre custodian conflict across DILG, OCD/NDRRMC and LGUs | NOT STARTED | AF1-11 | Current written response/source from each relevant custodian; unresolved negative findings preserved |
| AF1-35 | Discover public building/community asset inventories under RA 7160 §524 and DPWH DO 247 s.2024 | NOT STARTED | AF1-08, AF1-12 | Actual inventory files or documented custodian responses; do not infer a central public database |
| AF1-36 | Search for public-service offices and branches of SSS, GSIS, Pag-IBIG, LTO, PhilHealth and other agencies | IN PROGRESS | None | Official office locators/charters inspected; operator/host and current address verified. SSS branch locator completed: 323 branch records with institutional address published. GSIS WAF, Pag-IBIG reCAPTCHA and other locators remain blocked or unverified. |
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
| AF2-21 | Ingest DepEd EBEIS institution-level records with personal fields withheld | DONE | Field-level mapping/privacy review | Release `DEPED-EBEIS-NCR-2026-11-16` was acquired and parsed with `deped-ebeis-html-1.1.0`: 5,055 rows, 0 rejected, 5,055 existing facilities updated, 0 created. `Head / Position` is preserved only in the private raw row, is removed from the normalized payload, and is absent from assertions. The free-text `School Type` grade bands map to `offers_es`/`offers_jhs`/`offers_shs` (4,209/2,487/1,693 true) rather than being used as a subtype. All 5,055 rows use `OTHER_SCHOOL`, `ownership=unknown`, `DISCOVERY_CANDIDATE`, and remain `internal`; no public/private ownership is inferred. The Public/Private selector remains unreliable: `general_classification_id=0` returns all rows and `=1` returns 0. Evidence: `apps/ingest/philfacilities_ingest/sources/deped_ebeis.py`, `tests/test_parsers.py`, `var/reports/deped-ebeis-masterlist-ncr-deped-ebeis-ncr-2026-11-16-20261115T162923Z-aa97a6e0.json`. |
| AF2-22 | Ingest SSS branch-locator records | DONE | AF1-36, publication decision | 323 unique branch records acquired from the public region/branch/detail JSON endpoints on 15 Nov 2026; 323 published as GOCC government service facilities with postal address and region. Contact-person, e-mail and telephone/fax fields withheld; 0 validation issues or duplicates; 0 coordinates. Evidence: `apps/ingest/philfacilities_ingest/sources/sss_branch.py`, `tests/test_parsers.py`, release `SSS-BRANCHES-2026-11-15`. |
| AF2-23 | Ingest PAGASA automated-weather-station identities | DONE | AF1-13, publication decision | 113 station identities acquired from the public AWS page on 15 Nov 2026 and published as national-government environmental-monitoring facilities. Only site ID, site name and source last-updated value are public; live readings remain in the private dated artifact; 0 validation issues or duplicates; 0 coordinates. Evidence: `apps/ingest/philfacilities_ingest/sources/pagasa_aws.py`, `tests/test_parsers.py`, release `PAGASA-AWS-2026-11-15`. |
| AF2-24 | Ingest NBI regional/district offices | DONE | AF1-13, publication decision | 60 office cards acquired from the official NBI directory on 15 Nov 2026 and published as national-government offices. 52 records carry printed postal locations; 43 carry `map_geocoded` coordinates extracted from the page's official map embeds. Personal names, telephone numbers and protected e-mail values withheld. 0 duplicate keys; missing-location warnings retained for 11 cards. Evidence: `apps/ingest/philfacilities_ingest/sources/nbi.py`, `tests/test_parsers.py`, release `NBI-OFFICES-2026-11-15`. |

## AF3 — Geoportal and geospatial facility layers

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF3-01 | Build Geoportal layer metadata inventory | DONE | AF1-06 | 3,490 unique layer names saved with agency, title, tags, catalogue occurrence count, styles and download flag. Date/CRS/geometry/terms are explicitly recorded as missing because the catalogue does not supply them. Evidence: `expand/data/geoportal-layers.csv`. |
| AF3-02 | Test download/feature access for fire station layer | BLOCKED | AF3-01, rights | `bfp_office` is catalogue-only (download false), and `landmark_point10k` is one shared MMDA layer with a Fire Station style, not a BFP register. WFS returned 401 and the download form is a human flow. No vector data acquired; no bypass attempted. Evidence: `expand/docs/GEOPORTAL-LAYER-INVENTORY.md`. |
| AF3-03 | Test government offices/public office layers | BLOCKED | AF3-01, rights | `govoffices` is a 2003 MMDA layer; `landmark_point10k` is a shared style layer; `dti_offices`/`dti_ncr_offices` lack date/schema/rights. No layer was acquired; the 2003 vintage is recorded and not presented as current. |
| AF3-04 | Test market place layer | BLOCKED | AF3-01, rights | `marketplace` is a 2003 MMDA layer. No permitted vector data or current LGU coverage was acquired; the layer is flagged as stale. |
| AF3-05 | Test police precinct/station layer | BLOCKED | AF3-01, rights | The only catalogue match is a `landmark_point10k` style in a shared MMDA layer, not an authoritative PNP station register. No permitted vector data or reuse terms; security review outstanding. |
| AF3-06 | Test hospital/health facility layer | BLOCKED | AF3-01, rights | `updated_healthfacilities_061826` is undated, has no schema/feature count/rights evidence, and may duplicate DOH/PhilHealth identities. No vector data acquired, so no comparison or duplicate decision is claimed. The separate NHA WFS `DOH HF` layer was inspected as a candidate. |
| AF3-07 | Test DTI/Negosyo/shared-service facility layers | BLOCKED | AF3-01, rights | `negosyocenter`, `dti_offices`, `dti_ncr_offices`, `ssfr_20201120` and `dtssfp_v1_20201120` are catalogue-only or regional, with no layer-level rights. DTI's published JSON directory already supplies stronger identity for Negosyo Centers; the layers remain enrichment candidates only. |
| AF3-08 | Test DOTr national airport/nautical port layers | BLOCKED | AF3-01, rights | `dotc_nationalairports`, `airportcontrolstation_20220513` and `dpwh_nauticalport` lack date/schema/rights; airport control stations are security-sensitive. PPA's official port list is already published as the stronger identity source. No layer acquired. |
| AF3-09 | Implement per-layer source metadata and geometry validation | BLOCKED | AF3-01 to AF3-08 | No layer vector data was acquired, so there is no CRS/geometry to validate. The inventory records missing metadata instead of inventing it. |

## AF4 — Local-government acquisition programme

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF4-01 | Prepare LGU inventory request and import template | DONE | Scope/taxonomy | Added [`expand/templates/lgu-inventory-template.csv`](../templates/lgu-inventory-template.csv) and [`expand/docs/14-LGU-INVENTORY-TEMPLATE.md`](../docs/14-LGU-INVENTORY-TEMPLATE.md). The template carries the 10-digit LGU/barangay PSGC, taxonomy category/subtype/kind, ownership/operator, inclusion/access, address, coordinates with precision, capacity, reference date and source reference. `philfacilities-ingest validate-lgu-inventory` validates it; `apps/ingest/tests/test_lgu_inventory.py` covers 12 valid/invalid cases. |
| AF4-02 | Select pilot LGU cohort | NOT STARTED | AF4-01 | Diverse cohort and contact/source map documented |
| AF4-03 | Acquire first LGU Section 524/community facility inventory | NOT STARTED | AF4-02 | Actual authorized file and custodian metadata received |
| AF4-04 | Add barangay halls and government offices | NOT STARTED | Official LGU source | Source-backed records published for pilot coverage |
| AF4-05 | Add multipurpose halls, civic centres and covered courts | NOT STARTED | Official LGU source | Multi-use functions and shared sites modeled correctly |
| AF4-06 | Add parks, plazas, playgrounds and open spaces | NOT STARTED | Official LGU/GIS source | Geometry and owner/operator status verified |
| AF4-07 | Add public markets and slaughterhouses | NOT STARTED | Official LGU source | Government/private ownership and inclusion classes validated; eligible private facilities included |
| AF4-08 | Add local libraries, community centres and welfare facilities | NOT STARTED | Official LGU source | Records matched to national directories where available |
| AF4-09 | Implement LGU submission/review workflow if justified | IN PROGRESS | Pilot lessons | The intake validator rejects personal/security columns and out-of-taxonomy records, and never writes to the database. A validated file is still a proposal; import, duplicate review, rights review and approval remain separate steps. |
| AF4-10 | Add per-LGU and per-category coverage dashboard/data report | IN PROGRESS | AF4-03 onwards | `GET /v1/coverage` reports `by_lgu_coverage` with `NATIONAL`, `REGIONAL`, `PARTICIPATING_LGUS`, `SELECTED_LGUS` and `UNKNOWN` states from declared dataset coverage. It does not yet ingest per-LGU intake records or show "not contacted"/"request sent" states; missing coverage is explicitly not evidence of nonexistence. |

## AF5 — Emergency and public safety facilities

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF5-01 | Acquire DILG-PULSE public participating-LGU facility data | BLOCKED | AF1-02, rights | Public facility feed returned exactly one validated command-centre feature; map-layer endpoint empty. No broader validated export, written terms or emergency-coordinate security review exists, so no bulk ingest is claimed. |
| AF5-02 | Acquire current evacuation-centre inventories from OCD/NDRRMC/LGUs | NOT STARTED | AF1-11, rights | Facility designation, capacity unit, status and source date retained |
| AF5-03 | Acquire official BFP fire-station data | NOT STARTED | AF1-05, AF2-04 | Station records published with coverage gaps documented |
| AF5-04 | Acquire official PNP public station directory | NOT STARTED | AF1-10, rights | Official source records only; security review passed |
| AF5-05 | Add emergency functions to multi-use halls/schools | NOT STARTED | AF4 and AF5 datasets | Designation relationship is dated and sourced |
| AF5-06 | Add public safety/source security review checklist | DONE | AF5-01 to AF5-05 | Added `expand/docs/13-PUBLIC-SAFETY-SECURITY-CHECKLIST.md` covering pre-acquisition access/rights checks, personal/operational field minimization, publication gates, coordinate precision, incident handling and current source-by-source evidence. NBI, PAGASA, SSS and PPA decisions are documented there; PNP/jails/BFP operational data remain unpublished pending source/security review. |

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
| AF7-01 | Implement category/subtype coverage metrics | DONE | AF0, source releases | `GET /v1/coverage` returns `by_category` and `by_subtype` with facility count, published count and coordinate count, plus inclusion/ownership/access/region rows. Subtypes are sorted by category order and count; unknown values remain visible. Evidence: `apps/api/philfacilities_api/api/sources.py`, `tests/test_inclusion_model.py`, live DB endpoint check. |
| AF7-02 | Implement LGU coverage status | DONE | AF4 | `GET /v1/coverage` now returns `by_lgu_coverage` with `NATIONAL`, `REGIONAL`, `PARTICIPATING_LGUS`, `SELECTED_LGUS` and `UNKNOWN` states, source counts and dataset slugs. It is derived from declared dataset `coverage_scope`, not from an LGU inventory; the caveat keeps missing coverage separate from nonexistence. Tests: `tests/test_inclusion_model.py`. |
| AF7-03 | Implement source-date/freshness reporting | DONE | Release metadata | `source_coverage` rows expose `source_published_at`, `reference_period_start/end`, `retrieved_at`, `freshness_days` and `is_stale`; freshness anchors on reference-period end, then publication date, then retrieval. `coverage_stale_after_days` (default 365) and `stale_source_count` are returned. Evidence: `apps/api/philfacilities_api/api/sources.py`, `tests/test_inclusion_model.py`. |
| AF7-04 | Implement field-level provenance in facility profiles/API | DONE | Data model | `GET /v1/facilities/{id}/assertions` returns rights-gated claims with source field, raw value, normalized value, parser/backfill version and full source evidence. The pipeline now writes assertions for applied facility fields, location, functions, services, roles, and school/health profile fields. `backfill-assertions` reconstructed 342,661 exact claims from existing child rows; 659,745 assertions are now stored. Web profile lists claims. Evidence: `apps/ingest/philfacilities_ingest/assertions.py`, `tests/test_assertions.py`, live DB query. |
| AF7-05 | Implement location-precision display/filter | DONE | Geometry quality | Public API exposes `location.precision` on every facility and the `location_precision` filter on list/within/nearby/domain searches; map markers reduce emphasis for approximate points and profiles label the precision. Coordinate counts are reported per subtype. |
| AF7-06 | Implement facility match review/merge audit | DONE | Identity matching | `merge_match_candidate` records source/target snapshots, moved child IDs, location state and an `active` flag; `match-candidates-undo-merge` restores the source facility, links, locations and child evidence only when every moved row is unchanged. Both merge and undo write `history.facility_change_events`. Tests cover successful restore and refusal after evidence drift. Evidence: `apps/ingest/philfacilities_ingest/matching.py`, `tests/test_matching_merge.py`. |
| AF7-07 | Implement public correction proposal workflow | DEFERRED | Governance design | Corrections reviewed before publication |

## AF8 — Ongoing release operations

| ID | Task | Status | Dependencies | Acceptance evidence |
|---|---|---|---|---|
| AF8-01 | Publish multi-source release manifest | DONE | Source release records | `release-manifest` CLI builds a checksummed JSON manifest from published datasets/releases: exact release labels, source and reference dates, rights/publication/coverage states, counts, linked facilities, coordinates, attribution and known gaps. Excluded/blocked datasets are listed with reasons. Tests: `apps/ingest/tests/test_manifest.py`. Evidence: `apps/ingest/philfacilities_ingest/manifest.py`, `docs/reports/08-release-manifest.json`. |
| AF8-02 | Add source update discovery by source mode | DONE | Acquisition framework | `update_discovery_mode()` classifies each source as `file_checksum`, `payload_checksum`, `manual` or `observations_only`. Checks compare the fetched SHA-256 with the latest published release and record `update_available` plus `new_release_detected`; conditional 304 responses remain `not_modified`. PAGASA live readings are explicitly excluded from release detection, and human-download sources remain manual. Live check of PPA returned `file_checksum` with `new_release_detected=false`. Tests: `tests/test_scheduling.py`. |
| AF8-03 | Add schema drift and unusual count alerts | DONE | Source parsers | Source checks already fail a release on parse errors, zero accepted rows or missing expected markers, and quarantine a new failed release while retaining the previous published release. New: `row_count_anomaly()` compares parsed counts with the prior published release (baseline >= 20; outside 0.5–2.0 ratio) and writes a `quality.row_count_anomaly` warning plus report/stat fields without silently discarding the release. Tests: `tests/test_pipeline_reprocess.py`. |
| AF8-04 | Add atomic publication/rollback for multi-source release | NOT STARTED | Release manifest | Previous valid release recoverable |
| AF8-05 | Add monthly source register review | DONE | Source inventory | `philfacilities-ingest source-review --days 30` lists all 22 registered sources with URL, access method, update pattern, rights/publication decision, last check status/date and a `review_due` flag. Current run: `registered=22 review_due=11 window_days=30`, surfacing sources never checked since registration (BIR, CHED, DSWD, DTI, NMP, NBI and others). Tests: `tests/test_scheduling.py`. |
| AF8-06 | Publish coverage and quality release notes | DONE | AF7 | `philfacilities-ingest release-notes` writes Markdown notes plus a checksummed manifest with published facility counts by inclusion class/category, every included source release, coverage gaps, excluded datasets and caveats. Current artifact: `var/reports/release-notes.md` (105 lines), manifest checksum `4ea0d46…ac8e5`. Tests: `apps/ingest/tests/test_manifest.py`. |

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
| 2026-11-15 | AF1-06, AF1-07, AF1-28, AF3-01 to AF3-09 | Fetched the Geoportal public catalogue (HTTP 200, 1,887,823 bytes, 3,532 leaf entries), normalized 3,490 unique layer names, and assessed 20 facility candidates individually. Recorded WFS 401, the human bulk-download form, missing per-layer reuse terms, and `getlayerdetails` 404s. | Catalogue inventory is complete and machine-readable. No layer was ingested: access is gated and no layer-level rights exist, so AF3-02 to AF3-09 are `BLOCKED` rather than falsely marked done. |
| 2026-11-16 | AF4-01, AF4-09 | Added the LGU facility-inventory intake template and validator (`validate-lgu-inventory`), with 10-digit PSGC checks, taxonomy/ownership/access validation, coordinate bounds/precision checks, provenance/date requirements, and fatal rejection of personal/security columns. The template is intentionally not an importer; a valid file remains a proposal. | 12 validator tests pass. No LGU inventory has been acquired and no submission is auto-published. Pilot selection and DB-backed review remain open. |

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
- [x] AF0-11: Define and test exclusions for ordinary businesses, retail buildings, malls, factories, warehouses, residences and unrelated company records. Evidence: `apps/ingest/philfacilities_ingest/eligibility.py` rejects non-taxonomy categories, commercial/residential subtype labels, and project/infrastructure-asset kinds before insertion; `OTHER_QUALIFYING_FACILITY` needs a documented function, service or access condition. Tests also prove a government service unit inside a mall and a regulated cold-storage establishment remain eligible when their own evidence supports it. Tests: `apps/ingest/tests/test_eligibility.py`.
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
- [x] AF1-48: Complete field-level mapping and privacy review for the published DepEd EBEIS source release; keep personal fields withheld. Evidence: parser 1.1.0 drops `Head / Position` from normalized payloads and maps grade bands to school-level flags. **Publication remains blocked by AF1-38**: the source has no reliable per-row public/private sector field, so all 5,055 canonical rows stay `internal`/`DISCOVERY_CANDIDATE`. PHLPost canonical publication is complete.
