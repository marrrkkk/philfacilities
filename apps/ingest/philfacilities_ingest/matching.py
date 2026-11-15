"""Deterministic cross-source identity matching and review-queue operations.

The matcher only *proposes* links. It never merges facilities automatically. A candidate
must be accepted by a reviewer, and a merge is a separate explicit operation. Every
decision is retained with the algorithm version and evidence.
"""

from __future__ import annotations

import hashlib
import math
import re
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
    EnrollmentObservation,
    Facility,
    FacilityChangeEvent,
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
)
from sqlalchemy import select
from sqlalchemy.orm import Session

MATCH_METHOD = "exact_normalized_name_psgc_type"
ALGORITHM_VERSION = "1"
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
MERGED = "merged"

# Child tables that follow a facility when a human-confirmed merge is applied.
_MERGE_MODELS = (
    AttributeAssertion,
    SchoolProfile,
    EnrollmentObservation,
    ResourceObservation,
    HealthProfile,
    HealthLicense,
    HealthAccreditation,
    QualityIssue,
)


class MatchingError(Exception):
    """Raised when a review action cannot be applied safely."""


@dataclass
class _FacilityRef:
    facility: Facility
    location: FacilityLocation
    agency_codes: set[str] = field(default_factory=set)
    links: list[tuple[FacilitySourceLink, SourceRecord, Agency, Release]] = field(
        default_factory=list
    )

    def link_for_other_agency(self, other_codes: set[str]) -> tuple | None:
        for link, record, agency, release in self.links:
            if other_codes and agency.short_code in other_codes:
                continue
            return link, record, agency, release
        return None


def normalize_name(value: str | None) -> str:
    """Case-fold and collapse punctuation/whitespace for deterministic comparison."""

    if not value:
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def candidate_key(
    source_record_id: uuid.UUID,
    candidate_facility_id: uuid.UUID,
) -> str:
    raw = "|".join(
        (
            MATCH_METHOD,
            ALGORITHM_VERSION,
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
    if not source.facility_subtype or not candidate.facility_subtype:
        return True
    return normalize_name(source.facility_subtype) == normalize_name(candidate.facility_subtype)


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
    for link, record, agency, release, facility in rows:
        ref = refs.get(facility.id)
        if ref is None:
            location = _current_location(session, facility.id)
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
) -> MatchCandidate:
    """Retire the source facility into the accepted candidate facility.

    The source facility row is retained as an internal tombstone so its history and the
    candidate audit remain queryable. Source evidence, locations, observations, profiles,
    licences, accreditations, assertions, and issues move to the surviving facility.
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
    if source.facility_type != target.facility_type:
        raise MatchingError("Facilities with incompatible types cannot be merged.")

    now = datetime.now(UTC)
    today = date.today()
    source_before = _facility_snapshot(source)
    target_before = _facility_snapshot(target)
    moved_ids: dict[str, list[str]] = {}

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
        location.facility_id = target.id
        if target_has_current and location.is_current:
            location.is_current = False
            location.valid_to = today
        moved_ids["facility_locations"].append(str(location.id))

    counts: dict[str, int] = {
        "facility_source_links": len(links),
        "facility_locations": len(locations),
    }
    for model in _MERGE_MODELS:
        ids = list(session.scalars(select(model.id).where(model.facility_id == source.id)).all())
        if ids:
            session.execute(
                model.__table__.update()
                .where(model.__table__.c.facility_id == source.id)
                .values(facility_id=target.id)
            )
        table = model.__tablename__
        counts[table] = len(ids)
        moved_ids[table] = [str(value) for value in ids]

    source.publication_status = "internal"
    source.record_status = "merged"
    source.updated_at = now
    target.updated_at = now

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
    }
    session.flush()
    return candidate
