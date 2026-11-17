"""Geography and reference-data writers.

These releases update administrative reference tables rather than facilities, so
they have their own transaction and report path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from philfacilities_api.models import GeographicRelease, IngestionRun
from philfacilities_api.rights import PUBLICATION_INTERNAL_ONLY, PUBLICATION_PUBLISHED
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import IngestSettings, get_settings
from ..contracts import ReleaseSpec
from ..storage import RawStore, build_store
from .common import IngestResult
from .locking import dataset_ingestion_lock
from .release import _dataset_is_public, _write_report, ensure_source
from .stats import IngestStats


def run_geography_ingestion(
    *,
    spec: ReleaseSpec,
    units: list,
    warnings: list[str],
    session: Session,
    store: RawStore | None = None,
    settings: IngestSettings | None = None,
    previous_units_loader=None,
) -> IngestResult:
    """Persist one immutable geography release from any source adapter."""

    with dataset_ingestion_lock(
        session, agency_code=spec.agency_code, dataset_slug=spec.dataset_slug
    ):
        return _run_geography_ingestion_locked(
            spec=spec,
            units=units,
            warnings=warnings,
            session=session,
            store=store,
            settings=settings,
            previous_units_loader=previous_units_loader,
        )


def _run_geography_ingestion_locked(
    *,
    spec: ReleaseSpec,
    units: list,
    warnings: list[str],
    session: Session,
    store: RawStore | None,
    settings: IngestSettings | None,
    previous_units_loader,
) -> IngestResult:
    from ..sources.psgc import build_crosswalk

    settings = settings or get_settings()
    store = store or build_store(settings)
    _agency, dataset, gate = ensure_source(session, spec)
    preserved = store.preserve(
        agency=spec.agency_code,
        dataset=spec.dataset_slug,
        release_label=spec.release_label,
        filename=spec.filename,
        content=spec.content,
    )
    previous = session.scalars(
        select(GeographicRelease)
        .where(GeographicRelease.is_synthetic.is_(spec.is_synthetic))
        .order_by(GeographicRelease.reference_date.desc().nullslast())
    ).first()
    existing = session.scalars(
        select(GeographicRelease).where(GeographicRelease.release_label == spec.release_label)
    ).first()
    if existing:
        return IngestResult(
            dataset=spec.dataset_slug,
            release_label=spec.release_label,
            release_id=str(existing.id),
            status="skipped_duplicate",
            stats=IngestStats(units=len(units)).finish(),
        )
    geo = GeographicRelease(
        release_label=spec.release_label,
        reference_date=spec.reference_period_end,
        published_at=spec.source_published_at,
        retrieved_at=spec.retrieved_at or datetime.now(UTC),
        raw_object_uri=preserved.uri,
        sha256=preserved.sha256,
        source_url=spec.source_url,
        is_synthetic=spec.is_synthetic,
    )
    session.add(geo)
    session.flush()
    from philfacilities_api.models import AdministrativeUnit, GeographyCrosswalk

    for unit in units:
        session.add(
            AdministrativeUnit(
                release_id=geo.id,
                psgc_code=unit.psgc_code,
                name=unit.name,
                geographic_level=unit.geographic_level,
                parent_psgc_code=unit.parent_psgc_code,
                correspondence_code=unit.correspondence_code,
                old_name=unit.old_name,
                city_class=unit.city_class,
                income_classification=unit.income_classification,
                urban_rural=unit.urban_rural,
                island_region=unit.island_region,
                valid_from=spec.reference_period_start,
                valid_to=None,
            )
        )
    crosswalk_count = 0
    if previous and previous.id != geo.id:
        previous_units = None
        if previous_units_loader is not None:
            previous_units = previous_units_loader(previous, store)
        elif previous.raw_object_uri:
            from ..sources.psgc import parse_psgc_workbook

            previous_units, _ = parse_psgc_workbook(_read_raw(previous.raw_object_uri, store))
        if previous_units:
            for change in build_crosswalk(previous_units, units):
                session.add(
                    GeographyCrosswalk(
                        from_release_id=previous.id,
                        to_release_id=geo.id,
                        **change,
                    )
                )
                crosswalk_count += 1
    stats = IngestStats(
        units=len(units),
        by_level={
            level: sum(1 for unit in units if unit.geographic_level == level)
            for level in ("region", "province", "municipality", "barangay")
        },
        crosswalk_changes=crosswalk_count,
        warnings=warnings,
    ).finish()
    run = IngestionRun(
        dataset_id=dataset.id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status="published",
        stats=stats.snapshot(),
    )
    session.add(run)
    session.flush()
    public_geography = _dataset_is_public(dataset, gate)
    dataset.publication_status = (
        PUBLICATION_PUBLISHED if public_geography else PUBLICATION_INTERNAL_ONLY
    )
    json_path, md_path = _write_report(
        settings, spec=spec, run_id=run.id, status="published", stats=stats, issues=[]
    )
    run.report_path = json_path
    session.commit()
    return IngestResult(
        dataset=spec.dataset_slug,
        release_label=spec.release_label,
        release_id=str(geo.id),
        status="published",
        report_json=json_path,
        report_markdown=md_path,
        stats=stats,
    )


def run_psgc_ingestion(
    *,
    spec: ReleaseSpec,
    session: Session,
    store: RawStore | None = None,
    settings: IngestSettings | None = None,
) -> IngestResult:
    from ..sources.psgc import parse_psgc_workbook

    units, warnings = parse_psgc_workbook(spec.content)
    return run_geography_ingestion(
        spec=spec,
        units=units,
        warnings=warnings,
        session=session,
        store=store,
        settings=settings,
    )


def _read_raw(uri: str | None, store: RawStore) -> bytes:
    if not uri:
        raise ValueError("No raw object URI is stored for the previous release.")
    return store.read(uri)
