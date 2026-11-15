# 07 — Real API Examples

**Captured:** 2026-11-15T08:25:53.744762+00:00  
**API:** `http://127.0.0.1:8010`  
**Source of truth:** a live response from the running PhilFacilities API.

This report is a point-in-time snapshot. It does not claim nationwide coverage, completeness, or a legal review. Counts come from the response body, which only includes records that passed the publication gate. Current publication policy is in [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](../14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md); a captured example may predate a registry decision or a re-ingestion.

## Service health

HTTP `200`

```json
{
  "status": "ok",
  "service": "philfacilities-api",
  "version": "0.1.0",
  "database": "ok",
  "environment": "local"
}
```

### Published statistics

```http
GET /v1/statistics
```

HTTP `200` · `application/json`

Measured over public records only. Synthetic counts, if any, are labelled by the API.

```json
{
  "as_of": "2026-11-15T08:25:57.182884Z",
  "by_precision": {
    "map_geocoded": 70223
  },
  "by_region": [
    {
      "facility_count": 14216,
      "region_code_prefix": null,
      "region_name": null
    },
    {
      "facility_count": 7749,
      "region_code_prefix": "03",
      "region_name": "Region III (Central Luzon)"
    },
    {
      "facility_count": 7534,
      "region_code_prefix": "04",
      "region_name": "Region IV-A (CALABARZON)"
    },
    {
      "facility_count": 5434,
      "region_code_prefix": "08",
      "region_name": "Region VIII (Eastern Visayas)"
    },
    {
      "facility_count": 4874,
      "region_code_prefix": "05",
      "region_name": "Region V (Bicol Region)"
    },
    {
      "facility_count": 4327,
      "region_code_prefix": "01",
      "region_name": "Region I (Ilocos Region)"
    },
    {
      "facility_count": 3358,
      "region_code_prefix": "06",
      "region_name": "Region VI (Western Visayas)"
    },
    {
      "facility_count": 3267,
      "region_code_prefix": "02",
      "region_name": "Region II (Cagayan Valley)"
    },
    {
      "facility_count": 2644,
      "region_code_prefix": "17",
      "region_name": "MIMAROPA Region"
    },
    {
      "facility_count": 2540,
      "region_code_prefix": "07",
      "region_name": "Region VII (Central Visayas)"
    },
    {
      "facility_count": 2379,
      "region_code_prefix": "12",
      "region_name": "Region XII (SOCCSKSARGEN)"
    },
    {
      "facility_count": 2312,
      "region_code_prefix": "10",
      "region_name": "Region X (Northern Mindanao)"
    },
    {
      "facility_count": 2253,
      "region_code_prefix": "16",
      "region_name": "Region XIII (Caraga)"
    },
    {
      "facility_count": 2250,
      "region_code_prefix": "11",
      "region_name": "Region XI (Davao Region)"
    },
    {
      "facility_count": 2131,
      "region_code_prefix": "14",
      "region_name": "Cordillera Administrative Region (CAR)"
    },
    {
      "facility_count": 1805,
      "region_code_prefix": "09",
      "region_name": "Region IX (Zamboanga Peninsula)"
    },
    {
      "facility_count": 1150,
      "region_code_prefix": "19",
      "region_name": "Bangsamoro Autonomous Region In Muslim Mindanao (BARMM)"
    }
  ],
  "caveats": [
    "Statistics describe published PhilFacilities records only."
  ],
  "facilities_total": 83769,
  "health_facilities": 30956,
  "published_facilities": 83769,
  "schools": 52813,
  "source_releases": 47,
  "synthetic": 0,
  "with_coordinates": 70223
}
```

### 2024 Census population observations

```http
GET /v1/population?limit=5
```

HTTP `200` · `application/json`

Saved PSA OpenSTAT snapshots mirrored by BetterGov.PH. Values are statistical counts, not facility capacity; missing values remain null.

```json
{
  "items": [
    {
      "id": "8d535154-c984-4dea-a2af-beb22e617715",
      "psgc_code": "1004210051",
      "geographic_level": "barangay",
      "geographic_name": "50th District",
      "indicator_code": "1",
      "indicator_label": "Household Population",
      "value": 558.0,
      "unit": "persons",
      "reference_date": "2024-07-01",
      "reference_period": "2024 Census of Population; reference date 01 July 2024",
      "dimensions": {
        "Parameter": "Household Population",
        "Geographic Location": "50th District"
      },
      "source_url": "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__1A__PO_2024/0101A6DTPH9.px",
      "source_updated_at": "2026-08-12T09:17:54Z",
      "retrieved_at": "2026-09-09T18:49:26.441000Z",
      "release_id": "8be1752e-ade9-42d9-a294-3c586058e82b",
      "release_label": "PSA-2024-CENSUS-Region-X-Northern-Mindanao-2024-07-01",
      "dataset_slug": "psa-census-2024-population",
      "attribution_text": "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source"
    },
    {
      "id": "49704e94-3d3e-4a48-8e4b-7d2f6c3d7566",
      "psgc_code": "1004210051",
      "geographic_level": "barangay",
      "geographic_name": "50th District",
      "indicator_code": "2",
      "indicator_label": "Number of Households",
      "value": 139.0,
      "unit": "households",
      "reference_date": "2024-07-01",
      "reference_period": "2024 Census of Population; reference date 01 July 2024",
      "dimensions": {
        "Parameter": "Number of Households",
        "Geographic Location": "50th District"
      },
      "source_url": "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__1A__PO_2024/0101A6DTPH9.px",
      "source_updated_at": "2026-08-12T09:17:54Z",
      "retrieved_at": "2026-09-09T18:49:26.441000Z",
      "release_id": "8be1752e-ade9-42d9-a294-3c586058e82b",
      "release_label": "PSA-2024-CENSUS-Region-X-Northern-Mindanao-2024-07-01",
      "dataset_slug": "psa-census-2024-population",
      "attribution_text": "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source"
    },
    {
      "id": "0cb066e5-93c3-4e3e-9502-486b842bc271",
      "psgc_code": "1004210051",
      "geographic_level": "barangay",
      "geographic_name": "50th District",
      "indicator_code": "0",
      "indicator_label": "Total Population",
      "value": 581.0,
      "unit": "persons",
      "reference_date": "2024-07-01",
      "reference_period": "2024 Census of Population; reference date 01 July 2024",
      "dimensions": {
        "Parameter": "Total Population",
        "Geographic Location": "50th District"
      },
      "source_url": "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__1A__PO_2024/0101A6DTPH9.px",
      "source_updated_at": "2026-08-12T09:17:54Z",
      "retrieved_at": "2026-09-09T18:49:26.441000Z",
      "release_id": "8be1752e-ade9-42d9-a294-3c586058e82b",
      "release_label": "PSA-2024-CENSUS-Region-X-Northern-Mindanao-2024-07-01",
      "dataset_slug": "psa-census-2024-population",
      "attribution_text": "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source"
    },
    {
      "id": "334854b0-3dee-4695-9fa7-926a11c8b7cf",
      "psgc_code": "1403201001",
      "geographic_level": "barangay",
      "geographic_name": "Ababa-an",
      "indicator_code": "1",
      "indicator_label": "Household Population",
      "value": 438.0,
      "unit": "persons",
      "reference_date": "2024-07-01",
      "reference_period": "2024 Census of Population; reference date 01 July 2024",
      "dimensions": {
        "Parameter": "Household Population",
        "Geographic Location": "Ababa-an"
      },
      "source_url": "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__1A__PO_2024/0151A6DTHP4.px",
      "source_updated_at": "2026-08-12T09:17:54Z",
      "retrieved_at": "2026-09-09T18:49:31.832000Z",
      "release_id": "f7640033-c60f-4e63-89f6-cb0ed996ccb2",
      "release_label": "PSA-2024-CENSUS-Cordillera-Administrative-Region-CAR-2024-07-01",
      "dataset_slug": "psa-census-2024-population",
      "attribution_text": "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source"
    },
    {
      "id": "ffa9867e-e959-4ed1-b099-f6c104621662",
      "psgc_code": "1403201001",
      "geographic_level": "barangay",
      "geographic_name": "Ababa-an",
      "indicator_code": "2",
      "indicator_label": "Number of Households",
      "value": 83.0,
      "unit": "households",
      "reference_date": "2024-07-01",
      "reference_period": "2024 Census of Population; reference date 01 July 2024",
      "dimensions": {
        "Parameter": "Number of Households",
        "Geographic Location": "Ababa-an"
      },
      "source_url": "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__1A__PO_2024/0151A6DTHP4.px",
      "source_updated_at": "2026-08-12T09:17:54Z",
      "retrieved_at": "2026-09-09T18:49:31.832000Z",
      "release_id": "f7640033-c60f-4e63-89f6-cb0ed996ccb2",
      "release_label": "PSA-2024-CENSUS-Cordillera-Administrative-Region-CAR-2024-07-01",
      "dataset_slug": "psa-census-2024-population",
      "attribution_text": "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source"
    }
  ],
  "total": 134748,
  "limit": 5,
  "offset": 0,
  "caveats": [
    "Values are saved PSA OpenSTAT snapshots mirrored by BetterGov.PH, not live PSA data.",
    "Missing source values remain null; they are never treated as zero.",
    "Counts are persons or households as labelled, not facility capacity or service coverage.",
    "PSA remains the authoritative source; cite the PSA table URL and
… (truncated for this report)
```

## Facility examples

`GET /v1/facilities?limit=3` returned HTTP `200`. The first page is shown in full; no record was selected or edited by hand.

```json
{
  "items": [
    {
      "id": "ffd89b6c-d3c8-47af-a14e-1629b1548efb",
      "slug": "sky-diagnostic-medical-corp-philhealth",
      "display_name": "SKY DIAGNOSTIC MEDICAL CORP.",
      "facility_type": "health_facility",
      "facility_subtype": "Transvaginal Ultrasound",
      "ownership": "unknown",
      "record_status": "active_in_registry",
      "publication_status": "public",
      "is_synthetic": false,
      "location": {
        "latitude": null,
        "longitude": null,
        "precision": "unknown",
        "method": null,
        "address_text": null,
        "psgc_code": null,
        "review_status": null
      },
      "geography": {
        "psgc_code": null,
        "psgc_release": null,
        "region_code": null,
        "region_name": null,
        "province_code": null,
        "province_name": null,
        "municipality_code": null,
        "municipality_name": null,
        "barangay_code": null,
        "barangay_name": null
      },
      "source_count": 4,
      "updated_at": "2026-11-15T08:15:58.794200Z"
    },
    {
      "id": "ffd4c330-340e-4824-9c5d-0b79583b3785",
      "slug": "aguinaldo-municipal-health-office-philhealth",
      "display_name": "AGUINALDO MUNICIPAL HEALTH OFFICE",
      "facility_type": "health_facility",
      "facility_subtype": "Oral Health Benefit Package Providers",
      "ownership": "unknown",
      "record_status": "active_in_registry",
      "publication_status": "public",
      "is_synthetic": false,
      "location": {
        "latitude": null,
        "longitude": null,
        "precision": "unknown",
        "method": null,
        "address_text": null,
        "psgc_code": null,
        "review_status": null
      },
      "geography": {
        "psgc_code": null,
        "psgc_release": null,
        "region_code": null,
        "region_name": null,
        "province_code": null,
        "province_name": null,
        "municipality_code": null,
        "municipality_name": null,
        "barangay_code": null,
        "barangay_name": null
      },
      "source_count": 3,
      "updated_at": "2026-11-15T08:15:58.794200Z"
    },
    {
      "id": "ffceae8a-30a6-4eec-89b1-1134f9ac8487",
      "slug": "city-government-of-taguig-bambang-health-center-philhealth",
      "display_name": "CITY GOVERNMENT OF TAGUIG /BAMBANG HEALTH CENTER",
      "facility_type": "health_facility",
      "facility_subtype": "TB-DOTS Centers",
      "ownership": "unknown",
      "record_status": "active_in_registry",
      "publication_status": "public",
      "is_synthetic": false,
      "location": {
        "latitude": null,
        "longitude": null,
        "precision": "unknown",
        "method": null,
        "address_text": null,
        "psgc_code": null,
        "review_status": null
      },
      "geography": {
        "psgc_code": null,
        "psgc_release": null,
        "region_code": null,
        "region_name": null,
        "province_code": null,
        "province_name": null,
        "municipality_code": null,
        "municipality_name": null,
        "barangay_code": null,
        "barangay_name": null
      },
      "source_count": 2,
      "updated_at": "2026-11-15T08:15:58.794200Z"
    }
  ],
  "next_cursor": "eyJ1cGRhdGVkX2F0IjoiMjAyNi0xMS0xNVQwODoxNTo1OC43OTQyMDArMDA6MDAiLCJpZCI6ImZmY2VhZThhLTMwYTYtNGVlYy04OWIxLTExMzRmOWFjODQ4NyJ9",
  "has_more": true,
  "total": 83769,
  "limit": 3
}
```

### Facility detail — SKY DIAGNOSTIC MEDICAL CORP.

```http
GET /v1/facilities/ffd89b6c-d3c8-47af-a14e-1629b1548efb
```

HTTP `200` · `application/json`

```json
{
  "id": "ffd89b6c-d3c8-47af-a14e-1629b1548efb",
  "slug": "sky-diagnostic-medical-corp-philhealth",
  "display_name": "SKY DIAGNOSTIC MEDICAL CORP.",
  "facility_type": "health_facility",
  "facility_subtype": "Transvaginal Ultrasound",
  "ownership": "unknown",
  "record_status": "active_in_registry",
  "publication_status": "public",
  "is_synthetic": false,
  "location": {
    "latitude": null,
    "longitude": null,
    "precision": "unknown",
    "method": null,
    "address_text": null,
    "psgc_code": null,
    "review_status": null
  },
  "geography": {
    "psgc_code": null,
    "psgc_release": null,
    "region_code": null,
    "region_name": null,
    "province_code": null,
    "province_name": null,
    "municipality_code": null,
    "municipality_name": null,
    "barangay_code": null,
    "barangay_name": null
  },
  "source_count": 4,
  "updated_at": "2026-11-15T08:15:58.794200Z",
  "official_name": "SKY DIAGNOSTIC MEDICAL CORP.",
  "school": null,
  "health": {
    "doh_facility_id": null,
    "facility_category": "Yakap Clinics",
    "service_capability_level": null,
    "bed_capacity": null,
    "source_record_id": "2d8e2610-9954-4457-a1f9-c905dcd6cc55"
  },
  "accreditations": [
    {
      "id": "f0c7000f-f3c7-4547-a062-cb6baf768275",
      "authority": "PhilHealth",
      "provider_category": "Yakap Clinics",
      "benefit_package": "Yakap Clinics",
      "accreditation_category": "Yakap Clinics",
      "bed_count": null,
      "sector_code": "P",
      "source_status": null,
      "valid_from": null,
      "valid_until": "2027-12-31",
      "source_as_of": null,
      "page_reference": "page:25:row:24",
      "source_record_id": "2d8e2610-9954-4457-a1f9-c905dcd6cc55"
    },
    {
      "id": "eb13b52f-a2e8-4cfc-9aec-366d5a86d1e1",
      "authority": "PhilHealth",
      "provider_category": "Pelvic Ultrasound",
      "benefit_package": "Pelvic Ultrasound",
      "accreditation_category": "Pelvic Ultrasound",
      "bed_count": null,
      "sector_code": "P",
      "source_status": null,
      "valid_from": null,
      "valid_until": "2027-12-31",
      "source_as_of": "2026-09-30",
      "page_reference": "page:1:row:11",
      "source_record_id": "acf79b27-b62a-43de-9aba-686f89c1c412"
    },
    {
      "id": "545b6b97-b57a-43e2-9e52-a20d5bba2a3c",
      "authority": "PhilHealth",
      "provider_category": "Clinical Laboratory",
      "benefit_package": "Clinical Laboratory",
      "accreditation_category": "Clinical Laboratory",
      "bed_count": null,
      "sector_code": "P",
      "source_status": null,
      "valid_from": null,
      "valid_until": "2027-12-31",
      "source_as_of": "2026-09-30",
      "page_reference": "page:2:row:7",
      "source_record_id": "e1eb3f20-45cc-4244-a668-fe1c979a2882"
    },
    {
      "id": "f53d8a66-527e-4979-8030-57d3e126e62f",
      "authority": "PhilHealth",
      "provider_category": "Transvaginal Ultrasound",
      "benefit_package": "Transvaginal Ultrasound",
      "accreditation_category": "Transvaginal Ultrasound",
      "bed_count": null,
      "sector_code": "P",
      "source_status": null,
      "valid_from": null,
      "valid_until": "2027-12-31",
      "source_as_of": "2026-09-30",
      "page_reference": "page:1:row:11",
      "source_record_id": "bc72fb49-1cc0-45d5-a0bb-22aa0e32f4ca"
    }
  ],
  "sources": [
    {
      "id": "09ceda25-6fd4-4a80-940f-de194c0ea45e",
      "agency": "Philippine Health Insurance Corporation",
      "agency_code": "philhealth",
      "dataset": "PhilHealth — Yakap Clinics",
      "dataset_slug": "philhealth-yakap",
      "release_id": "8fc88506-f2be-4c5e-9e97-823f051b954d",
      "release_label": "PHILHEALTH-YAKAP-UNDATED",
      "source_record_id": "philhealth:yakap-clinics:sky-diagnostic-medical-corp:baliuag:c03477db97",
      "source_record_uuid": "2d8e2610-9954-4457-a1f9-c905dcd6cc55",
      "row_reference": "page:25:row:24",
      "source_published_at": null,
      "reference_period_start": null,
      "reference_period_end": null,
      "retrieved_at": "2026-11-15T08:08:07.434929Z",
      "processed_at": "2026-11-15T08:10:15.187401Z",
      "match_method": "exact_agency_id",
      "match_status": "automatic_high_confidence",
      "match_confidence": 1.0,
      "rights_status": "approved_with_attribution",
      "publication_status": "published",
      "license_identifier": null,
      "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
      "is_synthetic": false
    },
    {
      "id": "08adc0fd-b6a6-44d8-88b1-7b01cbd3daad",
      "agency": "Philippine Health Insurance Corporation",
      "agency_code": "philhealth",
      "dataset": "PhilHealth — Transvaginal Ultrasound",
      "dataset_slug": "philhealth-emcb-tvu",
      "release_id": "69dff254-e8b0-4de9-84d0-8fd2df525470",
      "release_label": "PHILHEALTH-EMCB-TVU_093026-2026-09-30",
      "source_record_id": "philhealth:transvaginal-ultrasound:sky-diagnostic-medical-corp:baliuag:4f63d1d678",
      "source_record_uuid": "bc72fb49-1cc0-45d5-a0bb-22aa0e32f4ca",
      "row_reference": "page:1:row:11",
      "source_published_at": "2026-09-30T00:00:00Z",
      "reference_period_start": "2026-09-30",
      "reference_period_end": "2026-09-30",
      "retrieved_at": "2026-11-15T04:39:17.137577Z",
      "processed_at": "2026-11-15T04:39:24.749654Z",
      "match_method": "exact_agency_id",
      "match_status": "automatic_high_confidence",
      "match_confidence": 1.0,
      "rights_status": "approved_with_attribution",
      "publication_status": "published",
      "license_identifier": null,
      "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
      "is_synthetic": false
    },
    {
      "id": "6bdaf373-eeaf-4f33-8589-ca4bc733c03e",
      "agency": "Philippine Health Insurance Corporation",
      "agency_code": "philhealth",
      "dataset": "PhilHealth — Clinical Laboratory",
      "dataset_slug": "philhealth-emcb-lab",
      "release_id": "02e534bb-b2a8-4a99-b9b3-853f7203b752",
      "release_label": "PHILHEALTH-EMCB-LAB_093026-2026-09-30",
      "source_record_id": "philhealth:clinical-laboratory:sky-diagnostic-medical-corp:baliuag:67ef3057a2",
      "source_record_uuid": "e1eb3f20-45cc-4244-a668-fe1c979a2882",
      "row_reference": "page:2:row:7",
      "source_published_at": "2026-09-30T00:00:00Z",
      "reference_period_start": "2026-09-30",
      "reference_period_end": "2026-09-30",
      "retrieved_at": "2026-11-15T04:33:44.408816Z",
      "processed_at": "2026-11-15T04:33:55.500370Z",
      "match_method": "exact_agency_id",
      "match_status": "automatic_high_confidence",
      "match_confidence": 1.0,
      "rights_status": "approved_with_attribution",
      "publication_status": "published",
      "license_identifier": null,
      "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
      "is_synthetic": false
    },
    {
      "id": "7cd0f7da-30fc-411d-b328-104dfed5f55c",
      "agency": "Philippine Health Insurance Corporation",
      "agency_code": "philhealth",
      "dataset": "PhilHealth — Pelvic Ultrasound",
      "dataset_slug": "philhealth-emcb-putz",
      "release_id": "1ef24424-b1dd-4a47-a231-c375e0d5cd41",
      "release_label": "PHILHEALTH-EMCB-PUTZ_093026-2026-09-30",
      "source_record_id": "philhealth:pelvic-ultrasound:sky-diagnostic-medical-corp:baliuag:920ca1bc29",
      "source_record_uuid": "acf79b27-b62a-43de-9aba-686f89c1c412",
      "row_reference": "page:1:row:11",
      "source_published_at": "2026-09-30T00:00:00Z",
      "reference_period_start": "2026-09-30",
      "reference_period_end": "2026-09-30",
      "retrieved_at": "2026-11-15T03:31:05.251986Z",
      "processed_at": "2026-11-15T03:31:16.931572Z",
      "match_method": "exact_agency_id",
      "match_status": "automatic_high_confidence",
      "match_confidence": 1.0,
      "rights_status": "approved_with_attribution",
      "publication_status": "published",
      "license_identifier": null,
      "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
      "is_synthetic": false
    }
  ],
  "quality": {
    "identity_status": "source_linked",
    "location_precision": "unknown",
    "warnings": [
      {
        "code": "no_coordinates",
        "severity": "info",
        "message": "No source coordinates were supplied. Location is unknown."
      }
    ],
    "source_count": 4
  },
  "created_at": "2026-11-15T02:27:01.147324Z"
}
```

### Facility source evidence

```http
GET /v1/facilities/ffd89b6c-d3c8-47af-a14e-1629b1548efb/sources
```

HTTP `200` · `application/json`

Evidence is filtered to rights-cleared, published releases. Internal-only sources do not appear.

```json
[
  {
    "id": "09ceda25-6fd4-4a80-940f-de194c0ea45e",
    "agency": "Philippine Health Insurance Corporation",
    "agency_code": "philhealth",
    "dataset": "PhilHealth — Yakap Clinics",
    "dataset_slug": "philhealth-yakap",
    "release_id": "8fc88506-f2be-4c5e-9e97-823f051b954d",
    "release_label": "PHILHEALTH-YAKAP-UNDATED",
    "source_record_id": "philhealth:yakap-clinics:sky-diagnostic-medical-corp:baliuag:c03477db97",
    "source_record_uuid": "2d8e2610-9954-4457-a1f9-c905dcd6cc55",
    "row_reference": "page:25:row:24",
    "source_published_at": null,
    "reference_period_start": null,
    "reference_period_end": null,
    "retrieved_at": "2026-11-15T08:08:07.434929Z",
    "processed_at": "2026-11-15T08:10:15.187401Z",
    "match_method": "exact_agency_id",
    "match_status": "automatic_high_confidence",
    "match_confidence": 1.0,
    "rights_status": "approved_with_attribution",
    "publication_status": "published",
    "license_identifier": null,
    "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
    "is_synthetic": false
  },
  {
    "id": "08adc0fd-b6a6-44d8-88b1-7b01cbd3daad",
    "agency": "Philippine Health Insurance Corporation",
    "agency_code": "philhealth",
    "dataset": "PhilHealth — Transvaginal Ultrasound",
    "dataset_slug": "philhealth-emcb-tvu",
    "release_id": "69dff254-e8b0-4de9-84d0-8fd2df525470",
    "release_label": "PHILHEALTH-EMCB-TVU_093026-2026-09-30",
    "source_record_id": "philhealth:transvaginal-ultrasound:sky-diagnostic-medical-corp:baliuag:4f63d1d678",
    "source_record_uuid": "bc72fb49-1cc0-45d5-a0bb-22aa0e32f4ca",
    "row_reference": "page:1:row:11",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T04:39:17.137577Z",
    "processed_at": "2026-11-15T04:39:24.749654Z",
    "match_method": "exact_agency_id",
    "match_status": "automatic_high_confidence",
    "match_confidence": 1.0,
    "rights_status": "approved_with_attribution",
    "publication_status": "published",
    "license_identifier": null,
    "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
    "is_synthetic": false
  },
  {
    "id": "6bdaf373-eeaf-4f33-8589-ca4bc733c03e",
    "agency": "Philippine Health Insurance Corporation",
    "agency_code": "philhealth",
    "dataset": "PhilHealth — Clinical Laboratory",
    "dataset_slug": "philhealth-emcb-lab",
    "release_id": "02e534bb-b2a8-4a99-b9b3-853f7203b752",
    "release_label": "PHILHEALTH-EMCB-LAB_093026-2026-09-30",
    "source_record_id": "philhealth:clinical-laboratory:sky-diagnostic-medical-corp:baliuag:67ef3057a2",
    "source_record_uuid": "e1eb3f20-45cc-4244-a668-fe1c979a2882",
    "row_reference": "page:2:row:7",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T04:33:44.408816Z",
    "processed_at": "2026-11-15T04:33:55.500370Z",
    "match_method": "exact_agency_id",
    "match_status": "automatic_high_confidence",
    "match_confidence": 1.0,
    "rights_status": "approved_with_attribution",
    "publication_status": "published",
    "license_identifier": null,
    "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
    "is_synthetic": false
  },
  {
    "id": "7cd0f7da-30fc-411d-b328-104dfed5f55c",
    "agency": "Philippine Health Insurance Corporation",
    "agency_code": "philhealth",
    "dataset": "PhilHealth — Pelvic Ultrasound",
    "dataset_slug": "philhealth-emcb-putz",
    "release_id": "1ef24424-b1dd-4a47-a231-c375e0d5cd41",
    "release_label": "PHILHEALTH-EMCB-PUTZ_093026-2026-09-30",
    "source_record_id": "philhealth:pelvic-ultrasound:sky-diagnostic-medical-corp:baliuag:920ca1bc29",
    "source_record_uuid": "acf79b27-b62a-43de-9aba-686f89c1c412",
    "row_reference": "page:1:row:11",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T03:31:05.251986Z",
    "processed_at": "2026-11-15T03:31:16.931572Z",
    "match_method": "exact_agency_id",
    "match_status": "automatic_high_confidence",
    "match_confidence": 1.0,
    "rights_status": "approved_with_attribution",
    "publication_status": "published",
    "license_identifier": null,
    "attribution_text": "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare Facilities directory",
    "is_synthetic": false
  }
]
```

## Source and release provenance

### Dataset catalogue

```http
GET /v1/sources
```

HTTP `200` · `application/json`

Rights, publication state, and latest release for every registered dataset.

```json
[
  {
    "access_method": "public_json_api",
    "agency": "BetterGov.PH",
    "agency_code": "bettergov",
    "attribution_text": "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; Philippine Statistics Authority remains the authoritative source",
    "description": null,
    "id": "8b2396af-5838-493b-867e-409783dffcef",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": null,
    "latest_release": {
      "id": "3d64f7d5-2d95-44aa-bf42-9c8aab354a69",
      "ingestion_status": "published",
      "label": "PSA-2024-CENSUS-Negros-Island-Region-NIR-2024-07-01",
      "publication_status": "published",
      "reference_period_end": "2024-07-01",
      "reference_period_start": "2024-07-01",
      "retrieved_at": "2026-09-09T18:49:34.797000Z",
      "row_count_parsed": 4260,
      "sha256": "5b5145a1afff85eecc516f0b34d6d28a22ae64a1049a02849c7be78e4b91272a",
      "source_published_at": "2026-08-12T09:17:54Z",
      "terms_review_status": "approved_with_attribution"
    },
    "license_identifier": "CC-BY-SA-4.0",
    "name": "2024 Census of Population: total population, household population and number of households by province, city, municipality and barangay",
    "personal_data_status": null,
    "publication_gate_status": "approved",
    "publication_status": "approved",
    "redistribution_status": "approved_with_attribution",
    "rights_basis": "BetterGov.PH publishes the Philippine Data Explorer's original material under CC BY-SA 4.0. The population values are saved PSA OpenSTAT snapshots reproduced without aggregation; PSA remains the authoritative source. BetterGov.PH states that its preview does not itself establish redistribution rights, so this publication decision relies on the CC BY-SA 4.0 licence for the compilation and retains the PSA table URL, release identifier and attribution. No new PSA terms review is claimed.",
    "schema_version": null,
    "slug": "psa-census-2024-population",
    "source_url": "https://statistics.bettergov.ph/api",
    "terms_url": "https://statistics.bettergov.ph/about",
    "update_pattern": "saved PSA OpenSTAT snapshot; checked periodically"
  },
  {
    "access_method": "public_api",
    "agency": "BetterGov.PH",
    "agency_code": "bettergov",
    "attribution_text": "BetterGov.PH Classification API (CC BY-SA 4.0), derived from PSA PSGC Q2 2024",
    "description": null,
    "id": "145ae26a-3ddc-4bc1-b2c2-270fa4ac2c5d",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": {
      "id": "c857730d-abc7-4b09-a55f-56cde6d530ba",
      "is_synthetic": false,
      "published_at": null,
      "reference_date": "2024-06-30",
      "release_label": "PSGC-Q2-2024-BETTERGOV",
      "retrieved_at": "2026-11-15T02:24:43.740698Z",
      "source_url": "https://statistics.bettergov.ph/api/classification/psgc"
    },
    "latest_release": null,
    "license_identifier": "CC-BY-SA-4.0",
    "name": "PSGC Q2 2024 snapshot (BetterGov Classification API)",
    "personal_data_status": null,
    "publication_gate_status": "approved",
    "publication_status": "published",
    "redistribution_status": "approved_with_attribution",
    "rights_basis": "BetterGov.PH publishes the classification API under CC BY-SA 4.0. The snapshot mirrors PSA PSGC Q2 2024; it is supplementary and is not the latest official PSA workbook. Attribution is retained and adaptations share the same licence.",
    "schema_version": null,
    "slug": "psgc-bettergov-q2-2024",
    "source_url": "https://statistics.bettergov.ph/api/classification/psgc",
    "terms_url": "https://statistics.bettergov.ph/api",
    "update_pattern": "quarterly snapshot"
  },
  {
    "access_method": "public_html_directory",
    "agency": "Commission on Higher Education",
    "agency_code": "ched",
    "attribution_text": null,
    "description": null,
    "id": "f464fb75-30c0-4609-b428-5bd615368531",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": null,
    "latest_release": null,
    "license_identifier": null,
    "name": "CHED HEIDA higher-education institution directory",
    "personal_data_status": null,
    "publication_gate_status": "review_required",
    "publication_status": "blocked",
    "redistribution_status": "review_required",
    "rights_basis": "The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked.",
    "schema_version": null,
    "slug": "ched-hei-directory",
    "source_url": "https://heida.ched.gov.ph/hei-directory",
    "terms_url": null,
    "update_pattern": "unknown"
  },
  {
    "access_method": "public_html_form",
    "agency": "Department of Education",
    "agency_code": "deped",
    "attribution_text": null,
    "description": null,
    "id": "f9c1b1ea-0c75-4227-ab8b-bd37c88ed638",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": null,
    "latest_release": {
      "id": "44f302df-4eff-48ee-8e98-f4110751d910",
      "ingestion_status": "published",
      "label": "DEPED-EBEIS-NCR-2026-11-15",
      "publication_status": "internal_only",
      "reference_period_end": null,
      "reference_period_start": null,
      "retrieved_at": "2026-11-15T05:58:33.800809Z",
      "row_count_parsed": 5055,
      "sha256": "f972cde8c01597a6b7cf064b4735b9d073b7c4746e8d505bd09abe1cbc0e218b",
      "source_published_at": null,
      "terms_review_status": "restricted_non_redistributable"
    },
    "license_identifier": null,
    "name": "DepEd EBEIS school masterlist (NCR result set)",
    "personal_data_status": "contains_school_head_names",
    "publication_gate_status": "internal_only",
    "publication_status": "internal_only",
    "redistribution_status": "restricted_non_redistributable",
    "rights_basis": "The public EBEIS masterlist has no explicit reuse licence and includes school-head personal names. It is stored privately for identity/provenance work and is internal-only pending DepEd terms and privacy review.",
    "schema_version": null,
    "slug": "deped-ebeis-masterlist-ncr",
    "source_url": "https://ebeis.deped.gov.ph/beis/reports_info/masterlist",
    "terms_url": null,
    "update_pattern": "school year"
  },
  {
    "access_method": "human_download",
    "agency": "Department of Education",
    "agency_code": "deped",
    "attribution_text": null,
    "description": null,
    "id": "6c64e480-eeaa-443f-ab01-7050b44ff71d",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": null,
    "latest_release": null,
    "license_identifier": null,
    "name": "DepEd Machine-Ready Files",
    "personal_data_status": null,
    "publication_gate_status": "review_required",
    "publication_status": "blocked",
    "redistribution_status": "review_required",
    "rights_basis": "The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked.",
    "schema_version": null,
    "slug": "deped-machine-ready-files",
    "source_url": "https://www.deped.gov.ph/machine-ready-files/",
    "terms_url": null,
    "update_pattern": "school year"
  },
  {
    "access_method": "official_registry",
    "agency": "Department of Health",
    "agency_code": "doh",
    "attribution_text": null,
    "description": null,
    "id": "e7115cda-12c6-44e9-8757-1ec7068156f2",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": null,
    "latest_release": null,
    "license_identifier": null,
    "name": "DOH National Health Facility Registry",
    "personal_data_status": null,
    "publication_gate_status": "review_required",
    "publication_status": "blocked",
    "redistribution_status": "review_required",
    "rights_basis": "The official endpoint was reachable only through a human terms/access flow or returned an access-control challenge. No redistribution decision exists; the dataset remains blocked.",
    "schema_version": null,
    "slug": "doh-nhfr",
    "source_url": "https://nhfr.doh.gov.ph/VActivefacilitiesList",
    "terms_url": null,
    "update_pattern": "weekly"
  },
  {
    "access_method": "public_geoparquet",
    "agency": "OpenStreetMap contributors (via HOT and BetterGov.PH)",
    "agency_code": "osm",
    "attribution_text": "© OpenStreetMap contributors, via HOT and BetterGov.PH",
    "description": null,
    "id": "7a7706e9-9085-4cee-af09-895996f34213",
    "is_public_source": true,
    "is_synthetic": false,
    "latest_geography_release": null,
    "latest_release": {
      "id": "03f05987-3ef4-4f0b-a215-29ef601c45cf",
      "ingestion_status": "published",
      "label": "HOT-OSM-PHL-EDUCATION-2026-11-15",
      "publication_status": "published",
      "reference_period_end": null,
      "reference_period_start": null,
      "retrieved_at": "20
… (truncated for this report)
```

### Release ledger

```http
GET /v1/source-releases?limit=10
```

HTTP `200` · `application/json`

Newest releases first; includes retained blocked and processing releases.

```json
[
  {
    "id": "5e38923d-321f-4247-94ee-70f00440f926",
    "dataset_slug": "philhealth-fdc",
    "dataset_name": "PhilHealth — Freestanding Dialysis Clinics",
    "agency": "Philippine Health Insurance Corporation",
    "source_release_label": "PHILHEALTH-FDC_093026-2026-09-30",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T08:13:58.949481Z",
    "processed_at": "2026-11-15T08:14:31.055094Z",
    "file_format": "pdf",
    "file_size_bytes": 3084801,
    "row_count_parsed": 1012,
    "ingestion_status": "published",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "published",
    "parser_version": "philhealth-pdf-1.2.0",
    "sha256": "b6c9ccce2bb7de8aa414dab9da3404f8de9616647dd2fa9f18214bc7c0418fa9"
  },
  {
    "id": "ca3e9daf-abbe-4300-b929-5a3e9a86b303",
    "dataset_slug": "philhealth-hosp",
    "dataset_name": "PhilHealth — Hospitals and Infirmaries/Dispensaries",
    "agency": "Philippine Health Insurance Corporation",
    "source_release_label": "PHILHEALTH-HOSP_093026-2026-09-30",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T08:12:42.492714Z",
    "processed_at": "2026-11-15T08:13:47.674518Z",
    "file_format": "pdf",
    "file_size_bytes": 4294314,
    "row_count_parsed": 1934,
    "ingestion_status": "published",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "published",
    "parser_version": "philhealth-pdf-1.2.0",
    "sha256": "9ef34056f893a5aa485619e71d8481f02da149ce61a1ca1d75686a2f4c81c0b4"
  },
  {
    "id": "8f86bdd6-4d6e-4d20-b650-b0076a5e88aa",
    "dataset_slug": "philhealth-gamot",
    "dataset_name": "PhilHealth — GAMOT Package Providers",
    "agency": "Philippine Health Insurance Corporation",
    "source_release_label": "PHILHEALTH-GAMOT-UNDATED",
    "source_published_at": null,
    "reference_period_start": null,
    "reference_period_end": null,
    "retrieved_at": "2026-11-15T08:10:37.982183Z",
    "processed_at": "2026-11-15T08:12:23.387648Z",
    "file_format": "pdf",
    "file_size_bytes": 5244098,
    "row_count_parsed": 3483,
    "ingestion_status": "published",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "published",
    "parser_version": "philhealth-pdf-1.2.0",
    "sha256": "a8649244ca31baa484607ca62a7cba44cf273725eea868ed4c54935c6436111a"
  },
  {
    "id": "8fc88506-f2be-4c5e-9e97-823f051b954d",
    "dataset_slug": "philhealth-yakap",
    "dataset_name": "PhilHealth — Yakap Clinics",
    "agency": "Philippine Health Insurance Corporation",
    "source_release_label": "PHILHEALTH-YAKAP-UNDATED",
    "source_published_at": null,
    "reference_period_start": null,
    "reference_period_end": null,
    "retrieved_at": "2026-11-15T08:08:07.434929Z",
    "processed_at": "2026-11-15T08:10:15.187401Z",
    "file_format": "pdf",
    "file_size_bytes": 5755769,
    "row_count_parsed": 4138,
    "ingestion_status": "published",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "published",
    "parser_version": "philhealth-pdf-1.2.0",
    "sha256": "2b288424cff77a37f2a31a02470165469be9877b021011966eceea52eceabf55"
  },
  {
    "id": "44f302df-4eff-48ee-8e98-f4110751d910",
    "dataset_slug": "deped-ebeis-masterlist-ncr",
    "dataset_name": "DepEd EBEIS school masterlist (NCR result set)",
    "agency": "Department of Education",
    "source_release_label": "DEPED-EBEIS-NCR-2026-11-15",
    "source_published_at": null,
    "reference_period_start": null,
    "reference_period_end": null,
    "retrieved_at": "2026-11-15T05:58:33.800809Z",
    "processed_at": "2026-11-15T06:00:23.721386Z",
    "file_format": "html",
    "file_size_bytes": 998059,
    "row_count_parsed": 5055,
    "ingestion_status": "published",
    "terms_review_status": "restricted_non_redistributable",
    "publication_status": "internal_only",
    "parser_version": "deped-ebeis-html-1.0.0",
    "sha256": "f972cde8c01597a6b7cf064b4735b9d073b7c4746e8d505bd09abe1cbc0e218b"
  },
  {
    "id": "03f05987-3ef4-4f0b-a215-29ef601c45cf",
    "dataset_slug": "osm-education-facilities",
    "dataset_name": "OpenStreetMap education facilities (HOT Philippines extract)",
    "agency": "OpenStreetMap contributors (via HOT and BetterGov.PH)",
    "source_release_label": "HOT-OSM-PHL-EDUCATION-2026-11-15",
    "source_published_at": null,
    "reference_period_start": null,
    "reference_period_end": null,
    "retrieved_at": "2026-11-15T05:02:30.586639Z",
    "processed_at": "2026-11-15T05:28:04.320531Z",
    "file_format": "parquet",
    "file_size_bytes": 34784703,
    "row_count_parsed": 55824,
    "ingestion_status": "published",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "published",
    "parser_version": "osm-geoparquet-1.0.0",
    "sha256": "f83ffcd492d83dfc071efe0d9c118ad8266b5e0bfd26f8adba043fc309989ba1"
  },
  {
    "id": "9507352f-088e-4b05-b114-6714d85c028e",
    "dataset_slug": "philhealth-emcb-ante",
    "dataset_name": "PhilHealth — Antenatal",
    "agency": "Philippine Health Insurance Corporation",
    "source_release_label": "PHILHEALTH-EMCB-ANTE_093026-2026-09-30",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T04:42:54.558908Z",
    "processed_at": "2026-11-15T04:45:42.926753Z",
    "file_format": "pdf",
    "file_size_bytes": 5462847,
    "row_count_parsed": 6562,
    "ingestion_status": "withdrawn",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "blocked",
    "parser_version": "philhealth-pdf-1.1.0",
    "sha256": "a6245006008377678d38a42d24132d7368d3630152223bb710d7d98b2ece2231"
  },
  {
    "id": "69dff254-e8b0-4de9-84d0-8fd2df525470",
    "dataset_slug": "philhealth-emcb-tvu",
    "dataset_name": "PhilHealth — Transvaginal Ultrasound",
    "agency": "Philippine Health Insurance Corporation",
    "source_release_label": "PHILHEALTH-EMCB-TVU_093026-2026-09-30",
    "source_published_at": "2026-09-30T00:00:00Z",
    "reference_period_start": "2026-09-30",
    "reference_period_end": "2026-09-30",
    "retrieved_at": "2026-11-15T04:39:17.137577Z",
    "processed_at": "2026-11-15T04:39:24.749654Z",
    "file_format": "pdf",
    "file_size_bytes": 2226194,
    "row_count_parsed": 90,
    "ingestion_status": "published",
    "terms_review_status": "approved_with_attribution",
    "publication_status": "published",
    "parser_version": "philhealth-pdf-1.1.0",
    "sha256": "a66fc8d348d11073cdd7922e3d839ae32f0cabef804982a8400a292b9187a362"
  },
  {
    "id": "af1fc4df-1129-4e3c-a855-7bfafe6cbbad",
    "dataset_slug": "philhealth-emcb-ppartum",
    "dataset_name": "PhilHealth — Postpartum",
… (truncated for this report)
```

### Latest source checks

```http
GET /v1/source-checks?limit=5
```

HTTP `200` · `application/json`

Append-only monitoring evidence, including access blockers.

```json
[
  {
    "id": "33968f58-bb2b-4395-b4cb-ea455e3c0f93",
    "dataset_id": "96312566-d8c1-4936-a214-5b62b2a79d2a",
    "dataset_slug": "philhealth-fdc",
    "agency_code": "philhealth",
    "checked_at": "2026-11-15T08:13:58.941872Z",
    "status": "ok",
    "url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/FDC_093026.pdf",
    "final_url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/FDC_093026.pdf",
    "http_status": 200,
    "etag": "\"6ad0808b-2f1201\"",
    "last_modified": "Thu, 15 Oct 2026 07:28:11 GMT",
    "content_type": "application/pdf",
    "content_length": 3084801,
    "sha256": "b6c9ccce2bb7de8aa414dab9da3404f8de9616647dd2fa9f18214bc7c0418fa9",
    "duration_ms": 6645,
    "message": "PhilHealth Freestanding Dialysis Clinics: HTTP 200; date basis: date encoded in source file name (093026).",
    "details": {
      "category": "Freestanding Dialysis Clinics",
      "filename": "FDC_093026.pdf",
      "date_basis": "2026-09-30",
      "source_key": "philhealth"
    },
    "next_check_at": null
  },
  {
    "id": "872826f2-0431-48eb-90c1-902bbd70c9fc",
    "dataset_id": "4a6a9ac3-761f-42cb-8cef-de2fd4c18e96",
    "dataset_slug": "philhealth-hosp",
    "agency_code": "philhealth",
    "checked_at": "2026-11-15T08:12:42.485038Z",
    "status": "ok",
    "url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/HOSP_093026.pdf",
    "final_url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/HOSP_093026.pdf",
    "http_status": 200,
    "etag": "\"6ad08069-4186aa\"",
    "last_modified": "Thu, 15 Oct 2026 07:27:37 GMT",
    "content_type": "application/pdf",
    "content_length": 4294314,
    "sha256": "9ef34056f893a5aa485619e71d8481f02da149ce61a1ca1d75686a2f4c81c0b4",
    "duration_ms": 11476,
    "message": "PhilHealth Hospitals and Infirmaries/Dispensaries: HTTP 200; date basis: date encoded in source file name (093026).",
    "details": {
      "category": "Hospitals and Infirmaries/Dispensaries",
      "filename": "HOSP_093026.pdf",
      "date_basis": "2026-09-30",
      "source_key": "philhealth"
    },
    "next_check_at": null
  },
  {
    "id": "eb9f01b5-da17-40e6-be4d-2460791628a6",
    "dataset_id": "71e743fc-7ebe-4ee8-a788-b8ba0a160153",
    "dataset_slug": "philhealth-gamot",
    "agency_code": "philhealth",
    "checked_at": "2026-11-15T08:10:37.974998Z",
    "status": "ok",
    "url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/GAMOT.pdf",
    "final_url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/GAMOT.pdf",
    "http_status": 200,
    "etag": "\"6ad08036-5004c2\"",
    "last_modified": "Thu, 15 Oct 2026 07:26:46 GMT",
    "content_type": "application/pdf",
    "content_length": 5244098,
    "sha256": "a8649244ca31baa484607ca62a7cba44cf273725eea868ed4c54935c6436111a",
    "duration_ms": 12300,
    "message": "PhilHealth GAMOT Package Providers: HTTP 200; date basis: source file name carries no publication date.",
    "details": {
      "category": "GAMOT Package Providers",
      "filename": "GAMOT.pdf",
      "date_basis": null,
      "source_key": "philhealth"
    },
    "next_check_at": null
  },
  {
    "id": "c99e3cf6-6707-4cc0-bdeb-b51670ce63ad",
    "dataset_id": "348c571e-bea4-4ee9-903f-ff8042b862b2",
    "dataset_slug": "philhealth-yakap",
    "agency_code": "philhealth",
    "checked_at": "2026-11-15T08:08:07.410648Z",
    "status": "ok",
    "url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf",
    "final_url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf",
    "http_status": 200,
    "etag": "\"6ad07f45-57d379\"",
    "last_modified": "Thu, 15 Oct 2026 07:22:45 GMT",
    "content_type": "application/pdf",
    "content_length": 5755769,
    "sha256": "2b288424cff77a37f2a31a02470165469be9877b021011966eceea52eceabf55",
    "duration_ms": 12520,
    "message": "PhilHealth Yakap Clinics: HTTP 200; date basis: source file name carries no publication date.",
    "details": {
      "category": "Yakap Clinics",
      "filename": "YAKAP.pdf",
      "date_basis": null,
      "source_key": "philhealth"
    },
    "next_check_at": null
  },
  {
    "id": "2779afdd-df66-45c3-95c8-3c2ae4e9b1d6",
    "dataset_id": "b1ebbd3d-38e7-4b93-a6cb-352748f516fe",
    "dataset_slug": "tesda-tvi-directory",
    "agency_code": "tesda",
    "checked_at": "2026-11-15T06:07:32.285246Z",
    "status": "access_blocked",
    "url": "https://www.tesda.gov.ph/TVI",
    "final_url": "https://www.tesda.gov.ph/TVI",
    "http_status": 200,
    "etag": null,
    "last_modified": null,
    "content_type": "text/html; charset=utf-8",
    "content_length": 26667,
    "sha256": "2ca31a9036412bbb8cb191d4f51db7cc39e208dceee328686a9114bb216f0cce",
    "duration_ms": 2502,
    "message": "The source returned an access/verification page or an authentication denial. No bypass was attempted
… (truncated for this report)
```

### Source monitoring summary

```http
GET /v1/monitoring
```

HTTP `200` · `application/json`

```json
[
  {
    "dataset_id": "8b2396af-5838-493b-867e-409783dffcef",
    "dataset_slug": "psa-census-2024-population",
    "dataset_name": "2024 Census of Population: total population, household population and number of households by province, city, municipality and barangay",
    "agency": "BetterGov.PH",
    "agency_code": "bettergov",
    "access_method": "public_json_api",
    "rights_status": "approved_with_attribution",
    "publication_status": "approved",
    "last_checked_at": "2026-11-15T06:07:20.927644Z",
    "last_successful_at": "2026-11-15T06:07:20.927644Z",
    "check_status": "ok",
    "http_status": 200,
    "last_message": "BetterGov.PH / Philippine Statistics Authority endpoint returned HTTP 200.",
    "latest_release_label": "PSA-2024-CENSUS-Negros-Island-Region-NIR-2024-07-01",
    "latest_release_at": "2026-09-09T18:49:34.797000Z",
    "latest_release_rows": 4260,
    "next_check_at": "2026-11-22T06:07:20.927603Z",
    "warning": null
  },
  {
    "dataset_id": "145ae26a-3ddc-4bc1-b2c2-270fa4ac2c5d",
    "dataset_slug": "psgc-bettergov-q2-2024",
    "dataset_name": "PSGC Q2 2024 snapshot (BetterGov Classification API)",
    "agency": "BetterGov.PH",
    "agency_code": "bettergov",
    "access_method": "public_api",
    "rights_status": "approved_with_attribution",
    "publication_status": "published",
    "last_checked_at": "2026-11-15T06:07:18.746135Z",
    "last_successful_at": "2026-11-15T06:07:18.746135Z",
    "check_status": "ok",
    "http_status": 200,
    "last_message": "BetterGov.PH endpoint returned HTTP 200.",
    "latest_release_label": null,
    "latest_release_at": null,
    "latest_release_rows": null,
    "next_check_at": "2027-02-13T06:07:18.746111Z",
    "warning": null
  },
  {
    "dataset_id": "f464fb75-30c0-4609-b428-5bd615368531",
    "dataset_slug": "ched-hei-directory",
    "dataset_name": "CHED HEIDA higher-education institution directory",
    "agency": "Commission on Higher Education",
    "agency_code": "ched",
    "access_method": "public_html_directory",
    "rights_status": "review_required",
    "publication_status": "blocked",
    "last_checked_at": "2026-11-15T06:07:29.742643Z",
    "last_successful_at": "2026-11-15T06:07:29.742643Z",
    "check_status": "ok",
    "http_status": 200,
    "last_message": "Commission on Higher Education endpoint returned HTTP 200.",
    "latest_release_label": null,
    "latest_release_at": null,
    "latest_release_rows": null,
    "next_check_at": "2026-11-22T06:07:29.742616Z",
    "warning": "Records are not public because publication is gated."
  },
  {
    "dataset_id": "f9c1b1ea-0c75-4227-ab8b-bd37c88ed638",
    "dataset_slug": "deped-ebeis-masterlist-ncr",
    "dataset_name": "DepEd EBEIS school masterlist (NCR result set)",
    "agency": "Department of Education",
    "agency_code": "deped",
    "access_method": "public_html_form",
    "rights_status": "restricted_non_redistributable",
    "publication_status": "internal_only",
    "last_checked_at": "2026-11-15T06:07:25.478678Z",
    "last_successful_at": "2026-11-15T06:07:25.478678Z",
    "check_status": "ok",
    "http_status": 200,
    "last_message": "Department of Education endpoint returned HTTP 200.",
    "latest_release_label": "DEPED-EBEIS-NCR-2026-11-15",
    "latest_release_at": "2026-11-15T05:58:33.800809Z",
    "latest_release_rows": 5055,
    "next_check_at": "2026-11-22T06:07:25.478653Z",
    "warning": "Records are not public because publication is gated."
  },
  {
    "dataset_id": "6c64e480-eeaa-443f-ab01-7050b44ff71d",
    "dataset_slug": "deped-machine-ready-files",
    "dataset_name": "DepEd Machine-Ready Files",
    "agency": "Department of Education",
    "agency_code": "deped",
    "access_method": "human_download",
    "rights_status": "review_required",
    "publication_status": "blocked",
    "last_checked_at": "2026-11-15T06:07:27.038103Z",
    "last_successful_at": null,
    "check_status": "access_blocked",
    "http_status": 403,
    "last_message": "The source returned an access/verification page or an authentication denial. No bypass was attempted; a human-assisted or authorized route is required.",
    "latest_release_label": null,
    "latest_release_at": null,
    "latest_release_rows": null,
    "next_check_at": "2026-11-22T06:07:27.038080Z",
    "warning": "Records are not public because publication is gated."
  },
  {
    "dataset_id": "e7115cda-12c6-44e9-8757-1ec7068156f2",
    "dataset_slug": "doh-nhfr",
    "dataset_name": "DOH National Health Facility Registry",
    "agency": "Department of Health",
    "agency_code": "doh",
    "access_method": "official_registry",
    "rights_status": "review_required",
    "publication_status": "blocked",
    "last_checked_at": "2026-11-15T06:07:27.965646Z",
    "last_successful_at": null,
    "check_status": "access_blocked",
    "http_status": 403,
    "last_message": "The source returned an access/verification page or an authentication denial. No bypass was attempted; a human-assist
… (truncated for this report)
```

## Bulk export

```http
GET /v1/downloads/facilities.csv
```

HTTP `200` · `text/csv; charset=utf-8` · `attachment; filename="philfacilities-facilities-2026-11-15.csv"`

```csv
id,display_name,facility_type,facility_subtype,ownership,record_status,publication_status,psgc_code,psgc_release,region_code,region_name,province_code,province_name,municipality_code,municipality_name,barangay_code,barangay_name,latitude,longitude,location_precision,location_method,address_text,source_count,source_records,is_synthetic,updated_at
d922beea-8c06-41cb-abdf-96f3801cf3f9,0-2,school,school,government,unknown,public,0305417006,PSGC-Q2-2024-BETTERGOV,0300000000,Region III (Central Luzon),0305400000,Pampanga,0305417000,San Luis,0305417006,San Nicolas,15.042615,120.79506,map_geocoded,openstreetmap_bbox_center,,1,osm:osm-education-facilities:way/858034206,False,2026-11-15T05:12:30.970089+00:00
97fb11c4-eb65-4f9a-8aeb-ef88cad9e26a,1,school,school,unknown,unknown,public,,,,,,,,,,,7.296666,125.303363,map_geocoded,openstreetmap_bbox_center,,1,osm:osm-education-facilities:way/333205620,False,2026-11-15T05:26:36.074809+00:00
80d9a494-0632-4d72-bdaf-2bf95ff8f1f4,1,health_facility,dentist,unknown,unknown,public,0403426024,PSGC-Q2-2024-BETTERGOV,0400000000,Region IV-A (CALABARZON),0403400000,Laguna,0403426000,Santa Cruz,0403426024,Santo Angel Central,14.281149,121.415136,map_geocoded,openstreetmap_bbox_center,,1,osm:osm-health-facilities:node/8519720316,False,2026-11-15T04:26:20.918019+00:00
… (84613 data rows in this snapshot)
```

The CSV uses the same publication gate as `/v1/facilities`; it is not a separate extraction path.

## Interpretation

- These are actual response samples from the local API, not fixtures written for documentation.
- A record can be present in a retained release and still be absent here if its rights gate is blocked, internal-only, or quarantined.
- OSM/HOT records are crowd-sourced map features with bbox-centre coordinates (`map_geocoded`) and unknown operational status; they are not official DOH or DepEd records.
- Counts in this file describe the captured snapshot, not the national facility universe.
