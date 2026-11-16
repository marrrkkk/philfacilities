# Blocked and gated sources

**As of:** 2026-11-16

A block is recorded, not bypassed. No Cloudflare/WAF challenge, CAPTCHA, login, download form, paywall or robots refusal was circumvented in this pass.

## `bai.agri_facilities` — Bureau of Animal Industry

- **Category:** ENVIRONMENT_AGRI
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** bai=TRANSPORT_ERROR; error=curl: (6) Could not resolve host: www.bai.da.gov.ph
- **Official URLs:** https://www.bai.da.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Retry later and request the official laboratory/station list through DA

## `bfar.fisheries_facilities` — Bureau of Fisheries and Aquatic Resources

- **Category:** ENVIRONMENT_AGRI
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** bfar=TRANSPORT_ERROR; error=curl: (6) Could not resolve host: www.bfar.da.gov.ph
- **Official URLs:** https://www.bfar.da.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Retry later and seek the official facility inventory through DA/BFAR

## `bfp.fire_stations` — Bureau of Fire Protection

- **Category:** EMERGENCY_DRM
- **Access state:** FOI_REQUIRED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FOI_ACCESS_CONFIRMED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://www.foi.gov.ph/agencies/bfp/list-of-all-fire-stations/, https://region3.bfp.gov.ph/contact-us/
- **Official alternate routes:**
  - [FOI release — BFP logistical report (August 2025)](https://www.foi.gov.ph/agencies/bfp/list-of-all-fire-stations/) — FOI response links a public Drive folder. A human must review the attachment scope and terms; no bypass was attempted.
  - [DILG DRRM-PULSE participating-LGU map](https://drrm.ncr.dilg.gov.ph/map) — Participating-LGU map categories include fire stations. Feed returned one command-centre feature in prior inspection; not a bulk register.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Download the linked attachment through normal public access, inspect its geographic scope/fields, ask BFP about national completeness and refresh frequency.

## `bjmp.facilities` — BJMP

- **Category:** JUSTICE_CORRECTIONS
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** DISCOVERY_ONLY
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** bjmp=HTTP_403
- **Official URLs:** https://bjmp.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P2/conditional.** Verify a public facility-only directory; avoid operational/security details.

## `bmb.protected_areas` — DENR Biodiversity Management Bureau

- **Category:** ENVIRONMENT_AGRI
- **Access state:** OPEN
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** OFFICIAL_PORTAL_VERIFIED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** pais=TRANSPORT_ERROR; error=curl: (35) TLS connect error: error:0A000126:SSL routines::unexpected eof while reading
- **Official URLs:** https://pais.bmb.gov.ph/index.php, https://bmb.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P2 / contextual geography.** Use to associate a facility/site with a protected area only when useful; do not count each protected-area polygon as a facility.

## `caap.airports` — CAAP

- **Category:** TRANSPORT
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** DIRECTORY_CONTENT_VERIFIED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** caap=HTTP_403
- **Official URLs:** https://www.caap.gov.ph/area-centers/, https://www.caap.gov.ph/17950-2/, https://www.caap.gov.ph/
- **Official alternate routes:**
  - [Philippine Geoportal — National Airport / Airport Control Station](https://geoportal.gov.ph/) — Catalogue layers exist but no date, schema, feature count or reuse terms; download flag false. Not acquired.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P1/P2.** Acquire current aerodrome directory/AIP or authorized list; verify operator/owner, identifier, coordinates and active status airport by airport.

## `denr_mgb.geohazards` — MGB

- **Category:** ENVIRONMENT_AGRI
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** DISCOVERY_ONLY
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://mgb.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P2 / enrichment.** Verify each layer, source date, CRS, spatial coverage and reuse terms.

## `dhsud.housing_offices` — Department of Human Settlements and Urban Development

- **Category:** HOUSING_SETTLEMENT
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** dhsud=HTTP_403
- **Official URLs:** https://dhsud.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Request the official office/settlement-service directory

## `dilg.barangay_halls` — DILG / LGUs / NAMRIA

- **Category:** GOV_ADMIN
- **Access state:** FOI_REQUIRED
- **Rights state:** UNKNOWN
- **Evidence state:** FOI_LIMITATION_CONFIRMED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://www.foi.gov.ph/agencies/dilg/list-of-barangay-halls/, https://dilg.gov.ph/page/Masterlist-of-Barangays/77, https://www.namria.gov.ph/
- **Official alternate routes:**
  - [LGU published barangay directories](https://mandaluyong.gov.ph/government/barangays/) — Verified example: Mandaluyong published 27 barangay office records. Coverage is single-LGU; no national hall masterlist was supplied.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Use barangay list only for geography. Acquire halls from LGU asset inventories, NAMRIA if a specific layer exists, or official LGU directories.

## `dilg.drrm_pulse` — DILG-NCR

- **Category:** EMERGENCY_DRM
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** PUBLIC_FEED_INSPECTED_NOT_USABLE
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://drrm.ncr.dilg.gov.ph/, https://drrm.ncr.dilg.gov.ph/about, https://drrm.ncr.dilg.gov.ph/map, https://drrm.ncr.dilg.gov.ph/lgus
- **Official alternate routes:**
  - [DILG Subaybayan — evacuation-centre project list](https://subaybayan.dilg.gov.ph/) — Project records, not operating facilities. Prior inspection returned HTTP 403; no bypass attempted.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **BLOCKED pending broader validated export and written terms.** Ask DILG-NCR for an authorized export/API; do not infer a national inventory or publish operational coordinates without security review. Evidence: `docs/03-SOURCE-REGISTER.md` §6A.

## `dilg.evacuation_ncr_foi` — DILG-NCR

- **Category:** EMERGENCY_DRM
- **Access state:** FOI_REQUIRED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FOI_ACCESS_CONFIRMED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://www.foi.gov.ph/agencies/dilg/lists-of-existing-evacuation-centers/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Obtain the NCR attachment and investigate individual LGU inventories. Record the inconsistent national custodianship; do not claim a national complete register.

## `dilg.public_markets` — LGUs

- **Category:** PUBLIC_COMMERCE
- **Access state:** FOI_REQUIRED
- **Rights state:** UNKNOWN
- **Evidence state:** FOI_LIMITATION_CONFIRMED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://www.foi.gov.ph/agencies/dilg/list-of-public-markets-in-the-philippines-dilg-905479402880/, https://www.foi.gov.ph/agencies/dilg/public-market-list-area-and-population/, https://lgu201.dilg.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Build LGU-specific source connectors and requests; do not create a fake central DILG market dataset.

## `dilg.subaybayan_evacuation_projects` — DILG

- **Category:** EMERGENCY_DRM
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FOI_ACCESS_CONFIRMED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://subaybayan.dilg.gov.ph/, https://www.foi.gov.ph/agencies/dilg/updated-list-of-evacuation-center-in-the-philippines/, https://www.foi.gov.ph/agencies/dilg/updated-master-list-of-evacuation-center-in-the-philippines-dilg-902947380736/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P0.** Test access in normal browser, inspect actual project rows/fields and download capability. Use only as project/asset evidence, not the sole evacuation-centre register.

## `doh.nhfr` — DOH

- **Category:** HEALTH
- **Access state:** FOI_REQUIRED
- **Rights state:** AGREEMENT_REQUIRED
- **Evidence state:** FOI_ACCESS_CONFIRMED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://nhfr.doh.gov.ph/VActivefacilitiesList, https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/, https://doh.gov.ph/
- **Official alternate routes:**
  - [NHA GeoServer WFS — DOH HF layer](https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=NHA_PH:DOH%20HF&outputFormat=application/json) — Public NHA GeoServer layer tagged 'DOH HF'. 31,016 features observed on 16 November 2026 with a DOH facility code, type, ownership, PSGC labels and coordinates; a partial alternate route, not the complete NHFR.
  - [PhilHealth accredited-provider categories](https://www.philhealth.gov.ph/partners/providers/facilities/accredited/) — 26 provider-category releases already published. Accreditation is benefit-package-specific and is not a DOH licence or registry record.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Recheck permitted browser export; obtain current official file via authorized route/FOI; review exact agreement before public use; preserve coordinate provenance.

## `doj.justice_offices` — Department of Justice

- **Category:** JUSTICE_CORRECTIONS
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** doj=HTTP_403
- **Official URLs:** https://www.doj.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Request a public office directory; exclude security-sensitive details

## `dotr.transport_facilities` — Department of Transportation

- **Category:** TRANSPORT
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** dotr=HTTP_403
- **Official URLs:** https://www.dotr.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Request permitted access or use the attached-agency source of record

## `dpwh.ngob_inventory` — DPWH / national agencies

- **Category:** GOV_ADMIN
- **Access state:** HUMAN_DOWNLOAD_REQUIRED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FILE_DOCUMENT_VERIFIED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://www.dpwh.gov.ph/dpwh/sites/default/files/issuances/do_247_s2024.pdf
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** a human must complete the publisher's download form/terms flow and preserve the exact release.
- **Next action:** **P0/P1.** Request the resulting inventory or an authorized/redacted export; identify the actual building-owning agencies.

## `drrm.lgu_offices_and_resources` — DILG/LGUs

- **Category:** EMERGENCY_DRM
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** DISCOVERED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://drrm.ncr.dilg.gov.ph/map, https://dilg.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P0/P1.** Import public facility subset; do not expose sensitive equipment/resource details without review.

## `dswd.crcf` — DSWD

- **Category:** SOCIAL_WELFARE
- **Access state:** OPEN
- **Rights state:** PUBLISHED
- **Evidence state:** DIRECTORY_CONTENT_VERIFIED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** standards-dswd=TRANSPORT_ERROR; error=curl: (35) TLS connect error: error:0A000126:SSL routines::unexpected eof while reading
- **Official URLs:** https://www.dswd.gov.ph/crcf/, https://standards.dswd.gov.ph/directories-3/, https://eodb.dswd.gov.ph/directory/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P0/P1.** Acquire dated directories; inspect actual files; do not count private/merely accredited providers as government-owned.

## `dswd.standards_directories` — DSWD Standards Bureau

- **Category:** SOCIAL_WELFARE
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** standards-dswd=TRANSPORT_ERROR; error=curl: (35) TLS connect error: error:0A000126:SSL routines::unexpected eof while reading
- **Official URLs:** https://standards.dswd.gov.ph/directories-3/
- **Official alternate routes:**
  - [DSWD Centers and Residential Care Facilities directory](https://www.dswd.gov.ph/crcf/) — 76 DSWD-operated CRCFs published; not the Standards Bureau accredited lists.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Retry through a supported client and request the dated directory and reuse terms

## `eccd.ncdc_cdc` — ECCD Council

- **Category:** SOCIAL_WELFARE
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FILE_DOCUMENT_VERIFIED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** eccd=HTTP_403
- **Official URLs:** https://eccdcouncil.gov.ph/ncdc/, https://eccdcouncil.gov.ph/resources/, https://eccdcouncil.gov.ph/wp-content/uploads/2024/10/AR-2023-051024-2_compressed.pdf, https://eccdcouncil.gov.ph/wp-content/uploads/2025/10/ECCD_AR2025_7.21.pdf
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P0/P1.** Acquire NCDC list first; contact ECCD Council/DSWD/LGUs for permitted CDC registry. Do not interpret 1,057 NCDCs as the total number of all CDCs.

## `geoportal.facility_layers` — NAMRIA / Philippine Geoportal / originating agencies

- **Category:** OTHER_QUALIFYING
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** CATALOGUE_CANDIDATE
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://geoportal.gov.ph/, https://www.geoportal.gov.ph/gpresources/GP_DataInventory.pdf, https://www.geoportal.gov.ph/gpresources/How%20to%20Download%20data%20from%20Geoportal%20Philippines.pdf, https://www.namria.gov.ph/Downloads.aspx
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P0.** Review the current inventory row by row; create one source entry per selected layer; obtain original metadata, date, owner, geometry, CRS, download permission and redistribution terms. Do not ingest stale/unknown layers as current truth.

## `govph.directory` — GOV.PH

- **Category:** GOV_ADMIN
- **Access state:** UNVERIFIED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_404 on 2026-11-16
- **Probe notes:** govph-directory=HTTP_404
- **Official URLs:** https://www.gov.ph/directory
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Use agency-specific official directories; do not reconstruct a national facility list from agency links

## `judiciary.courts` — Judiciary

- **Category:** JUSTICE_CORRECTIONS
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** judiciary=TRANSPORT_ERROR; error=curl: (60) SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)
- **Official URLs:** https://sc.judiciary.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Use an official court directory or authorized dataset with valid TLS

## `lgu.community_facility_inventory` — each LGU

- **Category:** COMMUNITY
- **Access state:** FOI_REQUIRED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** OFFICIAL_LAW_VERIFIED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://lawphil.net/statutes/repacts/ra1991/ra_7160_1991.html, https://lgu201.dilg.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Ask LGUs for their actual existing inventories and previous releases; capture responsible office, format, scope, date and rights.

## `lwua.water_districts` — Local Water Utilities Administration

- **Category:** UTILITIES_SANITATION
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** lwua=HTTP_403
- **Official URLs:** https://lwua.gov.ph/
- **Official alternate routes:**
  - [LWUA public site](https://lwua.gov.ph/) — HTTP 403 on 16 Nov 2026; no official alternate register verified.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Request an authorized facility/service-area inventory with critical-infrastructure review

## `marina.ports` — Maritime Industry Authority

- **Category:** TRANSPORT
- **Access state:** OPEN
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_404 on 2026-11-16
- **Probe notes:** marina=HTTP_200; marina-ports=HTTP_404
- **Official URLs:** https://marina.gov.ph/, https://marina.gov.ph/ports/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Locate an official port/terminal registry; do not infer facilities from the homepage

## `mwss.water_facilities` — Metropolitan Waterworks and Sewerage System

- **Category:** UTILITIES_SANITATION
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** mwss=HTTP_403
- **Official URLs:** https://mwss.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Seek a site-level inventory; exclude sensitive operational details before publication

## `ncca.cultural_facilities` — National Commission for Culture and the Arts

- **Category:** CULTURE_KNOWLEDGE
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** ncca=TRANSPORT_ERROR; error=curl: (6) Could not resolve host: ncca.gov.ph
- **Official URLs:** https://ncca.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Retry later and seek an official cultural-facility directory

## `nea.electric_cooperatives` — National Electrification Administration

- **Category:** UTILITIES_SANITATION
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** nea=HTTP_403
- **Official URLs:** https://nea.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Request the official cooperative/service-office list with reuse terms

## `nfa.grain_facilities` — National Food Authority

- **Category:** ENVIRONMENT_AGRI
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** nfa=HTTP_403
- **Official URLs:** https://www.nfa.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Request an authorized warehouse/facility list and publication terms

## `nhcp.heritage_sites` — National Historical Commission of the Philippines

- **Category:** CULTURE_KNOWLEDGE
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** nhcp=HTTP_403
- **Official URLs:** https://nhcp.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Seek an official heritage-site register with coordinates and access conditions

## `nwrb.water_permits` — National Water Resources Board

- **Category:** UTILITIES_SANITATION
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** nwrb=HTTP_403
- **Official URLs:** https://nwrb.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Confirm whether a public facility-level layer exists before building a connector

## `ocd.evacuation_centres` — OCD / NDRRMC / LGUs

- **Category:** EMERGENCY_DRM
- **Access state:** FOI_REQUIRED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FOI_LIMITATION_CONFIRMED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** ocd=HTTP_403; ndrrmc=HTTP_403
- **Official URLs:** https://ocd.gov.ph/, https://ndrrmc.gov.ph/, https://www.foi.gov.ph/agencies/ocd/updated-list-of-evacuation-center-in-the-philippines-ocd-397929143969/, https://www.foi.gov.ph/agencies/dilg/updated-list-of-evacuation-center-in-the-philippines/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** a human must submit or review the FOI request and the response conditions before ingestion.
- **Next action:** **P0.** Combine only independently sourced LGU and DILG project records with clear source type; request current authoritative scope from LGUs.

## `open_data_philippines` — Open Data Philippines / DICT

- **Category:** OTHER_QUALIFYING
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://data.gov.ph/
- **Official alternate routes:**
  - [Open Data Philippines (data.gov.ph)](https://data.gov.ph/) — HTTP 200 single-page catalogue shell. The CKAN-style API paths return the same HTML shell, so no machine-readable catalogue endpoint was verified.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** Not the original publisher unless the dataset itself is agency-issued; file rights remain source-specific

## `pagasa.climate` — PAGASA

- **Category:** ENVIRONMENT_AGRI
- **Access state:** HUMAN_DOWNLOAD_REQUIRED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** OFFICIAL_PORTAL_VERIFIED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://climgridph.pagasa.dost.gov.ph/climapv2/, https://www.pagasa.dost.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** a human must complete the publisher's download form/terms flow and preserve the exact release.
- **Next action:** **P2 / enrichment.** Preserve grid release, resolution, baseline and scenario.

## `pca.coconut_facilities` — Philippine Coconut Authority

- **Category:** ENVIRONMENT_AGRI
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** pca=HTTP_403
- **Official URLs:** https://www.pca.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Verify a facility-level dataset exists before adding a connector

## `pcg.stations` — Philippine Coast Guard

- **Category:** TRANSPORT
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** pcg=TRANSPORT_ERROR; error=curl: (6) Could not resolve host: www.pcg.gov.ph
- **Official URLs:** https://www.pcg.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Apply public-safety and critical-infrastructure review before any publication

## `pfda.fish_ports` — Philippine Fisheries Development Authority

- **Category:** ENVIRONMENT_AGRI
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** FILE_DOCUMENT_VERIFIED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** pfda=HTTP_403
- **Official URLs:** https://www.pfda.gov.ph/, https://www.pfda.gov.ph/images/ISO_/CO/QMS/PFDA_QMS_2023_09.pdf, https://fishcore.bfar.da.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P1/P2.** Request PFDA current inventory with port ID, status, coordinates, owner/operator and turnover date.

## `phivolcs.hazards` — PHIVOLCS

- **Category:** OTHER_QUALIFYING
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** OFFICIAL_PORTAL_VERIFIED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://maps.phivolcs.dost.gov.ph/, https://www.phivolcs.dost.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P2 / enrichment.** Do not put hazard layers into the core facility entity table.

## `pnr.stations` — Philippine National Railways

- **Category:** TRANSPORT
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** HTTP_403 on 2026-11-16
- **Probe notes:** pnr=HTTP_403
- **Official URLs:** https://pnr.gov.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P1. Seek a permitted station inventory with current names, coordinates and operating status

## `psa.psgc` — Philippine Statistics Authority

- **Category:** OTHER_QUALIFYING
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://psa.gov.ph/classification/psgc, https://classification.psa.gov.ph/psgc, https://psa.gov.ph/content/classification-api-guide
- **Official alternate routes:**
  - [BetterGov Classification API (PSGC Q2 2024 mirror)](https://statistics.bettergov.ph/api/classification/psgc) — 43,760 published geographic units. A labelled supplementary snapshot, not the latest official PSA release.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** Use official PSA version as geographic source of record. Keep each release. Do not rely on old third-party snapshots

## `shfc.housing_projects` — Social Housing Finance Corporation

- **Category:** HOUSING_SETTLEMENT
- **Access state:** ACCESS_BLOCKED
- **Rights state:** UNKNOWN
- **Evidence state:** DISCOVERED
- **Probe:** TRANSPORT_ERROR on 2026-11-16
- **Probe notes:** shfc=TRANSPORT_ERROR; error=curl: (60) SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)
- **Official URLs:** https://shfc.com.ph/
- **Official alternate routes:** none verified in this pass.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** P2. Use an authorized project list; distinguish project sites from completed facilities

## `tesda.providers` — TESDA

- **Category:** EDUCATION
- **Access state:** ACCESS_BLOCKED
- **Rights state:** REVIEW_REQUIRED
- **Evidence state:** DIRECTORY_CONTENT_VERIFIED
- **Probe:** NOT_PROBED on UNKNOWN
- **Probe notes:** No live probe is recorded for this candidate.
- **Official URLs:** https://www.tesda.gov.ph/TVI, https://www.tesda.gov.ph/AssessmentCenters, https://www.tesda.gov.ph/About/TESDA/53, https://www.tesda.gov.ph/
- **Official alternate routes:**
  - [Philippine Geoportal — TESDA TVET providers (NCR), 2022-02-10](https://geoportal.gov.ph/) — Catalogue marks download true but the bulk route needs a human form; no layer-level licence was found. Not acquired.
- **Authorization needed:** none identified for a public retry; a human must confirm the publisher's terms before acquisition.
- **Next action:** **P1.** Find permitted provider-level export or request it. Keep statistics as enrichment only.
