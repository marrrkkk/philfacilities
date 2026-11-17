# PhilHealth Antenatal re-ingestion — 16 November 2026

## Why

The 30 September 2026 Antenatal PDF (`EMCB-ANTE_093026.pdf`) was acquired and
released earlier, but its first parse counted the PDF's expiry/sector annex
(pages 121–240) as provider rows. The 6,562-row release was withdrawn and its
derived records removed. The corrected `philhealth-pdf-1.2.0` parser was tested
locally in this pass and read 3,221 provider rows, ending at page 120.

## Pre-state

- Dataset `philhealth-emcb-ante`: `publication_status=blocked`,
  `redistribution_status=approved_with_attribution`; publication gate already
  `approved`.
- Release `PHILHEALTH-EMCB-ANTE_093026-2026-09-30`: `withdrawn` / `blocked`,
  `row_count_parsed=6562`, 0 source records, 0 facility links.
- Snapshot: `pre-state.json`.

## Parser dry-run

```text
parser philhealth-pdf-1.2.0 rows 3221 warnings 0
first page refs: page:1:row:1, page:1:row:2, page:1:row:3
last page refs: page:120:row:5, page:120:row:6, page:120:row:7
```

## Re-ingestion attempt and fix

The first live retry failed at commit with a duplicate
`(release_id, facility_id)` snapshot key. `capture_facility_snapshot` checked
only the database, while the ingestion session uses `autoflush=False`, so a
pending snapshot from an earlier row was invisible. The function now checks
`session.new` first, keeping repeated captures idempotent. Regression coverage:
`tests/test_release_rollback.py::test_snapshot_is_recorded_once_per_release_and_facility`.

## Result

Command:

```text
uv run philfacilities-ingest load-philhealth --file EMCB-ANTE_093026.pdf
```

Outcome:

```text
status: published
parsed_rows: 3221
accepted_rows: 3221
rejected_rows: 0
duplicate_source_ids: 0
facilities_created: 0
facilities_updated: 3182
accreditations: 3221
issues: 0
```

Database verification (`post-state.json`):

- release `published` / `published`, SHA-256 `a6245006008377678d38a42d24132d7368d3630152223bb710d7d98b2ece2231`
- 3,221 source records, 3,221 facility links, 3,178 unique facilities
- 3,221 Antenatal accreditations
- 3,178 release snapshots
- maximum source page 120; **0** rows after page 120
- 0 facility-subtype changes versus the retained pre-release snapshots
- totals: 97,743 facilities, 67,004 public, 28,207 health accreditations

## Subtype correction

The first re-ingestion initially set all 3,178 linked facilities' `facility_subtype`
to `EMCB-ANTE`, repeating the earlier regression. The prior values were restored
from the release snapshots (3,103 Postpartum, 73 Transvaginal Ultrasound, 1
Clinical Laboratory, 1 INF/DISP). The adapter now treats Antenatal as an
accreditation-only benefit package: it retains the category on the health
profile and accreditation, but emits no facility subtype, so it cannot overwrite
the physical facility classification. A dry normalize check returns 3,221
candidates with 0 non-null subtypes and 3,221 Antenatal provider categories.
Regression coverage:
`apps/ingest/tests/test_parsers.py::test_philhealth_antenatal_rows_do_not_overwrite_facility_subtype`.

## Reprocess limitation

A later `--reprocess` attempt aborted before any mutation because this two-up PDF
repeats `page:N:row:M` references across table fragments (2,591 unique references
for 3,221 rows). The reprocess guard correctly refused to map two stored records
to one reference. The published release and its 3,221 records were retained, and
the release status was restored to `published` after verifying no data changed.
A future reprocess needs a stable unique row-reference scheme; this release does
not require one because its data and snapshots are already validated.

## Decision

The corrected release is published under the existing PhilHealth
`approved_with_attribution` decision. The 404 Birthing Homes PDF
(`MCP_073126.pdf`) remains a recorded source gap and is not replaced with
invented records.
