# 05 — Source Rights and Publication Report

**Generated:** 2026-11-15T13:36:25.172780+00:00  
**Source of truth:** the configured PhilFacilities PostgreSQL database.  

Recorded rights states and the technical publication gate per dataset and release.

**This is an evidence register, not a legal opinion.** No source has a completed formal legal review. Rights states record the terms and source evidence collected and the technical gate applied by the platform. Publication decisions follow `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.

**Snapshot note:** this report is generated from the configured database. A source registry or release decision and the canonical facility publication flag can move at different times; a re-ingestion or field-level review is required before every surface reflects the same state. For example, the current DepEd EBEIS release is published for institution-level fields, while its canonical facility rows remain `internal`.

## Dataset-level rights and publication gates

| Dataset | Rights status | Publication status | Basis / terms | Attribution | Personal data |
|---|---|---|---|---|---|
| psa-census-2024-population | approved_with_attribution | approved | BetterGov.PH publishes the Philippine Data Explorer's original material under CC BY-SA 4.0. The population values are saved PSA OpenSTAT snapshots reproduced without aggregation; PSA remains the authoritative source. BetterGov.PH states that its preview does not itself establish redistribution rights, so this publication decision relies on the CC BY-SA 4.0 licence for the compilation and retains the PSA table URL, release identifier and attribution. No new PSA terms review is claimed. | BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source | NULL |
| psgc-bettergov-q2-2024 | approved_with_attribution | published | BetterGov.PH publishes the classification API under CC BY-SA 4.0. The snapshot mirrors PSA PSGC Q2 2024; it is supplementary and is not the latest official PSA workbook. Attribution is retained and adaptations share the same licence. | BetterGov.PH Classification API (CC BY-SA 4.0), derived from PSA PSGC Q2 2024 | NULL |
| bir-revenue-district-offices | approved_with_attribution | published | RAO No. 006-2025 is an official issuance of the Bureau of Internal Revenue, a government agency. RA 8293 section 176 provides that no copyright subsists in a work of the Government of the Philippines, while prior approval may be required for commercial use. PhilFacilities publishes the institutional office list with attribution for non-commercial public-interest use. The PDF is image-only; OCR recovered text is stored alongside the original file and is not treated as a replacement for the official document. This is a documented publication decision, not a legal opinion. | Bureau of Internal Revenue — Revenue Administrative Order No. 006-2025, List of Revenue Regions and Revenue District Offices (9 December 2025) | NULL |
| ched-hei-directory | review_required | blocked | The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked. | NULL | NULL |
| deped-ebeis-masterlist-ncr | approved_with_attribution | published | The EBEIS masterlist is a public result set of the Department of Education, a government agency. RA 8293 section 176 provides that no copyright subsists in a work of the Government of the Philippines, while prior approval may be required for commercial use. PhilFacilities publishes institution-level school fields with attribution for non-commercial public-interest use. School-head names and other personal fields remain in the private source store and are not exposed by the public API. This is a documented publication decision, not a legal opinion. | Department of Education — Enhanced Basic Education Information System (EBEIS) school masterlist | school_head_names_retained_privately_not_published |
| deped-machine-ready-files | review_required | blocked | The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked. | NULL | NULL |
| doh-nhfr | review_required | blocked | The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked. | NULL | NULL |
| dswd-crcf-directory | approved_with_attribution | published | The DSWD Centers and Residential Care Facilities directory is a work of the Department of Social Welfare and Development, a government agency. RA 8293 section 176 provides that no copyright subsists in a work of the Government of the Philippines, while prior approval may be required for commercial use. PhilFacilities publishes institutional facility name, responsible field office and postal address with attribution for non-commercial public-interest use. No coordinates, admission rules or operational status are inferred. This is a documented publication decision, not a legal opinion. | Department of Social Welfare and Development — Centers and Residential Care Facilities (CRCF) directory | NULL |
| nlp-public-libraries | approved_with_attribution | published | The directory is a work of the Government of the Philippines. RA 8293 section 176 provides that no copyright subsists in a government work, while prior approval may be required for commercial use. PhilFacilities publishes the institutional library fields with attribution for non-commercial public-interest use and excludes personal librarian contact fields. This is a documented publication decision, not a legal opinion. | National Library of the Philippines, Public Libraries Division — Directory of Affiliated Public Libraries in the Philippines, December 2025 | NULL |
| nmis-naris-accredited-meat-establishments | approved_with_attribution | published | NARIS is the National Meat Inspection Service's public accreditation directory. The page carries an 'All rights reserved' notice but publishes factual establishment name, LTO number, establishment type and postal address. Under docs/14 and ADR 0008, PhilFacilities publishes only those factual fields with attribution and takedown-on-notice; it does not copy expressive page content and does not treat the notice as an automatic bar. The page currently returns a WAF challenge or TLS failure on recheck, so the verified 15 November 2026 artifact is the release of record. This is a documented product decision, not a legal opinion. | National Meat Inspection Service — NARIS Accredited Meat Establishments | NULL |
| nmp-regional-area-site-museums | approved_with_attribution | published | The National Museum directory and site pages are works of the Government of the Philippines. RA 8293 section 176 provides that no copyright subsists in a government work, while prior approval may be required for commercial use. PhilFacilities publishes institutional museum fields with attribution for non-commercial public-interest use. This is a documented publication decision, not a legal opinion. | National Museum of the Philippines — Regional, Area and Site Museums directory | NULL |
| osm-education-facilities | approved_with_attribution | published | OpenStreetMap data is made available under the Open Database License (ODbL) 1.0. Attribution to OpenStreetMap contributors and the HOT/BetterGov extract is required; derivative databases remain share-alike. | © OpenStreetMap contributors, via HOT and BetterGov.PH | NULL |
| osm-health-facilities | approved_with_attribution | published | OpenStreetMap data is made available under the Open Database License (ODbL) 1.0. Attribution to OpenStreetMap contributors and the HOT/BetterGov extract is required; derivative databases remain share-alike. | © OpenStreetMap contributors, via HOT and BetterGov.PH | NULL |
| philhealth-abpp | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-accredited-providers | approved_with_attribution | approved | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-ambu | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-asc | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-cancerscreening | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-chibp | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-ciu | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-covidlab | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-ctf | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-datrc | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-dental | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-dots | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-emcb-ante | approved_with_attribution | blocked | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-emcb-lab | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-emcb-ppartum | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-emcb-putz | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-emcb-tvu | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-fdc | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-fp | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-gamot | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-hosp | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-mcc | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-mcp | approved_with_attribution | approved | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-ohat | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-omp | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-opto | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-sam | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| philhealth-yakap | approved_with_attribution | published | PhilHealth's published site disclaimer states that its information may be used for educational or informative purposes and may be reproduced, copied or downloaded without written permission from PhilHealth. This is a terms-based publication decision, not a completed legal review; attribution is retained. | Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory | business_contact_information |
| phlpost-post-office-locator | approved_with_attribution | published | PHLPost is a government-owned and controlled corporation. Its public locator page carries an explicit copyright/all-rights-reserved notice. Under the product owner's public-record inclusion decision, PhilFacilities publishes only the factual locator fields needed for facility discovery (office name, province, address and listed services) with attribution, and does not republish the page's expressive content. This is a documented product decision, not a legal opinion; the source notice and a takedown route remain recorded. | Philippine Postal Corporation — Post Office Locator | NULL |
| ppa-port-list | approved_with_attribution | published | The List of Ports Covered in PPA Statistics is a published work of the Philippine Ports Authority, a government-owned and controlled corporation. RA 8293 section 176 provides that no copyright subsists in a work of the Government of the Philippines, while prior approval may be required for commercial use. PhilFacilities publishes the factual port name, PMO/region hierarchy, RORO and NON-RORO marks, remarks and private/government group with attribution for non-commercial public-interest use. No coordinates, berth capacity, owner names or operational status are inferred. This is a documented publication decision, not a legal opinion. | Philippine Ports Authority — List of Ports Covered in PPA Statistics | NULL |
| psgc-official | review_required | blocked | The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked. | NULL | NULL |
| tesda-tvi-directory | review_required | blocked | The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked. | NULL | NULL |

## Release-level gates

| Dataset | Release | Terms review | Publication |
|---|---|---|---|
| psa-census-2024-population | PSA-2024-CENSUS-Negros-Island-Region-NIR-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-National-Captial-Region-NCR-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-MIMAROPA-Region-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Cordillera-Administrative-Region-CAR-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Bangsamoro-Autonomous-Region-In-Muslim-Mindanao-BARMM-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XIII-Caraga-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XII-SOCCSKSARGEN-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Region-XI-Davao-Region-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Region-X-Northern-Mindanao-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Zamboanga-Peninsula-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Eastern-Visayas-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Central-Visayas-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Western-Visayas-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Bicol-Region-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-CALABARZON-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Central-Luzon-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Cagayan-Valley-2024-07-01 | approved_with_attribution | published |
| psa-census-2024-population | PSA-2024-CENSUS-Ilocos-Region-2024-07-01 | approved_with_attribution | published |
| bir-revenue-district-offices | BIR-RAO-006-2025 | approved_with_attribution | published |
| deped-ebeis-masterlist-ncr | DEPED-EBEIS-NCR-2026-11-15 | approved_with_attribution | published |
| deped-ebeis-masterlist-ncr | DEPED-EBEIS-NCR-2026-11-15 | restricted_non_redistributable | internal_only |
| dswd-crcf-directory | DSWD-CRCF-2026-11-15 | approved_with_attribution | published |
| nlp-public-libraries | NLP-PUBLIC-LIBRARIES-2025-12 | approved_with_attribution | published |
| nmis-naris-accredited-meat-establishments | NMIS-NARIS-2026-11-15 | approved_with_attribution | published |
| nmp-regional-area-site-museums | NMP-MUSEUMS-2026-11-15 | approved_with_attribution | published |
| osm-education-facilities | HOT-OSM-PHL-EDUCATION-2026-11-15 | approved_with_attribution | published |
| osm-health-facilities | HOT-OSM-PHL-HEALTH-2026-11-15 | approved_with_attribution | published |
| philhealth-abpp | PHILHEALTH-ABPP_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-ambu | PHILHEALTH-AMBU_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-asc | PHILHEALTH-ASC_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-cancerscreening | PHILHEALTH-CANCERSCREENING-UNDATED | approved_with_attribution | published |
| philhealth-chibp | PHILHEALTH-CHIBP_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-ciu | PHILHEALTH-CIU_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-covidlab | PHILHEALTH-COVIDLAB_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-ctf | PHILHEALTH-CTF_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-datrc | PHILHEALTH-DATRC_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-dental | PHILHEALTH-DENTAL_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-dots | PHILHEALTH-DOTS_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-emcb-ante | PHILHEALTH-EMCB-ANTE_093026-2026-09-30 | approved_with_attribution | blocked |
| philhealth-emcb-lab | PHILHEALTH-EMCB-LAB_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-emcb-ppartum | PHILHEALTH-EMCB-PPARTUM_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-emcb-putz | PHILHEALTH-EMCB-PUTZ_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-emcb-tvu | PHILHEALTH-EMCB-TVU_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-fdc | PHILHEALTH-FDC_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-fp | PHILHEALTH-FP_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-gamot | PHILHEALTH-GAMOT-UNDATED | approved_with_attribution | published |
| philhealth-hosp | PHILHEALTH-HOSP_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-mcc | PHILHEALTH-MCC_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-ohat | PHILHEALTH-OHAT_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-omp | PHILHEALTH-OMP_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-opto | PHILHEALTH-OPTO_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-sam | PHILHEALTH-SAM_093026-2026-09-30 | approved_with_attribution | published |
| philhealth-yakap | PHILHEALTH-YAKAP-UNDATED | approved_with_attribution | published |
| phlpost-post-office-locator | PHLPOST-LOCATOR-2026-11-15 | approved_with_attribution | published |
| phlpost-post-office-locator | PHLPOST-LOCATOR-2026-11-15 | review_required | internal_only |
| ppa-port-list | PPA-PORT-LIST-2026-11-15 | approved_with_attribution | published |

## Public exposure by dataset

| Dataset | Public facilities | Non-public facilities |
|---|---|---|
| osm-education-facilities | 41891 | 10933 |
| philhealth-yakap | 4109 | 1 |
| philhealth-emcb-ppartum | 3179 | 0 |
| philhealth-mcc | 3127 | 0 |
| philhealth-gamot | 3067 | 1 |
| osm-health-facilities | 2774 | 14636 |
| philhealth-dots | 2065 | 1 |
| philhealth-hosp | 1927 | 1 |
| nlp-public-libraries | 1752 | 0 |
| philhealth-abpp | 1666 | 0 |
| philhealth-fp | 1446 | 0 |
| phlpost-post-office-locator | 1272 | 0 |
| philhealth-fdc | 974 | 0 |
| philhealth-dental | 676 | 0 |
| ppa-port-list | 574 | 0 |
| philhealth-cancerscreening | 414 | 1 |
| nmis-naris-accredited-meat-establishments | 357 | 0 |
| philhealth-ohat | 339 | 0 |
| philhealth-asc | 281 | 0 |
| philhealth-emcb-lab | 222 | 0 |
| philhealth-sam | 207 | 0 |
| philhealth-opto | 125 | 0 |
| bir-revenue-district-offices | 124 | 0 |
| philhealth-covidlab | 105 | 0 |
| philhealth-ambu | 104 | 0 |
| philhealth-omp | 100 | 0 |
| philhealth-emcb-putz | 92 | 0 |
| philhealth-emcb-tvu | 90 | 0 |
| dswd-crcf-directory | 76 | 0 |
| philhealth-datrc | 24 | 0 |
| nmp-regional-area-site-museums | 17 | 0 |
| philhealth-ctf | 16 | 0 |
| philhealth-chibp | 11 | 0 |
| philhealth-ciu | 2 | 0 |
| ched-hei-directory | 0 | 0 |
| deped-ebeis-masterlist-ncr | 0 | 5055 |
| deped-machine-ready-files | 0 | 0 |
| doh-nhfr | 0 | 0 |
| philhealth-accredited-providers | 0 | 0 |
| philhealth-emcb-ante | 0 | 0 |
| philhealth-mcp | 0 | 0 |
| psa-census-2024-population | 0 | 0 |
| psgc-bettergov-q2-2024 | 0 | 0 |
| psgc-official | 0 | 0 |
| tesda-tvi-directory | 0 | 0 |

## Enforced rules

- A facility is public only when its cached publication flag is `public` **and** it links through a source record and release to a dataset whose redistribution status is public-compatible and whose release is approved or published.
- `restricted_non_redistributable`, `review_required`, `unknown`, `denied`, and `expired` sources are excluded, even if their records are stored.
- `publicly_available_verified` is public-compatible when the exact release is verified, publicly available, and not subject to an explicit prohibition, and only reviewed institutional fields are published with provenance, attribution, and takedown-on-notice.
- DepEd EBEIS contains school-head names. The current source release is published for institution-level fields with those names withheld; canonical facility rows remain `internal` until field-level mapping and privacy review.
- PHLPost publishes 1,272 factual locator facilities under a recorded product decision; an earlier review-required release is retained internally.
- Official PSA PSGC, official DepEd Machine-Ready Files, DOH NHFR/HFSRB, CHED, and TESDA are not published because no verified public release or agreement-based publication decision exists.
- OSM-derived records carry ODbL attribution and are labelled non-official.

