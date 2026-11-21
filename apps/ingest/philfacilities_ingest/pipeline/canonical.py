"""Canonical facility writes: identity, attributes, locations, and child rows."""

from __future__ import annotations

import uuid
import warnings
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityChangeEvent,
    FacilityContact,
    FacilityFunction,
    FacilityLocation,
    FacilityRole,
    FacilityService,
    FacilitySourceLink,
    HealthAccreditation,
    HealthLicense,
    HealthProfile,
    PublicationGate,
    QualityIssue,
    Release,
    ResourceObservation,
    SchoolProfile,
    SourceRecord,
    UtilityProfile,
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
from sqlalchemy import select
from sqlalchemy.exc import SADeprecationWarning
from sqlalchemy.orm import Session

from ..contracts import FacilityCandidate
from ..eligibility import exclusion_reason
from ..identity import normalize_display_name
from ..matching import enqueue_cross_source_candidates
from ..release_rollback import FacilityUpdatePrefetch, capture_facility_snapshot
from .common import _slug
from .release import _dataset_is_public
from .stats import IngestStats


def _find_facility_for_entity(
    session: Session,
    agency_id: uuid.UUID,
    entity_id: str,
    facility_by_entity: dict[str, uuid.UUID | Facility] | None = None,
) -> Facility | None:
    if facility_by_entity is not None:
        cached = facility_by_entity.get(entity_id)
        if cached is None:
            return None
        if isinstance(cached, Facility):
            # A facility created earlier in this unflushed batch has no
            # persistent identity yet, so the identity map cannot resolve it.
            # Return the pending instance directly instead of creating a
            # second facility for the same entity.
            return cached
        return session.get(Facility, cached)
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


def _new_slug(session: Session, name: str, used_slugs: set[str] | None = None) -> str:
    """Return an unused public slug.

    Slugs identify the facility, not the source that first reported it. A
    source agency suffix is deliberately absent: after consolidation a single
    facility may carry evidence from several datasets. Identically named
    facilities still receive a numeric suffix.

    Bulk sources can contain hundreds of identically named facilities (for
    example ``Barangay Health Station``). Querying the database once per suffix
    turns that into quadratic work, so callers that ingest many rows pass a
    preloaded set which is updated in memory.
    """

    base = _slug(name) or "facility"
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


BULK_ASSERTIONS_KEY = "philfacilities_bulk_assertions"
PENDING_ASSERTIONS_KEY = "philfacilities_pending_assertions"


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
    row = {
        "facility_id": facility_id,
        "attribute_name": attribute,
        "source_record_id": source_record_id,
        "source_field": source_field or attribute,
        "raw_value": None if raw_value is None else str(raw_value),
        "normalized_value": normalized,
        "transformation_version": version,
        "review_status": "source_supplied",
    }
    if session.info.get(BULK_ASSERTIONS_KEY):
        # Large releases produce well over a million assertion rows. Keeping
        # one ORM instance per row retains them in the session identity map
        # until commit, which is enough to exhaust memory on the 60k-school
        # Project Bukas release. Batch them as plain mappings instead and let
        # the runner insert them after the facility rows are flushed.
        session.info.setdefault(PENDING_ASSERTIONS_KEY, []).append(row)
        return
    session.add(AttributeAssertion(**row))


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


def _protects_public_facility(
    *,
    dataset: Dataset,
    gate: PublicationGate,
    facility: Facility,
    created: bool,
) -> bool:
    """True when an internal release must not rewrite a public facility.

    Internal releases still record assertions and child rows as evidence; those
    rows are filtered by source-record rights when read. Canonical identity,
    location, profile values, and publication state stay with the rights-cleared
    source that made the facility public.
    """

    return (
        not created
        and facility.publication_status == "public"
        and not _dataset_is_public(dataset, gate)
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
    stats: IngestStats,
    sector_by_facility: dict[uuid.UUID, set[str]] | None,
) -> None:
    """Resolve ownership from the source's explicit government/private sector code.

    PhilHealth's provider directory publishes a ``SEC`` value per accreditation. It
    is source-supplied sector evidence, not an inference from accreditation itself.
    A facility is only classified when every known accreditation agrees; a mixed
    facility stays ``unknown`` and is labelled ``DISCOVERY_CANDIDATE``. An explicit
    ownership value from a stronger source is never overwritten, and publication
    still follows the source rights gate rather than the class label.
    """

    if (candidate.ownership or "").strip().lower() != "unknown":
        return
    if not candidate.accreditations or sector_by_facility is None:
        return
    if _protects_public_facility(dataset=dataset, gate=gate, facility=facility, created=False):
        # Sector evidence from an internal-only accreditation directory must not
        # reclassify a public facility. The accreditation rows and assertions are
        # still stored and filtered on read.
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
    publication = "public" if _dataset_is_public(dataset, gate) else "internal"
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


_PLACEHOLDER_VALUES = {"", "unknown", "unset", "discovery_candidate"}


def _is_unset(value: object) -> bool:
    """True when a canonical field carries no established value yet."""

    return value is None or (
        isinstance(value, str) and value.strip().casefold() in _PLACEHOLDER_VALUES
    )


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
    stats: IngestStats,
    enqueue_matches: bool = True,
    used_slugs: set[str] | None = None,
    facility_by_entity: dict[str, uuid.UUID | Facility] | None = None,
    facility_by_doh_id: dict[str, uuid.UUID | None] | None = None,
    sector_by_facility: dict[uuid.UUID, set[str]] | None = None,
    pending_matches: list[tuple[Facility, SourceRecord]] | None = None,
    new_facilities: list[Facility] | None = None,
    current_location_by_facility: dict[uuid.UUID, FacilityLocation | None] | None = None,
    record_is_new: bool = False,
    update_prefetch: FacilityUpdatePrefetch | None = None,
) -> Facility | None:
    entity_id = candidate.source_entity_id or candidate.source_record_key
    facility = _find_facility_for_entity(
        session, agency.id, entity_id, facility_by_entity=facility_by_entity
    )
    ambiguous_doh_code = False
    matched_by_doh_facility_code = False
    if (
        facility is None
        and facility_by_doh_id is not None
        and candidate.health is not None
        and candidate.health.doh_facility_id
    ):
        # The DOH facility code is a stable cross-source identifier. The NHA
        # health-facility layer already stores it on the health profile, so a
        # second official DOH source must link to that facility rather than
        # creating a duplicate. A code already mapped to more than one facility
        # is ambiguous and must not create a third one.
        code = candidate.health.doh_facility_id
        if code in facility_by_doh_id:
            facility_id = facility_by_doh_id[code]
            ambiguous_doh_code = facility_id is None
            if facility_id is not None:
                facility = session.get(Facility, facility_id)
                if facility is None:
                    ambiguous_doh_code = True
            matched_by_doh_facility_code = facility is not None
    created = False
    if ambiguous_doh_code:
        session.add(
            QualityIssue(
                source_record_id=record.id,
                release_id=release.id,
                issue_code="ambiguous_doh_facility_code",
                severity="error",
                message=(
                    "DOH facility code resolves to more than one canonical facility; "
                    "no record was created or changed."
                ),
                details={"doh_facility_id": candidate.health.doh_facility_id},
                status="open",
            )
        )
        stats["unresolved"] += 1
        return None
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
    # Publication is a rights/safety decision, not a classification decision.
    # Records whose ownership is unknown stay public and are labelled
    # DISCOVERY_CANDIDATE, so the registry can maximize coverage without
    # asserting an owner the source never supplied.
    can_be_public = _dataset_is_public(dataset, gate)
    # Canonical fields of an already public facility are owned by the
    # rights-cleared release that published it. Internal releases may still add
    # assertions and gated child rows, but not rewrite what the public sees.
    protect_public = facility is not None and _protects_public_facility(
        dataset=dataset, gate=gate, facility=facility, created=False
    )

    if facility is None and candidate.link_only:
        # A stale or community-compiled enrichment layer can carry identifiers
        # that no longer exist in the registry. Creating a facility from such a
        # row would publish an outdated school and could duplicate a renamed or
        # split record, so the row is retained as source evidence but never
        # promoted to the canonical registry.
        session.add(
            QualityIssue(
                source_record_id=record.id,
                release_id=release.id,
                issue_code="unmatched_link_only_row",
                severity="info",
                message=(
                    "Link-only enrichment row has no facility with this agency "
                    "entity ID; no record was created."
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
        display_name = normalize_display_name(candidate.display_name)
        facility = Facility(
            # Assign the primary key client-side so a bulk load does not need a
            # flush (and a database round trip) per created facility. SQLAlchemy
            # can then batch the INSERTs during the periodic flush.
            id=uuid.uuid4(),
            slug=_new_slug(session, display_name, used_slugs=used_slugs),
            display_name=display_name,
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
        created = True
        if new_facilities is not None:
            new_facilities.append(facility)
        capture_facility_snapshot(
            session,
            release=release,
            facility=facility,
            was_created=True,
            prefetch=update_prefetch,
        )
        if facility_by_entity is not None:
            facility_by_entity[entity_id] = facility
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
        capture_facility_snapshot(
            session,
            release=release,
            facility=facility,
            was_created=False,
            prefetch=update_prefetch,
        )
        changed = {}
        if not protect_public:
            # Enrichment-only releases carry no ownership evidence. They must
            # never replace an identified school or hospital's class with a
            # discovery placeholder merely because their own row says "unknown".
            has_classification_evidence = candidate.inclusion_class is not None or (
                candidate.ownership or ""
            ).strip().lower() not in ("", "unknown")
            updates = {
                "display_name": normalize_display_name(candidate.display_name),
                "facility_subtype": candidate.facility_subtype,
                "inclusion_class": (inclusion_class if has_classification_evidence else None),
                "ownership": candidate.ownership,
                "ownership_type": candidate.ownership_type,
                "operator_type": candidate.operator_type,
                "public_access_class": candidate.public_access_class,
                "record_status": candidate.record_status,
            }
            for attribute, new_value in updates.items():
                old_value = getattr(facility, attribute)
                # Enrichment-only releases (for example resource observations)
                # carry no facility name or sector. Never let a blank/unknown
                # placeholder erase a value already established by an
                # identifying source release.
                if new_value in (None, "", "unknown", "UNKNOWN"):
                    continue
                # A later enrichment release may fill a gap, but it must not
                # rename the facility or replace an established classification.
                # DISCOVERY_CANDIDATE and unknown are placeholders, not
                # established values.
                if candidate.enrichment_only and (
                    attribute == "display_name" or not _is_unset(old_value)
                ):
                    continue
                if new_value != old_value:
                    setattr(facility, attribute, new_value)
                    changed[attribute] = {"old": old_value, "new": new_value}
            if (
                candidate.access_conditions
                and not candidate.enrichment_only
                and candidate.access_conditions != facility.access_conditions
            ):
                old_conditions = facility.access_conditions
                facility.access_conditions = candidate.access_conditions
                changed["access_conditions"] = {
                    "old": old_conditions,
                    "new": candidate.access_conditions,
                }
            if can_be_public and facility.publication_status != "public":
                old_publication = facility.publication_status
                facility.publication_status = "public"
                changed["publication_status"] = {
                    "old": old_publication,
                    "new": "public",
                }
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

    # A facility or source record created in this call cannot already have
    # assertions, so the per-row existence query is only needed when both the
    # facility and its source record predate this run.
    assertion_keys = (
        set()
        if created or record_is_new
        else {
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
    )
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
    if not created and not record_is_new:
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
    if matched_by_doh_facility_code:
        evidence["matched_doh_facility_id"] = candidate.health.doh_facility_id
    match_method = "new_canonical_record"
    if not created:
        match_method = (
            "exact_doh_facility_code" if matched_by_doh_facility_code else "exact_agency_id"
        )
    if link is None:
        session.add(
            FacilitySourceLink(
                facility_id=facility.id,
                source_record_id=record.id,
                source_entity_id=entity_id,
                match_method=match_method,
                match_confidence=Decimal("1.000"),
                match_status="automatic_high_confidence",
                evidence=evidence,
            )
        )
    else:
        link.source_entity_id = entity_id
        # Preserve how the link was originally established. Replaying the same
        # release finds the link through the stored agency ID and must not
        # rewrite a cross-agency DOH-code match as an exact agency-ID match.
        link.match_status = "automatic_high_confidence"
        link.evidence = evidence

    location = candidate.location
    has_coordinates = location.latitude is not None and location.longitude is not None
    # data.md §9.1: a postal address or PSGC code is usable location evidence
    # even without a point. Persist it as the current address-only location,
    # never invent coordinates, and never let it displace a coordinate-bearing
    # current location. ``with_coordinates`` stays a point count; the separate
    # ``address_only_locations`` counter measures the recovered evidence.
    has_location_claim = (
        location.latitude is not None
        or location.longitude is not None
        or bool(location.address_text)
        or bool(location.postal_code)
        or bool(location.psgc_code)
    )
    if has_location_claim:
        from geoalchemy2.elements import WKTElement

        geom = None
        if has_coordinates:
            geom = WKTElement(f"POINT({location.longitude} {location.latitude})", srid=4326)
        existing_location = None
        # Track the latest location object per facility for this run. Without
        # this, a second source row for the same entity in the same unflushed
        # batch cannot see the first row's pending "current" location and would
        # insert a second one.
        if current_location_by_facility is not None:
            if facility.id in current_location_by_facility:
                current_location = current_location_by_facility[facility.id]
            else:
                current_location = (
                    None
                    if created
                    else session.scalars(
                        select(FacilityLocation).where(
                            FacilityLocation.facility_id == facility.id,
                            FacilityLocation.is_current.is_(True),
                        )
                    ).first()
                )
                current_location_by_facility[facility.id] = current_location
        else:
            # A facility created in this call cannot already have a current
            # location, so skip the lookup entirely for new bulk-load rows.
            current_location = (
                None
                if created
                else session.scalars(
                    select(FacilityLocation).where(
                        FacilityLocation.facility_id == facility.id,
                        FacilityLocation.is_current.is_(True),
                    )
                ).first()
            )
        # An enrichment-only row may fill a missing location but must not
        # replace an established address with a less complete duplicate. It may
        # still promote coordinates over an address-only claim.
        fills_missing_location = current_location is not None and current_location.latitude is None
        may_replace_current = (
            not candidate.enrichment_only
            or current_location is None
            or (has_coordinates and fills_missing_location)
        )
        # A coordinate-only enrichment claim replaces an address-only current
        # location. Keep the established address on the new current row instead
        # of blanking it; the older location row remains as history and the
        # address assertion stays attached to its own source record.
        carried_address_text = None
        if (
            candidate.enrichment_only
            and may_replace_current
            and has_coordinates
            and current_location is not None
            and current_location.latitude is None
            and not location.address_text
        ):
            carried_address_text = current_location.address_text
        if current_location is not None and current_location.source_record_id == record.id:
            existing_location = current_location
        elif (
            current_location is not None
            and not protect_public
            and may_replace_current
            and (has_coordinates or current_location.latitude is None)
        ):
            # Only one current location is allowed per facility. The earlier
            # row keeps its own record link as history; the new claim becomes
            # current instead of rewriting provenance. An address-only claim
            # does not displace an existing coordinate-bearing location.
            current_location.is_current = False
            current_location.valid_to = date.today()
        if existing_location is None:
            new_location = FacilityLocation(
                facility_id=facility.id,
                source_record_id=record.id,
                geom=geom,
                latitude=location.latitude,
                longitude=location.longitude,
                precision=location.precision,
                method=location.method,
                address_text=location.address_text or carried_address_text,
                postal_code=location.postal_code,
                psgc_code=location.psgc_code,
                review_status=location.review_status,
                # An internal-only release cannot replace the coordinate shown
                # for an already public facility. Its claim is stored as
                # non-current history and hidden by the read-side gate.
                is_current=(
                    not protect_public
                    and (
                        current_location is None
                        or (
                            may_replace_current
                            and (has_coordinates or current_location.latitude is None)
                        )
                    )
                ),
            )
            session.add(new_location)
            if (
                current_location_by_facility is not None
                and not protect_public
                and new_location.is_current
            ):
                current_location_by_facility[facility.id] = new_location
        else:
            existing_location.geom = geom
            existing_location.latitude = location.latitude
            existing_location.longitude = location.longitude
            existing_location.precision = location.precision
            existing_location.method = location.method
            # Replaying a coordinate-only enrichment row must not erase an
            # address carried onto the row by an earlier apply.
            if not (candidate.enrichment_only and not location.address_text):
                existing_location.address_text = location.address_text
            existing_location.postal_code = location.postal_code
            existing_location.psgc_code = location.psgc_code
            existing_location.review_status = location.review_status
            if current_location_by_facility is not None:
                current_location_by_facility[facility.id] = existing_location
        if location.latitude is not None and location.longitude is not None:
            stats["with_coordinates"] += 1
        elif has_location_claim:
            stats["address_only_locations"] += 1
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
            ("location.postal_code", location.postal_code),
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

    for contact in candidate.contacts:
        value = (contact.value or "").strip()
        if not value:
            continue
        stored_value = value[:500]
        existing_contact = (
            None
            if created or record_is_new
            else session.scalars(
                select(FacilityContact).where(
                    FacilityContact.facility_id == facility.id,
                    FacilityContact.contact_type == contact.contact_type,
                    FacilityContact.value == stored_value,
                    FacilityContact.source_record_id == record.id,
                )
            ).first()
        )
        if existing_contact is None:
            session.add(
                FacilityContact(
                    facility_id=facility.id,
                    contact_type=contact.contact_type,
                    value=stored_value,
                    label=contact.label,
                    source_record_id=record.id,
                    source_field=contact.source_field,
                    valid_from=contact.valid_from,
                    valid_to=contact.valid_to,
                    review_status="source_supplied",
                )
            )
            stats["contacts"] += 1
        else:
            existing_contact.label = contact.label
            existing_contact.source_field = contact.source_field
            existing_contact.valid_from = contact.valid_from
            existing_contact.valid_to = contact.valid_to
        _add_assertion(
            session,
            facility_id=facility.id,
            source_record_id=record.id,
            attribute=f"contact.{contact.contact_type}",
            raw_value=value,
            normalized_value=stored_value,
            source_field=contact.source_field,
            version=parser_version,
            existing=assertion_keys,
        )

    for function in candidate.functions:
        existing_function = (
            None
            if created or record_is_new
            else session.scalars(
                select(FacilityFunction).where(
                    FacilityFunction.facility_id == facility.id,
                    FacilityFunction.function_code == function.function_code,
                    FacilityFunction.source_record_id == record.id,
                )
            ).first()
        )
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
        existing_service = (
            None
            if created or record_is_new
            else session.scalars(
                select(FacilityService).where(
                    FacilityService.facility_id == facility.id,
                    FacilityService.service_code == service.service_code,
                    FacilityService.source_record_id == record.id,
                )
            ).first()
        )
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
        existing_role = (
            None
            if created or record_is_new
            else session.scalars(
                select(FacilityRole).where(
                    FacilityRole.facility_id == facility.id,
                    FacilityRole.role_type == role.role_type,
                    FacilityRole.entity_name == role.entity_name,
                    FacilityRole.source_record_id == record.id,
                )
            ).first()
        )
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
        # School profiles are keyed by facility and DepEd ID, not by source
        # record, so a new record can still match an existing profile.
        profile = None
        if not created:
            if update_prefetch is not None:
                profile = update_prefetch.school_profile(facility.id, school.deped_school_id)
            else:
                profile = session.scalars(
                    select(SchoolProfile).where(
                        SchoolProfile.facility_id == facility.id,
                        SchoolProfile.deped_school_id == school.deped_school_id,
                    )
                ).first()
        if profile is None and not protect_public:
            profile = SchoolProfile(
                facility_id=facility.id,
                deped_school_id=school.deped_school_id,
                source_record_id=record.id,
            )
            session.add(profile)
            if update_prefetch is not None:
                update_prefetch.remember_school_profile(profile)
        for attribute in (
            "sector",
            "school_management",
            "division",
            "district",
            "legislative_district",
            "settlement_type",
            "offering_classification",
            "offers_es",
            "offers_jhs",
            "offers_shs",
        ):
            value = getattr(school, attribute)
            if value is not None:
                # An enrichment release fills a missing school attribute. The
                # profile's original source record keeps ownership of values it
                # already supplied.
                if (
                    profile is not None
                    and not protect_public
                    and (not candidate.enrichment_only or _is_unset(getattr(profile, attribute)))
                ):
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
        if profile is not None and not protect_public and not candidate.enrichment_only:
            profile.source_record_id = record.id
        for observation in school.resources:
            exists = (
                None
                if created or record_is_new
                else session.scalars(
                    select(ResourceObservation.id).where(
                        ResourceObservation.facility_id == facility.id,
                        ResourceObservation.school_year == observation.school_year,
                        ResourceObservation.resource_code == observation.resource_code,
                        ResourceObservation.source_record_id == record.id,
                    )
                ).first()
            )
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
        # Health profiles are keyed by facility and DOH ID, not by source
        # record, so a new record can still match an existing profile.
        profile = None
        if not created:
            if update_prefetch is not None:
                profile = update_prefetch.health_profile(facility.id, health.doh_facility_id)
            else:
                profile = session.scalars(
                    select(HealthProfile).where(
                        HealthProfile.facility_id == facility.id,
                        HealthProfile.doh_facility_id == health.doh_facility_id,
                    )
                ).first()
        if profile is None and not protect_public:
            profile = HealthProfile(
                facility_id=facility.id,
                doh_facility_id=health.doh_facility_id,
                source_record_id=record.id,
            )
            session.add(profile)
            if update_prefetch is not None:
                update_prefetch.remember_health_profile(profile)
        for attribute in (
            "facility_major_type",
            "facility_type_detail",
            "facility_category",
            "ownership_subclassification",
            "licensing_status",
            "bed_capacity",
        ):
            value = getattr(health, attribute)
            if value is not None:
                # An enrichment release fills a missing profile value but keeps
                # the source record that established an existing one.
                if (
                    profile is not None
                    and not protect_public
                    and (not candidate.enrichment_only or _is_unset(getattr(profile, attribute)))
                ):
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
        if profile is not None and not protect_public and not candidate.enrichment_only:
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

    if candidate.utility:
        utility = candidate.utility
        # Utility profiles are keyed by facility and DOE facility code, not by
        # source record, so a replayed release still matches the same profile.
        profile = None
        if not created:
            profile = session.scalars(
                select(UtilityProfile).where(
                    UtilityProfile.facility_id == facility.id,
                    UtilityProfile.doe_facility_code == utility.doe_facility_code,
                )
            ).first()
        if profile is None and not protect_public:
            profile = UtilityProfile(
                facility_id=facility.id,
                doe_facility_code=utility.doe_facility_code,
                source_record_id=record.id,
            )
            session.add(profile)
        for attribute in (
            "resource_type",
            "technology_type",
            "connection_type",
            "grid",
            "owner_type",
            "contract_type",
            "installed_mw",
            "dependable_mw",
            "number_of_units",
            "date_commissioned",
        ):
            value = getattr(utility, attribute)
            if value is not None:
                if profile is not None and not protect_public:
                    setattr(profile, attribute, value)
                _add_assertion(
                    session,
                    facility_id=facility.id,
                    source_record_id=record.id,
                    attribute=f"utility.{attribute}",
                    raw_value=value,
                    normalized_value=value,
                    version=parser_version,
                    existing=assertion_keys,
                    source_field=attribute,
                )
        if profile is not None and not protect_public:
            profile.source_record_id = record.id
        if utility.doe_facility_code:
            _add_assertion(
                session,
                facility_id=facility.id,
                source_record_id=record.id,
                attribute="utility.doe_facility_code",
                raw_value=utility.doe_facility_code,
                normalized_value=utility.doe_facility_code,
                version=parser_version,
                existing=assertion_keys,
            )

    for license_data in candidate.licenses:
        exists = (
            None
            if created or record_is_new
            else session.scalars(
                select(HealthLicense.id).where(
                    HealthLicense.facility_id == facility.id,
                    HealthLicense.license_number == license_data.license_number,
                    HealthLicense.source_record_id == record.id,
                )
            ).first()
        )
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
        exists = (
            None
            if created or record_is_new
            else session.scalars(
                select(HealthAccreditation.id).where(
                    HealthAccreditation.facility_id == facility.id,
                    HealthAccreditation.source_record_id == record.id,
                    HealthAccreditation.provider_category == accreditation.provider_category,
                    HealthAccreditation.accreditation_category
                    == accreditation.accreditation_category,
                    HealthAccreditation.valid_until == accreditation.valid_until,
                )
            ).first()
        )
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
        if pending_matches is not None:
            # Cross-source matching is a post-ingest concern. Collect the rows
            # now and run the matcher after the candidate loop has flushed, so
            # the hot apply path never flushes per row.
            pending_matches.append((facility, record))
        else:
            _maybe_flag_cross_source(session, facility, agency, record, release, stats)
    return facility


def _copy_mappings(
    session: Session,
    *,
    table: str,
    columns: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    """Stream insert mappings through PostgreSQL's COPY protocol.

    A large release produces well over a million assertion rows. SQLAlchemy's
    executable insert sends one statement per mapping through psycopg, which
    turns the release into millions of round trips and dominates the apply
    stage. COPY streams the same rows on the session's transaction in batches,
    which is both faster and far cheaper in memory because no ORM instances are
    created.
    """

    if not rows:
        return
    connection = session.connection().connection.driver_connection
    statement = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
    with connection.cursor() as cursor, cursor.copy(statement) as copy:
        for row in rows:
            copy.write_row(tuple(row[column] for column in columns))


def flush_attribute_assertions(session: Session) -> None:
    """Insert batched assertion mappings collected by ``_add_assertion``."""

    pending = session.info.pop(PENDING_ASSERTIONS_KEY, None)
    if not pending:
        return
    for assertion in pending:
        assertion.setdefault("id", uuid.uuid4())
    _copy_mappings(
        session,
        table="core.attribute_assertions",
        columns=(
            "id",
            "facility_id",
            "attribute_name",
            "source_record_id",
            "source_field",
            "raw_value",
            "normalized_value",
            "transformation_version",
            "review_status",
        ),
        rows=pending,
    )


def _flush_new_facilities(session: Session, facilities: list[Facility]) -> None:
    """Insert a batch of new facilities before their child rows.

    SQLAlchemy's unit of work orders mappers by mapper name rather than by the
    database foreign-key graph, so without relationships ``AttributeAssertion``
    and the other children sort before ``Facility``. Flushing the facility batch
    first keeps the child inserts batched while making the FK order explicit.

    ``Session.flush(objects=...)`` is the supported way to flush a subset of
    pending objects. It is soft-deprecated in SQLAlchemy 2.1 but remains the
    only API that avoids either a per-row flush or model-wide relationship
    changes; the warning filter is deliberately scoped to this call.
    """

    if not facilities:
        return
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"The `objects` parameter of `Session\.flush` is deprecated.*",
            category=SADeprecationWarning,
        )
        session.flush(objects=facilities)
    facilities.clear()


def _maybe_flag_cross_source(
    session: Session,
    facility: Facility,
    agency: Agency,
    record: SourceRecord,
    release: Release,
    stats: IngestStats,
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
