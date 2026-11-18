"""OSM administrative boundary polygons for map-location PSGC resolution.

The facility coordinates already in the database came from official or
community sources, but many locations have no PSGC code. A map point is strong
evidence for the administrative unit that contains it, so this module preserves
a filtered boundary layer from the same Geofabrik PBF snapshot used for the OSM
facility extract and resolves points by containment.

Boundary provenance is the OSM relation or way, its raw ``ref`` tag, and the
snapshot metadata. A boundary is used only when its ``ref`` maps to the current
PSGC release or its exact name maps to one unit under a spatially containing
parent. Ambiguous boundaries stay unresolved. Raw coordinates are never
changed.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import osmium
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from geoalchemy2.shape import from_shape
from philfacilities_api.models import (
    AdministrativeUnit,
    GeographicRelease,
    OsmAdminBoundary,
)
from shapely.geometry import MultiPolygon, Polygon
from shapely.strtree import STRtree
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .psgc_fill import GeographyIndex, _code, _text

PARSER_VERSION = "osm-boundaries-v1"
SPATIAL_RESOLUTION_VERSION = "psgc-spatial-v1"
BOUNDARY_RELEASE_LABEL = "OSM-ADMIN-BOUNDARIES-2026-11-15"

# OSM admin_level -> geographic levels accepted for a resolved PSGC unit.
LEVELS: dict[int, set[str]] = {
    3: {"region"},
    4: {"province"},
    6: {"municipality"},
    8: {"municipality", "barangay"},
    10: {"barangay"},
}
PARENT_LEVELS: dict[int, tuple[int, ...]] = {4: (3,), 6: (4, 3), 8: (6,), 10: (8, 6)}
PICK_LEVEL = {3: "region", 4: "province", 6: "municipality", 8: "municipality", 10: "barangay"}


@dataclass(frozen=True)
class BoundaryRow:
    osm_type: str
    osm_id: int
    admin_level: int
    name: str | None
    ref: str | None
    geom: MultiPolygon
    area_deg2: float


@dataclass(frozen=True)
class ResolvedBoundary:
    row: BoundaryRow
    psgc_code: str | None
    geographic_level: str | None
    parent_psgc_code: str | None
    resolution_method: str


@dataclass
class BoundaryExtractStats:
    boundaries: int = 0
    skipped: int = 0
    duplicates: int = 0
    elapsed_seconds: float = 0.0
    by_level: Counter[int] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parser_version": PARSER_VERSION,
            "boundaries": self.boundaries,
            "skipped": self.skipped,
            "duplicates": self.duplicates,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "by_level": {str(level): count for level, count in sorted(self.by_level.items())},
        }


@dataclass
class BoundaryImportStats:
    total: int = 0
    resolved: int = 0
    unresolved: int = 0
    release_label: str | None = None
    by_level: Counter[str] = field(default_factory=Counter)
    by_method: Counter[str] = field(default_factory=Counter)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_rows: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "parser_version": PARSER_VERSION,
            "release_label": self.release_label,
            "total": self.total,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "by_level": dict(sorted(self.by_level.items())),
            "by_method": dict(sorted(self.by_method.items())),
        }
        if include_rows:
            payload["boundaries"] = self.rows
        return payload


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 of one local source snapshot."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_multipolygon(geometry: Any) -> MultiPolygon | None:
    if geometry is None or geometry.is_empty:
        return None
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    parts = [part for part in getattr(geometry, "geoms", ()) if isinstance(part, Polygon)]
    return MultiPolygon(parts) if parts else None


class _BoundaryExtractor(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.rows: dict[tuple[str, int], BoundaryRow] = {}
        self.skipped = 0
        self.duplicates = 0

    def area(self, area: Any) -> None:
        tags = {tag.k: tag.v for tag in area.tags}
        if tags.get("boundary") != "administrative":
            return
        raw_level = _text(tags.get("admin_level"))
        if not raw_level or not raw_level.isdigit():
            return
        level = int(raw_level)
        if level not in LEVELS:
            return

        polygons: list[Polygon] = []
        for ring in area.outer_rings():
            coords = [(node.lon, node.lat) for node in ring]
            if len(coords) < 4:
                continue
            inners = [[(node.lon, node.lat) for node in inner] for inner in area.inner_rings(ring)]
            polygons.append(Polygon(coords, inners))
        if not polygons:
            self.skipped += 1
            return

        geometry = MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
        if not geometry.is_valid:
            geometry = shapely.make_valid(geometry)
        multipolygon = _as_multipolygon(geometry)
        if multipolygon is None:
            self.skipped += 1
            return

        osm_type = "way" if area.from_way() else "relation"
        key = (osm_type, int(area.id))
        row = BoundaryRow(
            osm_type=osm_type,
            osm_id=int(area.id),
            admin_level=level,
            name=_text(tags.get("name")),
            ref=_text(tags.get("ref")),
            geom=multipolygon,
            area_deg2=float(multipolygon.area),
        )
        previous = self.rows.get(key)
        if previous is not None:
            self.duplicates += 1
            if previous.area_deg2 >= row.area_deg2:
                return
        self.rows[key] = row


def extract_osm_boundaries(
    pbf_path: str | Path,
    output_path: str | Path,
    *,
    source_url: str,
    source_sha256: str | None = None,
    source_published_at: datetime | None = None,
    retrieved_at: datetime | None = None,
) -> BoundaryExtractStats:
    """Extract administrative boundary polygons from one PBF snapshot to Parquet."""

    source = Path(pbf_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    handler = _BoundaryExtractor()
    with tempfile.TemporaryDirectory(prefix="osm-boundary-node-cache-") as cache_dir:
        handler.apply_file(
            str(source),
            locations=True,
            idx=f"sparse_file_array,{Path(cache_dir) / 'nodes.cache'}",
            filters=[osmium.filter.TagFilter(("boundary", "administrative"))],
        )
    rows = sorted(
        handler.rows.values(), key=lambda row: (row.admin_level, row.osm_type, row.osm_id)
    )
    stats = BoundaryExtractStats(
        boundaries=len(rows),
        skipped=handler.skipped,
        duplicates=handler.duplicates,
        elapsed_seconds=time.monotonic() - started,
        by_level=Counter(row.admin_level for row in rows),
    )
    table = pa.table(
        {
            "osm_type": pa.array([row.osm_type for row in rows], pa.string()),
            "osm_id": pa.array([row.osm_id for row in rows], pa.int64()),
            "admin_level": pa.array([row.admin_level for row in rows], pa.int32()),
            "name": pa.array([row.name for row in rows], pa.string()),
            "ref": pa.array([row.ref for row in rows], pa.string()),
            "geometry": pa.array([shapely.to_wkb(row.geom) for row in rows], pa.binary()),
        }
    )
    pq.write_table(table, target)

    metadata = {
        **stats.to_dict(),
        "source_url": source_url,
        "source_sha256": source_sha256,
        "source_published_at": source_published_at.isoformat() if source_published_at else None,
        "retrieved_at": (retrieved_at or datetime.now(UTC)).isoformat(),
        "artifact": target.name,
    }
    target.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return stats


def read_boundary_parquet(path: str | Path) -> list[BoundaryRow]:
    table = pq.read_table(path)
    rows: list[BoundaryRow] = []
    for record in table.to_pylist():
        geometry = _as_multipolygon(shapely.from_wkb(record["geometry"]))
        if geometry is None:
            continue
        rows.append(
            BoundaryRow(
                osm_type=str(record["osm_type"]),
                osm_id=int(record["osm_id"]),
                admin_level=int(record["admin_level"]),
                name=_text(record.get("name")),
                ref=_text(record.get("ref")),
                geom=geometry,
                area_deg2=float(geometry.area),
            )
        )
    return rows


def _level_compatible(level: int, unit: AdministrativeUnit) -> bool:
    return unit.geographic_level in LEVELS.get(level, set())


def _resolve_boundaries(
    index: GeographyIndex,
    rows: Iterable[BoundaryRow],
) -> tuple[list[ResolvedBoundary], BoundaryImportStats]:
    by_level: dict[int, list[BoundaryRow]] = {level: [] for level in LEVELS}
    for row in rows:
        by_level[row.admin_level].append(row)

    resolved_by_level: dict[int, list[ResolvedBoundary]] = {level: [] for level in LEVELS}
    resolved: list[ResolvedBoundary] = []
    stats = BoundaryImportStats(total=sum(len(items) for items in by_level.values()))
    for level in sorted(LEVELS):
        parent_levels = PARENT_LEVELS.get(level, ())
        parents = [
            parent
            for parent_level in parent_levels
            for parent in resolved_by_level.get(parent_level, [])
            if parent.psgc_code
        ]
        parent_tree = STRtree([parent.row.geom for parent in parents]) if parents else None
        for row in by_level[level]:
            psgc_code: str | None = None
            geographic_level: str | None = None
            parent_psgc_code: str | None = None
            method = "unresolved"
            if row.ref:
                raw = _code(row.ref)
                code, ref_method, _ambiguous = (
                    index._lookup_code(raw) if raw else (None, None, False)
                )
                unit = index.by_code.get(code) if code else None
                if unit is not None and _level_compatible(level, unit):
                    psgc_code = unit.psgc_code
                    geographic_level = unit.geographic_level
                    parent_psgc_code = unit.parent_psgc_code
                    method = ref_method or "ref_exact"
            if psgc_code is None and row.name and parent_tree is not None:
                point = row.geom.representative_point()
                hits = parent_tree.query(point, predicate="covered_by")
                parent_codes = list(
                    {parents[int(hit)].psgc_code for hit in hits if parents[int(hit)].psgc_code}
                )
                parent_codes.sort(key=lambda code: index.depth(code), reverse=True)
                code, ambiguous = index._pick_name(PICK_LEVEL[level], row.name, parent_codes)
                unit = index.by_code.get(code) if code else None
                if unit is not None and not ambiguous and _level_compatible(level, unit):
                    psgc_code = unit.psgc_code
                    geographic_level = unit.geographic_level
                    parent_psgc_code = parent_codes[0] if parent_codes else None
                    method = "name_parent"
            boundary = ResolvedBoundary(
                row=row,
                psgc_code=psgc_code,
                geographic_level=geographic_level,
                parent_psgc_code=parent_psgc_code,
                resolution_method=method,
            )
            resolved.append(boundary)
            stats.by_level[str(level)] += 1
            stats.by_method[method] += 1
            if psgc_code:
                stats.resolved += 1
                resolved_by_level[level].append(boundary)
            else:
                stats.unresolved += 1
            stats.rows.append(
                {
                    "osm_type": row.osm_type,
                    "osm_id": row.osm_id,
                    "admin_level": row.admin_level,
                    "name": row.name,
                    "ref": row.ref,
                    "psgc_code": psgc_code,
                    "geographic_level": geographic_level,
                    "method": method,
                }
            )
    return resolved, stats


def _latest_real_release(session: Session) -> GeographicRelease | None:
    return session.scalars(
        select(GeographicRelease)
        .where(GeographicRelease.is_synthetic.is_(False))
        .order_by(GeographicRelease.retrieved_at.desc())
    ).first()


def import_osm_boundaries(
    session: Session,
    input_path: str | Path,
    *,
    release_label: str,
    source_url: str,
    source_sha256: str | None = None,
    source_published_at: datetime | None = None,
    retrieved_at: datetime | None = None,
    apply: bool = False,
    report_path: str | Path | None = None,
) -> BoundaryImportStats:
    """Resolve and store one boundary snapshot. Without ``apply`` this is a dry run."""

    release = _latest_real_release(session)
    if release is None:
        raise ValueError("No real PSGC release is loaded; refusing to resolve boundaries.")
    units = session.scalars(
        select(AdministrativeUnit).where(AdministrativeUnit.release_id == release.id)
    ).all()
    index = GeographyIndex(units)
    resolved, stats = _resolve_boundaries(index, read_boundary_parquet(input_path))
    stats.release_label = release_label

    if apply:
        session.execute(delete(OsmAdminBoundary))
        when = retrieved_at or datetime.now(UTC)
        for boundary in resolved:
            session.add(
                OsmAdminBoundary(
                    osm_type=boundary.row.osm_type,
                    osm_id=boundary.row.osm_id,
                    admin_level=boundary.row.admin_level,
                    name=boundary.row.name,
                    ref=boundary.row.ref,
                    psgc_code=boundary.psgc_code,
                    geographic_level=boundary.geographic_level,
                    parent_psgc_code=boundary.parent_psgc_code,
                    resolution_method=boundary.resolution_method,
                    geom=from_shape(boundary.row.geom, srid=4326),
                    area_deg2=boundary.row.area_deg2,
                    release_label=release_label,
                    source_url=source_url,
                    source_sha256=source_sha256,
                    source_published_at=source_published_at,
                    retrieved_at=when,
                )
            )
        session.commit()

    if report_path is not None:
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(stats.to_dict(), indent=2, default=str) + "\n", encoding="utf-8"
        )
    return stats


def boundary_artifacts(
    input_path: str | Path,
) -> tuple[list[BoundaryRow], dict[str, Any]]:
    """Read a boundary Parquet artifact and its optional metadata sidecar."""

    source = Path(input_path)
    rows = read_boundary_parquet(source)
    metadata_path = source.with_suffix(".json")
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return rows, metadata
