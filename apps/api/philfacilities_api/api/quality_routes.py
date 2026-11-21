"""API routes split from the original sources router: quality.

Decorators and route order are preserved; ``sources_common`` owns the shared
``APIRouter`` so ``/v1`` path ordering and OpenAPI output stay identical.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from ..db import get_db
from ..errors import ApiError
from ..middleware import conditional_json
from ..models import (
    Dataset,
    Facility,
    FacilityLocation,
    IngestionRun,
    MatchCandidate,
    QualityIssue,
)
from ..schemas import (
    MatchCandidateListResponse,
    MatchCandidateOut,
    QualityIssueOut,
    QualitySummary,
)
from ..services import public_facility_index_filter
from .sources_common import _MATCH_STATUSES as _MATCH_STATUSES
from .sources_common import router as router
from .sources_common import settings as settings


@router.get("/quality/summary", response_model=QualitySummary, summary="Quality overview")
def quality_summary(request: Request, db: Annotated[Session, Depends(get_db)]):
    facility_count = db.scalar(select(func.count()).select_from(Facility)) or 0
    published = (
        db.scalar(select(func.count()).select_from(Facility).where(*public_facility_index_filter()))
        or 0
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
