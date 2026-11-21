"""Service helpers: detail.

Split from ``services.py``; the package __init__ re-exports every name.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import (
    Facility,
    FacilityRelationship,
)
from ..publication import (
    public_source_record_condition,
)
from ..schemas import (
    CompactGeographyOut,
    CompactLocationOut,
    FacilityCompact,
    FacilityCompactListItem,
    FacilityFunctionOut,
    FacilityRelationshipOut,
    FacilityRoleOut,
    FacilityServiceOut,
    FacilitySummary,
    GeographyOut,
    LocationOut,
    SourceRefOut,
)
from .loaders import (
    load_attribute_assertions,
    load_current_locations,
    load_functions,
    load_geography,
    load_roles,
    load_services,
    load_source_evidence,
)
from .quality import quality_for
from .search import decimal_to_float

# ``include=assertions`` is a convenience view, not a paginated endpoint.
# Clients needing the complete claim set must use /assertions.
ASSERTION_INCLUDE_LIMIT = 200


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
                    postal_code=location.postal_code if location else None,
                    psgc_code=location.psgc_code if location else None,
                    review_status=location.review_status if location else None,
                ),
                geography=geo or GeographyOut(),
                source_count=len(sources),
                source_refs=[
                    SourceRefOut(
                        agency_code=source.agency_code,
                        dataset_slug=source.dataset_slug,
                        source_record_id=source.source_record_id,
                    )
                    for source in sources
                ],
                updated_at=facility.updated_at,
            )
        )
    return summaries


def project_compact(summary) -> FacilityCompact:
    return FacilityCompact(
        id=summary.id,
        name=summary.display_name,
        slug=summary.slug,
        display_name=summary.display_name,
        facility_type=summary.facility_type,
        facility_subtype=summary.facility_subtype,
        inclusion_class=summary.inclusion_class,
        ownership=summary.ownership,
        location=CompactLocationOut(
            latitude=summary.location.latitude,
            longitude=summary.location.longitude,
            precision=summary.location.precision,
            address_text=summary.location.address_text,
            psgc_code=summary.location.psgc_code,
        ),
        geography=CompactGeographyOut(
            psgc_code=summary.geography.psgc_code,
            region_name=summary.geography.region_name,
            province_name=summary.geography.province_name,
            municipality_name=summary.geography.municipality_name,
        ),
        source_refs=summary.source_refs,
        updated_at=summary.updated_at,
    )


def project_compact_list_item(summary) -> FacilityCompactListItem:
    """Lean list card: identity/location plus a source count, not full refs."""

    compact = project_compact(summary)
    return FacilityCompactListItem(
        **compact.model_dump(exclude={"source_refs"}),
        source_count=summary.source_count,
    )


def build_facility_compact(
    session: Session,
    facility: Facility,
    geography_release: str | None = None,
) -> FacilityCompact:
    """Project the existing summary into a small card payload.

    Deliberately calls only ``build_summaries``; calling ``build_facility_detail``
    here would keep the slow collection/profile queries and defeat the purpose.
    """

    return project_compact(build_summaries(session, [facility], geography_release)[0])


def build_facility_compact_extended(
    session: Session,
    facility: Facility,
    include: set[str],
    geography_release: str | None = None,
    *,
    resources: list | None = None,
    licenses: list | None = None,
):
    """Attach only the explicitly requested sections to a compact card.

    ``sources``, ``assertions`` and ``domain`` are opt-in: unrequested sections
    stay ``None`` rather than rendering as an empty collection that could be
    mistaken for "no published rows exist".
    """

    from ..schemas import FacilityCompactExtended

    compact = build_facility_compact(session, facility, geography_release)
    result = FacilityCompactExtended(**compact.model_dump())
    if "sources" in include:
        result.sources = load_source_evidence(session, [facility.id]).get(facility.id, [])
    if "assertions" in include:
        result.assertions = load_attribute_assertions(
            session, facility.id, limit=ASSERTION_INCLUDE_LIMIT
        )
    if "domain" in include:
        detail = build_facility_detail(session, facility, geography_release)
        result.school = detail.school
        result.health = detail.health
        result.utility = detail.utility
        result.accreditations = detail.accreditations
        result.resources = resources
        result.licenses = licenses
    return result


def build_facility_detail(
    session: Session,
    facility: Facility,
    geography_release: str | None = None,
) -> FacilitySummary:

    from ..models import (
        FacilityContact,
        HealthAccreditation,
        HealthProfile,
        SchoolProfile,
        UtilityProfile,
    )
    from ..schemas import (
        AccreditationOut,
        ContactOut,
        FacilityDetail,
        HealthProfileOut,
        SchoolProfileOut,
        UtilityProfileOut,
    )

    summary = build_summaries(session, [facility], geography_release)[0]
    sources = load_source_evidence(session, [facility.id]).get(facility.id, [])

    school = None
    health = None
    utility = None
    accreditations: list[AccreditationOut] = []
    if facility.facility_type == "school":
        profile = session.scalars(
            select(SchoolProfile)
            .where(
                SchoolProfile.facility_id == facility.id,
                public_source_record_condition(SchoolProfile.source_record_id),
            )
            # A merged facility can retain both the official six-digit BEIS
            # profile and a prefixed seven-digit duplicate profile. Prefer the
            # shorter (official) identifier deterministically, then the most
            # recent validity period.
            .order_by(
                func.length(SchoolProfile.deped_school_id).asc().nullslast(),
                SchoolProfile.deped_school_id.asc().nullslast(),
                SchoolProfile.valid_from.desc().nullslast(),
            )
        ).first()
        if profile:
            school = SchoolProfileOut(
                deped_school_id=profile.deped_school_id,
                sector=profile.sector,
                school_management=profile.school_management,
                division=profile.division,
                district=profile.district,
                legislative_district=profile.legislative_district,
                settlement_type=profile.settlement_type,
                offering_classification=profile.offering_classification,
                offers_es=profile.offers_es,
                offers_jhs=profile.offers_jhs,
                offers_shs=profile.offers_shs,
                source_record_id=profile.source_record_id,
            )
    elif facility.facility_type == "health_facility":
        profile = session.scalars(
            select(HealthProfile)
            .where(
                HealthProfile.facility_id == facility.id,
                public_source_record_condition(HealthProfile.source_record_id),
            )
            .order_by(HealthProfile.valid_from.desc().nullslast())
        ).first()
        if profile:
            health = HealthProfileOut(
                doh_facility_id=profile.doh_facility_id,
                facility_major_type=profile.facility_major_type,
                facility_type_detail=profile.facility_type_detail,
                facility_category=profile.facility_category,
                ownership_subclassification=profile.ownership_subclassification,
                licensing_status=profile.licensing_status,
                bed_capacity=profile.bed_capacity,
                source_record_id=profile.source_record_id,
            )
        for row in session.scalars(
            select(HealthAccreditation)
            .where(
                HealthAccreditation.facility_id == facility.id,
                public_source_record_condition(HealthAccreditation.source_record_id),
            )
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
                    telephone=row.telephone,
                    email=row.email,
                    street_address=row.street_address,
                    municipality=row.municipality,
                    page_reference=row.page_reference,
                    source_record_id=row.source_record_id,
                )
            )

    elif facility.facility_type == "utility_facility":
        profile = session.scalars(
            select(UtilityProfile)
            .where(
                UtilityProfile.facility_id == facility.id,
                public_source_record_condition(UtilityProfile.source_record_id),
            )
            .order_by(
                UtilityProfile.valid_from.desc().nullslast(),
                UtilityProfile.doe_facility_code,
            )
        ).first()
        if profile:
            utility = UtilityProfileOut(
                doe_facility_code=profile.doe_facility_code,
                resource_type=profile.resource_type,
                technology_type=profile.technology_type,
                connection_type=profile.connection_type,
                grid=profile.grid,
                owner_type=profile.owner_type,
                contract_type=profile.contract_type,
                installed_mw=decimal_to_float(profile.installed_mw),
                dependable_mw=decimal_to_float(profile.dependable_mw),
                number_of_units=profile.number_of_units,
                date_commissioned=profile.date_commissioned,
                source_record_id=profile.source_record_id,
            )

    contacts = [
        ContactOut(
            id=row.id,
            contact_type=row.contact_type,  # type: ignore[arg-type]
            value=row.value,
            label=row.label,
            source_field=row.source_field,
            source_record_id=row.source_record_id,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            review_status=row.review_status,
        )
        for row in session.scalars(
            select(FacilityContact)
            .where(
                FacilityContact.facility_id == facility.id,
                public_source_record_condition(FacilityContact.source_record_id),
            )
            .order_by(FacilityContact.contact_type, FacilityContact.value)
        ).all()
    ]

    function_rows = load_functions(session, [facility.id]).get(facility.id, [])
    service_rows = load_services(session, [facility.id]).get(facility.id, [])
    role_rows = load_roles(session, [facility.id]).get(facility.id, [])
    relationship_rows = session.scalars(
        select(FacilityRelationship).where(
            or_(
                FacilityRelationship.subject_facility_id == facility.id,
                FacilityRelationship.object_facility_id == facility.id,
            ),
            public_source_record_condition(FacilityRelationship.source_record_id),
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
        if related is not None and related.publication_status != "public":
            # A public relationship must not expose the name of an internal
            # facility that the caller cannot otherwise see.
            continue
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
        utility=utility,
        accreditations=accreditations,
        contacts=contacts,
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
