# Security Policy

PhilFacilities is currently a synthetic-data demonstration MVP. It is not a production public
service, and no official agency data is published from this checkout.

## Supported versions

| Version | Supported |
|---|---|
| `0.1.x` (demonstration MVP) | Security fixes are applied on the default branch |

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.** Do not include credentials, signed
data-use agreements, personal data, restricted source rows, or exploitable details in a public
issue or pull request.

When this repository is hosted on GitHub and private vulnerability reporting is enabled, use the
repository's **Security → Report a vulnerability** route. If that route is not available, contact
the repository maintainers through the private channel published with the repository. Do not invent
or rely on an unverified security email address.

Please include, where safe:

- the affected component (`web`, `api`, `ingest`, `api-client`, database, or operations);
- the version or commit;
- a minimal reproduction or proof of concept using synthetic data;
- the impact you believe is possible;
- any suggested remediation or disclosure constraints.

Maintainers will acknowledge reports as capacity allows, validate the issue, and coordinate a fix
and disclosure. No response-time SLA is currently published.

## Scope and known limitations

The internal review in [`docs/operations/security-review.md`](docs/operations/security-review.md)
records the controls implemented in this checkout and the remaining production gaps. Highlights:

- the web app sets baseline security headers but not a complete script/style CSP;
- the API has transparent rate limiting, request-ID validation, CORS restrictions, bounded
  pagination/spatial queries, and a consistent error envelope;
- MapLibre and JavaScript/Python dependencies are checked in CI with `pip-audit` and `pnpm audit`;
- there is no production WAF, TLS termination, secret manager, external penetration test, or
  on-call monitoring configuration in this repository.

Do not treat the demo deployment as approved for sensitive or official data.

## Dependency updates

Run the dependency checks before release:

```bash
uv run --with pip-audit pip-audit
pnpm audit --prod
```

Upgrade or mitigate known vulnerabilities, re-run the test suite, and record any residual risk in
the security review. Do not silence an advisory without documenting why it does not apply.

## Data and privacy

- Never commit secrets, tokens, credentials, or signed agreements containing personal details.
- Do not collect or expose learner, patient, or beneficiary personal data.
- Treat source-provided contact details as potentially sensitive until reviewed.
- Do not expose raw source payloads publicly unless the dataset's terms explicitly allow it.
- Report a suspected data exposure through the private route above; do not copy the data into a
  public issue.
