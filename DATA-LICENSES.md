# DATA-LICENSES.md — Source Rights Register

This file records the right to store, transform, display, and redistribute every external dataset
used by PhilFacilities. **A government dataset is not public domain merely because it can be viewed
or downloaded.** The technical publication gate in `apps/api/philfacilities_api/rights.py` and
`apps/ingest/philfacilities_ingest/sources/registry.py` enforces the decisions recorded here.

**Register updated:** 15 November 2026.  
**Scope:** this is a terms-based engineering register, not a completed legal review. No agreement
has been accepted on an operator's behalf, and no access control, CAPTCHA, or Cloudflare challenge
has been bypassed.

## 1. Current dataset decisions

| Dataset | Publisher / source | Rights state | Publication state | Evidence and scope |
|---|---|---|---|---|
| Synthetic test fixtures (`demo-*`) | This repository | `not_applicable` | Test database only | Deterministically generated; every row has `is_synthetic=true`. Never an official record. The working production database contains zero synthetic facilities. |
| PhilHealth accredited healthcare facilities (25 provider-category releases) | PhilHealth | `approved_with_attribution` | `published` | PhilHealth's public site disclaimer permits use/reproduction for educational or informative purposes without written permission. Attribution is retained. The index listed 27 PDF links; 26 files were acquired and 25 releases produced publishable rows (24,986 accreditations across 13,546 facilities). `MCP_073126.pdf` returns HTTP 404. The acquired Antenatal release is retained but blocked: its first parse recorded 6,562 rows, a review found the PDF's expiry/sector annex had been counted as provider rows, all derived records were withdrawn, and the corrected parser re-reads 3,221 provider rows. It is not published. Terms-based decision, not a legal opinion. |
| PSGC Q2 2024 snapshot (BetterGov Classification API) | BetterGov.PH, derived from PSA PSGC | `approved_with_attribution` | `published` | BetterGov publishes the classification API under CC BY-SA 4.0. The snapshot is supplementary, versioned as `PSGC-Q2-2024-BETTERGOV`, and is **not** the latest official PSA release. 43,760 units were loaded. Attribution and share-alike are retained. |
| OpenStreetMap health facilities (HOT Philippines GeoParquet extract) | OpenStreetMap contributors, via HOT and BetterGov.PH | `approved_with_attribution` | `published` | ODbL 1.0. 17,421 source records; 17,410 linked facilities. Coordinates are bbox-centre map geocodes (`map_geocoded`), not official or GPS locations. A mapped feature does not establish operational status. Attribution is required; derivative databases remain share-alike. |
| OpenStreetMap education facilities (HOT Philippines GeoParquet extract) | OpenStreetMap contributors, via HOT and BetterGov.PH | `approved_with_attribution` | `published` | ODbL 1.0. 52,839 source records; 52,824 linked facilities. Same coordinate, status, attribution, and share-alike caveats. This is not a DepEd masterlist. |
| DepEd EBEIS school masterlist (NCR result set) | Department of Education | `restricted_non_redistributable` | `internal_only` | The public HTML result set has no explicit reuse licence and contains school-head personal names. 5,055 records are retained privately for identity/provenance work only. Never returned by the public API, source evidence, statistics, or bulk downloads. |
| DepEd Machine-Ready Files | Department of Education | `review_required` | `blocked` | Human download/terms flow not completed. HTTP 403 on the checked page. No file acquired. |
| DOH National Health Facility Registry | Department of Health | `review_required` | `blocked` | Public endpoint returned HTTP 403 behind Cloudflare. Existing FOI disclosures may require a signed Data Release and Use Agreement; no agreement was reviewed or accepted. No export acquired. |
| DOH HFSRB licensed facilities | Department of Health | `review_required` | `blocked` | HTTP 403. No file acquired; licensing semantics and reuse terms are not established. |
| Official PSA PSGC workbook/API data | Philippine Statistics Authority | `review_required` | `blocked` | Workbook and page returned HTTP 403 behind Cloudflare on 15 November 2026. The classification index returned HTTP 200, but collection endpoints return HTTP 400 `Token is required.` No token was obtained and no access control was bypassed. |
| CHED HEIDA / HEI directory | Commission on Higher Education | `review_required` | `blocked` | Public directory returned HTTP 200; no verified bulk export, documented public API, or reuse terms. |
| TESDA TVI / Assessment Centers | TESDA | `review_required` | `blocked` | Directory page returned HTTP 200, but the monitoring classifier records an access challenge; no verified provider-level bulk export or reuse terms. |
| BetterGov Statistics API / PSA 2024 Census population | BetterGov.PH, reproducing saved PSA OpenSTAT tables | `approved_with_attribution` | `published` | 134,748 observations in 18 regional releases. BetterGov publishes its original material under CC BY-SA 4.0 and identifies each saved PSA table URL and release. The portal states that its preview does not itself establish redistribution rights, so this engineering decision relies on the CC BY-SA 4.0 compilation licence and retains PSA attribution and source-table links; PSA remains authoritative. Values are counts of persons or households as labelled, never facility capacity. Missing values stay null. |
| PSA OpenSTAT / 2024 Census (direct) | Philippine Statistics Authority | `review_required` | `blocked` | Only saved snapshots obtained through BetterGov have been inspected. Direct PSA OpenSTAT bulk acquisition and any dataset-specific terms review remain outstanding. |
| BetterGov Statistics API (other indicators) | BetterGov.PH / underlying PSA tables | `review_required` | `blocked` | The 2024 Census population tables are the only statistics ingested. Other indicators require their own source-table and rights review. |
| GeoRiskPH / HazardHunterPH | Office of Civil Defense and partner agencies | `unknown` | `blocked` | Discovery only. `georisk.gov.ph` failed local TLS verification; HazardHunterPH returned HTTP 200. No hazard layer or reuse permission was acquired. |
| PHIVOLCS | DOST-PHIVOLCS | `unknown` | `blocked` | Discovery only. Main site returned HTTP 200; the maps portal failed TLS negotiation. No layer or reuse permission acquired. |
| PAGASA | DOST-PAGASA | `unknown` | `blocked` | Discovery only. Main site and Climgrid/climapv2 returned HTTP 200. No climate layer or reuse permission acquired. |
| DENR — Mines and Geosciences Bureau | DENR-MGB | `unknown` | `blocked` | Discovery only. Homepage returned HTTP 403. No geohazard layer or reuse permission acquired. |
| Open Data Philippines | DICT / government publishers | `unknown` | `blocked` | Portal returned HTTP 200; the queried public dataset search API returned HTTP 404 unauthenticated. No dataset was registered or published from this catalogue. |
| Other agency facility directories (DILG, BFP, PNP, BJMP, BuCor, DSWD, DPWH, DENR, NAMRIA, NHA, NLP, NCCA, LWUA, MWSS, DOTr/LTFRB, DICT) | Various government agencies | `unknown` | `blocked` | Discovery targets only. Homepage reachability was probed on 15 November 2026; no verified facility dataset, machine-readable export, schema, or reuse decision exists. |

## 2. Implemented rights and publication states

Rights states:

- `unknown`
- `review_required`
- `approved_public_redistribution`
- `approved_with_attribution`
- `restricted_non_redistributable`
- `denied`
- `expired`

Publication states:

- `blocked`
- `internal_only`
- `quarantined`
- `approved`
- `published`

The canonical constants live in `apps/api/philfacilities_api/rights.py`. The public API filters
facilities by canonical publication status and filters source evidence to datasets/releases whose
rights state permits public display. Bulk CSV/Parquet endpoints, statistics, accreditation lists, and
facility detail source evidence apply the same gate.

## 3. Acquired artifacts and integrity evidence

| Dataset | Release(s) | Raw artifact | Rows / units | Notes |
|---|---|---|---|---|
| PSGC Q2 2024 | `PSGC-Q2-2024-BETTERGOV` | BetterGov API JSON | 43,760 units | 18 regions, 82 provinces, 1,656 municipalities, 42,004 barangays; two unknown-level rows skipped with warnings. SHA-256 `3f1fe61d…`. |
| PSA 2024 Census population | 18 regional releases | BetterGov JSON snapshots | 134,748 observations | 43,768 distinct PSGC codes; source table URLs, release identifiers, and retrieval timestamps retained. |
| PhilHealth hospitals | `PHILHEALTH-HOSP_093026-2026-09-30` | `HOSP_093026.pdf` | 1,932 accreditations | 75 pages; page/row references retained. Raw PDF retained. |
| PhilHealth other provider categories | 24 additional dated releases | Category PDFs | 22,825 accreditations | Includes one Antenatal release retained but `blocked` after its derived records were withdrawn. |
| PhilHealth Birthing Homes | No release | `MCP_073126.pdf` | 0 | HTTP 404 at the published URL; recorded as `not_found`, no rows fabricated. |
| OSM health | `HOT-OSM-PHL-HEALTH-2026-11-15` | `health_facilities.parquet` | 17,421 source records | Immutable GeoParquet with checksum; only named features become facilities. |
| OSM education | `HOT-OSM-PHL-EDUCATION-2026-11-15` | `education_facilities.parquet` | 52,839 source records | Immutable GeoParquet with checksum; only named features become facilities. |
| DepEd EBEIS NCR | `DEPED-EBEIS-NCR-2026-11-15` | Aggregated HTML result set | 5,055 records | Internal-only; contains school-head names; 169 result pages. |

Complete checksums, file sizes, row counts, and report paths are in the release rows in the
`source` schema and in `var/reports/`; the current measured snapshot is in
`docs/reports/02-acquisition-report.md`. Raw files are retained under `var/raw/` (or the configured
S3-compatible store) and are never overwritten by a later release.

## 4. Source-by-source checklist

- [x] PhilHealth: terms captured, attribution recorded, state set to `approved_with_attribution`; 25 releases published.
- [x] BetterGov PSGC: licence captured (CC BY-SA 4.0), attribution recorded, snapshot limitation documented.
- [x] OSM/HOT health and education: ODbL captured, attribution recorded, coordinate-precision limitation documented.
- [x] PSA 2024 Census population: saved OpenSTAT snapshots obtained through BetterGov; CC BY-SA 4.0 compilation licence, PSA table URLs and release identifiers retained; missing values kept null.
- [x] DepEd EBEIS: no explicit reuse licence found; personal names present; state set to `restricted_non_redistributable` and publication to `internal_only`.
- [ ] Official PSA PSGC workbook/API data: acquire through an authorized route and record terms.
- [ ] DepEd Machine-Ready Files: complete the human download/terms flow; inspect actual schemas and coordinates.
- [ ] DOH NHFR/HFSRB: review the applicable Data Release and Use Agreement before any publication.
- [ ] CHED/TESDA: verify a permitted bulk export and reuse terms.
- [ ] BetterGov Statistics/OpenSTAT/Census: inventory additional indicators and verify source-table rights.
- [ ] Hazard and additional agency sources: verify actual data and permission before integration.
- [ ] Formal legal review: not completed for any source. This register records engineering decisions
      based on published terms; it does not replace legal advice.

## 5. Publication rule

A source remains `unknown` or `review_required` until a documented decision exists. Do not expose
source rows, contact information, coordinates, or derived bulk exports publicly by default. Where
only limited use is allowed, configure the publication scope at dataset/field level. A failed or
blocked check must never delete or unpublish an earlier permitted release.

The current public boundary is verified by integration tests and by the measured reports:

- internal DepEd EBEIS records are absent from `/v1/facilities`, `/v1/schools`, downloads, and statistics;
- blocked official sources have no releases and no public facilities;
- blocked or internal source evidence is omitted from public facility detail pages;
- the PhilHealth Antenatal release is retained but blocked; its withdrawn parse is not published, and the 3,184 source-less change events from that parse were exported and removed;
- OSM records remain labelled crowd-sourced with `map_geocoded` coordinates and unknown operational status.

## 6. Code license is separate

The Apache-2.0 license for application code does not license source files or facts. See
`docs/09-OPEN-SOURCE-GOVERNANCE.md` and `docs/decisions/0004-data-licensing-and-publication-gates.md`.
