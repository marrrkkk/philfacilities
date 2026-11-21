"""Shared helpers for the PhilFacilities ingest CLI."""

from __future__ import annotations

import uuid
from datetime import date

import typer
from philfacilities_api.models import (
    Dataset,
    Facility,
    IngestionRun,
    Release,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..contracts import ReleaseSpec
from ..fixtures import (
    FIXTURE_PUBLISHED_AT,
    FIXTURE_RETRIEVED_AT,
    deped_enrollment,
    deped_masterlist,
    deped_resources,
    doh_csv,
    philhealth_pdf,
    psgc_workbook,
)
from ..matching import (
    MatchingError,
)
from ..pipeline import (
    build_engine,
    session_factory,
)
from ..sources.catalog import SOURCES
from ..sources.deped import DepEdEnrollmentAdapter, DepEdMasterlistAdapter, DepEdResourceAdapter
from ..sources.doh import DOHNHFRAdapter
from ..sources.philhealth import PhilHealthPdfAdapter

SYNTHETIC_AGENCY_NAMES = {
    "deped": "Department of Education (synthetic demo fixture)",
    "doh": "Department of Health (synthetic demo fixture)",
    "philhealth": "PhilHealth (synthetic demo fixture)",
    "psa": "Philippine Statistics Authority (synthetic demo fixture)",
}


def _session():
    settings = get_settings()
    engine = build_engine(settings)
    return engine, session_factory(engine)()


def _fixture_spec(
    *,
    agency_code: str,
    dataset_slug: str,
    dataset_name: str,
    release_label: str,
    filename: str,
    content: bytes,
    reference_start: date | None,
    reference_end: date | None,
    source_url: str | None = None,
) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code=agency_code,
        agency_name=SYNTHETIC_AGENCY_NAMES.get(agency_code, agency_code),
        dataset_slug=dataset_slug,
        dataset_name=dataset_name,
        release_label=release_label,
        filename=filename,
        content=content,
        source_url=source_url,
        source_published_at=FIXTURE_PUBLISHED_AT,
        retrieved_at=FIXTURE_RETRIEVED_AT,
        reference_period_start=reference_start,
        reference_period_end=reference_end,
        terms_url=None,
        redistribution_status="not_applicable",
        access_method="synthetic_fixture",
        update_pattern="generated for demonstration only",
        license_identifier="Synthetic fixture — no source-data rights",
        is_synthetic=True,
        notes=(
            "Synthetic demonstration fixture. Not a government release and not a claim about "
            "any real facility."
        ),
    )


def demo_specs() -> list[tuple[str, ReleaseSpec, object]]:
    """Return the ordered demo releases and their adapters."""

    specs: list[tuple[str, ReleaseSpec, object]] = []
    psgc_spec = _fixture_spec(
        agency_code="psa",
        dataset_slug="demo-psgc",
        dataset_name="Synthetic demo geography (PSGC-shaped)",
        release_label="SYNTHETIC-DEMO-2026-Q3",
        filename="synthetic-psgc-2026-q3.xlsx",
        content=psgc_workbook(),
        reference_start=date(2026, 7, 1),
        reference_end=date(2026, 9, 30),
    )
    specs.append(("psgc", psgc_spec, None))

    master_spec = _fixture_spec(
        agency_code="deped",
        dataset_slug="demo-deped-masterlist",
        dataset_name="Synthetic demo school masterlist",
        release_label="SYNTHETIC-DEMO-SY2024-2025",
        filename="synthetic-deped-masterlist-2024-2025.xlsx",
        content=deped_masterlist(),
        reference_start=date(2024, 6, 1),
        reference_end=date(2025, 3, 31),
    )
    specs.append(("deped-masterlist", master_spec, DepEdMasterlistAdapter(master_spec)))

    enrollment_spec = _fixture_spec(
        agency_code="deped",
        dataset_slug="demo-deped-enrollment",
        dataset_name="Synthetic demo school enrollment source file",
        release_label="SYNTHETIC-DEMO-SY2023-2025",
        filename="synthetic-deped-enrollment-2023-2025.xlsx",
        content=deped_enrollment(),
        reference_start=date(2023, 6, 1),
        reference_end=date(2025, 3, 31),
    )
    specs.append(("deped-enrollment", enrollment_spec, DepEdEnrollmentAdapter(enrollment_spec)))

    resources_spec = _fixture_spec(
        agency_code="deped",
        dataset_slug="demo-deped-resources",
        dataset_name="Synthetic demo school resource observations",
        release_label="SYNTHETIC-DEMO-SY2024-2025",
        filename="synthetic-deped-resources-2024-2025.xlsx",
        content=deped_resources(),
        reference_start=date(2024, 6, 1),
        reference_end=date(2025, 3, 31),
    )
    specs.append(("deped-resources", resources_spec, DepEdResourceAdapter(resources_spec)))

    doh_spec = _fixture_spec(
        agency_code="doh",
        dataset_slug="demo-doh-facilities",
        dataset_name="Synthetic demo health facilities",
        release_label="SYNTHETIC-DEMO-2026-09-30",
        filename="synthetic-doh-facilities-2026.csv",
        content=doh_csv(),
        reference_start=date(2026, 1, 1),
        reference_end=date(2026, 9, 30),
    )
    specs.append(("doh-facilities", doh_spec, DOHNHFRAdapter(doh_spec)))

    philhealth_spec = _fixture_spec(
        agency_code="philhealth",
        dataset_slug="demo-philhealth-accreditations",
        dataset_name="Synthetic demo PhilHealth-style accreditations",
        release_label="SYNTHETIC-DEMO-2026-09-30",
        filename="synthetic-philhealth-hospitals-2026-09-30.pdf",
        content=philhealth_pdf(),
        reference_start=date(2026, 9, 30),
        reference_end=date(2026, 9, 30),
    )
    specs.append(("philhealth-hospitals", philhealth_spec, PhilHealthPdfAdapter(philhealth_spec)))
    return specs


def _reset_demo(session: Session) -> None:
    from philfacilities_api.models import (
        GeographicRelease,
        PublicationGate,
        QualityIssue,
    )

    demo_dataset_ids = list(
        session.scalars(select(Dataset.id).where(Dataset.is_synthetic.is_(True))).all()
    )
    if demo_dataset_ids:
        demo_release_ids = set(
            session.scalars(
                select(Release.id).where(Release.dataset_id.in_(demo_dataset_ids))
            ).all()
        )
        demo_facilities = list(
            session.scalars(select(Facility).where(Facility.is_synthetic.is_(True))).all()
        )
        demo_facility_ids = [facility.id for facility in demo_facilities]
        issue_conditions = []
        if demo_facility_ids:
            issue_conditions.append(QualityIssue.facility_id.in_(demo_facility_ids))
        if demo_release_ids:
            issue_conditions.append(QualityIssue.release_id.in_(demo_release_ids))
        if issue_conditions:
            for issue in session.scalars(select(QualityIssue).where(or_(*issue_conditions))).all():
                session.delete(issue)
            session.flush()
        for facility in demo_facilities:
            session.delete(facility)
        session.flush()
        for release in session.scalars(
            select(Release).where(Release.dataset_id.in_(demo_dataset_ids))
        ).all():
            session.delete(release)
        for run in session.scalars(
            select(IngestionRun).where(IngestionRun.dataset_id.in_(demo_dataset_ids))
        ).all():
            session.delete(run)
        for gate in session.scalars(
            select(PublicationGate).where(PublicationGate.dataset_id.in_(demo_dataset_ids))
        ).all():
            session.delete(gate)
        session.flush()
        for dataset_id in demo_dataset_ids:
            dataset = session.get(Dataset, dataset_id)
            if dataset:
                session.delete(dataset)
        session.flush()
    for release in session.scalars(
        select(GeographicRelease).where(GeographicRelease.is_synthetic.is_(True))
    ).all():
        session.delete(release)
    session.flush()


def _review_candidate(
    action,
    candidate_id: uuid.UUID,
    reviewer: str,
    note: str | None,
) -> None:
    engine, session = _session()
    try:
        candidate = action(session, candidate_id, reviewer=reviewer, note=note)
        session.commit()
        typer.echo(f"{candidate.id} status={candidate.match_status} reviewer={candidate.reviewer}")
    except MatchingError as exc:
        session.rollback()
        typer.echo(f"Review failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _repair_agency_metadata(session: Session) -> None:
    """Remove the synthetic-demo label from agencies that now hold real data."""

    from philfacilities_api.models import Agency

    agencies = {
        definition.agency.code: (
            definition.agency.name,
            definition.agency.publisher_type,
        )
        for definition in SOURCES.values()
    }
    for code, (name, publisher_type) in agencies.items():
        agency = session.scalars(select(Agency).where(Agency.short_code == code)).first()
        if agency is None:
            continue
        if agency.name != name:
            agency.name = name
        if agency.publisher_type != publisher_type:
            agency.publisher_type = publisher_type
    session.flush()
