# 09 — Data Governance, Rights, Privacy, and Public Corrections

## 1. Data rights are source-specific

The code licence does not grant rights to agency datasets or private-provider records published by a regulator. The ownership-inclusive scope does not weaken source-specific rights requirements. A file may be viewable/downloadable while an explicit agreement or other restriction still limits redistribution, derivative publication, or long-term retention. Equally, the absence of an explicit licence is not by itself a prohibition: a verified, publicly available release with no explicit restriction may be published under the root [data inclusion and publication policy](../../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md) with reviewed institutional fields, provenance, attribution, and takedown-on-notice.

For every dataset and release, separately establish:

- access permission;
- download/acquisition permission;
- storage/retention permission;
- transformation/normalization permission;
- publication of derived facts permission;
- public redistribution permission or, where no explicit licence exists, the verified public-availability basis and absence of an explicit prohibition;
- attribution requirements;
- field-level exclusions;
- privacy/security restrictions;
- agreement version, effective date, and expiration.

If a source is access-controlled, governed by an explicit restriction, or unclear after acquiring the exact release, keep the source release internal/quarantined and seek clarification from the publisher. Do not guess that government data is all public domain, and do not treat silence as permission.

## 2. Source rights states

Use:

- `UNKNOWN`
- `REVIEW_REQUIRED`
- `PUBLICLY_AVAILABLE_VERIFIED`
- `APPROVED_INTERNAL_USE`
- `APPROVED_DERIVED_ONLY`
- `APPROVED_PUBLIC_REDISTRIBUTION`
- `APPROVED_WITH_ATTRIBUTION`
- `RESTRICTED_NON_REDISTRIBUTABLE`
- `DENIED`
- `EXPIRED`

`PUBLICLY_AVAILABLE_VERIFIED` means the exact release was acquired through an open public route, its records/schema were inspected, no explicit prohibition applies, only reviewed non-personal fields are published, and provenance, attribution, and a takedown route are recorded. It is a documented product decision, not a claim of public domain, and it does not bypass the release publication gate.

Publication should be field-aware where necessary. An agreement may permit publication of facility name and municipality but not precise coordinates, private contacts, or other attributes.

## 3. Publication states

Use:

- `BLOCKED`
- `INTERNAL_ONLY`
- `QUARANTINED`
- `APPROVED`
- `PUBLISHED`
- `WITHDRAWN`

No record may appear in public API, map, search, counts, bulk downloads, or client-side bundles unless the relevant source release/field is approved for public use. The canonical `publicly_available_verified` state is public-compatible, but the release must still be `APPROVED` or `PUBLISHED`, and field-level review still applies.

## 4. Source-specific caution areas

- DOH NHFR FOI files may be supplied under a signed data-release/use agreement. Review the actual agreement before publication.
- DepEd files have their own download/terms flow. Read and store the exact terms accepted for the release.
- PhilHealth files are public provider directories. The public disclaimer permits use/reproduction for educational or informative purposes; 26 provider-category releases are published with attribution (28,207 accreditations). The Antenatal release was re-ingested with the corrected parser (3,221 rows, ending at page 120); its earlier 6,562-row annex double-count remains withdrawn.
- DepEd EBEIS is a public result set. The current source release is published for institution-level fields with attribution and school-head names withheld; canonical rows remain internal pending field-level mapping/privacy review.
- PHLPost publishes 1,272 factual locator facilities under a recorded product decision; the page's copyright notice is recorded and an earlier review-required release is retained internally.
- Geoportal restrictions are layer-specific. The Geoportal inventory labels data restrictions, and the download guide says contact the data owner for layers that are restricted or not downloadable.
- DSWD accreditation lists may include private social welfare agencies. Do not classify them as government-owned.
- National Library directories may include named librarians/in-charge and personal contact information. Publish institution-level details and official institutional contact channels where possible; assess necessity and legal basis before publishing personal names/mobile/email.
- Police, correctional, emergency, and utility information may contain sensitive security or critical-infrastructure details. Publish only authorized public-facing facility information.

## 5. Privacy and data minimization

PhilFacilities is a facility database, not a people database.

Do not ingest or publish:

- patient/student/beneficiary/resident information;
- employee rosters or personal contact details unless clearly necessary, lawfully public, and reviewed;
- private mobile numbers or personal email addresses merely because they appear in a public PDF;
- sensitive security staffing, patrol, surveillance, access-control, or vulnerability information;
- non-public operational status or capacity data.

Prefer generic institutional contact channels over personal contacts.

Apply the Data Privacy Act principles: transparency, legitimate purpose, and proportionality. Conduct a privacy review where a source includes personal information.

## 6. Attribution and provenance

Every public dataset page and every facility profile should provide:

- original agency;
- dataset/document name;
- official source URL;
- source reference date;
- PhilFacilities retrieval/publication date;
- source record identifier where publication permits;
- applicable licence/terms/attribution;
- location precision and known caveats.

Bulk downloads must include a README/data dictionary and source attribution metadata.

## 7. Security and sensitive places

Before publishing sensitive facility categories, review:

- whether the facility is a public service location or protected installation;
- whether precise coordinates are already officially public;
- whether publishing attributes increases a security risk;
- whether the source restricts location disclosure;
- whether only a generalized location or municipality-level record should be exposed.

Do not publish security layout, restricted entrances, guard assignments, operational capacity, equipment stores, system vulnerabilities, or other sensitive details.

## 8. Corrections and disputes

Maintain a correction process that distinguishes:

- source error;
- PhilFacilities parsing/normalization error;
- entity matching error;
- outdated source;
- public user correction proposal;
- disputed ownership/operator/status.

A user correction does not override an official source automatically. Keep the current record and correction proposal separate until reviewed. If an official source later confirms the change, publish a new sourced assertion and change event.

## 9. Withdrawal and takedown

If an agency establishes that a field/release was published contrary to a restriction or without a recorded publication basis:

1. block new API responses and bulk exports for the affected scope;
2. remove or restrict affected public artifacts/caches;
3. preserve only what the agreement/law permits for audit or delete as required;
4. document the decision and source communication;
5. generate a corrected release/notice;
6. update `DATA-RIGHTS-REGISTER.md` and the release manifest.


## 10. Ownership-inclusive publication and representation

PhilFacilities includes qualifying private facilities in the same registry as government facilities, but source rights and factual representation remain strict. For each private provider, verify the authoritative source relationship (licence, registration, accreditation, recognition, contract or public-service designation), the facility-level identity, scope and validity period. Do not imply government ownership, government operation, endorsement, service quality, current operational status or real-time availability.

Use separate inclusion-class, ownership, operator, manager, host, regulator/accreditor and access fields. If the source does not establish an attribute, publish `UNKNOWN` or omit the field rather than infer it. Use separate metrics for government facilities, private public-service providers and public-access venues. A combined total must be labelled as the full qualifying registry.

Private facilities are not automatically in scope merely because they are listed in a company registry, licensed for an unrelated purpose, appear on a map, or are open to customers. Apply the inclusion criteria in `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`. Where a private facility is included, publish only the minimum fields needed for the public-service purpose and permitted by the exact source terms or the verified-public-availability policy.
