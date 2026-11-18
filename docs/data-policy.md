# Data inclusion and publication policy

**Status:** binding product and engineering policy.
**Applies to:** source discovery, acquisition, storage, transformation, canonical records, API, directory, map, statistics, exports, generated reports, and public claims.
**Decision records:** [ADR 0004](decisions/0004-data-licensing-and-publication-gates.md), [ADR 0008](decisions/0008-publicly-available-data-inclusion.md).
**Related:** [`DATA-LICENSES.md`](../DATA-LICENSES.md), [sources](sources.md), [data model](data-model.md).

## 1. What may be published

PhilFacilities publishes qualifying facility records, not every public web page. A dataset may be published when every applicable condition is met:

1. the exact release is **verified** — the file, API response, directory result set, or GIS layer was actually acquired or inspected;
2. it is **publicly available** through an open public route;
3. **no explicit prohibition** applies to the intended storage, transformation, and publication;
4. only non-personal, non-sensitive fields are published;
5. provenance, attribution, the rights basis, and a takedown route are recorded.

Absence of an explicit licence is **not by itself a prohibition**. It is also not proof that the data is in the public domain. This policy is a documented product and engineering decision about which public-interest records PhilFacilities will publish. It is **not legal advice** and does not override a licence, terms of use, contract, FOI condition, data-use agreement, privacy law, or other explicit restriction.

Explicit restrictions always control. Access-controlled, agreement-bound, personal, sensitive, security-relevant, or expressly non-redistributable data stays excluded or restricted even when some records can be viewed publicly.

## 2. Eligibility checklist

| # | Requirement | Evidence required |
|---|---|---|
| 1 | **Exact release verified** | The actual file, API response, directory result set, or GIS layer was acquired or inspected. Record source URL, publisher, release label, reference period, retrieval time, checksum where applicable, schema/fields, record count, and parser version. A homepage, news item, catalogue entry, or screenshot is not a verified release. |
| 2 | **Open public availability** | The exact release is available to the general public without authentication, payment, FOI request, negotiated agreement, token, CAPTCHA, Cloudflare challenge, or access-control bypass. A normal browser download or public API response is acceptable. Blocked or challenge-protected sources remain blocked. |
| 3 | **No explicit prohibition** | No licence, terms page, copyright notice, contract, agreement, law, or dataset-level statement prohibits the intended storage, transformation, or publication. An explicit prohibition controls. A generic copyright or “all rights reserved” notice is recorded and assessed; it is not treated as an automatic bar to publishing factual, non-expressive facility fields, but expressive content is not copied and takedown-on-notice applies. |
| 4 | **Field-level privacy and safety review** | Personal names, personal contact details, patient/student/beneficiary information, security-sensitive details, and other sensitive attributes are excluded, minimized, or generalized. Institutional contact channels are preferred. The review and excluded fields are recorded. |
| 5 | **Provenance and attribution** | Publisher, dataset, release, official URL, retrieval date, reference period, source identifier, attribution text, and rights basis are retained and visible with the published data. |
| 6 | **Takedown and review** | A takedown route and review date are recorded. A publisher objection is handled through the withdrawal process in section 9. |
| 7 | **Publication gate** | The dataset's redistribution state is in `PUBLIC_RIGHTS` **and** its publication gate is `approved` or `published`. A public URL alone never changes the gate. |

## 3. Rights states

The canonical constants live in `apps/api/philfacilities_api/rights.py`. The API and bulk exports use these values directly.

| State | Meaning | Public? |
|---|---|---|
| `publicly_available_verified` | The exact release is publicly available and verified; no explicit licence or permission was found; no explicit prohibition applies; only reviewed fields are published; provenance, attribution, and a takedown route are recorded. | **Yes**, when the publication gate is approved or published |
| `approved_public_redistribution` | An explicit licence or terms instrument permits the recorded public redistribution scope. | **Yes** |
| `approved_with_attribution` | An explicit licence, terms statement, government-work/public-interest basis, or other recorded instrument permits publication with attribution or conditions. | **Yes** |
| `unknown` | No rights review has been completed. | No |
| `review_required` | Access, terms, or the intended reuse remains unresolved or ambiguous. | No |
| `restricted_non_redistributable` | Redistribution is prohibited, agreement-bound, or unresolved in a way that keeps the release internal. | No |
| `denied` | The rights holder refused the intended use. | No |
| `expired` | A previously recorded permission is no longer valid. | No |

`unknown` and `review_required` are not permanent exclusions. A reviewer may change them to a public state only after completing the eligibility checklist and recording the evidence. Until then, the records remain internal or blocked.

## 4. What is a qualifying facility

PhilFacilities is one registry of qualifying facilities regardless of ownership. It includes government facilities, private or non-government facilities that provide a meaningful public service and are identified by authoritative records, and public-access civic/community/cultural/recreation/market/transport venues with an authoritative public function.

It is **not** a registry of every building, parcel, company, store, restaurant, mall, factory, warehouse, home, or point of interest.

Every publishable record carries one inclusion class:

| Value | Meaning | Public? |
|---|---|---|
| `GOVERNMENT_FACILITY` | Owned, operated, maintained, or officially designated as a government/public facility by a public body | Yes, when source rights and safety permit |
| `PRIVATE_PUBLIC_SERVICE_PROVIDER` | Private, NGO, non-profit, cooperative, religious/non-profit, or mixed facility providing a qualifying public/essential/regulated service | Yes, when inclusion criteria and source rights permit |
| `PUBLIC_ACCESS_VENUE` | Civic/community/cultural/recreation/market/transport venue with documented public access/function | Yes, when inclusion criteria and source rights permit |
| `DISCOVERY_CANDIDATE` | Institution-level record whose owner, operator, or qualifying class is not established by the source; published with an explicit unclassified label | Yes, when source rights, privacy, and safety permit |

Publication is gated by rights, privacy, safety, and source verification, not by the presence of an ownership claim. Unclassified records are published and labelled so they are never presented as government-owned or privately owned.

These are filters in the same registry and API, not separate databases. Government, private-provider, and public-access-venue counts must be reported separately. A combined total is “all qualifying PhilFacilities records”, never “government facilities”.

### Mandatory inclusion test

A candidate must meet every applicable test:

1. **It is a physical facility or service location.** The source identifies a place, site, campus, compound, building, branch, service counter, station, centre, venue, or other locatable facility unit. An organization, company, agency, route, project, licence record without a physical location, geographic area, or general statistical count is not itself a facility.
2. **It has a qualifying public-interest function.** Government administration or public-facing service; education, learning, or training; healthcare or regulated health services; social welfare or protective services; emergency response, disaster preparedness, or officially designated evacuation use; community, civic, sports, recreation, or public-space function; public library, museum, archive, cultural, or heritage function; public market, food-safety, or regulated supply-chain function; transport, port, airport, terminal, or mobility service; water, energy, waste, sanitation, or other essential utility service; environmental, agricultural, fisheries, or public-resource service; justice, correctional, or legal public service subject to security limits; another documented public, community, institutional, or essential service approved under the taxonomy.
3. **It has authoritative facility-level evidence.** Official government inventory; official public directory listing individual facility locations; official licence, registration, accreditation, or recognized-provider directory that identifies a physical site; official LGU inventory or ordinance/designation; authoritative GIS layer with usable facility metadata; official FOI response supplying a specific facility dataset; official institutional directory with facility-level address/site information; documented data-sharing release from a responsible public body. A company registration, unrelated business permit, generic map listing, user submission, or list of organizations without physical facility identities is not sufficient by itself.
4. **Rights, privacy, and safety permit publication.** Acquisition, storage, transformation, derived outputs, and public redistribution are reviewed separately. If an explicit restriction applies or no publication decision has been recorded, keep the records internal or quarantined.

### Explicit exclusions

Exclude by default:

- ordinary shops, restaurants, cafes, hotels, resorts, malls, supermarkets, cinemas, and entertainment businesses solely because they are open to customers;
- ordinary offices, office towers, coworking spaces, factories, industrial buildings, warehouses, and commercial premises;
- private residential buildings, houses, gated subdivisions, and private property;
- a company, organization, school operator, hospital corporation, agency, or programme without a physical facility record;
- places of worship solely because people can enter to worship — a specific officially designated evacuation/community service function may be represented as a dated function if supported by a source;
- roads, bridges, drainage networks, power lines, water distribution networks, and other linear/network assets (use the related infrastructure-asset model);
- planned projects as operating facilities without completion/commissioning/operation evidence;
- records where publishing the location or attributes creates unacceptable privacy, safety, or security risk.

**Host-site rule:** a private mall, university campus, office building, or other host property may contain a qualifying service unit. Represent the service unit as the facility and link it to the host/site when evidence supports that relationship. Do not add the whole host property automatically.

## 5. Ownership, operation, and access

Ownership is not inclusion class. Capture these separately when known:

- `inclusion_class`;
- `ownership_type` and owner entity;
- `operator_type` and operator entity;
- manager/maintainer;
- host/landlord/site owner;
- funder/project sponsor;
- regulator/licensor;
- accreditor/recognition authority;
- licence/registration/accreditation type, scope, status, and validity;
- `public_access_class` and conditions;
- source assertion/evidence for each relationship.

Suggested ownership values: national government, local government, GOCC, public educational institution, other public body, private corporate, private individual/partnership, NGO/non-profit, cooperative, religious/faith-based organization, public-private joint, unknown.

Suggested access values: public/free, public/paid or conditional, service-users only, appointment only, members/students only, staff only, restricted, unknown.

Do not infer owner or operator from regulator, source publisher, funder, accreditor, or host. If the source does not establish it, store `UNKNOWN`. A private facility listed by DOH, PhilHealth, DepEd, CHED, TESDA, DSWD, NMIS, PPA, CAAP, or another regulator may be included as a private provider; it must never be counted as government-owned merely because a government agency regulates or accredits it.

## 6. Excluded and restricted data

The following remain excluded from public release unless a separate, explicit, documented basis permits the specific field and use:

- personal data, including employee, school-head, librarian, patient, student, beneficiary, and resident names or contact details;
- private mobile numbers, personal email addresses, and home addresses;
- patient, student, beneficiary, personnel, or operational security records;
- security-sensitive layouts, staffing, patrol, surveillance, access-control, vulnerability, or critical-infrastructure details;
- data obtained through authentication, payment, FOI, a negotiated agreement, a token, a CAPTCHA, or an access-control bypass;
- data covered by a data-use agreement or FOI condition that does not permit public redistribution;
- data with an explicit “do not redistribute”, “internal use only”, “no scraping”, or equivalent prohibition;
- unverified records, homepage-only claims, catalogue entries without records, and datasets whose schema or coverage has not been inspected;
- expressive content, photographs, logos, campaign graphics, or substantial text copied from a source;
- raw source files where the source terms do not permit public re-hosting — publish derived facility fields and metadata instead;
- records whose publication would create an unacceptable privacy, safety, or security risk.

A negative finding is retained. A blocked source is not deleted merely because it cannot be published.

## 7. Evidence record

For every dataset and release, record at least:

- source ID, dataset slug, publisher, and data owner;
- exact official URL, access method, and retrieval time;
- release label, source publication date, and reference period;
- file format, size, SHA-256, and raw-object location where applicable;
- inspected schema, original field names, row count, and validation result;
- licence, terms, notice, agreement, or “none found” finding, with the URL and date checked;
- the specific basis for concluding that no explicit prohibition applies;
- fields published, fields excluded, and the personal-data/security review;
- attribution text and provenance display;
- redistribution state and publication gate;
- reviewer, decision date, next review date, and takedown route.

### Facility identity

- One public facility record represents one real-world facility. Source rows remain attached as evidence; they are not deleted when records are aggregated.
- Records are aggregated only on independent evidence: a shared official identifier, or a precise location bridge plus a consistent name and place. A similar name alone never merges two facilities, because two places can share a name.
- Conflicting official identifiers or contradictory places block an automatic merge; the pair stays as a pending candidate for review.
- A retired duplicate is an internal `merged` tombstone, not a public record. Its links, locations, profiles, observations, assertions, and history move to the survivor, and change events record the merge.
- The surviving record is chosen deterministically: official source first, then the most official identifiers, then the most source links, then the oldest record.
- The survivor keeps the most precise documented location. The promoted point keeps its recorded precision and method; the previous current location stays as history rather than being deleted.
- A duplicate profile only fills a survivor's missing values. The backfill is recorded so undo can reverse it, and undo refuses when a later edit changed the value.
- Every automatic merge is reversible with `match-candidates-undo-merge`. A merged facility's slug remains an alias to the survivor, so previously published links do not break.

[`DATA-LICENSES.md`](../DATA-LICENSES.md) is the rights register. [Sources](sources.md) records the acquisition evidence. The enforced code gate is authoritative for public exposure.

## 8. Attribution and provenance

Attribution is retained even when a source does not legally require it. Public dataset pages, facility profiles, exports, and API metadata state:

- the original publisher and dataset/release;
- the official source URL and retrieval date;
- the applicable licence or the “publicly available; no explicit licence found” basis;
- any required attribution or conditions;
- known coverage, precision, and status limitations.

Do not imply agency endorsement, partnership, or official status. Do not present a source's factual record as a PhilFacilities assertion beyond what the source supports.

## 9. Takedown and correction

If a publisher, data subject, or authorized representative establishes that a release or field should not be public:

1. block new API responses, downloads, statistics, and map/search exposure for the affected scope;
2. remove or restrict affected public artifacts and caches within the project's control;
3. preserve only what the applicable law, licence, or agreement permits for audit, or delete it as required;
4. record the request, decision, scope, and date in the rights register;
5. publish a corrected release or notice where appropriate;
6. update the source register and generated reports.

A takedown does not require deleting unrelated records from the same source. Apply the narrowest scope that resolves the issue.

## 10. Decision examples

| Situation | Decision | Basis |
|---|---|---|
| Public government directory lists facility names and addresses; no licence or terms page is found | Include reviewed institutional fields | `publicly_available_verified` |
| Public PDF includes librarian names, mobile numbers, and institutional addresses | Include institution-level fields; withhold personal contact fields | `publicly_available_verified`; privacy review |
| Official directory lists a branch telephone, branch email, and no named staff contact | Publish the institutional contact channels with source provenance | `publicly_available_verified`; field-level privacy review |
| Directory includes a named contact person, personal mobile number, or personal email | Withhold the personal fields; publish only the institutional channel if one exists separately | Personal-data minimization |
| Public page states “all rights reserved” but publishes factual office locations | Publish only factual locator fields, record the notice, retain attribution, apply takedown-on-notice | Documented public-record inclusion decision; not a claim of public domain |
| Source explicitly says “do not copy or redistribute” | Exclude or keep internal | Explicit prohibition controls |
| Source is available only through FOI or a signed data-use agreement | Publish only the fields and scope the agreement permits | Agreement controls |
| Source returns HTTP 403, a CAPTCHA, or a Cloudflare challenge | Record the block; do not bypass | Access-control and security rules |
| OpenStreetMap extract under ODbL 1.0 | Publish with ODbL attribution and share-alike | `approved_with_attribution` |
| DepEd EBEIS public result set with school-head names | Publish only institution-level fields with attribution; withhold personal names | Recorded government-work/public-interest basis; `approved_with_attribution` |
| Private hospital with a site listed in a PhilHealth directory | Include as `PRIVATE_PUBLIC_SERVICE_PROVIDER`; never count as government-owned | Accreditation is not ownership |
| Private mall hosting a PRC service centre | Include the PRC service unit; link the private host | Host-site rule |
| Ordinary restaurant or shopping mall | Exclude by default | Retail property alone does not satisfy the inclusion test |
| Road or bridge | Separate related asset | Not a facility record |
| Proposed evacuation-centre construction project | Project candidate only | Does not prove a completed facility exists |

## 11. Implementation and governance

- `apps/api/philfacilities_api/rights.py` defines the vocabulary and `PUBLIC_RIGHTS`. `publicly_available_verified` is public-compatible.
- `dataset_is_publishable()` requires both a public rights state and an approved/published gate. Adding a state to `PUBLIC_RIGHTS` does not bypass the gate.
- The API, downloads, statistics, facility detail source evidence, assertions, school/health observations, and map/search queries all use the same rights gate.
- Public membership follows the dataset's latest published release. A facility removed by a newer successful release is no longer current, while a failed or quarantined newer attempt does not displace the last good release.
- An internal-only release may store assertions and child rows against a public facility for audit, but it cannot rewrite that facility's canonical identity, current location, profiles, or publication state. Its rows remain read-gated.
- A manual `ingest-file` or `apply-publication-decisions` invocation that makes records public must name a reviewer; the reviewer and note are recorded on the publication gate. The command may not infer a rights decision.
- Tests cover the vocabulary, the public state, the requirement that rights alone are insufficient without an approved gate, latest-release membership, internal-release write protection, and reviewer-recorded decisions.
- The web data and dictionary pages list the state and explain the policy in plain language.
- No database migration is required for a new `redistribution_status` string; the column is a plain string. Existing releases retain their recorded state until a reviewed re-ingestion or explicit state update.

Any expansion into a new private-sector facility class requires a documented public-interest rationale, the authoritative source, facility-level identity evidence, the facility/provider/site/host boundary, ownership and access semantics, privacy and safety risks, publication rights, and the effect on category counts and API clients. Update this policy, the data model, the source catalog, and the rights register together.

This document and ADR 0008 amend the restrictive reading of ADR 0004 for verified, publicly available datasets with no explicit prohibition. The rest of ADR 0004 remains in force: code and data rights are separate; source-data rights are recorded per dataset and release; publication is gated in code; internal-only and blocked sources stay out of public outputs; synthetic fixtures remain labelled and confined to tests.
