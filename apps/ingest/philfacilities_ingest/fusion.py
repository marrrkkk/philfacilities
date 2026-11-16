"""Combine source claims instead of discarding them during deduplication.

The source record is the unit of truth: it is never rewritten. For every
canonical facility and attribute, this module materialises one *derived* value
plus every conflicting value and its provenance. A later merge of duplicate
facilities therefore keeps both values, both source records and both releases.

Two operations are provided:

``build_attribute_fusions``
    Deterministic field-level fusion. Missing/empty claims are not treated as
    zero or false; two claims that disagree produce ``status="conflict"`` and
    retain both values.

``auto_merge_exact_duplicates``
    Consolidates only identity candidates that already met the exact normalized
    name + same PSGC + compatible type test *and* whose recorded address matches
    exactly. Anything less certain stays in the human review queue.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from philfacilities_api.models import (
    Agency,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityAttributeFusion,
    FacilityChangeEvent,
    FacilitySourceLink,
    Release,
    SourceRecord,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .matching import (
    GEO_MATCH_METHOD,
    MatchingError,
    accept_match_candidate,
    generate_geo_match_candidates,
    generate_match_candidates,
    merge_match_candidate,
    normalize_name,
)

ALGORITHM_VERSION = "fusion-v1"
AUTO_MERGE_THRESHOLD = Decimal("0.900")
AUTO_MERGE_REVIEWER = "auto:fusion-v1"

# Fields where a fused value may safely replace the canonical display value.
# Names are deliberately excluded: a merged spelling is a curatorial decision,
# not a deterministic source preference.
SAFE_APPLY_FIELDS = {
    "facility_subtype",
    "ownership",
    "ownership_type",
    "operator_type",
    "public_access_class",
    "record_status",
}

# A small, explicit authority score. It is not a truth claim: it only orders
# claims when sources disagree, and the losing values remain in ``alternatives``.
GOVERNMENT_PUBLISHERS = {"government", "gocc", "lgu", "regional"}
AUTHORITY_TOKENS = (
    ("official", 0.4),
    ("registry", 0.4),
    ("masterlist", 0.4),
    ("licensed", 0.4),
    ("accredited", 0.3),
    ("directory", 0.2),
)
LOW_AUTHORITY_TOKENS = (("openstreetmap", -0.3), ("osm", -0.3), ("bettergov", -0.2))


@dataclass
class FusionStats:
    facilities_scanned: int = 0
    facilities_with_claims: int = 0
    attributes_written: int = 0
    single_source: int = 0
    agreed: int = 0
    conflict: int = 0
    skipped: int = 0
    by_attribute: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "facilities_scanned": self.facilities_scanned,
            "facilities_with_claims": self.facilities_with_claims,
            "attributes_written": self.attributes_written,
            "single_source": self.single_source,
            "agreed": self.agreed,
            "conflict": self.conflict,
            "skipped": self.skipped,
            "by_attribute": dict(sorted(self.by_attribute.items())),
            "algorithm_version": ALGORITHM_VERSION,
        }


@dataclass
class _Claim:
    normalized: str
    raw: str
    source_record_id: uuid.UUID
    agency_code: str | None
    agency_publisher_type: str | None
    dataset_slug: str | None
    release_id: uuid.UUID | None
    retrieved_at: datetime | None
    review_status: str


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"unknown", "n/a", "na", "null", "none", "-"}:
        return None
    return text


def _authority(claim: _Claim) -> float:
    score = 0.0
    if claim.review_status in {"confirmed", "reviewed"}:
        score += 2.0
    elif claim.review_status == "source_supplied":
        score += 0.5
    if (claim.agency_publisher_type or "").casefold() in GOVERNMENT_PUBLISHERS:
        score += 0.6
    haystack = f"{claim.dataset_slug or ''} {claim.agency_code or ''}".casefold()
    for token, delta in AUTHORITY_TOKENS:
        if token in haystack:
            score += delta
            break
    for token, delta in LOW_AUTHORITY_TOKENS:
        if token in haystack:
            score += delta
            break
    return score


def _claim_order(claim: _Claim) -> tuple:
    return (
        _authority(claim),
        claim.retrieved_at or datetime.min.replace(tzinfo=UTC),
        len(claim.raw),
        claim.raw,
    )


def _group_claims(rows: Iterable[tuple]) -> dict[tuple[uuid.UUID, str], list[_Claim]]:
    grouped: dict[tuple[uuid.UUID, str], list[_Claim]] = defaultdict(list)
    for assertion, _record, release, dataset, agency in rows:
        normalized = _text(assertion.normalized_value)
        raw = _text(assertion.raw_value) or normalized
        if normalized is None or raw is None:
            continue
        grouped[(assertion.facility_id, assertion.attribute_name)].append(
            _Claim(
                normalized=normalized,
                raw=raw,
                source_record_id=assertion.source_record_id,
                agency_code=agency.short_code if agency else None,
                agency_publisher_type=agency.publisher_type if agency else None,
                dataset_slug=dataset.slug if dataset else None,
                release_id=release.id if release else None,
                retrieved_at=release.retrieved_at if release else None,
                review_status=assertion.review_status or "source_supplied",
            )
        )
    return grouped


def _alternative_entries(claims: list[_Claim]) -> list[dict[str, Any]]:
    grouped: dict[str, list[_Claim]] = defaultdict(list)
    for claim in claims:
        grouped[normalize_name(claim.normalized) or claim.normalized.casefold()].append(claim)
    entries = []
    for key, group in grouped.items():
        ordered = sorted(group, key=_claim_order, reverse=True)
        entries.append(
            {
                "normalized_value": ordered[0].normalized,
                "comparison_key": key,
                "raw_values": sorted({claim.raw for claim in group}),
                "claim_count": len(group),
                "source_record_ids": sorted({str(claim.source_record_id) for claim in group}),
                "agency_codes": sorted({claim.agency_code for claim in group if claim.agency_code}),
                "dataset_slugs": sorted(
                    {claim.dataset_slug for claim in group if claim.dataset_slug}
                ),
                "release_ids": sorted(
                    {str(claim.release_id) for claim in group if claim.release_id}
                ),
                "latest_retrieved_at": (
                    max(
                        (claim.retrieved_at for claim in group if claim.retrieved_at),
                        default=None,
                    ).isoformat()
                    if any(claim.retrieved_at for claim in group)
                    else None
                ),
                "review_statuses": sorted({claim.review_status for claim in group}),
            }
        )
    entries.sort(key=lambda item: (-item["claim_count"], item["normalized_value"]))
    return entries


def _choose(claims: list[_Claim]) -> tuple[_Claim, str, Decimal, int]:
    grouped: dict[str, list[_Claim]] = defaultdict(list)
    for claim in claims:
        grouped[normalize_name(claim.normalized) or claim.normalized.casefold()].append(claim)

    def group_rank(item: tuple[str, list[_Claim]]) -> tuple:
        key, group = item
        ordered = sorted(group, key=_claim_order, reverse=True)
        best = ordered[0]
        return (
            len(group),
            _authority(best),
            best.retrieved_at or datetime.min.replace(tzinfo=UTC),
            key,
        )

    _key, group = max(grouped.items(), key=group_rank)
    selected = sorted(group, key=_claim_order, reverse=True)[0]
    if len(grouped) > 1:
        status = "conflict"
        confidence = Decimal("0.500")
    elif len({claim.source_record_id for claim in claims}) > 1:
        status = "agreed"
        confidence = Decimal("0.950")
    else:
        status = "single_source"
        confidence = Decimal("0.700")
    return selected, status, confidence, len(grouped)


def _upsert_fusions(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    for start in range(0, len(rows), 1000):
        chunk = rows[start : start + 1000]
        statement = insert(FacilityAttributeFusion).values(chunk)
        statement = statement.on_conflict_do_update(
            index_elements=["facility_id", "attribute_name"],
            set_={
                "selected_value": statement.excluded.selected_value,
                "selected_normalized_value": statement.excluded.selected_normalized_value,
                "selected_source_record_id": statement.excluded.selected_source_record_id,
                "selection_method": statement.excluded.selection_method,
                "status": statement.excluded.status,
                "confidence": statement.excluded.confidence,
                "distinct_value_count": statement.excluded.distinct_value_count,
                "claim_count": statement.excluded.claim_count,
                "alternatives": statement.excluded.alternatives,
                "algorithm_version": statement.excluded.algorithm_version,
                "computed_at": func.now(),
            },
        )
        session.execute(statement)


def _facility_ids(
    session: Session,
    facility_ids: Iterable[uuid.UUID] | None,
    *,
    multi_source_only: bool = False,
) -> Iterable[list[uuid.UUID]]:
    if facility_ids is not None:
        batch: list[uuid.UUID] = []
        for facility_id in facility_ids:
            batch.append(facility_id)
            if len(batch) >= 5000:
                yield batch
                batch = []
        if batch:
            yield batch
        return
    last: uuid.UUID | None = None
    while True:
        query = select(Facility.id).order_by(Facility.id).limit(5000)
        if multi_source_only:
            query = (
                select(Facility.id)
                .join(
                    FacilitySourceLink,
                    FacilitySourceLink.facility_id == Facility.id,
                )
                .group_by(Facility.id)
                .having(func.count(func.distinct(FacilitySourceLink.source_record_id)) > 1)
                .order_by(Facility.id)
                .limit(5000)
            )
        if last is not None:
            query = query.where(Facility.id > last)
        batch = list(session.scalars(query).all())
        if not batch:
            return
        yield batch
        last = batch[-1]


def build_attribute_fusions(
    session: Session,
    *,
    facility_ids: Iterable[uuid.UUID] | None = None,
    multi_source_only: bool = True,
    progress: Any = None,
) -> FusionStats:
    """Materialise one fusion row per facility/attribute from source claims.

    By default only facilities already linked to more than one source record are
    processed: those are where conflicting values can exist. Pass
    ``multi_source_only=False`` to materialise a row for every facility.
    """

    stats = FusionStats()
    for batch in _facility_ids(session, facility_ids, multi_source_only=multi_source_only):
        stats.facilities_scanned += len(batch)
        rows = session.execute(
            select(AttributeAssertion, SourceRecord, Release, Dataset, Agency)
            .join(SourceRecord, AttributeAssertion.source_record_id == SourceRecord.id)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .join(Agency, Dataset.agency_id == Agency.id)
            .where(AttributeAssertion.facility_id.in_(batch))
        ).all()
        grouped = _group_claims(rows)
        if grouped:
            stats.facilities_with_claims += len({facility_id for facility_id, _ in grouped})
        pending: list[dict[str, Any]] = []
        for (facility_id, attribute_name), claims in grouped.items():
            selected, status, confidence, distinct = _choose(claims)
            pending.append(
                {
                    "facility_id": facility_id,
                    "attribute_name": attribute_name,
                    "selected_value": selected.raw,
                    "selected_normalized_value": selected.normalized,
                    "selected_source_record_id": selected.source_record_id,
                    "selection_method": "authority_then_frequency_then_recency",
                    "status": status,
                    "confidence": confidence,
                    "distinct_value_count": distinct,
                    "claim_count": len(claims),
                    "alternatives": _alternative_entries(claims),
                    "algorithm_version": ALGORITHM_VERSION,
                }
            )
            stats.attributes_written += 1
            stats.by_attribute[attribute_name] = stats.by_attribute.get(attribute_name, 0) + 1
            if status == "conflict":
                stats.conflict += 1
            elif status == "agreed":
                stats.agreed += 1
            else:
                stats.single_source += 1
        _upsert_fusions(session, pending)
        session.flush()
        if progress is not None:
            progress(stats)
    return stats


def apply_fusions(
    session: Session,
    *,
    facility_ids: Iterable[uuid.UUID] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply only agreed or confirmed safe fields to the canonical facility.

    Conflicting or single-source unconfirmed values stay in the fusion table for
    review; the canonical row is not silently rewritten.
    """

    query = (
        select(FacilityAttributeFusion, Facility)
        .join(Facility, FacilityAttributeFusion.facility_id == Facility.id)
        .where(
            FacilityAttributeFusion.attribute_name.in_(SAFE_APPLY_FIELDS),
            or_(
                FacilityAttributeFusion.status == "agreed",
                and_(
                    FacilityAttributeFusion.status == "single_source",
                    FacilityAttributeFusion.confidence >= Decimal("0.900"),
                ),
            ),
        )
    )
    if facility_ids is not None:
        query = query.where(FacilityAttributeFusion.facility_id.in_(list(facility_ids)))
    rows = session.execute(query.order_by(FacilityAttributeFusion.facility_id)).all()
    applied = 0
    skipped = 0
    examples: list[dict[str, Any]] = []
    for fusion, facility in rows:
        if fusion.attribute_name not in SAFE_APPLY_FIELDS:
            continue
        if fusion.selected_value is None:
            continue
        if not (
            fusion.status == "agreed"
            or (fusion.status == "single_source" and fusion.confidence >= Decimal("0.900"))
        ):
            skipped += 1
            continue
        current = getattr(facility, fusion.attribute_name, None)
        if current == fusion.selected_value:
            continue
        if dry_run:
            applied += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "facility_id": str(facility.id),
                        "attribute": fusion.attribute_name,
                        "old": current,
                        "new": fusion.selected_value,
                    }
                )
            continue
        session.add(
            FacilityChangeEvent(
                facility_id=facility.id,
                change_type="attribute_fused",
                attribute_name=fusion.attribute_name,
                old_value={"value": current},
                new_value={
                    "value": fusion.selected_value,
                    "fusion_status": fusion.status,
                    "confidence": str(fusion.confidence),
                    "algorithm_version": ALGORITHM_VERSION,
                },
                source_record_id=fusion.selected_source_record_id,
                changed_by=f"fusion:{ALGORITHM_VERSION}",
            )
        )
        setattr(facility, fusion.attribute_name, fusion.selected_value)
        facility.updated_at = datetime.now(UTC)
        applied += 1
    return {"applied": applied, "skipped": skipped, "dry_run": dry_run, "examples": examples}


@dataclass
class AutoMergeStats:
    candidates_considered: int = 0
    merged: int = 0
    skipped_ambiguous: int = 0
    skipped_error: int = 0
    errors: list[str] = field(default_factory=list)
    merged_pairs: list[dict[str, Any]] = field(default_factory=list)
    generation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates_considered": self.candidates_considered,
            "merged": self.merged,
            "skipped_ambiguous": self.skipped_ambiguous,
            "skipped_error": self.skipped_error,
            "errors": self.errors[:20],
            "merged_pairs": self.merged_pairs[:20],
            "generation": self.generation,
            "algorithm_version": ALGORITHM_VERSION,
        }


def _is_exact_candidate(evidence: dict[str, Any] | None, confidence: Decimal) -> bool:
    if evidence is None or confidence < AUTO_MERGE_THRESHOLD:
        return False
    if evidence.get("algorithm") == GEO_MATCH_METHOD:
        return bool(
            evidence.get("name_specific") is True
            and evidence.get("official_side") is True
            and evidence.get("distance_m") is not None
            and float(evidence["distance_m"]) <= 25.0
            and evidence.get("source_agency_code") != evidence.get("candidate_agency_code")
        )
    if not evidence.get("address_match"):
        return False
    if evidence.get("normalized_name") and evidence.get("normalized_name") != normalize_name(
        (evidence.get("source_facility_snapshot") or {}).get("display_name")
    ):
        return False
    return (
        evidence.get("psgc_code") is not None
        and evidence.get("subtype_compatible") is True
        and evidence.get("source_agency_code") != evidence.get("candidate_agency_code")
    )


def auto_merge_exact_duplicates(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Merge only exact-address identity candidates; leave everything else queued."""

    from philfacilities_api.models import MatchCandidate

    psgc_stats = generate_match_candidates(session)
    geo_stats = generate_geo_match_candidates(session)
    candidates = list(
        session.scalars(
            select(MatchCandidate)
            .where(
                MatchCandidate.match_status == "pending",
                MatchCandidate.match_confidence >= AUTO_MERGE_THRESHOLD,
            )
            .order_by(MatchCandidate.match_confidence.desc(), MatchCandidate.created_at)
            .limit(limit)
        ).all()
    )
    stats = AutoMergeStats()
    stats.generation = {"psgc": psgc_stats, "geo": geo_stats}
    for candidate in candidates:
        stats.candidates_considered += 1
        if not _is_exact_candidate(candidate.evidence, candidate.match_confidence):
            stats.skipped_ambiguous += 1
            continue
        if dry_run:
            stats.merged_pairs.append(
                {
                    "candidate_id": str(candidate.id),
                    "source_facility_id": str(candidate.source_facility_id),
                    "candidate_facility_id": str(candidate.candidate_facility_id),
                    "confidence": str(candidate.match_confidence),
                    "action": "would_merge",
                }
            )
            stats.merged += 1
            continue
        try:
            accept_match_candidate(
                session,
                candidate.id,
                reviewer=AUTO_MERGE_REVIEWER,
                note="Exact normalized name, PSGC and address; deterministic fusion merge.",
            )
            merge_match_candidate(
                session,
                candidate.id,
                reviewer=AUTO_MERGE_REVIEWER,
                note="Deterministic exact-address duplicate; all source claims retained.",
            )
            stats.merged += 1
            stats.merged_pairs.append(
                {
                    "candidate_id": str(candidate.id),
                    "source_facility_id": str(candidate.source_facility_id),
                    "candidate_facility_id": str(candidate.candidate_facility_id),
                    "confidence": str(candidate.match_confidence),
                }
            )
        except MatchingError as exc:
            stats.skipped_error += 1
            stats.errors.append(f"{candidate.id}: {exc}")
    return stats.as_dict()


def fusion_report(session: Session) -> dict[str, Any]:
    counts = dict(
        session.execute(
            select(FacilityAttributeFusion.status, func.count()).group_by(
                FacilityAttributeFusion.status
            )
        ).all()
    )
    by_attribute = dict(
        session.execute(
            select(FacilityAttributeFusion.attribute_name, func.count())
            .group_by(FacilityAttributeFusion.attribute_name)
            .order_by(func.count().desc())
            .limit(40)
        ).all()
    )
    conflicts = session.execute(
        select(FacilityAttributeFusion, Facility)
        .join(Facility, FacilityAttributeFusion.facility_id == Facility.id)
        .where(FacilityAttributeFusion.status == "conflict")
        .order_by(FacilityAttributeFusion.attribute_name, Facility.display_name)
        .limit(25)
    ).all()
    return {
        "total": sum(counts.values()),
        "by_status": counts,
        "by_attribute": by_attribute,
        "conflict_samples": [
            {
                "facility_id": str(fusion.facility_id),
                "facility": facility.display_name,
                "attribute": fusion.attribute_name,
                "selected_value": fusion.selected_value,
                "distinct_values": fusion.distinct_value_count,
                "alternatives": fusion.alternatives,
            }
            for fusion, facility in conflicts
        ],
        "algorithm_version": ALGORITHM_VERSION,
    }
