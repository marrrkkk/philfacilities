# 06 — Source Ingestion, Snapshot, and Data Release Operations

## 1. Objective

Extend the existing ingestion implementation so it can continuously maintain a national registry of qualifying government facilities, private public-service providers and public-access venues. Reuse the completed platform architecture and the existing source adapter framework. Do not rebuild the stack.

The ingestion system must handle official APIs, downloadable spreadsheets, CSVs, PDFs, GIS layers, FOI-provided files, LGU-contributed inventories, and authoritative directories of private regulated/service providers. Source access may be automated, human-assisted, or restricted; the processing pipeline should remain consistent after an authorized file is obtained.

## 2. Source acquisition modes

Each source/dataset must use one of these modes:

- `public_automated` — an official endpoint or file listing permits repeatable automated acquisition.
- `authenticated_automated` — an official API or download requiring valid credentials/authorized token.
- `human_bootstrap_then_automated` — initial human browser download/terms acceptance, then automated processing and future updates where permitted.
- `human_release_import` — each release is obtained by an operator or FOI response and imported into the same pipeline.
- `manual_review_only` — the source is public but structurally unstable or legally/technically unsuitable for automation.
- `restricted` — no ingestion or publication without further authorization.

Never circumvent Cloudflare, CAPTCHAs, logins, access controls, licensing prompts, or agreement acceptance. HTTP 403 should create a blocked-source event and a documented next step, not trigger bypass attempts or endless retries.

## 3. Shared lifecycle

Every connector should implement the same logical lifecycle:

1. Discover source/release.
2. Check whether the release is new or changed.
3. Acquire using its authorized access mode.
4. Verify download/content signature and integrity.
5. Store an immutable raw copy.
6. Register release metadata and checksum.
7. Parse source-specific records.
8. Validate schema, counts, IDs, geography, and source-specific fields.
9. Load staging records.
10. Normalize source fields while retaining original values.
11. Resolve facility identities and relationships.
12. Generate quality reports and release diffs.
13. Enforce rights/publication approval.
14. Publish eligible data atomically.
15. Retain prior releases and rollback capability.

A parser success is not a publication decision.

## 4. Source discovery

Use the most stable permitted mechanism available for each source:

- Official API metadata and pagination.
- RSS/release feeds if published.
- Official source-page link discovery.
- Known official file indexes.
- HTTP `ETag` / `Last-Modified` where reliable.
- File SHA-256 and byte size.
- Official release/publication date.
- Geoportal layer metadata and data inventory.
- Human submission of a new release notice or file.

For websites with JavaScript-driven interfaces, inspect the official page's documented operations and data catalogue. Do not infer private endpoints or automate a protected session without authorization.

A source page changing does not prove its underlying dataset changed. Verify the actual release/file/metadata.

## 5. Immutable raw source store

Every acquired source release must be preserved exactly as acquired, subject to retention and licence terms.

Suggested object path:

`raw/{agency}/{dataset}/{release_key}/{sha256}/{original_filename}`

Store the following metadata:

- source ID;
- agency and publisher;
- dataset name;
- official source URL;
- acquisition mode;
- retrieved timestamp;
- publication date if supplied;
- reference/effective period;
- original filename and format;
- byte size;
- SHA-256;
- HTTP response metadata where relevant;
- source licence/terms reference, or the verified public route and absence of an explicit prohibition when no licence exists;
- data-use agreement reference;
- parser version;
- schema version;
- release status.

Do not put restricted source files into public object storage or Git. Do not retain a file longer than an applicable agreement permits.

## 6. Source-specific parser strategy

### Spreadsheets

- Inspect all sheets, hidden sheets, merged cells, formulas, headers, blank preambles, and footnotes.
- Preserve sheet and row references.
- Do not treat display-formatted codes as numeric; preserve leading zeros and IDs as strings.
- Produce a source schema report on every new release.
- Detect header/column changes and stop publication on unexpected drift.

### CSV

- Detect and record encoding and delimiter.
- Preserve original strings and null markers.
- Validate row widths and quoting.
- Never silently coerce identifiers to numbers.

### PDF

- Prefer embedded text/table extraction when valid.
- Use layout-aware parsing for structured tables.
- Use OCR only when the PDF is scanned and after assessing whether extraction quality is adequate.
- Preserve page numbers and extracted row/table references.
- Require manual validation for uncertain fields, especially IDs, addresses, bed counts, dates, and amounts.

### GIS files and services

- Preserve original CRS and metadata.
- Detect geometry type, coordinate system, invalid geometry, empty geometry, and duplicate features.
- Transform to the platform's storage CRS only through a recorded, tested operation.
- Preserve source geometry where permitted.
- Do not confuse WMS image rendering with downloadable vector data. Confirm WFS/download permission and per-layer restrictions.
- Store source layer name, owner, publication date, data date, metadata URL, and licence/restriction state.

### HTML directories

- Use official, publicly accessible pages only when terms and robots/access expectations permit.
- Prefer published downloads or API over page extraction.
- Treat changes to page markup as schema changes.
- Preserve canonical source URLs and retrieval timestamp.
- Do not scrape login-protected or rate-limited administrative portals without permission.

## 7. Staging and normalization

Load parsed records into source-specific staging tables before canonical publication.

Staging must retain:

- raw source row/document reference;
- original field names and values;
- parser version;
- row-level validation errors;
- source release ID;
- candidate normalized facility category/subtype;
- candidate PSGC relationships;
- candidate coordinate and precision;
- proposed match to canonical facility (if any).

Normalization should be deterministic and documented. Use source-specific mapping files/configuration for headers and category codes. Never hardcode unverified columns based on an old or third-party derivative schema.

## 8. Entity matching and release diffs

For each new release, compare source IDs against prior releases. Then generate:

- new source records;
- removed source records;
- changed names/addresses/geography;
- changed owner/operator/status;
- changed coordinates or precision;
- changed categories/functions;
- duplicate or ambiguous records;
- records no longer present in source.

A missing row in a new source release must not automatically set a facility to `CLOSED`. Mark it `not_in_latest_source` or `source_record_missing` until a reliable status source confirms closure.

Cross-agency matches must use exact identifiers first, then explainable deterministic evidence. Ambiguous cases remain separate or enter a review queue.

## 9. Release manifest

Each public PhilFacilities release should contain a manifest describing the exact source releases used.

Example:

```json
{
  "release_id": "2026-11-15T00:00:00Z",
  "schema_version": "1.x",
  "generated_at": "2026-11-15T00:00:00Z",
  "datasets": [
    {
      "source_id": "nlp.public_libraries",
      "source_release": "2025-12",
      "reference_date": "2025-12-31",
      "published": true,
      "record_count": 0,
      "rights_status": "approved_with_attribution"
    }
  ]
}
```

All example values are placeholders. Real manifests must contain real source-release identifiers, dates, counts, and rights status.

The manifest should include:

- PhilFacilities release ID;
- schema version;
- source dataset/release IDs;
- source reference/publication dates;
- source retrieval dates;
- record counts by source and facility type;
- rejected/quarantined counts;
- quality summary;
- licensing/attribution status;
- checksum for downloadable data artifacts;
- known coverage gaps.

A PhilFacilities release may contain datasets with different reference periods. Do not imply that all records are contemporaneous.

## 10. Atomic publication and rollback

Use a release-candidate process:

1. Build new normalized tables or a versioned snapshot.
2. Run release-level validation and quality thresholds.
3. Confirm rights approval for every included source/release/field.
4. Produce a preview manifest and diff report.
5. Publish atomically only when gates pass.
6. Retain the previous published release.
7. Provide rollback to the last valid release.

A failed new release must not corrupt or erase the previous public dataset.

## 11. Scheduling and monitoring

Use configurable discovery intervals based on actual source behavior. Initial suggested checks:

| Source group | Discovery cadence | Ingestion trigger |
|---|---|---|
| PSA PSGC | Weekly | New official release |
| DepEd | Monthly | New authorized file |
| DOH NHFR | Weekly/monthly | New authorized release |
| PhilHealth category files | Weekly | New dated file |
| DILG DRRM-PULSE | Weekly | New public facility/profile release, where detectable |
| DSWD directories | Monthly | Updated dated directory |
| National Library directory | Quarterly | New directory/revision |
| Geoportal layers | Monthly | Layer metadata/version change |
| BFP | Monthly | New official report/list |
| LGU portals/inventories | Monthly/quarterly | New official file or page revision |

These are monitoring suggestions, not claims that source agencies publish at these frequencies. Monitor; do not repeatedly scrape unchanged large documents.

## 12. Required ingestion states

Source-level states:

- `DISCOVERED`
- `REACHABLE`
- `UPDATE_AVAILABLE`
- `ACQUISITION_RUNNING`
- `ACQUIRED`
- `PARSE_FAILED`
- `SCHEMA_CHANGED`
- `VALIDATION_FAILED`
- `QUARANTINED`
- `AWAITING_RIGHTS_REVIEW`
- `APPROVED`
- `PUBLISHED`
- `ACCESS_BLOCKED`
- `NO_NEW_RELEASE`
- `DEFERRED`

Facility/source-record states must be separate from ingestion states.

## 13. Operational failure rules

- HTTP 403/CAPTCHA: record block and legitimate manual/FOI route; no evasion.
- HTTP 404: verify whether the official source moved or retired; do not delete old data.
- HTTP 429/503: respect `Retry-After`, use bounded retries/backoff.
- Changed file signature: quarantine, investigate content type and schema.
- Unexpected record-count drop: block publication pending review.
- Rights approval expired: block future publication; apply agreement-specific retention/removal requirements.
- Source page unavailable: retain last valid release and show its age.
- Parser failure: preserve raw file and error report; do not partially publish.

## 14. Minimum release evidence

A release is publishable only when:

- source file/data is acquired through an authorized route;
- original publisher and source record are known;
- source schema is inspected;
- records pass required validation;
- source geography is mapped or explicitly unresolved;
- identity matching has no unreviewed destructive merges;
- publication decision is recorded under the root inclusion policy (`approved_public_redistribution`, `approved_with_attribution`, or `publicly_available_verified`), and explicit restrictions or agreements have been cleared;
- public fields have no prohibited personal/sensitive information;
- release manifest and source attribution are generated;
- the prior release remains recoverable.


## 11. Ownership-inclusive source ingestion

The same source-adapter and release workflow applies to sources listing government facilities and sources listing qualifying private facilities. A government agency may be the regulator/accreditor or publisher without owning or operating the listed facility.

During normalization, every record must receive an inclusion-class decision under `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`. Store owner, operator, manager, host, funder, regulator, accreditor and access status separately. If ownership is not established, use `UNKNOWN`; do not infer it.

Private provider datasets are not a separate technical registry. They share the canonical facility model and API, but remain independently filterable/countable using `PRIVATE_PUBLIC_SERVICE_PROVIDER`. Public-access venues use `PUBLIC_ACCESS_VENUE`. Unverified candidate records remain internal-only.

Rights checks apply equally to all source records. An official regulator's publication of a private-provider record does not automatically permit PhilFacilities to redistribute the record. Apply release- and field-level publication gates.
