"""API routes split from the original sources router: downloads.

Decorators and route order are preserved; ``sources_common`` owns the shared
``APIRouter`` so ``/v1`` path ordering and OpenAPI output stay identical.
Bulk exports are produced in bounded pages so a national dataset does not have
to be materialised in memory before the first byte is sent.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..csv_safety import sanitize_csv_cell
from ..db import SessionLocal, get_db
from ..errors import ApiError
from ..models import (
    Agency,
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    Release,
    SourceRecord,
)
from ..publication import (
    latest_public_release_cte,
    public_dataset_condition,
    public_dataset_release_condition,
)
from ..services import public_facility_index_filter
from ..services.loaders import _chunked, _walk_ancestors, latest_geographic_release
from ..services.quality import _urban_rural
from .sources_common import _MATCH_STATUSES as _MATCH_STATUSES
from .sources_common import router as router
from .sources_common import settings as settings

# Output order is part of the download contract; keep it in one place so the
# streaming writer and the row builder cannot drift apart.
DOWNLOAD_COLUMNS = (
    "id",
    "slug",
    "display_name",
    "official_name",
    "facility_type",
    "facility_subtype",
    "facility_kind",
    "inclusion_class",
    "ownership",
    "ownership_type",
    "operator_type",
    "public_access_class",
    "record_status",
    "publication_status",
    "psgc_code",
    "psgc_release",
    "region_code",
    "region_name",
    "province_code",
    "province_name",
    "municipality_code",
    "municipality_name",
    "barangay_code",
    "barangay_name",
    "latitude",
    "longitude",
    "location_precision",
    "location_method",
    "address_text",
    "postal_code",
    "source_count",
    "source_records",
    "is_synthetic",
    "updated_at",
)

PAGE_SIZE = 10_000
PARQUET_BATCH_SIZE = 5_000


def _download_conditions(facility_type: str | None = None) -> list:
    # Bulk reads use the same indexed publication gate as the directory list.
    # The CTE-backed public_source_condition() is reserved for detail endpoints:
    # recomputing it for every export page dominated total export time. The gate
    # itself is unchanged -- both predicates resolve to publication_status=public.
    conditions = list(public_facility_index_filter())
    if facility_type:
        conditions.append(Facility.facility_type == facility_type)
    return conditions


def _iter_pages(
    db: Session, facility_type: str | None, page_size: int = PAGE_SIZE
) -> Iterator[list[Facility]]:
    """Yield publication-approved facilities in stable display-name order.

    Keyset pagination keeps each query bounded and preserves the historical CSV
    ordering (display name, then id) without a deep OFFSET.
    """

    conditions = _download_conditions(facility_type)
    after_name: str | None = None
    after_id = None
    while True:
        query = select(Facility).where(*conditions)
        if after_name is not None:
            query = query.where(
                or_(
                    Facility.display_name > after_name,
                    and_(
                        Facility.display_name == after_name,
                        Facility.id > after_id,
                    ),
                )
            )
        page = list(
            db.scalars(query.order_by(Facility.display_name, Facility.id).limit(page_size)).all()
        )
        if not page:
            return
        after_name = page[-1].display_name
        after_id = page[-1].id
        yield page


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _bulk_locations(db: Session, ids: list) -> dict:
    """Current public locations, using the same gate as the detail loaders."""

    result: dict = {}
    for chunk in _chunked(ids):
        rows = db.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id.in_(chunk),
                FacilityLocation.is_current.is_(True),
            )
        ).all()
        record_ids = {row.source_record_id for row in rows if row.source_record_id}
        public_ids: set = set()
        if record_ids:
            for part in _chunked(list(record_ids)):
                public_ids.update(
                    db.scalars(
                        select(SourceRecord.id)
                        .join(Release, SourceRecord.release_id == Release.id)
                        .join(Dataset, Release.dataset_id == Dataset.id)
                        .where(
                            SourceRecord.id.in_(part),
                            public_dataset_release_condition(),
                        )
                    ).all()
                )
        for row in rows:
            if row.source_record_id is not None and row.source_record_id not in public_ids:
                continue
            result.setdefault(row.facility_id, row)
    return result


def _bulk_evidence(db: Session, ids: list) -> dict:
    """Source references per facility, ordered exactly like the detail loader."""

    grouped: dict = defaultdict(list)
    latest = latest_public_release_cte()
    for chunk in _chunked(ids):
        rows = db.execute(
            select(
                FacilitySourceLink.facility_id,
                Agency.short_code,
                Dataset.slug,
                SourceRecord.source_record_key,
            )
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(latest, SourceRecord.release_id == latest.c.id)
            .join(Release, Release.id == latest.c.id)
            .join(Dataset, Dataset.id == latest.c.dataset_id)
            .join(Agency, Dataset.agency_id == Agency.id)
            .where(
                FacilitySourceLink.facility_id.in_(chunk),
                public_dataset_condition(),
            )
            .order_by(Release.retrieved_at.desc())
        ).all()
        for facility_id, agency_code, dataset_slug, source_key in rows:
            grouped[facility_id].append(f"{agency_code}:{dataset_slug}:{source_key}")
    return grouped


def _bulk_geography(db: Session, locations: dict) -> tuple[dict, str | None]:
    """Plain geography names per PSGC code (no Pydantic construction at scale)."""

    codes = {loc.psgc_code for loc in locations.values() if loc and loc.psgc_code}
    release = latest_geographic_release(db)
    if not codes or release is None:
        return {}, release.release_label if release else None
    units = _walk_ancestors(db, release.id, codes)
    result: dict = {}
    for code in codes:
        chain = []
        cursor = units.get(code)
        seen: set[str] = set()
        while cursor and cursor.psgc_code not in seen:
            seen.add(cursor.psgc_code)
            chain.append(cursor)
            cursor = units.get(cursor.parent_psgc_code) if cursor.parent_psgc_code else None
        by_level = {unit.geographic_level: unit for unit in chain}
        barangay = by_level.get("barangay")
        result[code] = {
            "psgc_code": code,
            "psgc_release": release.release_label,
            "region_code": by_level["region"].psgc_code if "region" in by_level else None,
            "region_name": by_level["region"].name if "region" in by_level else None,
            "province_code": by_level["province"].psgc_code if "province" in by_level else None,
            "province_name": by_level["province"].name if "province" in by_level else None,
            "municipality_code": (
                by_level["municipality"].psgc_code if "municipality" in by_level else None
            ),
            "municipality_name": (
                by_level["municipality"].name if "municipality" in by_level else None
            ),
            "barangay_code": barangay.psgc_code if barangay else None,
            "barangay_name": barangay.name if barangay else None,
            "urban_rural": _urban_rural(barangay.urban_rural if barangay else None),
        }
    return result, release.release_label


def _iter_row_dicts(db: Session, facilities: list[Facility]) -> Iterator[dict]:
    """Build export rows for one bounded page without Pydantic round-trips."""

    ids = [facility.id for facility in facilities]
    locations = _bulk_locations(db, ids)
    evidence = _bulk_evidence(db, ids)
    geographies, _release_label = _bulk_geography(db, locations)
    for facility in facilities:
        loc = locations.get(facility.id)
        psgc = loc.psgc_code if loc and loc.psgc_code else None
        geo = geographies.get(psgc or "", {})
        if not geo and psgc:
            geo = {"psgc_code": psgc}
        sources = evidence.get(facility.id, [])
        yield {
            "id": str(facility.id),
            "slug": facility.slug or "",
            "display_name": facility.display_name,
            "official_name": facility.official_name or "",
            "facility_type": facility.facility_type,
            "facility_subtype": facility.facility_subtype or "",
            "facility_kind": facility.facility_kind,
            "inclusion_class": facility.inclusion_class,
            "ownership": facility.ownership,
            "ownership_type": facility.ownership_type,
            "operator_type": facility.operator_type,
            "public_access_class": facility.public_access_class,
            "record_status": facility.record_status,
            "publication_status": facility.publication_status,
            "psgc_code": geo.get("psgc_code") or "",
            "psgc_release": geo.get("psgc_release") or "",
            "region_code": geo.get("region_code") or "",
            "region_name": geo.get("region_name") or "",
            "province_code": geo.get("province_code") or "",
            "province_name": geo.get("province_name") or "",
            "municipality_code": geo.get("municipality_code") or "",
            "municipality_name": geo.get("municipality_name") or "",
            "barangay_code": geo.get("barangay_code") or "",
            "barangay_name": geo.get("barangay_name") or "",
            "latitude": _decimal_to_float(loc.latitude) if loc else None,
            "longitude": _decimal_to_float(loc.longitude) if loc else None,
            "location_precision": loc.precision if loc else "unknown",
            "location_method": loc.method or "" if loc else "",
            "address_text": loc.address_text or "" if loc else "",
            "postal_code": loc.postal_code or "" if loc else "",
            "source_count": len(sources),
            "source_records": "; ".join(sources),
            "is_synthetic": facility.is_synthetic,
            "updated_at": facility.updated_at.isoformat(),
        }


def _download_rows(db: Session, facility_type: str | None) -> list[dict]:
    """Materialise every export row (kept for callers that need a list)."""

    rows: list[dict] = []
    for page in _iter_pages(db, facility_type):
        rows.extend(_iter_row_dicts(db, page))
    return rows


def _assert_has_rows(db: Session, facility_type: str | None) -> None:
    first = db.scalars(
        select(Facility.id).where(*_download_conditions(facility_type)).limit(1)
    ).first()
    if not first:
        raise ApiError(404, "no_downloadable_data", "No publication-approved facility rows exist.")


def _stream_csv(name: str, facility_type: str | None, db: Session) -> StreamingResponse:
    _assert_has_rows(db, facility_type)

    def generate() -> Iterator[bytes]:
        # The generator runs after the route returns, so it owns its session.
        # Yield in bounded batches: one HTTP chunk per row would add hundreds of
        # thousands of middleware and socket round-trips to a national export.
        with SessionLocal() as stream_db:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(DOWNLOAD_COLUMNS))
            writer.writeheader()
            pending = buffer.getvalue()
            for page in _iter_pages(stream_db, facility_type):
                for row in _iter_row_dicts(stream_db, page):
                    buffer.seek(0)
                    buffer.truncate(0)
                    writer.writerow({key: sanitize_csv_cell(value) for key, value in row.items()})
                    pending += buffer.getvalue()
                    if len(pending) >= 64 * 1024:
                        yield pending.encode("utf-8")
                        pending = ""
            if pending:
                yield pending.encode("utf-8")

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="philfacilities-{name}-{date.today().isoformat()}.csv"'
            )
        },
    )


def _build_parquet(db: Session, facility_type: str | None) -> bytes:
    _assert_has_rows(db, facility_type)
    sink = io.BytesIO()
    writer: pq.ParquetWriter | None = None
    try:
        for page in _iter_pages(db, facility_type):
            rows = list(_iter_row_dicts(db, page))
            for start in range(0, len(rows), PARQUET_BATCH_SIZE):
                batch = rows[start : start + PARQUET_BATCH_SIZE]
                table = pa.Table.from_pylist(batch)
                if writer is None:
                    writer = pq.ParquetWriter(sink, table.schema, compression="zstd")
                writer.write_table(table)
        if writer is None:
            raise ApiError(
                404, "no_downloadable_data", "No publication-approved facility rows exist."
            )
    finally:
        if writer is not None:
            writer.close()
    return sink.getvalue()


@router.get("/downloads/facilities.csv", summary="Bulk facility CSV")
def download_facilities_csv(db: Annotated[Session, Depends(get_db)]):
    return _stream_csv("facilities", None, db)


@router.get("/downloads/schools.csv", summary="Bulk school CSV")
def download_schools_csv(db: Annotated[Session, Depends(get_db)]):
    return _stream_csv("schools", "school", db)


@router.get("/downloads/health-facilities.csv", summary="Bulk health facility CSV")
def download_health_csv(db: Annotated[Session, Depends(get_db)]):
    return _stream_csv("health-facilities", "health_facility", db)


@router.get("/downloads/facilities.parquet", summary="Bulk facility Parquet")
def download_facilities_parquet(db: Annotated[Session, Depends(get_db)]):
    return Response(
        content=_build_parquet(db, None),
        media_type="application/vnd.apache.parquet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="philfacilities-{date.today().isoformat()}.parquet"'
            )
        },
    )
