"""Release staging: source records, validation issues, and row-count checks."""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter

from philfacilities_api.models import Release, SourceRecord
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..contracts import ParsedRelease, ParsedRow, ValidationResult
from .common import _hash
from .release import _record_issues

SOURCE_RECORD_KEY_LIMIT = 200


def _staged_record_keys(parsed_rows: list[ParsedRow]) -> list[str]:
    """Return one unique staging key per physical parsed row, in input order.

    ``ParsedRow.source_record_key`` is the source's business key. Some official
    directories repeat it for distinct physical rows (for example a duplicated
    OSM object id or a repeated institution code). ``source.records`` is unique
    on ``(release_id, source_record_key)``, so repeated keys receive a
    deterministic suffix instead of being dropped. The original key remains the
    prefix and is also recorded in the linked validation issue.
    """

    occurrences: Counter[str] = Counter()
    used: set[str] = set()
    keys: list[str] = []
    for row in parsed_rows:
        base = row.source_record_key
        occurrences[base] += 1
        occurrence = occurrences[base]
        if occurrence == 1 and base not in used:
            key = base
        else:
            digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
            while True:
                suffix = f"#staged-dup-{digest}-{occurrence}"
                key = f"{base[: SOURCE_RECORD_KEY_LIMIT - len(suffix)]}{suffix}"
                if key not in used:
                    break
                occurrence += 1
        used.add(key)
        keys.append(key)
    return keys


def row_count_anomaly(
    previous: int | None,
    current: int | None,
    *,
    minimum_baseline: int = 20,
    lower_ratio: float = 0.5,
    upper_ratio: float = 2.0,
) -> dict[str, float | int] | None:
    """Return details when a release count changes implausibly against the last release."""

    if previous is None or current is None or previous < minimum_baseline:
        return None
    ratio = current / previous
    if lower_ratio <= ratio <= upper_ratio:
        return None
    return {
        "previous_count": previous,
        "current_count": current,
        "ratio": round(ratio, 3),
    }


def _reconcile_source_record_keys(
    *,
    existing_records: list[SourceRecord],
    parsed_rows: list[ParsedRow],
    session: Session,
) -> None:
    """Re-key stored records after a parser's record-key scheme changes.

    A preserved file is immutable, so its page/row references remain the stable
    identity of each physical source row. When a parser fixes a key collision,
    an explicit reprocess keeps the existing record IDs (and every facility
    link, accreditation, and history event that references them) while moving
    each record to the corrected key. Rows that no parsed row accounts for abort
    the run; a parser regression must not silently orphan source evidence.
    """

    staged_keys = _staged_record_keys(parsed_rows)
    parsed_by_key = {staged_keys[index]: (row, index) for index, row in enumerate(parsed_rows)}
    if len(parsed_by_key) != len(parsed_rows):
        raise ValueError("Parser produced non-unique staging keys; reprocess aborted.")
    ref_counts = Counter(row.row_reference for row in parsed_rows)
    parsed_by_ref = {
        row.row_reference: (row, index)
        for index, row in enumerate(parsed_rows)
        if ref_counts[row.row_reference] == 1
    }

    legacy_ref_counts = Counter(record.row_number_or_page for record in existing_records)
    assignments: list[tuple[SourceRecord, ParsedRow, int]] = []
    assigned_indices: set[int] = set()
    for record in existing_records:
        row = None
        row_index = None
        keyed = parsed_by_key.get(record.source_record_key)
        if keyed is not None and (
            keyed[0].row_reference == record.row_number_or_page
            or legacy_ref_counts[record.row_number_or_page] > 1
        ):
            # A parser fix may have made a formerly duplicated row reference
            # unique. In that case the stable record key is the only
            # unambiguous link between the stored record and the parsed row.
            row, row_index = keyed
        elif record.row_number_or_page in parsed_by_ref:
            row, row_index = parsed_by_ref[record.row_number_or_page]
        if row is None or row_index is None:
            raise ValueError(
                "Stored source record is absent from the reprocessed release; "
                f"row reference {record.row_number_or_page!r}, key "
                f"{record.source_record_key!r}."
            )
        if row_index in assigned_indices:
            raise ValueError(
                "Two stored source records map to the same parsed row; "
                f"row reference {row.row_reference!r}."
            )
        assigned_indices.add(row_index)
        assignments.append((record, row, row_index))

    rekeys = [
        (record, staged_keys[row_index])
        for record, _row, row_index in assignments
        if record.source_record_key != staged_keys[row_index]
    ]
    if not rekeys:
        return
    # Free every old key before assigning corrected keys so a unique constraint
    # cannot fail on a transient collision between two re-keyed records.
    for record, _ in rekeys:
        record.source_record_key = f"rekey-pending:{uuid.uuid4()}"
    session.flush()
    for record, source_record_key in rekeys:
        record.source_record_key = source_record_key
    session.flush()


def stage_source_records(
    session: Session,
    *,
    release: Release,
    parsed: ParsedRelease,
    validation: ValidationResult,
    reprocess: bool,
    force_reapply: bool = False,
) -> tuple[dict[str, SourceRecord], dict[str, uuid.UUID], set[str], dict[str, bool]]:
    """Upsert every parsed row as a source record and record validation issues.

    Every physical parsed row is retained, including rows that share a business
    key and rows the validator rejected. Rejected rows are stamped
    ``validation_status='rejected'`` and their issues point at the retained
    record. Returns the record cache, the row-reference to record-ID map used by
    child issues, the keys that existed before this run, and the per-key
    unchanged flag used by reprocess to avoid re-asserting unchanged canonical
    fields.
    """

    record_by_key: dict[str, SourceRecord] = {}
    existing_record_list = list(
        session.scalars(select(SourceRecord).where(SourceRecord.release_id == release.id)).all()
    )
    if reprocess:
        _reconcile_source_record_keys(
            existing_records=existing_record_list,
            parsed_rows=parsed.rows,
            session=session,
        )
    existing_records = {record.source_record_key: record for record in existing_record_list}
    pre_existing_keys = set(existing_records)
    unchanged_by_key: dict[str, bool] = {}
    staged_keys = _staged_record_keys(parsed.rows)
    rejected_references = validation.rejected_row_references
    for row, record_key in zip(parsed.rows, staged_keys, strict=True):
        record = existing_records.get(record_key)
        validation_status = (
            "rejected" if row.row_reference in rejected_references else row.validation_status
        )
        if record is None:
            record = SourceRecord(
                # Client-side key keeps the staging insert batchable.
                id=uuid.uuid4(),
                release_id=release.id,
                source_record_key=record_key,
                row_number_or_page=row.row_reference,
                raw_payload=row.raw_payload,
                raw_record_hash=_hash(row.raw_payload),
                validation_status=validation_status,
            )
            session.add(record)
            unchanged_by_key[record_key] = False
        else:
            payload_hash = _hash(row.raw_payload)
            unchanged_by_key[record_key] = (
                False if force_reapply else record.raw_record_hash == payload_hash
            )
            record.row_number_or_page = row.row_reference
            record.raw_payload = row.raw_payload
            record.raw_record_hash = payload_hash
            record.validation_status = validation_status
        record_by_key[record_key] = record
    # One flush inserts every new source record. The client-side IDs keep this
    # a single batched executemany rather than per-row round trips.
    session.flush()
    record_by_row: dict[str, uuid.UUID] = {}
    for row, record_key in zip(parsed.rows, staged_keys, strict=True):
        # A parser can repeat a row reference. Keep the first record for issue
        # attachment; every physical row is still retained above.
        record_by_row.setdefault(row.row_reference, record_by_key[record_key].id)
    _record_issues(
        session,
        issues=validation.issues,
        release=release,
        record_by_row=record_by_row,
    )
    return record_by_key, record_by_row, pre_existing_keys, unchanged_by_key
