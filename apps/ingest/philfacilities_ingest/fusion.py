"""Combine source claims instead of discarding them during deduplication.

The source record is the unit of truth: it is never rewritten. For every
canonical facility and attribute, this module materialises one *derived* value
plus every competing value and its provenance. A later merge of duplicate
facilities therefore keeps both values, both source records and both releases.

Two operations are provided:

``build_attribute_fusions``
    Deterministic field-level fusion. Missing/empty claims are not treated as
    zero or false; two claims that disagree produce ``status="conflict"`` and
    retain both values. ``agreed`` means two or more *agencies* made the same
    claim; records from the same publisher are not independent corroboration.

``auto_merge_exact_duplicates``
    Consolidates only identity candidates that already met the exact normalized
    name + same PSGC + compatible type test *and* whose recorded address matches
    exactly. Anything less certain stays unmerged and is retried automatically
    when new evidence arrives.

Fusion is automatic; there is no review queue. ``apply_fusions`` writes only the
safe classification allowlist: cross-agency agreements, conflicts with a clear
authority winner, and single-source values that fill a missing canonical field.
Equal-authority conflicts stay derived-only. Names and other curatorial fields
are never overwritten.
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
from philfacilities_api.publication import (
    latest_published_release_id,
    public_dataset_release_condition,
)
from philfacilities_api.taxonomy import (
    ACCESS_CLASSES,
    FACILITY_SUBTYPES,
    OPERATOR_TYPES,
    OWNERSHIP_TYPES,
    OWNERSHIP_VALUES,
    RECORD_STATUSES,
)
from sqlalchemy import delete, func, select
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

ALGORITHM_VERSION = "fusion-v2"
AUTO_MERGE_THRESHOLD = Decimal("0.900")
AUTO_MERGE_REVIEWER = "auto:fusion-v2"

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

FUSION_STATUSES = ("single_source", "agreed", "conflict")
CONFIRMED_ASSERTION_STATUSES = {"confirmed", "reviewed"}
MIN_AGREED_CONFIDENCE = Decimal("0.900")
# A conflict is applied automatically only when the authority margin is clear.
# Equal-authority claims remain derived-only rather than overwriting the
# canonical row on an essentially arbitrary tie-break.
CLEAR_WINNER_CONFIDENCE = Decimal("0.600")

# Source authority is explicit dataset metadata, not a guess from a dataset
# name. Coverage scope refines an official source: a national inventory outranks
# a single-LGU directory even when both are government publishers.
AUTHORITY_WEIGHTS = {
    "official": 3.0,
    "community": 1.0,
    "synthetic": 0.5,
    "unknown": 1.5,
}
COVERAGE_BONUS = {
    "NATIONAL_OFFICIAL_INVENTORY": 1.0,
    "NATIONAL_PARTIAL": 0.5,
    "REGIONAL": 0.25,
    "PARTICIPATING_LGUS": 0.2,
    "SELECTED_LGUS": 0.15,
    "SINGLE_LGU": 0.1,
    "DIRECTORY_SUBSET": 0.1,
    "DISCOVERY_LAYER": 0.0,
    "UNKNOWN_COVERAGE": 0.0,
}

_CANONICAL_VALUES = {
    "ownership": frozenset(OWNERSHIP_VALUES),
    "ownership_type": frozenset(OWNERSHIP_TYPES),
    "operator_type": frozenset(OPERATOR_TYPES),
    "public_access_class": frozenset(ACCESS_CLASSES),
    "record_status": frozenset(RECORD_STATUSES),
    "facility_subtype": frozenset(FACILITY_SUBTYPES),
}
_CANONICAL_CASE = {
    "ownership": "lower",
    "record_status": "lower",
}
_MISSING_CANONICAL = {"", "unknown", "n/a", "na", "null", "none", "-"}
_MIN_TIMESTAMP = datetime.min.replace(tzinfo=UTC)


@dataclass
class FusionStats:
    facilities_scanned: int = 0
    facilities_with_claims: int = 0
    attributes_written: int = 0
    single_source: int = 0
    agreed: int = 0
    conflict: int = 0
    skipped: int = 0
    removed: int = 0
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
            "removed": self.removed,
            "by_attribute": dict(sorted(self.by_attribute.items())),
            "algorithm_version": ALGORITHM_VERSION,
        }


@dataclass
class _Claim:
    normalized: str
    raw: str
    source_record_id: uuid.UUID
    agency_id: uuid.UUID | None
    agency_code: str | None
    agency_publisher_type: str | None
    dataset_id: uuid.UUID | None
    dataset_slug: str | None
    dataset_authority_level: str | None
    dataset_is_synthetic: bool
    coverage_scope: str | None
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


def _comparison_key(claim: _Claim) -> str:
    return normalize_name(claim.normalized) or claim.normalized.casefold()


def _source_authority_level(claim: _Claim) -> str:
    if claim.dataset_is_synthetic:
        return "synthetic"
    level = (claim.dataset_authority_level or "unknown").casefold()
    if level != "unknown":
        return level if level in AUTHORITY_WEIGHTS else "unknown"
    publisher = (claim.agency_publisher_type or "").casefold()
    if publisher == "community":
        return "community"
    if publisher in {"government", "gocc", "lgu", "regional"}:
        return "official"
    return "unknown"


def _authority(claim: _Claim) -> float:
    score = 0.0
    if claim.review_status in CONFIRMED_ASSERTION_STATUSES:
        score += 10.0
    elif claim.review_status == "disputed":
        score -= 1.0
    level = _source_authority_level(claim)
    score += AUTHORITY_WEIGHTS[level]
    if level == "official":
        score += COVERAGE_BONUS.get((claim.coverage_scope or "").upper(), 0.0)
    return score


def _claim_order(claim: _Claim) -> tuple:
    return (
        _authority(claim),
        claim.retrieved_at or _MIN_TIMESTAMP,
        len(claim.raw),
        claim.raw.casefold(),
    )


def _support(claims: Iterable[_Claim]) -> tuple[int, int, int, int]:
    """Return distinct agencies, datasets, releases and source records."""

    claims = list(claims)
    agencies = {claim.agency_id for claim in claims if claim.agency_id is not None}
    if not agencies:
        agencies = {claim.agency_code for claim in claims if claim.agency_code}
    datasets = {claim.dataset_id for claim in claims if claim.dataset_id is not None}
    if not datasets:
        datasets = {claim.dataset_slug for claim in claims if claim.dataset_slug}
    releases = {claim.release_id for claim in claims if claim.release_id is not None}
    records = {claim.source_record_id for claim in claims}
    return len(agencies), len(datasets), len(releases), len(records)


def _group_claims(rows: Iterable[tuple]) -> dict[tuple[uuid.UUID, str], list[_Claim]]:
    grouped: dict[tuple[uuid.UUID, str], list[_Claim]] = defaultdict(list)
    for assertion, _record, release, dataset, agency in rows:
        if (assertion.review_status or "").casefold() == "rejected":
            continue
        normalized = _text(assertion.normalized_value)
        raw = _text(assertion.raw_value) or normalized
        if normalized is None or raw is None:
            continue
        grouped[(assertion.facility_id, assertion.attribute_name)].append(
            _Claim(
                normalized=normalized,
                raw=raw,
                source_record_id=assertion.source_record_id,
                agency_id=dataset.agency_id if dataset else None,
                agency_code=agency.short_code if agency else None,
                agency_publisher_type=agency.publisher_type if agency else None,
                dataset_id=dataset.id if dataset else None,
                dataset_slug=dataset.slug if dataset else None,
                dataset_authority_level=dataset.authority_level if dataset else None,
                dataset_is_synthetic=bool(dataset.is_synthetic) if dataset else False,
                coverage_scope=dataset.coverage_scope if dataset else None,
                release_id=release.id if release else None,
                retrieved_at=release.retrieved_at if release else None,
                review_status=(assertion.review_status or "source_supplied").casefold(),
            )
        )
    return grouped


def _group_by_value(claims: Iterable[_Claim]) -> dict[str, list[_Claim]]:
    grouped: dict[str, list[_Claim]] = defaultdict(list)
    for claim in claims:
        grouped[_comparison_key(claim)].append(claim)
    return grouped


def _alternative_entries(claims: list[_Claim], selected_key: str) -> list[dict[str, Any]]:
    entries = []
    for key, group in _group_by_value(claims).items():
        ordered = sorted(group, key=_claim_order, reverse=True)
        agencies, datasets, releases, _records = _support(group)
        latest = max(
            (claim.retrieved_at for claim in group if claim.retrieved_at),
            default=None,
        )
        entries.append(
            {
                "normalized_value": ordered[0].normalized,
                "comparison_key": key,
                "selected": key == selected_key,
                "raw_values": sorted({claim.raw for claim in group}),
                "claim_count": len(group),
                "distinct_agencies": agencies,
                "distinct_datasets": datasets,
                "distinct_releases": releases,
                "source_record_ids": sorted({str(claim.source_record_id) for claim in group}),
                "agency_codes": sorted({claim.agency_code for claim in group if claim.agency_code}),
                "dataset_slugs": sorted(
                    {claim.dataset_slug for claim in group if claim.dataset_slug}
                ),
                "authority_levels": sorted({_source_authority_level(claim) for claim in group}),
                "coverage_scopes": sorted(
                    {claim.coverage_scope for claim in group if claim.coverage_scope}
                ),
                "release_ids": sorted(
                    {str(claim.release_id) for claim in group if claim.release_id}
                ),
                "latest_retrieved_at": latest.isoformat() if latest else None,
                "review_statuses": sorted({claim.review_status for claim in group}),
            }
        )
    entries.sort(
        key=lambda item: (
            not item["selected"],
            -item["claim_count"],
            item["normalized_value"],
        )
    )
    return entries


def _group_rank(item: tuple[str, list[_Claim]]) -> tuple:
    key, group = item
    ordered = sorted(group, key=_claim_order, reverse=True)
    best = ordered[0]
    agencies, datasets, releases, records = _support(group)
    return (
        _authority(best),
        agencies,
        datasets,
        releases,
        records,
        best.retrieved_at or _MIN_TIMESTAMP,
        key,
    )


def _choose(claims: list[_Claim]) -> tuple[_Claim, str, Decimal, int, str]:
    grouped = _group_by_value(claims)
    ranked = sorted(grouped.items(), key=_group_rank, reverse=True)
    winner_key, winner_group = ranked[0]
    selected = sorted(winner_group, key=_claim_order, reverse=True)[0]

    if len(grouped) > 1:
        status = "conflict"
        top = _group_rank(ranked[0])
        runner_up = _group_rank(ranked[1])
        confidence = Decimal("0.650") if top[0] - runner_up[0] >= 1.0 else Decimal("0.350")
    else:
        agencies, _datasets, _releases, _records = _support(winner_group)
        if agencies > 1:
            status = "agreed"
            confidence = Decimal("0.950")
        else:
            status = "single_source"
            confidence = Decimal("0.700")
    return selected, status, confidence, len(grouped), winner_key


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
                # Review fields are deliberately untouched: a recomputation must
                # not erase a curator's decision.
            },
        )
        session.execute(statement)


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _filter_multi_source(session: Session, facility_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if not facility_ids:
        return []
    return list(
        session.scalars(
            select(FacilitySourceLink.facility_id)
            .where(FacilitySourceLink.facility_id.in_(facility_ids))
            .group_by(FacilitySourceLink.facility_id)
            .having(func.count(func.distinct(FacilitySourceLink.source_record_id)) > 1)
        ).all()
    )


def _facility_ids(
    session: Session,
    facility_ids: Iterable[uuid.UUID] | None,
    *,
    multi_source_only: bool = False,
) -> Iterable[list[uuid.UUID]]:
    if facility_ids is not None:
        unique = list(dict.fromkeys(facility_ids))
        for batch in _chunks(unique, 5000):
            scoped = _filter_multi_source(session, batch) if multi_source_only else batch
            if scoped:
                yield scoped
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


def _delete_stale_fusions(
    session: Session,
    facility_ids: list[uuid.UUID],
    current_keys: set[tuple[uuid.UUID, str]],
) -> int:
    """Remove derived rows whose claims no longer exist.

    A release rollback deletes assertions but cannot leave the old derived
    selection behind: a later apply pass would otherwise re-promote a value that
    no retained source claims any more.
    """

    existing = session.execute(
        select(
            FacilityAttributeFusion.id,
            FacilityAttributeFusion.facility_id,
            FacilityAttributeFusion.attribute_name,
        ).where(FacilityAttributeFusion.facility_id.in_(facility_ids))
    ).all()
    stale_ids = [
        row.id for row in existing if (row.facility_id, row.attribute_name) not in current_keys
    ]
    for batch in _chunks(stale_ids, 1000):
        session.execute(
            delete(FacilityAttributeFusion).where(FacilityAttributeFusion.id.in_(batch))
        )
    return len(stale_ids)


def delete_fusions_for_facilities(session: Session, facility_ids: Iterable[uuid.UUID]) -> int:
    """Invalidate derived fusion rows after a merge or rollback changes evidence."""

    unique = list(dict.fromkeys(facility_ids))
    removed = 0
    for batch in _chunks(unique, 1000):
        result = session.execute(
            delete(FacilityAttributeFusion).where(FacilityAttributeFusion.facility_id.in_(batch))
        )
        removed += result.rowcount or 0
    return removed


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
    ``multi_source_only=False`` to materialise a row for every facility. An
    explicit ``facility_ids`` list is scoped by the same rule, so ``--limit``
    cannot silently widen the run.
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
            .where(
                AttributeAssertion.facility_id.in_(batch),
                # Only current public claims may select or corroborate a value.
                # A restricted dataset, an unpublished release, or a superseded
                # snapshot must not override the public canonical record.
                Release.id == latest_published_release_id(Dataset.id),
                public_dataset_release_condition(),
            )
        ).all()
        grouped = _group_claims(rows)
        usable_claims = sum(len(claims) for claims in grouped.values())
        stats.skipped += max(0, len(rows) - usable_claims)
        if grouped:
            stats.facilities_with_claims += len({facility_id for facility_id, _ in grouped})
        pending: list[dict[str, Any]] = []
        for (facility_id, attribute_name), claims in grouped.items():
            selected, status, confidence, distinct, selected_key = _choose(claims)
            pending.append(
                {
                    "facility_id": facility_id,
                    "attribute_name": attribute_name,
                    "selected_value": selected.raw,
                    "selected_normalized_value": selected.normalized,
                    "selected_source_record_id": selected.source_record_id,
                    "selection_method": "authority_then_independent_support_then_recency",
                    "status": status,
                    "confidence": confidence,
                    "distinct_value_count": distinct,
                    "claim_count": len(claims),
                    "alternatives": _alternative_entries(claims, selected_key),
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
        stats.removed += _delete_stale_fusions(session, batch, set(grouped))
        _upsert_fusions(session, pending)
        session.flush()
        if progress is not None:
            progress(stats)
    return stats


def _canonical_value(attribute: str, value: Any) -> str | None:
    """Return the canonical spelling for a safe field, or ``None`` if invalid."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    allowed = _CANONICAL_VALUES.get(attribute)
    if allowed is None:
        return text
    candidate = text.lower() if _CANONICAL_CASE.get(attribute) == "lower" else text.upper()
    return candidate if candidate in allowed else None


def _is_missing_canonical(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in _MISSING_CANONICAL


def _apply_decision(
    fusion: FacilityAttributeFusion,
) -> tuple[str, str, uuid.UUID | None] | None:
    if fusion.status == "agreed" and fusion.confidence >= MIN_AGREED_CONFIDENCE:
        return ("agreed", fusion.selected_value, fusion.selected_source_record_id)
    if fusion.status == "conflict" and fusion.confidence >= CLEAR_WINNER_CONFIDENCE:
        return ("conflict_auto", fusion.selected_value, fusion.selected_source_record_id)
    if fusion.status == "single_source":
        return ("gap_fill", fusion.selected_value, fusion.selected_source_record_id)
    return None


def apply_fusions(
    session: Session,
    *,
    facility_ids: Iterable[uuid.UUID] | None = None,
    dry_run: bool = False,
    algorithm_version: str | None = ALGORITHM_VERSION,
) -> dict[str, Any]:
    """Apply safe fused values automatically; no human review step.

    Policy:

    - a cross-agency ``agreed`` value is applied when its confidence is at least
      ``0.900``;
    - a ``conflict`` with a clear authority winner is applied automatically;
    - an equal-authority conflict is left derived-only because the tie-break is
      not reliable enough to overwrite the canonical row;
    - a ``single_source`` value only fills a missing/unknown canonical field.

    Every applied change writes a ``FacilityChangeEvent`` with the fusion status,
    algorithm version and supporting source record. Alternatives and raw source
    claims are never rewritten, so the automated decision remains auditable.
    """

    query = (
        select(FacilityAttributeFusion, Facility)
        .join(Facility, FacilityAttributeFusion.facility_id == Facility.id)
        .where(
            FacilityAttributeFusion.attribute_name.in_(SAFE_APPLY_FIELDS),
            FacilityAttributeFusion.status.in_(FUSION_STATUSES),
        )
    )
    if algorithm_version is not None:
        query = query.where(FacilityAttributeFusion.algorithm_version == algorithm_version)
    if facility_ids is not None:
        query = query.where(
            FacilityAttributeFusion.facility_id.in_(list(dict.fromkeys(facility_ids)))
        )
    rows = session.execute(query.order_by(FacilityAttributeFusion.facility_id)).all()
    applied = 0
    skipped = 0
    skipped_by_reason: dict[str, int] = defaultdict(int)
    examples: list[dict[str, Any]] = []
    skipped_examples: list[dict[str, Any]] = []
    for fusion, facility in rows:
        decision = _apply_decision(fusion)
        if decision is None:
            skipped += 1
            skipped_by_reason[
                "ambiguous_conflict" if fusion.status == "conflict" else "not_applicable"
            ] += 1
            continue
        decision_kind, source_value, source_record_id = decision
        canonical = _canonical_value(fusion.attribute_name, source_value)
        if canonical is None:
            skipped += 1
            skipped_by_reason["invalid_canonical_value"] += 1
            if len(skipped_examples) < 10:
                skipped_examples.append(
                    {
                        "facility_id": str(facility.id),
                        "attribute": fusion.attribute_name,
                        "value": source_value,
                        "reason": "invalid_canonical_value",
                    }
                )
            continue
        current = getattr(facility, fusion.attribute_name, None)
        if current == canonical:
            continue
        if decision_kind == "gap_fill" and not _is_missing_canonical(current):
            skipped += 1
            skipped_by_reason["existing_value_not_missing"] += 1
            continue
        if dry_run:
            applied += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "facility_id": str(facility.id),
                        "attribute": fusion.attribute_name,
                        "old": current,
                        "new": canonical,
                        "decision": decision_kind,
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
                    "value": canonical,
                    "source_value": source_value,
                    "fusion_status": fusion.status,
                    "confidence": str(fusion.confidence),
                    "decision": decision_kind,
                    "algorithm_version": fusion.algorithm_version,
                },
                source_record_id=source_record_id,
                changed_by=f"fusion:{fusion.algorithm_version}",
            )
        )
        setattr(facility, fusion.attribute_name, canonical)
        facility.updated_at = datetime.now(UTC)
        applied += 1
    if not dry_run:
        session.flush()
    return {
        "applied": applied,
        "skipped": skipped,
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
        "skipped_examples": skipped_examples,
        "dry_run": dry_run,
        "examples": examples,
        "algorithm_version": algorithm_version,
    }


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


def fusion_report(
    session: Session,
    *,
    status: str | None = "conflict",
    limit: int = 25,
) -> dict[str, Any]:
    """Report fused attributes and any conflicts left derived-only."""

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
    unresolved_conflicts = (
        session.scalar(
            select(func.count()).where(
                FacilityAttributeFusion.status == "conflict",
                FacilityAttributeFusion.confidence < CLEAR_WINNER_CONFIDENCE,
            )
        )
        or 0
    )
    query = select(FacilityAttributeFusion, Facility).join(
        Facility, FacilityAttributeFusion.facility_id == Facility.id
    )
    if status is not None:
        query = query.where(FacilityAttributeFusion.status == status)
    samples = session.execute(
        query.order_by(
            FacilityAttributeFusion.attribute_name,
            FacilityAttributeFusion.status,
            Facility.display_name,
        ).limit(limit)
    ).all()
    return {
        "total": sum(counts.values()),
        "by_status": counts,
        "unresolved_conflicts": unresolved_conflicts,
        "by_attribute": by_attribute,
        "sample_status": status,
        "samples": [
            {
                "facility_id": str(fusion.facility_id),
                "facility": facility.display_name,
                "attribute": fusion.attribute_name,
                "selected_value": fusion.selected_value,
                "distinct_values": fusion.distinct_value_count,
                "claim_count": fusion.claim_count,
                "confidence": str(fusion.confidence),
                "status": fusion.status,
                "alternatives": fusion.alternatives,
            }
            for fusion, facility in samples
        ],
        "algorithm_version": ALGORITHM_VERSION,
    }
