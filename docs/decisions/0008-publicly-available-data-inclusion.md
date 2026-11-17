# 0008 — Include verified, publicly available data with no explicit prohibition

- **Status:** Accepted
- **Date:** 2026-11-15
- **Amends:** [0004](0004-data-licensing-and-publication-gates.md)

## Context

ADR 0004 required a recorded redistribution decision before publication. In practice,
several documents interpreted “no explicit licence or written permission” as an automatic
bar. That conflated three different situations:

1. a dataset that is publicly available and carries no restriction;
2. a dataset whose terms are simply unknown because no one has reviewed them; and
3. a dataset that is explicitly restricted, agreement-bound, or access-controlled.

The first category includes many official Philippine government directories and
public-interest sources. Blocking all of them prevented the project from publishing
verified, already-public facility records, even when the intended use was limited to
factual, institutional fields and personal data was withheld.

## Decision

Add a public-compatible rights state, `publicly_available_verified`, and apply the
following rule:

> A dataset may be included and published when its exact release is verified, it is
> publicly available through an open public route, and no explicit prohibition applies to
> the intended storage, transformation, and publication — provided that only reviewed
> non-personal, non-sensitive fields are published and provenance, attribution, and a
> takedown route are recorded.

Explicit restrictions always control. `unknown` and `review_required` remain non-public
until a reviewer completes the checklist and sets a public state. Access-controlled,
FOI/agreement-bound, personal, sensitive, security-relevant, and expressly
non-redistributable data remain excluded or restricted.

This decision:

- does **not** declare any dataset to be public domain;
- does **not** claim that the publisher has granted a licence;
- is a documented product and engineering policy, not legal advice;
- does **not** authorize bypassing authentication, payment, CAPTCHA, Cloudflare, or terms
  acceptance;
- does **not** relax the separate code licence or the code/data rights separation.

The operational policy, eligibility checklist, evidence requirements, and takedown process
are in [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](../14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md).

## Consequences

- More verified public datasets are eligible for publication without waiting for a formal
  licence that may never exist.
- Every such decision must record the exact release, the “no explicit prohibition”
  finding, the fields published and excluded, the attribution, and the reviewer.
- The public API gains one additional public-compatible rights state; the publication gate
  still requires an approved or published release.
- `unknown` and `review_required` are review states, not permanent rejections, but they
  remain non-public until reviewed.
- A publisher objection triggers the documented takedown process rather than a silent data
  edit.
- Older documents that say “do not publish until terms permit” are read as requiring a
  documented rights decision under this policy, not necessarily an explicit licence.

## Evidence

- [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](../14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md)
- [`DATA-LICENSES.md`](../../DATA-LICENSES.md)
- `apps/api/philfacilities_api/rights.py`
- `tests/test_rights.py`
- [`docs/decisions/0004-data-licensing-and-publication-gates.md`](0004-data-licensing-and-publication-gates.md)
