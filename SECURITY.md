# Security policy

PhilFacilities is a real-data public read service in active development. It is not certified for production use, and no external penetration test or formal legal/privacy review has been completed. The working database contains public records from sources with a recorded publication decision, alongside internal-only records that are excluded from public responses.

## Supported versions

Security fixes are applied to the default branch. No versioned support window is published.

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.** Do not include credentials, signed data-use agreements, personal data, restricted source rows, or exploitable details in a public issue or pull request.

When this repository is hosted on GitHub and private vulnerability reporting is enabled, use the repository's **Security → Report a vulnerability** route. If that route is unavailable, contact the repository maintainers through the private channel published with the repository. Do not invent or rely on an unverified security email address.

Please include, where safe:

- the affected component (`web`, `api`, `ingest`, `api-client`, database, or operations);
- the version or commit;
- a minimal reproduction or proof of concept using synthetic data;
- the impact you believe is possible;
- any suggested remediation or disclosure constraints.

Maintainers will acknowledge reports as capacity allows, validate the issue, and coordinate a fix and disclosure. No response-time SLA is currently published.

## Scope and known limitations

The internal review in [`docs/operations/security-review.md`](docs/operations/security-review.md) records implemented controls and remaining production gaps. Highlights:

- The API is read-only. Public responses apply a single publication gate.
- API middleware enforces request-ID validation, a consistent error envelope, bounded pagination and spatial queries, CORS allowlisting, and per-process rate limiting.
- The web app sets baseline security headers and a per-request nonce-based Content Security Policy in `apps/web/src/proxy.ts`; do not add a second CSP header.
- Bulk exports and the per-facility CSV export neutralize spreadsheet-formula prefixes.
- CI runs `pip-audit` and `pnpm audit`.
- No production TLS/HSTS, WAF, managed secret store, external penetration test, or on-call monitoring exists in this repository. Rate limiting is per API process; a reverse proxy needs documented trusted-proxy handling.
- Backups and raw source objects contain internal-only records and must follow the same rights restrictions as the database.

Do not treat the current checkout as approved for sensitive data or for a production launch.

## Dependency updates

```bash
uv run --with pip-audit pip-audit
pnpm audit --prod
```

Upgrade or mitigate known vulnerabilities, re-run the test suite, and record residual risk in the security review. Do not silence an advisory without documenting why it does not apply.

## Data and privacy

- Never commit secrets, tokens, credentials, or signed agreements containing personal details.
- Do not collect or expose learner, patient, or beneficiary personal data.
- Treat source-provided contact details as potentially sensitive until reviewed.
- Do not expose raw source payloads publicly unless the dataset's terms explicitly allow it.
- Report a suspected data exposure through the private route above; do not copy the data into a public issue.
- Rights and publication rules are in [`docs/data-policy.md`](docs/data-policy.md).
