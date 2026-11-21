"""Deterministic cross-source identity matching and audited merge operations.

The routine path only *proposes* links and applies the narrowly deterministic exact
name + PSGC + address merge. An uncertain candidate remains unmerged and is retried
automatically; explicit accept/reject/merge commands exist for operator
investigation, not as a required approval gate. Every decision is retained with the
algorithm version and evidence.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
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
    FacilityLocation,
    FacilitySourceLink,
    HealthAccreditation,
    HealthLicense,
    HealthProfile,
    MatchCandidate,
    QualityIssue,
    Release,
    ResourceObservation,
    SchoolProfile,
    SourceRecord,
    UtilityProfile,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .identity import (
    deped_prefixed_school_id,
    normalize_name,
    school_name_key,
    subtypes_compatible,
)

MATCH_METHOD = "exact_normalized_name_psgc_type"
GEO_MATCH_METHOD = "exact_normalized_name_geo"
DEPED_PREFIXED_MATCH_METHOD = "deped_prefixed_school_id"
ALGORITHM_VERSION = "1"
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
MERGED = "merged"

# Names that are too generic to identify one real-world facility even when two
# points are metres apart. They stay out of the automatic geo queue.
GENERIC_FACILITY_NAMES = frozenset(
    {
        "barangay health station",
        "health center",
        "health centre",
        "rural health unit",
        "birthing center",
        "birthing home",
        "public market",
        "barangay hall",
        "day care center",
        "daycare center",
        "elementary school",
        "high school",
        "national high school",
        "public school",
        "police station",
        "fire station",
        "post office",
        "multi purpose hall",
        "covered court",
        "gymnasium",
        "plaza",
        "terminal",
        "port",
        "airport",
        "hospital",
        "clinic",
    }
)

# Child tables that follow a facility when a human-confirmed merge is applied.
# School, health and utility profiles all use a ``profiles`` table in their own
# schema, so audit keys must be schema-qualified to stay unambiguous.
_MERGE_MODELS = (
    AttributeAssertion,
    SchoolProfile,
    ResourceObservation,
    HealthProfile,
    UtilityProfile,
    HealthLicense,
    HealthAccreditation,
    FacilityContact,
    QualityIssue,
)


def _audit_key(model: type) -> str:
    return model.__table__.fullname


class MatchingError(Exception):
    """Raised when a review action cannot be applied safely."""


@dataclass
class _FacilityRef:
    facility: Facility
    location: FacilityLocation
    agency_codes: set[str] = field(default_factory=set)
    dataset_slugs: set[str] = field(default_factory=set)
    links: list[tuple[FacilitySourceLink, SourceRecord, Agency, Release]] = field(
        default_factory=list
    )

    def link_for_other_agency(self, other_codes: set[str]) -> tuple | None:
        for link, record, agency, release in self.links:
            if other_codes and agency.short_code in other_codes:
                continue
            return link, record, agency, release
        return None


def candidate_key(
    source_record_id: uuid.UUID,
    candidate_facility_id: uuid.UUID,
    *,
    method: str = MATCH_METHOD,
    algorithm_version: str = ALGORITHM_VERSION,
) -> str:
    raw = "|".join(
        (
            method,
            algorithm_version,
            str(source_record_id),
            str(candidate_facility_id),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decimal(value: Any) -> float | None:
    return None if value is None else float(value)


def _distance_m(
    source: FacilityLocation | None, candidate: FacilityLocation | None
) -> float | None:
    if source is None or candidate is None:
        return None
    lat1, lon1 = _decimal(source.latitude), _decimal(source.longitude)
    lat2, lon2 = _decimal(candidate.latitude), _decimal(candidate.longitude)
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def _facility_snapshot(facility: Facility) -> dict[str, Any]:
    return {
        "id": str(facility.id),
        "slug": facility.slug,
        "display_name": facility.display_name,
        "official_name": facility.official_name,
        "facility_type": facility.facility_type,
        "facility_subtype": facility.facility_subtype,
        "ownership": facility.ownership,
        "record_status": facility.record_status,
        "publication_status": facility.publication_status,
        "is_synthetic": facility.is_synthetic,
    }


def _subtypes_compatible(source: Facility, candidate: Facility) -> bool:
    return subtypes_compatible(
        source.facility_type,
        source.facility_subtype,
        candidate.facility_subtype,
    )


def _confidence(
    source_location: FacilityLocation | None,
    candidate_location: FacilityLocation | None,
) -> tuple[Decimal, float | None, bool]:
    confidence = 0.800
    distance = _distance_m(source_location, candidate_location)
    address_match = bool(
        source_location
        and candidate_location
        and source_location.address_text
        and candidate_location.address_text
        and normalize_name(source_location.address_text)
        == normalize_name(candidate_location.address_text)
    )
    if address_match:
        confidence += 0.100
    if distance is not None and distance <= 250:
        confidence += 0.050
    return Decimal(str(min(confidence, 0.950))).quantize(Decimal("0.001")), distance, address_match


def enqueue_match_candidate(
    session: Session,
    *,
    source_record: SourceRecord,
    source_facility: Facility,
    candidate_facility: Facility,
    source_agency_code: str | None,
    candidate_agency_code: str | None,
    source_location: FacilityLocation | None,
    candidate_location: FacilityLocation | None,
) -> tuple[MatchCandidate | None, bool]:
    """Create one pending candidate row, or return the existing row for this pair."""

    if source_facility.id == candidate_facility.id:
        raise MatchingError("A facility cannot be a match candidate for itself.")
    if source_facility.facility_type != candidate_facility.facility_type:
        raise MatchingError("Facilities with incompatible types cannot be matched.")
    if not _subtypes_compatible(source_facility, candidate_facility):
        return None, False

    key = candidate_key(source_record.id, candidate_facility.id)
    existing = session.scalars(
        select(MatchCandidate).where(MatchCandidate.candidate_key == key)
    ).first()
    if existing is not None:
        return existing, False

    if not session.scalar(
        select(FacilitySourceLink.id).where(
            FacilitySourceLink.facility_id == source_facility.id,
            FacilitySourceLink.source_record_id == source_record.id,
        )
    ):
        raise MatchingError("The source record is not linked to the source facility.")

    confidence, distance, address_match = _confidence(source_location, candidate_location)
    evidence = {
        "reason": (
            "Exact normalized name, same current PSGC unit, compatible facility type, "
            "and a different source agency."
        ),
        "algorithm": MATCH_METHOD,
        "algorithm_version": ALGORITHM_VERSION,
        "normalized_name": normalize_name(source_facility.display_name),
        "psgc_code": source_location.psgc_code if source_location else None,
        "facility_type": source_facility.facility_type,
        "source_agency_code": source_agency_code,
        "candidate_agency_code": candidate_agency_code,
        "address_match": address_match,
        "distance_m": round(distance, 1) if distance is not None else None,
        "source_location_precision": source_location.precision if source_location else None,
        "candidate_location_precision": (
            candidate_location.precision if candidate_location else None
        ),
        "source_facility_snapshot": _facility_snapshot(source_facility),
        "candidate_facility_snapshot": _facility_snapshot(candidate_facility),
        "subtype_compatible": _subtypes_compatible(source_facility, candidate_facility),
    }
    candidate = MatchCandidate(
        candidate_key=key,
        source_record_id=source_record.id,
        source_facility_id=source_facility.id,
        candidate_facility_id=candidate_facility.id,
        source_agency_code=source_agency_code,
        candidate_agency_code=candidate_agency_code,
        match_method=MATCH_METHOD,
        algorithm_version=ALGORITHM_VERSION,
        match_confidence=confidence,
        match_status=PENDING,
        evidence=evidence,
    )
    session.add(candidate)
    session.flush()
    return candidate, True


def _current_location(session: Session, facility_id: uuid.UUID) -> FacilityLocation | None:
    return session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility_id,
            FacilityLocation.is_current.is_(True),
        )
    ).first()


def _current_locations(
    session: Session,
    *,
    facility_type: str | None = None,
    facility_ids: set[uuid.UUID] | None = None,
) -> dict[uuid.UUID, FacilityLocation]:
    """Load current locations once instead of querying per facility."""

    query = select(FacilityLocation).where(FacilityLocation.is_current.is_(True))
    if facility_type is not None:
        query = query.join(Facility, Facility.id == FacilityLocation.facility_id).where(
            Facility.facility_type == facility_type
        )
    if facility_ids is not None:
        query = query.where(FacilityLocation.facility_id.in_(facility_ids))
    locations: dict[uuid.UUID, FacilityLocation] = {}
    for location in session.scalars(
        query.order_by(FacilityLocation.facility_id, FacilityLocation.created_at)
    ):
        locations.setdefault(location.facility_id, location)
    return locations


def enqueue_cross_source_candidates(
    session: Session,
    *,
    source_record: SourceRecord,
    source_facility: Facility,
    source_agency: Agency,
    source_location: FacilityLocation | None = None,
) -> list[MatchCandidate]:
    """Queue candidates discovered while ingesting a source record."""

    location = source_location or _current_location(session, source_facility.id)
    if location is None or not location.psgc_code or not source_facility.display_name:
        return []
    normalized = normalize_name(source_facility.display_name)
    rows = session.execute(
        select(Facility, FacilityLocation, Agency.short_code)
        .select_from(Facility)
        .join(FacilityLocation, FacilityLocation.facility_id == Facility.id)
        .join(FacilitySourceLink, FacilitySourceLink.facility_id == Facility.id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .where(
            Facility.id != source_facility.id,
            Facility.publication_status == "public",
            Facility.facility_type == source_facility.facility_type,
            FacilityLocation.is_current.is_(True),
            FacilityLocation.psgc_code == location.psgc_code,
            Agency.id != source_agency.id,
        )
    ).all()
    created: list[MatchCandidate] = []
    seen: dict[uuid.UUID, tuple[Facility, FacilityLocation, str]] = {}
    for facility, candidate_location, agency_code in rows:
        if normalize_name(facility.display_name) != normalized:
            continue
        seen.setdefault(facility.id, (facility, candidate_location, agency_code))
    for facility, candidate_location, agency_code in seen.values():
        candidate, was_created = enqueue_match_candidate(
            session,
            source_record=source_record,
            source_facility=source_facility,
            candidate_facility=facility,
            source_agency_code=source_agency.short_code,
            candidate_agency_code=agency_code,
            source_location=location,
            candidate_location=candidate_location,
        )
        if candidate is not None and was_created:
            created.append(candidate)
    return created


def generate_match_candidates(session: Session) -> dict[str, int]:
    """Scan existing source links and queue deterministic cross-agency duplicates."""

    rows = session.execute(
        select(FacilitySourceLink, SourceRecord, Agency, Release, Facility)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .join(Facility, FacilitySourceLink.facility_id == Facility.id)
        .where(Facility.publication_status == "public")
        .order_by(Release.retrieved_at.desc(), FacilitySourceLink.created_at.desc())
    ).all()
    refs: dict[uuid.UUID, _FacilityRef] = {}
    locations = _current_locations(session)
    for link, record, agency, release, facility in rows:
        ref = refs.get(facility.id)
        if ref is None:
            location = locations.get(facility.id)
            if location is None or not location.psgc_code:
                continue
            ref = _FacilityRef(facility=facility, location=location)
            refs[facility.id] = ref
        ref.agency_codes.add(agency.short_code)
        ref.links.append((link, record, agency, release))

    groups: dict[tuple[str, str, str], list[_FacilityRef]] = defaultdict(list)
    for ref in refs.values():
        key = (
            ref.location.psgc_code or "",
            ref.facility.facility_type,
            normalize_name(ref.facility.display_name),
        )
        if key[0] and key[2]:
            groups[key].append(ref)

    stats = {
        "facilities_scanned": len(refs),
        "groups_considered": 0,
        "pairs_considered": 0,
        "created": 0,
        "existing": 0,
        "skipped_same_agency": 0,
        "skipped_subtype": 0,
    }
    for refs_in_group in groups.values():
        if len(refs_in_group) < 2:
            continue
        stats["groups_considered"] += 1
        ordered = sorted(
            refs_in_group,
            key=lambda ref: (ref.facility.created_at, str(ref.facility.id)),
        )
        for index, older in enumerate(ordered):
            for newer in ordered[index + 1 :]:
                if older.agency_codes == newer.agency_codes and len(older.agency_codes) == 1:
                    stats["skipped_same_agency"] += 1
                    continue
                if not _subtypes_compatible(newer.facility, older.facility):
                    stats["skipped_subtype"] += 1
                    continue
                chosen = newer.link_for_other_agency(older.agency_codes)
                if chosen is None:
                    stats["skipped_same_agency"] += 1
                    continue
                _link, record, agency, _release = chosen
                stats["pairs_considered"] += 1
                candidate, was_created = enqueue_match_candidate(
                    session,
                    source_record=record,
                    source_facility=newer.facility,
                    candidate_facility=older.facility,
                    source_agency_code=agency.short_code,
                    candidate_agency_code=next(
                        code for code in sorted(older.agency_codes) if code != agency.short_code
                    ),
                    source_location=newer.location,
                    candidate_location=older.location,
                )
                if candidate is None:
                    stats["skipped_subtype"] += 1
                elif was_created:
                    stats["created"] += 1
                else:
                    stats["existing"] += 1
    return stats


def _is_official_dataset(dataset_slugs: set[str]) -> bool:
    return any(
        not slug.startswith("osm-") and not slug.startswith("bettergov") for slug in dataset_slugs
    )


def _name_is_specific(display_name: str) -> bool:
    normalized = normalize_name(display_name)
    return (
        len(normalized) >= 12
        and len(normalized.split()) >= 2
        and normalized not in GENERIC_FACILITY_NAMES
    )


def _geo_confidence(
    distance_m: float,
    *,
    official_side: bool,
) -> Decimal:
    if distance_m <= 10:
        value = 0.950
    elif distance_m <= 25:
        value = 0.930
    elif distance_m <= 50:
        value = 0.900
    else:
        value = 0.800
    if not official_side:
        value = min(value, 0.850)
    return Decimal(str(value)).quantize(Decimal("0.001"))


def generate_geo_match_candidates(
    session: Session,
    *,
    max_distance_m: float = 50.0,
) -> dict[str, int]:
    """Queue cross-source facilities with the same name and near-identical points.

    This complements the PSGC-based matcher for sources such as OpenStreetMap
    that carry coordinates but no PSGC code. A candidate is proposed only when
    the normalized name is specific (not a generic "health center" label), the
    facility type matches, the agencies differ, and the points are within
    ``max_distance_m``. Ambiguous names and larger distances are not queued.
    """

    rows = session.execute(
        select(FacilitySourceLink, SourceRecord, Agency, Release, Facility, Dataset)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .join(Facility, FacilitySourceLink.facility_id == Facility.id)
        .where(Facility.publication_status == "public")
    ).all()
    locations = _current_locations(session)
    refs: dict[uuid.UUID, _FacilityRef] = {}
    for link, record, agency, release, facility, dataset in rows:
        location = locations.get(facility.id)
        if location is None:
            continue
        if location.latitude is None or location.longitude is None:
            continue
        ref = refs.get(facility.id)
        if ref is None:
            ref = _FacilityRef(facility=facility, location=location)
            refs[facility.id] = ref
        ref.agency_codes.add(agency.short_code)
        ref.links.append((link, record, agency, release))
        ref.dataset_slugs.add(dataset.slug)

    groups: dict[tuple[str, str], list[_FacilityRef]] = defaultdict(list)
    stats = {
        "facilities_scanned": len(refs),
        "groups_considered": 0,
        "pairs_considered": 0,
        "created": 0,
        "existing": 0,
        "skipped_same_agency": 0,
        "skipped_distance": 0,
        "skipped_generic": 0,
        "skipped_subtype": 0,
    }
    for ref in refs.values():
        normalized = normalize_name(ref.facility.display_name)
        if normalized:
            groups[(ref.facility.facility_type, normalized)].append(ref)

    for (facility_type, normalized), group in groups.items():
        if len(group) < 2:
            continue
        if normalized in GENERIC_FACILITY_NAMES or not _name_is_specific(
            group[0].facility.display_name
        ):
            stats["skipped_generic"] += len(group)
            continue
        stats["groups_considered"] += 1
        ordered = sorted(
            group,
            key=lambda ref: (ref.facility.created_at, str(ref.facility.id)),
        )
        for index, older in enumerate(ordered):
            for newer in ordered[index + 1 :]:
                if older.agency_codes == newer.agency_codes and len(older.agency_codes) == 1:
                    stats["skipped_same_agency"] += 1
                    continue
                if not _subtypes_compatible(newer.facility, older.facility):
                    stats["skipped_subtype"] += 1
                    continue
                distance = _distance_m(newer.location, older.location)
                if distance is None or distance > max_distance_m:
                    stats["skipped_distance"] += 1
                    continue
                newer_official = _is_official_dataset(newer.dataset_slugs)
                older_official = _is_official_dataset(older.dataset_slugs)
                if newer_official and not older_official:
                    candidate, source = newer, older
                elif older_official and not newer_official:
                    candidate, source = older, newer
                else:
                    candidate, source = older, newer
                chosen = source.link_for_other_agency(candidate.agency_codes)
                if chosen is None:
                    stats["skipped_same_agency"] += 1
                    continue
                _link, record, agency, _release = chosen
                confidence = _geo_confidence(
                    distance,
                    official_side=newer_official or older_official,
                )
                stats["pairs_considered"] += 1
                key = candidate_key(
                    record.id,
                    candidate.facility.id,
                    method=GEO_MATCH_METHOD,
                )
                existing = session.scalars(
                    select(MatchCandidate).where(MatchCandidate.candidate_key == key)
                ).first()
                if existing is not None:
                    stats["existing"] += 1
                    continue
                evidence = {
                    "reason": (
                        "Exact normalized name, same facility type, different source "
                        f"agency, and points {distance:.1f} m apart."
                    ),
                    "algorithm": GEO_MATCH_METHOD,
                    "algorithm_version": ALGORITHM_VERSION,
                    "normalized_name": normalized,
                    "facility_type": facility_type,
                    "source_agency_code": agency.short_code,
                    "candidate_agency_code": next(
                        code for code in sorted(candidate.agency_codes) if code != agency.short_code
                    ),
                    "address_match": False,
                    "distance_m": round(distance, 1),
                    "psgc_code": source.location.psgc_code or candidate.location.psgc_code,
                    "source_location_precision": source.location.precision,
                    "candidate_location_precision": candidate.location.precision,
                    "source_datasets": sorted(source.dataset_slugs),
                    "candidate_datasets": sorted(candidate.dataset_slugs),
                    "source_facility_snapshot": _facility_snapshot(source.facility),
                    "candidate_facility_snapshot": _facility_snapshot(candidate.facility),
                    "subtype_compatible": True,
                    "name_specific": True,
                    "official_side": newer_official or older_official,
                }
                session.add(
                    MatchCandidate(
                        candidate_key=key,
                        source_record_id=record.id,
                        source_facility_id=source.facility.id,
                        candidate_facility_id=candidate.facility.id,
                        source_agency_code=agency.short_code,
                        candidate_agency_code=evidence["candidate_agency_code"],
                        match_method=GEO_MATCH_METHOD,
                        algorithm_version=ALGORITHM_VERSION,
                        match_confidence=confidence,
                        match_status=PENDING,
                        evidence=evidence,
                    )
                )
                session.flush()
                stats["created"] += 1
    return stats


def _get_candidate(session: Session, candidate_id: uuid.UUID, *, lock: bool = False):
    query = select(MatchCandidate).where(MatchCandidate.id == candidate_id)
    if lock:
        query = query.with_for_update()
    candidate = session.scalars(query).first()
    if candidate is None:
        raise MatchingError(f"No match candidate exists with id {candidate_id}.")
    return candidate


def accept_match_candidate(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    reviewer: str,
    note: str | None = None,
) -> MatchCandidate:
    if not reviewer.strip():
        raise MatchingError("A reviewer is required.")
    candidate = _get_candidate(session, candidate_id, lock=True)
    if candidate.match_status != PENDING:
        raise MatchingError(
            f"Candidate is {candidate.match_status}; only pending candidates can be accepted."
        )
    candidate.match_status = ACCEPTED
    candidate.reviewer = reviewer.strip()
    candidate.reviewed_at = datetime.now(UTC)
    candidate.review_note = note
    session.flush()
    return candidate


def reject_match_candidate(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    reviewer: str,
    note: str | None = None,
) -> MatchCandidate:
    if not reviewer.strip():
        raise MatchingError("A reviewer is required.")
    candidate = _get_candidate(session, candidate_id, lock=True)
    if candidate.match_status != PENDING:
        raise MatchingError(
            f"Candidate is {candidate.match_status}; only pending candidates can be rejected."
        )
    candidate.match_status = REJECTED
    candidate.reviewer = reviewer.strip()
    candidate.reviewed_at = datetime.now(UTC)
    candidate.review_note = note
    session.flush()
    return candidate


def merge_match_candidate(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    reviewer: str,
    note: str | None = None,
    invalidate_fusions: bool = True,
    allow_facility_type_mismatch: bool = False,
) -> MatchCandidate:
    """Retire the source facility into the accepted candidate facility.

    The source facility row is retained as an internal tombstone so its history and the
    candidate audit remain queryable. Source evidence, locations, observations, profiles,
    licences, accreditations, assertions, and issues move to the surviving facility.

    Set ``invalidate_fusions=False`` for bulk passes that rebuild derived fusion rows
    once at the end. Per-merge invalidation is then redundant and its index lookups
    dominate the merge cost.

    ``allow_facility_type_mismatch`` is an explicit operator override for a reviewed
    cross-type candidate. The surviving facility keeps its own type; the retired
    facility remains an internal tombstone with its source evidence.
    """

    if not reviewer.strip():
        raise MatchingError("A reviewer is required.")
    candidate = _get_candidate(session, candidate_id, lock=True)
    if candidate.match_status != ACCEPTED:
        raise MatchingError(
            "Only an accepted candidate can be merged. Accept the candidate after review first."
        )
    if candidate.source_facility_id is None or candidate.candidate_facility_id is None:
        raise MatchingError("The candidate's facilities no longer exist.")
    source = session.get(Facility, candidate.source_facility_id)
    target = session.get(Facility, candidate.candidate_facility_id)
    if source is None or target is None:
        raise MatchingError("The candidate's facilities no longer exist.")
    if source.id == target.id:
        raise MatchingError("Source and candidate facilities are the same record.")
    if source.facility_type != target.facility_type and not allow_facility_type_mismatch:
        raise MatchingError("Facilities with incompatible types cannot be merged.")

    now = datetime.now(UTC)
    today = date.today()
    source_before = _facility_snapshot(source)
    target_before = _facility_snapshot(target)
    moved_ids: dict[str, list[str]] = {}
    location_state_before: dict[str, dict[str, Any]] = {}

    links = list(
        session.scalars(
            select(FacilitySourceLink).where(FacilitySourceLink.facility_id == source.id)
        ).all()
    )
    moved_ids["facility_source_links"] = []
    for link in links:
        duplicate = session.scalars(
            select(FacilitySourceLink).where(
                FacilitySourceLink.facility_id == target.id,
                FacilitySourceLink.source_record_id == link.source_record_id,
            )
        ).first()
        if duplicate is not None:
            raise MatchingError(
                "The target facility is already linked to one of the source facility's records."
            )
        link.facility_id = target.id
        moved_ids["facility_source_links"].append(str(link.id))

    locations = list(
        session.scalars(
            select(FacilityLocation).where(FacilityLocation.facility_id == source.id)
        ).all()
    )
    target_has_current = session.scalar(
        select(FacilityLocation.id).where(
            FacilityLocation.facility_id == target.id,
            FacilityLocation.is_current.is_(True),
        )
    )
    moved_ids["facility_locations"] = []
    for location in locations:
        location_state_before[str(location.id)] = {
            "is_current": location.is_current,
            "valid_to": location.valid_to.isoformat() if location.valid_to else None,
        }
        location.facility_id = target.id
        if target_has_current and location.is_current:
            location.is_current = False
            location.valid_to = today
        moved_ids["facility_locations"].append(str(location.id))

    counts: dict[str, int] = {
        "facility_source_links": len(links),
        "facility_locations": len(locations),
    }
    retained_on_source: dict[str, int] = {}

    # Profile tables are unique per (facility, official code). If the target
    # already holds the same code, keep the duplicate profile on the tombstone
    # instead of tripping the constraint; it remains queryable source evidence.
    retained_ids: set[uuid.UUID] = set()
    for model, field_name in (
        (SchoolProfile, "deped_school_id"),
        (UtilityProfile, "doe_facility_code"),
    ):
        field = getattr(model, field_name)
        for row in session.scalars(select(model).where(model.facility_id == source.id)).all():
            code = getattr(row, field_name)
            if code is None:
                continue
            duplicate = session.scalar(
                select(model.id).where(model.facility_id == target.id, field == code)
            )
            if duplicate is not None:
                retained_ids.add(row.id)

    for model in _MERGE_MODELS:
        if model is FacilityContact:
            contacts = list(
                session.scalars(
                    select(FacilityContact).where(FacilityContact.facility_id == source.id)
                ).all()
            )
            moved = []
            for contact in contacts:
                duplicate = session.scalar(
                    select(FacilityContact.id).where(
                        FacilityContact.facility_id == target.id,
                        FacilityContact.contact_type == contact.contact_type,
                        FacilityContact.value == contact.value,
                        # NULL source records are distinct in the unique
                        # constraint, but two identical unattributed contacts
                        # would still be duplicate display rows. Skip them too.
                        (
                            FacilityContact.source_record_id.is_(None)
                            if contact.source_record_id is None
                            else FacilityContact.source_record_id == contact.source_record_id
                        ),
                    )
                )
                if duplicate is not None:
                    # Keep the duplicate on the source tombstone. Moving it
                    # would violate uq_facility_contact_source.
                    continue
                contact.facility_id = target.id
                moved.append(contact)
            table = model.__table__.fullname
            counts[table] = len(moved)
            moved_ids[table] = [str(contact.id) for contact in moved]
            if len(moved) != len(contacts):
                retained_on_source[table] = len(contacts) - len(moved)
            continue
        rows = list(session.scalars(select(model).where(model.facility_id == source.id)).all())
        kept = [row for row in rows if row.id in retained_ids]
        rows = [row for row in rows if row.id not in retained_ids]
        for row in rows:
            row.facility_id = target.id
        table = model.__table__.fullname
        counts[table] = len(rows)
        moved_ids[table] = [str(row.id) for row in rows]
        if kept:
            retained_on_source[table] = len(kept)

    source.publication_status = "internal"
    source.record_status = "merged"
    source.updated_at = now
    target.updated_at = now

    from .fusion import delete_fusions_for_facilities

    if invalidate_fusions:
        delete_fusions_for_facilities(session, (source.id, target.id))

    session.add(
        FacilityChangeEvent(
            facility_id=source.id,
            change_type="facility_merged_into",
            attribute_name=None,
            old_value=source_before,
            new_value={"target_facility_id": str(target.id), "target_slug": target.slug},
            source_record_id=candidate.source_record_id,
            changed_by=f"review:{reviewer.strip()}",
        )
    )
    session.add(
        FacilityChangeEvent(
            facility_id=target.id,
            change_type="facility_merged_from",
            attribute_name=None,
            old_value=target_before,
            new_value={
                "target_facility_id": str(target.id),
                "target_slug": target.slug,
                "merged_source_facility": source_before,
            },
            source_record_id=candidate.source_record_id,
            changed_by=f"review:{reviewer.strip()}",
        )
    )

    candidate.match_status = MERGED
    candidate.reviewer = reviewer.strip()
    candidate.reviewed_at = now
    candidate.review_note = note
    candidate.resolution = {
        "merged_at": now.isoformat(),
        "source_facility_snapshot": source_before,
        "target_facility_snapshot": target_before,
        "source_facility_after": _facility_snapshot(source),
        "target_facility_after": _facility_snapshot(target),
        "moved_counts": counts,
        "moved_ids": moved_ids,
        "retained_on_source": retained_on_source,
        "location_state_before": location_state_before,
        "merged_by": reviewer.strip(),
        "active": True,
    }
    session.flush()
    return candidate


_SCHOOL_PROFILE_FIELDS = (
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
)


def _school_profile_snapshot(profile: SchoolProfile) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "facility_id": str(profile.facility_id),
        "deped_school_id": profile.deped_school_id,
        **{field: getattr(profile, field) for field in _SCHOOL_PROFILE_FIELDS},
        "source_record_id": str(profile.source_record_id) if profile.source_record_id else None,
    }


def consolidate_school_profiles(
    session: Session,
    facility_id: uuid.UUID,
    *,
    canonical_school_id: str | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Fill the canonical school profile from duplicate profiles after a merge.

    A merged facility can carry both the six-digit BEIS profile and a prefixed
    seven-digit profile. The six-digit profile remains the primary one; missing
    values are copied from the duplicate without replacing established values
    or changing the primary profile's source record. The returned audit maps
    the canonical profile id to the fields that changed and their previous
    values so an undo can reverse the backfill.
    """

    profiles = list(
        session.scalars(
            select(SchoolProfile)
            .where(SchoolProfile.facility_id == facility_id)
            .order_by(SchoolProfile.valid_from.desc().nullslast(), SchoolProfile.id)
        ).all()
    )
    if len(profiles) < 2:
        return {}
    canonical = next(
        (profile for profile in profiles if profile.deped_school_id == canonical_school_id),
        None,
    )
    if canonical is None:
        canonical = min(
            profiles,
            key=lambda profile: (len(profile.deped_school_id or ""), str(profile.id)),
        )
    changes: dict[str, dict[str, dict[str, Any]]] = {}
    for profile in profiles:
        if profile.id == canonical.id:
            continue
        for attribute_name in _SCHOOL_PROFILE_FIELDS:
            old_value = getattr(canonical, attribute_name)
            new_value = getattr(profile, attribute_name)
            if old_value is None and new_value is not None:
                changes.setdefault(str(canonical.id), {})[attribute_name] = {
                    "old": old_value,
                    "new": new_value,
                }
                setattr(canonical, attribute_name, new_value)
    return changes


def merge_deped_prefixed_duplicates(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 100,
    prefixed_school_ids: set[str] | None = None,
    affected_facility_ids: set[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Merge EBEIS prefixed-ID twin records into the six-digit canonical school.

    The EBEIS result set can emit one school twice: once with the official
    six-digit BEIS ID and once with a one-digit level/school-type prefix (``1``,
    ``2`` or ``3``) in front of that same ID. The prefix is not a separate
    school. Each verified pair gets an explicit accepted match candidate and the
    standard audited merge, so both source records remain linked to the survivor
    and the prefixed twin is retained as a ``merged`` tombstone.
    """

    profiles = list(
        session.scalars(
            select(SchoolProfile).where(
                SchoolProfile.deped_school_id.is_not(None),
                func.length(SchoolProfile.deped_school_id).in_((6, 7)),
            )
        ).all()
    )
    by_id: dict[str, list[SchoolProfile]] = defaultdict(list)
    for profile in profiles:
        if profile.deped_school_id:
            by_id[profile.deped_school_id].append(profile)

    pairs: list[tuple[SchoolProfile, SchoolProfile]] = []
    skipped_ambiguous_base = 0
    for profile in profiles:
        school_id = profile.deped_school_id or ""
        base_id = deped_prefixed_school_id(school_id)
        if not base_id:
            continue
        if prefixed_school_ids is not None and school_id not in prefixed_school_ids:
            continue
        base_profiles = by_id.get(base_id, [])
        if len(base_profiles) != 1:
            skipped_ambiguous_base += 1
            continue
        base_profile = base_profiles[0]
        if base_profile.facility_id == profile.facility_id:
            continue
        pairs.append((profile, base_profile))
    pairs.sort(key=lambda pair: (pair[0].deped_school_id or "", str(pair[0].facility_id)))

    stats: dict[str, Any] = {
        "prefixed_profiles": sum(
            1 for profile in profiles if deped_prefixed_school_id(profile.deped_school_id)
        ),
        "pairs_considered": 0,
        "would_merge": 0,
        "merged": 0,
        "skipped_ambiguous_base": skipped_ambiguous_base,
        "skipped_missing_facility": 0,
        "skipped_not_public": 0,
        "skipped_name_mismatch": 0,
        "skipped_no_source_record": 0,
        "skipped_existing_candidate": 0,
        "skipped_error": 0,
        "errors": [],
        "examples": [],
        "dry_run": dry_run,
        "algorithm_version": ALGORITHM_VERSION,
    }

    facility_ids = {profile.facility_id for pair in pairs for profile in pair}
    facilities = (
        {
            facility.id: facility
            for facility in session.scalars(select(Facility).where(Facility.id.in_(facility_ids)))
        }
        if facility_ids
        else {}
    )

    verified: list[tuple[SchoolProfile, SchoolProfile, Facility, Facility]] = []
    for source_profile, target_profile in pairs:
        source = facilities.get(source_profile.facility_id)
        target = facilities.get(target_profile.facility_id)
        if source is None or target is None:
            stats["skipped_missing_facility"] += 1
            continue
        if (
            source.facility_type != "school"
            or target.facility_type != "school"
            or source.publication_status != "public"
            or target.publication_status != "public"
            or source.record_status == "merged"
        ):
            stats["skipped_not_public"] += 1
            continue
        source_name = school_name_key(source.display_name)
        target_name = school_name_key(target.display_name)
        if not source_name or source_name != target_name:
            stats["skipped_name_mismatch"] += 1
            continue
        verified.append((source_profile, target_profile, source, target))

    source_facility_ids = {source.id for _sp, _tp, source, _target in verified}
    link_rows = (
        session.execute(
            select(FacilitySourceLink, SourceRecord, Release.retrieved_at)
            .join(SourceRecord, SourceRecord.id == FacilitySourceLink.source_record_id)
            .join(Release, Release.id == SourceRecord.release_id)
            .join(Dataset, Dataset.id == Release.dataset_id)
            .where(
                FacilitySourceLink.facility_id.in_(source_facility_ids),
                Dataset.slug.like("deped-ebeis-masterlist-%"),
            )
            .order_by(FacilitySourceLink.facility_id, Release.retrieved_at.desc())
        ).all()
        if source_facility_ids
        else []
    )
    source_record_by_facility: dict[uuid.UUID, SourceRecord] = {}
    for link, record, _retrieved_at in link_rows:
        source_record_by_facility.setdefault(link.facility_id, record)

    reviewer = "system:deped-prefixed-id"
    note = (
        "EBEIS seven-digit prefixed school ID resolves to the official six-digit "
        "BEIS ID with the same normalized school name."
    )
    for source_profile, target_profile, source, target in verified:
        record = source_record_by_facility.get(source.id)
        if record is None:
            stats["skipped_no_source_record"] += 1
            continue
        stats["pairs_considered"] += 1
        key = candidate_key(
            record.id,
            target.id,
            method=DEPED_PREFIXED_MATCH_METHOD,
        )
        existing = session.scalars(
            select(MatchCandidate).where(MatchCandidate.candidate_key == key)
        ).first()
        if existing is not None:
            stats["skipped_existing_candidate"] += 1
            continue
        if dry_run:
            stats["would_merge"] += 1
            if len(stats["examples"]) < 20:
                stats["examples"].append(
                    {
                        "prefixed_school_id": source_profile.deped_school_id,
                        "canonical_school_id": target_profile.deped_school_id,
                        "source_facility_id": str(source.id),
                        "target_facility_id": str(target.id),
                        "source_name": source.display_name,
                        "target_name": target.display_name,
                    }
                )
            continue
        if stats["merged"] >= limit:
            break
        evidence = {
            "reason": note,
            "algorithm": DEPED_PREFIXED_MATCH_METHOD,
            "algorithm_version": ALGORITHM_VERSION,
            "prefixed_school_id": source_profile.deped_school_id,
            "canonical_school_id": target_profile.deped_school_id,
            "normalized_name": school_name_key(source.display_name),
            "source_agency_code": "deped",
            "candidate_agency_code": "deped",
            "name_match": True,
            "source_profile_snapshot": _school_profile_snapshot(source_profile),
            "candidate_profile_snapshot": _school_profile_snapshot(target_profile),
            "source_facility_snapshot": _facility_snapshot(source),
            "candidate_facility_snapshot": _facility_snapshot(target),
        }
        now = datetime.now(UTC)
        candidate = MatchCandidate(
            candidate_key=key,
            source_record_id=record.id,
            source_facility_id=source.id,
            candidate_facility_id=target.id,
            source_agency_code="deped",
            candidate_agency_code="deped",
            match_method=DEPED_PREFIXED_MATCH_METHOD,
            algorithm_version=ALGORITHM_VERSION,
            match_confidence=Decimal("0.999"),
            match_status=ACCEPTED,
            reviewer=reviewer,
            reviewed_at=now,
            review_note=note,
            evidence=evidence,
        )
        session.add(candidate)
        session.flush()
        try:
            merge_match_candidate(session, candidate.id, reviewer=reviewer, note=note)
            backfill = consolidate_school_profiles(
                session,
                target.id,
                canonical_school_id=target_profile.deped_school_id,
            )
            if backfill:
                resolution = dict(candidate.resolution or {})
                resolution["profile_backfill"] = backfill
                candidate.resolution = resolution
            stats["merged"] += 1
            if affected_facility_ids is not None:
                affected_facility_ids.add(target.id)
            if len(stats["examples"]) < 20:
                stats["examples"].append(
                    {
                        "candidate_id": str(candidate.id),
                        "prefixed_school_id": source_profile.deped_school_id,
                        "canonical_school_id": target_profile.deped_school_id,
                        "source_facility_id": str(source.id),
                        "target_facility_id": str(target.id),
                    }
                )
        except MatchingError as exc:
            stats["skipped_error"] += 1
            if len(stats["errors"]) < 20:
                stats["errors"].append(f"{candidate.id}: {exc}")
    return stats


def undo_match_merge(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    reviewer: str,
    note: str | None = None,
) -> MatchCandidate:
    """Undo one applied merge and restore the source facility and its evidence.

    Undo is deliberately strict: every child row recorded during the merge must still
    exist and still belong to the surviving facility. If anything has moved since the
    merge, the operator must resolve that state before retrying rather than guess.
    """

    if not reviewer.strip():
        raise MatchingError("A reviewer is required.")
    candidate = _get_candidate(session, candidate_id, lock=True)
    if candidate.match_status != MERGED:
        raise MatchingError(
            f"Candidate is {candidate.match_status}; only a merged candidate can be undone."
        )
    resolution = candidate.resolution or {}
    if not resolution.get("active"):
        raise MatchingError("This merge has already been undone.")
    moved_ids = resolution.get("moved_ids") or {}
    if not isinstance(moved_ids, dict):
        raise MatchingError("The merge resolution has no restorable child-row audit.")
    if candidate.source_facility_id is None or candidate.candidate_facility_id is None:
        raise MatchingError("The candidate's facilities no longer exist.")
    source = session.get(Facility, candidate.source_facility_id)
    target = session.get(Facility, candidate.candidate_facility_id)
    if source is None or target is None:
        raise MatchingError("The candidate's facilities no longer exist.")
    if source.id == target.id:
        raise MatchingError("Source and candidate facilities are the same record.")
    if source.record_status != "merged":
        raise MatchingError(
            "The source facility is no longer in the merged state; refusing to restore."
        )

    _verify_moved_rows(session, target.id, moved_ids)

    # A prefixed-ID merge may have backfilled missing values onto the canonical
    # profile from the duplicate. Reverse only the fields the merge itself
    # changed, and refuse if a later edit has already replaced that value.
    profile_backfill = resolution.get("profile_backfill") or {}
    restored_backfill: dict[str, list[str]] = {}
    for raw_profile_id, fields in profile_backfill.items():
        profile = session.get(SchoolProfile, uuid.UUID(raw_profile_id))
        if profile is None:
            raise MatchingError("A school profile changed after the merge; refusing to restore.")
        for attribute_name, values in fields.items():
            current_value = getattr(profile, attribute_name)
            if current_value != values.get("new"):
                raise MatchingError(
                    "A school profile changed after the merge; refusing to restore."
                )
            setattr(profile, attribute_name, values.get("old"))
            restored_backfill.setdefault(raw_profile_id, []).append(attribute_name)

    now = datetime.now(UTC)
    source_before = _facility_snapshot(source)
    target_before = _facility_snapshot(target)
    restored: dict[str, int] = {}

    for raw_id in moved_ids.get("facility_source_links", []):
        link = session.get(FacilitySourceLink, uuid.UUID(raw_id))
        link.facility_id = source.id
    restored["facility_source_links"] = len(moved_ids.get("facility_source_links", []))

    location_state = resolution.get("location_state_before") or {}
    promotion = resolution.get("location_promotion") or {}
    promoted: FacilityLocation | None = None
    previous: FacilityLocation | None = None
    if promotion:
        promoted = session.get(FacilityLocation, uuid.UUID(promotion["promoted_location_id"]))
        previous = (
            session.get(FacilityLocation, uuid.UUID(promotion["current_location_id"]))
            if promotion.get("current_location_id")
            else None
        )
        if promoted is None or promoted.facility_id != target.id or not promoted.is_current:
            raise MatchingError(
                "The promoted location changed after the merge; refusing to restore."
            )
        if previous is None or previous.facility_id != target.id:
            raise MatchingError(
                "The previous current location moved after the merge; refusing to restore."
            )

    moved_locations: list[tuple[str, FacilityLocation]] = []
    for raw_id in moved_ids.get("facility_locations", []):
        location = session.get(FacilityLocation, uuid.UUID(raw_id))
        if location is None:
            raise MatchingError("A merged location no longer exists; refusing to restore.")
        location.facility_id = source.id
        moved_locations.append((raw_id, location))
    restored["facility_locations"] = len(moved_locations)

    resolved_children, unresolved_children = _resolve_moved_children(session, moved_ids)
    if unresolved_children:
        raise MatchingError(
            "The merge resolution references child rows that no longer exist; refusing to restore."
        )
    for model in _MERGE_MODELS:
        table = _audit_key(model)
        ids = resolved_children.get(model, [])
        for row_id in ids:
            row = session.get(model, row_id)
            if row is None:  # verified above, but stay defensive
                raise MatchingError(
                    "The merge resolution references child rows that no longer exist; "
                    "refusing to restore."
                )
            row.facility_id = source.id
        restored[table] = len(ids)

    # Restore current-location flags in two passes. A moved source location and
    # the survivor's previous current location can both end up current on
    # different facilities, but updating them one at a time can transiently put
    # two current rows on the survivor and trip the partial unique index. Close
    # every involved row first, then apply the recorded states together.
    final_states: dict[uuid.UUID, tuple[bool, date | None]] = {}
    for raw_id, location in moved_locations:
        state = location_state.get(raw_id) or {}
        valid_to = state.get("valid_to")
        final_states[location.id] = (
            bool(state.get("is_current", location.is_current)),
            date.fromisoformat(valid_to) if valid_to else None,
        )
    if promotion and promoted is not None and previous is not None:
        # A promoted row that came from the source already has its pre-merge
        # state above; only a target-owned promoted row needs the recorded
        # pre-promotion state.
        if promoted.id not in final_states:
            valid_to = promotion.get("promoted_valid_to")
            final_states[promoted.id] = (
                bool(promotion.get("promoted_is_current")),
                date.fromisoformat(valid_to) if valid_to else None,
            )
        valid_to = promotion.get("current_valid_to")
        final_states[previous.id] = (
            bool(promotion.get("current_is_current")),
            date.fromisoformat(valid_to) if valid_to else None,
        )
        restored["location_promotion"] = 1
    if final_states:
        involved = list(
            session.scalars(
                select(FacilityLocation)
                .where(FacilityLocation.id.in_(final_states))
                .order_by(FacilityLocation.id)
            ).all()
        )
        for location in involved:
            location.is_current = False
        session.flush()
        for location in involved:
            is_current, valid_to = final_states[location.id]
            location.is_current = is_current
            location.valid_to = valid_to
        # Refuse to create a second current location for any facility.
        current_counts: dict[uuid.UUID, int] = defaultdict(int)
        for location in involved:
            if location.is_current:
                current_counts[location.facility_id] += 1
        duplicate = next(
            (facility_id for facility_id, count in current_counts.items() if count > 1),
            None,
        )
        if duplicate is not None:
            raise MatchingError(
                "Undo would leave more than one current location for a facility; "
                "resolve the location history before retrying."
            )
        session.flush()

    source_snapshot = resolution.get("source_facility_snapshot") or {}
    source.publication_status = source_snapshot.get("publication_status", "internal")
    source.record_status = source_snapshot.get("record_status", "active")
    source.updated_at = now
    target.updated_at = now

    from .fusion import delete_fusions_for_facilities

    delete_fusions_for_facilities(session, (source.id, target.id))

    session.add(
        FacilityChangeEvent(
            facility_id=source.id,
            change_type="facility_merge_undone",
            attribute_name=None,
            old_value=source_before,
            new_value={"restored_facility_id": str(source.id), "restored_slug": source.slug},
            source_record_id=candidate.source_record_id,
            changed_by=f"review:{reviewer.strip()}",
        )
    )
    session.add(
        FacilityChangeEvent(
            facility_id=target.id,
            change_type="facility_merge_undone",
            attribute_name=None,
            old_value=target_before,
            new_value={
                "restored_source_facility_id": str(source.id),
                "restored_source_slug": source.slug,
            },
            source_record_id=candidate.source_record_id,
            changed_by=f"review:{reviewer.strip()}",
        )
    )

    resolution["active"] = False
    resolution["undone_at"] = now.isoformat()
    resolution["undone_by"] = reviewer.strip()
    resolution["undo_note"] = note
    resolution["restored_counts"] = restored
    if restored_backfill:
        resolution["restored_profile_backfill"] = restored_backfill
    history = list(resolution.get("undo_history") or [])
    history.append(
        {
            "undone_at": now.isoformat(),
            "undone_by": reviewer.strip(),
            "undo_note": note,
            "previous_reviewer": candidate.reviewer,
            "previous_reviewed_at": (
                candidate.reviewed_at.isoformat() if candidate.reviewed_at else None
            ),
            "previous_review_note": candidate.review_note,
        }
    )
    resolution["undo_history"] = history
    candidate.resolution = resolution
    candidate.match_status = ACCEPTED
    candidate.reviewer = reviewer.strip()
    candidate.reviewed_at = now
    candidate.review_note = note
    session.flush()
    return candidate


def _resolve_moved_children(
    session: Session,
    moved_ids: dict[str, list[str]],
) -> tuple[dict[type, list[uuid.UUID]], list[str]]:
    """Resolve audit keys to model classes, accepting legacy bare table names.

    Earlier merges keyed the audit by ``__tablename__`` only. School, health and
    utility profiles share the ``profiles`` table name in different schemas, so
    a legacy key is resolved per row when more than one model matches it.
    """

    by_table: dict[str, list[type]] = defaultdict(list)
    for model in _MERGE_MODELS:
        by_table[model.__tablename__].append(model)
    resolved: dict[type, list[uuid.UUID]] = defaultdict(list)
    unresolved: list[str] = []
    for key, raw_ids in moved_ids.items():
        if key in {"facility_source_links", "facility_locations"}:
            continue
        models = [model for model in _MERGE_MODELS if _audit_key(model) == key]
        if not models:
            models = by_table.get(key, [])
        if not models:
            unresolved.extend(f"{key}:{raw_id}" for raw_id in raw_ids)
            continue
        remaining = [uuid.UUID(raw_id) for raw_id in raw_ids]
        if len(models) == 1:
            resolved[models[0]].extend(remaining)
            continue
        for model in models:
            if not remaining:
                break
            found = set(session.scalars(select(model.id).where(model.id.in_(remaining))).all())
            if found:
                resolved[model].extend(found)
                remaining = [row_id for row_id in remaining if row_id not in found]
        unresolved.extend(f"{key}:{row_id}" for row_id in remaining)
    return dict(resolved), unresolved


def _verify_moved_rows(
    session: Session,
    target_id: uuid.UUID,
    moved_ids: dict[str, list[str]],
) -> None:
    checks: list[tuple[str, Any]] = [
        ("facility_source_links", FacilitySourceLink),
        ("facility_locations", FacilityLocation),
    ]
    resolved, unresolved = _resolve_moved_children(session, moved_ids)
    checks.extend((_audit_key(model), model) for model in _MERGE_MODELS)
    missing: list[str] = list(unresolved)
    misplaced: list[str] = []
    for table, model in checks:
        if model in _MERGE_MODELS:
            ids = [str(row_id) for row_id in resolved.get(model, [])]
        else:
            ids = moved_ids.get(table, [])
        if not ids:
            continue
        parsed = [uuid.UUID(raw_id) for raw_id in ids]
        rows = session.execute(
            select(model.id, model.facility_id).where(model.id.in_(parsed))
        ).all()
        found = {row.id: row.facility_id for row in rows}
        for raw_id, row_id in zip(ids, parsed, strict=True):
            if row_id not in found:
                missing.append(f"{table}:{raw_id}")
            elif found[row_id] != target_id:
                misplaced.append(f"{table}:{raw_id}")
    if missing or misplaced:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing[:10]))
        if misplaced:
            details.append("no longer on target=" + ",".join(misplaced[:10]))
        raise MatchingError(
            "The merged records changed after the merge; resolve them before undo ("
            + "; ".join(details)
            + ")."
        )
