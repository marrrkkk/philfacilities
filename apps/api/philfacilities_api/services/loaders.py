"""Service helpers: loaders.

Split from ``services.py``; the package __init__ re-exports every name.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import (
    AdministrativeUnit,
    Agency,
    AttributeAssertion,
    Dataset,
    FacilityFunction,
    FacilityLocation,
    FacilityRole,
    FacilityService,
    FacilitySourceLink,
    GeographicRelease,
    Release,
    SourceRecord,
)
from ..publication import (
    latest_public_release_cte,
    public_dataset_condition,
    public_dataset_release_condition,
    public_source_record_condition,
)
from ..publication import (
    latest_published_release_id as _latest_published_release_id,
)
from ..schemas import (
    AttributeAssertionOut,
    GeographyOut,
    SourceEvidence,
)
from .quality import _urban_rural


def load_current_locations(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FacilityLocation]:
    if not facility_ids:
        return {}
    result: dict[uuid.UUID, FacilityLocation] = {}
    for chunk in _chunked(facility_ids):
        # Fetch the current locations through the partial unique index first. The
        # previous query embedded an OR/EXISTS rights predicate, which made
        # PostgreSQL choose a sequential scan of every location for a page of 20.
        # The partial unique index uq_core_facility_locations_current guarantees
        # one current location per facility, so no ORDER BY is needed here.
        # Sorting forced a heap scan and dominated large bulk exports.
        rows = session.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id.in_(chunk),
                FacilityLocation.is_current.is_(True),
            )
        ).all()
        source_record_ids = {row.source_record_id for row in rows if row.source_record_id}
        public_record_ids: set[uuid.UUID] = set()
        if source_record_ids:
            # An internal-only release must not surface its coordinates even if
            # it was the last writer of the current location. This is a small
            # primary-key lookup for the page's locations, not a scan.
            public_record_ids = set(
                session.scalars(
                    select(SourceRecord.id)
                    .join(Release, SourceRecord.release_id == Release.id)
                    .join(Dataset, Release.dataset_id == Dataset.id)
                    .where(
                        SourceRecord.id.in_(source_record_ids),
                        public_dataset_release_condition(),
                    )
                ).all()
            )
        for row in rows:
            if row.source_record_id is not None and row.source_record_id not in public_record_ids:
                continue
            result.setdefault(row.facility_id, row)
    return result


def _chunked(values: list, size: int = 10_000):
    """Yield bounded slices so large bulk exports stay under the bind-parameter limit."""

    for index in range(0, len(values), size):
        yield values[index : index + size]


def load_source_evidence(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[SourceEvidence]]:
    if not facility_ids:
        return {}
    grouped: dict[uuid.UUID, list[SourceEvidence]] = defaultdict(list)
    # Current membership is a set-based join to the newest published release per
    # dataset. A correlated scalar subquery here degraded from milliseconds to
    # tens of seconds as the IN list grew, which made bulk exports impractical.
    latest = latest_public_release_cte()
    for chunk in _chunked(facility_ids):
        rows = session.execute(
            select(
                FacilitySourceLink,
                SourceRecord,
                Release,
                Dataset,
                Agency,
            )
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(latest, SourceRecord.release_id == latest.c.id)
            .join(Release, Release.id == latest.c.id)
            .join(Dataset, Dataset.id == latest.c.dataset_id)
            .join(Agency, Dataset.agency_id == Agency.id)
            .where(
                FacilitySourceLink.facility_id.in_(chunk),
                # Restricted/internal evidence must not leak through a public
                # facility page even when the canonical facility is public
                # because of another approved source. Synthetic fixtures retain
                # their demo behaviour.
                public_dataset_condition(),
            )
            .order_by(Release.retrieved_at.desc())
        ).all()
        for link, record, release, dataset, agency in rows:
            grouped[link.facility_id].append(
                SourceEvidence(
                    id=link.id,
                    agency=agency.name,
                    agency_code=agency.short_code,
                    dataset=dataset.name,
                    dataset_slug=dataset.slug,
                    release_id=release.id,
                    release_label=release.source_release_label,
                    source_record_id=record.source_record_key,
                    source_record_uuid=record.id,
                    row_reference=record.row_number_or_page,
                    source_published_at=release.source_published_at,
                    reference_period_start=release.reference_period_start,
                    reference_period_end=release.reference_period_end,
                    retrieved_at=release.retrieved_at,
                    processed_at=release.processed_at,
                    match_method=link.match_method,
                    match_status=link.match_status,
                    match_confidence=float(link.match_confidence),
                    rights_status=dataset.redistribution_status,
                    publication_status=dataset.publication_status,
                    license_identifier=dataset.license_identifier,
                    attribution_text=dataset.attribution_text,
                    is_synthetic=dataset.is_synthetic,
                )
            )
    return grouped


def load_attribute_assertions(
    session: Session,
    facility_id: uuid.UUID,
    *,
    attribute: str | None = None,
    limit: int = 200,
) -> list[AttributeAssertionOut]:
    """Field-level claims for one public facility.

    Only assertions whose source release is rights-cleared and published are
    exposed. A facility can be public because of one source while another source
    contributing to it is internal; the internal claim must not leak.
    """

    conditions = [
        AttributeAssertion.facility_id == facility_id,
        # An assertion from a release that the dataset has since replaced is
        # history, not current field provenance.
        Release.id == _latest_published_release_id(Dataset.id),
        public_dataset_release_condition(),
    ]
    if attribute:
        conditions.append(AttributeAssertion.attribute_name == attribute)

    rows = session.execute(
        select(
            AttributeAssertion,
            SourceRecord,
            Release,
            Dataset,
            Agency,
            FacilitySourceLink,
        )
        .join(SourceRecord, AttributeAssertion.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .join(
            FacilitySourceLink,
            and_(
                FacilitySourceLink.source_record_id == SourceRecord.id,
                FacilitySourceLink.facility_id == AttributeAssertion.facility_id,
            ),
        )
        .where(*conditions)
        .order_by(AttributeAssertion.asserted_at.desc(), AttributeAssertion.attribute_name)
        .limit(limit)
    ).all()

    return [
        AttributeAssertionOut(
            id=assertion.id,
            attribute=assertion.attribute_name,
            source_field=assertion.source_field,
            raw_value=assertion.raw_value,
            normalized_value=assertion.normalized_value,
            transformation_version=assertion.transformation_version,
            review_status=assertion.review_status,
            asserted_at=assertion.asserted_at,
            source=SourceEvidence(
                id=link.id,
                agency=agency.name,
                agency_code=agency.short_code,
                dataset=dataset.name,
                dataset_slug=dataset.slug,
                release_id=release.id,
                release_label=release.source_release_label,
                source_record_id=record.source_record_key,
                source_record_uuid=record.id,
                row_reference=record.row_number_or_page,
                source_published_at=release.source_published_at,
                reference_period_start=release.reference_period_start,
                reference_period_end=release.reference_period_end,
                retrieved_at=release.retrieved_at,
                processed_at=release.processed_at,
                match_method=link.match_method,
                match_status=link.match_status,
                match_confidence=float(link.match_confidence),
                rights_status=dataset.redistribution_status,
                publication_status=dataset.publication_status,
                license_identifier=dataset.license_identifier,
                attribution_text=dataset.attribution_text,
                is_synthetic=dataset.is_synthetic,
            ),
        )
        for assertion, record, release, dataset, agency, link in rows
    ]


def load_functions(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[FacilityFunction]]:
    grouped: dict[uuid.UUID, list[FacilityFunction]] = defaultdict(list)
    if not facility_ids:
        return grouped
    for chunk in _chunked(facility_ids):
        rows = session.scalars(
            select(FacilityFunction)
            .where(
                FacilityFunction.facility_id.in_(chunk),
                public_source_record_condition(FacilityFunction.source_record_id),
            )
            .order_by(FacilityFunction.function_code)
        ).all()
        for row in rows:
            grouped[row.facility_id].append(row)
    return grouped


def load_roles(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[FacilityRole]]:
    grouped: dict[uuid.UUID, list[FacilityRole]] = defaultdict(list)
    if not facility_ids:
        return grouped
    for chunk in _chunked(facility_ids):
        rows = session.scalars(
            select(FacilityRole)
            .where(
                FacilityRole.facility_id.in_(chunk),
                public_source_record_condition(FacilityRole.source_record_id),
            )
            .order_by(FacilityRole.role_type, FacilityRole.entity_name)
        ).all()
        for row in rows:
            grouped[row.facility_id].append(row)
    return grouped


def load_services(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[FacilityService]]:
    grouped: dict[uuid.UUID, list[FacilityService]] = defaultdict(list)
    if not facility_ids:
        return grouped
    for chunk in _chunked(facility_ids):
        rows = session.scalars(
            select(FacilityService)
            .where(
                FacilityService.facility_id.in_(chunk),
                public_source_record_condition(FacilityService.source_record_id),
            )
            .order_by(FacilityService.service_code)
        ).all()
        for row in rows:
            grouped[row.facility_id].append(row)
    return grouped


def latest_geographic_release(session: Session) -> GeographicRelease | None:
    """Return the newest usable geography release.

    A synthetic demonstration release must never mask a real PSGC snapshot.
    Real releases are preferred even when the synthetic fixture carries a later
    reference date. Releases are still never overwritten; only the ordering of
    currently available releases changes.
    """

    return session.scalars(
        select(GeographicRelease).order_by(
            GeographicRelease.is_synthetic.asc(),
            GeographicRelease.reference_date.desc().nullslast(),
        )
    ).first()


def _walk_ancestors(
    session: Session, release_id: uuid.UUID, codes: set[str]
) -> dict[str, AdministrativeUnit]:
    found: dict[str, AdministrativeUnit] = {}
    frontier = {code for code in codes if code}
    while frontier:
        units = []
        for chunk in _chunked(sorted(frontier)):
            units.extend(
                session.scalars(
                    select(AdministrativeUnit).where(
                        AdministrativeUnit.release_id == release_id,
                        AdministrativeUnit.psgc_code.in_(chunk),
                    )
                ).all()
            )
        next_frontier: set[str] = set()
        for unit in units:
            found[unit.psgc_code] = unit
            if unit.parent_psgc_code and unit.parent_psgc_code not in found:
                next_frontier.add(unit.parent_psgc_code)
        frontier = next_frontier
    return found


def load_geography(
    session: Session,
    locations: dict[uuid.UUID, FacilityLocation],
    release_label: str | None = None,
) -> tuple[dict[str, GeographyOut], GeographicRelease | None]:
    codes = {loc.psgc_code for loc in locations.values() if loc and loc.psgc_code}
    if not codes:
        return {}, None
    if release_label:
        release = session.scalars(
            select(GeographicRelease).where(GeographicRelease.release_label == release_label)
        ).first()
    else:
        release = latest_geographic_release(session)
    if not release:
        return {}, None
    units = _walk_ancestors(session, release.id, codes)
    results: dict[str, GeographyOut] = {}
    for code in codes:
        if code not in units:
            results[code] = GeographyOut(psgc_code=code, psgc_release=release.release_label)
            continue
        chain = []
        cursor = units[code]
        seen = set()
        while cursor and cursor.psgc_code not in seen:
            seen.add(cursor.psgc_code)
            chain.append(cursor)
            cursor = units.get(cursor.parent_psgc_code) if cursor.parent_psgc_code else None
        by_level = {unit.geographic_level: unit for unit in chain}
        barangay = by_level.get("barangay")
        results[code] = GeographyOut(
            psgc_code=code,
            psgc_release=release.release_label,
            region_code=by_level.get("region").psgc_code if by_level.get("region") else None,
            region_name=by_level.get("region").name if by_level.get("region") else None,
            province_code=by_level.get("province").psgc_code if by_level.get("province") else None,
            province_name=by_level.get("province").name if by_level.get("province") else None,
            municipality_code=(
                by_level.get("municipality").psgc_code if by_level.get("municipality") else None
            ),
            municipality_name=(
                by_level.get("municipality").name if by_level.get("municipality") else None
            ),
            barangay_code=barangay.psgc_code if barangay else None,
            barangay_name=barangay.name if barangay else None,
            urban_rural=_urban_rural(barangay.urban_rural if barangay else None),
        )
    return results, release
