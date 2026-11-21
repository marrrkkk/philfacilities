# 0009 — MCP is a public-API-only read adapter

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Model Context Protocol clients (Claude, ChatGPT, editor agents, custom assistants)
need a curated way to ask questions about published facilities and their evidence.
The repository already has a read-only `/v1` API with a committed OpenAPI contract,
one publication gate implemented in `rights.py`, and a generated TypeScript client.

Two options were considered: mount an MCP server inside the FastAPI process and let
its tools call internal service functions, or add a separate adapter that calls the
public API over HTTP. Similar BetterGov.ph projects colocate MCP with their Worker
and share data functions, but they do not have a rights gate or a second client
contract to protect.

Hand-rolling an MCP implementation would also mean tracking protocol revisions
manually. As of November 2026 the official Python SDK (v2) speaks the current
2026-07-28 protocol and maintains compatibility with older clients.

## Decision

Add `apps/mcp` as an independently deployable **read-only MCP adapter over the
public `/v1` API**.

- The server has no database credentials, imports no `philfacilities_api` module,
  and accepts no arbitrary URLs. Its only data path is the public API over HTTP.
- The publication gate, response shapes, vocabularies and rights states are not
  duplicated: they remain owned by the API. Tool results are API payloads passed
  through unchanged.
- Tools are curated and task-named, not a mechanical export of FastAPI routes.
  Internal quality/review endpoints are deliberately not exposed.
- Transport: stdio for local clients and stateless Streamable HTTP at `/mcp` for
  hosted clients. Both use the same tool code.
- Use the official MCP Python SDK (`mcp>=2.3,<3`), not standalone FastMCP. FastMCP
  can be adopted later if authentication, composition or proxying becomes a
  requirement; tool code would not need to change.
- The server is public and read-only, like the API. Hosted operation requires host
  and origin allowlists and edge rate limiting. The API's per-IP limiter is not a
  substitute because a hosted MCP service aggregates its callers behind one IP.

## Consequences

- A facility that the API will not publish cannot be reached through MCP, and an
  API contract change cannot silently produce a different MCP field shape.
- MCP can be deployed, scaled and restarted independently of the API and web app.
- There is one extra HTTP hop per tool call. In production the adapter points at
  the internal API origin, so this is a private network hop, not a public round
  trip. Reference responses (taxonomy, sources) may be cached briefly; facility
  and provenance responses must not be cached.
- The adapter cannot expose internal QA or ingestion data without a deliberate
  API change, which keeps the review boundary intact.
- A new tool requires a tool definition plus a contract assertion that its path
  and query arguments exist in `packages/api-client/openapi.json`.
- Server instructions and tool descriptions carry data caveats (null semantics,
  coordinate precision, partial coverage, no inferred operational status) because
  hosts pass them directly to the model.

## Evidence

- [`docs/mcp.md`](../mcp.md)
- `apps/mcp/philfacilities_mcp/`
- `apps/mcp/tests/test_contract.py`
- [ADR 0001](0001-monorepo-service-boundaries.md)
- [ADR 0007](0007-api-versioning-and-bulk-exports.md)
