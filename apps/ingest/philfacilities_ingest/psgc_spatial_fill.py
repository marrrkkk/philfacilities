"""Fill location PSGC codes from OSM administrative boundary containment.

A facility point already present on the map is direct evidence of the
administrative unit that contains it. This module intersects those points with
the preserved OSM boundary layer (``geo.osm_admin_boundaries``) and writes the
deepest unambiguous containing PSGC code.

Source-supplied codes are never replaced with a same-level or conflicting map
value by default. A null code is filled; with ``refine=True`` a code is upgraded
only when the map value is a descendant of the current code. ``prefer_map=True``
makes the containing map unit authoritative and replaces same-level or
different-branch source codes, while never downgrading a more specific source
code. Every write keeps an ``AttributeAssertion`` linked to the location's
source record, so the original source claim remains available. A facility whose
point is outside every resolved boundary stays unknown.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import shapely
from philfacilities_api.models import (
    AdministrativeUnit,
    AttributeAssertion,
    Facility,
    FacilityLocation,
    OsmAdminBoundary,
)
from shapely.geometry import Point
from shapely.strtree import STRtree
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .osm_boundaries import SPATIAL_RESOLUTION_VERSION, _as_multipolygon
from .psgc_fill import (
    MAX_IDS_PER_QUERY,
    GeographyIndex,
    _existing_psgc_claims,
    _latest_real_release,
)

# Outcomes reported for each examined location.
FILL = "fill"
REFINE = "refine"
REFINE_AVAILABLE = "refine_available"
OVERRIDE = "override"
SAME = "same"
CURRENT_MORE_SPECIFIC = "current_more_specific"
CONFLICT = "conflict"
NO_BOUNDARY = "no_boundary"
POLYGON_CONFLICT = "polygon_conflict"
INCONSISTENT = "inconsistent"
UNKNOWN_CODE = "unknown_code"
NO_COORDINATES = "no_coordinates"
NO_SOURCE_RECORD = "no_source_record"

WRITE_OUTCOMES = frozenset({FILL, REFINE, OVERRIDE})


@dataclass(frozen=True)
class BoundaryFeature:
    psgc_code: str
    admin_level: int
    geographic_level: str | None
    parent_psgc_code: str | None
    geom: Any


@dataclass(frozen=True)
class BoundaryLookup:
    outcome: str
    psgc_code: str | None = None
    admin_level: int | None = None


@dataclass(frozen=True)
class SpatialDecision:
    outcome: str
    psgc_code: str | None = None
    admin_level: int | None = None
    geographic_level: str | None = None
    method: str | None = None


@dataclass
class SpatialFillStats:
    examined: int = 0
    filled: int = 0
    refined: int = 0
    overridden: int = 0
    refinable: int = 0
    applied: int = 0
    refine_enabled: bool = False
    prefer_map: bool = False
    geography_release: str | None = None
    boundary_release: str | None = None
    boundaries: int = 0
    outcomes: Counter[str] = field(default_factory=Counter)
    by_level: Counter[str] = field(default_factory=Counter)
    by_method: Counter[str] = field(default_factory=Counter)
    rows: list[dict[str, Any]] = field(default_factory=list)
    conflict_samples: list[dict[str, Any]] = field(default_factory=list)
    unresolved_samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_rows: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "version": SPATIAL_RESOLUTION_VERSION,
            "geography_release": self.geography_release,
            "boundary_release": self.boundary_release,
            "boundaries": self.boundaries,
            "refine_enabled": self.refine_enabled,
            "prefer_map": self.prefer_map,
            "examined": self.examined,
            "filled": self.filled,
            "refined": self.refined,
            "overridden": self.overridden,
            "refinable": self.refinable,
            "applied": self.applied,
            "outcomes": dict(sorted(self.outcomes.items())),
            "by_level": dict(sorted(self.by_level.items())),
            "by_method": dict(sorted(self.by_method.items())),
            "conflict_samples": self.conflict_samples,
            "unresolved_samples": self.unresolved_samples,
        }
        if include_rows:
            payload["rows"] = self.rows
        return payload


class BoundaryIndex:
    """Point-in-polygon index over resolved boundaries for one PSGC release."""

    def __init__(
        self,
        features: Iterable[BoundaryFeature],
        geography: GeographyIndex,
    ) -> None:
        self.features = list(features)
        self.geography = geography
        self._tree = STRtree([feature.geom for feature in self.features]) if self.features else None

    def lookup(self, latitude: float, longitude: float) -> BoundaryLookup:
        if self._tree is None:
            return BoundaryLookup(NO_BOUNDARY)
        point = Point(longitude, latitude)
        hits = self._tree.query(point, predicate="covered_by")
        if len(hits) == 0:
            return BoundaryLookup(NO_BOUNDARY)
        matched = [self.features[int(index)] for index in hits]
        best_level = max(feature.admin_level for feature in matched)
        deepest = {feature.psgc_code for feature in matched if feature.admin_level == best_level}
        if len(deepest) != 1:
            return BoundaryLookup(POLYGON_CONFLICT, admin_level=best_level)
        code = next(iter(deepest))
        # A point can be covered by boundaries whose codes disagree about the
        # hierarchy (stale or overlapping OSM polygons). Only trust the deepest
        # code when every other containing code is its ancestor or itself.
        for feature in matched:
            if feature.psgc_code == code:
                continue
            if not self.geography.is_ancestor(feature.psgc_code, code):
                return BoundaryLookup(INCONSISTENT, admin_level=best_level)
        return BoundaryLookup("resolved", psgc_code=code, admin_level=best_level)


def classify(
    current_code: str | None,
    lookup: BoundaryLookup,
    geography: GeographyIndex,
    *,
    refine: bool = False,
    prefer_map: bool = False,
) -> SpatialDecision:
    """Decide what a map containment means for the location's current code.

    ``prefer_map`` makes the containing map unit authoritative for a
    coordinate-bearing location: it refines as usual, and it replaces a
    same-level or different-branch source code instead of preserving it. The
    source claim remains available in its original assertion.
    """

    if lookup.outcome != "resolved" or lookup.psgc_code is None:
        return SpatialDecision(lookup.outcome, admin_level=lookup.admin_level)
    code = lookup.psgc_code
    feature = geography.by_code.get(code)
    decision = SpatialDecision(
        FILL,
        psgc_code=code,
        admin_level=lookup.admin_level,
        geographic_level=feature.geographic_level if feature else None,
        method="osm_boundary_containment",
    )
    if current_code is None:
        return decision
    if current_code == code:
        return SpatialDecision(
            SAME,
            psgc_code=code,
            admin_level=lookup.admin_level,
            geographic_level=decision.geographic_level,
        )
    if current_code not in geography.by_code:
        if prefer_map:
            return SpatialDecision(
                OVERRIDE,
                psgc_code=code,
                admin_level=lookup.admin_level,
                geographic_level=decision.geographic_level,
                method="osm_boundary_override",
            )
        return SpatialDecision(
            UNKNOWN_CODE,
            psgc_code=code,
            admin_level=lookup.admin_level,
            geographic_level=decision.geographic_level,
        )
    if geography.is_ancestor(current_code, code):
        write = refine or prefer_map
        return SpatialDecision(
            REFINE if write else REFINE_AVAILABLE,
            psgc_code=code,
            admin_level=lookup.admin_level,
            geographic_level=decision.geographic_level,
            method="osm_boundary_refinement" if write else None,
        )
    if geography.is_ancestor(code, current_code):
        return SpatialDecision(
            CURRENT_MORE_SPECIFIC,
            psgc_code=code,
            admin_level=lookup.admin_level,
            geographic_level=decision.geographic_level,
        )
    if prefer_map:
        return SpatialDecision(
            OVERRIDE,
            psgc_code=code,
            admin_level=lookup.admin_level,
            geographic_level=decision.geographic_level,
            method="osm_boundary_override",
        )
    return SpatialDecision(
        CONFLICT,
        psgc_code=code,
        admin_level=lookup.admin_level,
        geographic_level=decision.geographic_level,
    )


def load_boundary_index(
    session: Session, geography: GeographyIndex
) -> tuple[BoundaryIndex, str | None]:
    """Load one boundary snapshot and the deepest range of geometry queries."""

    rows = session.execute(
        select(
            OsmAdminBoundary.psgc_code,
            OsmAdminBoundary.admin_level,
            OsmAdminBoundary.geographic_level,
            OsmAdminBoundary.parent_psgc_code,
            OsmAdminBoundary.release_label,
            func.ST_AsBinary(OsmAdminBoundary.geom),
        ).where(OsmAdminBoundary.psgc_code.is_not(None))
    ).all()
    features: list[BoundaryFeature] = []
    release_label: str | None = None
    for code, level, geographic_level, parent, label, wkb in rows:
        if not code or wkb is None:
            continue
        geometry = _as_multipolygon(shapely.from_wkb(bytes(wkb)))
        if geometry is None:
            continue
        features.append(
            BoundaryFeature(
                psgc_code=code,
                admin_level=int(level),
                geographic_level=geographic_level,
                parent_psgc_code=parent,
                geom=geometry,
            )
        )
        release_label = release_label or label
    return BoundaryIndex(features, geography), release_label


def _coordinate_rows(session: Session, *, batch_size: int = MAX_IDS_PER_QUERY):
    statement = (
        select(FacilityLocation, Facility.slug)
        .join(Facility, Facility.id == FacilityLocation.facility_id)
        .where(
            FacilityLocation.is_current.is_(True),
            FacilityLocation.geom.is_not(None),
            Facility.is_synthetic.is_(False),
        )
        .order_by(FacilityLocation.facility_id)
        .execution_options(yield_per=batch_size)
    )
    return session.execute(statement).partitions(batch_size)


def _apply_decision(
    session: Session,
    location: FacilityLocation,
    decision: SpatialDecision,
    existing_claims: set[tuple[uuid.UUID, uuid.UUID, str]],
) -> bool:
    """Write one map-derived code and its source-linked assertion."""

    record_id = location.source_record_id
    if location.psgc_code == decision.psgc_code or record_id is None:
        return False
    location.psgc_code = decision.psgc_code
    claim = (location.facility_id, record_id, decision.psgc_code)
    if claim not in existing_claims:
        existing_claims.add(claim)
        session.add(
            AttributeAssertion(
                facility_id=location.facility_id,
                source_record_id=record_id,
                attribute_name="psgc_code",
                source_field="geom",
                raw_value=f"{location.latitude},{location.longitude}",
                normalized_value=decision.psgc_code,
                transformation_version=SPATIAL_RESOLUTION_VERSION,
                review_status="derived",
            )
        )
    return True


def fill_location_psgc_from_map(
    session: Session,
    *,
    apply: bool = False,
    refine: bool = False,
    prefer_map: bool = False,
    report_path: str | Path | None = None,
) -> SpatialFillStats:
    """Fill or refine current-location PSGC codes from map containment.

    Without ``apply`` the command only reports the planned changes. ``refine``
    upgrades a non-null code only when the containing map unit is a descendant
    of the current code. ``prefer_map`` treats the containing map unit as
    authoritative: it overrides same-level and different-branch source codes,
    keeping the original source claim in its existing assertion.
    """

    release = _latest_real_release(session)
    if release is None:
        raise ValueError("No real PSGC release is loaded; refusing to use synthetic geography.")
    geography = GeographyIndex(
        session.scalars(
            select(AdministrativeUnit).where(AdministrativeUnit.release_id == release.id)
        ).all()
    )
    boundaries, boundary_release = load_boundary_index(session, geography)
    if not boundaries.features:
        raise ValueError(
            "No resolved OSM administrative boundaries are loaded; "
            "run import-osm-boundaries --apply first."
        )
    stats = SpatialFillStats(
        refine_enabled=refine,
        prefer_map=prefer_map,
        geography_release=release.release_label,
        boundary_release=boundary_release,
        boundaries=len(boundaries.features),
    )
    existing_claims = _existing_psgc_claims(session) if apply else set()

    for partition in _coordinate_rows(session):
        for location, slug in partition:
            stats.examined += 1
            if location.latitude is None or location.longitude is None:
                stats.outcomes[NO_COORDINATES] += 1
                continue
            lookup = boundaries.lookup(float(location.latitude), float(location.longitude))
            decision = classify(
                location.psgc_code,
                lookup,
                geography,
                refine=refine,
                prefer_map=prefer_map,
            )
            if decision.outcome in WRITE_OUTCOMES and location.source_record_id is None:
                stats.outcomes[NO_SOURCE_RECORD] += 1
                continue
            stats.outcomes[decision.outcome] += 1
            if decision.outcome == FILL:
                stats.filled += 1
            elif decision.outcome == REFINE:
                stats.refined += 1
            elif decision.outcome == OVERRIDE:
                stats.overridden += 1
            elif decision.outcome == REFINE_AVAILABLE:
                stats.refinable += 1
            if decision.outcome in WRITE_OUTCOMES and decision.psgc_code:
                if decision.geographic_level:
                    stats.by_level[decision.geographic_level] += 1
                if decision.method:
                    stats.by_method[decision.method] += 1
                stats.rows.append(
                    {
                        "facility_id": str(location.facility_id),
                        "facility_slug": slug,
                        "previous_psgc_code": location.psgc_code,
                        "psgc_code": decision.psgc_code,
                        "outcome": decision.outcome,
                        "admin_level": decision.admin_level,
                        "geographic_level": decision.geographic_level,
                        "latitude": str(location.latitude),
                        "longitude": str(location.longitude),
                        "source_record_id": str(location.source_record_id),
                    }
                )
                if apply and _apply_decision(session, location, decision, existing_claims):
                    stats.applied += 1
            elif decision.outcome == CONFLICT and len(stats.conflict_samples) < 200:
                stats.conflict_samples.append(
                    {
                        "facility_id": str(location.facility_id),
                        "facility_slug": slug,
                        "current_psgc_code": location.psgc_code,
                        "map_psgc_code": decision.psgc_code,
                        "admin_level": decision.admin_level,
                        "geographic_level": decision.geographic_level,
                        "latitude": str(location.latitude),
                        "longitude": str(location.longitude),
                    }
                )
            elif (
                decision.outcome in {INCONSISTENT, POLYGON_CONFLICT}
                and len(stats.unresolved_samples) < 200
            ):
                stats.unresolved_samples.append(
                    {
                        "facility_id": str(location.facility_id),
                        "facility_slug": slug,
                        "current_psgc_code": location.psgc_code,
                        "outcome": decision.outcome,
                        "admin_level": decision.admin_level,
                        "latitude": str(location.latitude),
                        "longitude": str(location.longitude),
                    }
                )
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
