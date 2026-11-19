"""The single facility-release runner.

Every source enters canonical storage through :func:`run_ingestion`. Staging,
canonical writes, and reporting live in their own modules; this module only
orchestrates the release lifecycle and the application loop.
"""

from __future__ import annotations

import gc
import resource
import uuid
from datetime import UTC, datetime
from typing import Any

from philfacilities_api.models import (
    AdministrativeUnit,
    Agency,
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySlugAlias,
    FacilitySourceLink,
    GeographicRelease,
    HealthAccreditation,
    HealthProfile,
    IngestionRun,
    PublicationGate,
    QualityIssue,
    Release,
    SourceRecord,
)
from philfacilities_api.rights import (
    PUBLICATION_APPROVED,
    PUBLICATION_BLOCKED,
    PUBLICATION_INTERNAL_ONLY,
    PUBLICATION_PUBLISHED,
    PUBLICATION_QUARANTINED,
    normalize_rights,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from ..config import IngestSettings, get_settings
from ..contracts import (
    FacilityCandidate,
    ParsedRelease,
    ReleaseSpec,
    SourceAdapter,
    ValidationIssue,
)
from ..release_rollback import UPDATE_PREFETCH_CHUNK_SIZE, FacilityUpdatePrefetch
from ..storage import RawStore, build_store
from ..validators import coordinate_issue
from .canonical import (
    BULK_ASSERTIONS_KEY,
    _apply_candidate,
    _flush_new_facilities,
    _maybe_flag_cross_source,
    flush_attribute_assertions,
    flush_enrollment_observations,
)
from .common import (
    APPLY_FLUSH_BATCH_SIZE,
    IngestResult,
    build_engine,
    session_factory,
)
from .locking import dataset_ingestion_lock
from .release import (
    _dataset_is_public,
    _existing_release,
    _record_issues,
    _resolve_open_issues,
    _write_report,
    ensure_source,
)
from .staging import row_count_anomaly, stage_source_records
from .stats import IngestStats


def run_ingestion(
    *,
    spec: ReleaseSpec,
    adapter: SourceAdapter,
    store: RawStore | None = None,
    session: Session | None = None,
    settings: IngestSettings | None = None,
    reprocess: bool = False,
    force_reapply: bool = False,
) -> IngestResult:
    settings = settings or get_settings()
    store = store or build_store(settings)
    own_session = session is None
    engine = None
    if own_session:
        engine = build_engine(settings)
        session = session_factory(engine)()
    assert session is not None
    try:
        with dataset_ingestion_lock(
            session, agency_code=spec.agency_code, dataset_slug=spec.dataset_slug
        ):
            return _run_ingestion_locked(
                spec=spec,
                adapter=adapter,
                store=store,
                session=session,
                settings=settings,
                reprocess=reprocess,
                force_reapply=force_reapply,
            )
    finally:
        if own_session:
            session.close()
        if engine is not None:
            engine.dispose()


def _run_ingestion_locked(
    *,
    spec: ReleaseSpec,
    adapter: SourceAdapter,
    store: RawStore,
    session: Session,
    settings: IngestSettings,
    reprocess: bool,
    force_reapply: bool = False,
) -> IngestResult:
    run_id = uuid.uuid4()
    stats = IngestStats()
    if force_reapply:
        # Reapplying an unchanged row is an explicit operator decision, never
        # an automatic consequence of a parser-version bump.
        reprocess = True
        stats["forced_reapply"] = True
    all_issues: list[dict[str, Any]] = []
    agency: Agency | None = None
    dataset: Dataset | None = None
    gate: PublicationGate | None = None
    release: Release | None = None
    run: IngestionRun | None = None
    was_published = False
    try:
        stats.start_stage("release")
        agency, dataset, gate = ensure_source(session, spec)
        preserved = store.preserve(
            agency=spec.agency_code,
            dataset=spec.dataset_slug,
            release_label=spec.release_label,
            filename=spec.filename,
            content=spec.content,
        )
        existing = _existing_release(session, dataset.id, preserved.sha256)
        parser_changed = bool(
            existing
            and existing.ingestion_status == "published"
            and (existing.parser_version or "") != adapter.parser_version
        )
        if parser_changed:
            # A parser fix must not require an operator to remember --reprocess.
            # The preserved artifact is unchanged, so re-derive records in place.
            reprocess = True
            stats["parser_reprocess"] = True
        run = IngestionRun(
            id=run_id,
            dataset_id=dataset.id,
            started_at=datetime.now(UTC),
            status="running",
        )
        session.add(run)
        if (
            existing
            and existing.ingestion_status == "published"
            and not reprocess
            and not _latest_run_failed(session, existing.id)
        ):
            stats.stop_stage("release")
            run.release_id = existing.id
            run.status = "skipped_duplicate"
            run.finished_at = datetime.now(UTC)
            stats["reason"] = "release checksum already published"
            stats["sha256"] = preserved.sha256
            run.stats = stats.snapshot()
            session.commit()
            stats.start_stage("report")
            json_path, md_path = _write_report(
                settings,
                spec=spec,
                run_id=run_id,
                status="skipped_duplicate",
                stats=stats,
                issues=[],
            )
            stats.stop_stage("report")
            stats.finish()
            run.report_path = json_path
            run.stats = stats.snapshot()
            session.commit()
            return IngestResult(
                dataset=spec.dataset_slug,
                release_label=spec.release_label,
                release_id=str(existing.id),
                status="skipped_duplicate",
                report_json=json_path,
                report_markdown=md_path,
                stats=stats.snapshot(),
            )
        if existing:
            release = existing
            was_published = (
                release.ingestion_status == "published"
                and release.publication_status == PUBLICATION_PUBLISHED
            )
            if reprocess:
                stats["reprocessed"] = True
            if not was_published:
                release.ingestion_status = "processing"
                release.processed_at = None
                release.source_release_label = spec.release_label
                release.source_published_at = spec.source_published_at
                release.reference_period_start = spec.reference_period_start
                release.reference_period_end = spec.reference_period_end
                release.retrieved_at = spec.retrieved_at or release.retrieved_at
                release.raw_object_uri = preserved.uri
                release.parser_version = adapter.parser_version
                release.terms_review_status = (
                    "synthetic_demo"
                    if spec.is_synthetic
                    else normalize_rights(spec.redistribution_status)
                )
                release.publication_status = (
                    PUBLICATION_APPROVED
                    if _dataset_is_public(dataset, gate)
                    else PUBLICATION_BLOCKED
                )
            # A release that is already public keeps its committed metadata and
            # status while it is reprocessed. The new derived state is committed
            # only after the whole run succeeds, so a failed reprocess cannot
            # hide the last good snapshot. Source records are updated in place
            # below so facility/source links survive a failed-then-retried
            # release. Nothing is duplicated by a retry.
        else:
            was_published = False
            release = Release(
                dataset_id=dataset.id,
                source_release_label=spec.release_label,
                source_published_at=spec.source_published_at,
                reference_period_start=spec.reference_period_start,
                reference_period_end=spec.reference_period_end,
                retrieved_at=spec.retrieved_at or datetime.now(UTC),
                raw_object_uri=preserved.uri,
                sha256=preserved.sha256,
                file_format=spec.filename.rsplit(".", 1)[-1].lower(),
                file_size_bytes=preserved.size_bytes,
                ingestion_status="processing",
                terms_review_status="synthetic_demo"
                if spec.is_synthetic
                else normalize_rights(spec.redistribution_status),
                publication_status=(
                    PUBLICATION_BLOCKED
                    if not _dataset_is_public(dataset, gate)
                    else PUBLICATION_APPROVED
                ),
                parser_version=adapter.parser_version,
                notes=spec.notes,
            )
            session.add(release)
            session.flush()
        run.release_id = release.id
        session.commit()
        stats.stop_stage("release")

        parsed: ParsedRelease
        stats.start_stage("parse")
        try:
            parsed = adapter.parse(spec)
        except Exception as exc:  # schema drift and unreadable files fail closed
            stats.stop_stage("parse")
            if not was_published:
                release.ingestion_status = "failed"
                release.publication_status = PUBLICATION_QUARANTINED
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_summary = f"parse_error: {exc}"[:1000]
            issue = {
                "code": "parse_error",
                "severity": "fatal",
                "message": str(exc),
                "row_reference": None,
            }
            all_issues.append(issue)
            # A retry can fail again; keep one current open parse issue rather
            # than accumulating duplicates for the same release.
            _resolve_open_issues(session, release.id, "parse_error")
            session.add(
                QualityIssue(
                    release_id=release.id,
                    issue_code="parse_error",
                    severity="fatal",
                    message=str(exc),
                    status="open",
                )
            )
            stats.start_stage("report")
            json_path, md_path = _write_report(
                settings, spec=spec, run_id=run_id, status="failed", stats=stats, issues=all_issues
            )
            stats.stop_stage("report")
            stats.finish()
            run.report_path = json_path
            run.stats = stats.snapshot()
            session.commit()
            return IngestResult(
                dataset=spec.dataset_slug,
                release_label=spec.release_label,
                release_id=str(release.id),
                status="failed",
                report_json=json_path,
                report_markdown=md_path,
                stats=stats.snapshot(),
                issues=all_issues,
            )

        stats.stop_stage("parse")
        if not was_published:
            release.parser_version = parsed.parser_version
            release.schema_version = parsed.schema_version
        stats["parser_version"] = parsed.parser_version
        stats["schema_version"] = parsed.schema_version
        stats["parsed_rows"] = len(parsed.rows)
        stats.start_stage("validate")
        validation = adapter.validate(parsed)
        stats.stop_stage("validate")
        validation.rejected_row_references = {
            issue.row_reference
            for issue in validation.issues
            if issue.severity in {"fatal", "error"} and issue.row_reference
        }
        parsed_rows = len(parsed.rows)
        acceptance_rate = validation.accepted_rows / parsed_rows if parsed_rows else None
        rejection_rate = validation.rejected_rows / parsed_rows if parsed_rows else None
        below_acceptance_floor = bool(
            acceptance_rate is not None
            and parsed_rows >= spec.minimum_acceptance_rows
            and acceptance_rate < spec.minimum_acceptance_rate
        )
        # Decide failure before candidate application. A release with no parsed
        # row, no accepted row, or one whose acceptance rate collapsed below the
        # source policy must not mutate canonical facilities at all.
        empty_release = parsed_rows == 0
        validation.failed = (
            empty_release or (validation.accepted_rows == 0 and parsed_rows > 0)
        ) or below_acceptance_floor
        if empty_release:
            validation.issues.append(
                ValidationIssue(
                    "release_empty",
                    "fatal",
                    (
                        "The parser returned no rows. An empty release is treated as "
                        "schema drift and quarantined instead of replacing the last good "
                        "snapshot."
                    ),
                )
            )
        if below_acceptance_floor:
            validation.issues.append(
                ValidationIssue(
                    "acceptance_rate_below_floor",
                    "fatal",
                    (
                        f"Only {validation.accepted_rows} of {parsed_rows} parsed rows were "
                        f"accepted ({acceptance_rate:.1%}), below the "
                        f"{spec.minimum_acceptance_rate:.0%} floor; the release was "
                        "quarantined before canonical writes."
                    ),
                    details={
                        "accepted_rows": validation.accepted_rows,
                        "parsed_rows": parsed_rows,
                        "acceptance_rate": round(acceptance_rate, 4),
                        "minimum_acceptance_rate": spec.minimum_acceptance_rate,
                        "minimum_acceptance_rows": spec.minimum_acceptance_rows,
                    },
                )
            )
        stats["accepted_rows"] = validation.accepted_rows
        stats["rejected_rows"] = validation.rejected_rows
        stats["acceptance_rate"] = (
            round(acceptance_rate, 4) if acceptance_rate is not None else None
        )
        stats["rejection_rate"] = round(rejection_rate, 4) if rejection_rate is not None else None
        stats["minimum_acceptance_rate"] = spec.minimum_acceptance_rate
        stats["minimum_acceptance_rows"] = spec.minimum_acceptance_rows
        stats["acceptance_floor_failed"] = below_acceptance_floor
        stats["rejected_row_references"] = len(validation.rejected_row_references)
        rejected_pairs = {
            (issue.code, issue.row_reference)
            for issue in validation.issues
            if issue.severity in {"fatal", "error"} and issue.row_reference
        }
        rejected_by_code: dict[str, int] = {}
        for code, _row_reference in rejected_pairs:
            rejected_by_code[code] = rejected_by_code.get(code, 0) + 1
        stats["rejected_rows_by_code"] = dict(sorted(rejected_by_code.items()))
        stats["release_failed"] = validation.failed
        stats["duplicate_source_ids"] = sum(
            1 for issue in validation.issues if "duplicate" in issue.code
        )
        for issue in validation.issues:
            all_issues.append(
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": issue.message,
                    "row_reference": issue.row_reference,
                    "details": issue.details,
                }
            )
        if below_acceptance_floor:
            # Keep one open quality issue per release across retries rather than
            # accumulating duplicates when the same bad checksum is retried.
            _resolve_open_issues(session, release.id, "acceptance_rate_below_floor")
            session.add(
                QualityIssue(
                    release_id=release.id,
                    issue_code="acceptance_rate_below_floor",
                    severity="error",
                    message=validation.issues[-1].message,
                    details=validation.issues[-1].details,
                    status="open",
                )
            )

        stats.start_stage("stage_records")
        if validation.failed and was_published:
            # A failed reprocess of a live release must not overwrite the source
            # records that the published snapshot still relies on. Keep the
            # existing rows for issue references and leave them untouched.
            existing_records = list(
                session.scalars(
                    select(SourceRecord).where(SourceRecord.release_id == release.id)
                ).all()
            )
            record_by_key = {record.source_record_key: record for record in existing_records}
            record_by_row: dict[str, uuid.UUID] = {}
            for record in existing_records:
                if record.row_number_or_page:
                    record_by_row.setdefault(record.row_number_or_page, record.id)
            pre_existing_keys = set(record_by_key)
            unchanged_by_key: dict[str, bool] = {}
            _record_issues(
                session,
                issues=validation.issues,
                release=release,
                record_by_row=record_by_row,
            )
            stats["staging_skipped"] = "published_reprocess_failed"
        else:
            (
                record_by_key,
                record_by_row,
                pre_existing_keys,
                unchanged_by_key,
            ) = stage_source_records(
                session,
                release=release,
                parsed=parsed,
                validation=validation,
                reprocess=reprocess,
                force_reapply=force_reapply,
            )
        rejected_references = validation.rejected_row_references
        stats.stop_stage("stage_records")

        stats.start_stage("normalize")
        candidates = adapter.normalize(parsed)
        stats["normalized_candidates"] = len(candidates)
        stats.stop_stage("normalize")
        # Normalization is the last consumer of the parsed row payloads. Drop
        # them before the apply loop so a 60k-row enrollment release does not
        # keep two full copies of every source row alive alongside its
        # candidates and staged source records.
        parsed.rows.clear()
        if validation.failed:
            # The failure decision was made before application. Keep the parsed
            # staging records and validation issues for audit, but touch no
            # canonical facility.
            candidates = []
            stats["apply_skipped"] = "validation_failed"
        stats.start_stage("apply_candidates")
        linked_record_ids = set(
            session.scalars(
                select(FacilitySourceLink.source_record_id)
                .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
                .where(SourceRecord.release_id == release.id)
            ).all()
        )
        # Geography validation must use the same provenance class as the dataset.
        # A synthetic demo release must never validate real PSGC codes (and a
        # real snapshot must never make synthetic demo codes look official).
        geography_query = select(GeographicRelease)
        if dataset.is_synthetic:
            geography_query = geography_query.where(GeographicRelease.is_synthetic.is_(True))
        else:
            geography_query = geography_query.where(GeographicRelease.is_synthetic.is_(False))
        latest_geo = session.scalars(
            geography_query.order_by(GeographicRelease.reference_date.desc().nullslast())
        ).first()
        # Bulk releases repeat generic facility names heavily. Keeping the slug
        # set in memory avoids one or more SELECTs per duplicate name.
        used_slugs = set(session.scalars(select(Facility.slug)).all())
        # A retired slug is still resolvable, so a new clean slug must not
        # reuse it.
        used_slugs.update(session.scalars(select(FacilitySlugAlias.slug)).all())
        # Preload this agency's entity links once, as facility IDs. A first bulk
        # load otherwise issues one lookup per row for an entity that cannot
        # exist yet. Keeping IDs rather than Facility instances means the apply
        # loop only holds the facilities in its current flush batch; older
        # instances are expunged instead of accumulating for 60k rows.
        facility_by_entity: dict[str, uuid.UUID] = {}
        # DepEd publishes one six-digit school ID in several datasets (EBEIS,
        # the SY 2020-2021 masterlist, Project Bukas). Materialising every
        # duplicate row would enlarge the session identity map by tens of
        # thousands of Facility objects for no benefit, so keep only the latest
        # link per entity in the database and then in memory.
        entity_rows = session.execute(
            select(FacilitySourceLink.source_entity_id, Facility.id)
            .join(Facility, FacilitySourceLink.facility_id == Facility.id)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .where(
                Dataset.agency_id == agency.id,
                FacilitySourceLink.source_entity_id.is_not(None),
            )
            .ext(distinct_on(FacilitySourceLink.source_entity_id))
            .order_by(
                FacilitySourceLink.source_entity_id,
                Release.retrieved_at.desc(),
            )
        ).all()
        for entity_id, facility_id in entity_rows:
            if entity_id:
                facility_by_entity.setdefault(entity_id, facility_id)
        # PhilHealth's explicit SEC field is the only sector evidence currently
        # ingested. Load the accumulated values once so a facility appearing in
        # several provider categories is classified consistently, and never by
        # last-writer-wins.
        sector_by_facility: dict[uuid.UUID, set[str]] = {}
        for facility_id, sector_code in session.execute(
            select(HealthAccreditation.facility_id, HealthAccreditation.sector_code).where(
                HealthAccreditation.sector_code.is_not(None)
            )
        ).all():
            value = (sector_code or "").strip().upper()
            if value in {"G", "P"}:
                sector_by_facility.setdefault(facility_id, set()).add(value)
        applied_candidate_keys: set[str] = set()
        pending_matches: list[tuple[Facility, SourceRecord]] = []
        pending_observations: list[dict[str, Any]] = []
        new_facilities: list[Facility] = []
        current_location_by_facility: dict[uuid.UUID, FacilityLocation | None] = {}
        # A health release can match an existing facility through a DOH code
        # that an earlier agency already recorded. Resolve those links in one
        # batched query so the apply loop does not select per row.
        facility_by_doh_id = _preload_facility_by_doh_id(session, candidates)
        # A stale-but-valid release can update every facility from an earlier
        # release. Preload the per-facility state that the update path would
        # otherwise query row by row: the current location and the pre-release
        # snapshot (one existence query plus one query per child table).
        candidate_facility_ids = _candidate_facility_ids(
            candidates=candidates,
            facility_by_entity=facility_by_entity,
            facility_by_doh_id=facility_by_doh_id,
        )
        bulk_apply_reset = bool(getattr(adapter, "bulk_apply_reset", False))
        if not bulk_apply_reset:
            # The preload holds one FacilityLocation per touched facility. A
            # bulk enrichment release would pin tens of thousands of them for
            # the whole run, so it resolves the current location per row and
            # releases it at the next flush instead.
            current_location_by_facility.update(
                _preload_current_locations(session, candidate_facility_ids)
            )
        update_prefetch = FacilityUpdatePrefetch(
            session, release=release, facility_ids=candidate_facility_ids
        )
        applied_since_flush = 0
        applied_total = 0
        known_psgc: set[str] = set()
        if latest_geo:
            known_psgc = set(
                session.scalars(
                    select(AdministrativeUnit.psgc_code).where(
                        AdministrativeUnit.release_id == latest_geo.id
                    )
                ).all()
            )
        else:
            all_issues.append(
                {
                    "code": "psgc_release_missing",
                    "severity": "warning",
                    "message": "No PSGC release is loaded; geography remains unresolved.",
                    "row_reference": None,
                }
            )
        # Bulk apply allocates hundreds of thousands of short-lived dicts and
        # ORM rows. Python's generational GC would repeatedly walk the whole
        # heap, which is pathological on a 60k-row release under memory
        # pressure. Freeze the already-loaded reference data, pause cyclic GC
        # for the tight loop, and restore it before the final flush.
        gc.collect()
        gc.freeze()
        gc.disable()
        # Assertions are insert-only. Collect them as mappings and bulk insert
        # them per flush instead of retaining one ORM instance per assertion in
        # the session identity map.
        session.info[BULK_ASSERTIONS_KEY] = True
        for candidate in candidates:
            if candidate.row_reference in rejected_references:
                stats["unresolved"] += 1
                continue
            if candidate.source_record_key in applied_candidate_keys:
                # A source file can repeat a row. The first occurrence is retained and
                # linked; the repeated occurrence is recorded as a quality issue rather
                # than violating the one-link-per-source-record constraint.
                all_issues.append(
                    {
                        "code": "duplicate_source_row",
                        "severity": "warning",
                        "message": "Duplicate source row skipped after the first occurrence.",
                        "row_reference": candidate.row_reference,
                    }
                )
                stats["duplicate_source_ids"] += 1
                continue
            applied_candidate_keys.add(candidate.source_record_key)
            if candidate.location.psgc_code:
                stats["psgc_provided"] += 1
                if latest_geo and candidate.location.psgc_code not in known_psgc:
                    all_issues.append(
                        {
                            "code": "psgc_unmatched",
                            "severity": "warning",
                            "message": (
                                f"PSGC code {candidate.location.psgc_code} is not in the "
                                f"{latest_geo.release_label} release; kept unresolved."
                            ),
                            "row_reference": candidate.row_reference,
                        }
                    )
                    candidate.location.psgc_code = None
                else:
                    stats["psgc_matched"] += 1
            outside = coordinate_issue(candidate.location.latitude, candidate.location.longitude)
            if outside is not None:
                all_issues.append(
                    {
                        "code": "coordinate_outside_philippines_bbox",
                        "severity": "warning",
                        "message": outside["message"],
                        "row_reference": candidate.row_reference,
                        "details": outside["details"],
                    }
                )
            record = record_by_key.get(candidate.source_record_key)
            if record is None:
                continue
            if (
                reprocess
                and candidate.source_record_key in pre_existing_keys
                and unchanged_by_key.get(candidate.source_record_key)
                and record.id in linked_record_ids
            ):
                # Reparsing an unchanged, already-applied row must not re-assert
                # canonical attributes. Without this guard, re-running one release
                # would let last-writer-wins order churn names and subtypes that no
                # source row actually changed.
                stats["reprocess_skipped_unchanged"] += 1
                continue
            applied_facility = _apply_candidate(
                session,
                candidate=candidate,
                release=release,
                record=record,
                agency=agency,
                dataset=dataset,
                gate=gate,
                parser_version=adapter.parser_version,
                stats=stats,
                enqueue_matches=spec.enqueue_cross_source_matches,
                used_slugs=used_slugs,
                facility_by_entity=facility_by_entity,
                facility_by_doh_id=facility_by_doh_id,
                sector_by_facility=sector_by_facility,
                pending_matches=pending_matches,
                new_facilities=new_facilities,
                current_location_by_facility=current_location_by_facility,
                record_is_new=candidate.source_record_key not in pre_existing_keys,
                update_prefetch=update_prefetch,
                pending_observations=pending_observations,
            )
            # Release the staged row after its candidate has been applied. The
            # raw payload is the largest per-row object in the run, and no
            # later candidate needs this source record.
            record_by_key.pop(candidate.source_record_key, None)
            applied_since_flush += 1
            if applied_since_flush >= APPLY_FLUSH_BATCH_SIZE:
                # Bound memory and keep the INSERT batches large enough to
                # amortise round trips without one flush per facility.
                _flush_new_facilities(session, new_facilities)
                session.flush()
                flush_attribute_assertions(session)
                flush_enrollment_observations(session, pending_observations)
                # Rollback snapshots and profile/location caches otherwise pin
                # every touched facility for the whole 60k-row release. They
                # are durable after the flush, so the next batch can reload
                # only what it needs.
                session.info.get("release_facility_snapshots", {}).clear()
                current_location_by_facility.clear()
                update_prefetch.reset(release=release)
                # Cyclic garbage from the per-row ORM graphs (source records,
                # snapshots and their child state) cannot be reclaimed while
                # automatic GC is paused for the bulk loop. Collect at each
                # batch boundary so a 40k-row release does not grow to multiple
                # gigabytes and start swapping; keep automatic GC disabled
                # between collections to avoid repeatedly walking the heap.
                gc.collect()
                applied_since_flush = 0
                applied_total += APPLY_FLUSH_BATCH_SIZE
                if applied_total % 10_000 == 0:
                    print(
                        f"applied {applied_total} rows; "
                        f"maxrss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024} MiB",
                        flush=True,
                    )
            # Attribute assertions are written by _apply_candidate for every
            # source-supplied field, including display_name and ownership.
            facility_id = applied_facility.id if applied_facility else None
            if facility_id:
                if candidate.location.latitude is None and candidate.location.longitude is None:
                    _record_issues(
                        session,
                        issues=[
                            ValidationIssue(
                                "location_missing",
                                "info",
                                "No source coordinate or area geometry; the facility is "
                                "unmapped rather than placed at an invented point.",
                                row_reference=candidate.row_reference,
                            )
                        ],
                        release=release,
                        record_by_row=record_by_row,
                        facility_id=facility_id,
                    )
                elif candidate.location.precision == "unknown":
                    _record_issues(
                        session,
                        issues=[
                            ValidationIssue(
                                "location_precision_unknown",
                                "warning",
                                "Coordinates are present but the source did not declare a "
                                "coordinate precision; they must not be presented as a precise "
                                "building pin.",
                                row_reference=candidate.row_reference,
                            )
                        ],
                        release=release,
                        record_by_row=record_by_row,
                        facility_id=facility_id,
                    )

        gc.enable()
        gc.unfreeze()
        _flush_new_facilities(session, new_facilities)
        session.flush()
        flush_attribute_assertions(session)
        flush_enrollment_observations(session, pending_observations)
        session.info.pop(BULK_ASSERTIONS_KEY, None)
        if pending_matches:
            # Deferred cross-source matching runs once, after every link exists.
            for pending_facility, pending_record in pending_matches:
                _maybe_flag_cross_source(
                    session,
                    pending_facility,
                    agency,
                    pending_record,
                    release,
                    stats,
                )
        stats.stop_stage("apply_candidates")
        stats["psgc_match_rate"] = (
            round(stats["psgc_matched"] / stats["psgc_provided"], 4)
            if stats["psgc_provided"]
            else None
        )
        previous_release = session.scalars(
            select(Release)
            .where(
                Release.dataset_id == release.dataset_id,
                Release.id != release.id,
                Release.ingestion_status == "published",
                Release.row_count_parsed.is_not(None),
            )
            .order_by(Release.retrieved_at.desc())
            .limit(1)
        ).first()
        anomaly = row_count_anomaly(
            previous_release.row_count_parsed if previous_release else None,
            parsed_rows,
        )
        stats["row_count_previous"] = (
            previous_release.row_count_parsed if previous_release else None
        )
        stats["row_count_ratio"] = anomaly["ratio"] if anomaly else None
        stats["row_count_anomaly"] = bool(anomaly)
        if anomaly:
            message = (
                f"Parsed row count changed from {anomaly['previous_count']} to "
                f"{anomaly['current_count']} (ratio {anomaly['ratio']}); review the source "
                "before treating this release as comparable."
            )
            session.add(
                QualityIssue(
                    release_id=release.id,
                    issue_code="row_count_anomaly",
                    severity="warning",
                    message=message,
                    details={
                        **anomaly,
                        "previous_release": previous_release.source_release_label,
                    },
                    status="open",
                )
            )
            all_issues.append(
                {
                    "code": "row_count_anomaly",
                    "severity": "warning",
                    "message": message,
                    "row_reference": None,
                    "details": anomaly,
                }
            )
        failed = validation.failed
        if not failed:
            # A previous attempt may have failed during parsing; this release has
            # now been parsed successfully, so the transient issue is closed.
            _resolve_open_issues(session, release.id, "parse_error")
        public_release = _dataset_is_public(dataset, gate)
        if not (failed and was_published):
            # A failed reprocess leaves the live release's committed snapshot
            # exactly as it was. Any other outcome records the new metadata.
            release.source_release_label = spec.release_label
            release.source_published_at = spec.source_published_at
            release.reference_period_start = spec.reference_period_start
            release.reference_period_end = spec.reference_period_end
            release.retrieved_at = spec.retrieved_at or release.retrieved_at
            release.raw_object_uri = preserved.uri
            release.parser_version = parsed.parser_version
            release.schema_version = parsed.schema_version
            release.terms_review_status = (
                "synthetic_demo"
                if spec.is_synthetic
                else normalize_rights(spec.redistribution_status)
            )
            release.row_count_parsed = parsed_rows
            release.row_count_reported = stats.get("input_rows") or parsed_rows
            release.processed_at = datetime.now(UTC)
            release.ingestion_status = "failed" if failed else "published"
            if failed:
                # A new failed release is quarantined. A previously published
                # release is handled by the branch above.
                release.publication_status = PUBLICATION_QUARANTINED
            elif public_release:
                release.publication_status = PUBLICATION_PUBLISHED
            else:
                release.publication_status = (
                    PUBLICATION_INTERNAL_ONLY
                    if gate.status == PUBLICATION_INTERNAL_ONLY
                    else PUBLICATION_BLOCKED
                )
        if public_release and not failed:
            dataset.publication_status = PUBLICATION_PUBLISHED
        elif dataset.publication_status == PUBLICATION_APPROVED and not public_release:
            dataset.publication_status = PUBLICATION_BLOCKED
        run.status = "failed" if failed else "published"
        run.finished_at = datetime.now(UTC)
        stats.finish()
        run.stats = stats.snapshot()
        stats.start_stage("report")
        json_path, md_path = _write_report(
            settings,
            spec=spec,
            run_id=run_id,
            status=run.status,
            stats=stats,
            issues=all_issues,
        )
        stats.stop_stage("report")
        stats.finish()
        run.report_path = json_path
        run.stats = stats.snapshot()
        session.commit()
        return IngestResult(
            dataset=spec.dataset_slug,
            release_label=spec.release_label,
            release_id=str(release.id),
            status=run.status,
            report_json=json_path,
            report_markdown=md_path,
            stats=stats.snapshot(),
            issues=all_issues,
        )
    except Exception as exc:
        session.rollback()
        if run and run.id:
            persisted_run = session.get(IngestionRun, run.id)
            if persisted_run:
                persisted_run.status = "failed"
                persisted_run.finished_at = datetime.now(UTC)
                persisted_run.error_summary = str(exc)[:1000]
        if release and not was_published:
            persisted_release = session.get(Release, release.id)
            if persisted_release:
                persisted_release.ingestion_status = "failed"
                # A release that was never public must not be left looking
                # approved after an unexpected apply error. A previously
                # published release keeps serving its last good data.
                if persisted_release.publication_status != PUBLICATION_PUBLISHED:
                    persisted_release.publication_status = PUBLICATION_QUARANTINED
        session.commit()
        raise


def _latest_run_failed(session: Session, release_id: uuid.UUID) -> bool:
    """True when the newest run for a release ended in failure.

    A failed reprocess deliberately leaves the release published so the last
    good snapshot stays visible. Re-running the same checksum without
    ``--reprocess`` must retry that release rather than treating it as an
    unchanged duplicate.
    """

    status = session.scalar(
        select(IngestionRun.status)
        .where(IngestionRun.release_id == release_id)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
        .limit(1)
    )
    return status == "failed"


def _preload_facility_by_doh_id(
    session: Session, candidates: list[FacilityCandidate]
) -> dict[str, uuid.UUID | None]:
    """Resolve DOH facility codes already stored on a health profile.

    A code that maps to more than one canonical facility is stored as ``None``
    so the apply step can reject the row as ambiguous instead of silently
    merging two established facilities. Only codes present in this release are
    queried.
    """

    codes = sorted(
        {
            candidate.health.doh_facility_id
            for candidate in candidates
            if candidate.health is not None and candidate.health.doh_facility_id
        }
    )
    resolved: dict[str, uuid.UUID | None] = {}
    for start in range(0, len(codes), UPDATE_PREFETCH_CHUNK_SIZE):
        chunk = codes[start : start + UPDATE_PREFETCH_CHUNK_SIZE]
        rows = session.execute(
            select(HealthProfile.doh_facility_id, Facility.id)
            .join(Facility, Facility.id == HealthProfile.facility_id)
            .where(HealthProfile.doh_facility_id.in_(chunk))
        ).all()
        for code, facility_id in rows:
            if code in resolved:
                existing = resolved[code]
                if existing is None or existing != facility_id:
                    resolved[code] = None
            else:
                resolved[code] = facility_id
    return resolved


def _candidate_facility_ids(
    *,
    candidates: list[FacilityCandidate],
    facility_by_entity: dict[str, uuid.UUID],
    facility_by_doh_id: dict[str, uuid.UUID | None] | None = None,
) -> list[uuid.UUID]:
    """Return existing facilities touched by this release, in apply order.

    Snapshot prefetching loads one chunk when its first facility is captured.
    Preserving first-candidate order means that chunk has not been mutated yet.
    """

    facility_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for candidate in candidates:
        entity_id = candidate.source_entity_id or candidate.source_record_key
        facility_id = facility_by_entity.get(entity_id)
        if facility_id is None and facility_by_doh_id and candidate.health is not None:
            facility_id = facility_by_doh_id.get(candidate.health.doh_facility_id or "")
        if facility_id is not None and facility_id not in seen:
            seen.add(facility_id)
            facility_ids.append(facility_id)
    return facility_ids


def _preload_current_locations(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FacilityLocation | None]:
    """Load current locations for an update batch in one query per chunk."""

    locations: dict[uuid.UUID, FacilityLocation | None] = {
        facility_id: None for facility_id in facility_ids
    }
    for start in range(0, len(facility_ids), UPDATE_PREFETCH_CHUNK_SIZE):
        chunk = facility_ids[start : start + UPDATE_PREFETCH_CHUNK_SIZE]
        for location in session.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id.in_(chunk),
                FacilityLocation.is_current.is_(True),
            )
        ):
            locations[location.facility_id] = location
    return locations
