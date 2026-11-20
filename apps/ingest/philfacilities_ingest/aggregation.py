"""General evidence-based facility aggregation for every facility type.

The exact matcher asks whether two rows have the same name and PSGC. Real
sources describe the same place with slightly different names (``St.`` vs
``Saint``, with or without ``Inc.``) and often have no PSGC at all. This module
scores independent identity dimensions instead:

* a canonical name key and a conservative name similarity;
* city, barangay, address and coordinate agreement;
* official identifiers already stored in school, health or utility profiles;
* source authority and agency independence.

Only a mutually compatible clique of strong pairs is merged automatically: every
pair must be eligible, and at least one must share an official identifier or
strong location evidence. Anything ambiguous becomes a pending candidate for
review. The fusion module remains responsible for combining attributes and
retaining every source claim on the surviving facility.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from philfacilities_api.models import (
    AdministrativeUnit,
    Agency,
    Dataset,
    Facility,
    FacilityChangeEvent,
    FacilityLocation,
    FacilitySourceLink,
    GeographicRelease,
    HealthProfile,
    MatchCandidate,
    Release,
    SchoolProfile,
    SourceRecord,
    UtilityProfile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .identity import (
    address_overlap,
    address_tokens,
    deped_prefixed_school_id,
    facility_name_key,
    name_similarity,
    normalize_name,
    psgc_barangay_code,
    psgc_city_code,
    school_name_key,
)
from .matching import (
    MatchingError,
    _current_locations,
    _distance_m,
    _facility_snapshot,
    _subtypes_compatible,
    candidate_key,
    merge_match_candidate,
)

GENERAL_MATCH_METHOD = "facility_identity_evidence_v1"
ALGORITHM_VERSION = "2"
AUTO_REVIEWER = "system:facility-identity-evidence"
AUTO_MIN_NAME_SCORE = 0.9
AUTO_MIN_LOCATION_SCORE = 0.9
# Two rows from the same agency with the exact same name are duplicates only
# when they describe the same point, not merely the same city or barangay.
# A source can legitimately publish several branches of one office in a city.
SAME_AGENCY_POINT_DISTANCE_M = 50.0
CITY_ONLY_LOCATION_SCORE = 0.6
MAX_CLUSTER_SIZE = 8
CONFLICTING_POINT_DISTANCE_M = 1_000.0
# Small name groups are compared exhaustively. Bucketing is only needed to keep
# prolific generic names (pharmacies, barangay halls) tractable.
ALL_PAIRS_GROUP_MAX = 64
# A ~1.1 km cell plus its neighbours keeps co-located rows comparable even when
# two sources assign them to different cities or barangays.
CELL_BUCKET_DEGREES = 0.01
# Reordered connectors ("Hospital and Maternity" vs "Maternity Hospital") are
# the same name. Dropping only connector words keeps service-unit words such as
# "Birthing Facility" intact so those remain distinct names.
NAME_VARIANT_CONNECTORS = frozenset({"and", "of", "the"})
# Cross-type duplicates are only proposed as review candidates, never merged
# automatically. The point threshold is deliberately tighter than the same-type
# gate because the type evidence disagrees.
CROSS_TYPE_MAX_DISTANCE_M = 50.0


@dataclass
class _AdminIndex:
    city_alias_to_codes: dict[str, set[str]]
    city_names: dict[str, str]
    barangay_names: dict[str, str]
    administrative_tokens: frozenset[str]
    # Province/region-scoped city aliases resolve duplicate municipality names
    # (for example the several "San Isidro" municipalities).
    city_alias_to_parent_alias_codes: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    # Barangay names repeat across the country, so resolution is scoped by the
    # parent city/municipality code.
    barangay_alias_to_parent_codes: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    city_region_codes: dict[str, str] = field(default_factory=dict)
    region_names: dict[str, str] = field(default_factory=dict)
    region_alias_to_codes: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class _Ref:
    facility: Facility
    location: FacilityLocation
    agency_codes: set[str] = field(default_factory=set)
    dataset_slugs: set[str] = field(default_factory=set)
    official: bool = False
    # (source_record_id, agency_code, dataset_slug, authority_level) — plain
    # values keep the whole-registry scan from loading every source record,
    # release and dataset as ORM instances.
    links: list[tuple[uuid.UUID, str, str, str]] = field(default_factory=list)
    name_key: str = ""
    token_key: str = ""
    specific: bool = False
    generic: bool = False
    city_code: str | None = None
    barangay_code: str | None = None
    city_name: str | None = None
    barangay_name: str | None = None
    # True when the code was resolved from the source's municipality/barangay
    # text rather than supplied as a PSGC code. Matching evidence records this
    # distinction; it is never written back as a published location code.
    city_code_derived: bool = False
    barangay_code_derived: bool = False
    deped_ids: set[str] = field(default_factory=set)
    doh_ids: set[str] = field(default_factory=set)
    doe_ids: set[str] = field(default_factory=set)

    @property
    def id(self) -> uuid.UUID:
        return self.facility.id


@dataclass
class _Pair:
    left: _Ref
    right: _Ref
    name_score: float
    name_reason: str
    location_score: float
    location_reason: str
    distance_m: float | None
    shared_address_tokens: int
    same_city: bool
    same_barangay: bool
    conflicting_location: bool
    conflicting_ids: bool
    shared_ids: bool
    different_agency: bool
    auto_eligible: bool
    note: str
    cross_type: bool = False


_SAINT_ALIASES = {"sta": "santa", "sto": "santo", "st": "saint"}

# Established alternate spellings used by DepEd in its administrative fields.
# These name the same city; they do not merge two different administrative
# units.
_CITY_SPELLING_ALIASES = {
    "baliuag": "baliwag",
    "kalookan": "caloocan",
    "ozamis": "ozamiz",
}

_REGION_SHORT_ALIASES = {
    "ncr": "national capital region",
    "car": "cordillera administrative region",
    "barmm": "bangsamoro autonomous region in muslim mindanao",
}


def _city_aliases(name: str) -> set[str]:
    """Return comparable aliases for a city/municipality name.

    DepEd publishes forms such as ``SURIGAO CITY (Capital)``,
    ``CITY MALAYBALAY (Capital)`` and ``STA. RITA``. Parenthetical qualifiers
    are administrative notes (or former names), not part of the name, and saint
    abbreviations are expanded so they match the official PSGC spelling.
    """

    normalized = normalize_name(re.sub(r"\([^)]*\)", " ", name or ""))
    if not normalized:
        return set()
    tokens = [
        _CITY_SPELLING_ALIASES.get(token, _SAINT_ALIASES.get(token, token))
        for token in normalized.split()
        if token not in {"capital", "poblacion"}
    ]
    normalized = " ".join(tokens)
    aliases = {normalized}
    for prefix in ("city of ", "municipality of "):
        if normalized.startswith(prefix):
            base = normalized[len(prefix) :].strip()
            aliases.add(base)
            # Addresses usually write "Lucena City" even when the official
            # name is "City of Lucena".
            aliases.add(f"{base} city" if prefix == "city of " else f"{base} municipality")
    if normalized.startswith("city ") and not normalized.startswith("city of "):
        base = normalized[len("city ") :].strip()
        aliases.add(base)
        aliases.add(f"{base} city")
    for suffix in (" city", " municipality"):
        if normalized.endswith(suffix):
            aliases.add(normalized[: -len(suffix)].strip())
    return {alias for alias in aliases if alias}


def _load_admin_index(session: Session) -> _AdminIndex:
    latest_release_id = session.scalar(
        select(GeographicRelease.id).order_by(GeographicRelease.retrieved_at.desc()).limit(1)
    )
    if latest_release_id is None:
        return _AdminIndex({}, {}, {}, set())
    units = list(
        session.scalars(
            select(AdministrativeUnit).where(AdministrativeUnit.release_id == latest_release_id)
        ).all()
    )
    by_code = {unit.psgc_code: unit for unit in units}
    city_names: dict[str, str] = {}
    barangay_names: dict[str, str] = {}
    region_names: dict[str, str] = {}
    alias_codes: dict[str, set[str]] = defaultdict(set)
    parent_alias_codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    barangay_alias_codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    city_region_codes: dict[str, str] = {}
    region_alias_codes: dict[str, set[str]] = defaultdict(set)
    tokens: set[str] = set()
    for unit in units:
        name = normalize_name(unit.name)
        if not name:
            continue
        tokens.update(name.split())
        if unit.geographic_level == "region":
            region_names[unit.psgc_code] = unit.name
            for alias in _city_aliases(unit.name):
                region_alias_codes[alias].add(unit.psgc_code)
            for short, long_name in _REGION_SHORT_ALIASES.items():
                if long_name in normalize_name(unit.name):
                    region_alias_codes[short].add(unit.psgc_code)

    for unit in units:
        if unit.geographic_level == "municipality":
            city_names[unit.psgc_code] = unit.name
            aliases = _city_aliases(unit.name)
            parent = by_code.get(unit.parent_psgc_code)
            parent_aliases = _city_aliases(parent.name) if parent else set()
            region_code: str | None = None
            if parent is not None:
                if parent.geographic_level == "region":
                    region_code = parent.psgc_code
                elif parent.parent_psgc_code:
                    grandparent = by_code.get(parent.parent_psgc_code)
                    if grandparent is not None and grandparent.geographic_level == "region":
                        region_code = grandparent.psgc_code
            if region_code:
                city_region_codes[unit.psgc_code] = region_code
                parent_aliases |= _city_aliases(region_names.get(region_code, ""))
            for alias in aliases:
                alias_codes[alias].add(unit.psgc_code)
                tokens.update(alias.split())
                for parent_alias in parent_aliases:
                    parent_alias_codes[(alias, parent_alias)].add(unit.psgc_code)
        elif unit.geographic_level == "barangay":
            barangay_names[unit.psgc_code] = unit.name
            if unit.parent_psgc_code:
                for alias in _barangay_aliases(unit.name):
                    barangay_alias_codes[(alias, unit.parent_psgc_code)].add(unit.psgc_code)
                    tokens.update(alias.split())
    return _AdminIndex(
        city_alias_to_codes={alias: codes for alias, codes in alias_codes.items() if codes},
        city_names=city_names,
        barangay_names=barangay_names,
        administrative_tokens=frozenset(tokens),
        city_alias_to_parent_alias_codes={
            key: codes for key, codes in parent_alias_codes.items() if codes
        },
        barangay_alias_to_parent_codes={
            key: codes for key, codes in barangay_alias_codes.items() if codes
        },
        city_region_codes=city_region_codes,
        region_names=region_names,
        region_alias_to_codes={
            alias: codes for alias, codes in region_alias_codes.items() if codes
        },
    )


_SUB_CITY_PREFIXES = frozenset(
    {
        "barangay",
        "blk",
        "block",
        "bldg",
        "brgy",
        "building",
        "floor",
        "lot",
        "purok",
        "sitio",
        "unit",
        "zone",
    }
)


def _city_codes_in_text(text: str, admin: _AdminIndex) -> set[str]:
    """Resolve the longest city/municipality alias mentioned in ``text``."""

    tokens = normalize_name(text).split()
    for size in (4, 3, 2, 1):
        codes: set[str] = set()
        for index in range(len(tokens) - size + 1):
            codes.update(
                admin.city_alias_to_codes.get(" ".join(tokens[index : index + size]), set())
            )
        if codes:
            return codes
    return set()


def _city_from_address(address: str | None, admin: _AdminIndex) -> str | None:
    """Resolve a city/municipality from a free-text address.

    Philippine addresses often append the province after the city. A province
    can share its name with an unrelated city (``Lucena City, Quezon`` versus
    ``Quezon City``), so a whole-string token match is ambiguous. Prefer the
    address segment that explicitly says city/municipality, then the first
    segment that is not a barangay/street fragment, and never guess between
    genuinely ambiguous bare names.
    """

    if not address:
        return None
    segments = [segment for segment in re.split(r"[,;]", address) if normalize_name(segment)]
    for segment in segments:
        tokens = set(normalize_name(segment).split())
        if not tokens & {"city", "municipality"}:
            continue
        codes = _city_codes_in_text(segment, admin)
        if len(codes) == 1:
            return next(iter(codes))
        if len(codes) > 1:
            return None
    for segment in segments:
        tokens = normalize_name(segment).split()
        if tokens and tokens[0] in _SUB_CITY_PREFIXES:
            continue
        codes = _city_codes_in_text(segment, admin)
        if len(codes) == 1:
            return next(iter(codes))
        if len(codes) > 1:
            return None
    codes = _city_codes_in_text(address, admin)
    return next(iter(codes)) if len(codes) == 1 else None


_BARANGAY_TOKEN_ALIASES = {
    "bry": "bgy",
    "brgy": "bgy",
    "bgy": "bgy",
    "pob": "poblacion",
    "pobl": "poblacion",
}


def _barangay_aliases(name: str | None) -> set[str]:
    """Return comparable aliases for a barangay name.

    DepEd writes ``BRY. NO. 18, SAN QUIRINO (POB.)`` while PSGC writes
    ``Bgy. No. 18, San Quirino (Pob.)``. Abbreviations and saint spellings are
    folded, but the barangay-specific tokens (``Poblacion``) are preserved,
    unlike the city aliases where they are administrative noise.
    """

    normalized = normalize_name(name)
    if not normalized:
        return set()
    tokens = [
        _BARANGAY_TOKEN_ALIASES.get(token, _SAINT_ALIASES.get(token, token))
        for token in normalized.split()
    ]
    aliases = {" ".join(tokens)}
    if tokens and tokens[0] == "bgy":
        aliases.add(" ".join(tokens[1:]))
    return {alias for alias in aliases if alias}


def _resolve_city_code(
    admin: _AdminIndex,
    *,
    municipality: str | None,
    division: str | None = None,
    region: str | None = None,
) -> str | None:
    """Resolve a DepEd municipality name to one PSGC city/municipality code.

    The municipality text is matched against PSGC names, then scoped by the
    DepEd division and, as a last resort, the region. Only a unique result is
    returned; an ambiguous name is left unresolved rather than guessed.
    """

    aliases = _city_aliases(municipality or "")
    if not aliases:
        return None
    codes: set[str] = set()
    for alias in aliases:
        codes.update(admin.city_alias_to_codes.get(alias, set()))
    if len(codes) == 1:
        return next(iter(codes))
    hints = [division or ""]
    hints.extend(part.strip() for part in re.split(r"[,/]", division or "") if part.strip())
    for hint in hints:
        for alias in aliases:
            for parent_alias in _city_aliases(hint):
                scoped = admin.city_alias_to_parent_alias_codes.get((alias, parent_alias), set())
                if len(scoped) == 1:
                    return next(iter(scoped))
    # A source that writes "CITY" is describing a city, so a same-named
    # municipality is a different administrative unit. This resolves names
    # such as "BACOLOD CITY" when the city is administratively independent and
    # its province hint no longer matches a reorganised region.
    normalized_municipality = normalize_name(re.sub(r"\([^)]*\)", " ", municipality or ""))
    if " city" in f" {normalized_municipality}" or normalized_municipality.startswith("city "):
        city_codes = {
            code
            for code in codes
            if "city" in normalize_name(admin.city_names.get(code, "")).split()
            or normalize_name(admin.city_names.get(code, "")).startswith("city of ")
        }
        if len(city_codes) == 1:
            return next(iter(city_codes))
    if len(codes) > 1 and region:
        region_codes: set[str] = set()
        for alias in _city_aliases(region):
            region_codes.update(admin.region_alias_to_codes.get(alias, set()))
        regional = {code for code in codes if admin.city_region_codes.get(code) in region_codes}
        if len(regional) == 1:
            return next(iter(regional))
    return None


def _resolve_barangay_code(
    admin: _AdminIndex,
    barangay: str | None,
    city_code: str | None,
) -> str | None:
    """Resolve a barangay name inside one city/municipality to a PSGC code."""

    if not barangay or not city_code:
        return None
    codes: set[str] = set()
    for alias in _barangay_aliases(barangay):
        codes.update(admin.barangay_alias_to_parent_codes.get((alias, city_code), set()))
    return next(iter(codes)) if len(codes) == 1 else None


def _mentions_admin_name(address: str | None, name: str | None) -> bool:
    normalized_address = normalize_name(address)
    normalized_name = normalize_name(name)
    if not normalized_address or not normalized_name:
        return False
    return f" {normalized_name} " in f" {normalized_address} "


def _load_structured_school_admin(
    session: Session,
    facility_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[str | None, str | None, str | None, str | None]]:
    """Load DepEd municipality/division/region/barangay text for facilities.

    The EBEIS masterlist location only carries a free-text address. Its detail
    release publishes the administrative names as separate fields, which is the
    evidence needed to resolve a DepEd-only facility to a PSGC city and
    barangay. Values are used only for matching and are never written back to
    the canonical location.
    """

    result: dict[uuid.UUID, tuple[str | None, str | None, str | None, str | None]] = {}
    if not facility_ids:
        return result
    payload = SourceRecord.raw_payload
    for chunk in _chunks(facility_ids):
        rows = session.execute(
            select(
                FacilitySourceLink.facility_id,
                payload["municipality"].astext,
                payload["division"].astext,
                payload["region"].astext,
                payload["barangay"].astext,
            )
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .where(
                Dataset.slug == "deped-masterlist-sy2020-2021-detail",
                FacilitySourceLink.facility_id.in_(chunk),
            )
            .order_by(Release.retrieved_at.desc())
        ).all()
        for facility_id, municipality, division, region, barangay in rows:
            actual = facility_id
            if actual in result:
                continue
            result[actual] = (municipality, division, region, barangay)
    return result


def _load_refs(
    session: Session,
    admin: _AdminIndex,
    *,
    include_synthetic: bool,
    facility_type: str | None = None,
) -> dict[uuid.UUID, _Ref]:
    query = (
        select(
            FacilitySourceLink.facility_id,
            FacilitySourceLink.source_record_id,
            Agency.short_code,
            Dataset.slug,
            Dataset.authority_level,
            Facility,
        )
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .join(Facility, FacilitySourceLink.facility_id == Facility.id)
        .where(
            Facility.publication_status == "public",
            Facility.record_status != "merged",
        )
        .order_by(Release.retrieved_at.desc(), FacilitySourceLink.created_at.desc())
    )
    if facility_type is not None:
        query = query.where(Facility.facility_type == facility_type)
    rows = session.execute(query).all()
    locations = _current_locations(session, facility_type=facility_type)
    refs: dict[uuid.UUID, _Ref] = {}
    for _facility_id, record_id, agency_code, dataset_slug, authority_level, facility in rows:
        if facility.is_synthetic and not include_synthetic:
            continue
        location = locations.get(facility.id)
        if location is None:
            continue
        if facility.id not in refs:
            name_key = (
                school_name_key(facility.display_name)
                if facility.facility_type == "school"
                else facility_name_key(facility.display_name)
            )
            refs[facility.id] = _Ref(
                facility=facility,
                location=location,
                name_key=name_key,
                token_key=" ".join(sorted(name_key.split())),
                specific=len(name_key) >= 12 and len(name_key.split()) >= 2,
                generic=normalize_name(facility.display_name) in _GENERIC_DISPLAY_NAMES,
                city_code=psgc_city_code(location.psgc_code)
                or psgc_city_code(_city_from_address(location.address_text, admin)),
                barangay_code=psgc_barangay_code(location.psgc_code),
            )
        ref = refs[facility.id]
        ref.agency_codes.add(agency_code)
        ref.dataset_slugs.add(dataset_slug)
        ref.official = ref.official or authority_level == "official"
        ref.links.append((record_id, agency_code, dataset_slug, authority_level))
        if ref.city_code and not ref.city_name:
            ref.city_name = admin.city_names.get(f"{ref.city_code}000")
        if ref.barangay_code and not ref.barangay_name:
            ref.barangay_name = admin.barangay_names.get(ref.barangay_code)
    unresolved = [
        facility_id
        for facility_id, ref in refs.items()
        if not ref.city_code or (ref.city_code and not ref.barangay_code)
    ]
    city_cache: dict[tuple[str | None, str | None, str | None], str | None] = {}
    barangay_cache: dict[tuple[str | None, str | None], str | None] = {}
    for facility_id, (
        municipality,
        division,
        region,
        barangay,
    ) in _load_structured_school_admin(session, unresolved).items():
        ref = refs.get(facility_id)
        if ref is None:
            continue
        if not ref.city_code:
            city_key = (municipality, division, region)
            if city_key not in city_cache:
                city_cache[city_key] = _resolve_city_code(
                    admin, municipality=municipality, division=division, region=region
                )
            city_code = city_cache[city_key]
            if city_code:
                ref.city_code = psgc_city_code(city_code)
                ref.city_code_derived = True
                ref.city_name = ref.city_name or admin.city_names.get(city_code)
        if not ref.barangay_code and ref.city_code:
            barangay_key = (barangay, ref.city_code)
            if barangay_key not in barangay_cache:
                barangay_cache[barangay_key] = _resolve_barangay_code(
                    admin, barangay, f"{ref.city_code}000"
                )
            barangay_code = barangay_cache[barangay_key]
            if barangay_code:
                ref.barangay_code = barangay_code
                ref.barangay_code_derived = True
                ref.barangay_name = ref.barangay_name or admin.barangay_names.get(barangay_code)
    return refs


_GENERIC_DISPLAY_NAMES = frozenset(
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
        "school",
    }
)


def _chunks(values: list[uuid.UUID], size: int = 10_000) -> list[list[uuid.UUID]]:
    """Split an IN-list into driver-safe parameter batches."""

    return [values[index : index + size] for index in range(0, len(values), size)]


def _attach_identifiers(session: Session, refs: dict[uuid.UUID, _Ref]) -> None:
    facility_ids = list(refs)
    if not facility_ids:
        return
    deped = defaultdict(set)
    for chunk in _chunks(facility_ids):
        for facility_id, school_id in session.execute(
            select(SchoolProfile.facility_id, SchoolProfile.deped_school_id).where(
                SchoolProfile.facility_id.in_(chunk),
                SchoolProfile.deped_school_id.is_not(None),
            )
        ).all():
            deped[facility_id].add(deped_prefixed_school_id(school_id) or school_id)
    doh = defaultdict(set)
    for chunk in _chunks(facility_ids):
        for facility_id, doh_id in session.execute(
            select(HealthProfile.facility_id, HealthProfile.doh_facility_id).where(
                HealthProfile.facility_id.in_(chunk),
                HealthProfile.doh_facility_id.is_not(None),
            )
        ).all():
            doh[facility_id].add(doh_id)
    doe = defaultdict(set)
    for chunk in _chunks(facility_ids):
        for facility_id, doe_id in session.execute(
            select(UtilityProfile.facility_id, UtilityProfile.doe_facility_code).where(
                UtilityProfile.facility_id.in_(chunk),
                UtilityProfile.doe_facility_code.is_not(None),
            )
        ).all():
            doe[facility_id].add(doe_id)
    for facility_id, ref in refs.items():
        ref.deped_ids = deped.get(facility_id, set())
        ref.doh_ids = doh.get(facility_id, set())
        ref.doe_ids = doe.get(facility_id, set())


def _different_agencies(left: _Ref, right: _Ref) -> bool:
    if not left.agency_codes or not right.agency_codes:
        return False
    if left.agency_codes != right.agency_codes:
        return True
    return len(left.agency_codes) > 1


def _same_agency_duplicate(
    left: _Ref,
    right: _Ref,
    *,
    name_score: float,
    distance: float | None,
    conflicting_ids: bool,
    conflicting_location: bool,
) -> bool:
    """Whether two rows from one agency are the same point, not two branches.

    This is deliberately stricter than a cross-agency match. The name must be
    identical, both records must be specific named places, and the rows must
    share a point within 50 m. The same city, barangay or free-text address
    alone is not enough, because one agency can publish several branches of the
    same office in one barangay and often repeats a city-level address for them.
    """

    if name_score != 1.0 or conflicting_ids or conflicting_location:
        return False
    if not left.agency_codes or left.agency_codes != right.agency_codes:
        return False
    if not left.specific or not right.specific or left.generic or right.generic:
        return False
    return distance is not None and distance <= SAME_AGENCY_POINT_DISTANCE_M


def _id_evidence(left: _Ref, right: _Ref) -> tuple[bool, bool]:
    """Return ``(conflict, shared)`` for official identifiers."""

    for field_name in ("deped_ids", "doh_ids", "doe_ids"):
        left_ids = getattr(left, field_name)
        right_ids = getattr(right, field_name)
        if left_ids and right_ids:
            if left_ids & right_ids:
                return False, True
            return True, False
    return False, False


def _location_evidence(
    left: _Ref,
    right: _Ref,
    admin: _AdminIndex,
) -> tuple[float, str, float | None, int, bool, bool]:
    same_city = bool(left.city_code and right.city_code and left.city_code == right.city_code)
    same_barangay = bool(
        left.barangay_code and right.barangay_code and left.barangay_code == right.barangay_code
    )
    mentions_barangay = bool(
        (
            left.barangay_name
            and _mentions_admin_name(right.location.address_text, left.barangay_name)
        )
        or (
            right.barangay_name
            and _mentions_admin_name(left.location.address_text, right.barangay_name)
        )
    )
    shared_address = address_overlap(
        left.location.address_text,
        right.location.address_text,
        administrative_names=admin.administrative_tokens,
    )
    distance = _distance_m(left.location, right.location)
    if same_barangay or mentions_barangay:
        return 1.0, "same_barangay", distance, shared_address, same_city, same_barangay
    if distance is not None and distance <= 50:
        return 1.0, "coordinates_within_50m", distance, shared_address, same_city, same_barangay
    if distance is not None and distance <= 250 and same_city:
        return 0.9, "coordinates_within_250m", distance, shared_address, same_city, same_barangay
    if shared_address >= 1 and same_city:
        return 0.9, "shared_address", distance, shared_address, same_city, same_barangay
    if same_city:
        return (
            CITY_ONLY_LOCATION_SCORE,
            "same_city",
            distance,
            shared_address,
            same_city,
            same_barangay,
        )
    if distance is not None and distance <= 250:
        return (
            0.7,
            "coordinates_within_250m_no_city",
            distance,
            shared_address,
            same_city,
            same_barangay,
        )
    return 0.0, "no_location_evidence", distance, shared_address, same_city, same_barangay


_STREET_ADDRESS_MARKERS = frozenset(
    {
        "ave",
        "avenue",
        "blvd",
        "boulevard",
        "dr",
        "drive",
        "highway",
        "hwy",
        "lane",
        "purok",
        "rd",
        "road",
        "sitio",
        "st",
        "street",
        "subd",
        "subdivision",
    }
)

_ADMIN_ADDRESS_WORDS = frozenset(
    {
        "barangay",
        "bgy",
        "brgy",
        "capital",
        "city",
        "district",
        "first",
        "fourth",
        "huc",
        "municipality",
        "ncr",
        "not",
        "pob",
        "poblacion",
        "province",
        "region",
        "second",
        "sixth",
        "third",
        "zone",
    }
)


def _street_address_tokens(
    value: str | None,
    administrative_names: set[str] | frozenset[str] | None = None,
) -> set[str]:
    """Return address tokens that can distinguish one street address from another.

    City, barangay and region names are administrative context, not street
    evidence. Numeric tokens are usually house or barangay numbers and cannot
    distinguish two nearby descriptions of the same block.
    """

    return {
        token
        for token in address_tokens(value, administrative_names=administrative_names)
        if not token.isdigit() and token not in _ADMIN_ADDRESS_WORDS
    }


def _has_street_marker(value: str | None) -> bool:
    """Whether an address names a street-level location rather than a locality."""

    return bool(set(normalize_name(value).split()) & _STREET_ADDRESS_MARKERS)


def _conflicting_location(
    left: _Ref,
    right: _Ref,
    distance: float | None,
    *,
    same_barangay: bool,
    name_score: float,
    administrative_names: set[str] | frozenset[str] | None = None,
) -> bool:
    if distance is not None and distance > CONFLICTING_POINT_DISTANCE_M:
        return True
    if same_barangay:
        # DepEd commonly publishes a site note ("Purok 2") while OSM publishes
        # the barangay name. Once both records agree on the same barangay, that
        # administrative bridge outranks a difference in free-text address.
        return False
    if left.barangay_code and right.barangay_code and left.barangay_code != right.barangay_code:
        # A crowd-sourced or geocoded point can fall on the neighbouring side of
        # a barangay boundary while an official registry places the same site in
        # its own barangay. When the names are exact, both places are specific,
        # the points are within 50 m, and at least one side is map-derived, the
        # mismatch is boundary noise rather than evidence of two facilities.
        if (
            name_score == 1.0
            and distance is not None
            and distance <= 50
            and left.specific
            and right.specific
            and not left.generic
            and not right.generic
        ):
            return not _has_map_derived_precision(left, right)
        return True
    left_tokens = _street_address_tokens(
        left.location.address_text,
        administrative_names=administrative_names,
    )
    right_tokens = _street_address_tokens(
        right.location.address_text,
        administrative_names=administrative_names,
    )
    # Distinct street-level addresses are evidence of different branches. Only
    # treat them as a conflict when both sides actually carry street evidence
    # and no address token matches at all. A locality-only description (for
    # example "Lucena City, Quezon") is less precise than a street address, not
    # a competing one.
    if not (left_tokens and right_tokens and not (left_tokens & right_tokens)):
        return False
    if not (
        _has_street_marker(left.location.address_text)
        and _has_street_marker(right.location.address_text)
    ):
        return False
    # A specific matching name at the same point outranks a free-text address
    # difference. One source often records a street while the other records an
    # administrative or compound description of the same site.
    same_specific_name_at_same_point = (
        distance is not None
        and distance <= 50
        and name_score >= 0.9
        and left.specific
        and right.specific
        and not left.generic
        and not right.generic
    )
    return not same_specific_name_at_same_point


# Precision classes for the barangay-boundary exception. A map-derived point
# cannot establish which side of a barangay boundary a site is on; two
# independently surveyed points that disagree stay separate.
_MAP_DERIVED_PRECISIONS = frozenset({"map_geocoded", "barangay_centroid"})
_LOCATION_PRECISIONS = (
    frozenset({"source_gps", "gps_verified", "surveyed", "field_verified"})
    | _MAP_DERIVED_PRECISIONS
)


def _has_map_derived_precision(left: _Ref, right: _Ref) -> bool:
    left_map = left.location.precision in _MAP_DERIVED_PRECISIONS
    right_map = right.location.precision in _MAP_DERIVED_PRECISIONS
    if not (left_map or right_map):
        return False
    other = right if left_map else left
    return other.location.precision in _LOCATION_PRECISIONS


def _evaluate_pair(
    left: _Ref,
    right: _Ref,
    admin: _AdminIndex,
    *,
    allow_type_mismatch: bool = False,
) -> _Pair | None:
    same_type = left.facility.facility_type == right.facility.facility_type
    if not same_type and not allow_type_mismatch:
        return None
    if same_type and not _subtypes_compatible(left.facility, right.facility):
        return None
    name_score, name_reason = name_similarity(
        left.facility.display_name,
        right.facility.display_name,
        school="school" in (left.facility.facility_type, right.facility.facility_type),
    )
    if name_score < 0.9:
        return None
    (
        location_score,
        location_reason,
        distance,
        shared_address,
        same_city,
        same_barangay,
    ) = _location_evidence(left, right, admin)
    conflicting_location = _conflicting_location(
        left,
        right,
        distance,
        same_barangay=same_barangay,
        name_score=name_score,
        administrative_names=admin.administrative_tokens,
    )
    conflicting_ids, shared_ids = _id_evidence(left, right)
    different_agency = _different_agencies(left, right)
    cross_type = not same_type
    if cross_type:
        # A type disagreement is evidence in its own right. Co-location and a
        # matching specific name are enough to ask a reviewer, never enough to
        # merge automatically.
        auto = False
        note = "facility type differs; review required"
    elif not different_agency:
        auto = _same_agency_duplicate(
            left,
            right,
            name_score=name_score,
            distance=distance,
            conflicting_ids=conflicting_ids,
            conflicting_location=conflicting_location,
        )
        note = "same-agency exact duplicate" if auto else "same agency only"
    elif conflicting_ids:
        auto = False
        note = "conflicting official identifiers"
    elif conflicting_location:
        auto = False
        note = "address or coordinates point to different places"
    elif not left.specific or not right.specific or left.generic or right.generic:
        auto = location_score >= AUTO_MIN_LOCATION_SCORE
        note = "generic name requires strong location evidence"
    elif name_score == 1.0:
        if same_city and (left.official or right.official):
            auto = True
            note = "exact canonical name and same city with an official source"
        else:
            auto = location_score >= AUTO_MIN_LOCATION_SCORE
            note = "exact canonical name with strong location evidence"
    else:
        auto = location_score >= AUTO_MIN_LOCATION_SCORE
        note = "name variant requires strong location evidence"
    return _Pair(
        left=left,
        right=right,
        name_score=name_score,
        name_reason=name_reason,
        location_score=location_score,
        location_reason=location_reason,
        distance_m=distance,
        shared_address_tokens=shared_address,
        same_city=same_city,
        same_barangay=same_barangay,
        conflicting_location=conflicting_location,
        conflicting_ids=conflicting_ids,
        shared_ids=shared_ids,
        different_agency=different_agency,
        auto_eligible=auto,
        note=note,
        cross_type=cross_type,
    )


def _pair_key(left: _Ref, right: _Ref) -> tuple[uuid.UUID, uuid.UUID]:
    return (left.id, right.id) if str(left.id) < str(right.id) else (right.id, left.id)


def _confidence(pair: _Pair) -> Decimal:
    value = 0.90 + 0.04 * pair.name_score + 0.04 * pair.location_score
    if pair.shared_ids:
        value = max(value, 0.985)
    if pair.same_barangay:
        value = max(value, 0.98)
    return Decimal(str(min(value, 0.995))).quantize(Decimal("0.001"))


def _candidate_evidence(pair: _Pair, target: _Ref) -> dict[str, Any]:
    source = pair.left if target is pair.right else pair.right
    reason = (
        "The records share a specific name and point but disagree on facility type; "
        "a reviewer must decide whether they describe the same place."
        if pair.cross_type
        else (
            "Independent name, location and identifier evidence agree; "
            "no conflicting identifiers or places were found."
        )
    )
    return {
        "reason": reason,
        "algorithm": GENERAL_MATCH_METHOD,
        "algorithm_version": ALGORITHM_VERSION,
        "cross_type": pair.cross_type,
        "name_score": pair.name_score,
        "name_reason": pair.name_reason,
        "normalized_name": source.name_key,
        "candidate_normalized_name": target.name_key,
        "location_score": pair.location_score,
        "location_reason": pair.location_reason,
        "city_code": source.city_code or target.city_code,
        "barangay_code": source.barangay_code or target.barangay_code,
        "city_code_derived": source.city_code_derived or target.city_code_derived,
        "barangay_code_derived": (source.barangay_code_derived or target.barangay_code_derived),
        "same_city": pair.same_city,
        "same_barangay": pair.same_barangay,
        "shared_address_tokens": pair.shared_address_tokens,
        "distance_m": round(pair.distance_m, 1) if pair.distance_m is not None else None,
        "conflicting_location": pair.conflicting_location,
        "conflicting_ids": pair.conflicting_ids,
        "shared_official_ids": pair.shared_ids,
        "official_source": source.official or target.official,
        "source_agency_codes": sorted(source.agency_codes),
        "candidate_agency_codes": sorted(target.agency_codes),
        "source_datasets": sorted(source.dataset_slugs),
        "candidate_datasets": sorted(target.dataset_slugs),
        "source_facility_type": source.facility.facility_type,
        "candidate_facility_type": target.facility.facility_type,
        "facility_type": target.facility.facility_type,
        "note": pair.note,
        "source_facility_snapshot": _facility_snapshot(source.facility),
        "candidate_facility_snapshot": _facility_snapshot(target.facility),
    }


def _choose_target(refs: list[_Ref]) -> _Ref:
    return min(
        refs,
        key=lambda ref: (
            not ref.official,
            -(len(ref.deped_ids) + len(ref.doh_ids) + len(ref.doe_ids)),
            -len(ref.links),
            ref.facility.created_at,
            str(ref.facility.id),
        ),
    )


def _existing_candidate(
    session: Session,
    source_facility_id: uuid.UUID,
    target_facility_id: uuid.UUID,
) -> MatchCandidate | None:
    candidates = list(
        session.scalars(
            select(MatchCandidate)
            .where(
                MatchCandidate.source_facility_id == source_facility_id,
                MatchCandidate.candidate_facility_id == target_facility_id,
            )
            .order_by(MatchCandidate.created_at.desc())
        ).all()
    )
    for status in ("accepted", "pending", "merged", "rejected"):
        for candidate in candidates:
            if candidate.match_status == status:
                return candidate
    return candidates[0] if candidates else None


def _accept_existing_candidate(
    session: Session,
    candidate: MatchCandidate,
    pair: _Pair,
    target: _Ref,
) -> bool:
    """Promote an already-queued candidate when fresh evidence is conclusive.

    A rejected merge is a human decision and is never overridden. A merged one
    means the pair was already consolidated. A pending candidate is accepted in
    place, keeping its original key and evidence for audit.
    """

    if candidate.match_status in {"merged", "rejected"}:
        return False
    if candidate.match_status == "pending":
        evidence = dict(candidate.evidence or {})
        evidence["facility_identity_evidence"] = _candidate_evidence(pair, target)
        candidate.evidence = evidence
        candidate.match_status = "accepted"
        candidate.match_confidence = max(
            candidate.match_confidence or Decimal("0"), _confidence(pair)
        )
        candidate.reviewer = AUTO_REVIEWER
        candidate.reviewed_at = datetime.now(UTC)
        candidate.review_note = pair.note
        session.flush()
    return True


def _source_link_for_target(source: _Ref, target: _Ref) -> tuple | None:
    for link in source.links:
        if link[1] not in target.agency_codes:
            return link
    return source.links[0] if source.links else None


def _record_candidate(
    session: Session,
    *,
    source: _Ref,
    target: _Ref,
    pair: _Pair,
    accepted: bool,
    reviewer: str | None,
) -> MatchCandidate | None:
    chosen = _source_link_for_target(source, target)
    if chosen is None:
        return None
    record_id, agency_code, _dataset_slug, _authority_level = chosen
    key = candidate_key(
        record_id,
        target.id,
        method=GENERAL_MATCH_METHOD,
        algorithm_version=ALGORITHM_VERSION,
    )
    if (
        session.scalars(select(MatchCandidate).where(MatchCandidate.candidate_key == key)).first()
        is not None
    ):
        return None
    now = datetime.now(UTC)
    candidate = MatchCandidate(
        candidate_key=key,
        source_record_id=record_id,
        source_facility_id=source.id,
        candidate_facility_id=target.id,
        source_agency_code=agency_code,
        candidate_agency_code=next(
            (code for code in sorted(target.agency_codes) if code != agency_code),
            next(iter(sorted(target.agency_codes)), None),
        ),
        match_method=GENERAL_MATCH_METHOD,
        algorithm_version=ALGORITHM_VERSION,
        match_confidence=_confidence(pair),
        match_status="accepted" if accepted else "pending",
        reviewer=reviewer if accepted else None,
        reviewed_at=now if accepted else None,
        review_note=pair.note if accepted else None,
        evidence=_candidate_evidence(pair, target),
    )
    session.add(candidate)
    session.flush()
    return candidate


def _name_variant_key(name_key: str) -> str:
    """A name key that ignores connector-word order but keeps service words."""

    tokens = sorted(token for token in name_key.split() if token not in NAME_VARIANT_CONNECTORS)
    return " ".join(tokens) if len(tokens) >= 2 else ""


def _bucket_keys(ref: _Ref) -> set[tuple[str, Any]]:
    """Return comparison buckets for a facility.

    Names repeat across the country (``Mercury Drug`` has over a thousand
    rows), so large name groups are bucketed instead of compared exhaustively.
    A facility is placed in both its city bucket and the point cells around its
    coordinate. The coordinate bucket is essential: two sources can assign the
    same site to different cities or barangays, and a city-only bucket would
    never compare them even when their points are metres apart.
    """

    keys: set[tuple[str, Any]] = set()
    if ref.city_code:
        keys.add(("city", ref.city_code))
    latitude = ref.location.latitude
    longitude = ref.location.longitude
    if latitude is not None and longitude is not None:
        row = round(float(latitude) / CELL_BUCKET_DEGREES)
        column = round(float(longitude) / CELL_BUCKET_DEGREES)
        for row_offset in (-1, 0, 1):
            for column_offset in (-1, 0, 1):
                keys.add(
                    (
                        "cell",
                        (row + row_offset, column + column_offset),
                    )
                )
    if not keys:
        keys.add(("unlocated", None))
    return keys


def _auto_pair(pair: _Pair) -> bool:
    """Whether a pair is eligible for automatic consolidation at all."""

    return pair.auto_eligible and not pair.cross_type


def _strong_pair(pair: _Pair) -> bool:
    """Whether a pair has more than same-city name agreement.

    A shared official identifier, the same barangay, an address match, or a
    point within 250 m. Exact names in the same city alone are not enough,
    because chains and branches legitimately share both.
    """

    return pair.shared_ids or pair.location_score >= AUTO_MIN_LOCATION_SCORE


def _pair_score(pair: _Pair) -> float:
    return pair.name_score + pair.location_score


def _ref_rank(ref: _Ref) -> tuple:
    """Order surviving targets: official, most identifiers, most links, oldest."""

    return (
        not ref.official,
        -(len(ref.deped_ids) + len(ref.doh_ids) + len(ref.doe_ids)),
        -len(ref.links),
        ref.facility.created_at,
        str(ref.facility.id),
    )


def _cliques(pairs: list[_Pair]) -> list[list[_Ref]]:
    """Return disjoint cliques that each contain at least one strong pair.

    A duplicate cluster is merged only when every pair inside it is eligible and
    the cluster contains a strong identity bridge. Requiring a complete
    connection component instead would let one conflicting record (for example
    a co-located laboratory with a different official code) block the confirmed
    duplicates around it.

    Each clique is grown from a strong pair so a large weak city-only group
    cannot consume the strong evidence and prevent the supported merge.
    """

    adjacency: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    edge_by_key: dict[tuple[uuid.UUID, uuid.UUID], _Pair] = {}
    refs: dict[uuid.UUID, _Ref] = {}
    strong_edges: list[_Pair] = []
    for pair in pairs:
        if not _auto_pair(pair):
            continue
        adjacency[pair.left.id].add(pair.right.id)
        adjacency[pair.right.id].add(pair.left.id)
        edge_by_key[_pair_key(pair.left, pair.right)] = pair
        refs[pair.left.id] = pair.left
        refs[pair.right.id] = pair.right
        if _strong_pair(pair):
            strong_edges.append(pair)

    remaining = set(adjacency)
    cliques: list[list[_Ref]] = []
    while remaining:
        best: list[uuid.UUID] = []
        best_score: tuple[float, float] | None = None
        for edge in sorted(
            (
                edge
                for edge in strong_edges
                if edge.left.id in remaining and edge.right.id in remaining
            ),
            key=_pair_score,
            reverse=True,
        ):
            clique = [edge.left.id, edge.right.id]
            candidates = set.intersection(*(adjacency[ref_id] for ref_id in clique))
            candidates &= remaining
            while candidates and len(clique) < MAX_CLUSTER_SIZE:
                chosen = min(
                    candidates,
                    key=lambda ref_id: (
                        -min(
                            _pair_score(edge_by_key[_pair_key(refs[ref_id], refs[other])])
                            for other in clique
                        ),
                        -len(adjacency[ref_id] & candidates),
                        _ref_rank(refs[ref_id]),
                    ),
                )
                clique.append(chosen)
                candidates &= adjacency[chosen]
            score = (
                float(len(clique)),
                sum(
                    _pair_score(edge_by_key[_pair_key(refs[ref_id], refs[other])])
                    for index, ref_id in enumerate(clique)
                    for other in clique[index + 1 :]
                ),
            )
            if best_score is None or score > best_score:
                best = clique
                best_score = score
        if len(best) < 2:
            break
        cliques.append([refs[ref_id] for ref_id in best])
        remaining -= set(best)
    return cliques


_PRECISION_RANK = {
    "gps_verified": 6,
    "field_verified": 6,
    "surveyed": 6,
    "source_gps": 5,
    "map_geocoded": 4,
    "barangay_centroid": 2,
}


def _location_rank(location: FacilityLocation) -> tuple[int, datetime, str]:
    if location.latitude is None or location.longitude is None:
        # An address-only row can be more precise than a barangay centroid.
        return (3, location.created_at, str(location.id))
    return (
        _PRECISION_RANK.get(location.precision or "unknown", 1),
        location.created_at,
        str(location.id),
    )


def promote_best_location(
    session: Session,
    facility_id: uuid.UUID,
    *,
    reviewer: str,
) -> dict[str, Any] | None:
    """Promote the most precise available point to the current location.

    Merging moves the other source's coordinate row to the survivor, but the
    survivor's old address-only row can remain current. The promoted row keeps
    its own source record; the demoted row keeps its provenance and is closed
    with ``valid_to``. The returned audit is attached to the merge resolution so
    undo can reverse the promotion.
    """

    locations = list(
        session.scalars(
            select(FacilityLocation).where(FacilityLocation.facility_id == facility_id)
        ).all()
    )
    if len(locations) < 2:
        return None
    current = next((location for location in locations if location.is_current), None)

    best = max(locations, key=_location_rank)
    if current is not None and best.id == current.id:
        return None
    if current is not None and _location_rank(best)[0] <= _location_rank(current)[0]:
        return None
    before = {
        "current_location_id": str(current.id) if current else None,
        "current_is_current": current.is_current if current else None,
        "current_valid_to": current.valid_to.isoformat() if current and current.valid_to else None,
        "promoted_location_id": str(best.id),
        "promoted_is_current": best.is_current,
        "promoted_valid_to": best.valid_to.isoformat() if best.valid_to else None,
    }
    if current is not None:
        current.is_current = False
        current.valid_to = date.today()
        session.flush()
    best.is_current = True
    best.valid_to = None
    session.add(
        FacilityChangeEvent(
            facility_id=facility_id,
            change_type="location_promoted",
            attribute_name="current_location",
            old_value={"location_id": before["current_location_id"]},
            new_value={
                "location_id": str(best.id),
                "precision": best.precision,
                "method": best.method,
            },
            changed_by=f"review:{reviewer}",
        )
    )
    session.flush()
    return before


def consolidate_facilities(
    session: Session,
    *,
    dry_run: bool = True,
    limit: int = 100,
    include_synthetic: bool = False,
    pending_limit: int = 500,
    example_limit: int = 20,
    affected_facility_ids: set[uuid.UUID] | None = None,
    facility_type: str | None = None,
    commit_every: int | None = None,
    defer_fusion: bool = False,
    merged_facility_ids: set[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Merge complete evidence clusters and queue ambiguous candidates.

    ``commit_every`` commits the completed merges periodically so a long pass
    keeps its work if interrupted. ``defer_fusion`` skips the per-merge fusion
    invalidation and lets the caller rebuild derived rows once at the end; the
    retired source IDs are collected in ``merged_facility_ids`` so that pass can
    clean their stale rows.
    """

    admin = _load_admin_index(session)
    refs = _load_refs(
        session,
        admin,
        include_synthetic=include_synthetic,
        facility_type=facility_type,
    )
    if facility_type is not None:
        refs = {
            ref_id: ref
            for ref_id, ref in refs.items()
            if ref.facility.facility_type == facility_type
        }
    _attach_identifiers(session, refs)

    exact_groups: dict[tuple[str, str], list[_Ref]] = defaultdict(list)
    token_groups: dict[tuple[str, str], list[_Ref]] = defaultdict(list)
    variant_groups: dict[tuple[str, str], list[_Ref]] = defaultdict(list)
    all_exact_groups: dict[str, list[_Ref]] = defaultdict(list)
    all_token_groups: dict[str, list[_Ref]] = defaultdict(list)
    for ref in refs.values():
        if not ref.name_key:
            continue
        exact_groups[(ref.facility.facility_type, ref.name_key)].append(ref)
        token_groups[(ref.facility.facility_type, ref.token_key)].append(ref)
        if ref.specific and not ref.generic:
            variant_key = _name_variant_key(ref.name_key)
            if variant_key:
                variant_groups[(ref.facility.facility_type, variant_key)].append(ref)
            all_exact_groups[ref.name_key].append(ref)
            all_token_groups[ref.token_key].append(ref)

    pairs: dict[tuple[uuid.UUID, uuid.UUID], _Pair] = {}
    groups_considered = 0

    def evaluate_group(
        group: list[_Ref],
        *,
        allow_type_mismatch: bool,
        cross_type_only: bool,
    ) -> None:
        nonlocal groups_considered
        if len(group) < 2:
            return
        if len(group) <= ALL_PAIRS_GROUP_MAX:
            buckets = [group]
        else:
            bucket_map: dict[tuple[str, Any], list[_Ref]] = defaultdict(list)
            for ref in group:
                for bucket_key in _bucket_keys(ref):
                    bucket_map[bucket_key].append(ref)
            buckets = [bucket for bucket in bucket_map.values() if len(bucket) >= 2]
        for bucket in buckets:
            if len(bucket) < 2:
                continue
            groups_considered += 1
            ordered = sorted(bucket, key=lambda ref: (ref.facility.created_at, str(ref.id)))
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    key = _pair_key(left, right)
                    if key in pairs:
                        continue
                    pair = _evaluate_pair(
                        left,
                        right,
                        admin,
                        allow_type_mismatch=allow_type_mismatch,
                    )
                    if pair is None:
                        continue
                    if cross_type_only and not pair.cross_type:
                        continue
                    pairs[key] = pair

    for group in (
        list(exact_groups.values()) + list(token_groups.values()) + list(variant_groups.values())
    ):
        evaluate_group(group, allow_type_mismatch=False, cross_type_only=False)
    for group in list(all_exact_groups.values()) + list(all_token_groups.values()):
        if len({ref.facility.facility_type for ref in group}) < 2:
            continue
        evaluate_group(group, allow_type_mismatch=True, cross_type_only=True)

    parent: dict[uuid.UUID, uuid.UUID] = {ref_id: ref_id for ref_id in refs}

    def find(value: uuid.UUID) -> uuid.UUID:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: uuid.UUID, right: uuid.UUID) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    auto_pairs = [pair for pair in pairs.values() if pair.auto_eligible]
    mergeable_pairs = [pair for pair in auto_pairs if _auto_pair(pair)]
    for pair in mergeable_pairs:
        union(pair.left.id, pair.right.id)

    components: dict[uuid.UUID, list[_Pair]] = defaultdict(list)
    for pair in mergeable_pairs:
        components[find(pair.left.id)].append(pair)

    stats: dict[str, Any] = {
        "facilities_scanned": len(refs),
        "groups_considered": groups_considered,
        "pairs_considered": len(pairs),
        "auto_pairs": len(auto_pairs),
        "mergeable_pairs": len(mergeable_pairs),
        "components_considered": len(components),
        "clusters_accepted": 0,
        "clusters_rejected": 0,
        "merged": 0,
        "would_merge": 0,
        "pending_created": 0,
        "skipped_existing": 0,
        "skipped_cluster_incomplete": 0,
        "skipped_limit": 0,
        "skipped_error": 0,
        "errors": [],
        "examples": [],
        "dry_run": dry_run,
        "algorithm_version": ALGORITHM_VERSION,
    }

    merged_facilities: set[uuid.UUID] = set()
    merges_since_commit = 0
    for component_pairs in components.values():
        component_cliques = _cliques(component_pairs)
        if not component_cliques:
            stats["clusters_rejected"] += 1
            stats["skipped_cluster_incomplete"] += 1
            continue
        edge_by_key = {_pair_key(pair.left, pair.right): pair for pair in component_pairs}
        for clique_refs in component_cliques:
            if any(ref.id in merged_facilities for ref in clique_refs):
                continue
            if not dry_run and stats["merged"] >= limit:
                # The batch is full; report the remaining clusters instead of
                # silently counting them as accepted.
                stats["skipped_limit"] += 1
                continue
            target = _choose_target(clique_refs)
            stats["clusters_accepted"] += 1
            merged_before = stats["merged"]
            for source in clique_refs:
                if source.id == target.id:
                    continue
                pair = edge_by_key.get(_pair_key(source, target))
                if pair is None:
                    continue
                existing = _existing_candidate(session, source.id, target.id)
                if existing is not None and existing.match_status in {"merged", "rejected"}:
                    stats["skipped_existing"] += 1
                    continue
                if len(stats["examples"]) < example_limit:
                    stats["examples"].append(
                        {
                            "source_facility_id": str(source.id),
                            "target_facility_id": str(target.id),
                            "source_name": source.facility.display_name,
                            "target_name": target.facility.display_name,
                            "facility_type": source.facility.facility_type,
                            "source_city": source.city_name or source.city_code,
                            "target_city": target.city_name or target.city_code,
                            "source_barangay": source.barangay_name or source.barangay_code,
                            "target_barangay": target.barangay_name or target.barangay_code,
                            "name_score": pair.name_score,
                            "name_reason": pair.name_reason,
                            "location_score": pair.location_score,
                            "location_reason": pair.location_reason,
                            "distance_m": pair.distance_m,
                            "shared_address_tokens": pair.shared_address_tokens,
                            "shared_official_ids": pair.shared_ids,
                            "same_city": pair.same_city,
                            "same_barangay": pair.same_barangay,
                            "confidence": str(_confidence(pair)),
                        }
                    )
                if dry_run:
                    stats["would_merge"] += 1
                    continue
                if stats["merged"] >= limit:
                    continue
                if existing is not None:
                    if not _accept_existing_candidate(session, existing, pair, target):
                        stats["skipped_existing"] += 1
                        continue
                    candidate = existing
                else:
                    candidate = _record_candidate(
                        session,
                        source=source,
                        target=target,
                        pair=pair,
                        accepted=True,
                        reviewer=AUTO_REVIEWER,
                    )
                    if candidate is None:
                        stats["skipped_existing"] += 1
                        continue
                try:
                    merge_match_candidate(
                        session,
                        candidate.id,
                        reviewer=AUTO_REVIEWER,
                        note=(
                            "Independent name, location and identifier evidence; "
                            "every pair in the merged cluster agrees and no places "
                            "or official identifiers conflict."
                        ),
                        invalidate_fusions=not defer_fusion,
                    )
                    promotion = promote_best_location(session, target.id, reviewer=AUTO_REVIEWER)
                    if promotion:
                        resolution = dict(candidate.resolution or {})
                        resolution["location_promotion"] = promotion
                        candidate.resolution = resolution
                    stats["merged"] += 1
                    merged_facilities.add(source.id)
                    if merged_facility_ids is not None:
                        merged_facility_ids.add(source.id)
                    if affected_facility_ids is not None:
                        affected_facility_ids.add(target.id)
                except MatchingError as exc:
                    stats["skipped_error"] += 1
                    if len(stats["errors"]) < 20:
                        stats["errors"].append(f"{candidate.id}: {exc}")
            merged_facilities.add(target.id)
            merges_since_commit += stats["merged"] - merged_before
            if (
                not dry_run
                and commit_every is not None
                and commit_every > 0
                and merges_since_commit >= commit_every
            ):
                session.commit()
                merges_since_commit = 0

    if not dry_run and stats["pending_created"] < pending_limit:
        for pair in pairs.values():
            if pair.auto_eligible:
                continue
            if pair.cross_type:
                # Cross-type evidence is review-only. Require a specific name,
                # a co-located point, and one official and one non-official
                # source before asking a reviewer.
                if pair.name_score < 0.9:
                    continue
                if pair.distance_m is None or pair.distance_m > CROSS_TYPE_MAX_DISTANCE_M:
                    continue
                if pair.conflicting_ids or pair.conflicting_location:
                    continue
                if (
                    not pair.left.specific
                    or not pair.right.specific
                    or pair.left.generic
                    or pair.right.generic
                ):
                    continue
                if pair.left.official == pair.right.official:
                    continue
                if pair.left.official:
                    source, target = pair.right, pair.left
                else:
                    source, target = pair.left, pair.right
            else:
                if pair.name_score < 0.9 or not pair.same_city:
                    continue
                if pair.conflicting_ids or pair.conflicting_location:
                    continue
                source, target = pair.left, pair.right
            if source.id in merged_facilities or target.id in merged_facilities:
                continue
            if (
                session.get(Facility, source.id).record_status == "merged"
                or session.get(Facility, target.id).record_status == "merged"
            ):
                continue
            if (
                _existing_candidate(session, source.id, target.id) is not None
                or _existing_candidate(session, target.id, source.id) is not None
            ):
                continue
            if stats["pending_created"] >= pending_limit:
                break
            candidate = _record_candidate(
                session,
                source=source,
                target=target,
                pair=pair,
                accepted=False,
                reviewer=None,
            )
            if candidate is not None:
                stats["pending_created"] += 1
    return stats
