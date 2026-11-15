# 07 — Coverage, Data Quality, and Public Trust

## 1. Purpose

The registry must communicate what is known, how it is known, how current it is, and what is missing. It must not hide weak data behind a confident-looking map pin.

## 2. Separate quality dimensions

Do not collapse all quality into a single score.

| Dimension | Question | Example values |
|---|---|---|
| Source authority | Who published the record? | Official national agency, official LGU, official Geoportal layer, third-party lead |
| Identity confidence | Are we sure this is the same facility? | Exact source ID, multi-field match, manual confirmed, ambiguous |
| Location precision | How precise is the geometry? | GPS/survey, source geocoded, map geocoded, barangay centroid, municipality centroid, unknown |
| Attribute confidence | Is the attribute supported by a source? | Source-reported, cross-source corroborated, derived, unknown |
| Freshness | How old is the source observation? | Freshness computed from source date, not fetch date |
| Completeness | Which required fields are present? | Field-level completeness, not a vague overall label |
| Rights status | Can this information be shown publicly? | Approved, conditional, internal-only, blocked |
| Coverage scope | What geographic/source universe does this record set represent? | National, regional, participating LGUs, selected LGUs, one city |

## 3. Location-quality classes

Recommended internal values:

- `surveyed_or_gps` — source explicitly states a GPS/survey method or field verification with evidence.
- `agency_geocoded` — coordinates supplied by an agency but method/precision not fully documented.
- `map_geocoded` — matched from a map/geocoder or external map reference.
- `barangay_centroid` — coordinate is a barangay centroid, not a facility entrance/building.
- `municipality_centroid` — approximate locality-level point.
- `polygon_only` — a site boundary exists but no canonical point.
- `unknown` — provenance/precision unknown.

Only use `surveyed_or_gps` when the source supports it. A valid-looking coordinate is not evidence of accuracy.

For map behavior:

- display precise coordinates as facility pins;
- render map-geocoded points with an approximate marker/label;
- render barangay/municipal centroids as approximate area markers, not exact facility locations;
- show polygon-only facilities as areas where appropriate;
- keep facilities without coordinates in directory/search results;
- allow users to filter by location quality.

## 4. Freshness model

Track four separate dates:

1. `source_published_at` — when the source publisher released the dataset/document.
2. `source_reference_date` — the effective date or period the information describes.
3. `retrieved_at` — when PhilFacilities acquired it.
4. `published_at` — when PhilFacilities made the normalized record public.

Freshness must be calculated from the source reference/publication date, not just `retrieved_at`.

For example, a 2023 library directory downloaded in November 2026 remains a 2023 directory. A new download does not make the source information current.

## 5. Coverage model

Track coverage by:

- facility category and subtype;
- region/province/city/municipality/barangay;
- source agency and source release;
- inclusion class;
- ownership/operator type;
- rights and publication state, including the recorded publication basis;
- source reference period.

Use explicit coverage states:

- `NATIONAL_OFFICIAL_INVENTORY` — an official source claims complete national coverage and methodology supports the claim;
- `NATIONAL_PARTIAL` — nationwide source exists but known omissions/incompleteness remain;
- `REGIONAL`;
- `PARTICIPATING_LGUS`;
- `SELECTED_LGUS`;
- `SINGLE_LGU`;
- `DIRECTORY_SUBSET`;
- `DISCOVERY_LAYER`;
- `UNKNOWN_COVERAGE`.

Do not infer nationwide completeness from a map titled “Philippines” or from a national agency's existence. Require documented scope and record-level evidence.

## 6. Data-quality checks

### Identity

- source ID uniqueness;
- empty/malformed IDs;
- duplicate exact IDs;
- same-name candidates in different LGUs;
- inconsistent source identifiers;
- aliases and renamed facilities;
- false-merge detection.

### Geography

- valid PSGC code for the relevant PSGC release;
- region/province/city/municipality/barangay hierarchy consistency;
- point-in-polygon checks where authoritative boundaries are available;
- source CRS and geometry validity;
- longitude/latitude bounds;
- duplicate/co-located records;
- coordinate method/precision presence.

A point outside the assigned boundary should be flagged, not automatically moved.

### Facility category and functions

- recognized category/subtype;
- source term preserved;
- ambiguous multi-use classifications reviewed;
- government ownership not inferred from a public-service function;
- private regulated/accredited providers classified as `PRIVATE_PUBLIC_SERVICE_PROVIDER` where eligible;
- public-access venues classified separately;
- government, private-provider, public-venue and unknown-ownership counts kept distinct;
- ordinary private businesses and buildings excluded unless they meet the inclusion policy.

### Lifecycle/status

- source status preserved;
- status effective date present when provided;
- closure/relocation not inferred solely from missing records;
- expired accreditation not treated as facility closure;
- planned project not treated as operating facility.

### Domain data

Apply typed checks for each source domain: bed counts, school enrollment, library status, market stalls, capacity units, service categories, licence dates, and so on. Never compare capacity fields with different units.

## 7. Completeness and reliability reporting

For each source release, report:

- total raw records;
- parsed records;
- accepted records;
- rejected/quarantined records;
- duplicate source identifiers;
- canonical facilities created;
- source records linked to existing facilities;
- ambiguous matches;
- missing PSGC assignments;
- missing coordinates;
- location precision distribution;
- field-level missingness;
- records published vs held back;
- source reference date and retrieval date.

For each facility type and geography, show the proportion of records with coordinates, source dates, official IDs, and known owner/operator. Do not fabricate a coverage denominator when no official total exists.

## 8. Public coverage statements

Use truthful labels such as:

- “Records from participating LGUs”
- “Based on the DSWD directory dated 24 September 2026”
- “Geoportal discovery layer; source date not yet verified”
- “Selected LGU records; national coverage not established”
- “No record found in the sources currently ingested”

Avoid:

- “All barangay halls in the Philippines” without a validated national inventory;
- “Every evacuation centre” when only DILG-PULSE participating LGUs are covered;
- “Nearest hospital” when only approximate centroids are available;
- “Open/current/operational” without a current authoritative status source.

## 9. Public corrections

If the product supports public corrections:

1. Accept correction proposals, not automatic database updates.
2. Require a facility reference and proposed field change.
3. Allow supporting evidence/source links.
4. Keep the current published value until reviewed.
5. Record reviewer decision and reason.
6. Notify/coordinate with the source custodian where practical.
7. Publish a correction event with provenance, not an anonymous silent overwrite.
8. Provide an abuse and defamation moderation policy.

Do not collect personal information not needed for a correction.


## 10. Ownership-inclusive quality and coverage reporting

Report completeness and source coverage separately for each inclusion class and ownership type. At minimum provide:

- government facility counts;
- private public-service provider counts;
- public-access venue counts;
- unknown ownership counts;
- counts by facility category/subtype and geography;
- counts by original regulator/accreditor/source agency;
- counts for records with source-backed owner, operator, host and public-access information.

A private provider can be fully valid as a PhilFacilities record while its owner, exact operator or access conditions remain unknown. Show those missing attributes rather than excluding the facility automatically, unless the missing information prevents the inclusion test from being satisfied.

Do not present a combined registry count as a government-facility count. API statistics, map legends, charts, exports and marketing copy must use the same inclusion-class definitions.
