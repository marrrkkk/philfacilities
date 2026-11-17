# 09 — Open-Source Governance

## 1. Repository model

Use a public monorepo for web, API, ingestion connectors, schemas, documentation, and deployment examples. Keep deployments independent. Contributors should be able to work on a source adapter without needing to understand the frontend.

## 2. Licensing policy

Recommended starting policy:

| Asset | Proposed license/policy | Gate |
|---|---|---|
| Application code, API, ETL connectors | Apache-2.0 | Confirm project contributors agree and add LICENSE |
| Database schema/migration code | Apache-2.0 | Same code license |
| Original documentation | CC BY 4.0 | Attribute source material and contributors |
| API specification | Publish as part of the project docs; code license applies to project-authored spec unless separately stated | Keep versioned |
| Normalized datasets | Per-source and per-dataset decision under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`; no global default | Documented rights decision per source; explicit restrictions control |
| Raw government source files | Original agency terms or agreement; retain privately unless a publication basis is recorded | Store privately unless the release and fields are approved for publication |
| Third-party derived datasets | Their own license and terms | Do not copy/re-host beyond the permitted scope |

Apache-2.0 is suggested for code because it has an express patent grant. Do not infer that it grants rights to agency data.

## 3. Data rights register

Maintain root `DATA-LICENSES.md` and the source register with:

- source owner/publisher;
- exact source and terms URL;
- retrieval method;
- file/license version;
- attribution requirements;
- commercial-use status if stated;
- modification/redistribution permission;
- FOI/data-use agreement constraints;
- personal-data restrictions;
- reviewer and review date;
- approved publication scope.

Allowed rights/publication decisions:

- `UNKNOWN`: no conclusion reached; do not publish source-derived records by default.
- `REVIEW_REQUIRED`: access, terms, or the intended reuse is unresolved; pause publication.
- `INTERNAL_ONLY`: may be processed internally under documented authority but not republished.
- `METADATA_ONLY`: source link, file metadata, and non-substitutive metadata may be shown; confirm terms.
- `DERIVED_FIELDS_ONLY`: only explicitly approved derived fields may be published.
- `PUBLICLY_AVAILABLE_VERIFIED`: the exact release is verified and publicly available, no explicit prohibition applies, and only reviewed non-personal fields are published with provenance, attribution, and a takedown route. This is a documented product decision, not a claim of public domain.
- `PUBLIC_REUSE_ALLOWED`: documented permission for the defined reuse scope.
- `REVIEW_REQUIRED`: terms ambiguous or conflicting; pause publication.

An FOI response is not automatically an open license. A signed DOH data-use agreement must be read and followed. Verified public availability may support publication even without a licence only when the policy checklist is met; explicit restrictions and agreement conditions control.

The register distinguishes "no explicit licence found" from "explicitly restricted". A verified,
publicly available dataset with no explicit prohibition may be published under
`publicly_available_verified` when the eligibility checklist in
[`14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md) is met.
The code license and the data rights are separate; see [`NOTICE`](../NOTICE).

## 4. Contribution workflow

The contributor guide is [`CONTRIBUTING.md`](../CONTRIBUTING.md). It covers local setup, the full
check list, source-adapter requirements, schema/API change rules, and the pull-request workflow.

- Issues should identify a clear scope and acceptance criteria.
- Source adapter changes must include raw/synthetic fixtures that are safe to redistribute.
- Changes to canonical schema require an ADR or schema-change note.
- Changes to data publication scope require a documented decision under `docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`.
- Pull requests must include relevant tests, docs, and tracker IDs.
- Require review for migrations, identity merges, data deletion, licensing changes, and public data release changes.

## 5. Contributor areas

Label issues by component:

- `area:web`
- `area:api`
- `area:ingestion`
- `area:deped`
- `area:doh`
- `area:philhealth`
- `area:psgc`
- `area:data-model`
- `area:quality`
- `area:docs`
- `area:infra`

Use `good first issue`, `help wanted`, `needs-source-verification`, `needs-legal-review`, `data-quality`, and `breaking-change` where appropriate.

## 6. Source adapter contribution contract

Every connector PR includes:

- official source URL and publisher;
- acquisition method and access restrictions;
- sample file/schema or fixture;
- parser implementation;
- schema mapping;
- validation rules;
- expected source fields and missingness behavior;
- license/terms status;
- tests for schema drift and duplicate runs;
- example ingestion report.

## 7. Security and privacy

- Never commit passwords, API tokens, FOI credentials, or signed agreements containing personal details.
- Keep secrets in environment variables/secret manager.
- Do not collect patient/student/beneficiary personal data.
- Exclude individual personal phone numbers/emails unless clearly institutional and lawfully publishable.
- Treat source-provided contact details as potentially sensitive until reviewed.
- Do not expose raw source payloads publicly unless the release and fields are approved for publication under the data-inclusion policy.
- Provide a security reporting route and dependency update process. The current route and
  limitations are in [`SECURITY.md`](../SECURITY.md).

## 8. Public communication

Clearly say PhilFacilities is an independent community-built data project, not an official government registry, unless a formal government designation/partnership exists. Never use agency logos in a way that implies endorsement. Attribute sources and state that agency records may be incomplete or outdated.
