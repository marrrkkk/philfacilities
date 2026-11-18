"""Deterministic PSGC resolution for facility locations.

A source row can publish an administrative code, or only the administrative
names, that identify its barangay/city/province/region. The ingestion pipeline
keeps only codes that appear verbatim in the current PSGC release, so legacy
9-digit codes and stale OSM P-codes leave otherwise well-described locations
showing "Unknown". This module resolves those gaps from the linked source
payloads without inventing a location:

* an exact current PSGC code;
* the release's published ``correspondence_code`` for a legacy code;
* an exact normalized administrative-name hierarchy when a code is absent or
  stale.

Resolution is conservative. Ambiguous names, conflicting codes, or names that
do not agree with their parent hierarchy stay unresolved. A non-null
``FacilityLocation.psgc_code`` is never overwritten, and every resolved value is
recorded as an ``AttributeAssertion`` pointing at the source record that
supplied the evidence.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from philfacilities_api.models import (
    AdministrativeUnit,
    AttributeAssertion,
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    GeographicRelease,
    Release,
    SourceRecord,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .matching import normalize_name

RESOLUTION_VERSION = "psgc-resolution-v1"
MAX_IDS_PER_QUERY = 5000

_CODE_FIELDS = (
    "psgc_code",
    "brgy_psgc",
    "barangay_psgc",
    "adm4_pcode",
    "muni_psgc",
    "city_psgc",
    "municipality_psgc",
    "adm3_pcode",
    "prov_psgc",
    "province_psgc",
    "adm2_pcode",
    "reg_psgc",
    "region_psgc",
    "adm1_pcode",
)

_LEVEL_RANK = {
    "region": 0,
    "province": 1,
    "municipality": 2,
    "barangay": 3,
}

# level -> (flat payload keys, OSM tag keys), most specific first for reporting.
_NAME_FIELDS = (
    (
        "barangay",
        ("brgy_name", "barangay_name", "adm4_name"),
        ("addr:barangay",),
    ),
    (
        "municipality",
        (
            "municity",
            "city",
            "city_municipality",
            "municipality",
            "city_name",
            "municipality_name",
            "adm3_name",
        ),
        ("addr:city", "addr:town", "addr:municipality"),
    ),
    (
        "province",
        ("prov_name", "province_name", "province", "adm2_name"),
        ("addr:province",),
    ),
    (
        "region",
        ("reg_name", "region_name", "region", "adm1_name"),
        ("addr:region",),
    ),
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _code(value: Any) -> str | None:
    """Normalize a source PSGC/P-code while preserving leading zeros."""

    text = _text(value)
    if not text:
        return None
    if text.upper().startswith("PH"):
        text = text[2:]
    digits = re.sub(r"\D", "", text)
    return digits or None


def _name_aliases(value: str | None) -> set[str]:
    """Normalized names plus common ``City of X``/``X City`` administrative aliases."""

    normalized = normalize_name(value)
    if not normalized:
        return set()
    aliases = {normalized}
    for prefix in (
        "city of ",
        "municipality of ",
        "province of ",
        "region ",
        "barangay ",
        "bgy ",
        "brgy ",
    ):
        if normalized.startswith(prefix):
            aliases.add(normalized[len(prefix) :].strip())
    for suffix in (" city", " municipality", " province"):
        if normalized.endswith(suffix):
            aliases.add(normalized[: -len(suffix)].strip())
    return {alias for alias in aliases if alias}


def _first_text(
    payload: dict[str, Any],
    keys: Iterable[str],
    tags: Iterable[str] = (),
) -> tuple[str, str] | None:
    for key in keys:
        value = _text(payload.get(key))
        if value:
            return key, value
    raw_tags = payload.get("tags")
    tags_by_key = raw_tags if isinstance(raw_tags, dict) else {}
    for key in tags:
        value = _text(tags_by_key.get(key))
        if value:
            return key, value
    return None


@dataclass(frozen=True)
class _Claim:
    level: str
    field: str
    raw: str
    code: str
    method: str


class GeographyIndex:
    """Immutable index over one PSGC release.

    The index is built from ``AdministrativeUnit`` objects loaded by the caller.
    ``correspondence_code`` is the release's own crosswalk from the legacy
    9-digit series, so it is preferred over guessing a zero-padded code.
    """

    def __init__(self, units: Iterable[AdministrativeUnit]) -> None:
        self.by_code: dict[str, AdministrativeUnit] = {}
        self.correspondence: dict[str, set[str]] = defaultdict(set)
        self.by_level_alias: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.by_parent_alias: dict[tuple[str, str], set[str]] = defaultdict(set)
        for unit in units:
            self.by_code[unit.psgc_code] = unit
        for unit in units:
            for alias in _name_aliases(unit.name):
                self.by_level_alias[(unit.geographic_level, alias)].add(unit.psgc_code)
                if unit.parent_psgc_code:
                    self.by_parent_alias[(unit.parent_psgc_code, alias)].add(unit.psgc_code)
            if unit.correspondence_code:
                self.correspondence[unit.correspondence_code].add(unit.psgc_code)
        self._depths: dict[str, int] = {}

    def depth(self, code: str) -> int:
        if code in self._depths:
            return self._depths[code]
        depth = 0
        seen: set[str] = set()
        current = code
        while current and current not in seen:
            seen.add(current)
            unit = self.by_code.get(current)
            if unit is None or not unit.parent_psgc_code:
                break
            depth += 1
            current = unit.parent_psgc_code
        self._depths[code] = depth
        return depth

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        current: str | None = descendant
        seen: set[str] = set()
        while current and current not in seen:
            if current == ancestor:
                return True
            seen.add(current)
            unit = self.by_code.get(current)
            current = unit.parent_psgc_code if unit else None
        return False

    def _lookup_code(self, raw: str) -> tuple[str | None, str | None, bool]:
        exact = self.by_code.get(raw)
        if exact is not None:
            return exact.psgc_code, "source_code_exact", False
        matches = self.correspondence.get(raw, set())
        if len(matches) == 1:
            return next(iter(matches)), "source_code_correspondence", False
        return None, None, len(matches) > 1

    def _pick_name(
        self,
        level: str,
        name: str,
        parents: list[str],
    ) -> tuple[str | None, bool]:
        aliases = _name_aliases(name)
        for parent in parents:
            candidates: set[str] = set()
            for alias in aliases:
                candidates |= self.by_parent_alias.get((parent, alias), set())
            if len(candidates) == 1:
                return next(iter(candidates)), False
            if len(candidates) > 1:
                return None, True
        candidates = set()
        for alias in aliases:
            candidates |= self.by_level_alias.get((level, alias), set())
        if len(candidates) == 1:
            return next(iter(candidates)), False
        return None, len(candidates) > 1

    def resolve_payload(self, payload: dict[str, Any]) -> PayloadResolution:
        """Resolve one source payload without guessing beyond its own evidence."""

        code_claims: list[_Claim] = []
        saw_ambiguous = False
        for key in _CODE_FIELDS:
            raw = _code(payload.get(key))
            if not raw:
                continue
            matched, method, ambiguous = self._lookup_code(raw)
            if matched:
                unit = self.by_code.get(matched)
                code_claims.append(
                    _Claim(
                        level=unit.geographic_level if unit else "unknown",
                        field=key,
                        raw=raw,
                        code=matched,
                        method=method or "source_code_exact",
                    )
                )
            elif ambiguous:
                saw_ambiguous = True

        if code_claims:
            return self._finish_claims(code_claims, name_mode=False)

        name_claims: list[_Claim] = []
        region = _first_text(payload, _NAME_FIELDS[3][1], _NAME_FIELDS[3][2])
        region_code: str | None = None
        if region is not None:
            region_code, ambiguous = self._pick_name("region", region[1], [])
            saw_ambiguous = saw_ambiguous or ambiguous
            if region_code:
                name_claims.append(
                    _Claim("region", region[0], region[1], region_code, "admin_name_hierarchy")
                )

        province = _first_text(payload, _NAME_FIELDS[2][1], _NAME_FIELDS[2][2])
        province_code: str | None = None
        if province is not None:
            province_code, ambiguous = self._pick_name(
                "province", province[1], [region_code] if region_code else []
            )
            saw_ambiguous = saw_ambiguous or ambiguous
            if province_code:
                name_claims.append(
                    _Claim(
                        "province",
                        province[0],
                        province[1],
                        province_code,
                        "admin_name_hierarchy",
                    )
                )

        city = _first_text(payload, _NAME_FIELDS[1][1], _NAME_FIELDS[1][2])
        city_code: str | None = None
        if city is not None:
            parents = [code for code in (province_code, region_code) if code]
            city_code, ambiguous = self._pick_name("municipality", city[1], parents)
            saw_ambiguous = saw_ambiguous or ambiguous
            if city_code:
                name_claims.append(
                    _Claim(
                        "municipality",
                        city[0],
                        city[1],
                        city_code,
                        "admin_name_hierarchy",
                    )
                )

        barangay = _first_text(payload, _NAME_FIELDS[0][1], _NAME_FIELDS[0][2])
        if barangay is not None:
            parents = [city_code] if city_code else []
            barangay_code, ambiguous = self._pick_name("barangay", barangay[1], parents)
            saw_ambiguous = saw_ambiguous or ambiguous
            if barangay_code:
                name_claims.append(
                    _Claim(
                        "barangay",
                        barangay[0],
                        barangay[1],
                        barangay_code,
                        "admin_name_hierarchy",
                    )
                )

        if not name_claims:
            return PayloadResolution(
                match=None,
                reason="ambiguous" if saw_ambiguous else "no_match",
            )
        return self._finish_claims(name_claims, name_mode=True)

    def _finish_claims(self, claims: list[_Claim], *, name_mode: bool) -> PayloadResolution:
        """Choose the deepest internally consistent claim.

        A region or province claim can be stale after a PSGC reorganization
        (for example the 2024 Negros Island Region) or merely geographic context
        for an independent city, so it does not invalidate a deeper city or
        barangay code. A conflicting city/district claim does: the deeper name
        may have matched a same-named place elsewhere, so resolution drops back
        to the city. Two different claims at the same depth and level stay a
        conflict.
        """

        ordered = sorted(claims, key=lambda claim: self.depth(claim.code), reverse=True)
        while ordered:
            primary = ordered[0]
            primary_depth = self.depth(primary.code)
            accepted = [primary]
            restart: int | None = None
            for index, claim in enumerate(ordered[1:], start=1):
                if claim.code == primary.code:
                    accepted.append(claim)
                    continue
                claim_depth = self.depth(claim.code)
                if self.is_ancestor(claim.code, primary.code):
                    accepted.append(claim)
                    continue
                if claim_depth == primary_depth:
                    if claim.level == primary.level:
                        return PayloadResolution(match=None, reason="conflict")
                    # An independent city and its geographic province share a
                    # depth. Prefer the more specific level and drop the other.
                    if _LEVEL_RANK.get(claim.level, 0) > _LEVEL_RANK.get(primary.level, 0):
                        restart = index
                        break
                    continue
                if claim_depth >= 2:
                    restart = index
                    break
                # Region/province context that the current PSGC release has
                # superseded or that does not contain an independent city.
            if restart is None:
                fields = {claim.field for claim in accepted} if name_mode else {primary.field}
                return PayloadResolution(
                    match=PsgcMatch(
                        psgc_code=primary.code,
                        method=primary.method,
                        source_field="+".join(sorted(fields)),
                        raw_value=primary.raw,
                    ),
                    reason="resolved",
                )
            ordered = ordered[restart:]
        return PayloadResolution(match=None, reason="conflict")


@dataclass(frozen=True)
class PsgcMatch:
    psgc_code: str
    method: str
    source_field: str
    raw_value: str


@dataclass(frozen=True)
class PayloadResolution:
    match: PsgcMatch | None
    reason: str


@dataclass(frozen=True)
class SourcedMatch:
    match: PsgcMatch
    source_record_id: uuid.UUID
    dataset_slug: str


@dataclass(frozen=True)
class LinkedPayload:
    record_id: uuid.UUID
    dataset_slug: str
    payload: dict[str, Any]


@dataclass
class PsgcFillStats:
    examined: int = 0
    resolved: int = 0
    unresolved: int = 0
    ambiguous: int = 0
    conflict: int = 0
    geography_release: str | None = None
    by_method: Counter[str] = field(default_factory=Counter)
    by_dataset: Counter[str] = field(default_factory=Counter)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_rows: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "version": RESOLUTION_VERSION,
            "geography_release": self.geography_release,
            "examined": self.examined,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "ambiguous": self.ambiguous,
            "conflict": self.conflict,
            "by_method": dict(sorted(self.by_method.items())),
            "by_dataset": dict(sorted(self.by_dataset.items())),
        }
        if include_rows:
            payload["fills"] = self.rows
        return payload


def _apply_resolution(
    session: Session,
    location: FacilityLocation,
    sourced: SourcedMatch,
    existing_claims: set[tuple[uuid.UUID, uuid.UUID, str]],
) -> bool:
    """Write one resolution unless the location already has a non-null code."""

    if location.psgc_code is not None:
        return False
    match = sourced.match
    location.psgc_code = match.psgc_code
    claim = (location.facility_id, sourced.source_record_id, match.psgc_code)
    if claim not in existing_claims:
        existing_claims.add(claim)
        session.add(
            AttributeAssertion(
                facility_id=location.facility_id,
                source_record_id=sourced.source_record_id,
                attribute_name="psgc_code",
                source_field=match.source_field,
                raw_value=match.raw_value,
                normalized_value=match.psgc_code,
                transformation_version=RESOLUTION_VERSION,
                review_status="derived",
            )
        )
    return True


def _linked_payloads(
    session: Session,
    locations: list[FacilityLocation],
) -> dict[uuid.UUID, list[LinkedPayload]]:
    """Payloads linked to the target facilities, own source record first."""

    facility_ids = [location.facility_id for location in locations]
    payloads: dict[uuid.UUID, list[LinkedPayload]] = defaultdict(list)
    rows = session.execute(
        select(
            FacilitySourceLink.facility_id,
            SourceRecord.id,
            SourceRecord.raw_payload,
            Dataset.slug,
        )
        .join(SourceRecord, SourceRecord.id == FacilitySourceLink.source_record_id)
        .join(Release, Release.id == SourceRecord.release_id)
        .join(Dataset, Dataset.id == Release.dataset_id)
        .where(FacilitySourceLink.facility_id.in_(facility_ids))
        .order_by(
            FacilitySourceLink.facility_id,
            Release.retrieved_at.desc(),
            Dataset.slug,
            SourceRecord.source_record_key,
        )
    ).all()
    found_records: set[uuid.UUID] = set()
    for facility_id, record_id, payload, slug in rows:
        found_records.add(record_id)
        if isinstance(payload, dict):
            payloads[facility_id].append(
                LinkedPayload(record_id=record_id, dataset_slug=slug, payload=payload)
            )

    missing = {
        location.source_record_id
        for location in locations
        if location.source_record_id is not None and location.source_record_id not in found_records
    }
    if missing:
        missing_rows = session.execute(
            select(SourceRecord.id, SourceRecord.raw_payload, Dataset.slug)
            .join(Release, Release.id == SourceRecord.release_id)
            .join(Dataset, Dataset.id == Release.dataset_id)
            .where(SourceRecord.id.in_(missing))
        ).all()
        by_record = {
            record_id: LinkedPayload(record_id=record_id, dataset_slug=slug, payload=payload)
            for record_id, payload, slug in missing_rows
            if isinstance(payload, dict)
        }
        for location in locations:
            own = by_record.get(location.source_record_id) if location.source_record_id else None
            if own is not None:
                payloads[location.facility_id].insert(0, own)

    for location in locations:
        items = payloads.get(location.facility_id, [])
        if location.source_record_id is not None:
            items.sort(key=lambda item: item.record_id != location.source_record_id)
        payloads[location.facility_id] = items
    return payloads


def _choose_resolution(
    index: GeographyIndex,
    payloads: list[LinkedPayload],
) -> tuple[SourcedMatch | None, str]:
    """Choose one resolution from the location's own record, then linked records."""

    if not payloads:
        return None, "no_match"

    own = payloads[0]
    own_outcome = index.resolve_payload(own.payload)
    if own_outcome.match is not None:
        return (
            SourcedMatch(
                match=own_outcome.match,
                source_record_id=own.record_id,
                dataset_slug=own.dataset_slug,
            ),
            "resolved",
        )

    resolved: list[SourcedMatch] = []
    reasons: Counter[str] = Counter()
    for item in payloads:
        outcome = index.resolve_payload(item.payload)
        if outcome.match is not None:
            resolved.append(
                SourcedMatch(
                    match=outcome.match,
                    source_record_id=item.record_id,
                    dataset_slug=item.dataset_slug,
                )
            )
        else:
            reasons[outcome.reason] += 1

    if resolved:
        codes = {item.match.psgc_code for item in resolved}
        if len(codes) == 1:
            return resolved[0], "resolved"
        return None, "conflict"
    if reasons["conflict"]:
        return None, "conflict"
    if reasons["ambiguous"]:
        return None, "ambiguous"
    return None, "no_match"


def _latest_real_release(session: Session) -> GeographicRelease | None:
    return session.scalars(
        select(GeographicRelease)
        .where(GeographicRelease.is_synthetic.is_(False))
        .order_by(GeographicRelease.retrieved_at.desc())
    ).first()


def _target_rows(session: Session, *, batch_size: int = MAX_IDS_PER_QUERY):
    statement = (
        select(FacilityLocation, Facility.slug)
        .join(Facility, Facility.id == FacilityLocation.facility_id)
        .where(
            FacilityLocation.is_current.is_(True),
            FacilityLocation.psgc_code.is_(None),
            Facility.is_synthetic.is_(False),
        )
        .order_by(FacilityLocation.facility_id)
        .execution_options(yield_per=batch_size)
    )
    return session.execute(statement).partitions(batch_size)


def _existing_psgc_claims(session: Session) -> set[tuple[uuid.UUID, uuid.UUID, str]]:
    return {
        (facility_id, source_record_id, normalized_value)
        for facility_id, source_record_id, normalized_value in session.execute(
            select(
                AttributeAssertion.facility_id,
                AttributeAssertion.source_record_id,
                AttributeAssertion.normalized_value,
            ).where(AttributeAssertion.attribute_name == "psgc_code")
        ).all()
    }


def fill_location_psgc(
    session: Session,
    *,
    apply: bool = False,
    report_path: str | Path | None = None,
) -> PsgcFillStats:
    """Fill missing current-location PSGC codes. Without ``apply`` this is a dry run."""

    release = _latest_real_release(session)
    if release is None:
        raise ValueError("No real PSGC release is loaded; refusing to use synthetic geography.")
    units = session.scalars(
        select(AdministrativeUnit).where(AdministrativeUnit.release_id == release.id)
    ).all()
    index = GeographyIndex(units)
    stats = PsgcFillStats(geography_release=release.release_label)
    existing_claims = _existing_psgc_claims(session) if apply else set()

    for partition in _target_rows(session):
        locations = [row[0] for row in partition]
        slugs = {row[0].facility_id: row[1] for row in partition}
        payloads = _linked_payloads(session, locations)
        for location in locations:
            stats.examined += 1
            sourced, reason = _choose_resolution(index, payloads.get(location.facility_id, []))
            if sourced is None:
                if reason == "conflict":
                    stats.conflict += 1
                elif reason == "ambiguous":
                    stats.ambiguous += 1
                else:
                    stats.unresolved += 1
                continue
            stats.resolved += 1
            stats.by_method[sourced.match.method] += 1
            stats.by_dataset[sourced.dataset_slug] += 1
            stats.rows.append(
                {
                    "facility_id": str(location.facility_id),
                    "facility_slug": slugs.get(location.facility_id),
                    "psgc_code": sourced.match.psgc_code,
                    "method": sourced.match.method,
                    "source_field": sourced.match.source_field,
                    "raw_value": sourced.match.raw_value,
                    "source_record_id": str(sourced.source_record_id),
                    "dataset": sourced.dataset_slug,
                }
            )
            if apply:
                _apply_resolution(session, location, sourced, existing_claims)
        if apply:
            session.flush()

    if apply:
        session.commit()
    if report_path is not None:
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(stats.to_dict(), indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    return stats
