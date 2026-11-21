# Data inclusion and publication policy

> **Status** — binding product and engineering policy.
> **Applies to** — source discovery, acquisition, storage, transformation, canonical records, API, directory, map, statistics, exports, generated reports, and public claims.
> **Decision records** — [ADR 0004](decisions/0004-data-licensing-and-publication-gates.md), [ADR 0008](decisions/0008-publicly-available-data-inclusion.md).
> **Related** — [`DATA-LICENSES.md`](../DATA-LICENSES.md) · [Sources](sources.md) · [Data model](data-model.md)

## 1. What may be published

PhilFacilities publishes qualifying facility records, not every public web page. A dataset may be published when every applicable condition is met:

1. the exact release is **verified** — the file, API response, directory result set, or GIS layer was actually acquired or inspected;
2. it is **publicly available** through an open public route;
3. **no explicit prohibition** applies to the intended storage, transformation, and publication;
4. only non-personal, non-sensitive fields are published;
5. provenance, attribution, the rights basis, and a takedown route are recorded.

Absence of an explicit licence is **not by itself a prohibition**, nor proof of public domain. This policy is a documented product and engineering decision, **not legal advice**, and does not override a licence, terms of use, contract, FOI condition, data-use agreement, privacy law, or other explicit restriction. Explicit restrictions always control. Access-controlled, agreement-bound, personal, sensitive, security-relevant, or expressly non-redistributable data stays excluded or restricted even when some records can be viewed publicly.

## 2. Eligibility checklist

| # | Requirement | Evidence required |
|---|---|---|
| 1 | **Exact release verified** | The actual file/response/layer was acquired or inspected. Record URL, publisher, release label, reference period, retrieval time, checksum, schema, record count, parser version. A homepage or catalogue entry is not a verified release. |
| 2 | **Open public availability** | Available to the general public without authentication, payment, FOI, agreement, token, CAPTCHA, challenge, or access-control bypass. Blocked sources remain blocked. |
| 3 | **No explicit prohibition** | No licence, terms, copyright notice, contract, law, or dataset statement prohibits the intended storage/transformation/publication. A generic "all rights reserved" notice is recorded and assessed; expressive content is not copied, and takedown-on-notice applies. |
| 4 | **Field-level privacy and safety review** | Personal names, contacts, patient/student/beneficiary information, security-sensitive details, and sensitive attributes are excluded, minimized, or generalized. The review and excluded fields are recorded. |
| 5 | **Provenance and attribution** | Publisher, dataset, release, URL, retrieval date, reference period, source ID, attribution text, and rights basis retained and visible. |
| 6 | **Takedown and review** | A takedown route and review date are recorded; objections follow section 9. |
| 7 | **Publication gate** | Dataset redistribution state in `PUBLIC_RIGHTS` **and** publication gate `approved`/`published`. A public URL alone never changes the gate. |

## 3. Rights states

Canonical constants live in `apps/api/philfacilities_api/rights.py`; the API and exports use them directly.

| State | Meaning | Public? |
|---|---|---|
| `publicly_available_verified` | Exact release publicly available and verified; no explicit licence or permission found; no explicit prohibition; reviewed fields only; provenance, attribution, takedown recorded | **Yes**, with approved/published gate |
| `approved_public_redistribution` | Explicit licence or terms permits the recorded scope | **Yes** |
| `approved_with_attribution` | Explicit licence, terms, government-work/public-interest basis, or other instrument permits publication with attribution/conditions | **Yes** |
| `unknown` | No rights review completed | No |
| `review_required` | Access, terms, or intended reuse unresolved | No |
| `restricted_non_redistributable` | Redistribution prohibited, agreement-bound, or unresolved | No |
| `denied` | Rights holder refused the intended use | No |
| `expired` | Previously recorded permission is no longer valid | No |

`unknown` and `review_required` are not permanent exclusions; a reviewer may change them only after completing the checklist and recording evidence.

## 4. What is a qualifying facility

PhilFacilities is one registry of qualifying facilities regardless of ownership: government facilities; private or non-government facilities providing a meaningful public service identified by authoritative records; and public-access civic/community/cultural/recreation/market/transport venues with an authoritative public function. It is **not** a registry of every building, parcel, company, store, restaurant, mall, factory, warehouse, home, or point of interest.

| Inclusion class | Meaning | Public? |
|---|---|---|
| `GOVERNMENT_FACILITY` | Owned, operated, maintained, or officially designated by a public body | Yes, when rights and safety permit |
| `PRIVATE_PUBLIC_SERVICE_PROVIDER` | Private, NGO, non-profit, cooperative, religious/non-profit, or mixed facility providing a qualifying public/essential/regulated service | Yes, when criteria and rights permit |
| `PUBLIC_ACCESS_VENUE` | Civic/community/cultural/recreation/market/transport venue with documented public function | Yes, when criteria and rights permit |
| `DISCOVERY_CANDIDATE` | Institution-level record whose owner or qualifying class is not established; published with an explicit unclassified label | Yes, when rights, privacy, and safety permit |

Publication is gated by rights, privacy, safety, and source verification, not by the presence of an ownership claim. These are filters in the same registry and API, not separate databases; government, private-provider, and public-access-venue counts must be reported separately. A combined total is "all qualifying PhilFacilities records", never "government facilities".

### Mandatory inclusion test

1. **Physical facility or service location** — a place, site, campus, compound, building, branch, counter, station, centre, venue, or locatable unit. An organization, company, agency, route, project, licence without a physical location, or statistical aggregate is not itself a facility.
2. **Qualifying public-interest function** — government/service, education, health, social welfare, emergency/DRRM, community/civic/sports/public space, library/museum/culture, market/food-safety, transport, utilities, environment/agriculture, justice/corrections, or another documented public service approved under the taxonomy.
3. **Authoritative facility-level evidence** — official inventory, public directory of individual facilities, licence/accreditation directory identifying a site, LGU inventory or designation, authoritative GIS layer, FOI-supplied facility dataset, institutional directory with site information, or documented data-sharing release. A company registration, generic map listing, user submission, or organization-only list is insufficient.
4. **Rights, privacy, and safety permit publication** — reviewed separately; explicit restrictions or missing decisions keep records internal or quarantined.

### Explicit exclusions

Exclude by default: ordinary shops, restaurants, hotels, malls, supermarkets, cinemas, entertainment businesses, offices, factories, warehouses, commercial premises, private residences; an organization without a physical facility record; places of worship solely because people can enter; roads, bridges, networks, and linear assets; planned projects without completion evidence; and records whose publication creates unacceptable privacy, safety, or security risk.

**Host-site rule:** a private mall, campus, or office building may contain a qualifying service unit. Represent the unit as the facility and link it to the host/site when evidence supports that relationship; do not add the whole host property automatically.

## 5. Ownership, operation, and access

Ownership is not inclusion class. Capture separately when known: inclusion class; ownership type and owner; operator type and operator; manager/maintainer; host/landlord/site owner; funder; regulator/licensor; accreditor/recognition authority; licence type/scope/status/validity; public access class and conditions; and source evidence for each relationship.

Suggested ownership values: national government, local government, GOCC, public educational institution, other public body, private corporate, private individual/partnership, NGO/non-profit, cooperative, religious/faith-based, public-private joint, unknown. Suggested access values: public/free, public/paid or conditional, service-users only, appointment only, members/students only, staff only, restricted, unknown.

Do not infer owner or operator from regulator, publisher, funder, accreditor, or host. If the source does not establish it, store `UNKNOWN`. A private facility listed by DOH, PhilHealth, DepEd, CHED, TESDA, DSWD, NMIS, PPA, or CAAP may be included as a private provider; it must never be counted as government-owned merely because an agency regulates or accredits it.

## 6. Excluded and restricted data

The following remain excluded unless a separate, explicit, documented basis permits the specific field and use: personal data (employee, school-head, librarian, patient, student, beneficiary, resident names or contacts); private mobile numbers, personal emails, home addresses; patient/student/beneficiary/personnel/security records; security-sensitive layouts, staffing, patrol, surveillance, access-control, or critical-infrastructure details; data obtained through authentication, payment, FOI, agreement, token, CAPTCHA, or bypass; data under an agreement or FOI condition that does not permit redistribution; explicit "do not redistribute"/"internal use only"/"no scraping" prohibitions; unverified records and uninspected schemas; expressive content, photographs, logos, or substantial copied text; raw source files where terms do not permit re-hosting (publish derived fields instead); and records creating unacceptable risk. A negative finding is retained — a blocked source is not deleted merely because it cannot be published.

## 7. Evidence record

For every dataset and release, record: source ID, slug, publisher, owner; exact URL, access method, retrieval time; release label, publication date, reference period; format, size, SHA-256, raw-object location; inspected schema, field names, row count, validation result; licence/terms/"none found" finding with URL and date; the specific basis for concluding no explicit prohibition applies; fields published and excluded plus privacy review; attribution; redistribution state and gate; reviewer, decision date, next review date, and takedown route.

Facility identity rules: one public facility per real-world facility with source rows retained as evidence; aggregation only on independent evidence (shared official ID, or precise location bridge plus consistent name/place); conflicting IDs or places block automatic merges and stay pending; a type mismatch becomes review-only (`cross_type: true`) and an operator-confirmed merge requires `--allow-facility-type-mismatch`; a retired duplicate is an internal `merged` tombstone with moved evidence and change events; survivor chosen deterministically (official source, most official IDs, most source links, oldest); most precise documented location becomes current with its precision preserved; every automatic merge is reversible and merged slugs remain aliases. Full rules are in [Data model](data-model.md) and [Ingestion](ingestion.md).

[`DATA-LICENSES.md`](../DATA-LICENSES.md) is the rights register; [Sources](sources.md) records acquisition evidence; the enforced code gate is authoritative for public exposure.

## 8. Attribution and provenance

Attribution is retained even when not legally required. Public dataset pages, profiles, exports, and API metadata state the original publisher and dataset/release, official URL and retrieval date, applicable licence or "publicly available; no explicit licence found" basis, required attribution or conditions, and known coverage/precision/status limitations. Do not imply endorsement, partnership, or official status, and do not present a source's factual record as a PhilFacilities assertion beyond what the source supports.

## 9. Takedown and correction

If a publisher, data subject, or authorized representative establishes that a release or field should not be public:

1. block new API responses, downloads, statistics, and map/search exposure for the affected scope;
2. remove or restrict affected public artifacts and caches within project control;
3. preserve only what law/licence/agreement permits for audit, or delete as required;
4. record the request, decision, scope, and date in the rights register;
5. publish a corrected release or notice where appropriate;
6. update the source register and generated reports.

Apply the narrowest scope that resolves the issue; a takedown does not require deleting unrelated records.

## 10. Decision examples

| Situation | Decision | Basis |
|---|---|---|
| Public government directory, names and addresses, no licence found | Include reviewed institutional fields | `publicly_available_verified` |
| Public PDF with librarian names, mobile numbers, institutional addresses | Include institution-level fields; withhold personal contacts | `publicly_available_verified`; privacy review |
| Official directory with branch phone/email, no named staff | Publish institutional channels with provenance | Field-level privacy review |
| Named contact person or personal mobile/email | Withhold personal fields; publish institutional channel if separate | Personal-data minimization |
| "All rights reserved" but factual office locations | Publish factual locator fields, record notice, attribution, takedown-on-notice | Documented public-record decision, not public domain |
| Source says "do not copy or redistribute" | Exclude or keep internal | Explicit prohibition controls |
| Source available only through FOI or agreement | Publish only permitted fields/scope | Agreement controls |
| HTTP 403, CAPTCHA, or challenge | Record the block; do not bypass | Access-control rules |
| OpenStreetMap under ODbL 1.0 | Publish with ODbL attribution and share-alike | `approved_with_attribution` |
| DepEd EBEIS with school-head names | Publish institution-level fields only; withhold names | Recorded government-work basis |
| Private hospital in a PhilHealth directory | Include as `PRIVATE_PUBLIC_SERVICE_PROVIDER`; never government-owned | Accreditation is not ownership |
| Private mall hosting a PRC service centre | Include the service unit; link the private host | Host-site rule |
| Road, bridge, proposed project, or ordinary business | Exclude or model as a separate asset/project | Inclusion test fails |

## 11. Implementation and governance

- `apps/api/philfacilities_api/rights.py` defines the vocabulary and `PUBLIC_RIGHTS`; `publicly_available_verified` is public-compatible.
- `dataset_is_publishable()` requires a public rights state **and** an approved/published gate; adding a state to `PUBLIC_RIGHTS` does not bypass the gate.
- API, downloads, statistics, detail source evidence, assertions, school/health observations, map, and search all use the same gate.
- Public membership follows the dataset's latest published release; a failed newer attempt does not displace the last good release.
- An internal-only release may store assertions against a public facility for audit but cannot rewrite canonical identity, location, profiles, or publication state.
- Manual `ingest-file` and `apply-publication-decisions` invocations that publish records must name a reviewer; the command may not infer a rights decision.
- Tests cover the vocabulary, public state, gate requirement, latest-release membership, internal-write protection, and reviewer-recorded decisions.
- No migration is needed for a new `redistribution_status` string; existing releases retain their state until reviewed re-ingestion or explicit update.

This document and [ADR 0008](decisions/0008-publicly-available-data-inclusion.md) amend the restrictive reading of [ADR 0004](decisions/0004-data-licensing-and-publication-gates.md) for verified, publicly available datasets with no explicit prohibition. The rest of ADR 0004 remains in force. Any expansion into a new private-sector facility class requires a documented public-interest rationale, authoritative source, facility-level identity evidence, facility/provider/site/host boundary, ownership and access semantics, privacy and safety risks, publication rights, and the effect on category counts and API clients — update this policy, the data model, the source catalog, and the rights register together.
