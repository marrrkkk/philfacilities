# PhilHealth source-record key repair — 15 November 2026

## What was wrong

PhilHealth PDF releases ingested with parser `philhealth-pdf-1.1.0` built the
source-record key from the provider category, facility name, municipality,
expiry date, and PDF page. The key omitted the physical row number. When a page
repeated the same facility values on more than one row, the ingestion loop
treated the later rows as duplicate keys and never wrote a `source.records` row
for them. The run still reported every parsed row as accepted.

The current parser, `philhealth-pdf-1.2.0`, includes the row number in the key.
Re-parsing the preserved PDFs with the current parser produced exactly the
missing count:

| Dataset | Release | Parsed rows | Records before | Collapsed | Records after |
|---|---|---:|---:|---:|---:|
| `philhealth-gamot` | `PHILHEALTH-GAMOT-UNDATED` | 3,483 | 3,279 | 204 | 3,483 |
| `philhealth-fdc` | `PHILHEALTH-FDC_093026-2026-09-30` | 1,012 | 993 | 19 | 1,012 |
| `philhealth-hosp` | `PHILHEALTH-HOSP_093026-2026-09-30` | 1,934 | 1,932 | 2 | 1,934 |
| `philhealth-yakap` | `PHILHEALTH-YAKAP-UNDATED` | 4,138 | 4,134 | 4 | 4,138 |
| **Total** | | **10,567** | **10,338** | **229** | **10,567** |

The old key composition was reproduced directly from the PDFs:
`name + municipality + expiry + page` yields 3,279 unique GAMOT keys, exactly
matching the stored record count. Adding the row number yields 3,483.

## Why this was not a source change

The four PDFs still match their stored SHA-256 values. Nothing in the source
changed; the missing rows were an ingestion-key defect. The repair therefore had
to preserve record IDs and all facility/source links rather than delete and
re-ingest the releases.

## Repair path

`run_ingestion(..., reprocess=True)` and
`philfacilities-ingest load-philhealth --reprocess` were added:

1. The existing release is reopened instead of being skipped as a duplicate
   checksum.
2. Stored records are reconciled to the current parser keys by the preserved
   `page:row` reference. Old keys are moved to temporary values, flushed, then
   assigned the corrected keys so the unique constraint cannot fail on a
   transient collision. Record IDs are unchanged.
3. Every stored record must map to a parsed row. If a parser would drop a row
   that the release already contains, the run aborts instead of orphaning source
   evidence.
4. Rows that are already linked and whose raw payload hash is unchanged are
   skipped. Newly recovered rows are inserted and linked.
5. Accreditations, source links, and history events continue to reference the
   same record IDs.

The first reprocess pass was run before the skip guard existed. It re-applied
all unchanged rows and produced last-writer-wins attribute churn. The run was
audited and the canonical state was restored, not accepted:

- 5,387 re-application history events were exported to
  `reprocess-change-events.csv` and deleted.
- 3,378 canonical values were restored from the earliest recorded `old_value`
  in those events (354 `display_name`, 3,024 `facility_subtype`) and verified
  against `restore-canonical-values.csv` with zero mismatches.
- 10,566 duplicate `location_missing` issues created by the re-application were
  exported to `duplicate-location-issues.csv` and deleted.
- One redundant facility-level `location_missing` issue left from an earlier
  cleanup was exported to `redundant-facility-issue.csv` and deleted. The
  facility retains five source-backed issues; no per-record issue duplication
  remains.

## Before and after

`before-counts.txt` records the pre-repair database totals:

- 234,820 source records
- 24,757 accreditations
- 88,824 facilities
- 100,046 source links

After the repair:

- **235,049** source records (+229)
- **24,986** accreditations (+229)
- **88,824** facilities (unchanged)
- **100,275** source links (+229)
- **100,304** history events (unchanged; the artifact events were removed)
- **30,041** open `location_missing` issues (no per-record duplicates)
- **0** `EMCB-ANTE` facilities, **0** source-less history events
- **80** Python tests passing
- **90** recorded source checks (four new checks from the reprocess)

Each repaired release now satisfies
`row_count_parsed = count(source.records)` and
`count(source.records) = count(health.accreditations)` for its rows.

## Files

| File | Contents |
|---|---|
| `before-counts.txt` | Pre-repair totals and per-release collapse counts |
| `before-record-key-map.csv` | Every pre-repair record key and page/row reference (10,338 rows) |
| `reprocess-log.txt` | CLI output and per-release statistics from the four reprocess runs |
| `reprocess-change-events.csv` | The 5,387 re-application history events exported before deletion |
| `restore-canonical-values.csv` | The 3,378 canonical values restored from those events |
| `duplicate-location-issues.csv` | The 10,566 duplicate quality issues exported before deletion |
| `redundant-facility-issue.csv` | The one redundant facility-level issue exported before deletion |

## Verification queries

```sql
-- Parsed rows must equal stored records and accreditations for the repaired releases
SELECT d.slug, r.row_count_parsed, count(DISTINCT sr.id) AS records,
       count(DISTINCT a.id) AS accreditations
FROM source.releases r
JOIN source.datasets d ON d.id = r.dataset_id
LEFT JOIN source.records sr ON sr.release_id = r.id
LEFT JOIN health.accreditations a ON a.source_record_id = sr.id
WHERE d.slug IN ('philhealth-gamot','philhealth-fdc','philhealth-hosp','philhealth-yakap')
GROUP BY 1,2 ORDER BY 1;

-- No per-record location issue may be duplicated
SELECT source_record_id, issue_code, count(*)
FROM quality.issues
WHERE issue_code = 'location_missing'
GROUP BY 1,2 HAVING count(*) > 1;

-- No re-application artifacts may remain
SELECT count(*) FROM history.facility_change_events
WHERE changed_by = 'ingest:philhealth-pdf-1.2.0';
```

The observed results were: every `parsed`/`records`/`accreditations` triple
equal (3,483 / 1,012 / 1,934 / 4,138), zero duplicate per-record issues, and
zero re-application history events.

## Scope and limitations

This evidence covers a parser and record-identity repair only. It does not
change source rights, add new sources, establish nationwide completeness, or
constitute legal review. The underlying PDFs remain subject to the PhilHealth
attribution terms recorded in `DATA-LICENSES.md`.

## Final audit check (15 November 2026)

The repaired releases were re-checked during the final `data.md` acceptance
audit against the working database. Each of the four releases still satisfies
`row_count_parsed = count(source.records) = count(health.accreditations)`
(3,483 / 1,012 / 1,934 / 4,138), no `ingest:philhealth-pdf-1.2.0` change event
remains, and the duplicate per-record issue query returns no rows. The audit
also confirmed 235,049 total source records, 24,986 accreditations, 100,275
source links, and 80 passing Python tests. These are local verification results,
not a claim of hosted monitoring or external review.
