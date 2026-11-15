from __future__ import annotations

import csv
import io
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from typing import Annotated

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..csv_safety import sanitize_csv_cell
from ..db import get_db
from ..errors import ApiError
from ..middleware import conditional_json
from ..models import (
    AdministrativeUnit,
    Agency,
    Dataset,
    Facility,
    FacilityChangeEvent,
    FacilityLocation,
    GeographicRelease,
    IngestionRun,
    MatchCandidate,
    PublicationGate,
    QualityIssue,
    Release,
    SourceCheck,
)
from ..schemas import (
    ChangeListResponse,
    CoverageOut,
    CoverageRow,
    DatasetOut,
    MatchCandidateListResponse,
    MatchCandidateOut,
    QualityIssueOut,
    QualitySummary,
    ReleaseOut,
    SourceCheckOut,
    SourceCoverageRow,
    SourceMonitoringOut,
    StatisticsOut,
)
from ..services import build_summaries, public_facility_filter
from ..taxonomy import (
    ACCESS_CLASSES,
    CATEGORY_LABELS,
    FACILITY_CATEGORIES,
    INCLUSION_CLASS_LABELS,
    OWNERSHIP_TYPES,
    PUBLIC_INCLUSION_CLASSES,
)

router = APIRouter(tags=["sources"])

_MATCH_STATUSES = ("pending", "accepted", "rejected", "merged")


def _dataset_payload(
    dataset: Dataset,
    agency: Agency,
    gate,
    latest: Release | None,
    geography_release: GeographicRelease | None = None,
) -> DatasetOut:
    latest_release = None
    if latest:
        latest_release = {
            "id": str(latest.id),
            "label": latest.source_release_label,
            "retrieved_at": latest.retrieved_at,
            "source_published_at": latest.source_published_at,
            "reference_period_start": latest.reference_period_start,
            "reference_period_end": latest.reference_period_end,
            "ingestion_status": latest.ingestion_status,
            "terms_review_status": latest.terms_review_status,
            "publication_status": latest.publication_status,
            "row_count_parsed": latest.row_count_parsed,
            "sha256": latest.sha256,
        }
    latest_geography_release = None
    if geography_release:
        latest_geography_release = {
            "id": geography_release.id,
            "release_label": geography_release.release_label,
            "reference_date": geography_release.reference_date,
            "published_at": geography_release.published_at,
            "retrieved_at": geography_release.retrieved_at,
            "source_url": geography_release.source_url,
            "is_synthetic": geography_release.is_synthetic,
        }
    return DatasetOut(
        id=dataset.id,
        agency=agency.name,
        agency_code=agency.short_code,
        slug=dataset.slug,
        name=dataset.name,
        description=dataset.description,
        source_url=dataset.source_url,
        access_method=dataset.access_method,
        terms_url=dataset.terms_url,
        license_identifier=dataset.license_identifier,
        redistribution_status=dataset.redistribution_status,
        rights_basis=dataset.rights_basis,
        attribution_text=dataset.attribution_text,
        personal_data_status=dataset.personal_data_status,
        publication_status=dataset.publication_status,
        coverage_scope=dataset.coverage_scope,  # type: ignore[arg-type]
        coverage_note=dataset.coverage_note,
        update_pattern=dataset.update_pattern,
        schema_version=dataset.schema_version,
        is_public_source=dataset.is_public_source,
        is_synthetic=dataset.is_synthetic,
        publication_gate_status=gate.status if gate else None,
        latest_release=latest_release,
        latest_geography_release=latest_geography_release,
    )


def _is_geography_dataset(dataset: Dataset) -> bool:
    """PSGC releases are held in the geography ledger rather than the row-file ledger."""

    return "psgc" in dataset.slug.lower() or "psgc" in dataset.name.lower()


def _latest_geography_release(
    db: Session, dataset: Dataset | None = None
) -> GeographicRelease | None:
    """Return the newest geography release relevant to a dataset.

    Synthetic demo geography must never mask a real snapshot. A real dataset only
    receives a real geography release; a blocked dataset receives none. When no
    dataset is supplied, prefer a non-synthetic release.
    """

    query = select(GeographicRelease).order_by(
        GeographicRelease.is_synthetic.asc(),
        GeographicRelease.reference_date.desc().nullslast(),
    )
    if dataset is not None:
        if dataset.is_synthetic:
            query = query.where(GeographicRelease.is_synthetic.is_(True))
        elif "bettergov" in dataset.slug.lower():
            query = query.where(GeographicRelease.is_synthetic.is_(False))
        else:
            return None
    return db.scalars(query).first()


@router.get("/sources", response_model=list[DatasetOut], summary="Dataset and source catalogue")
def list_sources(request: Request, db: Annotated[Session, Depends(get_db)]):
    rows = db.execute(
        select(Dataset, Agency, PublicationGate)
        .join(Agency, Dataset.agency_id == Agency.id)
        .outerjoin(PublicationGate, PublicationGate.dataset_id == Dataset.id)
        .order_by(Agency.short_code, Dataset.slug)
    ).all()
    releases = db.scalars(select(Release).order_by(Release.retrieved_at.desc())).all()
    latest: dict[uuid.UUID, Release] = {}
    for release in releases:
        latest.setdefault(release.dataset_id, release)
    payload = [
        _dataset_payload(
            dataset,
            agency,
            gate,
            latest.get(dataset.id),
            _latest_geography_release(db, dataset) if _is_geography_dataset(dataset) else None,
        ).model_dump(mode="json")
        for dataset, agency, gate in rows
    ]
    return conditional_json(request, payload, max_age=120)


@router.get("/sources/{source_id}", response_model=DatasetOut, summary="One dataset")
def get_source(source_id: str, db: Annotated[Session, Depends(get_db)]):
    query = (
        select(Dataset, Agency, PublicationGate)
        .join(Agency, Dataset.agency_id == Agency.id)
        .outerjoin(PublicationGate, PublicationGate.dataset_id == Dataset.id)
    )
    try:
        dataset = db.get(Dataset, uuid.UUID(source_id))
    except ValueError:
        dataset = None
    if dataset:
        row = db.execute(query.where(Dataset.id == dataset.id)).first()
    else:
        row = db.execute(query.where(Dataset.slug == source_id)).first()
    if not row:
        raise ApiError(404, "dataset_not_found", "No dataset exists with that identifier.")
    dataset, agency, gate = row
    latest = db.scalars(
        select(Release)
        .where(Release.dataset_id == dataset.id)
        .order_by(Release.retrieved_at.desc())
    ).first()
    geography_release = (
        _latest_geography_release(db, dataset) if _is_geography_dataset(dataset) else None
    )
    return _dataset_payload(dataset, agency, gate, latest, geography_release)


def _check_payload(check: SourceCheck, dataset: Dataset, agency: Agency) -> SourceCheckOut:
    return SourceCheckOut(
        id=check.id,
        dataset_id=dataset.id,
        dataset_slug=dataset.slug,
        agency_code=agency.short_code,
        checked_at=check.checked_at,
        status=check.status,
        url=check.url,
        final_url=check.final_url,
        http_status=check.http_status,
        etag=check.etag,
        last_modified=check.last_modified,
        content_type=check.content_type,
        content_length=check.content_length,
        sha256=check.sha256,
        duration_ms=check.duration_ms,
        message=check.message,
        details=check.details,
        next_check_at=check.next_check_at,
    )


@router.get(
    "/source-checks",
    response_model=list[SourceCheckOut],
    summary="Append-only source monitoring checks",
)
def list_source_checks(
    db: Annotated[Session, Depends(get_db)],
    dataset: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    query = (
        select(SourceCheck, Dataset, Agency)
        .join(Dataset, SourceCheck.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .order_by(SourceCheck.checked_at.desc())
        .limit(limit if dataset else max(limit * 10, 500))
    )
    if dataset:
        query = query.where(Dataset.slug == dataset)
    rows = db.execute(query).all()
    payload: list[SourceCheckOut] = []
    seen: set[uuid.UUID] = set()
    for check, dataset_row, agency in rows:
        if dataset is None and dataset_row.id in seen:
            continue
        seen.add(dataset_row.id)
        payload.append(_check_payload(check, dataset_row, agency))
        if len(payload) >= limit:
            break
    return payload


@router.get(
    "/monitoring",
    response_model=list[SourceMonitoringOut],
    summary="Source monitoring dashboard",
)
def monitoring(db: Annotated[Session, Depends(get_db)]):
    datasets = db.execute(
        select(Dataset, Agency)
        .join(Agency, Dataset.agency_id == Agency.id)
        .order_by(Agency.short_code, Dataset.slug)
    ).all()
    checks = db.execute(select(SourceCheck).order_by(SourceCheck.checked_at.desc())).scalars()
    latest_check: dict[uuid.UUID, SourceCheck] = {}
    successful_check: dict[uuid.UUID, SourceCheck] = {}
    for check in checks:
        latest_check.setdefault(check.dataset_id, check)
        if check.status in {"ok", "not_modified"}:
            successful_check.setdefault(check.dataset_id, check)
    releases = db.scalars(select(Release).order_by(Release.retrieved_at.desc())).all()
    latest_release: dict[uuid.UUID, Release] = {}
    for release in releases:
        latest_release.setdefault(release.dataset_id, release)
    payload: list[SourceMonitoringOut] = []
    for dataset, agency in datasets:
        check = latest_check.get(dataset.id)
        success = successful_check.get(dataset.id)
        release = latest_release.get(dataset.id)
        warning = None
        if dataset.publication_status in {"blocked", "internal_only"}:
            warning = "Records are not public because publication is gated."
        elif check and check.status in {"access_blocked", "schema_changed", "source_error"}:
            warning = check.message
        payload.append(
            SourceMonitoringOut(
                dataset_id=dataset.id,
                dataset_slug=dataset.slug,
                dataset_name=dataset.name,
                agency=agency.name,
                agency_code=agency.short_code,
                access_method=dataset.access_method,
                rights_status=dataset.redistribution_status,
                publication_status=dataset.publication_status,
                last_checked_at=check.checked_at if check else None,
                last_successful_at=success.checked_at if success else None,
                check_status=check.status if check else None,
                http_status=check.http_status if check else None,
                last_message=check.message if check else None,
                latest_release_label=release.source_release_label if release else None,
                latest_release_at=release.retrieved_at if release else None,
                latest_release_rows=release.row_count_parsed if release else None,
                next_check_at=check.next_check_at if check else None,
                warning=warning,
            )
        )
    return payload


@router.get("/source-releases", response_model=list[ReleaseOut], summary="Source releases")
def list_source_releases(
    db: Annotated[Session, Depends(get_db)],
    dataset: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    query = (
        select(Release, Dataset, Agency)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .order_by(Release.retrieved_at.desc())
        .limit(limit)
    )
    if dataset:
        query = query.where(Dataset.slug == dataset)
    rows = db.execute(query).all()
    return [
        ReleaseOut(
            id=release.id,
            dataset_slug=dataset_row.slug,
            dataset_name=dataset_row.name,
            agency=agency.name,
            source_release_label=release.source_release_label,
            source_published_at=release.source_published_at,
            reference_period_start=release.reference_period_start,
            reference_period_end=release.reference_period_end,
            retrieved_at=release.retrieved_at,
            processed_at=release.processed_at,
            file_format=release.file_format,
            file_size_bytes=release.file_size_bytes,
            row_count_parsed=release.row_count_parsed,
            ingestion_status=release.ingestion_status,
            terms_review_status=release.terms_review_status,
            publication_status=release.publication_status,
            parser_version=release.parser_version,
            sha256=release.sha256,
        )
        for release, dataset_row, agency in rows
    ]


@router.get("/quality/summary", response_model=QualitySummary, summary="Quality overview")
def quality_summary(request: Request, db: Annotated[Session, Depends(get_db)]):
    facility_count = db.scalar(select(func.count()).select_from(Facility)) or 0
    published = (
        db.scalar(select(func.count()).select_from(Facility).where(*public_facility_filter())) or 0
    )
    synthetic = (
        db.scalar(select(func.count()).select_from(Facility).where(Facility.is_synthetic.is_(True)))
        or 0
    )
    precision_rows = db.execute(
        select(FacilityLocation.precision, func.count())
        .where(FacilityLocation.is_current.is_(True))
        .group_by(FacilityLocation.precision)
    ).all()
    severity_rows = db.execute(
        select(QualityIssue.severity, func.count())
        .where(QualityIssue.status == "open")
        .group_by(QualityIssue.severity)
    ).all()
    match_status_rows = db.execute(
        select(MatchCandidate.match_status, func.count()).group_by(MatchCandidate.match_status)
    ).all()
    redistribution_rows = db.execute(
        select(Dataset.redistribution_status, func.count()).group_by(Dataset.redistribution_status)
    ).all()
    runs = db.execute(
        select(IngestionRun, Dataset.slug)
        .join(Dataset, IngestionRun.dataset_id == Dataset.id)
        .order_by(IngestionRun.started_at.desc())
        .limit(50)
    ).all()
    seen: set[str] = set()
    last_runs = []
    for run, slug in runs:
        if slug in seen:
            continue
        seen.add(slug)
        last_runs.append(
            {
                "dataset": slug,
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "report_path": run.report_path,
            }
        )
    caveats = [
        (
            "Coverage counts describe processed source records, not the real-world "
            "facility universe."
        ),
        "Missing values remain unknown; they are never converted to zero or inactive.",
        (
            "Source publication date, reference period, retrieval time, and processing "
            "time are distinct."
        ),
    ]
    if synthetic:
        caveats.append(
            "Synthetic demonstration records are included in these counts and are "
            "labelled is_synthetic=true in every facility record."
        )
    match_status_counts = dict(match_status_rows)
    payload = QualitySummary(
        as_of=datetime.now(UTC),
        facility_count=facility_count,
        published_facility_count=published,
        synthetic_facility_count=synthetic,
        coordinate_precision={precision: count for precision, count in precision_rows},
        open_issues_by_severity={severity: count for severity, count in severity_rows},
        match_candidates_by_status={
            match_status: match_status_counts.get(match_status, 0)
            for match_status in _MATCH_STATUSES
        },
        datasets_by_redistribution_status={status: count for status, count in redistribution_rows},
        last_successful_runs=last_runs,
        caveats=caveats,
    )
    return conditional_json(request, payload.model_dump(mode="json"), max_age=60)


@router.get(
    "/quality/issues", response_model=list[QualityIssueOut], summary="Open data quality issues"
)
def quality_issues(
    db: Annotated[Session, Depends(get_db)],
    status: str = "open",
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    query = select(QualityIssue).where(QualityIssue.status == status)
    if severity:
        query = query.where(QualityIssue.severity == severity)
    rows = db.scalars(query.order_by(QualityIssue.created_at.desc()).limit(limit)).all()
    return [
        QualityIssueOut(
            id=row.id,
            facility_id=row.facility_id,
            release_id=row.release_id,
            issue_code=row.issue_code,
            severity=row.severity,
            message=row.message,
            details=row.details,
            status=row.status,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]


_MATCH_STATUS_VALUES = frozenset(_MATCH_STATUSES)


def _match_candidate_payload(
    candidate: MatchCandidate,
    source_facility: Facility | None,
    candidate_facility: Facility | None,
) -> MatchCandidateOut:
    evidence = candidate.evidence or {}
    source_snapshot = evidence.get("source_facility_snapshot") or {}
    candidate_snapshot = evidence.get("candidate_facility_snapshot") or {}
    return MatchCandidateOut(
        id=candidate.id,
        candidate_key=candidate.candidate_key,
        match_status=candidate.match_status,
        match_method=candidate.match_method,
        algorithm_version=candidate.algorithm_version,
        match_confidence=float(candidate.match_confidence),
        source_record_id=candidate.source_record_id,
        source_facility_id=candidate.source_facility_id,
        source_facility_name=(
            source_facility.display_name if source_facility else source_snapshot.get("display_name")
        ),
        source_facility_slug=(
            source_facility.slug if source_facility else source_snapshot.get("slug")
        ),
        candidate_facility_id=candidate.candidate_facility_id,
        candidate_facility_name=(
            candidate_facility.display_name
            if candidate_facility
            else candidate_snapshot.get("display_name")
        ),
        candidate_facility_slug=(
            candidate_facility.slug if candidate_facility else candidate_snapshot.get("slug")
        ),
        source_agency_code=candidate.source_agency_code,
        candidate_agency_code=candidate.candidate_agency_code,
        evidence=candidate.evidence,
        reviewed_at=candidate.reviewed_at,
        resolution=candidate.resolution,
        created_at=candidate.created_at,
    )


def _match_candidate_query():
    source_facility = aliased(Facility)
    candidate_facility = aliased(Facility)
    query = (
        select(MatchCandidate, source_facility, candidate_facility)
        .outerjoin(source_facility, MatchCandidate.source_facility_id == source_facility.id)
        .outerjoin(
            candidate_facility, MatchCandidate.candidate_facility_id == candidate_facility.id
        )
    )
    return query, source_facility, candidate_facility


@router.get(
    "/quality/match-candidates",
    response_model=MatchCandidateListResponse,
    summary="Deterministic identity-match review queue",
)
def list_match_candidates(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    if status is not None and status not in _MATCH_STATUS_VALUES:
        raise ApiError(
            400,
            "invalid_match_status",
            "The match status filter is invalid.",
            {"allowed": sorted(_MATCH_STATUS_VALUES)},
        )
    query, _source_alias, _candidate_alias = _match_candidate_query()
    count_query = select(func.count()).select_from(MatchCandidate)
    if status:
        query = query.where(MatchCandidate.match_status == status)
        count_query = count_query.where(MatchCandidate.match_status == status)
    rows = db.execute(query.order_by(MatchCandidate.created_at.desc()).limit(limit)).all()
    status_rows = db.execute(
        select(MatchCandidate.match_status, func.count()).group_by(MatchCandidate.match_status)
    ).all()
    status_counts = dict(status_rows)
    return MatchCandidateListResponse(
        items=[_match_candidate_payload(row[0], row[1], row[2]) for row in rows],
        total=db.scalar(count_query) or 0,
        by_status={
            match_status: status_counts.get(match_status, 0) for match_status in _MATCH_STATUSES
        },
        limit=limit,
    )


@router.get(
    "/quality/match-candidates/{candidate_id}",
    response_model=MatchCandidateOut,
    summary="One identity-match candidate",
)
def get_match_candidate(candidate_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        identifier = uuid.UUID(candidate_id)
    except ValueError as exc:
        raise ApiError(
            404, "match_candidate_not_found", "No match candidate exists with that identifier."
        ) from exc
    query, _source_alias, _candidate_alias = _match_candidate_query()
    row = db.execute(query.where(MatchCandidate.id == identifier)).first()
    if row is None:
        raise ApiError(
            404, "match_candidate_not_found", "No match candidate exists with that identifier."
        )
    return _match_candidate_payload(row[0], row[1], row[2])


def _public_facility_rows(db: Session):
    """Load the public facility set once, with current location evidence."""

    published = public_facility_filter()
    rows = db.execute(
        select(
            Facility.id,
            Facility.facility_type,
            Facility.facility_subtype,
            Facility.inclusion_class,
            Facility.ownership_type,
            Facility.public_access_class,
            Facility.is_synthetic,
            FacilityLocation.id.label("location_id"),
            FacilityLocation.precision,
            FacilityLocation.psgc_code,
            FacilityLocation.latitude,
            FacilityLocation.longitude,
            FacilityLocation.created_at.label("location_created_at"),
        )
        .select_from(Facility)
        .outerjoin(
            FacilityLocation,
            and_(
                FacilityLocation.facility_id == Facility.id,
                FacilityLocation.is_current.is_(True),
            ),
        )
        .where(*published)
    ).all()
    # A facility should have at most one current location, but historical data
    # and imports can leave duplicates. Count each canonical facility once and
    # choose the newest current location, matching the detail-page loader.
    facilities: dict[uuid.UUID, object] = {}
    locations: dict[uuid.UUID, object] = {}
    for row in rows:
        facilities[row.id] = row
        if row.location_id is None:
            continue
        existing = locations.get(row.id)
        if existing is None or row.location_created_at > existing.location_created_at:
            locations[row.id] = row
    return facilities, locations


def _humanise(value: str) -> str:
    return value.replace("_", " ").title()


def _ordered_counts(values, order: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    ordered = {key: counts.get(key, 0) for key in order if counts.get(key, 0)}
    for key, count in counts.most_common():
        if key not in ordered and count:
            ordered[key] = count
    return ordered


@router.get("/statistics", response_model=StatisticsOut, summary="Measured coverage statistics")
def statistics(request: Request, db: Annotated[Session, Depends(get_db)]):
    facilities, locations = _public_facility_rows(db)
    total = len(facilities)
    schools = sum(1 for row in facilities.values() if row.facility_type == "school")
    health = sum(1 for row in facilities.values() if row.facility_type == "health_facility")
    synthetic = sum(1 for row in facilities.values() if row.is_synthetic)
    with_coords = sum(
        1 for row in locations.values() if row.latitude is not None and row.longitude is not None
    )
    precision_rows = Counter(
        row.precision for row in locations.values() if row.precision
    ).most_common()
    region_rows = Counter(
        ((row.psgc_code or "")[:2] or None) for row in locations.values()
    ).most_common()
    region_names = {
        prefix: name
        for prefix, name in db.execute(
            select(
                func.substr(AdministrativeUnit.psgc_code, 1, 2),
                AdministrativeUnit.name,
            ).where(AdministrativeUnit.geographic_level == "region")
        ).all()
    }
    release_count = db.scalar(select(func.count()).select_from(Release)) or 0
    payload = StatisticsOut(
        as_of=datetime.now(UTC),
        facilities_total=total,
        published_facilities=total,
        schools=schools,
        health_facilities=health,
        with_coordinates=with_coords,
        synthetic=synthetic,
        by_precision={precision: count for precision, count in precision_rows},
        by_region=[
            {
                "region_code_prefix": prefix,
                "region_name": region_names.get(prefix),
                "facility_count": count,
            }
            for prefix, count in region_rows
        ],
        by_inclusion_class=_ordered_counts(
            (row.inclusion_class for row in facilities.values()), PUBLIC_INCLUSION_CLASSES
        ),
        by_ownership_type=_ordered_counts(
            (row.ownership_type for row in facilities.values()), OWNERSHIP_TYPES
        ),
        by_category=_ordered_counts(
            (row.facility_type for row in facilities.values()), FACILITY_CATEGORIES
        ),
        by_access_class=_ordered_counts(
            (row.public_access_class for row in facilities.values()), ACCESS_CLASSES
        ),
        source_releases=release_count,
        caveats=[
            (
                "Statistics describe published PhilFacilities records, not the complete "
                "national facility universe."
            ),
            (
                "Government, private public-service and public-access venue counts are "
                "reported separately; the combined total is never a government-facility "
                "count."
            ),
            (
                "Synthetic demonstration records are included in these counts and are "
                "labelled in every facility record."
            ),
        ]
        if synthetic
        else [
            "Statistics describe published PhilFacilities records only.",
            (
                "Government, private public-service and public-access venue counts are "
                "reported separately."
            ),
        ],
    )
    return conditional_json(request, payload.model_dump(mode="json"), max_age=60)


@router.get(
    "/coverage",
    response_model=CoverageOut,
    summary="Registry coverage by class and source",
)
def coverage(request: Request, db: Annotated[Session, Depends(get_db)]):
    facilities, locations = _public_facility_rows(db)
    coordinate_ids = {
        facility_id
        for facility_id, location in locations.items()
        if location.latitude is not None and location.longitude is not None
    }

    def rows_for(attribute: str, order: tuple[str, ...], labels=None) -> list[CoverageRow]:
        values = [(getattr(row, attribute), facility_id) for facility_id, row in facilities.items()]
        counts = Counter(value for value, _identifier in values)
        coordinate_counts = Counter(
            value for value, identifier in values if identifier in coordinate_ids
        )
        keys = list(order) + sorted(key for key in counts if key and key not in order)
        return [
            CoverageRow(
                key=key,
                label=(labels or {}).get(key) or _humanise(key),
                facility_count=counts.get(key, 0),
                published_count=counts.get(key, 0),
                with_coordinates=coordinate_counts.get(key, 0),
            )
            for key in keys
            if counts.get(key, 0)
        ]

    region_counts = Counter(((row.psgc_code or "")[:2] or "UNKNOWN") for row in locations.values())
    region_coordinate_counts = Counter(
        ((row.psgc_code or "")[:2] or "UNKNOWN")
        for facility_id, row in locations.items()
        if facility_id in coordinate_ids
    )
    region_names = {
        str(prefix): name
        for prefix, name in db.execute(
            select(
                func.substr(AdministrativeUnit.psgc_code, 1, 2),
                AdministrativeUnit.name,
            ).where(AdministrativeUnit.geographic_level == "region")
        ).all()
    }
    source_rows: list[SourceCoverageRow] = []
    dataset_rows = db.execute(
        select(Dataset, Agency, PublicationGate)
        .join(Agency, Dataset.agency_id == Agency.id)
        .outerjoin(PublicationGate, PublicationGate.dataset_id == Dataset.id)
        .order_by(Agency.short_code, Dataset.slug)
    ).all()
    releases = db.scalars(select(Release).order_by(Release.retrieved_at.desc())).all()
    latest: dict[uuid.UUID, Release] = {}
    for release in releases:
        latest.setdefault(release.dataset_id, release)
    for dataset, agency, _gate in dataset_rows:
        release = latest.get(dataset.id)
        source_rows.append(
            SourceCoverageRow(
                dataset_slug=dataset.slug,
                dataset_name=dataset.name,
                agency_code=agency.short_code,
                coverage_scope=dataset.coverage_scope or "UNKNOWN_COVERAGE",
                coverage_note=dataset.coverage_note,
                latest_release_label=release.source_release_label if release else None,
                source_published_at=release.source_published_at if release else None,
                reference_period_end=release.reference_period_end if release else None,
                retrieved_at=release.retrieved_at if release else None,
                row_count_parsed=release.row_count_parsed if release else None,
                publication_status=dataset.publication_status,
            )
        )
    registry_total = db.scalar(select(func.count()).select_from(Facility)) or 0
    payload = CoverageOut(
        as_of=datetime.now(UTC),
        registry_records=registry_total,
        published_records=len(facilities),
        by_inclusion_class=rows_for(
            "inclusion_class", PUBLIC_INCLUSION_CLASSES, INCLUSION_CLASS_LABELS
        ),
        by_category=rows_for("facility_type", FACILITY_CATEGORIES, CATEGORY_LABELS),
        by_ownership_type=rows_for("ownership_type", OWNERSHIP_TYPES),
        by_access_class=rows_for("public_access_class", ACCESS_CLASSES),
        by_region=[
            CoverageRow(
                key=prefix,
                label=region_names.get(prefix) or prefix,
                facility_count=count,
                published_count=count,
                with_coordinates=region_coordinate_counts.get(prefix, 0),
            )
            for prefix, count in region_counts.most_common()
        ],
        source_coverage=source_rows,
        caveats=[
            (
                "Registry totals include internal discovery candidates, but their records "
                "are not exposed. Published counts include only rights-cleared sources."
            ),
            (
                "Source coverage scope describes the source, not proof of national "
                "completeness. Missing records do not prove a facility does not exist."
            ),
        ],
    )
    return conditional_json(request, payload.model_dump(mode="json"), max_age=120)


@router.get("/changes", response_model=ChangeListResponse, summary="Canonical change feed")
def changes(
    db: Annotated[Session, Depends(get_db)],
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
):
    query = (
        select(FacilityChangeEvent)
        .join(Facility, Facility.id == FacilityChangeEvent.facility_id)
        .where(*public_facility_filter())
        .order_by(FacilityChangeEvent.changed_at.desc(), FacilityChangeEvent.id.desc())
    )
    if since:
        query = query.where(FacilityChangeEvent.changed_at >= since)
    if cursor:
        changed_at, event_id = _decode_event_cursor(cursor)
        query = query.where(
            or_(
                FacilityChangeEvent.changed_at < changed_at,
                and_(
                    FacilityChangeEvent.changed_at == changed_at,
                    FacilityChangeEvent.id < event_id,
                ),
            )
        )
    rows = list(db.scalars(query.limit(limit + 1)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ChangeListResponse(
        items=[
            {
                "id": row.id,
                "facility_id": row.facility_id,
                "change_type": row.change_type,
                "attribute_name": row.attribute_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "changed_at": row.changed_at,
                "changed_by": row.changed_by,
                "source_record_id": row.source_record_id,
            }
            for row in rows
        ],
        next_cursor=(
            _encode_event_cursor(rows[-1].changed_at, rows[-1].id) if has_more and rows else None
        ),
        has_more=has_more,
    )


def _encode_event_cursor(changed_at: datetime, event_id: uuid.UUID) -> str:
    import base64
    import json

    payload = {"changed_at": changed_at.astimezone(UTC).isoformat(), "id": str(event_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_event_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    import base64
    import json

    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["changed_at"]), uuid.UUID(payload["id"])
    except Exception as exc:
        raise ApiError(400, "invalid_cursor", "The pagination cursor is invalid.") from exc


def _download_conditions(facility_type: str | None = None) -> list:
    # The shared public filter already requires either a synthetic fixture or a
    # rights-cleared, published source link. Use it for exports as well so the bulk
    # files cannot drift from the facility endpoints.
    conditions = list(public_facility_filter())
    if facility_type:
        conditions.append(Facility.facility_type == facility_type)
    return conditions


def _download_rows(db: Session, facility_type: str | None) -> list[dict]:
    facilities = list(
        db.scalars(
            select(Facility)
            .where(*_download_conditions(facility_type))
            .order_by(Facility.display_name)
        ).all()
    )
    summaries = build_summaries(db, facilities)
    from ..services import load_source_evidence

    evidence = load_source_evidence(db, [facility.id for facility in facilities])
    publication_status = {facility.id: facility.publication_status for facility in facilities}
    rows = []
    for summary in summaries:
        sources = evidence.get(summary.id, [])
        rows.append(
            {
                "id": str(summary.id),
                "display_name": summary.display_name,
                "facility_type": summary.facility_type,
                "facility_subtype": summary.facility_subtype or "",
                "ownership": summary.ownership,
                "record_status": summary.record_status,
                "publication_status": publication_status[summary.id],
                "psgc_code": summary.geography.psgc_code or "",
                "psgc_release": summary.geography.psgc_release or "",
                "region_code": summary.geography.region_code or "",
                "region_name": summary.geography.region_name or "",
                "province_code": summary.geography.province_code or "",
                "province_name": summary.geography.province_name or "",
                "municipality_code": summary.geography.municipality_code or "",
                "municipality_name": summary.geography.municipality_name or "",
                "barangay_code": summary.geography.barangay_code or "",
                "barangay_name": summary.geography.barangay_name or "",
                "latitude": summary.location.latitude,
                "longitude": summary.location.longitude,
                "location_precision": summary.location.precision,
                "location_method": summary.location.method or "",
                "address_text": summary.location.address_text or "",
                "source_count": summary.source_count,
                "source_records": "; ".join(
                    f"{item.agency_code}:{item.dataset_slug}:{item.source_record_id}"
                    for item in sources
                ),
                "is_synthetic": summary.is_synthetic,
                "updated_at": summary.updated_at.isoformat(),
            }
        )
    return rows


@router.get("/downloads/facilities.csv", summary="Bulk facility CSV")
def download_facilities_csv(db: Annotated[Session, Depends(get_db)]):
    rows = _download_rows(db, None)
    return _csv_response("facilities", rows)


@router.get("/downloads/schools.csv", summary="Bulk school CSV")
def download_schools_csv(db: Annotated[Session, Depends(get_db)]):
    rows = _download_rows(db, "school")
    return _csv_response("schools", rows)


@router.get("/downloads/health-facilities.csv", summary="Bulk health facility CSV")
def download_health_csv(db: Annotated[Session, Depends(get_db)]):
    rows = _download_rows(db, "health_facility")
    return _csv_response("health-facilities", rows)


@router.get("/downloads/facilities.parquet", summary="Bulk facility Parquet")
def download_facilities_parquet(db: Annotated[Session, Depends(get_db)]):
    rows = _download_rows(db, None)
    if not rows:
        raise ApiError(404, "no_downloadable_data", "No publication-approved facility rows exist.")
    table = pa.Table.from_pylist(rows)
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="zstd")
    return Response(
        content=sink.getvalue(),
        media_type="application/vnd.apache.parquet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="philfacilities-{date.today().isoformat()}.parquet"'
            )
        },
    )


def _csv_response(name: str, rows: list[dict]) -> Response:
    if not rows:
        raise ApiError(404, "no_downloadable_data", "No publication-approved facility rows exist.")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: sanitize_csv_cell(value) for key, value in row.items()})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="philfacilities-{name}-{date.today().isoformat()}.csv"'
            )
        },
    )
