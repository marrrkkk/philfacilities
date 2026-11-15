# Architecture decision records

Short records of decisions that shape the repository. Each record states the
context, the decision, and the consequences that later work must respect. Update a
record only by adding a new one that supersedes it.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-monorepo-service-boundaries.md) | Monorepo with independently deployable services | Accepted |
| [0002](0002-canonical-facility-identity.md) | Canonical facility identity and reviewed source links | Accepted |
| [0003](0003-temporal-model-and-history.md) | Append-only source releases and explicit change history | Accepted |
| [0004](0004-data-licensing-and-publication-gates.md) | Separate code and data rights with publication gates | Accepted; amended by 0008 |
| [0005](0005-coordinate-precision-and-matching.md) | Preserve coordinate precision; never auto-merge | Accepted |
| [0006](0006-basemap-provider.md) | MapLibre renderer with a configurable, licensed basemap | Proposed for production; demo in use |
| [0007](0007-api-versioning-and-bulk-exports.md) | Stable `/v1` contract and gated bulk exports | Accepted |
| [0008](0008-publicly-available-data-inclusion.md) | Include verified, publicly available data with no explicit prohibition | Accepted |

This directory satisfies the ADR list in
[02 — Architecture](../02-ARCHITECTURE.md#9-architecture-decisions).
