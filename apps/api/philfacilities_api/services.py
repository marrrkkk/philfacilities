"""Shared query helpers that turn rows into public API payloads."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from .models import (
    AdministrativeUnit,
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityFunction,
    FacilityLocation,
    FacilityRelationship,
    FacilityRole,
    FacilityService,
    FacilitySourceLink,
    GeographicRelease,
    Release,
    SourceRecord,
)
from .rights import PUBLIC_RIGHTS
from .schemas import (
    AttributeAssertionOut,
    FacilityFunctionOut,
    FacilityQuality,
    FacilityRelationshipOut,
    FacilityRoleOut,
    FacilityServiceOut,
    FacilitySummary,
    GeographyOut,
    LocationOut,
    QualityWarning,
    SourceEvidence,
)


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def public_source_condition():
    """True when a facility has at least one rights-cleared, published source link."""

    return exists(
        select(1)
        .select_from(FacilitySourceLink)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(
            FacilitySourceLink.facility_id == Facility.id,
            Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
            Dataset.publication_status.in_(("approved", "published")),
            Release.publication_status.in_(("approved", "published")),
        )
        .correlate(Facility)
    )


def public_facility_filter() -> list:
    # Keep the stored publication flag and additionally require current source-link
    # evidence. If rights are withdrawn or a release is quarantined, the record stops
    # being public even before a re-ingestion pass rewrites the cached flag.
    return [
        Facility.publication_status == "public",
        or_(Facility.is_synthetic.is_(True), public_source_condition()),
    ]


def load_current_locations(
    session: Session, facility_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FacilityLocation]:
    if not facility_ids:
        return {}
    result: dict[uuid.UUID, FacilityLocation] = {}
    for chunk in _chunked(facility_ids):
        rows = session.scalars(
            select(FacilityLocation)
            .where(
                FacilityLocation.facility_id.in_(chunk),
                FacilityLocation.is_current.is_(True),
            )
            .order_by(FacilityLocation.created_at.desc())
        ).all()
        for row in rows:
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
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .join(Agency, Dataset.agency_id == Agency.id)
            .where(
                FacilitySourceLink.facility_id.in_(chunk),
                # Restricted/internal evidence must not leak through a public facility
                # page even when the canonical facility is public because of another
                # approved source. Synthetic fixtures retain their demo behaviour.
                or_(
                    Dataset.is_synthetic.is_(True),
                    and_(
                        Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
                        Dataset.publication_status.in_(("approved", "published")),
                        Release.publication_status.in_(("approved", "published")),
                    ),
                ),
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
        or_(
            Dataset.is_synthetic.is_(True),
            and_(
                Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
                Dataset.publication_status.in_(("approved", "published")),
                Release.publication_status.in_(("approved", "published")),
            ),
        ),
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
            .where(FacilityFunction.facility_id.in_(chunk))
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
            .where(FacilityRole.facility_id.in_(chunk))
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
            .where(FacilityService.facility_id.in_(chunk))
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
            barangay_code=by_level.get("barangay").psgc_code if by_level.get("barangay") else None,
            barangay_name=by_level.get("barangay").name if by_level.get("barangay") else None,
        )
    return results, release


def quality_for(
    facility: Facility,
    location: FacilityLocation | None,
    source_count: int,
) -> FacilityQuality:
    warnings: list[QualityWarning] = []
    precision = location.precision if location else "unknown"
    if not location or location.latitude is None or location.longitude is None:
        warnings.append(
            QualityWarning(
                code="no_coordinates",
                severity="info",
                message="No source coordinates were supplied. Location is unknown.",
            )
        )
    elif precision in {"barangay_centroid", "map_geocoded"}:
        warnings.append(
            QualityWarning(
                code="low_precision_location",
                severity="warning",
                message="Coordinates are area-level or geocoded; they do not represent a building.",
            )
        )
    if facility.is_synthetic:
        warnings.append(
            QualityWarning(
                code="synthetic_record",
                severity="info",
                message=(
                    "Synthetic demonstration record; not an official government facility record."
                ),
            )
        )
    if source_count == 0:
        warnings.append(
            QualityWarning(
                code="no_source_evidence",
                severity="warning",
                message="No source record is linked to this facility.",
            )
        )
    return FacilityQuality(
        identity_status="source_linked" if source_count else "unverified",
        location_precision=precision,  # type: ignore[arg-type]
        warnings=warnings,
        source_count=source_count,
    )


def build_summaries(
    session: Session,
    facilities: list[Facility],
    geography_release: str | None = None,
) -> list[FacilitySummary]:
    ids = [facility.id for facility in facilities]
    locations = load_current_locations(session, ids)
    evidence = load_source_evidence(session, ids)
    functions = load_functions(session, ids)
    geographies, _ = load_geography(session, locations, geography_release)
    summaries: list[FacilitySummary] = []
    for facility in facilities:
        location = locations.get(facility.id)
        geo = geographies.get(location.psgc_code if location and location.psgc_code else "", None)
        sources = evidence.get(facility.id, [])
        summaries.append(
            FacilitySummary(
                id=facility.id,
                slug=facility.slug,
                display_name=facility.display_name,
                facility_type=facility.facility_type,  # type: ignore[arg-type]
                facility_subtype=facility.facility_subtype,
                facility_kind=facility.facility_kind,  # type: ignore[arg-type]
                inclusion_class=facility.inclusion_class,  # type: ignore[arg-type]
                ownership=facility.ownership,  # type: ignore[arg-type]
                ownership_type=facility.ownership_type,  # type: ignore[arg-type]
                operator_type=facility.operator_type,  # type: ignore[arg-type]
                public_access_class=facility.public_access_class,  # type: ignore[arg-type]
                functions=sorted({row.function_code for row in functions.get(facility.id, [])}),
                record_status=facility.record_status,  # type: ignore[arg-type]
                publication_status=facility.publication_status,
                is_synthetic=facility.is_synthetic,
                location=LocationOut(
                    latitude=decimal_to_float(location.latitude) if location else None,
                    longitude=decimal_to_float(location.longitude) if location else None,
                    precision=location.precision if location else "unknown",  # type: ignore[arg-type]
                    method=location.method if location else None,
                    address_text=location.address_text if location else None,
                    psgc_code=location.psgc_code if location else None,
                    review_status=location.review_status if location else None,
                ),
                geography=geo or GeographyOut(),
                source_count=len(sources),
                updated_at=facility.updated_at,
            )
        )
    return summaries


def build_facility_detail(
    session: Session,
    facility: Facility,
    geography_release: str | None = None,
) -> FacilitySummary:
    from sqlalchemy import func

    from .models import (
        EnrollmentObservation,
        HealthAccreditation,
        HealthProfile,
        SchoolProfile,
    )
    from .schemas import AccreditationOut, FacilityDetail, HealthProfileOut, SchoolProfileOut

    summary = build_summaries(session, [facility], geography_release)[0]
    sources = load_source_evidence(session, [facility.id]).get(facility.id, [])

    school = None
    health = None
    accreditations: list[AccreditationOut] = []
    if facility.facility_type == "school":
        profile = session.scalars(
            select(SchoolProfile)
            .where(SchoolProfile.facility_id == facility.id)
            .order_by(SchoolProfile.valid_from.desc().nullslast())
        ).first()
        if profile:
            latest_year = session.scalar(
                select(func.max(EnrollmentObservation.school_year)).where(
                    EnrollmentObservation.facility_id == facility.id
                )
            )
            total = None
            if latest_year:
                rows = session.scalars(
                    select(EnrollmentObservation).where(
                        EnrollmentObservation.facility_id == facility.id,
                        EnrollmentObservation.school_year == latest_year,
                    )
                ).all()
                if any(row.grade_level == "total" and row.sex == "all" for row in rows):
                    total = sum(
                        row.learner_count or 0
                        for row in rows
                        if row.grade_level == "total" and row.sex == "all"
                    )
                else:
                    total = sum(row.learner_count or 0 for row in rows)
            school = SchoolProfileOut(
                deped_school_id=profile.deped_school_id,
                sector=profile.sector,
                school_management=profile.school_management,
                annex_status=profile.annex_status,
                offers_es=profile.offers_es,
                offers_jhs=profile.offers_jhs,
                offers_shs=profile.offers_shs,
                reference_school_year=latest_year,
                enrollment_total=total,
                source_record_id=profile.source_record_id,
            )
    elif facility.facility_type == "health_facility":
        profile = session.scalars(
            select(HealthProfile)
            .where(HealthProfile.facility_id == facility.id)
            .order_by(HealthProfile.valid_from.desc().nullslast())
        ).first()
        if profile:
            health = HealthProfileOut(
                doh_facility_id=profile.doh_facility_id,
                facility_category=profile.facility_category,
                service_capability_level=profile.service_capability_level,
                bed_capacity=profile.bed_capacity,
                source_record_id=profile.source_record_id,
            )
        for row in session.scalars(
            select(HealthAccreditation)
            .where(HealthAccreditation.facility_id == facility.id)
            .order_by(HealthAccreditation.valid_until.desc().nullslast())
        ).all():
            accreditations.append(
                AccreditationOut(
                    id=row.id,
                    authority=row.authority,
                    provider_category=row.provider_category,
                    benefit_package=row.benefit_package,
                    accreditation_category=row.accreditation_category,
                    bed_count=row.bed_count,
                    sector_code=row.sector_code,
                    source_status=row.source_status,
                    valid_from=row.valid_from,
                    valid_until=row.valid_until,
                    source_as_of=row.source_as_of,
                    page_reference=row.page_reference,
                    source_record_id=row.source_record_id,
                )
            )

    function_rows = load_functions(session, [facility.id]).get(facility.id, [])
    service_rows = load_services(session, [facility.id]).get(facility.id, [])
    role_rows = load_roles(session, [facility.id]).get(facility.id, [])
    relationship_rows = session.scalars(
        select(FacilityRelationship).where(
            or_(
                FacilityRelationship.subject_facility_id == facility.id,
                FacilityRelationship.object_facility_id == facility.id,
            )
        )
    ).all()
    relationships: list[FacilityRelationshipOut] = []
    for relationship in relationship_rows:
        related_id = (
            relationship.object_facility_id
            if relationship.subject_facility_id == facility.id
            else relationship.subject_facility_id
        )
        related = session.get(Facility, related_id)
        relationships.append(
            FacilityRelationshipOut(
                relationship_type=relationship.relationship_type,
                related_facility_id=related_id,
                related_facility_name=related.display_name if related else None,
                related_facility_slug=related.slug if related else None,
            )
        )

    location = load_current_locations(session, [facility.id]).get(facility.id)
    return FacilityDetail(
        **summary.model_dump(),
        official_name=facility.official_name,
        access_conditions=facility.access_conditions,
        school=school,
        health=health,
        accreditations=accreditations,
        function_details=[
            FacilityFunctionOut(
                function_code=row.function_code,
                source_value=row.source_value,
                source_record_id=row.source_record_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                capacity_value=decimal_to_float(row.capacity_value),
                capacity_unit=row.capacity_unit,
                designation_status=row.designation_status,
            )
            for row in function_rows
        ],
        services=[
            FacilityServiceOut(
                service_code=row.service_code,
                service_name=row.service_name,
                source_field=row.source_field,
                source_record_id=row.source_record_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
            )
            for row in service_rows
        ],
        roles=[
            FacilityRoleOut(
                role_type=row.role_type,
                entity_name=row.entity_name,
                entity_type=row.entity_type,
                source_record_id=row.source_record_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                evidence=row.evidence,
            )
            for row in role_rows
        ],
        relationships=relationships,
        sources=sources,
        quality=quality_for(facility, location, len(sources)),
        created_at=facility.created_at,
    )


def dumps_with_default(value):
    import json

    return json.dumps(value, default=str)


def utcnow() -> datetime:
    return datetime.now(UTC)


def facility_search_condition(q: str):
    """Return a condition matching facilities by name, source key, address, or locality.

    Every branch is an uncorrelated ID query. The previous correlated EXISTS form
    re-ran the source and location joins for every facility and took tens of
    seconds against the national dataset. An uncorrelated UNION lets PostgreSQL
    use the trigram indexes once per branch and hash the result.
    """

    pattern = f"%{q.strip()}%"
    latest_release = (
        select(GeographicRelease.id)
        .order_by(GeographicRelease.reference_date.desc().nullslast())
        .limit(1)
        .scalar_subquery()
    )

    # A location stores only its own PSGC code. Truncate a matching unit's code
    # to its level prefix (region 2, province 5, municipality 7, barangay 10) so
    # a municipality/province/region name finds the facilities below it while a
    # province name does not pull in a whole municipality. The current geographic
    # release is used so retired names do not resurface.
    matched_prefix = case(
        (
            AdministrativeUnit.geographic_level == "region",
            func.substr(AdministrativeUnit.psgc_code, 1, 2),
        ),
        (
            AdministrativeUnit.geographic_level == "province",
            func.substr(AdministrativeUnit.psgc_code, 1, 5),
        ),
        (
            AdministrativeUnit.geographic_level == "municipality",
            func.substr(AdministrativeUnit.psgc_code, 1, 7),
        ),
        else_=AdministrativeUnit.psgc_code,
    )
    locality_ids = (
        select(FacilityLocation.facility_id)
        .join(
            AdministrativeUnit,
            and_(
                AdministrativeUnit.release_id == latest_release,
                AdministrativeUnit.name.ilike(pattern),
                func.starts_with(FacilityLocation.psgc_code, matched_prefix),
            ),
        )
        .where(FacilityLocation.is_current.is_(True))
    )

    source_ids = (
        select(FacilitySourceLink.facility_id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .where(SourceRecord.source_record_key.ilike(pattern))
    )
    address_ids = select(FacilityLocation.facility_id).where(
        FacilityLocation.is_current.is_(True),
        FacilityLocation.address_text.ilike(pattern),
    )

    matched_ids = (
        select(Facility.id)
        .where(Facility.display_name.ilike(pattern))
        .union(
            select(Facility.id).where(Facility.official_name.ilike(pattern)),
            source_ids,
            address_ids,
            locality_ids,
        )
    )
    return Facility.id.in_(matched_ids)
