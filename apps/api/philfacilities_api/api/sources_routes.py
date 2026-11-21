"""API routes split from the original sources router: sources.

Decorators and route order are preserved; ``sources_common`` owns the shared
``APIRouter`` so ``/v1`` path ordering and OpenAPI output stay identical.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..middleware import conditional_json
from ..models import (
    Agency,
    Dataset,
    GeographicRelease,
    IngestionRun,
    PublicationGate,
    Release,
    SourceCheck,
)
from ..schemas import (
    DatasetOut,
    ReleaseOut,
    SourceCheckOut,
    SourceMonitoringOut,
)
from .sources_common import _MATCH_STATUSES as _MATCH_STATUSES
from .sources_common import router as router
from .sources_common import settings as settings


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
    # Monitoring shows one row per dataset. Scanning full history here grows
    # without bound as checks, releases, and runs accumulate, so let PostgreSQL
    # return only the newest row for each dataset instead.
    checks = db.scalars(
        select(SourceCheck)
        .order_by(SourceCheck.dataset_id, SourceCheck.checked_at.desc(), SourceCheck.id.desc())
        .ext(distinct_on(SourceCheck.dataset_id))
    ).all()
    latest_check = {check.dataset_id: check for check in checks}
    successful_checks = db.scalars(
        select(SourceCheck)
        .where(SourceCheck.status.in_(("ok", "not_modified")))
        .order_by(SourceCheck.dataset_id, SourceCheck.checked_at.desc(), SourceCheck.id.desc())
        .ext(distinct_on(SourceCheck.dataset_id))
    ).all()
    successful_check = {check.dataset_id: check for check in successful_checks}
    releases = db.scalars(
        select(Release)
        .order_by(Release.dataset_id, Release.retrieved_at.desc(), Release.created_at.desc())
        .ext(distinct_on(Release.dataset_id))
    ).all()
    latest_release = {release.dataset_id: release for release in releases}
    runs = db.scalars(
        select(IngestionRun)
        .order_by(IngestionRun.dataset_id, IngestionRun.started_at.desc(), IngestionRun.id.desc())
        .ext(distinct_on(IngestionRun.dataset_id))
    ).all()
    latest_run = {run.dataset_id: run for run in runs}
    payload: list[SourceMonitoringOut] = []
    for dataset, agency in datasets:
        check = latest_check.get(dataset.id)
        success = successful_check.get(dataset.id)
        release = latest_release.get(dataset.id)
        run = latest_run.get(dataset.id)
        run_stats = (run.stats if run else None) or {}
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
                latest_run_acceptance_rate=run_stats.get("acceptance_rate"),
                latest_run_rejection_rate=run_stats.get("rejection_rate"),
                latest_run_status=run.status if run else None,
                latest_run_at=run.started_at if run else None,
                latest_run_duration_ms=run_stats.get("total_ms"),
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
