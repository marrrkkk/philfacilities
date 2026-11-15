# 01 — Complete Government Data Source Directory

**Generated:** 2026-11-15T08:21:10.247010+00:00  
**Source of truth:** the configured PhilFacilities PostgreSQL database.  

Every registered dataset and every discovery-only source that was probed.

This directory lists every dataset registered in the platform and the discovery-only sources that were probed but not registered. A listed row is not evidence that a dataset is accessible, current, complete, or legally publishable.

## Registered sources

| Agency | Dataset | Official URL | Access | Update | Rights | Publication | Personal data | Releases | Source records | Population observations | Facilities linked | Last check |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bettergov | psa-census-2024-population | https://statistics.bettergov.ph/api | public_json_api | saved PSA OpenSTAT snapshot; checked periodically | approved_with_attribution | approved | NULL | 18 | 134748 | 134748 | 0 | ok (200) at 2026-11-15 06:07:20.927644+00:00 |
| bettergov | psgc-bettergov-q2-2024 | https://statistics.bettergov.ph/api/classification/psgc | public_api | quarterly snapshot | approved_with_attribution | published | NULL | 0 | 0 | 0 | 0 | ok (200) at 2026-11-15 06:07:18.746135+00:00 |
| ched | ched-hei-directory | https://heida.ched.gov.ph/hei-directory | public_html_directory | unknown | review_required | blocked | NULL | 0 | 0 | 0 | 0 | ok (200) at 2026-11-15 06:07:29.742643+00:00 |
| deped | deped-ebeis-masterlist-ncr | https://ebeis.deped.gov.ph/beis/reports_info/masterlist | public_html_form | school year | restricted_non_redistributable | internal_only | contains_school_head_names | 1 | 5055 | 0 | 5055 | ok (200) at 2026-11-15 06:07:25.478678+00:00 |
| deped | deped-machine-ready-files | https://www.deped.gov.ph/machine-ready-files/ | human_download | school year | review_required | blocked | NULL | 0 | 0 | 0 | 0 | access_blocked (403) at 2026-11-15 06:07:27.038103+00:00 |
| doh | doh-nhfr | https://nhfr.doh.gov.ph/VActivefacilitiesList | official_registry | weekly | review_required | blocked | NULL | 0 | 0 | 0 | 0 | access_blocked (403) at 2026-11-15 06:07:27.965646+00:00 |
| osm | osm-education-facilities | https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/education_facilities.parquet | public_geoparquet | irregular snapshot | approved_with_attribution | published | NULL | 1 | 52839 | 0 | 52824 | not_modified (304) at 2026-11-15 06:07:23.829746+00:00 |
| osm | osm-health-facilities | https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/health_facilities.parquet | public_geoparquet | irregular snapshot | approved_with_attribution | published | NULL | 1 | 17421 | 0 | 17410 | not_modified (304) at 2026-11-15 06:07:23.570577+00:00 |
| philhealth | philhealth-abpp | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/ABPP_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 1670 | 0 | 1666 | ok (200) at 2026-11-15 03:17:32.999150+00:00 |
| philhealth | philhealth-accredited-providers | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/ | public_html_index | monthly | approved_with_attribution | approved | business_contact_information | 0 | 0 | 0 | 0 | ok (200) at 2026-11-15 06:07:22.630226+00:00 |
| philhealth | philhealth-ambu | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/AMBU_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 104 | 0 | 104 | ok (200) at 2026-11-15 03:19:35.043845+00:00 |
| philhealth | philhealth-asc | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/ASC_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 281 | 0 | 281 | ok (200) at 2026-11-15 03:19:49.159199+00:00 |
| philhealth | philhealth-cancerscreening | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/CancerScreening.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 415 | 0 | 415 | ok (200) at 2026-11-15 02:30:05.404929+00:00 |
| philhealth | philhealth-chibp | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/CHIBP_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 11 | 0 | 11 | ok (200) at 2026-11-15 03:20:14.934293+00:00 |
| philhealth | philhealth-ciu | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/CIU_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 2 | 0 | 2 | ok (200) at 2026-11-15 03:20:25.530338+00:00 |
| philhealth | philhealth-covidlab | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/COVIDLAB_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 105 | 0 | 105 | ok (200) at 2026-11-15 03:20:36.158501+00:00 |
| philhealth | philhealth-ctf | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/CTF_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 16 | 0 | 16 | ok (200) at 2026-11-15 03:20:58.801967+00:00 |
| philhealth | philhealth-datrc | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/DATRC_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 24 | 0 | 24 | ok (200) at 2026-11-15 03:21:09.743649+00:00 |
| philhealth | philhealth-dental | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/DENTAL_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 687 | 0 | 676 | ok (200) at 2026-11-15 03:21:31.097398+00:00 |
| philhealth | philhealth-dots | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/DOTS_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 2097 | 0 | 2066 | ok (200) at 2026-11-15 03:23:16.105429+00:00 |
| philhealth | philhealth-emcb-ante | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/EMCB-ANTE_093026.pdf | public_html_index | monthly | approved_with_attribution | blocked | business_contact_information | 1 | 0 | 0 | 0 | ok (200) at 2026-11-15 04:42:54.544611+00:00 |
| philhealth | philhealth-emcb-lab | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/EMCB-LAB_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 222 | 0 | 222 | ok (200) at 2026-11-15 04:33:44.393097+00:00 |
| philhealth | philhealth-emcb-ppartum | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/EMCB-PPARTUM_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 3222 | 0 | 3179 | ok (200) at 2026-11-15 04:35:13.378702+00:00 |
| philhealth | philhealth-emcb-putz | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/EMCB-PUTZ_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 92 | 0 | 92 | ok (200) at 2026-11-15 03:31:05.236812+00:00 |
| philhealth | philhealth-emcb-tvu | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/EMCB-TVU_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 90 | 0 | 90 | ok (200) at 2026-11-15 04:39:17.129216+00:00 |
| philhealth | philhealth-fdc | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/FDC_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 1012 | 0 | 974 | ok (200) at 2026-11-15 08:13:58.941872+00:00 |
| philhealth | philhealth-fp | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/FP_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 1465 | 0 | 1446 | ok (200) at 2026-11-15 03:31:36.806368+00:00 |
| philhealth | philhealth-gamot | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/GAMOT.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 3483 | 0 | 3068 | ok (200) at 2026-11-15 08:10:37.974998+00:00 |
| philhealth | philhealth-hosp | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/HOSP_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 1934 | 0 | 1928 | ok (200) at 2026-11-15 08:12:42.485038+00:00 |
| philhealth | philhealth-mcc | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/MCC_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 3140 | 0 | 3127 | ok (200) at 2026-11-15 03:09:50.119502+00:00 |
| philhealth | philhealth-mcp | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/MCP_073126.pdf | public_html_index | monthly | approved_with_attribution | approved | business_contact_information | 0 | 0 | 0 | 0 | not_found (404) at 2026-11-15 03:14:57.657062+00:00 |
| philhealth | philhealth-ohat | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/OHAT_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 342 | 0 | 339 | ok (200) at 2026-11-15 03:34:58.148689+00:00 |
| philhealth | philhealth-omp | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/OMP_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 100 | 0 | 100 | ok (200) at 2026-11-15 03:35:56.732200+00:00 |
| philhealth | philhealth-opto | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/OPTO_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 125 | 0 | 125 | ok (200) at 2026-11-15 03:36:25.705155+00:00 |
| philhealth | philhealth-sam | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/SAM_093026.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 209 | 0 | 207 | ok (200) at 2026-11-15 03:36:55.507262+00:00 |
| philhealth | philhealth-yakap | https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf | public_html_index | monthly | approved_with_attribution | published | business_contact_information | 1 | 4138 | 0 | 4110 | ok (200) at 2026-11-15 08:08:07.410648+00:00 |
| psa | psgc-official | https://psa.gov.ph/classification/psgc | official_workbook | quarterly | review_required | blocked | NULL | 0 | 0 | 0 | 0 | access_blocked (403) at 2026-11-15 06:07:16.632229+00:00 |
| tesda | tesda-tvi-directory | https://www.tesda.gov.ph/TVI | public_html_directory | unknown | review_required | blocked | NULL | 0 | 0 | 0 | 0 | access_blocked (200) at 2026-11-15 06:07:32.285246+00:00 |

## Versioned geographic releases

PSGC releases are stored separately from facility datasets so codes keep their leading zeros and previous releases remain addressable.

| Geographic release | Reference date | Retrieved | Units | Synthetic | SHA-256 | Raw object |
|---|---|---|---|---|---|---|
| PSGC-Q2-2024-BETTERGOV | 2024-06-30 | 2026-11-15T02:24:43.740698+00:00 | 43760 | false | 3f1fe61dab0fafd4bc64930facb471ed707bda2f936bd7708e23ca4990ead697 | var/raw/bettergov/psgc-bettergov-q2-2024/PSGC-Q2-2024-BETTERGOV/3f1fe61dab0fafd4-psgc-q2-2024-bettergov.json |

## Non-public sources

The following registered datasets are deliberately blocked or internal-only. They must not be exposed by the public API until the recorded gate changes.

| Dataset | Status | Reason / latest check |
|---|---|---|
| ched-hei-directory | blocked | The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked. |
| deped-ebeis-masterlist-ncr | internal_only | Public EBEIS result set for National Capital Region: 5055 rows across 169 pages. Aggregated acquisition artifact; internal-only pending terms/privacy review. |
| deped-machine-ready-files | blocked | The source returned an access/verification page or an authentication denial. No bypass was attempted; a human-assisted or authorized route is required. |
| doh-nhfr | blocked | The source returned an access/verification page or an authentication denial. No bypass was attempted; a human-assisted or authorized route is required. |
| philhealth-emcb-ante | blocked | PhilHealth public provider-category PDF. date encoded in source file name (093026). Publication relies on PhilHealth's published reuse statement; attribution retained. Post-ingestion review (2026-11-15): the first successful parse recorded 6,562 rows, but this is a two-up landscape PDF; pages 1-120 carry provider rows and pages 121-240 carry only the expiry/sector annex. The withdrawn run counted annex rows as provider rows. All derived source records, accreditations, and facility links were removed. Corrected parser philhealth-pdf-1.2.0 re-reads 3,221 provider rows from the retained raw file. This release remains blocked pending a validated re-ingestion. |
| psgc-official | blocked | The source returned an access/verification page or an authentication denial. No bypass was attempted; a human-assisted or authorized route is required. |
| tesda-tvi-directory | blocked | The source returned an access/verification page or an authentication denial. No bypass was attempted; a human-assisted or authorized route is required. |

## Discovery-only sources (not registered as datasets)

These sources were probed during source discovery, but no dataset row, release, file, or field schema was registered. They are listed so the directory is complete; none is available to the public API.

| Source | Official URL | Access result | Rights / publication |
|---|---|---|---|
| DOH HFSRB licensed health facilities | https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/ | HTTP 403 Cloudflare challenge; no file or agreement acquired | blocked; licensing semantics and reuse terms not established |
| PSA classification API | https://classification.psa.gov.ph/psgc | `/regions` HTTP 200; data collections require a token that was not obtained | blocked; no token requested or bypassed |
| TESDA Assessment Centers | https://www.tesda.gov.ph/AssessmentCenters | not independently acquired | blocked; terms and programmatic access not verified |
| HazardHunterPH | https://hazardhunter.georisk.gov.ph/ | HTTP 200 HTML; no hazard layer requested | blocked; no reuse permission acquired |
| GeoRiskPH | https://georisk.gov.ph/ | TLS certificate verification failure from the probe host | blocked; no layer acquired and TLS was not bypassed |
| PHIVOLCS | https://www.phivolcs.dost.gov.ph/ | main site HTTP 200; maps portal TLS failure | blocked; no layer or reuse permission acquired |
| PAGASA / Climgrid | https://www.pagasa.dost.gov.ph/ | HTTP 200 HTML; no climate layer requested | blocked; no layer or reuse permission acquired |
| DENR-MGB | https://mgb.gov.ph/ | HTTP 403 WAF/challenge | blocked; no geohazard layer acquired |
| Open Data Philippines | https://data.gov.ph/ | HTTP 200 single-page app; public API search returned 404 | blocked; no dataset from this catalogue was registered or published |

## Reading this directory

- `approved_with_attribution` records collected terms evidence, not a completed legal review.
- `review_required` and `blocked` sources remain unavailable to the public API.
- `internal_only` releases may be retained for validation but are excluded from public endpoints and downloads.
- Reachability checks record what an endpoint returned at a point in time; they do not grant permission to republish.
- Original field names, types, and missing-value statistics are in report 03. Per-source coverage, acquisition procedure, and evidence notes are in `docs/03-SOURCE-REGISTER.md`.
- The `Update` column is the recorded expected cadence, not evidence that a hosted scheduled run exists.

