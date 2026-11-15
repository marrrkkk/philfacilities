# 03 — Schema Report

**Generated:** 2026-11-15T14:28:56.207026+00:00  
**Source of truth:** the configured PhilFacilities PostgreSQL database.  

Original stored keys, types, presence, and missing-value counts by dataset.

The tables below describe the original top-level keys actually stored in `source.records.raw_payload`. They are not an agency-published data dictionary. Normalization mappings are implemented in the source adapters under `apps/ingest/philfacilities_ingest/sources/` and are versioned per release.

Nested objects are reported as a JSON type rather than flattened. Counts are measured over every stored record for the dataset. No acquired real dataset is a spreadsheet, so original sheet names are not applicable to the stored data; the DepEd workbook adapter is unused because no Machine-Ready File was acquired. Container formats and file identities are in report 02.

## Normalized field mapping

| Source family | Original field / key | Normalized destination | Rule / caveat |
|---|---|---|---|
| PhilHealth provider PDFs | Provider-name column (e.g. `NAME OF HEALTH FACILITY`) | `core.facilities.display_name`, `core.facilities.official_name` | Trimmed for display; the original string remains in `source.records.raw_payload`. |
| PhilHealth provider PDFs | Provider category column (e.g. `CAT`) | `core.facilities.facility_subtype`, `health.profiles.facility_category`, `health.accreditations.accreditation_category` | Benefit-package category, not an operational or licensed status. |
| PhilHealth provider PDFs | Contact/address columns where present (`TEL_NO`, `EMAIL`, `STREET`, `MUNICIPALITY`) | `health.accreditations.telephone`, `.email`, `.street_address`, `.municipality`; `core.facility_locations.address_text` | Address text is retained; no coordinates are inferred from it. |
| PhilHealth provider PDFs | `EXPIRE DATE` | `health.accreditations.valid_until` | Parsed only when the column/value exists; otherwise null. |
| PhilHealth provider PDFs | `SEC` | `health.accreditations.sector_code` | Null when the annex/column is absent. |
| DepEd EBEIS result pages | `School ID` | `source.records.source_record_key`, `source.records.source_entity_id`, `school.profiles.deped_school_id` | Leading zeros are preserved; the row key also carries the result-page table row. |
| DepEd EBEIS result pages | `School Name` | `core.facilities.display_name`, `core.facilities.official_name` | Original name retained; no cross-source rename is inferred. |
| DepEd EBEIS result pages | `School Type` | `core.facilities.facility_subtype` | Stored as reported; school type is not a licensing status. |
| DepEd EBEIS result pages | `Address` | `core.facility_locations.address_text` | No coordinates are inferred from the address. |
| DepEd EBEIS result pages | `Head / Position` | No normalized field; retained in the private raw record only | Personal data; never published. School-head names are withheld even though the source release is approved for institution-level publication. |
| HOT/OSM GeoParquet | `id` | `source.records.source_record_key`, `source.records.source_entity_id` | Entity key is prefixed `osm:`. |
| HOT/OSM GeoParquet | `name` / `name_en` | `core.facilities.display_name`, `core.facilities.official_name` | Unnamed features are rejected rather than invented. |
| HOT/OSM GeoParquet | `healthcare` / `amenity` / `building` | `core.facilities.facility_subtype` | Domain-specific choice; the raw tags remain in the source record. |
| HOT/OSM GeoParquet | `addr_full` / `addr_city` | `core.facility_locations.address_text` | No address geocoding is performed. |
| HOT/OSM GeoParquet | Feature bbox centre | `core.facility_locations.latitude`, `.longitude` | Always `precision=map_geocoded`, `method=openstreetmap_bbox_center`; never promoted to a precise pin. |
| HOT/OSM GeoParquet | `operator_type` | `core.facilities.ownership` | `unknown` when absent; registry presence does not imply operation. |
| PSA 2024 Census via BetterGov | `codes[0]` | `stats.population_observations.psgc_code` | PSGC code as text; leading zeros preserved. |
| PSA 2024 Census via BetterGov | `codes[1]` | `stats.population_observations.indicator_code` | PSA parameter code; the label is stored separately. |
| PSA 2024 Census via BetterGov | `labels[0]` / `labels[1]` | `stats.population_observations.geographic_name` / `.indicator_label` | Original labels retained with leading dots stripped for display only. |
| PSA 2024 Census via BetterGov | `value` | `stats.population_observations.value` | Null is preserved; a missing value is never converted to zero. |
| BetterGov PSGC mirror | `code`, `area_name`, `geographic_level` | `geo.administrative_units.psgc_code`, `.name`, `.geographic_level` | Versioned per geographic release; leading zeros preserved. |
| BetterGov PSGC mirror | `correspondence_code`, `old_name`, `city_class`, `income_classification`, `urban_rural`, `island_region` | `geo.administrative_units` fields of the same names | Retained as published; previous geographic releases remain addressable. |

## Per-dataset original schema

### `bir-revenue-district-offices`

- Declared schema version: `not recorded`
- Stored source records: 124
- Distinct source-record keys: 124
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| ocr_confidence | 124 | 0 | 0 | number | 0.951461254504689 |
| page | 124 | 0 | 0 | number | 1 |
| raw_ocr_text | 124 | 0 | 0 | string | RDONo.100-MisamisOccidental |
| rdo_code | 124 | 0 | 0 | string | 1 |
| rdo_name | 124 | 0 | 0 | string | Abra |
| revenue_region_name | 124 | 0 | 0 | string | Bicol Region |
| revenue_region_number | 124 | 0 | 0 | string | 1 |

### `ched-heida-hei-directory`

- Declared schema version: `not recorded`
- Stored source records: 2711
- Distinct source-record keys: 2711
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| address | 2711 | 0 | 1 | null, string | #005 Maysan Road, Valenzuela City, Metro Manila |
| code | 2711 | 0 | 0 | string | - |
| name | 2711 | 0 | 0 | string | 1MRDA Academic Center |
| region | 2711 | 0 | 0 | string | Bangsamoro Autonomous Region In Muslim Mindanao (BARMM) |
| region_id | 2711 | 0 | 0 | string | 1 |
| source_page | 2711 | 0 | 0 | string | https://heida.ched.gov.ph/hei-directory/10?page=1 |
| source_row | 2711 | 0 | 0 | number | 1 |
| type | 2711 | 0 | 0 | string | Chartered State College/University (Main) |

### `deped-ebeis-masterlist-ncr`

- Declared schema version: `not recorded`
- Stored source records: 10110
- Distinct source-record keys: 5055
- Duplicate source-record keys: 5055
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| Address | 10110 | 0 | 110 | string |  |
| Head / Position | 10110 | 0 | 0 | string | - |
| School ID | 10110 | 0 | 0 | string | 107975 |
| School Name | 10110 | 0 | 0 | string | 15th Avenue Elementary School |
| School Type | 10110 | 0 | 0 | string | Grade 11-12 |
| _table_row | 10110 | 0 | 0 | number | 10 |

### `deped-machine-ready-files`

No source records are stored for this dataset, so no original schema can be reported.

### `doh-nhfr`

No source records are stored for this dataset, so no original schema can be reported.

### `dswd-crcf-directory`

- Declared schema version: `not recorded`
- Stored source records: 76
- Distinct source-record keys: 76
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| accordion_block | 76 | 0 | 0 | number | 1 |
| address | 76 | 0 | 0 | string | 19 San Isidro Ave, Cotabato City, Maguindanao |
| card_index | 76 | 0 | 0 | number | 1 |
| detail_url | 76 | 0 | 28 | null, string | http://Elsie%20Gaches%20Village |
| facility_name | 76 | 0 | 0 | string | ACCELERATING MINOR'S OPPORTUNITY FOR RECOVERY(AMOR) VILLAGE |
| field_office | 76 | 0 | 0 | string | Field Office 10 – Northern Mindanao |
| region | 76 | 0 | 0 | string | CARAGA Region |
| _row | 76 | 0 | 0 | number | 1 |
| variant_count | 76 | 0 | 0 | number | 2 |

### `dti-negosyo-centers`

- Declared schema version: `not recorded`
- Stored source records: 1427
- Distinct source-record keys: 1427
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| address | 1427 | 0 | 0 | string | 0171 P.M. Durias Bldg., Quezon Ave., Extn., Pala-o, Iligan City |
| city | 1427 | 0 | 0 | string | Aborlan |
| email | 1427 | 0 | 225 | null, string | ABR-NCBaayLicuan_LGU@dti.gov.ph |
| id | 1427 | 0 | 0 | number | 1434 |
| is_active | 1427 | 0 | 0 | boolean | true |
| name | 1427 | 0 | 0 | string | Aborlan Negosyo Center |
| phone | 1427 | 0 | 1427 | null | NULL |
| province | 1427 | 0 | 0 | string | Abra |
| region | 1427 | 0 | 0 | string | CAR - Cordillera Administrative Region |

### `nlp-public-libraries`

- Declared schema version: `not recorded`
- Stored source records: 1752
- Distinct source-record keys: 1752
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| ADDRESS | 1752 | 0 | 0 | string | - |
| DATE AFFILIATED | 1752 | 0 | 6 | string |  |
| LOCATION | 1752 | 0 | 0 | string | Abra |
| NAME OF LIBRARY | 1752 | 0 | 0 | string | 13 Leon Kilat Barangay Reading Center |
| NO. | 1752 | 0 | 0 | string | 1 |
| _page | 1752 | 0 | 0 | number | 1 |
| PHILIPPINE PUBLIC LIBRARY ID | 1752 | 0 | 0 | string | PPLB-00001 |
| REGION | 1752 | 0 | 0 | string | 1 |
| _row | 1752 | 0 | 0 | string | 1 |
| STATUS | 1752 | 0 | 0 | string | Active |
| TELEPHONE NUMBER | 1752 | 0 | 0 | string | - |
| TYPE OF PUBLIC LIBRARY | 1752 | 0 | 0 | string | Barangay Reading Center |

### `nmis-naris-accredited-meat-establishments`

- Declared schema version: `not recorded`
- Stored source records: 357
- Distinct source-record keys: 357
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| address_variants | 357 | 0 | 0 | array | [{"cached_lat": 10.2921765, "cached_lng": 123.9034668, "full_address": "M. C.  Briones Street, San Roque, Cebu City", "barangay_name": "San Roque", "province_name": "Cebu", "municipality_name": "City of Cebu"}] |
| barangay_name | 357 | 0 | 266 | null, string | Abella |
| cached_lat | 357 | 0 | 269 | null, number | 10.2921765 |
| cached_lng | 357 | 0 | 269 | null, number | 120.3826159 |
| company_name | 357 | 0 | 0 | string | 2WHEELS ADVENTURES INC. |
| establishment_type | 357 | 0 | 0 | string | coldstorage_warehouse |
| full_address | 357 | 0 | 0 | string | 10320 PROVINCIAL ROAD,SITIO TABAY LAWOM,SAN VICENTE,LILOAN, CEBU |
| lto_number | 357 | 0 | 0 | string | MCP-006-AA |
| municipality_name | 357 | 0 | 263 | null, string | 031411000 |
| province_name | 357 | 0 | 274 | null, string | 031400000 |
| region_code | 357 | 0 | 0 | string | 010000000 |
| _row | 357 | 0 | 0 | number | 1 |
| variant_count | 357 | 0 | 0 | number | 1 |

### `nmp-regional-area-site-museums`

- Declared schema version: `not recorded`
- Stored source records: 17
- Distinct source-record keys: 17
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| address | 17 | 0 | 5 | null, string | Aggugaddan, Peñablanca, Cagayan |
| detail_status | 17 | 0 | 0 | number | 200 |
| email | 17 | 0 | 4 | null, string | cebu@nationalmuseum.gov.ph |
| name | 17 | 0 | 0 | string | National Museum of the Philippines – Batanes |
| telephone | 17 | 0 | 17 | null | NULL |
| url | 17 | 0 | 0 | string | https://www.nationalmuseum.gov.ph/nmp-cebu-2/ |

### `osm-education-facilities`

- Declared schema version: `not recorded`
- Stored source records: 52839
- Distinct source-record keys: 52839
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| addr_city | 52839 | 0 | 30963 | null, string | Aborlan |
| addr_full | 52839 | 0 | 52836 | null, string | 127 Binangonan St. Barangay 27 Zone 3 District 2, Caloocan City |
| adm0_name | 52839 | 0 | 0 | string | Philippines |
| adm0_pcode | 52839 | 0 | 0 | string | PHL |
| adm1_name | 52839 | 0 | 249 | null, string | Bangsamoro Autonomous Region In Muslim Mindanao (BARMM) |
| adm1_pcode | 52839 | 0 | 249 | null, string | PH01 |
| adm2_name | 52839 | 0 | 249 | null, string | Abra |
| adm2_pcode | 52839 | 0 | 249 | null, string | PH01028 |
| adm3_name | 52839 | 0 | 249 | null, string | Aborlan |
| adm3_pcode | 52839 | 0 | 249 | null, string | PH0102801 |
| adm4_name | 52839 | 0 | 249 | null, string | Abaca |
| adm4_pcode | 52839 | 0 | 249 | null, string | PH0102801001 |
| amenity | 52839 | 0 | 3835 | null, string | bar |
| bbox | 52839 | 0 | 0 | object | {"xmax": 114.2869437, "xmin": 114.2864708, "ymax": 11.0531904, "ymin": 11.0529407} |
| _bbox_center_latitude | 52839 | 0 | 0 | number | 10.00009865 |
| _bbox_center_longitude | 52839 | 0 | 0 | number | 114.28670725 |
| building | 52839 | 0 | 48152 | null, string | civic |
| capacity_persons | 52839 | 0 | 52306 | null, string | 100-250 |
| id | 52839 | 0 | 0 | string | node/1000830749 |
| name | 52839 | 0 | 14 | null, string | 0-2 |
| name_en | 52839 | 0 | 50797 | null, string | Abantas |
| name_fil | 52839 | 0 | 52802 | null, string | Colegio de San Juan de Letran Manaoag |
| name_latin | 52839 | 0 | 0 | string | 0-2 |
| operator_type | 52839 | 0 | 10701 | null, string | autonomous_regional_government |
| source | 52839 | 0 | 52839 | null | NULL |
| _source_row | 52839 | 0 | 0 | number | 1 |

### `osm-health-facilities`

- Declared schema version: `not recorded`
- Stored source records: 17421
- Distinct source-record keys: 17421
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| addr_city | 17421 | 0 | 12835 | null, string | Abuyog |
| addr_full | 17421 | 0 | 17293 | null, string | 1017 J.P. Rizal St., cor. Magestic St. Megabuck Bldg. Brgy. Concepcion 1, Marikina |
| adm0_name | 17421 | 0 | 0 | string | Philippines |
| adm0_pcode | 17421 | 0 | 0 | string | PHL |
| adm1_name | 17421 | 0 | 8 | null, string | Bangsamoro Autonomous Region In Muslim Mindanao (BARMM) |
| adm1_pcode | 17421 | 0 | 8 | null, string | PH01 |
| adm2_name | 17421 | 0 | 8 | null, string | Abra |
| adm2_pcode | 17421 | 0 | 8 | null, string | PH01028 |
| adm3_name | 17421 | 0 | 8 | null, string | Aborlan |
| adm3_pcode | 17421 | 0 | 8 | null, string | PH0102802 |
| adm4_name | 17421 | 0 | 8 | null, string | Abaca |
| adm4_pcode | 17421 | 0 | 8 | null, string | PH0102802013 |
| amenity | 17421 | 0 | 1796 | null, string | birthing_centre |
| bbox | 17421 | 0 | 0 | object | {"xmax": 117.4350945, "xmin": 117.4349333, "ymax": 8.5292791, "ymin": 8.5289924} |
| _bbox_center_latitude | 17421 | 0 | 0 | number | 10.004560999999999 |
| _bbox_center_longitude | 17421 | 0 | 0 | number | 117.4350139 |
| building | 17421 | 0 | 13800 | null, string | Botique |
| capacity_persons | 17421 | 0 | 16537 | null, string | 100 |
| healthcare | 17421 | 0 | 5050 | null, string | alternative |
| healthcare_speciality | 17421 | 0 | 15222 | null, string | acupuncture |
| id | 17421 | 0 | 0 | string | node/10002525238 |
| name | 17421 | 0 | 11 | null, string | 1 |
| name_en | 17421 | 0 | 16878 | null, string | 5th drugstore |
| name_fil | 17421 | 0 | 17418 | null, string | Bahay Pamahalaan ng Barangay Wawa |
| name_latin | 17421 | 0 | 0 | string | 1 |
| operator_type | 17421 | 0 | 14316 | null, string | autonomous_regional_government |
| source | 17421 | 0 | 17421 | null | NULL |
| _source_row | 17421 | 0 | 0 | number | 10 |

### `philhealth-abpp`

- Declared schema version: `not recorded`
- Stored source records: 1670
- Distinct source-record keys: 1670
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 1670 | 0 | 44 | null, string | 09zdsbayogrhu@gmail.com |
| expire_date | 1670 | 0 | 0 | string | 10/10/2026 |
| municipality | 1670 | 0 | 0 | string | ABUYOG |
| name_of_health_facility | 1670 | 0 | 0 | string | 1HEALTH INTERNATIONAL ANIMAL BITE CENTER |
| _page | 1670 | 0 | 0 | number | 1 |
| _row | 1670 | 0 | 0 | number | 10 |
| sec | 1670 | 0 | 0 | string | G |
| street | 1670 | 0 | 0 | string | 005 BUNSURAN 1, |
| tel_no | 1670 | 0 | 36 | null, string | 0033-3115046 |

### `philhealth-accredited-providers`

No source records are stored for this dataset, so no original schema can be reported.

### `philhealth-ambu`

- Declared schema version: `not recorded`
- Stored source records: 104
- Distinct source-record keys: 104
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 104 | 0 | 1 | null, string | 09zdsbayogrhu@gmail.com |
| expire_date | 104 | 0 | 0 | string | 12/31/2026 |
| municipality | 104 | 0 | 0 | string | APARRI |
| name_of_health_facility | 104 | 0 | 0 | string | ABRA PROVINCIAL HOSPITAL |
| _page | 104 | 0 | 0 | number | 1 |
| _row | 104 | 0 | 0 | number | 10 |
| sec | 104 | 0 | 0 | string | G |
| street | 104 | 0 | 0 | string | 1232 JUANING ST., 471, 1ST DISTRICT, |
| tel_no | 104 | 0 | 1 | null, string | (02)8553-8185/0917-183-7375 |

### `philhealth-asc`

- Declared schema version: `not recorded`
- Stored source records: 281
- Distinct source-record keys: 281
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 281 | 0 | 0 | string | acuvisioneyecenter.manager@gmail.co m |
| expire_date | 281 | 0 | 0 | string | 12/31/2026 |
| municipality | 281 | 0 | 0 | string | ABULUG |
| name_of_health_facility | 281 | 0 | 0 | string | 1FB HEALTH |
| _page | 281 | 0 | 0 | number | 1 |
| _row | 281 | 0 | 0 | number | 10 |
| sec | 281 | 0 | 0 | string | G |
| street | 281 | 0 | 0 | string | 008 M.H. DEL PILAR, POBLACION NORTE, |
| tel_no | 281 | 0 | 1 | null, string | 01978936091 |

### `philhealth-cancerscreening`

- Declared schema version: `not recorded`
- Stored source records: 415
- Distinct source-record keys: 415
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| alphafeto_protein | 415 | 0 | 93 | null, string | ✓ |
| breast_utz | 415 | 0 | 25 | null, string | ✓ |
| colonosc_opy | 415 | 0 | 176 | null, string | ✓ |
| email | 415 | 0 | 0 | string | acctg.philhealth@chmci.net |
| expire_date | 415 | 0 | 0 | string | 12/31/2026 |
| liver_utz | 415 | 0 | 16 | null, string | ✓ |
| low_dose_chest_ctscan | 415 | 0 | 120 | null, string | ✓ |
| mammo | 415 | 0 | 216 | null, string | ✓ |
| municipality | 415 | 0 | 0 | string | ABUYOG |
| name_of_health_facility | 415 | 0 | 0 | string | AC SACRED HEART MEDICAL CENTER |
| _page | 415 | 0 | 0 | number | 1 |
| _row | 415 | 0 | 0 | number | 10 |
| sec | 415 | 0 | 0 | string | G |
| street | 415 | 0 | 0 | string | 001 SAN AGUSTIN ST. COR CARUNCHO AVE, PINAGBUHATAN, |
| tel_no | 415 | 0 | 0 | string | (02) 478-5209/049-801-0182 |

### `philhealth-chibp`

- Declared schema version: `not recorded`
- Stored source records: 11
- Distinct source-record keys: 11
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 11 | 0 | 0 | string | apaciblememorialdistricthospital@yaho o.com |
| expire_date | 11 | 0 | 0 | string | 12/31/2026 |
| municipality | 11 | 0 | 0 | string | BAGUIO CITY |
| name_of_health_facility | 11 | 0 | 0 | string | APACIBLE MEMORIAL DISTRICT HOSPITAL |
| _page | 11 | 0 | 0 | number | 1 |
| _row | 11 | 0 | 0 | number | 12 |
| sec | 11 | 0 | 0 | string | G |
| street | 11 | 0 | 0 | string | 118 E. QUIRINO AVE., |
| tel_no | 11 | 0 | 0 | string | (032) 253-9891-99 |

### `philhealth-ciu`

- Declared schema version: `not recorded`
- Stored source records: 2
- Distinct source-record keys: 2
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 2 | 0 | 0 | string | crmc_12@yahoo.com |
| expire_date | 2 | 0 | 0 | string | 12/31/2026 |
| municipality | 2 | 0 | 0 | string | COTABATO CITY |
| name_of_health_facility | 2 | 0 | 0 | string | COTABATO REGIONAL AND MEDICAL CENTER COMMUNITY ISOLATION UNIT |
| _page | 2 | 0 | 0 | number | 1 |
| _row | 2 | 0 | 0 | number | 4 |
| sec | 2 | 0 | 0 | string | G |
| street | 2 | 0 | 0 | string | OLD KAPATAGAN PROVINCIAL HOSPITAL BUILDING, POB. |
| tel_no | 2 | 0 | 0 | string | (063) 227-9522/09177177223 |

### `philhealth-covidlab`

- Declared schema version: `not recorded`
- Stored source records: 105
- Distinct source-record keys: 105
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 105 | 0 | 0 | string | adas@phc.gov.ph/director@phc.gov. ph |
| expire_date | 105 | 0 | 0 | string | 12/31/2026 |
| municipality | 105 | 0 | 0 | string | ANTIPOLO |
| name_of_health_facility | 105 | 0 | 0 | string | AMANG RODRIGUEZ MEMORIAL MEDICAL CENTER |
| _page | 105 | 0 | 0 | number | 1 |
| _row | 105 | 0 | 0 | number | 10 |
| sec | 105 | 0 | 0 | string | G |
| street | 105 | 0 | 0 | string | 100 D. TUAZON ST. BRGY. LOURDES STA. MESA HEIGHTS |
| tel_no | 105 | 0 | 0 | string | (032) 233-8620 local 317 |

### `philhealth-ctf`

- Declared schema version: `not recorded`
- Stored source records: 16
- Distinct source-record keys: 16
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 16 | 0 | 0 | string | admin.mci@medicus.com.ph |
| expire_date | 16 | 0 | 0 | string | 12/31/2026 |
| municipality | 16 | 0 | 0 | string | BAGUIO CITY |
| name_of_health_facility | 16 | 0 | 0 | string | BATAAN DIABETES, THYROID AND ENDOCRINE SPECIALIST INC. |
| _page | 16 | 0 | 0 | number | 1 |
| _row | 16 | 0 | 0 | number | 11 |
| sec | 16 | 0 | 0 | string | G |
| street | 16 | 0 | 0 | string | 22 EAST AVE., BRGY. PINYAHAN, DILIMAN |
| tel_no | 16 | 0 | 0 | string | 028-681 1647 |

### `philhealth-datrc`

- Declared schema version: `not recorded`
- Stored source records: 24
- Distinct source-record keys: 24
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 24 | 0 | 0 | string | boh.rehab@gmail.com |
| expire_date | 24 | 0 | 0 | string | 12/31/2026 |
| municipality | 24 | 0 | 0 | string | ALABEL |
| name_of_health_facility | 24 | 0 | 0 | string | BALAI BANYUHAY: VALENZUELA CITY TREATMENT AND REHABILITATION CENTER FOR DRUG DEPENDENTS |
| _page | 24 | 0 | 0 | number | 1 |
| _row | 24 | 0 | 0 | number | 11 |
| sec | 24 | 0 | 0 | string | G |
| street | 24 | 0 | 0 | string | 364 AGUIRRE AVENUE, BF HOMES |
| tel_no | 24 | 0 | 0 | string | (032) 3494860 |

### `philhealth-dental`

- Declared schema version: `not recorded`
- Stored source records: 687
- Distinct source-record keys: 687
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 687 | 0 | 40 | null, string | 0917-8706177 |
| expire_date | 687 | 0 | 0 | string | 12/31/2026 |
| municipality | 687 | 0 | 0 | string | AGOO |
| name_of_health_facility | 687 | 0 | 0 | string | 1303RD PAF DENTAL DISPENSARY |
| _page | 687 | 0 | 0 | number | 1 |
| _row | 687 | 0 | 0 | number | 10 |
| sec | 687 | 0 | 0 | string | G |
| street | 687 | 0 | 2 | null, string | 024 FIRE TREE STREET POBLACION |
| tel_no | 687 | 0 | 53 | null, string | (02) 53101325 |

### `philhealth-dots`

- Declared schema version: `not recorded`
- Stored source records: 2097
- Distinct source-record keys: 2097
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 2097 | 0 | 52 | null, string | 01isurcervantesrhu@gmail.com |
| expire_date | 2097 | 0 | 0 | string | 10/10/2026 |
| municipality | 2097 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 2097 | 0 | 0 | string | ABORLAN MEDICARE HOSPITAL |
| _page | 2097 | 0 | 0 | number | 1 |
| _row | 2097 | 0 | 0 | number | 10 |
| sec | 2097 | 0 | 0 | string | G |
| street | 2097 | 0 | 0 | string | 004 POBLACION |
| tel_no | 2097 | 0 | 46 | null, string | 02-7118-4392/09618240861 |

### `philhealth-emcb-ante`

No source records are currently stored; the release is withdrawn and blocked. The retained PDF's provider pages were observed with columns `NAME OF HEALTH FACILITY`, `CAT`, `TEL_NO`, `EMAIL`, `STREET`, and `MUNICIPALITY`; pages 121-240 carry the aligned `EXPIRE DATE` and `SEC` annex. The corrected parser reads 3,221 provider rows. See reports 02 and 04 for the withdrawal record.

### `philhealth-emcb-lab`

- Declared schema version: `not recorded`
- Stored source records: 222
- Distinct source-record keys: 222
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 222 | 0 | 1 | null, string | abpisamama@gmail.com |
| expire_date | 222 | 0 | 0 | string | 12/31/2026 |
| municipality | 222 | 0 | 0 | string | ALCALA |
| name_of_health_facility | 222 | 0 | 0 | string | ABPI-SAMAMA MEDICAL LYING-IN CLINIC AND HOSPITAL |
| _page | 222 | 0 | 0 | number | 1 |
| _row | 222 | 0 | 0 | number | 10 |
| sec | 222 | 0 | 0 | string | G |
| street | 222 | 0 | 1 | null, string | 0038 R1 A. MABINI ST., PUROK 3, BRGY. MOJON, |
| tel_no | 222 | 0 | 1 | null, string | (032) 233-8620 local 317 |

### `philhealth-emcb-ppartum`

- Declared schema version: `not recorded`
- Stored source records: 3222
- Distinct source-record keys: 3222
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 3222 | 0 | 62 | null, string | 01isurcervantesrhu@gmail.com |
| expire_date | 3222 | 0 | 0 | string | 12/23/2026 |
| municipality | 3222 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 3222 | 0 | 0 | string | 1ST TOUCH LYING-IN CLINIC |
| _page | 3222 | 0 | 0 | number | 1 |
| _row | 3222 | 0 | 0 | number | 10 |
| sec | 3222 | 0 | 0 | string | G |
| street | 3222 | 0 | 1 | null, string | 0001 BIGNAY - PUNTURIN BYPASS RD. CORNER P. FAUSTINO ST., PUNTURIN |
| tel_no | 3222 | 0 | 33 | null, string | 0093-275 8636 |

### `philhealth-emcb-putz`

- Declared schema version: `not recorded`
- Stored source records: 92
- Distinct source-record keys: 92
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 92 | 0 | 1 | null, string | acegrumo@gmail.com |
| expire_date | 92 | 0 | 0 | string | 12/31/2026 |
| municipality | 92 | 0 | 0 | string | ALFONSO |
| name_of_health_facility | 92 | 0 | 0 | string | 24/7 LYING-IN MATERNITY AND SPECIALTY CLINICS |
| _page | 92 | 0 | 0 | number | 1 |
| _row | 92 | 0 | 0 | number | 10 |
| sec | 92 | 0 | 0 | string | G |
| street | 92 | 0 | 0 | string | 0038 R1 A. MABINI ST., PUROK 3, BRGY. MOJON, |
| tel_no | 92 | 0 | 0 | string | (032) 233-8620 local 317 |

### `philhealth-emcb-tvu`

- Declared schema version: `not recorded`
- Stored source records: 90
- Distinct source-record keys: 90
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 90 | 0 | 1 | null, string | acegrumo@gmail.com |
| expire_date | 90 | 0 | 0 | string | 12/31/2026 |
| municipality | 90 | 0 | 0 | string | ALFONSO |
| name_of_health_facility | 90 | 0 | 0 | string | 24/7 LYING-IN MATERNITY AND SPECIALTY CLINICS |
| _page | 90 | 0 | 0 | number | 1 |
| _row | 90 | 0 | 0 | number | 10 |
| sec | 90 | 0 | 0 | string | G |
| street | 90 | 0 | 0 | string | 0038 R1 A. MABINI ST., PUROK 3, BRGY. MOJON, |
| tel_no | 90 | 0 | 0 | string | (032) 233-8620 local 317 |

### `philhealth-fdc`

- Declared schema version: `not recorded`
- Stored source records: 1012
- Distinct source-record keys: 1012
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 1012 | 0 | 23 | null, string | 5400rhdcc@gmail.com |
| expire_date | 1012 | 0 | 0 | string | 12/31/2026 |
| municipality | 1012 | 0 | 0 | string | ABUCAY |
| name_of_health_facility | 1012 | 0 | 0 | string | 88LIFESTREAM MEDICAL DIALYSIS CENTER GUIGUINTO, INC. |
| _ordinal | 1012 | 0 | 0 | number | 1 |
| _page | 1012 | 0 | 0 | number | 1 |
| _row | 1012 | 0 | 0 | number | 10 |
| sec | 1012 | 0 | 0 | string | G |
| street | 1012 | 0 | 0 | string | 0027 SHAW BLVD. COR. SAINT JOSE MARIA ESCRIVA DRIVE, SAN ANTONIO DISTRICT 1, |
| tel_no | 1012 | 0 | 24 | null, string | 02-4879433/ 0960-8133595 |

### `philhealth-fp`

- Declared schema version: `not recorded`
- Stored source records: 1465
- Distinct source-record keys: 1465
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 1465 | 0 | 15 | null, string | 09sosmenarhu@gmail.com |
| expire_date | 1465 | 0 | 0 | string | 11/17/2026 |
| municipality | 1465 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 1465 | 0 | 0 | string | 3 KINGS BIRTHING HOME |
| _page | 1465 | 0 | 0 | number | 1 |
| _row | 1465 | 0 | 0 | number | 10 |
| sec | 1465 | 0 | 0 | string | G |
| street | 1465 | 0 | 0 | string | 0018 VIOLETA HOMES SUBD., SAOG, |
| tel_no | 1465 | 0 | 19 | null, string | 02-53101336 |

### `philhealth-gamot`

- Declared schema version: `not recorded`
- Stored source records: 3483
- Distinct source-record keys: 3483
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 3483 | 0 | 56 | null, string | 09sosmenarhu@gmail.com |
| expire_date | 3483 | 0 | 0 | string | 10/10/2027 |
| municipality | 3483 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 3483 | 0 | 0 | string | 1421 MEDICAL SERVICES |
| _ordinal | 3483 | 0 | 0 | number | 1 |
| _page | 3483 | 0 | 0 | number | 1 |
| _row | 3483 | 0 | 0 | number | 10 |
| sec | 3483 | 0 | 0 | string | G |
| street | 3483 | 0 | 5 | null, string | 001 CAMERINO DRV BITANGAN ST. |
| tel_no | 3483 | 0 | 47 | null, string | 00-828-4445 |

### `philhealth-hosp`

- Declared schema version: `not recorded`
- Stored source records: 1934
- Distinct source-record keys: 1934
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| beds | 1934 | 0 | 0 | string | 0 |
| cat | 1934 | 0 | 0 | string | INF/DISP |
| email | 1934 | 0 | 1 | null, string | 2014.jmvch@gmail.com |
| expire_date | 1934 | 0 | 0 | string | 12/26/2026 |
| municipality | 1934 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 1934 | 0 | 0 | string | 10TH STATION HOSPITAL (10TH SH) FORMERLY: CAMP GENERAL MANUEL T. YAN SR. STATION HOSPITAL |
| _ordinal | 1934 | 0 | 0 | number | 1 |
| _page | 1934 | 0 | 0 | number | 1 |
| _row | 1934 | 0 | 0 | number | 10 |
| sec | 1934 | 0 | 0 | string | G |
| street | 1934 | 0 | 3 | null, string | 001 MAYO ST., POBLACION II |
| tel_no | 1934 | 0 | 8 | null, string | (02) 478-5209/049-801-0182 |

### `philhealth-mcc`

- Declared schema version: `not recorded`
- Stored source records: 3140
- Distinct source-record keys: 3140
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 3140 | 0 | 64 | null, string | 01isurcervantesrhu@gmail.com |
| expire_date | 3140 | 0 | 0 | string | 12/23/2026 |
| municipality | 3140 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 3140 | 0 | 0 | string | 1ST TOUCH LYING-IN CLINIC |
| _page | 3140 | 0 | 0 | number | 1 |
| _row | 3140 | 0 | 0 | number | 10 |
| sec | 3140 | 0 | 0 | string | G |
| street | 3140 | 0 | 0 | string | 0001 BIGNAY - PUNTURIN BYPASS RD. CORNER P. FAUSTINO ST., PUNTURIN |
| tel_no | 3140 | 0 | 33 | null, string | 0093-275 8636 |

### `philhealth-mcp`

No source records are stored for this dataset, so no original schema can be reported.

### `philhealth-ohat`

- Declared schema version: `not recorded`
- Stored source records: 342
- Distinct source-record keys: 342
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 342 | 0 | 2 | null, string | achievewellness.ph@gmail.com |
| expire_date | 342 | 0 | 0 | string | 12/31/2026 |
| municipality | 342 | 0 | 0 | string | ABUYOG |
| name_of_health_facility | 342 | 0 | 0 | string | ABOUT US PH CO. |
| _page | 342 | 0 | 0 | number | 1 |
| _row | 342 | 0 | 0 | number | 10 |
| sec | 342 | 0 | 0 | string | G |
| street | 342 | 0 | 1 | null, string | 097 3/F ROOM # 2, VENCER BLDG., NATIONAL HIGHWAY, |
| tel_no | 342 | 0 | 3 | null, string | 02-83643219 |

### `philhealth-omp`

- Declared schema version: `not recorded`
- Stored source records: 100
- Distinct source-record keys: 100
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 100 | 0 | 6 | null, string | abucay_rhu@yahoo.com |
| expire_date | 100 | 0 | 0 | string | 12/31/2026 |
| municipality | 100 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 100 | 0 | 0 | string | ABORLAN MUNICIPAL HEALTH OFFICE |
| _page | 100 | 0 | 0 | number | 1 |
| _row | 100 | 0 | 0 | number | 10 |
| sec | 100 | 0 | 0 | string | G |
| street | 100 | 0 | 1 | null, string | 290 DELICONA ST., DAGOCDOC, |
| tel_no | 100 | 0 | 2 | null, string | 03605650276 |

### `philhealth-opto`

- Declared schema version: `not recorded`
- Stored source records: 125
- Distinct source-record keys: 125
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 125 | 0 | 6 | null, string | abarintosvisioncenter@gmail.com |
| expire_date | 125 | 0 | 0 | string | 10/18/2027 |
| municipality | 125 | 0 | 0 | string | ALFONSO |
| name_of_health_facility | 125 | 0 | 0 | string | 168 PINEDA SICAT OPTICAL CLINIC |
| _page | 125 | 0 | 0 | number | 1 |
| _row | 125 | 0 | 0 | number | 10 |
| sec | 125 | 0 | 0 | string | G |
| street | 125 | 0 | 0 | string | 0093E ROXAS AVE. COR. BADELLES ST. |
| tel_no | 125 | 0 | 3 | null, string | (02) 84226-8888 |

### `philhealth-sam`

- Declared schema version: `not recorded`
- Stored source records: 209
- Distinct source-record keys: 209
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 209 | 0 | 1 | null, string | 09sosmenarhu@gmail.com |
| expire_date | 209 | 0 | 0 | string | 12/31/2026 |
| municipality | 209 | 0 | 0 | string | ABRA DEL ILOG |
| name_of_health_facility | 209 | 0 | 0 | string | ALABAT RHU TB IDOTS FACILITY |
| _page | 209 | 0 | 0 | number | 1 |
| _row | 209 | 0 | 0 | number | 10 |
| sec | 209 | 0 | 0 | string | G |
| street | 209 | 0 | 2 | null, string | 1258 WETSBANK ROAD, COR. JAVIER BRIDGE FLOODWAY |
| tel_no | 209 | 0 | 5 | null, string | (032) 253-9891-99 |

### `philhealth-yakap`

- Declared schema version: `not recorded`
- Stored source records: 4138
- Distinct source-record keys: 4138
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| email | 4138 | 0 | 110 | null, string | 01isurcervantesrhu@gmail.com |
| expire_date | 4138 | 0 | 0 | string | 10/1/2026 |
| municipality | 4138 | 0 | 0 | string | ABORLAN |
| name_of_health_facility | 4138 | 0 | 0 | string | 178 B HEALTH CENTER |
| _ordinal | 4138 | 0 | 0 | number | 1 |
| _page | 4138 | 0 | 0 | number | 1 |
| _row | 4138 | 0 | 0 | number | 10 |
| sec | 4138 | 0 | 0 | string | G |
| street | 4138 | 0 | 8 | null, string | 001 MAYO ST. POB. II TIAONG, QUEZON |
| tel_no | 4138 | 0 | 134 | null, string | 004 795 1622 |

### `phlpost-post-office-locator`

- Declared schema version: `not recorded`
- Stored source records: 2544
- Distinct source-record keys: 1272
- Duplicate source-record keys: 1272
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| Addresss | 2544 | 0 | 0 | string | 001 Valbuena, Pinili, Ilocos Norte |
| Post Offices | 2544 | 0 | 0 | string | Aborlan Post Office |
| Provinces | 2544 | 0 | 0 | string | Abra |
| _row | 2544 | 0 | 0 | string | 10 |
| Services | 2544 | 0 | 0 | string | Acceptance |

### `ppa-port-list`

- Declared schema version: `not recorded`
- Stored source records: 574
- Distinct source-record keys: 574
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| group | 574 | 0 | 0 | string | BASEPORT |
| name | 574 | 0 | 0 | string | 1590 EC-Pier (Bauang Private Power Corp. (BPPC)) |
| non_roro | 574 | 0 | 284 | boolean, null | true |
| _ordinal | 574 | 0 | 0 | number | 1 |
| page | 574 | 0 | 0 | number | 1 |
| pmo_code | 574 | 0 | 0 | string | AGS |
| pmo_name | 574 | 0 | 0 | string | AGUSAN |
| region | 574 | 0 | 0 | string | MANILA_NORTHERN_LUZON |
| remarks | 574 | 0 | 574 | null | NULL |
| roro | 574 | 0 | 498 | boolean, null | true |
| row_reference | 574 | 0 | 0 | string | pdf:page:10:row:1 |
| source_number | 574 | 0 | 0 | string | 1 |
| source_record_key | 574 | 0 | 0 | string | PPA:AGS:BASEPORT:NASIPIT |
| unregistered | 574 | 0 | 0 | boolean | false |

### `psa-census-2024-population`

- Declared schema version: `not recorded`
- Stored source records: 134748
- Distinct source-record keys: 134748
- Duplicate source-record keys: 0
- Blank source-record keys: 0

| Original key | Present | Missing | Null/blank | JSON types | Sample value |
|---|---|---|---|---|---|
| codes | 134748 | 0 | 0 | array | ["0100000000", "0"] |
| dataset_id | 134748 | 0 | 0 | string | 182e14eaaa4fa5ba5ac5 |
| dataset_title | 134748 | 0 | 0 | string | Total Population, Household Population, and Number of Households by Province, City, Municipality, and Barangay as of 01 July 2024 : Bangsamoro Autonomous Region In Muslim Mindanao (BARMM) |
| dimensions | 134748 | 0 | 0 | array | ["Geographic Location", "Parameter"] |
| labels | 134748 | 0 | 0 | array | ["........50th District", "Household Population"] |
| psa_source_url | 134748 | 0 | 0 | string | https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__1A__PO_2024/0011A6DTPH0.px |
| release | 134748 | 0 | 0 | string | 2026-08-12T09-17-53-06df6099e3f1 |
| status | 134748 | 0 | 134748 | string |  |
| value | 134748 | 0 | 0 | number | 0 |

### `psgc-bettergov-q2-2024`

No source records are stored for this dataset, so no original schema can be reported.

### `psgc-official`

No source records are stored for this dataset, so no original schema can be reported.

### `tesda-tvi-directory`

No source records are stored for this dataset, so no original schema can be reported.

