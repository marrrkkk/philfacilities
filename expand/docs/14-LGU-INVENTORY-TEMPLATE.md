# 14 — LGU Facility Inventory Intake Template

This document defines the controlled intake format for LGU facility inventories. It implements the template and validation part of AF4-01/AF4-09.

The template is an **intake** format, not a publication format. A validated row is a proposal for review. Validation does not import, approve, or publish a record, and does not establish ownership, operation, access, or current status.

## Files and commands

- Template: [`expand/templates/lgu-inventory-template.csv`](../templates/lgu-inventory-template.csv)
- Validator: `apps/ingest/philfacilities_ingest/lgu_inventory.py`
- Command:

```bash
uv run philfacilities-ingest validate-lgu-inventory path/to/lgu-inventory.csv
uv run philfacilities-ingest validate-lgu-inventory path/to/lgu-inventory.csv --json
uv run philfacilities-ingest validate-lgu-inventory path/to/lgu-inventory.csv \
  --output var/reports/lgu-inventory-validation.json
```

The command exits non-zero when any row is rejected or the file has a fatal schema/privacy issue.

## Required columns

| Column | Meaning |
|---|---|
| `lgu_psgc_code` | 10-digit PSGC code of the city/municipality, with leading zeros. |
| `lgu_name` | Official city/municipality name. |
| `facility_name` | Official/local facility name. |
| `facility_type` | Published facility category, e.g. `government_office`. |
| `facility_subtype` | Published subtype for that category, e.g. `CITY_MUNICIPAL_HALL`. |
| `facility_kind` | `facility`, `site`, `building`, or `facility_unit`. |
| `ownership_type` | Controlled ownership vocabulary, e.g. `LOCAL_GOVERNMENT`. |
| `operator_type` | Controlled operator vocabulary. |
| `address_text` | Street/landmark address as held by the LGU. |
| `reference_date` | ISO date or reporting date for the inventory. |
| `source_reference` | Inventory file, sheet, page, URL, or official reference. |

## Optional columns

`lgu_facility_id`, `inclusion_class`, `public_access_class`, `barangay_psgc_code`, `barangay_name`, `municipality_city`, `province_name`, `region_name`, `latitude`, `longitude`, `coordinate_precision`, `coordinate_method`, `owner_name`, `operator_name`, `manager_name`, `funding_source`, `capacity_value`, `capacity_unit`, `operational_status_evidence`, `status_as_of`, `access_conditions`, `notes`.

`capacity_value` and `capacity_unit` are paired conceptually: never mix seats, persons, beds, stalls, classrooms, and square metres in one untyped number.

## Validation rules

1. Required columns must be present.
2. `lgu_psgc_code` must be exactly 10 digits; leading zeros are preserved.
3. `barangay_psgc_code`, when supplied, must be 10 digits and share the LGU prefix.
4. `facility_type` and `facility_subtype` must belong to the published taxonomy.
5. `facility_kind` must be an operating facility/site/building/unit. `project` and `infrastructure_asset` are rejected because they belong to the related-asset model.
6. `ownership_type` and `operator_type` must use the controlled vocabulary.
7. `inclusion_class` and `public_access_class`, when supplied, must use controlled values.
8. `reference_date` is required and must be ISO `YYYY-MM-DD`.
9. Coordinates must be supplied as a latitude/longitude pair, numeric, inside the Philippine bounding box, and accompanied by a `coordinate_precision` value.
10. Duplicate `(lgu_psgc_code, facility_name)` pairs are warnings, because distinct sites can share a name; they are not silently merged.
11. Personal contact columns (`contact_person`, `mobile`, `email`, `telephone`, `fax`, and similar) are fatal. Submit institutional fields only.
12. Security-sensitive columns (`security_detail`, `guard_count`, `patrol_route`, `radio_frequency`, `cctv`, and similar) are fatal.

## Review workflow

```text
Draft submission
  -> schema validation
  -> geography validation
  -> duplicate/candidate matching
  -> source and rights review
  -> field-level publication decision
  -> approval
  -> release
```

A submission must remain a proposal until reviewed. The validator deliberately does not write to the database. Import, matching, approval, and publication remain separate controlled operations.

Record the submitting LGU/organization, the authority represented, the supporting document, review notes, and final decision in the review record. Never treat an LGU listing as proof of ownership, operation, public access, or current operating status.

## Privacy and security

- Do not request or accept personal names, personal mobile numbers, personal e-mail addresses, or security operational details.
- Use institutional office names and public office addresses.
- If an inventory contains restricted or sensitive fields, ask the custodian for a redacted extract rather than importing the restricted fields.
- Emergency, police, corrections, utility, and critical-infrastructure records require the review in [`13-PUBLIC-SAFETY-SECURITY-CHECKLIST.md`](13-PUBLIC-SAFETY-SECURITY-CHECKLIST.md).

## Current limitations

- There is no automatic LGU import or publication step yet; validation is the implemented gate.
- A validated file is not a source release. Acquisition must record the exact file, retrieval time, checksum, custodian, reference date, and rights decision.
- No pilot LGU inventory has been acquired. Coverage must not be inferred from the existence of this template.
