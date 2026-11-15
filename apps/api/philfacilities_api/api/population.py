"""Public read endpoints for approved population statistics.

Facility counts and demographic counts are deliberately separate. A population
value is never merged into a facility record; callers can join by PSGC code when
they need a ratio, and the caveats explain that the value is a saved PSA
OpenSTAT snapshot rather than a live PSA feed.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Dataset, PopulationObservation, Release
from ..rights import PUBLIC_RIGHTS
from ..schemas import PopulationListResponse, PopulationObservationOut

router = APIRouter(tags=["statistics"])

_PUBLIC_STATUSES = ("approved", "published")


def _public_population_filter():
    return (
        Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
        Dataset.publication_status.in_(_PUBLIC_STATUSES),
        Release.publication_status.in_(_PUBLIC_STATUSES),
    )


@router.get(
    "/population",
    response_model=PopulationListResponse,
    summary="Approved 2024 Census population observations",
)
def population(
    db: Annotated[Session, Depends(get_db)],
    psgc: Annotated[
        str | None,
        Query(max_length=12, description="Exact PSGC code, e.g. 1300000000."),
    ] = None,
    level: Annotated[
        str | None,
        Query(max_length=40, description="region, province_or_huc, municipality, barangay."),
    ] = None,
    indicator: Annotated[
        str | None,
        Query(max_length=160, description="Indicator code or exact label."),
    ] = None,
    q: Annotated[
        str | None,
        Query(max_length=120, description="Search the source geographic name."),
    ] = None,
    release_id: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
):
    filters = list(_public_population_filter())
    if psgc:
        filters.append(PopulationObservation.psgc_code == psgc)
    if level:
        filters.append(PopulationObservation.geographic_level == level)
    if indicator:
        filters.append(
            (PopulationObservation.indicator_label == indicator)
            | (PopulationObservation.indicator_code == indicator)
        )
    if q:
        filters.append(PopulationObservation.geographic_name.ilike(f"%{q}%"))
    if release_id:
        try:
            filters.append(PopulationObservation.release_id == uuid.UUID(release_id))
        except ValueError:
            filters.append(PopulationObservation.release_id.is_(None))

    total = (
        db.scalar(
            select(func.count())
            .select_from(PopulationObservation)
            .join(Release, Release.id == PopulationObservation.release_id)
            .join(Dataset, Dataset.id == Release.dataset_id)
            .where(*filters)
        )
        or 0
    )
    rows = db.execute(
        select(PopulationObservation, Release, Dataset)
        .join(Release, Release.id == PopulationObservation.release_id)
        .join(Dataset, Dataset.id == Release.dataset_id)
        .where(*filters)
        .order_by(
            PopulationObservation.geographic_name,
            PopulationObservation.indicator_label,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        PopulationObservationOut(
            id=observation.id,
            psgc_code=observation.psgc_code,
            geographic_level=observation.geographic_level,
            geographic_name=observation.geographic_name,
            indicator_code=observation.indicator_code,
            indicator_label=observation.indicator_label,
            value=float(observation.value) if observation.value is not None else None,
            unit=observation.unit,
            reference_date=observation.reference_date,
            reference_period=observation.reference_period,
            dimensions=observation.dimensions,
            source_url=observation.source_url,
            source_updated_at=observation.source_updated_at,
            retrieved_at=observation.retrieved_at,
            release_id=release.id,
            release_label=release.source_release_label,
            dataset_slug=dataset.slug,
            attribution_text=dataset.attribution_text,
        )
        for observation, release, dataset in rows
    ]
    return PopulationListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        caveats=[
            "Values are saved PSA OpenSTAT snapshots mirrored by BetterGov.PH, not live PSA data.",
            "Missing source values remain null; they are never treated as zero.",
            "Counts are persons or households as labelled, not facility capacity "
            "or service coverage.",
            "PSA remains the authoritative source; cite the PSA table URL and "
            "release shown for each row.",
        ],
    )
