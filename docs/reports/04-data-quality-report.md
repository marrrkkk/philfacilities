# 04 — Data Quality Report

**Generated:** 2026-11-15T13:36:25.172780+00:00  
**Source of truth:** the configured PhilFacilities PostgreSQL database.  

Accepted, rejected, missing, duplicate, geographic, coordinate, and identity measures.

This snapshot reports measured counts from the current database. A zero value means the source reported or the pipeline recorded zero; a missing value means the measure was not recorded and is not an implied zero.

## Facility counts

| Total | Synthetic | Public | Non-public |
|---|---|---|---|
| 92996 | 0 | 62380 | 30616 |

### By facility type

| Facility type | Facilities |
|---|---|
| school | 57868 |
| health_facility | 30956 |
| library | 1752 |
| government_office | 1396 |
| transport_facility | 574 |
| agricultural_facility | 357 |
| social_welfare_facility | 76 |
| museum | 17 |

## Location and geography quality

| Facilities | With coordinates | Without any current location | With a current location but no PSGC |
|---|---|---|---|
| 92996 | 70311 | 22685 | 14304 |

### Current coordinate precision

| Precision | Facilities |
|---|---|
| map_geocoded | 70223 |
| geocoded | 88 |

## Identity and cross-source matching

A linked record is matched to a canonical facility by an exact agency identifier (OSM feature id, DepEd School ID, or PhilHealth name+municipality key). Name-only fuzzy merges are not automatic. A facility linked from more than one dataset has not necessarily been matched across agencies; the multi-agency count measures that separately.

| Measure | Count |
|---|---|
| Facility-domain source records | 110800 |
| Records linked to a canonical facility | 110774 |
| Records without a canonical link | 26 |
| Facilities with at least one source link | 92996 |
| Facilities linked from more than one dataset | 5594 |
| Facilities linked from more than one agency | 0 |
| Links created as new canonical records | 84914 |
| Links matched by exact agency identifier | 25860 |
| Pending / ambiguous match candidates | 0 |

### Match-review queue

_No match candidates recorded._

## Population statistics

Population and household counts are stored separately from facility records. They are never merged into a facility attribute and a null source value is not converted to zero.

| Observations | PSGC codes | Releases | Null values | Zero values | Public observations | Duplicate source keys |
|---|---|---|---|---|---|---|
| 134748 | 43768 | 18 | 0 | 43 | 134748 | 0 |

### Observations by geographic level

| Geographic level | Observations | PSGC codes |
|---|---|---|
| barangay | 129333 | 42011 |
| municipality | 4962 | 1608 |
| province_or_huc | 357 | 117 |
| region | 54 | 18 |
| unknown | 42 | 14 |

### Observations by indicator

| Indicator | Unit | Observations | Null values |
|---|---|---|---|
| Household Population | persons | 44916 | 0 |
| Number of Households | households | 44916 | 0 |
| Total Population | persons | 44916 | 0 |

The source's 2024 Census tables include 42 Manila city-district rows whose labels do not carry one of PSA's dotted hierarchy prefixes; they are stored with `geographic_level = unknown` rather than guessed to be a province, city, or barangay.

## Recorded quality issues

| Issue code | Severity | Status | Count |
|---|---|---|---|
| location_missing | info | open | 40452 |
| duplicate_osm_id | error | open | 3572 |
| missing_facility_name | error | open | 25 |
| coordinate_outside_philippines_bbox | error | open | 1 |

## Source-to-database reconciliation

Reported rows are the source's own count where recorded; parsed and stored counts are measured in this database. Unlinked records have no canonical facility link (for example, a rejected or unresolved row). These are not silently treated as valid facilities.

| Dataset | Release | Reported rows | Parsed rows | Stored records | Linked records | Unlinked records | Unmatched PSGC | Missing location | Invalid coordinates | Duplicate source rows |
|---|---|---|---|---|---|---|---|---|---|---|
| bir-revenue-district-offices | BIR-RAO-006-2025 | 124 | 124 | 124 | 124 | 0 | 0 | 124 | 0 | 0 |
| deped-ebeis-masterlist-ncr | DEPED-EBEIS-NCR-2026-11-15 | 5055 | 5055 | 5055 | 5055 | 0 | 0 | 5055 | 0 | 0 |
| deped-ebeis-masterlist-ncr | DEPED-EBEIS-NCR-2026-11-15 | 5055 | 5055 | 5055 | 5055 | 0 | 0 | 5055 | 0 | 0 |
| dswd-crcf-directory | DSWD-CRCF-2026-11-15 | 76 | 76 | 76 | 76 | 0 | 0 | 76 | 0 | 0 |
| nlp-public-libraries | NLP-PUBLIC-LIBRARIES-2025-12 | 1752 | 1752 | 1752 | 1752 | 0 | 0 | 1752 | 0 | 0 |
| nmis-naris-accredited-meat-establishments | NMIS-NARIS-2026-11-15 | 357 | 357 | 357 | 357 | 0 | 0 | 269 | 0 | 0 |
| nmp-regional-area-site-museums | NMP-MUSEUMS-2026-11-15 | 17 | 17 | 17 | 17 | 0 | 0 | 17 | 0 | 0 |
| osm-education-facilities | HOT-OSM-PHL-EDUCATION-2026-11-15 | 55824 | 55824 | 52839 | 52824 | 15 | 0 | 0 | 1 | 0 |
| osm-health-facilities | HOT-OSM-PHL-HEALTH-2026-11-15 | 18008 | 18008 | 17421 | 17410 | 11 | 0 | 0 | 0 | 0 |
| philhealth-abpp | PHILHEALTH-ABPP_093026-2026-09-30 | 1670 | 1670 | 1670 | 1670 | 0 | 0 | 1670 | 0 | 0 |
| philhealth-ambu | PHILHEALTH-AMBU_093026-2026-09-30 | 104 | 104 | 104 | 104 | 0 | 0 | 104 | 0 | 0 |
| philhealth-asc | PHILHEALTH-ASC_093026-2026-09-30 | 281 | 281 | 281 | 281 | 0 | 0 | 281 | 0 | 0 |
| philhealth-cancerscreening | PHILHEALTH-CANCERSCREENING-UNDATED | 415 | 415 | 415 | 415 | 0 | 0 | 415 | 0 | 0 |
| philhealth-chibp | PHILHEALTH-CHIBP_093026-2026-09-30 | 11 | 11 | 11 | 11 | 0 | 0 | 11 | 0 | 0 |
| philhealth-ciu | PHILHEALTH-CIU_093026-2026-09-30 | 2 | 2 | 2 | 2 | 0 | 0 | 2 | 0 | 0 |
| philhealth-covidlab | PHILHEALTH-COVIDLAB_093026-2026-09-30 | 105 | 105 | 105 | 105 | 0 | 0 | 105 | 0 | 0 |
| philhealth-ctf | PHILHEALTH-CTF_093026-2026-09-30 | 16 | 16 | 16 | 16 | 0 | 0 | 16 | 0 | 0 |
| philhealth-datrc | PHILHEALTH-DATRC_093026-2026-09-30 | 24 | 24 | 24 | 24 | 0 | 0 | 24 | 0 | 0 |
| philhealth-dental | PHILHEALTH-DENTAL_093026-2026-09-30 | 687 | 687 | 687 | 687 | 0 | 0 | 687 | 0 | 0 |
| philhealth-dots | PHILHEALTH-DOTS_093026-2026-09-30 | 2097 | 2097 | 2097 | 2097 | 0 | 0 | 2097 | 0 | 0 |
| philhealth-emcb-ante | PHILHEALTH-EMCB-ANTE_093026-2026-09-30 | 6562 | 6562 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| philhealth-emcb-lab | PHILHEALTH-EMCB-LAB_093026-2026-09-30 | 222 | 222 | 222 | 222 | 0 | 0 | 222 | 0 | 0 |
| philhealth-emcb-ppartum | PHILHEALTH-EMCB-PPARTUM_093026-2026-09-30 | 3222 | 3222 | 3222 | 3222 | 0 | 0 | 3222 | 0 | 0 |
| philhealth-emcb-putz | PHILHEALTH-EMCB-PUTZ_093026-2026-09-30 | 92 | 92 | 92 | 92 | 0 | 0 | 92 | 0 | 0 |
| philhealth-emcb-tvu | PHILHEALTH-EMCB-TVU_093026-2026-09-30 | 90 | 90 | 90 | 90 | 0 | 0 | 90 | 0 | 0 |
| philhealth-fdc | PHILHEALTH-FDC_093026-2026-09-30 | 1012 | 1012 | 1012 | 1012 | 0 | 0 | 1012 | 0 | 0 |
| philhealth-fp | PHILHEALTH-FP_093026-2026-09-30 | 1465 | 1465 | 1465 | 1465 | 0 | 0 | 1465 | 0 | 0 |
| philhealth-gamot | PHILHEALTH-GAMOT-UNDATED | 3483 | 3483 | 3483 | 3483 | 0 | 0 | 3483 | 0 | 0 |
| philhealth-hosp | PHILHEALTH-HOSP_093026-2026-09-30 | 1934 | 1934 | 1934 | 1934 | 0 | 0 | 1934 | 0 | 0 |
| philhealth-mcc | PHILHEALTH-MCC_093026-2026-09-30 | 3140 | 3140 | 3140 | 3140 | 0 | 0 | 3140 | 0 | 0 |
| philhealth-ohat | PHILHEALTH-OHAT_093026-2026-09-30 | 342 | 342 | 342 | 342 | 0 | 0 | 342 | 0 | 0 |
| philhealth-omp | PHILHEALTH-OMP_093026-2026-09-30 | 100 | 100 | 100 | 100 | 0 | 0 | 100 | 0 | 0 |
| philhealth-opto | PHILHEALTH-OPTO_093026-2026-09-30 | 125 | 125 | 125 | 125 | 0 | 0 | 125 | 0 | 0 |
| philhealth-sam | PHILHEALTH-SAM_093026-2026-09-30 | 209 | 209 | 209 | 209 | 0 | 0 | 209 | 0 | 0 |
| philhealth-yakap | PHILHEALTH-YAKAP-UNDATED | 4138 | 4138 | 4138 | 4138 | 0 | 0 | 4138 | 0 | 0 |
| phlpost-post-office-locator | PHLPOST-LOCATOR-2026-11-15 | 1272 | 1272 | 1272 | 1272 | 0 | 0 | 1272 | 0 | 0 |
| phlpost-post-office-locator | PHLPOST-LOCATOR-2026-11-15 | 1272 | 1272 | 1272 | 1272 | 0 | 0 | 1272 | 0 | 0 |
| ppa-port-list | PPA-PORT-LIST-2026-11-15 | 574 | 574 | 574 | 574 | 0 | 0 | 574 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Negros-Island-Region-NIR-2024-07-01 | 4260 | 4260 | 4260 | 0 | 4260 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-National-Captial-Region-NCR-2024-07-01 | 5241 | 5241 | 5241 | 0 | 5241 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-MIMAROPA-Region-2024-07-01 | 4617 | 4617 | 4617 | 0 | 4617 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Cordillera-Administrative-Region-CAR-2024-07-01 | 7230 | 7230 | 7230 | 0 | 7230 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Bangsamoro-Autonomous-Region-In-Muslim-Mindanao-BARMM-2024-07-01 | 6900 | 6900 | 6900 | 0 | 6900 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XIII-Caraga-2024-07-01 | 4173 | 4173 | 4173 | 0 | 4173 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XII-SOCCSKSARGEN-2024-07-01 | 3453 | 3453 | 3453 | 0 | 3453 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XI-Davao-Region-2024-07-01 | 3651 | 3651 | 3651 | 0 | 3651 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Region-X-Northern-Mindanao-2024-07-01 | 6363 | 6363 | 6363 | 0 | 6363 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Zamboanga-Peninsula-2024-07-01 | 7230 | 7230 | 7230 | 0 | 7230 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Eastern-Visayas-2024-07-01 | 13545 | 13545 | 13545 | 0 | 13545 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Central-Visayas-2024-07-01 | 7248 | 7248 | 7248 | 0 | 7248 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Western-Visayas-2024-07-01 | 10488 | 10488 | 10488 | 0 | 10488 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Bicol-Region-2024-07-01 | 10776 | 10776 | 10776 | 0 | 10776 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-CALABARZON-2024-07-01 | 12423 | 12423 | 12423 | 0 | 12423 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Central-Luzon-2024-07-01 | 9729 | 9729 | 9729 | 0 | 9729 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Cagayan-Valley-2024-07-01 | 7230 | 7230 | 7230 | 0 | 7230 | 0 | 0 | 0 | 0 |
| psa-census-2024-population | PSA-2024-CENSUS-Ilocos-Region-2024-07-01 | 10191 | 10191 | 10191 | 0 | 10191 | 0 | 0 | 0 | 0 |

## Conflicting source attributes

Counts facilities whose stored field-level assertions disagree across sources. Conflict detection is informational; no value is auto-merged.

| Attribute | Facilities with conflicting source values |
|---|---|
| display_name | 458 |

## Per-release ingestion statistics

| Dataset | Release | Input | Parsed | Accepted | Rejected | Duplicate IDs | With coords | PSGC provided | PSGC matched | Match candidates | Run status | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bir-revenue-district-offices | BIR-RAO-006-2025 | 0 | 124 | 124 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| deped-ebeis-masterlist-ncr | DEPED-EBEIS-NCR-2026-11-15 | 0 | 5055 | 5055 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| deped-ebeis-masterlist-ncr | DEPED-EBEIS-NCR-2026-11-15 | 0 | 5055 | 5055 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| dswd-crcf-directory | DSWD-CRCF-2026-11-15 | 0 | 76 | 76 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| nlp-public-libraries | NLP-PUBLIC-LIBRARIES-2025-12 | 0 | 1752 | 1752 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| nmis-naris-accredited-meat-establishments | NMIS-NARIS-2026-11-15 | 0 | 357 | 357 | 0 | 0 | 88 | 0 | 0 | 0 | published | NULL |
| nmp-regional-area-site-museums | NMP-MUSEUMS-2026-11-15 | 0 | 17 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| osm-education-facilities | HOT-OSM-PHL-EDUCATION-2026-11-15 | 0 | 55824 | 52824 | 3000 | 2985 | 52824 | 52576 | 44814 | 0 | published | NULL |
| osm-health-facilities | HOT-OSM-PHL-HEALTH-2026-11-15 | 0 | 18008 | 17410 | 598 | 587 | 17410 | 17402 | 11202 | 0 | published | NULL |
| philhealth-abpp | PHILHEALTH-ABPP_093026-2026-09-30 | 0 | 1670 | 1670 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-ambu | PHILHEALTH-AMBU_093026-2026-09-30 | 0 | 104 | 104 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-asc | PHILHEALTH-ASC_093026-2026-09-30 | 0 | 281 | 281 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-cancerscreening | PHILHEALTH-CANCERSCREENING-UNDATED | 0 | 415 | 415 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-chibp | PHILHEALTH-CHIBP_093026-2026-09-30 | 0 | 11 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-ciu | PHILHEALTH-CIU_093026-2026-09-30 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-covidlab | PHILHEALTH-COVIDLAB_093026-2026-09-30 | 0 | 105 | 105 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-ctf | PHILHEALTH-CTF_093026-2026-09-30 | 0 | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-datrc | PHILHEALTH-DATRC_093026-2026-09-30 | 0 | 24 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-dental | PHILHEALTH-DENTAL_093026-2026-09-30 | 0 | 687 | 687 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-dots | PHILHEALTH-DOTS_093026-2026-09-30 | 0 | 2097 | 2097 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-emcb-ante | PHILHEALTH-EMCB-ANTE_093026-2026-09-30 | 0 | 6562 | 6562 | 0 | 394 | 0 | 0 | 0 | 0 | withdrawn | withdrawn_after_review: the 6,562-row parse counted the PDF expiry/sector annex (pages 121-240) as provider rows. All derived source records, accreditations, and links were removed; corrected parser philhealth-pdf-1.2.0 re-reads 3,221 provider rows. No records from this release are published. |
| philhealth-emcb-lab | PHILHEALTH-EMCB-LAB_093026-2026-09-30 | 0 | 222 | 222 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-emcb-ppartum | PHILHEALTH-EMCB-PPARTUM_093026-2026-09-30 | 0 | 3222 | 3222 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-emcb-putz | PHILHEALTH-EMCB-PUTZ_093026-2026-09-30 | 0 | 92 | 92 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-emcb-tvu | PHILHEALTH-EMCB-TVU_093026-2026-09-30 | 0 | 90 | 90 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-fdc | PHILHEALTH-FDC_093026-2026-09-30 | 0 | 1012 | 1012 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-fp | PHILHEALTH-FP_093026-2026-09-30 | 0 | 1465 | 1465 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-gamot | PHILHEALTH-GAMOT-UNDATED | 0 | 3483 | 3483 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-hosp | PHILHEALTH-HOSP_093026-2026-09-30 | 0 | 1934 | 1934 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-mcc | PHILHEALTH-MCC_093026-2026-09-30 | 0 | 3140 | 3140 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-ohat | PHILHEALTH-OHAT_093026-2026-09-30 | 0 | 342 | 342 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-omp | PHILHEALTH-OMP_093026-2026-09-30 | 0 | 100 | 100 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-opto | PHILHEALTH-OPTO_093026-2026-09-30 | 0 | 125 | 125 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-sam | PHILHEALTH-SAM_093026-2026-09-30 | 0 | 209 | 209 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| philhealth-yakap | PHILHEALTH-YAKAP-UNDATED | 0 | 4138 | 4138 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| phlpost-post-office-locator | PHLPOST-LOCATOR-2026-11-15 | 0 | 1272 | 1272 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| phlpost-post-office-locator | PHLPOST-LOCATOR-2026-11-15 | 0 | 1272 | 1272 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| ppa-port-list | PPA-PORT-LIST-2026-11-15 | 0 | 574 | 574 | 0 | 0 | 0 | 0 | 0 | 0 | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-CALABARZON-2024-07-01 | 12423 | 12423 | 12423 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Central-Luzon-2024-07-01 | 9729 | 9729 | 9729 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Western-Visayas-2024-07-01 | 10488 | 10488 | 10488 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Central-Visayas-2024-07-01 | 7248 | 7248 | 7248 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Cagayan-Valley-2024-07-01 | 7230 | 7230 | 7230 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Negros-Island-Region-NIR-2024-07-01 | 4260 | 4260 | 4260 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Bicol-Region-2024-07-01 | 10776 | 10776 | 10776 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XIII-Caraga-2024-07-01 | 4173 | 4173 | 4173 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XII-SOCCSKSARGEN-2024-07-01 | 3453 | 3453 | 3453 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-MIMAROPA-Region-2024-07-01 | 4617 | 4617 | 4617 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XI-Davao-Region-2024-07-01 | 3651 | 3651 | 3651 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Region-X-Northern-Mindanao-2024-07-01 | 6363 | 6363 | 6363 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Bangsamoro-Autonomous-Region-In-Muslim-Mindanao-BARMM-2024-07-01 | 6900 | 6900 | 6900 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Ilocos-Region-2024-07-01 | 10191 | 10191 | 10191 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-National-Captial-Region-NCR-2024-07-01 | 5241 | 5241 | 5241 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Eastern-Visayas-2024-07-01 | 13545 | 13545 | 13545 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Zamboanga-Peninsula-2024-07-01 | 7230 | 7230 | 7230 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |
| psa-census-2024-population | PSA-2024-CENSUS-Cordillera-Administrative-Region-CAR-2024-07-01 | 7230 | 7230 | 7230 | 0 | NULL | NULL | NULL | NULL | NULL | published | NULL |

## Interpretation limits

- Missing coordinates are retained as missing. No coordinates were fabricated to fill the map.
- OSM coordinates are bounding-box centres and are labelled `map_geocoded`, not verified facility points.
- A mapped or registered facility does not prove that it is currently open.
- PSGC match counts describe code matching, not boundary or address verification.

