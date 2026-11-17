# 14 — Data Inclusion and Publication Policy

**Status:** Binding product and engineering policy.  
**Applies to:** source discovery, acquisition, storage, transformation, canonical records, API, directory, map, statistics, exports, generated reports, and public claims.  
**Decision record:** [ADR 0008](decisions/0008-publicly-available-data-inclusion.md).  
**Related:** [`DATA-LICENSES.md`](../DATA-LICENSES.md), [`docs/09-OPEN-SOURCE-GOVERNANCE.md`](09-OPEN-SOURCE-GOVERNANCE.md), [`docs/decisions/0004-data-licensing-and-publication-gates.md`](decisions/0004-data-licensing-and-publication-gates.md), [`expand/docs/09-DATA-GOVERNANCE.md`](../expand/docs/09-DATA-GOVERNANCE.md).

## 1. Policy decision

PhilFacilities may include and publish a dataset even when the publisher has not issued an explicit reuse licence or written permission, provided that:

1. the exact release is **verified**;
2. it is **publicly available** through an open public route;
3. **no explicit prohibition** applies to the intended storage, transformation, and publication;
4. only non-personal, non-sensitive fields are published; and
5. provenance, attribution, the rights basis, and a takedown route are recorded.

Absence of an explicit licence is **not by itself a prohibition**. It is also not proof that the data is in the public domain. This policy is a documented product and engineering decision about which public-interest records PhilFacilities will publish. It is **not legal advice**, does not declare any dataset to be public domain, and does not override a licence, terms of use, contract, FOI condition, data-use agreement, privacy law, or other explicit restriction.

Explicit restrictions always control. A dataset that is access-controlled, agreement-bound, personal, sensitive, security-relevant, or expressly non-redistributable remains excluded or restricted even if some of its records can be viewed publicly.

## 2. Eligibility checklist

A dataset may be published under this policy only when every applicable item is satisfied and evidenced.

| # | Requirement | Evidence required |
|---|---|---|
| 1 | **Exact release verified** | The actual file, API response, directory result set, or GIS layer was acquired or inspected. Record the source URL, publisher, release label, reference period, retrieval time, checksum where applicable, schema/fields, record count, and parser version. A homepage, news item, catalogue entry, or screenshot is not a verified release. |
| 2 | **Open public availability** | The exact release is available to the general public without authentication, payment, FOI request, negotiated agreement, token, CAPTCHA, Cloudflare challenge, or access-control bypass. A normal browser download or public API response is acceptable. Blocked or challenge-protected sources remain blocked. |
| 3 | **No explicit prohibition** | No licence, terms page, copyright notice, contract, agreement, law, or dataset-level statement prohibits the intended storage, transformation, or publication. An explicit prohibition controls. A generic copyright or “all rights reserved” notice is recorded and assessed; it is not treated as an automatic bar to publishing factual, non-expressive facility fields, but expressive content is not copied and takedown-on-notice applies. |
| 4 | **Field-level privacy and safety review** | Personal names, personal contact details, patient/student/beneficiary information, security-sensitive details, and other sensitive attributes are excluded, minimized, or generalized. Institutional contact channels are preferred. The review and excluded fields are recorded. |
| 5 | **Provenance and attribution** | The publisher, dataset, release, official URL, retrieval date, reference period, source identifier, attribution text, and rights basis are retained and visible with the published data. |
| 6 | **Takedown and review** | A takedown route and review date are recorded. A publisher objection is handled through the withdrawal process in section 7. |
| 7 | **Publication gate** | The dataset's redistribution state is in `PUBLIC_RIGHTS` **and** its publication gate is `approved` or `published`. A public URL alone never changes the gate. |

## 3. Rights states

The canonical constants are in [`apps/api/philfacilities_api/rights.py`](../apps/api/philfacilities_api/rights.py). The public API and bulk exports use these states directly.

| State | Meaning | Public? |
|---|---|---|
| `publicly_available_verified` | The exact release is publicly available and verified; no explicit licence or permission was found; no explicit prohibition applies; only reviewed fields are published; provenance, attribution, and a takedown route are recorded. This is the state for the policy in this document. | **Yes**, when the publication gate is approved or published |
| `approved_public_redistribution` | An explicit licence or terms instrument permits the recorded public redistribution scope. | **Yes** |
| `approved_with_attribution` | An explicit licence, terms statement, government-work/public-interest basis, or other recorded instrument permits publication with attribution or conditions. | **Yes** |
| `unknown` | No rights review has been completed. | No |
| `review_required` | Access, terms, or the intended reuse remains unresolved or ambiguous. | No |
| `restricted_non_redistributable` | Redistribution is prohibited, agreement-bound, or unresolved in a way that keeps the release internal. | No |
| `denied` | The rights holder refused the intended use. | No |
| `expired` | A previously recorded permission is no longer valid. | No |

`unknown` and `review_required` are not permanent exclusions. A reviewer may change them to a public state only after completing the eligibility checklist and recording the evidence. Until then, the records remain internal or blocked.

## 4. Excluded and restricted cases

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
- raw source files where the source terms do not permit public re-hosting; publish derived facility fields and metadata instead;
- records whose publication would create an unacceptable privacy, safety, or security risk.

A negative finding is retained. A blocked source is not deleted merely because it cannot be published.

## 5. Evidence record

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

The rights register in [`DATA-LICENSES.md`](../DATA-LICENSES.md) and the source register in [`docs/03-SOURCE-REGISTER.md`](03-SOURCE-REGISTER.md) are the operational records. The enforced code gate is authoritative for public exposure.

## 6. Attribution and provenance

Attribution is retained even when a source does not legally require it. Public dataset pages, facility profiles, exports, and API metadata should state:

- the original publisher and dataset/release;
- the official source URL and retrieval date;
- the applicable licence or the “publicly available; no explicit licence found” basis;
- any required attribution or conditions;
- known coverage, precision, and status limitations.

Do not imply agency endorsement, partnership, or official status. Do not present a source's factual record as a PhilFacilities assertion beyond what the source supports.

## 7. Takedown and correction

If a publisher, data subject, or authorized representative establishes that a release or field should not be public:

1. block new API responses, downloads, statistics, and map/search exposure for the affected scope;
2. remove or restrict affected public artifacts and caches within the project's control;
3. preserve only what the applicable law, licence, or agreement permits for audit, or delete it as required;
4. record the request, decision, scope, and date in the rights register;
5. publish a corrected release or notice where appropriate;
6. update the source register, tracker, and generated reports.

A takedown does not require deleting unrelated records from the same source. Apply the narrowest scope that resolves the issue.

## 8. Decision examples

| Situation | Decision | Basis |
|---|---|---|
| Public government directory lists facility names and addresses; no licence or terms page is found | Include reviewed institutional fields | `publicly_available_verified` |
| Public PDF includes librarian names, mobile numbers, and institutional addresses | Include institution-level fields; withhold personal contact fields | `publicly_available_verified`; privacy review |
| Public page states “all rights reserved” but publishes factual office locations | Publish only factual locator fields, record the notice, retain attribution, and apply takedown-on-notice | Documented public-record inclusion decision; not a claim of public domain |
| Source explicitly says “do not copy or redistribute” | Exclude or keep internal | Explicit prohibition controls |
| Source is available only through FOI or a signed data-use agreement | Publish only the fields and scope the agreement permits | Agreement controls |
| Source returns HTTP 403, a CAPTCHA, or a Cloudflare challenge | Record the block; do not bypass | Access-control and security rules |
| OpenStreetMap extract under ODbL 1.0 | Publish with ODbL attribution and share-alike | `approved_with_attribution` |
| DepEd EBEIS public result set with school-head names | Publish only institution-level fields with attribution; withhold personal names | Recorded government-work/public-interest basis; `approved_with_attribution` in the current registry |

## 9. Implementation

- `apps/api/philfacilities_api/rights.py` defines the vocabulary and `PUBLIC_RIGHTS`. `publicly_available_verified` is a public-compatible state.
- `dataset_is_publishable()` requires both a public rights state and an approved/published gate. Adding a state to `PUBLIC_RIGHTS` does not bypass the gate.
- The API, downloads, statistics, facility detail source evidence, and map/search queries all use the same rights gate.
- Tests cover the vocabulary, the new state, and the requirement that rights alone are insufficient without an approved gate.
- The web data and dictionary pages list the state and explain the policy in plain language.
- No database migration is required for a new `redistribution_status` string; the column is a plain string. Existing stored releases retain their recorded state until a reviewed re-ingestion or explicit state update.

## 10. Relationship to earlier policy

This document and ADR 0008 amend the restrictive reading of ADR 0004 for verified, publicly available datasets with no explicit prohibition. The rest of ADR 0004 remains in force:

- code and data rights are separate;
- source-data rights are recorded per dataset and release;
- publication is gated in code;
- internal-only and blocked sources stay out of public outputs;
- synthetic fixtures remain labelled and confined to tests.

Where an older document says that a dataset must not be published until an explicit licence or FOI agreement permits it, read that statement as requiring a documented rights decision under this policy. An explicit licence is one sufficient basis; verified public availability with no explicit prohibition is another.
