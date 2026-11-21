"""API routes split from the original sources router: statistics.

Decorators and route order are preserved; ``sources_common`` owns the shared
``APIRouter`` so ``/v1`` path ordering and OpenAPI output stay identical.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..middleware import conditional_json
from ..models import (
    AdministrativeUnit,
    Agency,
    Dataset,
    Facility,
    FacilityLocation,
    PublicationGate,
    Release,
)
from ..schemas import (
    CoverageOut,
    CoverageRow,
    CoverageSubtypeRow,
    LguCoverageRow,
    SourceCoverageRow,
    StatisticsOut,
)
from ..services import public_facility_index_filter
from ..taxonomy import (
    ACCESS_CLASSES,
    CATEGORY_LABELS,
    FACILITY_CATEGORIES,
    INCLUSION_CLASS_LABELS,
    OWNERSHIP_TYPES,
    PUBLIC_INCLUSION_CLASSES,
)
from .sources_common import _MATCH_STATUSES as _MATCH_STATUSES
from .sources_common import router as router
from .sources_common import settings as settings


def _humanise(value: str) -> str:
    return value.replace("_", " ").title()


def _ordered_counts_from_counts(counts, order: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(counts)
    ordered = {key: counts.get(key, 0) for key in order if counts.get(key, 0)}
    for key, count in counts.most_common():
        if key not in ordered and count:
            ordered[key] = count
    return ordered


@router.get("/statistics", response_model=StatisticsOut, summary="Measured coverage statistics")
def statistics(request: Request, db: Annotated[Session, Depends(get_db)]):
    published = public_facility_index_filter()
    # One grouped pass over the published facilities replaces five separate
    # national scans (totals plus four dimension distributions).
    dimension_rows = db.execute(
        select(
            Facility.inclusion_class,
            Facility.ownership_type,
            Facility.facility_type,
            Facility.public_access_class,
            Facility.is_synthetic,
            func.count(),
        )
        .select_from(Facility)
        .where(*published)
        .group_by(
            Facility.inclusion_class,
            Facility.ownership_type,
            Facility.facility_type,
            Facility.public_access_class,
            Facility.is_synthetic,
        )
    ).all()
    total = 0
    schools = 0
    health = 0
    synthetic = 0
    by_inclusion: Counter[str] = Counter()
    by_ownership: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_access: Counter[str] = Counter()
    for inclusion, ownership_type, category, access, is_synthetic, count in dimension_rows:
        total += count
        if category == "school":
            schools += count
        elif category == "health_facility":
            health += count
        if is_synthetic:
            synthetic += count
        by_inclusion[inclusion] += count
        by_ownership[ownership_type] += count
        by_category[category] += count
        by_access[access] += count
    # One pass over current locations yields the precision and region
    # distributions plus the coordinate count, instead of loading 256k rows.
    region_prefix = func.substr(FacilityLocation.psgc_code, 1, 2)
    precision_region_rows = db.execute(
        select(
            FacilityLocation.precision,
            region_prefix,
            func.count(),
            func.count().filter(
                and_(
                    FacilityLocation.latitude.is_not(None),
                    FacilityLocation.longitude.is_not(None),
                )
            ),
        )
        .select_from(FacilityLocation)
        .join(Facility, Facility.id == FacilityLocation.facility_id)
        .where(*published, FacilityLocation.is_current.is_(True))
        .group_by(FacilityLocation.precision, region_prefix)
    ).all()
    precision_counts: Counter[str] = Counter()
    region_counts: Counter[str | None] = Counter()
    with_coords = 0
    for precision, prefix, count, coordinate_count in precision_region_rows:
        if precision:
            precision_counts[precision] += count
        region_counts[(prefix or "")[:2] or None] += count
        with_coords += coordinate_count
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
        by_precision=dict(precision_counts.most_common()),
        by_region=[
            {
                "region_code_prefix": prefix,
                "region_name": region_names.get(prefix),
                "facility_count": count,
            }
            for prefix, count in region_counts.most_common()
        ],
        by_inclusion_class=_ordered_counts_from_counts(by_inclusion, PUBLIC_INCLUSION_CLASSES),
        by_ownership_type=_ordered_counts_from_counts(by_ownership, OWNERSHIP_TYPES),
        by_category=_ordered_counts_from_counts(by_category, FACILITY_CATEGORIES),
        by_access_class=_ordered_counts_from_counts(by_access, ACCESS_CLASSES),
        source_releases=release_count,
        caveats=[
            (
                "Statistics describe published PhilFacilities records, not the complete "
                "national facility universe."
            ),
            (
                "Government, private public-service, public-access venue and unclassified "
                "records are counted separately; the combined total is never a "
                "government-facility count."
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
                "Government, private public-service, public-access venue and unclassified "
                "records are counted separately."
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
    published = public_facility_index_filter()
    coordinate_filter = and_(
        FacilityLocation.latitude.is_not(None),
        FacilityLocation.longitude.is_not(None),
    )
    # Aggregate the published set by its dimensions in one grouped pass. Loading
    # 258k facility rows into Python took ~7s and produced the same counters.
    dimension_rows = db.execute(
        select(
            Facility.inclusion_class,
            Facility.ownership_type,
            Facility.facility_type,
            Facility.facility_subtype,
            Facility.public_access_class,
            func.count(),
            func.count().filter(coordinate_filter),
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
        .group_by(
            Facility.inclusion_class,
            Facility.ownership_type,
            Facility.facility_type,
            Facility.facility_subtype,
            Facility.public_access_class,
        )
    ).all()
    counts: dict[str, Counter] = {
        "inclusion_class": Counter(),
        "ownership_type": Counter(),
        "facility_type": Counter(),
        "public_access_class": Counter(),
    }
    coordinate_counts: dict[str, Counter] = {
        "inclusion_class": Counter(),
        "ownership_type": Counter(),
        "facility_type": Counter(),
        "public_access_class": Counter(),
    }
    subtype_counts: Counter = Counter()
    subtype_coordinate_counts: Counter = Counter()
    published_records = 0
    for (
        inclusion,
        ownership_type,
        category,
        subtype,
        access,
        count,
        coordinate_count,
    ) in dimension_rows:
        published_records += count
        for attribute, value in (
            ("inclusion_class", inclusion),
            ("ownership_type", ownership_type),
            ("facility_type", category),
            ("public_access_class", access),
        ):
            counts[attribute][value] += count
            coordinate_counts[attribute][value] += coordinate_count
        subtype_key = (category, subtype or "UNSPECIFIED")
        subtype_counts[subtype_key] += count
        subtype_coordinate_counts[subtype_key] += coordinate_count

    def rows_for(attribute: str, order: tuple[str, ...], labels=None) -> list[CoverageRow]:
        attribute_counts = counts[attribute]
        attribute_coordinates = coordinate_counts[attribute]
        keys = list(order) + sorted(key for key in attribute_counts if key and key not in order)
        return [
            CoverageRow(
                key=key,
                label=(labels or {}).get(key) or _humanise(key),
                facility_count=attribute_counts.get(key, 0),
                published_count=attribute_counts.get(key, 0),
                with_coordinates=attribute_coordinates.get(key, 0),
            )
            for key in keys
            if attribute_counts.get(key, 0)
        ]

    region_prefix = func.substr(FacilityLocation.psgc_code, 1, 2)
    region_rows = db.execute(
        select(
            region_prefix,
            func.count(),
            func.count().filter(coordinate_filter),
        )
        .select_from(FacilityLocation)
        .join(Facility, Facility.id == FacilityLocation.facility_id)
        .where(*published, FacilityLocation.is_current.is_(True))
        .group_by(region_prefix)
    ).all()
    region_counts: Counter[str] = Counter()
    region_coordinate_counts: Counter[str] = Counter()
    for prefix, count, coordinate_count in region_rows:
        key = (prefix or "")[:2] or "UNKNOWN"
        region_counts[key] += count
        region_coordinate_counts[key] += coordinate_count
    category_order = {category: index for index, category in enumerate(FACILITY_CATEGORIES)}
    by_subtype = [
        CoverageSubtypeRow(
            category=category,
            subtype=subtype,
            label=_humanise(subtype),
            facility_count=subtype_counts[(category, subtype)],
            published_count=subtype_counts[(category, subtype)],
            with_coordinates=subtype_coordinate_counts.get((category, subtype), 0),
        )
        for category, subtype in sorted(
            subtype_counts,
            key=lambda key: (
                category_order.get(key[0], len(category_order)),
                -subtype_counts[key],
                key[1],
            ),
        )
    ]
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
    today = datetime.now(UTC).date()

    def _freshness(release: Release | None) -> tuple[int | None, bool | None]:
        if release is None:
            return None, None
        anchor = release.reference_period_end
        if anchor is None and release.source_published_at is not None:
            anchor = release.source_published_at.date()
        if anchor is None:
            anchor = release.retrieved_at.date()
        days = max((today - anchor).days, 0)
        return days, days > settings.coverage_stale_after_days

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
        freshness_days, is_stale = _freshness(release)
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
                rights_status=dataset.redistribution_status,
                freshness_days=freshness_days,
                is_stale=is_stale,
            )
        )

    def _lgu_state(scope: str | None) -> str:
        value = (scope or "UNKNOWN_COVERAGE").upper()
        if value in {"NATIONAL_OFFICIAL_INVENTORY", "NATIONAL_PARTIAL"}:
            return "NATIONAL"
        if value == "REGIONAL":
            return "REGIONAL"
        if value == "PARTICIPATING_LGUS":
            return "PARTICIPATING_LGUS"
        if value in {"SELECTED_LGUS", "SINGLE_LGU"}:
            return "SELECTED_LGUS"
        return "UNKNOWN"

    lgu_states = (
        "NATIONAL",
        "REGIONAL",
        "PARTICIPATING_LGUS",
        "SELECTED_LGUS",
        "UNKNOWN",
    )
    lgu_buckets: dict[str, list[str]] = {state: [] for state in lgu_states}
    for dataset, _agency, _gate in dataset_rows:
        lgu_buckets[_lgu_state(dataset.coverage_scope)].append(dataset.slug)
    lgu_labels = {
        "NATIONAL": "National source (complete or partial national scope)",
        "REGIONAL": "Regional source",
        "PARTICIPATING_LGUS": "Participating LGUs only",
        "SELECTED_LGUS": "Selected or single LGU only",
        "UNKNOWN": "Coverage scope not established",
    }
    by_lgu_coverage = [
        LguCoverageRow(
            state=state,
            label=lgu_labels[state],
            source_count=len(slugs),
            dataset_slugs=sorted(slugs),
        )
        for state, slugs in lgu_buckets.items()
        if slugs
    ]
    registry_total = db.scalar(select(func.count()).select_from(Facility)) or 0
    payload = CoverageOut(
        as_of=datetime.now(UTC),
        registry_records=registry_total,
        published_records=published_records,
        by_inclusion_class=rows_for(
            "inclusion_class", PUBLIC_INCLUSION_CLASSES, INCLUSION_CLASS_LABELS
        ),
        by_category=rows_for("facility_type", FACILITY_CATEGORIES, CATEGORY_LABELS),
        by_subtype=by_subtype,
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
        by_lgu_coverage=by_lgu_coverage,
        source_coverage=source_rows,
        coverage_stale_after_days=settings.coverage_stale_after_days,
        stale_source_count=sum(1 for row in source_rows if row.is_stale),
        caveats=[
            (
                "Registry totals include records from sources that are not rights-cleared; "
                "those records are not exposed. Published counts include every public "
                "record, including unclassified records."
            ),
            (
                "Source coverage scope describes the source, not proof of national "
                "completeness. Missing records do not prove a facility does not exist."
            ),
            (
                "Freshness is measured from the source's reference period end (or its "
                "publication/retrieval date when no reference period exists), not from "
                "real-time operational availability."
            ),
        ],
    )
    return conditional_json(request, payload.model_dump(mode="json"), max_age=120)
