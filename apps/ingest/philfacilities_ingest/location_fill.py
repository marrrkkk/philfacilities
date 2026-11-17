"""Deterministic OSM coordinate gap-fill for unlocated facilities.

data.md §10.6: when a facility has no point, the approved OSM/HOT/Geofabrik
snapshot may supply a *map location*. The match must be deterministic: the same
normalized name, the same city/municipality, a compatible category, and a unique
candidate. The OSM point never overwrites an official coordinate and never
changes the facility's source of record.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from philfacilities_api.models import (
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    Release,
    SourceRecord,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .matching import normalize_name

COMMUNITY_METHOD = "openstreetmap_match"
COMMUNITY_PRECISION = "map_geocoded"
COMMUNITY_REVIEW = "community_fallback"
OSM_AUTHORITY = "community"


@dataclass
class LocationFillResult:
    unlocated: int = 0
    candidates: int = 0
    matched: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    already_filled: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)
    unlocated_by_category_region: dict[str, int] = field(default_factory=dict)
    unresolved_by_category_region: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "unlocated": self.unlocated,
            "candidates": self.candidates,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "already_filled": self.already_filled,
            "unlocated_by_category_region": dict(sorted(self.unlocated_by_category_region.items())),
            "unresolved_by_category_region": dict(
                sorted(self.unresolved_by_category_region.items())
            ),
            "fills": self.rows,
        }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coordinate(payload: dict[str, Any]) -> tuple[float | None, float | None]:
    for lat_key, lon_key in (
        ("_bbox_center_latitude", "_bbox_center_longitude"),
        ("latitude", "longitude"),
        ("lat", "lon"),
    ):
        lat = payload.get(lat_key)
        lon = payload.get(lon_key)
        try:
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except (TypeError, ValueError):
            continue
    return None, None


def _psgc_from_payload(payload: dict[str, Any]) -> str | None:
    """Return a 10-digit city/municipality-shaped code from an OSM/admin pcode.

    HOT/OSM P-codes are country-prefixed and may be 9 or 10 digits after the
    prefix. The first seven digits identify the city/municipality in the
    platform's 10-digit PSGC shape; province-only codes cannot identify a city
    and are therefore not used for this deterministic match.
    """

    for key in ("adm4_pcode", "adm3_pcode"):
        value = _text(payload.get(key))
        if not value:
            continue
        digits = value.removeprefix("PH").strip()
        if not digits.isdigit():
            digits = "".join(character for character in value if character.isdigit())
        if len(digits) >= 7:
            return digits[:7] + "000"
    return None


def _city_prefix(psgc: str | None) -> str | None:
    if not psgc or not psgc.isdigit() or len(psgc) < 7:
        return None
    return psgc[:7]


def _city_aliases(name: str | None) -> set[str]:
    """Normalized city names plus the common ``City of X``/``X City`` aliases."""

    normalized = normalize_name(name)
    if not normalized:
        return set()
    aliases = {normalized}
    for prefix in ("city of ", "municipality of "):
        if normalized.startswith(prefix):
            aliases.add(normalized[len(prefix) :].strip())
    for suffix in (" city", " municipality"):
        if normalized.endswith(suffix):
            aliases.add(normalized[: -len(suffix)].strip())
    return {alias for alias in aliases if alias}


class _CityResolver:
    """Resolve a source city/province label to a city PSGC prefix.

    Resolution is conservative: an alias must map to one city/municipality, or
    the province must disambiguate it. Free-text address tokens are accepted
    only when exactly one city/municipality name appears in the address.
    """

    def __init__(self, session: Session) -> None:
        from philfacilities_api.models import AdministrativeUnit, GeographicRelease

        latest = session.scalars(
            select(GeographicRelease)
            .where(GeographicRelease.is_synthetic.is_(False))
            .order_by(GeographicRelease.retrieved_at.desc())
        ).first()
        if latest is None:
            # Never fall back to all units: the only releases present may be
            # synthetic demo geography, which must not geocode real facilities.
            units = []
        else:
            units = session.scalars(
                select(AdministrativeUnit).where(AdministrativeUnit.release_id == latest.id)
            ).all()
        provinces = {
            unit.psgc_code: normalize_name(unit.name)
            for unit in units
            if unit.geographic_level == "province"
        }
        self.by_name: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.by_city: dict[str, set[str]] = defaultdict(set)
        self.by_alias: dict[str, set[str]] = defaultdict(set)
        self.by_alias_province: dict[tuple[str, str], set[str]] = defaultdict(set)
        for unit in units:
            if unit.geographic_level not in ("city", "municipality", "city_municipality"):
                continue
            city = normalize_name(unit.name)
            province = provinces.get(unit.parent_psgc_code or "")
            prefix = unit.psgc_code[:7]
            if province:
                self.by_name[(city, province)].add(prefix)
            self.by_city[city].add(prefix)
            for alias in _city_aliases(unit.name):
                self.by_alias[alias].add(prefix)
                if province:
                    self.by_alias_province[(alias, province)].add(prefix)
        self.max_alias_words = max((len(alias.split()) for alias in self.by_alias), default=1)

    def resolve(self, payload: dict[str, Any]) -> str | None:
        return self.resolve_fields(
            _text(payload.get("addr_city")),
            _text(payload.get("addr_province")),
        )

    def resolve_fields(self, city: str | None, province: str | None = None) -> str | None:
        if not city:
            return None
        province_name = normalize_name(province)
        candidates: set[str] = set()
        for alias in _city_aliases(city):
            if province_name:
                candidates |= self.by_alias_province.get((alias, province_name), set())
            if not candidates:
                candidates |= self.by_alias.get(alias, set())
        return next(iter(candidates)) if len(candidates) == 1 else None

    def resolve_address(self, text: str | None, province: str | None = None) -> str | None:
        normalized = normalize_name(text)
        if not normalized:
            return None
        words = normalized.split()
        province_name = normalize_name(province)
        candidates: set[str] = set()
        seen_aliases: set[str] = set()
        for size in range(1, min(self.max_alias_words, 4) + 1):
            for index in range(len(words) - size + 1):
                alias = " ".join(words[index : index + size])
                if alias not in self.by_alias or alias in seen_aliases:
                    continue
                seen_aliases.add(alias)
                if province_name:
                    matches = self.by_alias_province.get((alias, province_name))
                    if matches:
                        candidates |= matches
                        continue
                candidates |= self.by_alias[alias]
        return next(iter(candidates)) if len(candidates) == 1 else None


def _osm_candidates(session: Session, resolver: _CityResolver) -> list[dict[str, Any]]:
    rows = session.execute(
        select(SourceRecord, Release, Dataset)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(
            Dataset.authority_level == OSM_AUTHORITY,
            Dataset.slug.like("osm-%"),
        )
    ).all()
    candidates: list[dict[str, Any]] = []
    for record, release, dataset in rows:
        payload = record.raw_payload or {}
        name = _text(payload.get("name"))
        if not name:
            continue
        latitude, longitude = _coordinate(payload)
        if latitude is None or longitude is None:
            continue
        psgc = _psgc_from_payload(payload)
        city_prefix = _city_prefix(psgc) or resolver.resolve(payload)
        if not city_prefix:
            continue
        candidates.append(
            {
                "record_id": record.id,
                "osm_id": _text(payload.get("id")),
                "name": name,
                "normalized_name": normalize_name(name),
                "city_prefix": city_prefix,
                "psgc": psgc,
                "latitude": latitude,
                "longitude": longitude,
                "dataset": dataset.slug,
                "release_id": release.id,
                "snapshot": release.retrieved_at.date().isoformat()
                if release.retrieved_at
                else None,
                "address": _text(payload.get("addr_full"))
                or _text((payload.get("tags") or {}).get("addr:full")),
            }
        )
    return candidates


def _target_facilities(session: Session) -> list[tuple[Facility, FacilityLocation]]:
    """Facilities with no current point but with PSGC/address evidence."""

    rows = session.execute(
        select(Facility, FacilityLocation)
        .join(FacilityLocation, FacilityLocation.facility_id == Facility.id)
        .where(
            FacilityLocation.is_current.is_(True),
            FacilityLocation.latitude.is_(None),
            Facility.is_synthetic.is_(False),
            (FacilityLocation.psgc_code.is_not(None))
            | (FacilityLocation.address_text.is_not(None)),
        )
    ).all()
    return [(facility, location) for facility, location in rows]


_CITY_PAYLOAD_KEYS = (
    "municipality",
    "city",
    "city_municipality",
    "municipality_name",
    "city_name",
    "addr_city",
)
_PROVINCE_PAYLOAD_KEYS = (
    "province",
    "province_name",
    "addr_province",
)


def _payload_city_province(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    city = next(
        (_text(payload.get(key)) for key in _CITY_PAYLOAD_KEYS if _text(payload.get(key))),
        None,
    )
    province = next(
        (_text(payload.get(key)) for key in _PROVINCE_PAYLOAD_KEYS if _text(payload.get(key))),
        None,
    )
    return city, province


def _target_payloads(
    session: Session | None, facility_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Raw source payloads linked to the target facilities, in bounded batches."""

    if session is None or not facility_ids:
        return {}
    payloads: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    ids = list(facility_ids)
    for start in range(0, len(ids), 5000):
        chunk = ids[start : start + 5000]
        rows = session.execute(
            select(FacilitySourceLink.facility_id, SourceRecord.raw_payload)
            .join(SourceRecord, SourceRecord.id == FacilitySourceLink.source_record_id)
            .where(FacilitySourceLink.facility_id.in_(chunk))
        ).all()
        for facility_id, payload in rows:
            if isinstance(payload, dict):
                payloads[facility_id].append(payload)
    return payloads


def _resolve_target_city(
    location: FacilityLocation,
    payloads: list[dict[str, Any]],
    resolver: Any,
) -> tuple[str | None, str | None]:
    """Resolve the target city prefix from source PSGC, source fields or address.

    The returned evidence is descriptive; a resolved city is a matching key, not
    a new source coordinate or an asserted PSGC value.
    """

    prefix = _city_prefix(location.psgc_code)
    if prefix:
        return prefix, f"source PSGC {location.psgc_code}"
    resolve_fields = getattr(resolver, "resolve_fields", None)
    if resolve_fields is not None:
        for payload in payloads:
            city, province = _payload_city_province(payload)
            if not city:
                continue
            prefix = resolve_fields(city, province)
            if prefix:
                return prefix, f"source city/municipality {city!r}"
    resolve_address = getattr(resolver, "resolve_address", None)
    if resolve_address is not None and location.address_text:
        prefix = resolve_address(location.address_text)
        if prefix:
            return prefix, "exact city/municipality name in source address"
    return None, None


def _unresolved_bucket(
    facility: Facility,
    location: FacilityLocation,
    city_prefix: str | None = None,
) -> str:
    category = facility.facility_type or "UNKNOWN"
    psgc = location.psgc_code
    region = f"{psgc[:2]}00000000" if psgc and psgc[:2].isdigit() else "UNKNOWN"
    if region == "UNKNOWN" and city_prefix and city_prefix[:2].isdigit():
        region = f"{city_prefix[:2]}00000000"
    return f"{category}|{region}"


def _already_filled(session: Session, facility_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not facility_ids:
        return set()
    filled: set[uuid.UUID] = set()
    ids = list(facility_ids)
    # PostgreSQL accepts at most 65535 bind parameters per statement. The
    # target set can exceed that on a national rebuild, so query in bounded
    # batches instead of sending every id in one ``IN`` clause.
    for start in range(0, len(ids), 5000):
        chunk = ids[start : start + 5000]
        filled.update(
            session.scalars(
                select(FacilityLocation.facility_id).where(
                    FacilityLocation.facility_id.in_(chunk),
                    FacilityLocation.is_current.is_(True),
                    FacilityLocation.method == COMMUNITY_METHOD,
                )
            )
        )
    return filled


def fill_locations_from_osm(
    session: Session,
    *,
    apply: bool = False,
    report_path: str | Path | None = None,
) -> LocationFillResult:
    """Run the deterministic gap-fill. Without ``apply`` this is a dry run."""

    from geoalchemy2.elements import WKTElement

    result = LocationFillResult()
    resolver = _CityResolver(session)
    candidates = _osm_candidates(session, resolver)
    result.candidates = len(candidates)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate["normalized_name"], candidate["city_prefix"])].append(candidate)

    targets = _target_facilities(session)
    result.unlocated = len(targets)
    target_ids = {facility.id for facility, _ in targets}
    filled_ids = _already_filled(session, target_ids)
    result.already_filled = len(filled_ids)
    payloads = _target_payloads(session, target_ids)

    for facility, location in targets:
        if facility.id in filled_ids:
            bucket = _unresolved_bucket(facility, location)
            result.unlocated_by_category_region[bucket] = (
                result.unlocated_by_category_region.get(bucket, 0) + 1
            )
            continue
        city_prefix, city_evidence = _resolve_target_city(
            location, payloads.get(facility.id, []), resolver
        )
        bucket = _unresolved_bucket(facility, location, city_prefix)
        result.unlocated_by_category_region[bucket] = (
            result.unlocated_by_category_region.get(bucket, 0) + 1
        )
        if not city_prefix:
            result.unmatched += 1
            result.unresolved_by_category_region[bucket] = (
                result.unresolved_by_category_region.get(bucket, 0) + 1
            )
            continue
        matches = grouped.get((normalize_name(facility.display_name), city_prefix), [])
        # Keep only points inside the Philippine plausibility box.
        matches = [
            item
            for item in matches
            if 4.0 <= item["latitude"] <= 22.0 and 115.0 <= item["longitude"] <= 128.0
        ]
        if len(matches) > 1:
            result.ambiguous += 1
            result.unresolved_by_category_region[bucket] = (
                result.unresolved_by_category_region.get(bucket, 0) + 1
            )
            continue
        if not matches:
            result.unmatched += 1
            result.unresolved_by_category_region[bucket] = (
                result.unresolved_by_category_region.get(bucket, 0) + 1
            )
            continue
        match = matches[0]
        result.matched += 1
        result.rows.append(
            {
                "facility_id": str(facility.id),
                "facility_slug": facility.slug,
                "facility_name": facility.display_name,
                "facility_type": facility.facility_type,
                "psgc_code": location.psgc_code,
                "address_text": location.address_text,
                "osm_id": match["osm_id"],
                "osm_name": match["name"],
                "osm_dataset": match["dataset"],
                "osm_snapshot": match["snapshot"],
                "osm_psgc": match.get("psgc"),
                "match_method": COMMUNITY_METHOD,
                "match_evidence": (
                    f"exact normalized name + city/municipality {city_prefix} "
                    f"({city_evidence}); unique OSM candidate"
                ),
                "city_evidence": city_evidence,
                "precision": COMMUNITY_PRECISION,
                "latitude": match["latitude"],
                "longitude": match["longitude"],
                "community_fallback": True,
                "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
            }
        )
        if not apply:
            continue
        location.is_current = False
        location.valid_to = date.today()
        session.add(
            FacilityLocation(
                facility_id=facility.id,
                source_record_id=match["record_id"],
                geom=WKTElement(f"POINT({match['longitude']} {match['latitude']})", srid=4326),
                latitude=match["latitude"],
                longitude=match["longitude"],
                precision=COMMUNITY_PRECISION,
                method=COMMUNITY_METHOD,
                address_text=location.address_text,
                postal_code=location.postal_code,
                # The OSM feature's own P-code is community evidence; do not
                # promote a derived city prefix to an asserted PSGC value.
                psgc_code=match.get("psgc") or location.psgc_code,
                review_status=COMMUNITY_REVIEW,
                is_current=True,
            )
        )

    if apply:
        session.commit()
    if report_path is not None:
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(result.to_dict(), indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    return result
