# Agent Instructions — PhilFacilities Ownership-Inclusive All-Facilities Expansion

## Mission

Expand the already-built PhilFacilities platform into a reliable, source-linked registry of all qualifying facilities in the Philippines, regardless of ownership: government facilities, private public-service providers, and documented public-access venues. This is not a census of every building or business.

The application foundation (web, map, API, database, deployment, monorepo and design system) is already implemented. This work is focused on expanding verified real-world data coverage, source acquisition, rights review, normalization, quality, and ongoing maintenance. Do not rebuild the application.

## Read first

1. `README.md`
2. `docs/01-PRODUCT-SCOPE.md`
3. `docs/02-FACILITY-TAXONOMY.md`
4. `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`
5. `docs/03-SOURCE-REGISTER.md`
6. `docs/04-LGU-ACQUISITION-STRATEGY.md`
7. `docs/05-DATA-MODEL-EXTENSION.md`
8. `docs/06-INGESTION-AND-RELEASES.md`
9. `docs/07-COVERAGE-AND-QUALITY.md`
10. `docs/09-DATA-GOVERNANCE.md`
11. `docs/11-VERIFIED-SOURCE-DISCOVERY.md`
12. `DATA-RIGHTS-REGISTER.md`
13. `planning/TRACKER.md`

## Do not rebuild completed work

- Do not recreate the Next.js app, FastAPI service, PostGIS database, map, CI/CD, deployment, monorepo, or design system unless a concrete source-integration requirement cannot be met without a targeted change.
- Do not perform a visual redesign as part of source expansion.
- Do not replace the established stack for preference reasons.
- Audit the repository and reuse existing source adapters, source registry, schemas, endpoints, UI components, migrations, tests and ingestion code.
- Make targeted migrations and backward-compatible changes where possible.

## Product scope

- PhilFacilities includes all **qualifying facilities regardless of ownership**: government facilities, private/non-government public-service providers, and documented public-access venues. It is not a census of every building or business.
- Follow `docs/01-PRODUCT-SCOPE.md`, `docs/02-FACILITY-TAXONOMY.md`, and the binding `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`.
- Private schools, healthcare providers, registered training providers, accredited social-welfare providers, and other qualifying private facilities are first-class records in the same registry/API, with a separate `PRIVATE_PUBLIC_SERVICE_PROVIDER` inclusion class.
- Never treat licence, accreditation, public funding, regulation, or a government-hosted service counter as government ownership.
- Keep government, private provider, and public-access venue counts distinct.
- Exclude ordinary private buildings/businesses unless they meet the documented inclusion test.
- Model facility category, subtype, function, service, inclusion class, owner, operator, manager, regulator, funder, host and public-access class separately.
- Support one physical facility with multiple functions (e.g. multipurpose hall + covered court + evacuation site).
- Distinguish a site/compound, building, facility unit, infrastructure asset and project.
- Roads, bridges, drainage networks, polygons and utility networks are not automatically facilities.

## Verified-source requirements

The source register is a living research inventory, not a complete or approved dataset list. The agent **must continue researching additional official sources** across every facility category.

For every source:

1. Start with the original official agency/publisher or data owner.
2. Locate the exact dataset, official directory, API endpoint, downloadable file, GIS layer, FOI attachment or LGU inventory.
3. Test actual reachability through an authorized route.
4. Inspect actual records or file contents before claiming field names, row counts, currentness or coverage.
5. Preserve the exact source column names and identifiers.
6. Record the release/publication date separately from the underlying reference period and retrieval time.
7. Establish whether records are national, regional, participating-LGU, selected-LGU, or single-LGU.
8. Identify ownership/operator/host/accreditation semantics.
9. Review exact storage, transformation, derived-data, attribution and redistribution terms. If no explicit licence exists, record whether the exact release is publicly available and whether any explicit prohibition applies.
10. Update `docs/03-SOURCE-REGISTER.md`, `DATA-RIGHTS-REGISTER.md`, and `planning/TRACKER.md` with evidence.

A homepage loading is not proof that a dataset is usable. An interactive map is not proof of bulk access. A Geoportal catalogue entry is not proof that its layer is downloadable or current. An FOI request marked successful is not proof that every requested field was supplied.

Use `docs/11-VERIFIED-SOURCE-DISCOVERY.md` as the mandatory protocol and evidence grading scheme.

## Expanded source inventory baseline — public and private sources

In addition to the original DepEd, DOH, PhilHealth, PSA/PSGC, CHED, TESDA, DSWD, Geoportal and DPWH leads, the current research register includes:

- DILG DRRM-PULSE participating-LGU facility map, Subaybayan LIME 20 evacuation-centre project records, and DILG FOI findings for barangay halls, public markets and evacuation-centre inventories;
- ECCD Council NCDCs/CDC profile resources;
- National Library of the Philippines public-library directories and National Museum site-museum directory;
- BFP logistical/station records;
- BIR Revenue District Offices and Citizen's Charter office listings;
- DTI Negosyo Centres and Geoportal shared-service facility candidates;
- PHLPost post-office/service locations and PRC regional/offsite service centres;
- PPA port lists, CAAP Area Centers/aerodrome references and PFDA regional/municipal fish-port references;
- NMIS NARIS accredited meat establishments;
- DENR-EMB air-quality monitoring stations, DENR-BMB PAIS and DENR-MGB geohazard candidates;
- NHA MAPS, NAMRIA products and Philippine Geoportal layers;
- Open Data Philippines as a dataset-discovery catalogue;
- PSA OpenSTAT/PSGC and BetterGov Statistics/Classification as geographic/statistical enrichment, not facility-of-record sources.

These resources have different evidence grades. Some are actual files/directories; some are FOI routes, project lists, participating-LGU portals, GIS catalogue candidates or discovery-only sources. Some official directories list private providers; these are eligible for the same registry when they meet the inclusion policy, but must retain private ownership/operator classifications. The source register states the distinctions and limitations. Re-test every resource during execution.

## Research more — required behavior

Do not stop at the sources currently listed. Systematically search official agencies, attached agencies, GOCCs, regional offices, LGU websites, official GIS portals, government open-data portals, public FOI disclosures, Citizen's Charters, annual reports and inventory forms.

At minimum research every category in `02-FACILITY-TAXONOMY.md` and the discovery queue in `03-SOURCE-REGISTER.md`.

When a source is missing or blocked, retain the negative finding and follow the official referral to the actual custodian or LGUs. Do not keep claiming an agency holds a dataset after it says it does not.

Do not invent datasets, APIs, URLs, columns, record counts, ownership, facility status or permissions. Keep a source as `DISCOVERY ONLY` until actual records are verified.

## Access and security rules

- Never bypass Cloudflare, CAPTCHAs, authentication, access controls, terms acceptance, download restrictions or licensing prompts.
- Never use stealth browser automation, rotating proxies, spoofed identity or CAPTCHA-solving services to obtain government data.
- Do not accept agreements or submit FOI/data requests in a person's name without explicit authorization.
- If authorized acquisition requires a human, build a controlled import workflow and automate subsequent processing/update steps only where permitted.
- Treat HTTP 403 as a source-access blocker, not a challenge to circumvent.
- Conduct extra security review for police, corrections, emergency, utility and critical infrastructure records. Exclude sensitive operational details.

## Data integrity

- Preserve original source files and parsed source records subject to retention terms.
- Use immutable source snapshots and release manifests.
- Keep raw source values separate from normalized values.
- Preserve original IDs, names, classifications and codes.
- Maintain source-release and facility history.
- Do not delete a facility just because it disappears from a later release.
- Do not infer closure from absence.
- Do not invent coordinates, capacities, operational status, owners, operators or services.
- Keep GPS/field-verified, geocoded, centroid and unknown locations distinct.
- Ambiguous matches remain unresolved or undergo documented human review.
- A private accredited provider is eligible as a `PRIVATE_PUBLIC_SERVICE_PROVIDER` when it meets the inclusion policy, but must never be counted as government-owned/operated.

## Publishing and legal controls

- Enforce dataset-, source-release- and field-level publication rights.
- No record from `BLOCKED`, `INTERNAL_ONLY`, `QUARANTINED`, `RESTRICTED`, `RIGHTS_UNKNOWN` or `REVIEW_REQUIRED` sources may appear in public API, map, search, statistics or exports.
- A verified, publicly available source with no explicit prohibition may be set to `PUBLICLY_AVAILABLE_VERIFIED` and published with reviewed institutional fields, provenance, attribution and takedown-on-notice. Explicit restrictions, FOI/agreement conditions, and personal or sensitive data still control. Follow root [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md).
- Preserve attribution and provenance.
- Minimize personal information; use institutional contacts rather than individual names/mobile/email where possible.
- Do not infer public access from public ownership or government operation; preserve access restrictions where known.
- Publish partial coverage honestly. Never claim nationwide completeness without a defensible universe/denominator and current source evidence.

## Tracker rules

- `planning/TRACKER.md` is the single implementation/research tracker.
- A URL found is not an acquired dataset.
- A source page is not a verified schema.
- A parser is not a completed ingestion until successfully executed against an actual authorized source release.
- A downloaded source is not publishable until its publication decision and quality checks pass.
- Mark `DONE` only with actual file/API evidence, exact release, row count, validation output, tests and a recorded publication decision.
- Preserve blocked, unknown, partial-coverage and deferred states.
- Keep source register, rights register, coverage report and tracker consistent.

## Execution priorities

1. Audit and preserve the existing school/health pipelines and PhilHealth parser; include both public and private records where authoritative sources support them.
2. Complete source discovery and rights checks for every category and ownership class.
3. Add verified private education, healthcare, training, social-welfare, utility and transport providers to the same canonical registry with distinct inclusion classes.
4. Add service-location directories (e.g. public libraries, DSWD centres, post offices, PRC service locations, BIR RDOs, DTI Negosyo Centres), distinguishing the service unit from a private host building.
5. Add emergency/public-safety sources (DRRM-PULSE, Subaybayan projects, BFP, evacuation sites, PNP) with coverage/security cautions.
6. Build LGU source acquisition for barangay halls, multipurpose halls, covered courts, markets, parks, plazas and other local facilities; include privately operated venues only where their public function is authoritative and documented.
7. Add port/airport/fish-port, public/private utility, agriculture, slaughterhouse, environmental monitoring and other sectors where legitimate facility-level records are verified.
8. Add GIS and hazard context only after layer-level source, age, download and rights checks.

## Required completion report

At every milestone report:

- source/dataset and original publisher;
- official URL and acquisition method;
- exact source release/reference date;
- file/response format and checksum where applicable;
- exact fields and actual record count;
- source scope/geographic coverage;
- quality findings and coordinate precision;
- rights/publication decision;
- actual records published, if any;
- known exclusions and limitations;
- tests/evidence;
- tracker IDs updated.

Never claim data is complete, national, current, official, or legally publishable without evidence.


## Ownership-inclusive scope is binding

The agent must not interpret “all facilities” as “government-owned facilities only”. Private facilities qualify when they are authoritative, publicly relevant service providers or public-access venues under the inclusion policy. They must be searchable in the same application and API, but separately classified and counted. Do not expand to all businesses or all buildings. The inclusion policy is the source of truth if another document uses older “government facilities” wording.
