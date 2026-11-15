# 01 — Project Charter

## 1. Vision

PhilFacilities is an independent, open public-data platform that builds and maintains a source-linked registry of facilities in the Philippines, beginning with schools and health facilities.

It converts fragmented official records into normalized, historically traceable entities that citizens can search and that developers, researchers, NGOs, journalists, and local planners can reuse through an API and bulk downloads.

**Product promise:** One discoverable facility record, original government identities preserved, source evidence visible, and uncertainty made explicit.

## 2. Problem

Facility information is distributed across agencies and publication formats. The same physical institution can appear in multiple systems with different identifiers, names, addresses, status fields, and update schedules. Public access does not guarantee a common API, comparable schemas, complete coverage, or accurate coordinates.

A new map alone does not solve this problem. The missing product is a maintainable data layer that:

- reconciles source records without losing original IDs;
- records where each attribute came from;
- preserves changes and historical snapshots;
- normalizes geography against versioned PSGC references;
- distinguishes source-reported facts from derived or unverified values;
- exposes the result in documented APIs and bulk downloads.

## 3. Users and jobs-to-be-done

| User | Need | PhilFacilities response |
|---|---|---|
| Citizen / parent / patient | Find facilities and understand what the record actually says | Searchable directory, source dates, contact/address where publishable, map with precision warnings |
| Developer | Avoid scraping multiple agency portals | Stable REST API, OpenAPI, filters, bulk CSV/Parquet, change feed |
| Researcher / journalist | Reproduce analysis and trace facts | Source snapshots, release history, data dictionary, provenance |
| NGO / local planner | Understand facility distribution | PSGC-based aggregation, downloadable geographic data, quality indicators |
| Open-source contributor | Improve a source connector or schema | Modular adapters, fixtures, tests, contributor docs |

## 4. Goals

### MVP goals

1. Ingest a verified official PSGC release.
2. Ingest at least one actual DepEd school-level file.
3. Acquire and lawfully process a DOH NHFR extract; if its agreement does not permit public redistribution, keep it private for matching/validation or defer DOH publication until clarified.
4. Ingest PhilHealth public provider-category records where terms permit, preserving package-specific status and source dates.
5. Build canonical identities and retain original agency identifiers.
6. Preserve raw files and source-release metadata.
7. Publish a versioned read API with source/provenance fields.
8. Deliver a directory and map that clearly communicate data age and location confidence.
9. Provide source documentation, OpenAPI docs, bulk exports where legally permitted, and a data quality report.

### Longer-term goals

- Expand to CHED and TESDA after source-level acquisition and terms validation.
- Add facility-level historical changes, public corrections, and reviewed entity matching.
- Add health-access and school-access analytical modules only when the input data supports defensible calculations.
- Add facility-to-infrastructure-project and hazard-exposure relationships as separate, traceable datasets.

## 5. Non-goals for MVP

- Real-time bed availability, appointment booking, or live service availability.
- Claiming a facility is open/operational based only on appearing in an old registry.
- Patient, student, employee, or beneficiary personal-data collection.
- Individual health records or PhilHealth claims data.
- Crowdsourced reports presented as official facts.
- Predictive facility quality, hospital rankings, school rankings, or unsupported safety scores.
- Replacing DepEd, DOH, PhilHealth, CHED, TESDA, PSA, or BetterGov portals.
- A nationwide vector tile infrastructure before there is a demonstrated need.

## 6. Product boundaries and initial coverage

The platform model may represent government and private facilities when an official source legitimately provides them. The UI must label ownership clearly. The initial public-facing emphasis is on public-service discovery; private records must not be mislabeled as public facilities.

Initial facility domains:

- `school`: DepEd basic education institutions.
- `health_facility`: DOH NHFR establishments.
- `accreditation`: separate PhilHealth provider-category records linked to health facilities when matching is sufficiently confident.

PSA PSGC is the canonical geographic reference. Population statistics from PSA or BetterGov are contextual observations, not facility attributes.

## 7. Success measures

Do not optimize for raw record count alone. Track:

- source releases ingested successfully;
- percentage of source records with stable original IDs;
- PSGC match rate by administrative level;
- duplicate/ambiguous-match rate;
- coordinate completeness and precision distribution;
- percentage of public attributes with provenance;
- source freshness by dataset;
- rejected-row rate and unresolved quality issues;
- API uptime, p95 latency, and error rate;
- successful API/bulk-download integrations by external users;
- correction reports received and resolved.

Every metric must include its denominator and reference period. A source with 100% of rows processed is not necessarily 100% complete relative to the real-world universe of facilities.

## 8. Product principles

- Evidence before polish.
- Preserve raw source data and publish transformations transparently.
- Treat records as time-bound observations, not timeless truths.
- Prefer deterministic matching and human review over aggressive fuzzy merging.
- Display unknown values honestly.
- Keep public APIs useful without the website.
- Use open-source code while respecting source-specific data licenses and agreements.
