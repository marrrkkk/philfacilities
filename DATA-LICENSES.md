# DATA-LICENSES.md — Source Rights Register

This file records the right to store, transform, display, and redistribute every external dataset
used by PhilFacilities. **A government dataset is not automatically public domain merely because it
can be viewed or downloaded.** Equally, the absence of an explicit licence or written permission is
not by itself a prohibition. Under [`docs/data-policy.md`](docs/data-policy.md),
a dataset may be published when its exact release is verified, publicly available through an open
route, and not subject to an explicit prohibition, provided that only reviewed non-personal fields
are exposed and provenance, attribution, and a takedown route are recorded. Explicit restrictions,
FOI/agreement conditions, and personal or sensitive data still control.

The technical publication gate in `apps/api/philfacilities_api/rights.py` and
`apps/ingest/philfacilities_ingest/sources/registry.py` enforces the decisions recorded here.

**Register updated:** 15 November 2026.  
**Scope:** this is a rights and engineering register, not a completed legal review. No agreement
has been accepted on an operator's behalf, and no access control, CAPTCHA, or Cloudflare challenge
has been bypassed.

## 1. Current dataset decisions

| Dataset | Publisher / source | Rights state | Publication state | Evidence and scope |
|---|---|---|---|---|
| Synthetic test fixtures (`demo-*`) | This repository | `not_applicable` | Test database only | Deterministically generated; every row has `is_synthetic=true`. Never an official record. The working production database contains zero synthetic facilities. |
| PhilHealth accredited healthcare facilities (26 provider-category releases) | PhilHealth | `approved_with_attribution` | `published` | PhilHealth's public site disclaimer permits use/reproduction for educational or informative purposes without written permission. Attribution is retained. The index listed 27 PDF links; 26 releases now produce publishable rows (28,207 accreditations across 13,546 linked facilities). `MCP_073126.pdf` returns HTTP 404. The Antenatal release was re-ingested with the corrected parser: 3,221 provider rows, ending at page 120; the PDF's expiry/sector annex (pages 121–240) is not counted. Evidence: `docs/operations/evidence/2026-11-16-philhealth-antenatal-reingestion/`. Terms-based decision, not a legal opinion. |
| PSGC Q2 2024 snapshot (BetterGov Classification API) | BetterGov.PH, derived from PSA PSGC | `approved_with_attribution` | `published` | BetterGov publishes the classification API under CC BY-SA 4.0. The snapshot is supplementary, versioned as `PSGC-Q2-2024-BETTERGOV`, and is **not** the latest official PSA release. 43,760 units were loaded. Attribution and share-alike are retained. |
| OpenStreetMap health facilities (HOT Philippines GeoParquet extract) | OpenStreetMap contributors, via HOT and BetterGov.PH | `approved_with_attribution` | `published` | ODbL 1.0. 17,421 source records; 17,410 linked facilities. Coordinates are bbox-centre map geocodes (`map_geocoded`), not official or GPS locations. A mapped feature does not establish operational status. Attribution is required; derivative databases remain share-alike. |
| OpenStreetMap education facilities (HOT Philippines GeoParquet extract) | OpenStreetMap contributors, via HOT and BetterGov.PH | `approved_with_attribution` | `published` | ODbL 1.0. 52,839 source records; 52,824 linked facilities. Same coordinate, status, attribution, and share-alike caveats. This is not a DepEd masterlist. |
| DepEd EBEIS school masterlist (NCR result set) | Department of Education | `approved_with_attribution` | source release `published`; canonical facilities published as unclassified | The public EBEIS result set is a government work. RA 8293 §176 supports publication of institution-level fields for non-commercial public-interest use, with attribution and a recorded takedown route; this is not a legal opinion. The re-ingested 15 November 2026 release is `approved_with_attribution`/`published`; the earlier `restricted_non_redistributable` release is retained. School-head names and other personal fields stay in the private source store and are never published. 5,055 records are linked and published as `DISCOVERY_CANDIDATE`/unclassified because the source has no reliable sector field. |
| DepEd Masterlist of Schools, SY 2020-2021 | Department of Education | `approved_with_attribution` | `published` (enrichment-only) | Official 544-page PDF with 60,924 rows. Government work; RA 8293 §176 supports publication of institution-level fields with attribution for non-commercial public-interest use; this is not a legal opinion. DepEd returns HTTP 403 to automated clients, so the preserved Wayback copy of the same 5,893,824-byte artifact (SHA-256 `461a96d3fa2bca1f046ac4fb5c5ea1b7430e2f190c7253fe54f64dfdf87547d5`) is acquired and checksummed. The release fills missing ownership, classification, and school-sector fields by exact six-digit BEIS ID; it does not create or rename facilities, and it only replaces placeholder classifications such as `DISCOVERY_CANDIDATE`/`unknown`. |
| DepEd Masterlist SY 2020-2021 — tabular detail (BetterGov dataset 41) | Department of Education; transcription via BetterGov Open Data Portal | `approved_with_attribution` | `published` (enrichment-only) | BetterGov dataset 41 states CC BY 4.0 and attributes the work to DepEd. The CSV is 10,397,735 bytes with SHA-256 `8ff9e4483b3b32453819f14a1a5260ceffbcdbb972395c9e95241dcb3e42b3fd` and 60,924 unique six-digit BEIS IDs. Only institution-level school fields are published, with attribution and takedown on notice. The release fills missing school-management, division, district, legislative-district, settlement, and offering fields by exact BEIS ID; it never creates or renames a facility. |
| National Library of the Philippines public-library directory | National Library of the Philippines | `approved_with_attribution` | `published` | December 2025 official PDF, 1,752 rows. Government work published under RA 8293 §176 and the documented public-interest basis, with attribution. Institutional library fields are published; named librarian and personal contact fields remain in the private raw release and are not exposed. This is a documented publication decision, not a legal opinion. |
| National Museum regional, area and site museums | National Museum of the Philippines | `approved_with_attribution` | `published` | Official directory and linked site pages. Government work published under RA 8293 §176 and the documented public-interest basis, with attribution. This is a directory subset of NMP-run sites, not a census of all Philippine museums. |
| PHLPost post-office locator | Philippine Postal Corporation | `approved_with_attribution` | `published` | Public locator table with province, post-office name, address, and services. The page carries a copyright/all-rights-reserved notice; the recorded product decision publishes only factual locator fields with attribution and takedown-on-notice, and does not copy expressive content. 1,272 facilities are published. The earlier `review_required` release is retained internally. This is a documented product decision, not legal advice. |
| BIR Revenue Regions and Revenue District Offices | Bureau of Internal Revenue | `approved_with_attribution` | `published` | RAO No. 006-2025, 9 December 2025. Government work published under RA 8293 §176 and the documented public-interest basis, with attribution. The image-only PDF was processed with local OCR; raw OCR output and confidence are retained, and OCR text is not treated as a replacement for the official document. 128 RDO rows and 19 revenue-region headings. |
| DSWD Centers and Residential Care Facilities (CRCF) directory | Department of Social Welfare and Development | `approved_with_attribution` | `published` | Official public directory. Institutional facility name, responsible field office, and postal address are published under RA 8293 §176 and the documented public-interest basis, with attribution. No coordinates, admission rules, or operational status are inferred. 76 facilities. |
| NMIS NARIS accredited meat establishments | National Meat Inspection Service | `approved_with_attribution` | `published` | Public accreditation directory carrying an all-rights-reserved notice. Only factual establishment name, LTO number, establishment type, and postal address are published with attribution and takedown-on-notice; expressive page content is not copied. The page currently returns a WAF challenge/TLS failure, so the verified 15 November 2026 artifact is the release of record. 357 establishments; many operators are private and a licence is not proof of current operation. |
| PPA List of Ports Covered in PPA Statistics | Philippine Ports Authority | `approved_with_attribution` | `published` | 22-page public PDF published by a government-owned and controlled corporation. RA 8293 §176 provides that no copyright subsists in a government work, subject to prior approval for commercial use; PhilFacilities publishes the factual port name, PPA region/PMO hierarchy, base-port/TMO/other-government/private group, RORO/NON-RORO marks and remarks for non-commercial public-interest use with attribution. No coordinates, berth capacity, owner names or operational status are inferred. 574 rows: 303 government (54 base ports, 94 TMO/OTP, 155 other government) and 271 private public-service providers. Directory subset, not a census of every port or landing place. |
| DTI Negosyo Center directory | Department of Trade and Industry | `approved_with_attribution` | `published` | Public DTI finder backed by unauthenticated JSON endpoints. DTI's Terms and Conditions permit quoting or reproducing the information in whole or in part provided DTI is informed/credited, and restrict commercial resale/redistribution/derivative works without written consent. PhilFacilities publishes the factual center name, postal address, region/province/city labels and source active flag for non-commercial public-interest use with attribution and takedown-on-notice; phone and email values are withheld. 1,427 active center records across 17 regions. No coordinates, PSGC codes, ownership, operator, hours or public-access conditions are inferred; a center is a government service unit, not a claim about its host building. |
| DepEd Machine-Ready Files | Department of Education | `review_required` | `blocked` | Human download/terms flow not completed. HTTP 403 on the checked page. No file acquired. |
| BetterGov Open Data Portal dataset 26, “Philippine Critical Facilities” | BetterGov.PH, consolidating UP WebGIS/OSM layers | `review_required` | `blocked` | Dataset metadata states no licence or licence URL. The 55,829-point file is explicitly undeduplicated and carries only `type`, `name`, `amenity`, `osm_id` and point geometry. It adds no ownership, subtype, service or operational field beyond the OSM layers already ingested, and provenance mixes UP WebGIS with OSM-derived records. Not ingested. |
| DOH National Health Facility Registry | Department of Health | `approved_with_attribution` | `published` (enrichment-only) | Official September 2026 XLSX export: 44,799 facilities with unique DOH codes. Government work; RA 8293 §176 supports publication of institution-level fields with attribution for non-commercial public-interest use; this is not a legal opinion. The official site returns HTTP 403 behind Cloudflare, so the preserved public copy of the same 4,939,611-byte export (SHA-256 `470c967db52e90bf9d7018d0434d3166e1d17ed04714edcc7ceadb78bad82835`) is acquired and checksummed. Contact details, street/building addresses, and facility-head fields are discarded. Exact DOH-code matches fill only missing profile fields; unmatched rows create new official health facilities. 29,779 existing codes were enriched and 15,020 facilities added. |
| DOH HFSRB licensed facilities | Department of Health | `review_required` | `blocked` | HTTP 403. No file acquired; licensing semantics and reuse terms are not established. |
| Official PSA PSGC workbook/API data | Philippine Statistics Authority | `review_required` | `blocked` | Workbook and page returned HTTP 403 behind Cloudflare on 15 November 2026. The classification index returned HTTP 200, but collection endpoints return HTTP 400 `Token is required.` No token was obtained and no access control was bypassed. |
| CHED HEIDA HEI directory | Commission on Higher Education | `publicly_available_verified` | `published` | Public server-rendered directory at https://heida.ched.gov.ph/hei-directory; 18 regional directories, 280 pages and 2,716 institution rows were read on 15 November 2026 (2,711 unique after 5 duplicate source rows). No explicit prohibition, access control or terms restriction was found. Only institutional name, CHED code, institutional type, address and region are published; contact details and institutional-head names are discarded. 527 chartered state colleges/universities and 160 local-government colleges/universities are government facilities; 868 non-profit, 616 private-corporate and 418 religious/faith-based institutions are private public-service providers; 123 `Others`/`CHED-Supervised Institution`/unrecognised rows are published as unclassified records. No coordinates, PSGC codes, campus-level precision or operational status are inferred. Attribution and a takedown-on-notice route are recorded. This is a documented publication decision, not a legal opinion. |
| TESDA TVI / Assessment Centers | TESDA | `review_required` | `blocked` | Directory page returned HTTP 200, but the monitoring classifier records an access challenge; no verified provider-level bulk release. |
| BetterGov Statistics API / PSA 2024 Census population | BetterGov.PH, reproducing saved PSA OpenSTAT tables | `approved_with_attribution` | `published` | 134,748 observations in 18 regional releases. BetterGov publishes its original material under CC BY-SA 4.0 and identifies each saved PSA table URL and release. The portal states that its preview does not itself establish redistribution rights, so this engineering decision relies on the CC BY-SA 4.0 compilation licence and retains PSA attribution and source-table links; PSA remains authoritative. Values are counts of persons or households as labelled, never facility capacity. Missing values stay null. |
| PSA OpenSTAT / 2024 Census (direct) | Philippine Statistics Authority | `review_required` | `blocked` | Only saved snapshots obtained through BetterGov have been inspected. Direct PSA OpenSTAT bulk acquisition and any dataset-specific terms review remain outstanding. |
| BetterGov Statistics API (other indicators) | BetterGov.PH / underlying PSA tables | `review_required` | `blocked` | The 2024 Census population tables are the only statistics ingested. Other indicators require their own source-table and rights review. |
| GeoRiskPH / HazardHunterPH | Office of Civil Defense and partner agencies | `unknown` | `blocked` | Discovery only. `georisk.gov.ph` failed local TLS verification; HazardHunterPH returned HTTP 200. No hazard layer was acquired. |
| PHIVOLCS | DOST-PHIVOLCS | `unknown` | `blocked` | Discovery only. Main site returned HTTP 200; the maps portal failed TLS negotiation. No layer acquired. |
| PAGASA | DOST-PAGASA | `unknown` | `blocked` | Discovery only. Main site and Climgrid/climapv2 returned HTTP 200. No climate layer acquired. |
| DENR — Mines and Geosciences Bureau | DENR-MGB | `unknown` | `blocked` | Discovery only. Homepage returned HTTP 403. No geohazard layer acquired. |
| Open Data Philippines | DICT / government publishers | `unknown` | `blocked` | Portal returned HTTP 200; the queried public dataset search API returned HTTP 404 unauthenticated. No dataset was registered or published from this catalogue. |
| DILG DRRM-PULSE facility feed | Department of the Interior and Local Government — NCR | `review_required` | `blocked` | Public portal at https://drrm.ncr.dilg.gov.ph/ describes participating-LGU validation. The public `/api/facilities.geojson` endpoint returned exactly one validated feature on 15 November 2026 (`Marikina Rescue 161 / MCDRRMO Command Center`, exact coordinates) regardless of query parameters, while `/api/map-layers.geojson` returned an empty collection and the `/lgus` page listed participating LGUs. The feed is not a usable bulk facility inventory, and emergency-facility coordinates require a security review. No bulk ingest or publication decision is claimed. |
| Other agency facility directories (DILG, BFP, PNP, BJMP, BuCor, DPWH, DENR, NAMRIA, NHA, NCCA, LWUA, MWSS, DOTr/LTFRB, DICT) | Various government agencies | `unknown` | `blocked` | Discovery targets only. Homepage reachability was probed on 15 November 2026; no verified facility dataset, machine-readable export, schema, or publication decision exists. The DSWD CRCF directory is recorded separately and is published. |

## 2. Implemented rights and publication states

Rights states:

- `unknown`
- `review_required`
- `approved_public_redistribution`
- `approved_with_attribution`
- `publicly_available_verified`
- `restricted_non_redistributable`
- `denied`
- `expired`

Publication states:

- `blocked`
- `internal_only`
- `quarantined`
- `approved`
- `published`

The canonical constants live in `apps/api/philfacilities_api/rights.py`. `publicly_available_verified`
is public-compatible: the exact release is verified, publicly available, and not subject to an
explicit prohibition, and only reviewed institutional fields are published. It does **not** bypass
the publication gate, which still requires an approved or published release. The public API filters
facilities by canonical publication status and filters source evidence to datasets/releases whose
rights state permits public display. Bulk CSV/Parquet endpoints, statistics, accreditation lists, and
facility detail source evidence apply the same gate.

## 3. Acquired artifacts and integrity evidence

| Dataset | Release(s) | Raw artifact | Rows / units | Notes |
|---|---|---|---|---|
| PSGC Q2 2024 | `PSGC-Q2-2024-BETTERGOV` | BetterGov API JSON | 43,760 units | 18 regions, 82 provinces, 1,656 municipalities, 42,004 barangays; two unknown-level rows skipped with warnings. SHA-256 `3f1fe61d…`. |
| PSA 2024 Census population | 18 regional releases | BetterGov JSON snapshots | 134,748 observations | 43,768 distinct PSGC codes; source table URLs, release identifiers, and retrieval timestamps retained. |
| PhilHealth hospitals | `PHILHEALTH-HOSP_093026-2026-09-30` | `HOSP_093026.pdf` | 1,932 accreditations | 75 pages; page/row references retained. Raw PDF retained. |
| PhilHealth other provider categories | 25 additional dated releases | Category PDFs | 26,273 accreditations | Includes the re-ingested Antenatal release (3,221 accreditations) after the annex double-count was corrected and withdrawn records were removed. |
| PhilHealth Birthing Homes | No release | `MCP_073126.pdf` | 0 | HTTP 404 at the published URL; recorded as `not_found`, no rows fabricated. |
| OSM health | `HOT-OSM-PHL-HEALTH-2026-11-15` | `health_facilities.parquet` | 17,421 source records | Immutable GeoParquet with checksum; only named features become facilities. |
| OSM education | `HOT-OSM-PHL-EDUCATION-2026-11-15` | `education_facilities.parquet` | 52,839 source records | Immutable GeoParquet with checksum; only named features become facilities. |
| DepEd EBEIS NCR | `DEPED-EBEIS-NCR-2026-11-15` | Aggregated HTML result set | 5,055 records | Current release is `approved_with_attribution`/`published`; the earlier `restricted_non_redistributable` release is retained. School-head names withheld; rows without an exact 2020 masterlist match remain unclassified. |
| DepEd Masterlist SY 2020-2021 | `DEPED-MASTERLIST-SY2020-2021` | Official PDF, 544 pages | 60,924 records | Enrichment-only release; 60,924 exact six-digit BEIS IDs updated with sector/ownership evidence. SHA-256 `461a96d3fa2bca1f046ac4fb5c5ea1b7430e2f190c7253fe54f64dfdf87547d5`. The official DepEd URL returns HTTP 403; the preserved Wayback copy is the acquired artifact. |
| DepEd Masterlist SY 2020-2021 — tabular detail | `DEPED-MASTERLIST-SY2020-2021-DETAIL` | BetterGov dataset 41 CSV, CC BY 4.0 | 60,924 records | Enrichment-only release; 60,924 exact six-digit BEIS IDs updated with school-management, division, district, legislative-district, settlement, and offering fields. CSV SHA-256 `8ff9e4483b3b32453819f14a1a5260ceffbcdbb972395c9e95241dcb3e42b3fd`. |
| NLP public libraries | `NLP-PUBLIC-LIBRARIES-2025-12` | Official PDF | 1,752 rows | Institutional fields published; personal librarian contact fields excluded. |
| NMP museums | `NMP-MUSEUMS-2026-11-15` | Official directory | Directory subset | NMP-run regional, area, and site museums; not all Philippine museums. |
| PHLPost locator | `PHLPOST-LOCATOR-2026-11-15` | Public HTML table | 1,272 facilities | Factual locator fields published; earlier `review_required` release retained internally. |
| BIR RDOs | `BIR-RAO-006-2025` | Official image-only PDF + local OCR | 128 RDO rows; 19 region headings | OCR output retained with confidence; not a substitute for the official document. |
| DSWD CRCF directory | `DSWD-CRCF-2026-11-15` | Official HTML directory | 76 facilities | Institutional name, field office, and postal address; no coordinates or operational status. |
| NMIS NARIS establishments | `NMIS-NARIS-2026-11-15` | Public accreditation directory | 357 establishments | Factual establishment fields only; many operators are private; page currently behind a WAF/TLS failure. |
| PPA ports | `PPA-PORT-LIST-2026-11-15` | Official PDF, 22 pages | 574 port rows | 303 government and 271 private public-service providers; hierarchy and RORO marks preserved; no coordinates or operational status inferred. |
| DTI Negosyo Centers | `DTI-NEGOSYO-2026-11-15` | Public JSON API | 1,427 active center records | Factual name, address and geographic labels; contact fields withheld; government service units with unspecified ownership/operator; no coordinates or operational status inferred. |

Complete checksums, file sizes, row counts, and report paths are in the release rows in the
`source` schema and in `var/reports/`; the current measured snapshot is in
`var/reports/02-acquisition-report.md`. Raw files are retained under `var/raw/` (or the configured
S3-compatible store) and are never overwritten by a later release.

## 4. Source-by-source checklist

- [x] PhilHealth: terms captured, attribution recorded, state set to `approved_with_attribution`; 25 releases published.
- [x] BetterGov PSGC: licence captured (CC BY-SA 4.0), attribution recorded, snapshot limitation documented.
- [x] OSM/HOT health and education: ODbL captured, attribution recorded, coordinate-precision limitation documented.
- [x] PSA 2024 Census population: saved OpenSTAT snapshots obtained through BetterGov; CC BY-SA 4.0 compilation licence, PSA table URLs and release identifiers retained; missing values kept null.
- [x] DepEd EBEIS: public government result set; current release published for institution-level fields with attribution and a recorded takedown route; school-head names withheld. Rows without an exact 2020 masterlist match remain unclassified.
- [x] DepEd SY 2020-2021 Masterlist: official PDF acquired from the preserved Wayback copy; institution-level sector/ownership enrichment published with attribution; 60,924 exact BEIS IDs updated without renaming facilities or replacing established classifications.
- [x] NLP public libraries: public government PDF; institution-level fields published with attribution; personal librarian contacts withheld.
- [x] NMP museums: public government directory; institutional museum fields published with attribution.
- [x] PHLPost locator: 1,272 factual locator facilities published with attribution and takedown-on-notice; copyright notice recorded; earlier release retained internally.
- [x] BIR RDOs: official RAO parsed with local OCR; institutional office fields published with attribution.
- [x] DSWD CRCF: official directory; institutional facility fields published with attribution.
- [x] NMIS NARIS: factual establishment fields published with attribution and takedown-on-notice; all-rights-reserved notice recorded.
- [x] PPA ports: official government-work PDF; factual port name, hierarchy and RORO marks published with attribution; private ports classified as providers, not government facilities.
- [x] DTI Negosyo Centers: public JSON directory; factual center name, address and geographic labels published with attribution and takedown-on-notice; contact fields withheld; no ownership/operator/host inference.
- [ ] Official PSA PSGC workbook/API data: acquire through an authorized route and record terms.
- [ ] DepEd Machine-Ready Files: complete the human download/terms flow; inspect actual schemas and coordinates.
- [x] DOH NHFR: official September 2026 export acquired from the preserved public mirror and checksum-pinned; institution-level registry fields published with attribution; contact details, street/building address, and facility-head fields withheld while barangay/city/province locality is retained. 29,779 exact DOH codes enriched without renaming or reclassifying, and 15,020 unmatched official facilities added.
- [ ] DOH HFSRB licensed facilities: review the applicable terms and licensing semantics before any publication.
- [x] CHED HEIDA: public directory published under `publicly_available_verified` for institutional fields only; contact details and head names discarded.
- [ ] TESDA: verify a provider-level bulk export or public dataset; if it is publicly available with no explicit prohibition, apply the policy in `docs/data-policy.md`.
- [ ] BetterGov Statistics/OpenSTAT/Census: inventory additional indicators and verify source-table rights.
- [ ] Hazard and additional agency sources: verify actual data and any explicit prohibition before integration.
- [ ] Formal legal review: not completed for any source. This register records engineering and product decisions; it does not replace legal advice.

## 5. Publication rule

A source remains `unknown` or `review_required` until a documented decision exists. A verified,
publicly available source with no explicit prohibition may be set to `publicly_available_verified`;
an explicit licence or terms statement may support `approved_public_redistribution` or
`approved_with_attribution`. Do not expose source rows, contact information, coordinates, or derived
bulk exports publicly by default. Where only limited use is allowed, configure the publication scope
at dataset/field level. A failed or blocked check must never delete or unpublish an earlier permitted
release.

Explicit restrictions always control. A source that is access-controlled, FOI/agreement-bound,
expressly non-redistributable, or personal/security-sensitive remains excluded or restricted even if
some records can be viewed publicly.

The current public boundary is verified by integration tests and by the measured reports:

- the current DepEd EBEIS source release is published for institution-level fields, canonical
  DepEd facilities are published as unclassified records, and school-head names are never public;
- PHLPost publishes 1,272 factual locator facilities; an earlier review-required release is retained
  internally;
- blocked official sources have no releases and no public facilities;
- blocked or internal source evidence is omitted from public facility detail pages;
- the Antenatal PhilHealth release was re-ingested with the corrected parser; its 3,221
  provider rows stop at page 120, the 121–240 annex is not counted, and the earlier
  3,184 source-less change events remain exported and removed;
- OSM records remain labelled crowd-sourced with `map_geocoded` coordinates and unknown operational
  status.

Reports generated from the database describe the last measured database state. A source registry or
release decision and the canonical facility publication flag can move at different times; a
re-ingestion or field-level review is required before every surface reflects the same state. This
distinction is retained rather than rewriting a measured snapshot as if it were a fresh run.

## 6. Code license is separate

The Apache-2.0 license for application code does not license source files or facts. See `NOTICE`,
`docs/data-policy.md`, and
`docs/decisions/0004-data-licensing-and-publication-gates.md`.
