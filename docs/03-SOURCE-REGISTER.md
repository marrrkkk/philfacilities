# 03 — Government Source Register

**Research baseline:** 14 November 2026.  
**Actual acquisition/probe status:** 15 November 2026.  
**Purpose:** A controlled register of actual source locations, access mechanisms, observed fields, limitations, and next acquisition actions.

> Reachability is not, by itself, a rights decision. A source may be viewable or downloadable while
> governed by a data-use agreement, website terms, privacy restrictions, or specific attribution
> requirements. Equally, the absence of an explicit licence is not automatically a prohibition:
> verified, publicly available records may be published under
> [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md)
> when no explicit restriction applies and only reviewed institutional fields are exposed. A
> registered source is not evidence that a complete national dataset exists.

## 0. Actual acquisition outcomes (15 November 2026)

Measured counts, checksums, release IDs, and rights states are in `docs/reports/01`–`05` and `DATA-LICENSES.md`.

| Source | Actual outcome | Public state |
|---|---|---|
| BetterGov PSGC Q2 2024 mirror | 43,760 units acquired and loaded: 18 regions, 82 provinces, 1,656 municipalities, 42,004 barangays; 2 unknown-level rows skipped | `published` with CC BY-SA 4.0 attribution; supplementary, not the latest official PSA workbook |
| PhilHealth provider-category PDFs | 26 current PDFs acquired; 25 releases produced publishable rows (24,986 accreditations); one PDF (`MCP_073126.pdf`) returned HTTP 404; the Antenatal release is retained but blocked after its initial parse was withdrawn | `published` with PhilHealth attribution, except the blocked Antenatal release |
| HOT/OSM health extract | 17,421 source records; 17,410 linked facilities; named features only, `map_geocoded` bbox-centre coordinates, `record_status=unknown` | `published` with ODbL attribution; not a DOH registry |
| HOT/OSM education extract | 52,839 source records; 52,824 linked facilities; same coordinate/status caveats | `published` with ODbL attribution; not a DepEd masterlist |
| PSA 2024 Census population via BetterGov | 134,748 observations across 18 regional releases; 43,768 distinct PSGC codes | `published` with CC BY-SA 4.0 compilation attribution; PSA remains authoritative |
| DepEd EBEIS masterlist (NCR) | 5,055 records acquired from 169 result pages | Current source release `published` for institution-level fields; canonical rows remain `internal` pending field-level mapping/privacy review |
| Official PSA PSGC workbook | HTTP 403 Cloudflare challenge; no file acquired | `blocked` |
| DepEd Machine-Ready Files | HTTP 403 / human terms flow; no file acquired | `blocked` |
| DOH NHFR / HFSRB | HTTP 403 Cloudflare challenge; no file or agreement accepted | `blocked` |
| CHED / TESDA | Directory pages reachable, but no verified bulk export or reuse terms | `blocked` (discovery only) |
| GeoRiskPH, HazardHunterPH, PHIVOLCS, PAGASA, DENR-MGB | Discovery probes only; no layer acquired | `blocked` |

The exact unauthenticated GET probe results, including TLS failures and HTTP statuses, are preserved in `docs/operations/evidence/2026-11-15-source-access/source-probes-2026-11-15.txt`.

## 1. Source overview

| Source | Official entry point | Observed access | Register status | Important caveat |
|---|---|---|---|---|
| DepEd Machine-Ready Files | https://www.deped.gov.ph/machine-ready-files/ | HTTP 403; human download/terms flow | Blocked | No official file acquired; no enrollment, facilities, personnel, ICT, or WASH schema verified |
| DepEd EBEIS masterlist | https://ebeis.deped.gov.ph/beis/reports_info/masterlist | HTTP 200 server-rendered result pages | Current source release published for institution-level fields; canonical rows internal | NCR result set acquired; contains school-head names that are withheld from publication |
| DOH NHFR | https://nhfr.doh.gov.ph/VActivefacilitiesList | HTTP 403 Cloudflare | Blocked | FOI disclosures may carry a Data Release and Use Agreement; no agreement reviewed or accepted |
| DOH HFSRB licensed facilities | https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/ | HTTP 403 Cloudflare | Blocked | Licensing semantics and reuse terms not established |
| PhilHealth accredited facilities | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/ | HTTP 200; category-specific PDFs | Published | Accreditation is benefit-package-specific and time-bound; one linked PDF is 404 |
| PSA PSGC | https://psa.gov.ph/classification/psgc | Page/workbook HTTP 403; API index 200, data collections require token | Blocked | BetterGov Q2 2024 mirror is loaded as labelled supplementary geography |
| PSA classification API | https://classification.psa.gov.ph/psgc | `/regions` HTTP 200; `/regions/all` HTTP 400 `Token is required.` | Blocked | A token is required; no token was obtained or bypassed |
| BetterGov Classification API | https://statistics.bettergov.ph/api/classification/psgc | HTTP 200 JSON | Published supplement | CC BY-SA 4.0; Q2 2024 snapshot, not the latest PSA release |
| BetterGov Statistics API | https://statistics.bettergov.ph/api/v1 | HTTP 200 JSON | Published supplement | Saved PSA OpenSTAT snapshots; only the 2024 Census population tables are used |
| HOT/OSM via BetterGov | https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/ | HTTP 200 GeoParquet | Published crowd-sourced facilities | ODbL; bbox-centre geocodes; operational status unknown |
| NLP public libraries | https://web.nlp.gov.ph/wp-content/uploads/2026/01/OFFICIAL-Integrated-Directory-of-Public-Libraries-as-of-December-2025.pdf | HTTP 200 PDF; 1,752 rows | Published | Institutional fields published; personal librarian contacts withheld |
| NMP museums | https://www.nationalmuseum.gov.ph/our-museums/regional-area-and-site-museums/ | HTTP 200 HTML directory | Published | NMP-run sites only; not all Philippine museums |
| PHLPost locator | https://phlpost.gov.ph/post-office-locator/ | HTTP 200 HTML table | Published; 1,272 factual locator facilities | Factual locator fields only; copyright notice recorded; earlier release retained internally |
| BIR RDOs | https://bir-cdn.bir.gov.ph/BIR/pdf/RAO%20No.%206-2025.pdf | HTTP 200 image-only PDF; local OCR | Published | Office/jurisdiction list, not street addresses or coordinates |
| DSWD CRCF directory | https://www.dswd.gov.ph/crcf/ | HTTP 200 HTML directory | Published; 76 facilities | Institutional name, field office, postal address only |
| NMIS NARIS | https://naris.nmis.gov.ph/ | Public accreditation directory; current recheck hits a WAF/TLS failure | Published; 357 establishments | Factual establishment fields only; many operators are private; licence is not operational status |
| PPA ports | https://ppa.com.ph/sites/default/files/List%20of%20Ports%20covered%20in%20PPA%20Statistics.pdf | HTTP 200 PDF, 22 pages | Published; 574 port rows | 303 government and 271 private providers; hierarchy and RORO marks preserved; no coordinates, owner names or operational status inferred |
| CHED HEIDA | https://heida.ched.gov.ph/hei-directory | HTTP 200 HTML | Later expansion | No complete bulk national export or documented public API verified |
| TESDA TVI | https://www.tesda.gov.ph/TVI | HTTP 200 HTML; monitor records an access challenge | Later expansion | No public JSON API or verified bulk export |
| TESDA Assessment Centers | https://www.tesda.gov.ph/AssessmentCenters | Not independently acquired | Later expansion | Terms and programmatic access not verified |
| HazardHunterPH | https://hazardhunter.georisk.gov.ph/ | HTTP 200 HTML | Discovery only | No hazard layer or publication decision acquired |
| GeoRiskPH | https://georisk.gov.ph/ | Local TLS certificate verification failure | Discovery only | Not bypassed; no data acquired |
| PHIVOLCS | https://www.phivolcs.dost.gov.ph/ | HTTP 200 HTML; maps portal TLS failure | Discovery only | No layer or publication decision acquired |
| PAGASA / Climgrid | https://www.pagasa.dost.gov.ph/ and https://climgridph.pagasa.dost.gov.ph/climapv2/ | HTTP 200 HTML | Discovery only | No climate layer or publication decision acquired |
| DENR-MGB | https://mgb.gov.ph/ | HTTP 403 | Discovery only | No geohazard layer or publication decision acquired |
| Open Data Philippines | https://data.gov.ph/ | HTTP 200 SPA; queried public API search returned 404 | Discovery only | No dataset from this catalogue was registered or published |

## 2. DepEd — schools

### Official sources

- Machine-Ready Files: https://www.deped.gov.ph/machine-ready-files/
- EBEIS masterlist: https://ebeis.deped.gov.ph/beis/reports_info/masterlist

### Identified dataset families (not acquired)

| Dataset family | Reference coverage identified in prior research | Potential value |
|---|---|---|
| School masterlist / characteristics | SY2023–24 listing | School identity, type, sector, administrative geography, levels offered |
| School enrollment | SY2017–18 to SY2024–25 advertised on the official page | Historical enrollment by year and grade/sex where present |
| School facilities | SY2023–24 | Rooms/buildings/facility condition indicators where published |
| Personnel | SY2023–24 | Teachers and school leadership counts where published |
| ICT | SY2023–24 | Academic/administrative computing resources |
| WASH and utilities | SY2023–24 | Water, sanitation, electricity, connectivity fields where published |
| Learner / assessment data | Dataset-specific periods | Only aggregate/institution-level public data appropriate for this product |

The Machine-Ready Files page advertises these families, but the actual files were not acquired. Do not treat advertised coverage as verified schema or content.

### EBEIS NCR result set (acquired, internal only)

- `https://ebeis.deped.gov.ph/beis/reports_info/masterlist` returned HTTP 200 on 15 November 2026.
- The NCR result set contained **5,055 rows across 169 result pages**.
- Observed columns: `School ID`, `School Name`, `Head / Position`, `Address`, `School Type`.
- The parser created 5,055 internal school records with zero coordinates and zero PSGC assignments. It did not guess geography or coordinates.
- The dataset is `approved_with_attribution` in the source registry. The re-ingested 15 November 2026 release is `published` for institution-level fields; the earlier `restricted_non_redistributable` release is retained. School-head names and other personal fields are withheld.
- Canonical DepEd facilities remain `internal`/`DISCOVERY_CANDIDATE` (5,055 records) until field-level mapping and privacy review. The absence of an explicit reuse licence is not the reason for keeping them internal.
- Evidence: `docs/reports/02-acquisition-report.md`, `docs/reports/03-schema-report.md`, and `var/reports/deped-ebeis-masterlist-ncr-*`.

### Acquisition tasks

- [ ] Open the official Machine-Ready Files page and record current filenames/links through an authorized human route.
- [ ] Complete any required download/terms steps; do not accept terms on another person's behalf.
- [ ] Save original files privately with checksum and source URL.
- [ ] Inspect every workbook sheet, header row, types, null markers, encoding, and reference period.
- [ ] Record the official school ID format and test uniqueness.
- [ ] Verify whether original files contain coordinates; do not infer them from administrative geography.
- [ ] Review DepEd terms and record the publication basis; ask for written clarification if normalized-row redistribution is unclear.
- [ ] Complete field-level mapping and privacy review so canonical EBEIS rows can move from `internal` to an approved public state; keep school-head names excluded.

## 3. DOH — NHFR and licensed health facilities

### Official sources

- NHFR: https://nhfr.doh.gov.ph/VActivefacilitiesList
- HFSRB licensed facilities: https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/

### Access evidence and caveats

- Both URLs returned HTTP 403 Cloudflare challenge pages on 15 November 2026.
- Official DOH FOI responses in 2025 and 2026 describe health-facility CSV/Excel and ESRI shapefile extracts. One response required a signed Agreement for the Release and Use of Health Data. No agreement was reviewed or accepted.
- DOH has disclosed that registry population is ongoing, some coordinates are GPS-derived, some come from online maps, some are barangay centroids, some facilities lack coordinates, and information can change without notice.

### Documented field families

These are fields specified by collection forms or prior disclosures; the exact export headers were not verified:

- Facility name, type, subtype, ownership.
- Service capability / hospital level and bed capacity where applicable.
- License / registration number, type, status, validity.
- Street/building address; region, province, municipality, barangay, ZIP.
- Telephone, fax, mobile, email.
- Latitude and longitude; coordinate collection method/provenance.

### Acquisition tasks

- [x] Attempt the normal public download and record exact behavior/status.
- [ ] Obtain the latest export through a permitted official route.
- [ ] Review the applicable signed data-use agreement before any republication.
- [ ] Inspect actual CSV/Excel headers and shapefile schema.
- [ ] Identify facility IDs, license IDs, dates, ownership codes, and coordinate precision.
- [ ] Determine whether API display, bulk redistribution, derived fields, caching, and historical retention are permitted.
- [ ] If redistribution is restricted, use DOH data only for matching/validation or defer publication pending written permission.

## 4. PhilHealth — accredited provider lists

Official index: https://www.philhealth.gov.ph/partners/providers/facilities/accredited/

On 15 November 2026 the index returned HTTP 200 and listed 27 provider-category PDF links. The
index states "Updated as of September 30, 2026." The hospital/infirmary PDF was retrieved (HTTP 200,
4,294,314 bytes, 75 pages, SHA-256
`9ef34056f893a5aa485619e71d8481f02da149ce61a1ca1d75686a2f4c81c0b4`) and parses to 1,932 stored
accreditations under parser `philhealth-pdf-1.1.0`; the current parser is `philhealth-pdf-1.2.0`,
which fixes the two-up Antenatal annex handling. The local pre-ingestion sample produced 1,934
extracted rows; stored rows differ because duplicate/overlapping source rows and facility linking
are handled explicitly. Page/row references are retained.

| Provider category | Filename | Date basis |
|---|---|---|
| Yakap Clinics | `YAKAP.pdf` | index date 2026-09-30; no date in filename |
| Cancer Screening Test Providers | `CancerScreening.pdf` | index date 2026-09-30; no date in filename |
| GAMOT Package Providers | `GAMOT.pdf` | index date 2026-09-30; no date in filename |
| Hospitals and Infirmaries/Dispensaries | `HOSP_093026.pdf` | 2026-09-30 |
| Freestanding Dialysis Clinics | `FDC_093026.pdf` | 2026-09-30 |
| Birthing Homes Providers | `MCP_073126.pdf` | 2026-07-31; HTTP 404 |
| Maternity Care Providers | `MCC_093026.pdf` | 2026-09-30 |
| Animal Bite Package Providers | `ABPP_093026.pdf` | 2026-09-30 |
| Outpatient Malaria Package Providers | `OMP_093026.pdf` | 2026-09-30 |
| Family Planning Providers | `FP_093026.pdf` | 2026-09-30 |
| TB-DOTS Centers | `DOTS_093026.pdf` | 2026-09-30 |
| Drug Abuse Treatment and Rehab Centers | `DATRC_093026.pdf` | 2026-09-30 |
| DOH-Designated HIV Treatment Hubs | `OHAT_093026.pdf` | 2026-09-30 |
| Cancer Treatment Facilities | `CTF_093026.pdf` | 2026-09-30 |
| COVID-19 Testing Laboratories | `COVIDLAB_093026.pdf` | 2026-09-30 |
| Community Isolation Units | `CIU_093026.pdf` | 2026-09-30 |
| COVID-19 Home Isolation Benefit Package Providers | `CHIBP_093026.pdf` | 2026-09-30 |
| Oral Health Benefit Package Providers | `DENTAL_093026.pdf` | 2026-09-30 |
| Optometry Benefit Package Providers | `OPTO_093026.pdf` | 2026-09-30 |
| Severe Acute Malnutrition Package Providers | `SAM_093026.pdf` | 2026-09-30 |
| Ambulatory Surgical Clinics | `ASC_093026.pdf` | 2026-09-30 |
| Ambulance Service Provider | `AMBU_093026.pdf` | 2026-09-30 |
| Pelvic Ultrasound | `EMCB-PUTZ_093026.pdf` | 2026-09-30 |
| Postpartum | `EMCB-PPARTUM_093026.pdf` | 2026-09-30 |
| Antenatal | `EMCB-ANTE_093026.pdf` | 2026-09-30; corrected parser reads 3,221 provider rows; earlier 6,562-row parse withdrawn; blocked |
| Transvaginal Ultrasound | `EMCB-TVU_093026.pdf` | 2026-09-30 |
| Clinical Laboratory | `EMCB-LAB_093026.pdf` | 2026-09-30 |

All links resolve under `https://www.philhealth.gov.ph/partners/providers/facilities/accredited/`.
Do not assume the index date applies to every file; `MCP_073126.pdf` is encoded as 31 July 2026,
and three files carry no date in the filename.

### Hospital PDF fields observed

- Facility name (`NAME OF HEALTH FACILITY`).
- Bed count (`BEDS`).
- Hospital/accreditation category (`CAT`).
- Telephone (`TEL_NO`).
- Email.
- Street.
- Municipality.
- Accreditation expiry date (`EXPIRE DATE`).
- Sector code (`SEC`; meaning still to be validated against official documentation).

The real table has region and province separator rows with no expiry or facility name; the adapter
skips them rather than creating records. Multi-line street/email cells are preserved as source text.
The synthetic official-layout fixture exercises these headers without redistributing agency data.

### Acquisition tasks

- [x] Inventory all provider-category documents and exact URLs.
- [x] Record the source-as-of or update date per file.
- [x] Parse PDF tables and preserve a page/row reference for every extracted record.
- [x] Model accreditation as multiple, dated, benefit-specific records.
- [x] Publish rights-cleared releases with attribution.
- [ ] Validate sector-code meanings against official PhilHealth documentation.
- [x] Record the 404 Birthing Homes link without inventing a replacement.
- [x] Withdraw the Antenatal release after its first parse counted the PDF's expiry/sector annex as provider rows; keep the raw file and block publication pending validated re-ingestion.

## 5. PSA — PSGC

Official page: https://psa.gov.ph/classification/psgc

Q3 2026 workbook identified:
https://psa.gov.ph/system/files/scd/PSGC-3Q-2026-Publication-Datafile.xlsx

Reference period stated in prior research: 30 September 2026. Do not treat these figures as
verified until the workbook is acquired.

### Observed access

- Public PSGC page: HTTP 403 Cloudflare.
- Q3 2026 workbook: HTTP 403 Cloudflare.
- Classification index `https://classification.psa.gov.ph/psgc`: HTTP 404 as probed; the
  collection route `https://classification.psa.gov.ph/psgc/regions` returned HTTP 200 JSON.
- `https://classification.psa.gov.ph/psgc/regions/all` returned HTTP 400
  `{"error":"Token is required."}`. No token was obtained, and no access control was bypassed.
- Evidence: `docs/operations/evidence/2026-11-15-source-access/psgc.txt` and
  `source-probes-2026-11-15.txt`.

### BetterGov supplementary mirror

- `https://statistics.bettergov.ph/api/classification/psgc` returned HTTP 200.
- The Q2 2024 snapshot was acquired as `PSGC-Q2-2024-BETTERGOV` and loaded as a versioned
  geographic release: 43,760 units.
- The mirror is CC BY-SA 4.0 and is **not** the latest official PSA release. It is used as
  supplementary geography because the official workbook is blocked; public labels say so.

### Acquisition tasks

- [ ] Download the official XLSX release through an authorized route and store its checksum.
- [ ] Inspect workbook sheets, columns, code type/leading zeros, and hierarchy.
- [ ] Compare with previous PSGC releases and build a versioned crosswalk.
- [ ] Obtain/authorize API token access if needed for the classification API.
- [ ] Replace the BetterGov mirror with the official release when terms and access permit.

## 6. CHED — HEIDA

- Directory: https://heida.ched.gov.ph/hei-directory
- Portal: https://heida.ched.gov.ph/

The public directory returned HTTP 200 on 15 November 2026. A complete national machine-readable
dataset and documented public REST API were not verified. The portal describes API/developer
capabilities as upcoming HEIDA v2 features. Do not scrape behind a login or invent an API.

Acquisition tasks:

- [ ] Inspect public HTML/network responses for permitted structured data.
- [ ] Contact CHED or use a formal request for a public institution export.
- [ ] Record official institution identifiers and address fields.
- [ ] Do not automate behind login or bypass access restrictions.

## 7. TESDA — training providers

- Training institutions: https://www.tesda.gov.ph/TVI
- Assessment centers: https://www.tesda.gov.ph/AssessmentCenters
- Statistics: https://www.tesda.gov.ph/About/TESDA/53

The TVI page returned HTTP 200 in a manual probe, but the source monitor classified the response as
an access challenge on 15 November 2026. No public JSON API or verified bulk national provider
export was found. Aggregate TVET statistics are not a substitute for individual provider records.

Acquisition tasks:

- [ ] Inspect publicly accessible page/network responses and terms.
- [ ] Determine whether a complete export exists.
- [ ] Identify provider ID, registered programs, validity/status, address, and location fields.
- [ ] Request public bulk data where no machine-readable access exists.

## 8. Hazard and environmental discovery

These sources are not facility identity registries and are not part of the current public release.
Do not implement hazard exposure without an acquired layer, a documented CRS/version, and a
documented rights decision under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.

| Source | Probe result | What was verified | Next action |
|---|---|---|---|
| GeoRiskPH | TLS certificate verification failed (`unable to get local issuer certificate`) | Homepage did not load; no layer accessed | Use a trusted network/browser and record the certificate chain; do not disable verification |
| HazardHunterPH | HTTP 200 HTML | Public hazard tool page reachable | Investigate a documented data/download route and terms |
| PHIVOLCS main | HTTP 200 HTML | Public site reachable | Identify actual GIS products and terms |
| PHIVOLCS maps | TLS `unexpected eof while reading` | Portal did not load | Retry from a trusted network; do not bypass TLS |
| PAGASA main | HTTP 200 HTML | Public site reachable | Identify climate data request/download process |
| Climgrid/climapv2 | HTTP 200 HTML | Public platform reachable | Investigate available datasets and reuse terms |
| DENR-MGB | HTTP 403 | Homepage blocked by WAF/challenge | Use authorized public/FOI route; no bypass |

## 9. Open Data Philippines and additional agency discovery

`https://data.gov.ph/` returned HTTP 200 as an Angular single-page application. The queried public
dataset search endpoint `https://api.data.gov.ph/api/public/dataset/search` returned HTTP 404
unauthenticated on 15 November 2026. No catalogue dataset was registered, acquired, or published.
A publicly listed dataset must still be traced to its original agency and a recorded publication
decision.

Homepage reachability was probed for the following discovery targets. Reachability of a homepage is
**not** evidence that a facility dataset, schema, or publication decision exists. None was registered
or ingested:

| Agency | Probe | Discovery status |
|---|---|---|
| DILG | TLS `unexpected eof` | No dataset verified |
| Bureau of Fire Protection | HTTP 403 | No dataset verified |
| Philippine National Police | HTTP 403 | No dataset verified |
| BJMP | HTTP 403 | No dataset verified |
| Bureau of Corrections | HTTP 200 | No facility export verified |
| DSWD | HTTP 200 | No residential-care facility export verified |
| DPWH | HTTP 403 | No infrastructure dataset verified |
| DENR | HTTP 403 | No protected-area/facility dataset verified |
| NAMRIA | HTTP 200 | No licensed geographic product acquired |
| NHA | HTTP 403 | No housing-project dataset verified |
| National Library of the Philippines | HTTP 200 | No public-library directory export verified |
| NCCA | DNS resolution failed | No dataset verified |
| LWUA | HTTP 403 | No water-district dataset verified |
| MWSS | HTTP 403 | No service-area dataset verified |
| DOTr / LTFRB | HTTP 403 | No terminal/route dataset verified |
| DICT | HTTP 403 | No public digital-service facility dataset verified |

For every future source, establish the original agency, exact dataset, access procedure, actual
schema, geographic coverage, identifiers, history, update pattern, and reuse rights before adding a
connector.

### Recurring discovery probes

`uv run philfacilities-ingest discover-sources` runs the 25 discovery-only targets registered in
`apps/ingest/philfacilities_ingest/discovery.py`. It records the HTTP status, redirect, TLS or access
blocker, and observation time for each target. It never registers a dataset, accepts terms, downloads
a bulk file, or bypasses an access control. The `discover-sources` job in
`.github/workflows/source-checks.yml` runs monthly (`17 5 1 * *`) and uploads the JSON report as
workflow evidence. A probe result is discovery evidence only; it does not change a source's rights
or publication status. A hosted scheduled run has not yet been observed.

## 10. Source record acceptance checklist

A source is not marked `READY_FOR_PUBLICATION` until all are true:

- [ ] Official origin established.
- [ ] Exact URL/access method recorded.
- [ ] Actual file or response retrieved and checksum stored.
- [ ] Schema inspected and documented.
- [ ] Source reference period/publication/retrieval dates distinguished.
- [ ] Stable source identifiers understood.
- [ ] Data-use/licence/FOI agreement reviewed.
- [ ] Personal/sensitive fields excluded or lawful basis reviewed.
- [ ] Transformation and matching rules documented.
- [ ] Quality checks pass and known limitations published.

## 11. Source status vocabulary

- `DISCOVERED`: official source page located.
- `REACHABLE`: actual page/endpoint/file was accessed successfully.
- `ACQUIRED`: raw file/response stored with checksum.
- `SCHEMA_VERIFIED`: actual columns/types inspected.
- `TERMS_REVIEWED`: reuse conditions documented.
- `INGESTION_TESTED`: adapter processed a representative release.
- `PUBLICATION_APPROVED`: public redistribution is permitted and approved.
- `READY_FOR_PUBLICATION`: all release gates pass.

Do not collapse these statuses into a single "available" flag. A blocked source remains blocked even
when its homepage or a single API route returns HTTP 200.
