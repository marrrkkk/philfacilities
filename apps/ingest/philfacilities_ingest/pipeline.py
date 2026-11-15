from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from philfacilities_api.models import (
    AdministrativeUnit,
    Agency,
    AttributeAssertion,
    Dataset,
    EnrollmentObservation,
    Facility,
    FacilityChangeEvent,
    FacilityFunction,
    FacilityLocation,
    FacilityRole,
    FacilityService,
    FacilitySourceLink,
    GeographicRelease,
    HealthAccreditation,
    HealthLicense,
    HealthProfile,
    IngestionRun,
    PublicationGate,
    QualityIssue,
    Release,
    ResourceObservation,
    SchoolProfile,
    SourceRecord,
)
from philfacilities_api.rights import (
    PUBLIC_RIGHTS,
    PUBLICATION_APPROVED,
    PUBLICATION_BLOCKED,
    PUBLICATION_INTERNAL_ONLY,
    PUBLICATION_PUBLISHED,
    PUBLICATION_QUARANTINED,
    RIGHTS_REVIEW_REQUIRED,
    dataset_is_publishable,
    normalize_rights,
    rights_allow_public,
)
from philfacilities_api.taxonomy import (
    DISCOVERY_CANDIDATE,
    GOVERNMENT_FACILITY,
    GOVERNMENT_UNSPECIFIED,
    PRIVATE_PUBLIC_SERVICE_PROVIDER,
    PRIVATE_UNSPECIFIED,
    PUBLIC_INCLUSION_CLASSES,
    UNKNOWN,
    derive_inclusion_class,
)
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from .config import IngestSettings, get_settings
from .contracts import (
    FacilityCandidate,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    SourceAdapter,
    ValidationIssue,
)
from .eligibility import exclusion_reason
from .matching import enqueue_cross_source_candidates
from .storage import RawStore, build_store

# Kept as a compatibility alias for callers that imported the old set. New code
# should use the canonical rights vocabulary in philfacilities_api.rights.
PUBLIC_REDISTRIBUTION = PUBLIC_RIGHTS
PHILIPPINES_BBOX = {"min_lat": 4.2, "max_lat": 21.5, "min_lon": 116.0, "max_lon": 127.0}
PUBLISHER_TYPE_BY_AGENCY = {
    "bettergov": "community",
    "osm": "community",
    "psa": "government",
    "deped": "government",
    "doh": "government",
    "philhealth": "government",
    "ched": "government",
    "tesda": "government",
}


@dataclass
class IngestResult:
    dataset: str
    release_label: str
    release_id: str | None
    status: str
    report_json: str | None = None
    report_markdown: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)


def build_engine(settings: IngestSettings):
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:120] or "record"


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _json(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def ensure_source(session: Session, spec: ReleaseSpec) -> tuple[Agency, Dataset, PublicationGate]:
    agency = session.scalars(select(Agency).where(Agency.short_code == spec.agency_code)).first()
    if agency is None:
        agency = Agency(
            name=spec.agency_name,
            short_code=spec.agency_code,
            publisher_type=PUBLISHER_TYPE_BY_AGENCY.get(
                spec.agency_code,
                "government" if not spec.is_synthetic else "synthetic_fixture",
            ),
        )
        session.add(agency)
        session.flush()
    elif not spec.is_synthetic:
        # A real release must never leave the synthetic demo label on an agency
        # that now publishes official or rights-cleared records.
        if "(synthetic demo fixture)" in (agency.name or ""):
            agency.name = spec.agency_name
        agency.publisher_type = PUBLISHER_TYPE_BY_AGENCY.get(
            spec.agency_code, agency.publisher_type or "government"
        )
    rights = (
        spec.redistribution_status
        if spec.is_synthetic
        else normalize_rights(spec.redistribution_status)
    )
    requested_publication = spec.requested_publication_status or (
        PUBLICATION_APPROVED if rights_allow_public(rights) else PUBLICATION_BLOCKED
    )
    if spec.personal_data_status and "internal" in spec.personal_data_status.lower():
        requested_publication = PUBLICATION_INTERNAL_ONLY
    dataset = session.scalars(
        select(Dataset).where(Dataset.agency_id == agency.id, Dataset.slug == spec.dataset_slug)
    ).first()
    if dataset is None:
        dataset = Dataset(
            agency_id=agency.id,
            slug=spec.dataset_slug,
            name=spec.dataset_name,
            description=None,
            source_url=spec.source_url,
            access_method=spec.access_method,
            terms_url=spec.terms_url,
            license_identifier=spec.license_identifier,
            redistribution_status=rights,
            rights_basis=spec.rights_basis,
            attribution_text=spec.attribution_text,
            personal_data_status=spec.personal_data_status,
            publication_status=requested_publication,
            coverage_scope=spec.coverage_scope,
            coverage_note=spec.coverage_note,
            update_pattern=spec.update_pattern,
            is_public_source=True,
            is_synthetic=spec.is_synthetic,
        )
        session.add(dataset)
        session.flush()
    else:
        dataset.source_url = spec.source_url or dataset.source_url
        dataset.terms_url = spec.terms_url or dataset.terms_url
        if not dataset.is_synthetic:
            dataset.redistribution_status = rights
        dataset.is_synthetic = dataset.is_synthetic or spec.is_synthetic
        if spec.license_identifier:
            dataset.license_identifier = spec.license_identifier
        if spec.rights_basis:
            dataset.rights_basis = spec.rights_basis
        if spec.attribution_text:
            dataset.attribution_text = spec.attribution_text
        if spec.personal_data_status:
            dataset.personal_data_status = spec.personal_data_status
        if spec.update_pattern:
            dataset.update_pattern = spec.update_pattern
        if spec.coverage_scope:
            dataset.coverage_scope = spec.coverage_scope
        if spec.coverage_note:
            dataset.coverage_note = spec.coverage_note
        if requested_publication in (PUBLICATION_BLOCKED, PUBLICATION_INTERNAL_ONLY):
            dataset.publication_status = requested_publication
    gate = session.scalars(
        select(PublicationGate).where(PublicationGate.dataset_id == dataset.id)
    ).first()
    if gate is None:
        if spec.is_synthetic:
            status = "synthetic_demo"
        elif requested_publication == PUBLICATION_INTERNAL_ONLY:
            status = PUBLICATION_INTERNAL_ONLY
        elif rights_allow_public(rights):
            status = PUBLICATION_APPROVED
        elif normalize_rights(rights) == RIGHTS_REVIEW_REQUIRED:
            status = "review_required"
        else:
            status = PUBLICATION_BLOCKED
        gate = PublicationGate(
            dataset_id=dataset.id,
            status=status,
            scope={"fields": ["facility", "location", "domain", "provenance"]}
            if spec.is_synthetic
            else None,
            reviewer="automated-policy" if spec.is_synthetic else None,
            reviewed_at=datetime.now(UTC) if spec.is_synthetic else None,
            notes=(
                "Synthetic fixture data; not an official government release."
                if spec.is_synthetic
                else (
                    spec.rights_basis
                    or "Publication awaits source-terms review; records remain internal."
                )
            ),
        )
        session.add(gate)
        session.flush()
    return agency, dataset, gate


def _dataset_is_public(dataset: Dataset, gate: PublicationGate) -> bool:
    return dataset_is_publishable(
        redistribution_status=dataset.redistribution_status,
        gate_status=gate.status,
        is_synthetic=dataset.is_synthetic,
        publication_status=dataset.publication_status,
    )


def _existing_release(session: Session, dataset_id: uuid.UUID, sha256: str) -> Release | None:
    return session.scalars(
        select(Release).where(Release.dataset_id == dataset_id, Release.sha256 == sha256)
    ).first()


def _record_issues(
    session: Session,
    *,
    issues: list[ValidationIssue],
    release: Release,
    record_by_row: dict[str, uuid.UUID],
    facility_id: uuid.UUID | None = None,
) -> None:
    for issue in issues:
        session.add(
            QualityIssue(
                facility_id=facility_id,
                source_record_id=record_by_row.get(issue.row_reference or ""),
                release_id=release.id,
                issue_code=issue.code,
                severity=issue.severity if issue.severity != "fatal" else "error",
                message=issue.message,
                details=issue.details,
                status="open",
            )
        )


def _resolve_open_issues(session: Session, release_id: uuid.UUID, issue_code: str) -> None:
    """Retire a transient issue once a later attempt for the same release succeeds."""

    session.execute(
        update(QualityIssue)
        .where(
            QualityIssue.release_id == release_id,
            QualityIssue.issue_code == issue_code,
            QualityIssue.status == "open",
        )
        .values(status="resolved", resolved_at=datetime.now(UTC))
    )


def _find_facility_for_entity(
    session: Session,
    agency_id: uuid.UUID,
    entity_id: str,
    facility_by_entity: dict[str, uuid.UUID] | None = None,
) -> Facility | None:
    if facility_by_entity is not None:
        facility_id = facility_by_entity.get(entity_id)
        return session.get(Facility, facility_id) if facility_id else None
    facility_id = session.scalar(
        select(FacilitySourceLink.facility_id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(
            Dataset.agency_id == agency_id,
            FacilitySourceLink.source_entity_id == entity_id,
        )
        .order_by(Release.retrieved_at.desc())
        .limit(1)
    )
    if facility_id is None:
        return None
    return session.get(Facility, facility_id)


def _new_slug(
    session: Session, name: str, agency_code: str, used_slugs: set[str] | None = None
) -> str:
    """Return an unused facility slug.

    Bulk sources can contain hundreds of identically named facilities (for
    example ``Barangay Health Station``). Querying the database once per suffix
    turns that into quadratic work, so callers that ingest many rows pass a
    preloaded set which is updated in memory.
    """

    base = f"{_slug(name)}-{agency_code}"
    candidate = base
    suffix = 1
    if used_slugs is not None:
        while candidate in used_slugs:
            suffix += 1
            candidate = f"{base}-{suffix}"
        used_slugs.add(candidate)
        return candidate
    while session.scalars(select(Facility.id).where(Facility.slug == candidate)).first():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _add_assertion(
    session: Session,
    *,
    facility_id: uuid.UUID,
    source_record_id: uuid.UUID,
    attribute: str,
    raw_value: Any,
    normalized_value: Any,
    version: str,
    source_field: str | None = None,
    existing: set[tuple[str, str]] | None = None,
) -> None:
    normalized = None if normalized_value is None else str(normalized_value)
    if existing is not None:
        key = (attribute, normalized or "")
        if key in existing:
            return
        existing.add(key)
    session.add(
        AttributeAssertion(
            facility_id=facility_id,
            attribute_name=attribute,
            source_record_id=source_record_id,
            source_field=source_field or attribute,
            raw_value=None if raw_value is None else str(raw_value),
            normalized_value=normalized,
            transformation_version=version,
            review_status="source_supplied",
        )
    )


def _assert_facility_fields(
    session: Session,
    *,
    facility: Facility,
    candidate: FacilityCandidate,
    record: SourceRecord,
    inclusion_class: str,
    version: str,
    existing: set[tuple[str, str]] | None = None,
) -> None:
    """Record the source's claim for every canonical field it supplies.

    The pipeline currently preserves typed source rows and links them to a
    facility, but only a handful of fields had explicit assertions.  These
    claims are what the facility profile exposes as field-level provenance, so
    they must be written for the values actually applied rather than inferred
    later from the canonical row.
    """

    claims = (
        ("display_name", candidate.display_name),
        ("facility_type", candidate.facility_type),
        ("facility_subtype", candidate.facility_subtype),
        ("facility_kind", candidate.facility_kind),
        ("ownership", candidate.ownership),
        ("ownership_type", candidate.ownership_type),
        ("operator_type", candidate.operator_type),
        ("public_access_class", candidate.public_access_class),
        ("access_conditions", candidate.access_conditions),
        ("record_status", candidate.record_status),
        ("inclusion_class", inclusion_class),
    )
    for attribute, value in claims:
        if value in (None, "", "unknown", "UNKNOWN"):
            continue
        _add_assertion(
            session,
            facility_id=facility.id,
            source_record_id=record.id,
            attribute=attribute,
            raw_value=value,
            normalized_value=value,
            version=version,
            existing=existing,
        )


def _apply_sector_ownership(
    session: Session,
    *,
    facility: Facility,
    candidate: FacilityCandidate,
    record: SourceRecord,
    dataset: Dataset,
    gate: PublicationGate,
    parser_version: str,
    stats: dict[str, Any],
    sector_by_facility: dict[uuid.UUID, set[str]] | None,
) -> None:
    """Resolve ownership from the source's explicit government/private sector code.

    PhilHealth's provider directory publishes a ``SEC`` value per accreditation. It
    is source-supplied sector evidence, not an inference from accreditation itself.
    A facility is only classified when every known accreditation agrees; a mixed
    facility stays ``unknown`` and internal. An explicit ownership value from a
    stronger source is never overwritten.
    """

    if (candidate.ownership or "").strip().lower() != "unknown":
        return
    if not candidate.accreditations or sector_by_facility is None:
        return
    sectors = sector_by_facility.setdefault(facility.id, set())
    for accreditation in candidate.accreditations:
        value = (accreditation.sector_code or "").strip().upper()
        if value in {"G", "P"}:
            sectors.add(value)
    if sectors == {"G"}:
        ownership, ownership_type, inclusion_class = (
            "government",
            GOVERNMENT_UNSPECIFIED,
            GOVERNMENT_FACILITY,
        )
    elif sectors == {"P"}:
        ownership, ownership_type, inclusion_class = (
            "private",
            PRIVATE_UNSPECIFIED,
            PRIVATE_PUBLIC_SERVICE_PROVIDER,
        )
    else:
        ownership, ownership_type, inclusion_class = UNKNOWN.lower(), UNKNOWN, DISCOVERY_CANDIDATE
    if (
        facility.ownership == ownership
        and facility.ownership_type == ownership_type
        and facility.inclusion_class == inclusion_class
    ):
        return
    old = {
        "ownership": facility.ownership,
        "ownership_type": facility.ownership_type,
        "inclusion_class": facility.inclusion_class,
    }
    facility.ownership = ownership
    facility.ownership_type = ownership_type
    facility.inclusion_class = inclusion_class
    publication = (
        "public"
        if _dataset_is_public(dataset, gate) and inclusion_class in PUBLIC_INCLUSION_CLASSES
        else "internal"
    )
    facility.publication_status = publication
    facility.updated_at = datetime.now(UTC)
    stats["facilities_updated"] += 1
    for attribute in ("ownership", "ownership_type", "inclusion_class"):
        session.add(
            FacilityChangeEvent(
                facility_id=facility.id,
                change_type="attribute_updated",
                attribute_name=attribute,
                old_value={"value": old[attribute]},
                new_value={"value": getattr(facility, attribute)},
                source_record_id=record.id,
                changed_by=f"ingest:{parser_version}",
            )
        )


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


def _apply_candidate(
    session: Session,
    *,
    candidate: FacilityCandidate,
    release: Release,
    record: SourceRecord,
    agency: Agency,
    dataset: Dataset,
    gate: PublicationGate,
    parser_version: str,
    stats: dict[str, Any],
    candidate_issues: list[QualityIssue],
    enqueue_matches: bool = True,
    used_slugs: set[str] | None = None,
    facility_by_entity: dict[str, uuid.UUID] | None = None,
    sector_by_facility: dict[uuid.UUID, set[str]] | None = None,
) -> Facility | None:
    entity_id = candidate.source_entity_id or candidate.source_record_key
    facility = _find_facility_for_entity(
        session, agency.id, entity_id, facility_by_entity=facility_by_entity
    )
    created = False
    inclusion_class = candidate.inclusion_class or derive_inclusion_class(candidate.ownership)
    if inclusion_class not in (*PUBLIC_INCLUSION_CLASSES, DISCOVERY_CANDIDATE):
        raise ValueError(f"Unsupported inclusion class {inclusion_class!r}")
    excluded = exclusion_reason(candidate)
    if excluded:
        stats["excluded_rows"] += 1
        session.add(
            QualityIssue(
                source_record_id=record.id,
                release_id=release.id,
                issue_code="policy_excluded",
                severity="info",
                message=f"Row excluded from the facility registry: {excluded}.",
                details={
                    "facility_type": candidate.facility_type,
                    "facility_subtype": candidate.facility_subtype,
                    "facility_kind": candidate.facility_kind,
                },
                status="closed",
            )
        )
        return None
    can_be_public = (
        _dataset_is_public(dataset, gate) and inclusion_class in PUBLIC_INCLUSION_CLASSES
    )

    if facility is None:
        if not candidate.display_name:
            session.add(
                QualityIssue(
                    facility_id=None,
                    source_record_id=record.id,
                    release_id=release.id,
                    issue_code="unresolved_source_record",
                    severity="error",
                    message=(
                        "Source row could not be linked to an existing facility by its stable "
                        "agency identifier; no record was created."
                    ),
                    details={
                        "source_entity_id": entity_id,
                        "source_record_key": candidate.source_record_key,
                    },
                    status="open",
                )
            )
            stats["unresolved"] += 1
            return None
        facility = Facility(
            slug=_new_slug(
                session, candidate.display_name, agency.short_code, used_slugs=used_slugs
            ),
            display_name=candidate.display_name,
            official_name=candidate.display_name,
            facility_type=candidate.facility_type,
            facility_subtype=candidate.facility_subtype,
            facility_kind=candidate.facility_kind or "facility",
            inclusion_class=inclusion_class,
            ownership=candidate.ownership,
            ownership_type=candidate.ownership_type,
            operator_type=candidate.operator_type,
            public_access_class=candidate.public_access_class,
            access_conditions=candidate.access_conditions,
            record_status=candidate.record_status,
            publication_status="public" if can_be_public else "internal",
            is_synthetic=dataset.is_synthetic,
            updated_at=datetime.now(UTC),
        )
        session.add(facility)
        session.flush()
        created = True
        if facility_by_entity is not None:
            facility_by_entity[entity_id] = facility.id
        stats["facilities_created"] += 1
        session.add(
            FacilityChangeEvent(
                facility_id=facility.id,
                change_type="facility_created",
                attribute_name=None,
                old_value=None,
                new_value={
                    "display_name": facility.display_name,
                    "facility_type": facility.facility_type,
                    "ownership": facility.ownership,
                },
                source_record_id=record.id,
                changed_by=f"ingest:{parser_version}",
            )
        )
    else:
        changed = {}
        # Enrichment-only releases (enrollment totals, resources) carry no ownership
        # evidence. They must never demote an identified school or hospital to an
        # internal discovery candidate merely because their own row says "unknown".
        has_classification_evidence = candidate.inclusion_class is not None or (
            candidate.ownership or ""
        ).strip().lower() not in ("", "unknown")
        updates = {
            "display_name": candidate.display_name,
            "facility_subtype": candidate.facility_subtype,
            "inclusion_class": inclusion_class if has_classification_evidence else None,
            "ownership": candidate.ownership,
            "ownership_type": candidate.ownership_type,
            "operator_type": candidate.operator_type,
            "public_access_class": candidate.public_access_class,
            "record_status": candidate.record_status,
        }
        for attribute, new_value in updates.items():
            old_value = getattr(facility, attribute)
            # Enrichment-only releases (enrollment/resource observations) carry no
            # facility name or sector. Never let a blank/unknown placeholder erase a
            # value already established by an identifying source release.
            if new_value in (None, "", "unknown", "UNKNOWN"):
                continue
            if new_value != old_value:
                setattr(facility, attribute, new_value)
                changed[attribute] = {"old": old_value, "new": new_value}
        if (
            candidate.access_conditions
            and candidate.access_conditions != facility.access_conditions
        ):
            old_conditions = facility.access_conditions
            facility.access_conditions = candidate.access_conditions
            changed["access_conditions"] = {
                "old": old_conditions,
                "new": candidate.access_conditions,
            }
        if (
            has_classification_evidence
            and inclusion_class == DISCOVERY_CANDIDATE
            and facility.publication_status != "internal"
        ):
            old_publication = facility.publication_status
            facility.publication_status = "internal"
            changed["publication_status"] = {"old": old_publication, "new": "internal"}
        elif can_be_public and facility.publication_status != "public":
            old_publication = facility.publication_status
            facility.publication_status = "public"
            changed["publication_status"] = {"old": old_publication, "new": "public"}
        if changed:
            facility.updated_at = datetime.now(UTC)
            stats["facilities_updated"] += 1
            for attribute, values in changed.items():
                session.add(
                    FacilityChangeEvent(
                        facility_id=facility.id,
                        change_type="attribute_updated",
                        attribute_name=attribute,
                        old_value={"value": values["old"]},
                        new_value={"value": values["new"]},
                        source_record_id=record.id,
                        changed_by=f"ingest:{parser_version}",
                    )
                )

    assertion_keys = {
        (attribute, normalized or "")
        for attribute, normalized in session.execute(
            select(
                AttributeAssertion.attribute_name,
                AttributeAssertion.normalized_value,
            ).where(
                AttributeAssertion.facility_id == facility.id,
                AttributeAssertion.source_record_id == record.id,
            )
        )
    }
    _assert_facility_fields(
        session,
        facility=facility,
        candidate=candidate,
        record=record,
        inclusion_class=inclusion_class,
        version=parser_version,
        existing=assertion_keys,
    )

    link = None
    if not created:
        link = session.scalars(
            select(FacilitySourceLink).where(
                FacilitySourceLink.facility_id == facility.id,
                FacilitySourceLink.source_record_id == record.id,
            )
        ).first()
    evidence = {
        "source_entity_id": entity_id,
        "source_record_key": candidate.source_record_key,
        "parser_version": parser_version,
    }
    if link is None:
        session.add(
            FacilitySourceLink(
                facility_id=facility.id,
                source_record_id=record.id,
                source_entity_id=entity_id,
                match_method="new_canonical_record" if created else "exact_agency_id",
                match_confidence=Decimal("1.000"),
                match_status="automatic_high_confidence",
                evidence=evidence,
            )
        )
    else:
        link.source_entity_id = entity_id
        link.match_method = "new_canonical_record" if created else "exact_agency_id"
        link.match_status = "automatic_high_confidence"
        link.evidence = evidence

    location = candidate.location
    if location.latitude is not None or location.longitude is not None:
        from geoalchemy2.elements import WKTElement

        geom = None
        if location.latitude is not None and location.longitude is not None:
            geom = WKTElement(f"POINT({location.longitude} {location.latitude})", srid=4326)
        existing_location = None
        if not created:
            existing_location = session.scalars(
                select(FacilityLocation).where(
                    FacilityLocation.facility_id == facility.id,
                    FacilityLocation.source_record_id == record.id,
                    FacilityLocation.is_current.is_(True),
                )
            ).first()
        if existing_location is None:
            session.add(
                FacilityLocation(
                    facility_id=facility.id,
                    source_record_id=record.id,
                    geom=geom,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    precision=location.precision,
                    method=location.method,
                    address_text=location.address_text,
                    psgc_code=location.psgc_code,
                    review_status=location.review_status,
                    is_current=True,
                )
            )
        else:
            existing_location.geom = geom
            existing_location.latitude = location.latitude
            existing_location.longitude = location.longitude
            existing_location.precision = location.precision
            existing_location.method = location.method
            existing_location.address_text = location.address_text
            existing_location.psgc_code = location.psgc_code
            existing_location.review_status = location.review_status
        if location.latitude is not None and location.longitude is not None:
            stats["with_coordinates"] += 1
        stats["precision"][location.precision] = stats["precision"].get(location.precision, 0) + 1
        if location.psgc_code:
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute="psgc_code",
                raw_value=location.psgc_code,
                normalized_value=location.psgc_code,
                version=parser_version,
                existing=assertion_keys,
            )
        for attribute, value in (
            ("location.latitude", location.latitude),
            ("location.longitude", location.longitude),
            ("location.precision", location.precision),
            ("location.method", location.method),
            ("location.address_text", location.address_text),
        ):
            if value in (None, ""):
                continue
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute=attribute,
                raw_value=value,
                normalized_value=value,
                version=parser_version,
                existing=assertion_keys,
            )

    for function in candidate.functions:
        existing_function = session.scalars(
            select(FacilityFunction).where(
                FacilityFunction.facility_id == facility.id,
                FacilityFunction.function_code == function.function_code,
                FacilityFunction.source_record_id == record.id,
            )
        ).first()
        if existing_function is None:
            session.add(
                FacilityFunction(
                    facility_id=facility.id,
                    function_code=function.function_code,
                    source_record_id=record.id,
                    source_value=function.source_value,
                    valid_from=function.valid_from,
                    valid_to=function.valid_to,
                    capacity_value=(
                        Decimal(str(function.capacity_value))
                        if function.capacity_value is not None
                        else None
                    ),
                    capacity_unit=function.capacity_unit,
                    designation_status=function.designation_status,
                    evidence=function.evidence,
                )
            )
            stats["functions"] += 1
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute="function_code",
                raw_value=function.source_value or function.function_code,
                normalized_value=function.function_code,
                version=parser_version,
                existing=assertion_keys,
            )

    for service in candidate.services:
        existing_service = session.scalars(
            select(FacilityService).where(
                FacilityService.facility_id == facility.id,
                FacilityService.service_code == service.service_code,
                FacilityService.source_record_id == record.id,
            )
        ).first()
        if existing_service is None:
            session.add(
                FacilityService(
                    facility_id=facility.id,
                    service_code=service.service_code,
                    service_name=service.service_name,
                    source_record_id=record.id,
                    source_field=service.source_field,
                    valid_from=service.valid_from,
                    valid_to=service.valid_to,
                    details=service.details,
                )
            )
            stats["services"] += 1
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute="service_code",
                raw_value=service.source_field or service.service_code,
                normalized_value=service.service_code,
                version=parser_version,
                existing=assertion_keys,
            )

    for role in candidate.roles:
        existing_role = session.scalars(
            select(FacilityRole).where(
                FacilityRole.facility_id == facility.id,
                FacilityRole.role_type == role.role_type,
                FacilityRole.entity_name == role.entity_name,
                FacilityRole.source_record_id == record.id,
            )
        ).first()
        if existing_role is None:
            session.add(
                FacilityRole(
                    facility_id=facility.id,
                    role_type=role.role_type,
                    entity_name=role.entity_name,
                    entity_type=role.entity_type,
                    source_record_id=record.id,
                    valid_from=role.valid_from,
                    valid_to=role.valid_to,
                    evidence=role.evidence,
                )
            )
            stats["roles"] += 1
            for attribute, value in (
                ("role_type", role.role_type),
                ("role_entity_name", role.entity_name),
            ):
                if not value:
                    continue
                _add_assertion(
                    session,
                    facility_id=facility.id,
                    source_record_id=record.id,
                    attribute=attribute,
                    raw_value=value,
                    normalized_value=value,
                    version=parser_version,
                    existing=assertion_keys,
                )

    if candidate.school:
        school = candidate.school
        profile = session.scalars(
            select(SchoolProfile).where(
                SchoolProfile.facility_id == facility.id,
                SchoolProfile.deped_school_id == school.deped_school_id,
            )
        ).first()
        if profile is None:
            profile = SchoolProfile(
                facility_id=facility.id,
                deped_school_id=school.deped_school_id,
                source_record_id=record.id,
            )
            session.add(profile)
        for attribute in (
            "sector",
            "school_management",
            "annex_status",
            "offers_es",
            "offers_jhs",
            "offers_shs",
        ):
            value = getattr(school, attribute)
            if value is not None:
                setattr(profile, attribute, value)
                _add_assertion(
                    session,
                    facility_id=facility.id,
                    source_record_id=record.id,
                    attribute=f"school.{attribute}",
                    raw_value=value,
                    normalized_value=value,
                    version=parser_version,
                    existing=assertion_keys,
                    source_field=attribute,
                )
        profile.source_record_id = record.id
        for observation in school.enrollment:
            exists = session.scalars(
                select(EnrollmentObservation.id).where(
                    EnrollmentObservation.facility_id == facility.id,
                    EnrollmentObservation.school_year == observation.school_year,
                    EnrollmentObservation.grade_level == observation.grade_level,
                    EnrollmentObservation.sex == observation.sex,
                    EnrollmentObservation.source_record_id == record.id,
                )
            ).first()
            if exists is None:
                session.add(
                    EnrollmentObservation(
                        facility_id=facility.id,
                        school_year=observation.school_year,
                        grade_level=observation.grade_level,
                        sex=observation.sex,
                        learner_count=observation.learner_count,
                        source_record_id=record.id,
                    )
                )
                stats["enrollment_observations"] += 1
        for observation in school.resources:
            exists = session.scalars(
                select(ResourceObservation.id).where(
                    ResourceObservation.facility_id == facility.id,
                    ResourceObservation.school_year == observation.school_year,
                    ResourceObservation.resource_code == observation.resource_code,
                    ResourceObservation.source_record_id == record.id,
                )
            ).first()
            if exists is None:
                session.add(
                    ResourceObservation(
                        facility_id=facility.id,
                        school_year=observation.school_year,
                        resource_category=observation.resource_category,
                        resource_code=observation.resource_code,
                        value_numeric=observation.value_numeric,
                        value_text=observation.value_text,
                        unit=observation.unit,
                        source_record_id=record.id,
                    )
                )
                stats["resource_observations"] += 1
        if school.deped_school_id:
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute="deped_school_id",
                raw_value=school.deped_school_id,
                normalized_value=school.deped_school_id,
                version=parser_version,
                existing=assertion_keys,
            )

    if candidate.health:
        health = candidate.health
        profile = session.scalars(
            select(HealthProfile).where(
                HealthProfile.facility_id == facility.id,
                HealthProfile.doh_facility_id == health.doh_facility_id,
            )
        ).first()
        if profile is None:
            profile = HealthProfile(
                facility_id=facility.id,
                doh_facility_id=health.doh_facility_id,
                source_record_id=record.id,
            )
            session.add(profile)
        for attribute in (
            "facility_category",
            "service_capability_level",
            "bed_capacity",
        ):
            value = getattr(health, attribute)
            if value is not None:
                setattr(profile, attribute, value)
                _add_assertion(
                    session,
                    facility_id=facility.id,
                    source_record_id=record.id,
                    attribute=f"health.{attribute}",
                    raw_value=value,
                    normalized_value=value,
                    version=parser_version,
                    existing=assertion_keys,
                    source_field=attribute,
                )
        profile.source_record_id = record.id
        if health.doh_facility_id:
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute="doh_facility_id",
                raw_value=health.doh_facility_id,
                normalized_value=health.doh_facility_id,
                version=parser_version,
                existing=assertion_keys,
            )

    for license_data in candidate.licenses:
        exists = session.scalars(
            select(HealthLicense.id).where(
                HealthLicense.facility_id == facility.id,
                HealthLicense.license_number == license_data.license_number,
                HealthLicense.source_record_id == record.id,
            )
        ).first()
        if exists is None:
            session.add(
                HealthLicense(
                    facility_id=facility.id,
                    issuing_authority=license_data.issuing_authority,
                    license_number=license_data.license_number,
                    license_type=license_data.license_type,
                    source_status=license_data.source_status,
                    valid_from=license_data.valid_from,
                    valid_until=license_data.valid_until,
                    source_record_id=record.id,
                )
            )
            stats["licenses"] += 1

    for accreditation in candidate.accreditations:
        exists = session.scalars(
            select(HealthAccreditation.id).where(
                HealthAccreditation.facility_id == facility.id,
                HealthAccreditation.source_record_id == record.id,
                HealthAccreditation.provider_category == accreditation.provider_category,
                HealthAccreditation.accreditation_category == accreditation.accreditation_category,
                HealthAccreditation.valid_until == accreditation.valid_until,
            )
        ).first()
        if exists is None:
            session.add(
                HealthAccreditation(
                    facility_id=facility.id,
                    authority=accreditation.authority,
                    provider_category=accreditation.provider_category,
                    benefit_package=accreditation.benefit_package,
                    accreditation_category=accreditation.accreditation_category,
                    bed_count=accreditation.bed_count,
                    sector_code=accreditation.sector_code,
                    source_status=accreditation.source_status,
                    valid_from=accreditation.valid_from,
                    valid_until=accreditation.valid_until,
                    source_as_of=accreditation.source_as_of,
                    telephone=accreditation.telephone,
                    email=accreditation.email,
                    street_address=accreditation.street_address,
                    municipality=accreditation.municipality,
                    source_record_id=record.id,
                    page_reference=accreditation.page_reference,
                )
            )
            stats["accreditations"] += 1

    _apply_sector_ownership(
        session,
        facility=facility,
        candidate=candidate,
        record=record,
        dataset=dataset,
        gate=gate,
        parser_version=parser_version,
        stats=stats,
        sector_by_facility=sector_by_facility,
    )

    if enqueue_matches:
        _maybe_flag_cross_source(session, candidate, facility, agency, record, release, stats)
    return facility


def _maybe_flag_cross_source(
    session: Session,
    candidate: FacilityCandidate,
    facility: Facility,
    agency: Agency,
    record: SourceRecord,
    release: Release,
    stats: dict[str, Any],
) -> None:
    # Sessions use autoflush=False. The matcher queries for the source link and current
    # location that were just added for this record, so flush before it runs.
    session.flush()
    created = enqueue_cross_source_candidates(
        session,
        source_record=record,
        source_facility=facility,
        source_agency=agency,
    )
    if not created:
        return
    stats["candidate_matches"] += len(created)
    for match in created:
        details = {
            "match_candidate_id": str(match.id),
            "candidate_key": match.candidate_key,
            "candidate_facility_id": str(match.candidate_facility_id),
            "candidate_agency": match.candidate_agency_code,
            "source_record_id": str(record.id),
            "reason": (
                "Exact normalized name and PSGC, compatible type, different agency. "
                "Not merged automatically; review is required."
            ),
        }
        session.add(
            QualityIssue(
                facility_id=facility.id,
                source_record_id=record.id,
                release_id=release.id,
                issue_code="cross_source_match_candidate",
                severity="info",
                message=(
                    "A possible cross-source match exists. It was not merged automatically; "
                    "review is required."
                ),
                details=details,
                status="open",
            )
        )


def _write_report(
    settings: IngestSettings,
    *,
    spec: ReleaseSpec,
    run_id: uuid.UUID,
    status: str,
    stats: dict[str, Any],
    issues: list[dict[str, Any]],
) -> tuple[str, str]:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{spec.dataset_slug}-{_slug(spec.release_label)}-{stamp}-{str(run_id)[:8]}"
    json_path = settings.report_dir / f"{base}.json"
    md_path = settings.report_dir / f"{base}.md"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "agency": spec.agency_code,
        "dataset": spec.dataset_slug,
        "release_label": spec.release_label,
        "source_url": spec.source_url,
        "source_published_at": _json(spec.source_published_at),
        "reference_period_start": _json(spec.reference_period_start),
        "reference_period_end": _json(spec.reference_period_end),
        "retrieved_at": _json(spec.retrieved_at or datetime.now(UTC)),
        "is_synthetic": spec.is_synthetic,
        "redistribution_status": spec.redistribution_status,
        "rights_basis": spec.rights_basis,
        "attribution_text": spec.attribution_text,
        "personal_data_status": spec.personal_data_status,
        "requested_publication_status": spec.requested_publication_status,
        "status": status,
        "stats": stats,
        "issues": issues,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = [
        f"# Ingestion report — {spec.agency_code} / {spec.dataset_slug}",
        "",
        f"- Release: `{spec.release_label}`",
        f"- Status: **{status}**",
        f"- Synthetic fixture: **{spec.is_synthetic}**",
        f"- Source URL: {spec.source_url or 'not supplied'}",
        f"- Retrieved: {payload['retrieved_at']}",
        f"- Reference period: {payload['reference_period_start']} → "
        f"{payload['reference_period_end']}",
        f"- Redistribution: `{spec.redistribution_status}`",
        "",
        "## Counts",
        "",
        "| Measure | Value |",
        "|---|---|",
    ]
    for key, value in stats.items():
        lines.append(
            f"| {key} | {json.dumps(value) if isinstance(value, (dict, list)) else value} |"
        )
    lines += ["", "## Issues", ""]
    if issues:
        lines.append("| Code | Severity | Message | Row |")
        lines.append("|---|---|---|---|")
        for issue in issues:
            lines.append(
                f"| {issue.get('code')} | {issue.get('severity')} | "
                f"{str(issue.get('message', '')).replace('|', '\\|')} | "
                f"{issue.get('row_reference') or ''} |"
            )
    else:
        lines.append("No validation issues were recorded.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)


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

    parsed_by_key = {row.source_record_key: row for row in parsed_rows}
    parsed_by_ref = {row.row_reference: row for row in parsed_rows}
    if len(parsed_by_key) != len(parsed_rows):
        raise ValueError("Parser produced duplicate source record keys; reprocess aborted.")
    if len(parsed_by_ref) != len(parsed_rows):
        raise ValueError("Parser produced duplicate row references; reprocess aborted.")

    assignments: list[tuple[SourceRecord, ParsedRow]] = []
    assigned_rows: set[str] = set()
    for record in existing_records:
        row = None
        keyed = parsed_by_key.get(record.source_record_key)
        if keyed is not None and keyed.row_reference == record.row_number_or_page:
            row = keyed
        elif record.row_number_or_page in parsed_by_ref:
            row = parsed_by_ref[record.row_number_or_page]
        if row is None:
            raise ValueError(
                "Stored source record is absent from the reprocessed release; "
                f"row reference {record.row_number_or_page!r}, key "
                f"{record.source_record_key!r}."
            )
        if row.row_reference in assigned_rows:
            raise ValueError(
                "Two stored source records map to the same parsed row; "
                f"row reference {row.row_reference!r}."
            )
        assigned_rows.add(row.row_reference)
        assignments.append((record, row))

    rekeys = [
        (record, row.source_record_key)
        for record, row in assignments
        if record.source_record_key != row.source_record_key
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


def run_ingestion(
    *,
    spec: ReleaseSpec,
    adapter: SourceAdapter,
    store: RawStore | None = None,
    session: Session | None = None,
    settings: IngestSettings | None = None,
    reprocess: bool = False,
) -> IngestResult:
    settings = settings or get_settings()
    store = store or build_store(settings)
    own_session = session is None
    engine = None
    if own_session:
        engine = build_engine(settings)
        session = session_factory(engine)()
    assert session is not None
    run_id = uuid.uuid4()
    stats: dict[str, Any] = {
        "input_rows": 0,
        "parsed_rows": 0,
        "accepted_rows": 0,
        "rejected_rows": 0,
        "duplicate_source_ids": 0,
        "facilities_created": 0,
        "facilities_updated": 0,
        "unresolved": 0,
        "excluded_rows": 0,
        "with_coordinates": 0,
        "precision": {},
        "psgc_provided": 0,
        "psgc_matched": 0,
        "enrollment_observations": 0,
        "resource_observations": 0,
        "licenses": 0,
        "accreditations": 0,
        "functions": 0,
        "services": 0,
        "roles": 0,
        "candidate_matches": 0,
        "reprocess_skipped_unchanged": 0,
    }
    all_issues: list[dict[str, Any]] = []
    agency: Agency | None = None
    dataset: Dataset | None = None
    gate: PublicationGate | None = None
    release: Release | None = None
    run: IngestionRun | None = None
    try:
        agency, dataset, gate = ensure_source(session, spec)
        preserved = store.preserve(
            agency=spec.agency_code,
            dataset=spec.dataset_slug,
            release_label=spec.release_label,
            filename=spec.filename,
            content=spec.content,
        )
        existing = _existing_release(session, dataset.id, preserved.sha256)
        run = IngestionRun(
            id=run_id,
            dataset_id=dataset.id,
            started_at=datetime.now(UTC),
            status="running",
        )
        session.add(run)
        if existing and existing.ingestion_status == "published" and not reprocess:
            run.release_id = existing.id
            run.status = "skipped_duplicate"
            run.finished_at = datetime.now(UTC)
            run.stats = {"reason": "release checksum already published", "sha256": preserved.sha256}
            session.commit()
            json_path, md_path = _write_report(
                settings,
                spec=spec,
                run_id=run_id,
                status="skipped_duplicate",
                stats=run.stats,
                issues=[],
            )
            run.report_path = json_path
            session.commit()
            return IngestResult(
                dataset=spec.dataset_slug,
                release_label=spec.release_label,
                release_id=str(existing.id),
                status="skipped_duplicate",
                report_json=json_path,
                report_markdown=md_path,
                stats=run.stats,
            )
        if existing:
            release = existing
            was_published = release.publication_status == PUBLICATION_PUBLISHED
            if reprocess:
                stats["reprocessed"] = True
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
                PUBLICATION_APPROVED if _dataset_is_public(dataset, gate) else PUBLICATION_BLOCKED
            )
            # Source records are updated in place below so facility/source links survive a
            # failed-then-retried release. Nothing is duplicated by a retry.
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

        parsed: ParsedRelease
        try:
            parsed = adapter.parse(spec)
        except Exception as exc:  # schema drift and unreadable files fail closed
            release.ingestion_status = "failed"
            release.publication_status = (
                PUBLICATION_PUBLISHED if was_published else PUBLICATION_QUARANTINED
            )
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
            json_path, md_path = _write_report(
                settings, spec=spec, run_id=run_id, status="failed", stats=stats, issues=all_issues
            )
            run.report_path = json_path
            run.stats = stats
            session.commit()
            return IngestResult(
                dataset=spec.dataset_slug,
                release_label=spec.release_label,
                release_id=str(release.id),
                status="failed",
                report_json=json_path,
                report_markdown=md_path,
                stats=stats,
                issues=all_issues,
            )

        stats["parsed_rows"] = len(parsed.rows)
        validation = adapter.validate(parsed)
        stats["accepted_rows"] = validation.accepted_rows
        stats["rejected_rows"] = validation.rejected_rows
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

        record_by_row: dict[str, uuid.UUID] = {}
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
        rejected_references = {
            issue.row_reference
            for issue in validation.issues
            if issue.severity in {"fatal", "error"} and issue.row_reference
        }
        for row in parsed.rows:
            if row.source_record_key in record_by_key:
                continue
            record = existing_records.get(row.source_record_key)
            if record is None:
                record = SourceRecord(
                    release_id=release.id,
                    source_record_key=row.source_record_key,
                    row_number_or_page=row.row_reference,
                    raw_payload=row.raw_payload,
                    raw_record_hash=_hash(row.raw_payload),
                    validation_status=row.validation_status,
                )
                session.add(record)
                session.flush()
                unchanged_by_key[row.source_record_key] = False
            else:
                payload_hash = _hash(row.raw_payload)
                unchanged_by_key[row.source_record_key] = record.raw_record_hash == payload_hash
                record.row_number_or_page = row.row_reference
                record.raw_payload = row.raw_payload
                record.raw_record_hash = payload_hash
                record.validation_status = row.validation_status
            record_by_key[row.source_record_key] = record
            record_by_row[row.row_reference] = record.id
        _record_issues(
            session,
            issues=validation.issues,
            release=release,
            record_by_row=record_by_row,
        )

        candidates = adapter.normalize(parsed)
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
        # Preload this agency's entity links once. A first bulk load otherwise
        # issues one lookup per row for an entity that cannot exist yet.
        facility_by_entity: dict[str, uuid.UUID] = {}
        entity_rows = session.execute(
            select(FacilitySourceLink.source_entity_id, FacilitySourceLink.facility_id)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .where(Dataset.agency_id == agency.id)
            .order_by(Release.retrieved_at.desc())
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
            if (
                candidate.location.latitude is not None
                and candidate.location.longitude is not None
                and not (
                    PHILIPPINES_BBOX["min_lat"]
                    <= candidate.location.latitude
                    <= PHILIPPINES_BBOX["max_lat"]
                    and PHILIPPINES_BBOX["min_lon"]
                    <= candidate.location.longitude
                    <= PHILIPPINES_BBOX["max_lon"]
                )
            ):
                all_issues.append(
                    {
                        "code": "coordinate_outside_philippines_bbox",
                        "severity": "warning",
                        "message": (
                            "Coordinate lies outside the Philippines plausibility box; "
                            "retained with warning."
                        ),
                        "row_reference": candidate.row_reference,
                        "details": {
                            "latitude": candidate.location.latitude,
                            "longitude": candidate.location.longitude,
                        },
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
                candidate_issues=[],
                enqueue_matches=spec.enqueue_cross_source_matches,
                used_slugs=used_slugs,
                facility_by_entity=facility_by_entity,
                sector_by_facility=sector_by_facility,
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
            len(parsed.rows),
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
        failed = validation.accepted_rows == 0 and len(parsed.rows) > 0
        if not failed:
            # A previous attempt may have failed during parsing; this release has
            # now been parsed successfully, so the transient issue is closed.
            _resolve_open_issues(session, release.id, "parse_error")
        release.row_count_parsed = len(parsed.rows)
        release.row_count_reported = stats.get("input_rows") or len(parsed.rows)
        release.processed_at = datetime.now(UTC)
        public_release = _dataset_is_public(dataset, gate)
        release.ingestion_status = "failed" if failed else "published"
        if failed:
            # A new failed release is quarantined. A previously published release keeps
            # its published status so a failed re-ingestion cannot hide the old data.
            release.publication_status = (
                PUBLICATION_PUBLISHED if was_published else PUBLICATION_QUARANTINED
            )
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
        run.stats = stats
        json_path, md_path = _write_report(
            settings,
            spec=spec,
            run_id=run_id,
            status=run.status,
            stats=stats,
            issues=all_issues,
        )
        run.report_path = json_path
        session.commit()
        return IngestResult(
            dataset=spec.dataset_slug,
            release_label=spec.release_label,
            release_id=str(release.id),
            status=run.status,
            report_json=json_path,
            report_markdown=md_path,
            stats=stats,
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
        if release:
            persisted_release = session.get(Release, release.id)
            if persisted_release:
                persisted_release.ingestion_status = "failed"
        session.commit()
        raise
    finally:
        if own_session and session is not None:
            session.close()
        if engine is not None:
            engine.dispose()


def run_geography_ingestion(
    *,
    spec: ReleaseSpec,
    units: list,
    warnings: list[str],
    session: Session,
    store: RawStore | None = None,
    settings: IngestSettings | None = None,
    previous_units_loader=None,
) -> IngestResult:
    """Persist one immutable geography release from any source adapter."""

    from .sources.psgc import build_crosswalk

    settings = settings or get_settings()
    store = store or build_store(settings)
    _agency, dataset, gate = ensure_source(session, spec)
    preserved = store.preserve(
        agency=spec.agency_code,
        dataset=spec.dataset_slug,
        release_label=spec.release_label,
        filename=spec.filename,
        content=spec.content,
    )
    previous = session.scalars(
        select(GeographicRelease)
        .where(GeographicRelease.is_synthetic.is_(spec.is_synthetic))
        .order_by(GeographicRelease.reference_date.desc().nullslast())
    ).first()
    existing = session.scalars(
        select(GeographicRelease).where(GeographicRelease.release_label == spec.release_label)
    ).first()
    if existing:
        return IngestResult(
            dataset=spec.dataset_slug,
            release_label=spec.release_label,
            release_id=str(existing.id),
            status="skipped_duplicate",
            stats={"units": len(units)},
        )
    geo = GeographicRelease(
        release_label=spec.release_label,
        reference_date=spec.reference_period_end,
        published_at=spec.source_published_at,
        retrieved_at=spec.retrieved_at or datetime.now(UTC),
        raw_object_uri=preserved.uri,
        sha256=preserved.sha256,
        source_url=spec.source_url,
        is_synthetic=spec.is_synthetic,
    )
    session.add(geo)
    session.flush()
    from philfacilities_api.models import AdministrativeUnit, GeographyCrosswalk

    for unit in units:
        session.add(
            AdministrativeUnit(
                release_id=geo.id,
                psgc_code=unit.psgc_code,
                name=unit.name,
                geographic_level=unit.geographic_level,
                parent_psgc_code=unit.parent_psgc_code,
                correspondence_code=unit.correspondence_code,
                old_name=unit.old_name,
                city_class=unit.city_class,
                income_classification=unit.income_classification,
                urban_rural=unit.urban_rural,
                island_region=unit.island_region,
                valid_from=spec.reference_period_start,
                valid_to=None,
            )
        )
    crosswalk_count = 0
    if previous and previous.id != geo.id:
        previous_units = None
        if previous_units_loader is not None:
            previous_units = previous_units_loader(previous, store)
        elif previous.raw_object_uri:
            from .sources.psgc import parse_psgc_workbook

            previous_units, _ = parse_psgc_workbook(
                _read_raw(previous.raw_object_uri, store), expected_filename="previous.xlsx"
            )
        if previous_units:
            for change in build_crosswalk(previous_units, units):
                session.add(
                    GeographyCrosswalk(
                        from_release_id=previous.id,
                        to_release_id=geo.id,
                        **change,
                    )
                )
                crosswalk_count += 1
    run = IngestionRun(
        dataset_id=dataset.id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status="published",
        stats={"units": len(units), "crosswalk_changes": crosswalk_count, "warnings": warnings},
    )
    session.add(run)
    session.flush()
    stats = {
        "units": len(units),
        "by_level": {
            level: sum(1 for unit in units if unit.geographic_level == level)
            for level in ("region", "province", "municipality", "barangay")
        },
        "crosswalk_changes": crosswalk_count,
        "warnings": warnings,
    }
    public_geography = _dataset_is_public(dataset, gate)
    dataset.publication_status = (
        PUBLICATION_PUBLISHED if public_geography else PUBLICATION_INTERNAL_ONLY
    )
    json_path, md_path = _write_report(
        settings, spec=spec, run_id=run.id, status="published", stats=stats, issues=[]
    )
    run.report_path = json_path
    session.commit()
    return IngestResult(
        dataset=spec.dataset_slug,
        release_label=spec.release_label,
        release_id=str(geo.id),
        status="published",
        report_json=json_path,
        report_markdown=md_path,
        stats=stats,
    )


def run_psgc_ingestion(
    *,
    spec: ReleaseSpec,
    session: Session,
    store: RawStore | None = None,
    settings: IngestSettings | None = None,
) -> IngestResult:
    from .sources.psgc import parse_psgc_workbook

    units, warnings = parse_psgc_workbook(spec.content, expected_filename=spec.filename)
    return run_geography_ingestion(
        spec=spec,
        units=units,
        warnings=warnings,
        session=session,
        store=store,
        settings=settings,
    )


def _read_raw(uri: str | None, store: RawStore) -> bytes:
    if not uri:
        raise ValueError("No raw object URI is stored for the previous release.")
    return store.read(uri)
