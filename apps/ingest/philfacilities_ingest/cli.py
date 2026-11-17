"""Command-line entry point for PhilFacilities ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer
from philfacilities_api.models import (
    Dataset,
    Facility,
    IngestionRun,
    MatchCandidate,
    Release,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .acquisition import (
    AcquisitionError,
    HttpAcquirer,
    actionable_failures,
    classify_response,
    record_check,
    send_failure_alert,
    validate_signature,
)
from .assertions import backfill_assertions
from .compare import ReleaseComparisonError, compare_releases
from .config import get_settings
from .contracts import ReleaseSpec
from .discovery import DISCOVERY_TARGETS, probe_discovery_targets
from .fixtures import (
    FIXTURE_PUBLISHED_AT,
    FIXTURE_RETRIEVED_AT,
    all_fixtures,
    deped_enrollment,
    deped_masterlist,
    deped_resources,
    doh_csv,
    philhealth_pdf,
    psgc_workbook,
)
from .lgu_inventory import validate_inventory
from .manifest import render_release_notes, write_release_manifest
from .matching import (
    MatchingError,
    accept_match_candidate,
    generate_match_candidates,
    merge_match_candidate,
    reject_match_candidate,
    undo_match_merge,
)
from .pipeline import (
    build_engine,
    ensure_source,
    run_geography_ingestion,
    run_ingestion,
    run_psgc_ingestion,
    session_factory,
)
from .release_rollback import ReleaseRollbackError, rollback_release
from .scraper import CrawlPolicy, crawl, summary_json
from .source_candidates import (
    load_source_candidates,
    summarize_source_candidates,
    validate_source_candidates,
)
from .source_inventory import (
    build_source_inventory,
    summarize_source_inventory,
    validate_source_inventory,
    write_source_inventory,
)
from .sources.bettergov import OSMParquetAdapter, load_psgc_release_payload
from .sources.bettergov_stats import (
    CENSUS_2024_DATASET_IDS,
    fetch_population_snapshot,
    load_population_snapshot,
)
from .sources.bir import BirRevenueDistrictOfficeAdapter
from .sources.cainta import CaintaHealthCenterAdapter, fetch_cainta_health_centers
from .sources.ched_heida import ChedHeidaAdapter, fetch_heida_directory
from .sources.deped import DepEdEnrollmentAdapter, DepEdMasterlistAdapter, DepEdResourceAdapter
from .sources.deped_ebeis import DepEdEBEISAdapter
from .sources.doh import DOHNHFRAdapter
from .sources.dswd_crcf import DswdCrcfDirectoryAdapter
from .sources.dti_negosyo import DtiNegosyoCenterAdapter, fetch_negosyo_centers
from .sources.mandaluyong import MandaluyongBarangayAdapter, fetch_mandaluyong_directory
from .sources.national_museum import NationalMuseumDirectoryAdapter, fetch_national_museum_directory
from .sources.nbi import NbiOfficeAdapter, fetch_nbi_offices
from .sources.nlp import NlpPublicLibraryPdfAdapter
from .sources.nmis_naris import NmisNarisDirectoryAdapter
from .sources.pagasa_aws import PagasaAwsAdapter, fetch_pagasa_aws
from .sources.pasay import PasayHealthCenterAdapter, fetch_pasay_health_centers
from .sources.philhealth import PhilHealthPdfAdapter
from .sources.philhealth_offices import PhilHealthOfficeAdapter, fetch_philhealth_offices
from .sources.phlpost import PhlPostLocatorAdapter
from .sources.ppa import PpaPortListAdapter
from .sources.quezon_city import QuezonCityLguAdapter, fetch_quezon_city_directory
from .sources.quezon_city_places import QuezonCityPlacesAdapter, fetch_quezon_city_places
from .sources.registry import (
    EBEIS_REGIONS,
    REAL_SOURCES,
    apply_publication_decisions,
    check_sources,
    due_source_keys,
    fetch_ebeis_region,
    fetch_psgc_collections,
    latest_checks,
    philhealth_catalog,
    philhealth_dataset_slug,
    psgc_release_content,
    psgc_units,
    source_review_rows,
    source_spec,
)
from .sources.sss_branch import SssBranchAdapter, fetch_sss_branches

app = typer.Typer(
    add_completion=False,
    help="Source acquisition, repeatable ingestion, reports, and status for PhilFacilities.",
)

SYNTHETIC_AGENCY_NAMES = {
    "deped": "Department of Education (synthetic demo fixture)",
    "doh": "Department of Health (synthetic demo fixture)",
    "philhealth": "PhilHealth (synthetic demo fixture)",
    "psa": "Philippine Statistics Authority (synthetic demo fixture)",
}

REAL_AGENCY_METADATA = {
    "bettergov": ("BetterGov.PH", "community"),
    "ched": ("Commission on Higher Education", "government"),
    "deped": ("Department of Education", "government"),
    "doh": ("Department of Health", "government"),
    "dswd": ("Department of Social Welfare and Development", "government"),
    "nlp": ("National Library of the Philippines", "government"),
    "nmp": ("National Museum of the Philippines", "government"),
    "nbi": ("National Bureau of Investigation", "government"),
    "nmis": ("National Meat Inspection Service", "government"),
    "osm": ("OpenStreetMap contributors (via HOT and BetterGov.PH)", "community"),
    "philhealth": ("Philippine Health Insurance Corporation", "government"),
    "phlpost": ("Philippine Postal Corporation", "government"),
    "ppa": ("Philippine Ports Authority", "government"),
    "psa": ("Philippine Statistics Authority", "government"),
    "sss": ("Social Security System", "government"),
    "pagasa": (
        "Philippine Atmospheric, Geophysical and Astronomical Services Administration",
        "government",
    ),
    "tesda": ("Technical Education and Skills Development Authority", "government"),
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
        dataset_name="Synthetic demo school enrollment observations",
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


@app.command("generate-fixtures")
def generate_fixtures(
    output: Annotated[Path, typer.Option(help="Directory for generated fixture files.")] = Path(
        "database/fixtures/synthetic"
    ),
) -> None:
    """Write deterministic synthetic fixture files and a checksum manifest."""

    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for fixture in all_fixtures():
        target = output / fixture.name
        target.write_bytes(fixture.content)
        manifest.append(
            {
                "filename": fixture.name,
                "bytes": len(fixture.content),
                "sha256": hashlib.sha256(fixture.content).hexdigest(),
                "synthetic": True,
                "notice": "Synthetic demonstration data; not an official government release.",
            }
        )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "purpose": "Deterministic synthetic fixtures for PhilFacilities tests and demo.",
                "files": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Wrote {len(manifest)} synthetic fixtures to {output}")


@app.command("load-demo")
def load_demo(
    reset: Annotated[bool, typer.Option(help="Delete existing demo facilities first.")] = False,
) -> None:
    """Load the complete synthetic demonstration dataset through the real pipeline."""

    settings = get_settings()
    engine, session = _session()
    try:
        if reset:
            _reset_demo(session)
            session.commit()
        for name, spec, adapter in demo_specs():
            typer.echo(f"→ {name}: {spec.release_label}")
            if adapter is None:
                result = run_psgc_ingestion(spec=spec, session=session, settings=settings)
            else:
                result = run_ingestion(
                    spec=spec, adapter=adapter, session=session, settings=settings
                )
            if "facilities_created" in result.stats:
                created_label = "facilities_created"
                created_count = result.stats["facilities_created"]
            else:
                created_label = "units_created"
                created_count = result.stats.get("units", 0)
            typer.echo(f"  {result.status} · {created_label}={created_count}")
            if result.issues:
                typer.echo(f"  warnings/issues: {len(result.issues)}")
        session.commit()
        typer.echo("Synthetic demo data loaded. All records are labelled is_synthetic=true.")
    finally:
        session.close()
        engine.dispose()


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


@app.command("ingest-file")
def ingest_file(
    source: Annotated[
        str, typer.Argument(help="deped, deped-enrollment, deped-resources, doh, philhealth, psgc")
    ],
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Source file")],
    release_label: Annotated[str, typer.Option(help="Agency release label")],
    dataset: Annotated[str, typer.Option(help="Dataset slug")],
    reference_start: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
    reference_end: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
    source_url: Annotated[str | None, typer.Option(help="Official source URL")] = None,
    redistribution_status: Annotated[
        str,
        typer.Option(
            help=(
                "unknown, restricted, permission_required, allowed_with_conditions, "
                "allowed, not_applicable"
            )
        ),
    ] = "unknown",
    agency: Annotated[str, typer.Option(help="Agency short code")] = "unknown",
    agency_name: Annotated[str | None, typer.Option(help="Agency display name")] = None,
    is_synthetic: Annotated[bool, typer.Option(help="Mark as synthetic fixture")] = False,
) -> None:
    """Ingest one real or synthetic source file through its adapter."""

    content = path.read_bytes()
    spec = ReleaseSpec(
        agency_code=agency,
        agency_name=agency_name or agency,
        dataset_slug=dataset,
        dataset_name=dataset.replace("-", " ").title(),
        release_label=release_label,
        filename=path.name,
        content=content,
        source_url=source_url,
        source_published_at=None,
        retrieved_at=datetime.now(UTC),
        reference_period_start=date.fromisoformat(reference_start) if reference_start else None,
        reference_period_end=date.fromisoformat(reference_end) if reference_end else None,
        redistribution_status=redistribution_status,
        access_method="manual_file",
        is_synthetic=is_synthetic,
        notes=(
            "Acquired through the documented manual file flow; terms must be reviewed "
            "before publication."
        ),
    )
    settings = get_settings()
    engine, session = _session()
    try:
        if source == "psgc":
            result = run_psgc_ingestion(spec=spec, session=session, settings=settings)
        else:
            adapters = {
                "deped": DepEdMasterlistAdapter,
                "deped-enrollment": DepEdEnrollmentAdapter,
                "deped-resources": DepEdResourceAdapter,
                "doh": DOHNHFRAdapter,
                "philhealth": PhilHealthPdfAdapter,
            }
            if source not in adapters:
                raise typer.BadParameter(f"Unknown source {source!r}.")
            result = run_ingestion(
                spec=spec, adapter=adapters[source](spec), session=session, settings=settings
            )
        session.commit()
        typer.echo(json.dumps(result.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("status")
def status() -> None:
    """Show measured database counts and latest ingestion runs."""

    engine, session = _session()
    try:
        facilities = session.scalar(select(func.count()).select_from(Facility)) or 0
        datasets = session.scalar(select(func.count()).select_from(Dataset)) or 0
        releases = session.scalar(select(func.count()).select_from(Release)) or 0
        synthetic = (
            session.scalar(
                select(func.count()).select_from(Facility).where(Facility.is_synthetic.is_(True))
            )
            or 0
        )
        typer.echo(
            f"facilities={facilities} synthetic={synthetic} datasets={datasets} releases={releases}"
        )
        for run, slug in session.execute(
            select(IngestionRun, Dataset.slug)
            .join(Dataset, IngestionRun.dataset_id == Dataset.id)
            .order_by(IngestionRun.started_at.desc())
            .limit(10)
        ).all():
            typer.echo(
                f"  {run.started_at:%Y-%m-%d %H:%M} {slug}: {run.status} "
                f"report={run.report_path or '—'}"
            )
    finally:
        session.close()
        engine.dispose()


@app.command("source-candidates")
def source_candidates_command(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Candidate registry JSON. Defaults to expand/source-candidates.json.",
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the validation summary as JSON.")
    ] = False,
) -> None:
    """Validate the researched source-candidate inventory.

    This does not acquire, register, or publish a source. It catches duplicate
    IDs, missing custodians/URLs, and invalid state values before the register
    is used for acquisition decisions.
    """

    payload = load_source_candidates(path)
    errors = validate_source_candidates(payload)
    summary = summarize_source_candidates(payload)
    if as_json:
        typer.echo(json.dumps({"summary": summary, "errors": errors}, indent=2))
    else:
        typer.echo(f"source candidates: {summary['total']}")
        typer.echo(f"evidence: {summary['by_evidence_state']}")
        typer.echo(f"access: {summary['by_access_state']}")
        typer.echo(f"rights: {summary['by_rights_state']}")
        typer.echo(f"coverage: {summary['by_coverage_scope']}")
        if errors:
            for error in errors:
                typer.echo(f"ERROR: {error}", err=True)
        else:
            typer.echo("validation: ok")
    if errors:
        raise typer.Exit(code=1)


@app.command("source-inventory")
def source_inventory_command(
    register: Annotated[
        Path | None,
        typer.Option(
            "--register",
            help="Source register Markdown. Defaults to expand/docs/03-SOURCE-REGISTER.md.",
        ),
    ] = None,
    candidates: Annotated[
        Path | None,
        typer.Option(
            "--candidates",
            help="Candidate registry JSON. Defaults to expand/source-candidates.json.",
        ),
    ] = None,
    probes: Annotated[
        Path | None,
        typer.Option(
            "--probes",
            help="Probe ledger. Defaults to the 16 Nov 2026 category-search ledger.",
        ),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="Merged inventory JSON output path."),
    ] = None,
    csv_output: Annotated[
        Path | None,
        typer.Option("--csv-output", help="Merged inventory CSV output path."),
    ] = None,
    check: Annotated[
        bool,
        typer.Option("--check", help="Validate only; do not write the JSON/CSV inventory."),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the validation summary as JSON.")
    ] = False,
) -> None:
    """Merge the register, candidate registry and probe ledgers into one inventory.

    An inventory row is still a candidate. This command does not acquire a
    source, approve rights, create a release, or publish records. Probe results
    are preserved, including HTTP 403, DNS and TLS failures.
    """

    payload = build_source_inventory(register, candidates, probes)
    errors = validate_source_inventory(payload)
    summary = summarize_source_inventory(payload)
    written: tuple[Path, Path] | None = None
    if not errors and not check:
        written = write_source_inventory(payload, json_output, csv_output)
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "summary": summary,
                    "errors": errors,
                    "written": [str(path) for path in written or ()],
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"source inventory: {summary['total']} candidates")
        typer.echo(
            f"register={summary['from_register']} candidates={summary['from_candidates']} "
            f"probed={summary['probed']} unmatched_probes={summary['unmatched_probes']}"
        )
        typer.echo(f"published={summary['published']} internal_only={summary['internal_only']}")
        typer.echo(f"category: {summary['by_category']}")
        typer.echo(f"access: {summary['by_access_state']}")
        typer.echo(f"evidence: {summary['by_evidence_state']}")
        typer.echo(f"coverage: {summary['by_coverage_scope']}")
        if written:
            typer.echo(f"wrote: {written[0]}")
            typer.echo(f"wrote: {written[1]}")
        if errors:
            for error in errors:
                typer.echo(f"ERROR: {error}", err=True)
        else:
            typer.echo("validation: ok")
    if errors:
        raise typer.Exit(code=1)


@app.command("validate-lgu-inventory")
def validate_lgu_inventory_command(
    path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, help="LGU inventory CSV to validate."),
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the validation summary as JSON.")
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write the full validation report as JSON."),
    ] = None,
) -> None:
    """Validate an LGU facility-inventory submission without importing it.

    A valid row is still a proposal. This command only checks schema, taxonomy,
    geography and provenance shape; it never publishes records, infers ownership,
    or accepts personal/security-sensitive columns.
    """

    result = validate_inventory(path)
    payload = result.as_dict()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(
            f"rows={result.rows} accepted={result.accepted} rejected={result.rejected} "
            f"issues={len(result.issues)}"
        )
        for issue in result.issues:
            typer.echo(
                f"{issue.severity.upper()} row={issue.row_number or '-'} "
                f"{issue.code}: {issue.message}"
            )
        if output is not None:
            typer.echo(f"report={output}")
    if result.rejected or any(issue.severity == "fatal" for issue in result.issues):
        raise typer.Exit(code=1)


@app.command("backfill-assertions")
def backfill_assertions_command() -> None:
    """Reconstruct exact field claims from existing source-linked child rows.

    This does not re-download a source and does not guess provenance for
    facility-level fields that several sources could have supplied.
    """

    engine, session = _session()
    try:
        stats = backfill_assertions(session)
        session.commit()
        typer.echo(json.dumps(stats.as_dict(), indent=2))
    finally:
        session.close()
        engine.dispose()


@app.command("match-candidates-generate")
def match_candidates_generate() -> None:
    """Scan existing source links and queue deterministic duplicate candidates."""

    engine, session = _session()
    try:
        stats = generate_match_candidates(session)
        session.commit()
        typer.echo(json.dumps(stats, indent=2))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("match-candidates")
def match_candidates_list(
    status: Annotated[
        str | None, typer.Option(help="pending, accepted, rejected, merged, or all")
    ] = "pending",
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
) -> None:
    """List identity-match candidates and their review state."""

    engine, session = _session()
    try:
        query = select(MatchCandidate).order_by(MatchCandidate.created_at.desc()).limit(limit)
        if status and status != "all":
            query = query.where(MatchCandidate.match_status == status)
        rows = session.scalars(query).all()
        counts = dict(
            session.execute(
                select(MatchCandidate.match_status, func.count()).group_by(
                    MatchCandidate.match_status
                )
            ).all()
        )
        typer.echo(
            "counts="
            + json.dumps(
                {key: counts.get(key, 0) for key in ("pending", "accepted", "rejected", "merged")}
            )
        )
        if not rows:
            typer.echo("No match candidates.")
            return
        for row in rows:
            typer.echo(
                f"{row.id} {row.match_status} confidence={float(row.match_confidence):.3f} "
                f"{row.source_agency_code}:{row.source_facility_id} -> "
                f"{row.candidate_agency_code}:{row.candidate_facility_id}"
            )
    finally:
        session.close()
        engine.dispose()


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


@app.command("match-candidates-accept")
def match_candidates_accept(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for the decision.")] = None,
) -> None:
    """Confirm a candidate as the same facility. Merging is a separate explicit step."""

    _review_candidate(accept_match_candidate, candidate_id, reviewer, note)


@app.command("match-candidates-reject")
def match_candidates_reject(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for the decision.")] = None,
) -> None:
    """Reject a candidate and retain it so the pair is not re-queued."""

    _review_candidate(reject_match_candidate, candidate_id, reviewer, note)


@app.command("match-candidates-merge")
def match_candidates_merge(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for the merge.")] = None,
) -> None:
    """Apply an accepted candidate: retire the source facility into the candidate facility."""

    _review_candidate(merge_match_candidate, candidate_id, reviewer, note)


@app.command("match-candidates-undo-merge")
def match_candidates_undo_merge(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for undoing the merge.")] = None,
) -> None:
    """Undo a merge and restore the source facility and its linked evidence."""

    _review_candidate(undo_match_merge, candidate_id, reviewer, note)


@app.command("check-sources")
def check_sources_command(
    source: Annotated[
        list[str] | None,
        typer.Option("--source", "-s", help="Repeat to check only selected source keys."),
    ] = None,
) -> None:
    """Probe every registered real source and append monitoring evidence.

    Blocked endpoints are recorded as blocked. This command never bypasses an
    access control, never accepts a licence on the operator's behalf, and never
    publishes a release.
    """

    engine, session = _session()
    try:
        results = check_sources(session, keys=source)
        typer.echo(json.dumps(results, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("apply-publication-decisions")
def apply_publication_decisions_command(
    source: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            "-s",
            help=(
                "Repeat to reconcile selected source keys. Omit to reconcile existing "
                "datasets only."
            ),
        ),
    ] = None,
) -> None:
    """Reconcile stored dataset rights/gates with the reviewed source registry.

    This does not ingest or publish records. Reprocess the affected releases
    afterwards so their records inherit the updated gate.
    """

    engine, session = _session()
    try:
        results = apply_publication_decisions(session, keys=source)
        typer.echo(json.dumps(results, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("check-due-sources")
def check_due_sources_command(
    source: Annotated[
        list[str] | None,
        typer.Option("--source", "-s", help="Repeat to consider only selected source keys."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Check selected sources regardless of next_check_at.")
    ] = False,
) -> None:
    """Run source checks whose recorded next_check_at is due.

    Designed for a cron/systemd timer or CI schedule. Exit status is 2 when a
    check needs operator action (request failure, schema change, or source error);
    known access blocks remain recorded without causing a false incident.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        keys = due_source_keys(session, keys=source, force=force)
        if not keys:
            typer.echo("No source checks are due.")
            return
        typer.echo(f"Checking {len(keys)} due source(s): {', '.join(keys)}")
        results = check_sources(session, keys=keys)
        alerted = send_failure_alert(settings, results, command="check-due-sources")
        typer.echo(json.dumps(results, indent=2, default=str))
        if alerted:
            typer.echo("Failure alert sent to the configured webhook.")
        failures = actionable_failures(results)
        if failures:
            typer.echo(f"Actionable failures: {', '.join(sorted(failures))}", err=True)
            raise typer.Exit(code=2)
    finally:
        session.close()
        engine.dispose()


@app.command("monitoring")
def monitoring() -> None:
    """Show the latest append-only source check for every monitored dataset."""

    engine, session = _session()
    try:
        rows = latest_checks(session)
        if not rows:
            typer.echo("No source checks recorded. Run 'philfacilities-ingest check-sources'.")
            return
        for row in rows:
            typer.echo(
                f"{row['checked_at']:%Y-%m-%d %H:%M} {row['dataset_slug']}: "
                f"{row['status']} http={row['http_status']} — {row['message']}"
            )
    finally:
        session.close()
        engine.dispose()


@app.command("source-review")
def source_review_command(
    days: Annotated[
        int, typer.Option(min=1, help="Flag sources not checked within this many days.")
    ] = 30,
    json_output: Annotated[bool, typer.Option("--json", help="Emit the review as JSON.")] = False,
) -> None:
    """List the monthly review state of every registered source link and rights entry."""

    engine, session = _session()
    try:
        rows = source_review_rows(session, days=days)
    finally:
        session.close()
        engine.dispose()
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
        return
    due = [row for row in rows if row["review_due"]]
    typer.echo(f"registered={len(rows)} review_due={len(due)} window_days={days}")
    for row in rows:
        marker = "DUE" if row["review_due"] else "ok"
        last = row["last_checked_at"] or "never"
        typer.echo(
            f"{marker:3} {row['source_key']}: {row['agency']} | "
            f"checked={last} status={row['last_check_status'] or 'unchecked'} | "
            f"{row['rights']}/{row['publication_status']}"
        )


@app.command("compare-releases")
def compare_releases_command(
    dataset_slug: Annotated[str, typer.Argument(help="Dataset slug, e.g. philhealth-hosp.")],
    from_label: Annotated[str | None, typer.Option("--from", help="Earlier release label.")] = None,
    to_label: Annotated[str | None, typer.Option("--to", help="Later release label.")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the comparison as JSON.")
    ] = False,
) -> None:
    """Compare two retained releases of one dataset without mutating either one."""

    engine, session = _session()
    try:
        report = compare_releases(
            session,
            dataset_slug=dataset_slug,
            from_label=from_label,
            to_label=to_label,
        )
    except ReleaseComparisonError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        session.close()
        engine.dispose()

    if json_output:
        typer.echo(json.dumps(report, indent=2, default=str))
        return

    source = report["source_records"]
    links = report["facility_links"]
    typer.echo(f"dataset={report['dataset']['slug']} {report['dataset']['name']}")
    typer.echo(
        f"from={report['from']['release_label']} rows={report['from']['row_count_parsed']} "
        f"status={report['from']['ingestion_status']}/{report['from']['publication_status']}"
    )
    typer.echo(
        f"to={report['to']['release_label']} rows={report['to']['row_count_parsed']} "
        f"status={report['to']['ingestion_status']}/{report['to']['publication_status']}"
    )
    typer.echo(
        f"source_records from={source['from']} to={source['to']} added={source['added']} "
        f"removed={source['removed']} retained={source['retained']} "
        f"changed_payload={source['changed_payload']}"
    )
    typer.echo(
        f"facility_links from={links['from']} to={links['to']} added={links['added']} "
        f"removed={links['removed']} retained={links['retained']}"
    )
    for label, keys in (
        ("added", source["sample_added"]),
        ("removed", source["sample_removed"]),
        ("changed_payload", source["sample_changed_payload"]),
    ):
        if keys:
            typer.echo(f"sample_{label}: {', '.join(keys)}")


@app.command("release-manifest")
def release_manifest_command(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Write the release manifest to this JSON path."),
    ] = Path("var/reports/release-manifest.json"),
) -> None:
    """Write a versioned manifest of published source releases and known gaps."""

    engine, session = _session()
    try:
        manifest = write_release_manifest(session, output)
    finally:
        session.close()
        engine.dispose()
    totals = manifest["totals"]
    typer.echo(f"wrote {output}")
    typer.echo(
        f"datasets_included={totals['datasets_included']} "
        f"datasets_excluded={totals['datasets_excluded']} "
        f"published_facilities={totals['published_facilities']}"
    )
    typer.echo(f"checksum={manifest['checksum']}")


@app.command("release-notes")
def release_notes_command(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Write Markdown release notes to this path."),
    ] = Path("var/reports/release-notes.md"),
) -> None:
    """Write public release notes with coverage, gaps, exclusions and caveats."""

    engine, session = _session()
    try:
        manifest = write_release_manifest(session, output.with_suffix(".manifest.json"))
    finally:
        session.close()
        engine.dispose()
    notes = render_release_notes(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(notes, encoding="utf-8")
    typer.echo(f"wrote {output} ({len(notes.splitlines())} lines)")
    typer.echo(f"manifest_checksum={manifest['checksum']}")


@app.command("release-rollback")
def release_rollback_command(
    dataset_slug: Annotated[str, typer.Argument(help="Dataset slug to roll back.")],
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    release_label: Annotated[
        str | None,
        typer.Option("--release", help="Release label; defaults to the latest release."),
    ] = None,
    note: Annotated[str | None, typer.Option(help="Reason for the rollback.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate and count without changing data.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the result as JSON.")] = False,
) -> None:
    """Restore canonical state captured before a release, conservatively.

    Refuses when a later release exists, a facility changed after the release, or
    later evidence has been linked. Raw source records and the release are retained;
    the release is marked rolled_back/quarantined.
    """

    engine, session = _session()
    try:
        result = rollback_release(
            session,
            dataset_slug=dataset_slug,
            release_label=release_label,
            reviewer=reviewer,
            note=note,
            dry_run=dry_run,
        )
        if not dry_run:
            session.commit()
    except ReleaseRollbackError as exc:
        session.rollback()
        typer.echo(f"Rollback refused: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
    if as_json:
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(
            f"dataset={result['dataset']} release={result['release_label']} "
            f"dry_run={result['dry_run']} snapshots={result['snapshots']} "
            f"restored={result['restored']} deleted={result['deleted']} "
            f"skipped={result['skipped']}"
        )


@app.command("crawl")
def crawl_public_sources(
    urls: Annotated[
        list[str],
        typer.Option("--url", help="Absolute public seed URL; repeatable."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", help="JSONL destination for the page ledger."),
    ] = Path("var/crawl/latest.jsonl"),
    tables_dir: Annotated[
        Path | None,
        typer.Option("--tables-dir", help="Write extracted HTML tables as CSV files here."),
    ] = None,
    max_pages: Annotated[
        int, typer.Option("--max-pages", min=1, help="Hard page-request limit.")
    ] = 100,
    max_depth: Annotated[
        int, typer.Option("--max-depth", min=0, help="Maximum link-follow depth.")
    ] = 2,
    concurrency: Annotated[
        int, typer.Option("--concurrency", min=1, help="Global concurrent request limit.")
    ] = 8,
    per_host: Annotated[
        int, typer.Option("--per-host", min=1, help="Concurrent request limit per host.")
    ] = 2,
    rps: Annotated[
        float, typer.Option("--rps", min=0, help="Requests per second per host (0 disables).")
    ] = 1.5,
    max_bytes: Annotated[
        int, typer.Option("--max-bytes", min=1, help="Maximum response size per page.")
    ] = 10 * 1024 * 1024,
    include: Annotated[
        str | None, typer.Option("--include", help="Only follow URLs matching this regex.")
    ] = None,
    exclude: Annotated[
        str | None, typer.Option("--exclude", help="Skip URLs matching this regex.")
    ] = None,
    same_host: Annotated[
        bool,
        typer.Option("--same-host/--any-host", help="Restrict links to the current host."),
    ] = True,
    robots: Annotated[
        bool,
        typer.Option("--robots/--no-robots", help="Check robots.txt before fetching."),
    ] = True,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the crawl summary as JSON.")
    ] = False,
) -> None:
    """Crawl public pages politely. Challenge/WAF pages are recorded, never bypassed."""

    policy = CrawlPolicy(
        max_concurrency=concurrency,
        per_host_concurrency=per_host,
        requests_per_second_per_host=rps,
        max_pages=max_pages,
        max_depth=max_depth,
        max_bytes=max_bytes,
        same_host=same_host,
        respect_robots=robots,
        include_pattern=include,
        exclude_pattern=exclude,
    )
    summary = asyncio.run(crawl(urls, policy=policy, output_path=output, tables_dir=tables_dir))
    payload = summary_json(summary)
    if json_output:
        typer.echo(payload)
        return
    typer.echo(
        f"requested={summary.pages_requested} fetched={summary.pages_fetched} "
        f"blocked={summary.pages_blocked} failed={summary.pages_failed} "
        f"links={summary.links_discovered} tables={summary.tables_written}"
    )
    for page in summary.pages:
        state = "BLOCKED" if page.blocked else page.status_code
        typer.echo(f"{state} d={page.depth} {page.final_url} ({page.size_bytes} bytes)")
    typer.echo(f"ledger={summary.output_path}")


@app.command("discover-sources")
def discover_sources(
    target_keys: Annotated[
        list[str] | None,
        typer.Option("--target", help="Probe only this discovery key; repeatable."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the probe results as JSON.")
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write JSON evidence to this path."),
    ] = None,
) -> None:
    """Probe discovery-only official sources without registering or publishing them."""

    targets = list(DISCOVERY_TARGETS)
    if target_keys:
        known = {target.key for target in targets}
        unknown = sorted(set(target_keys) - known)
        if unknown:
            raise typer.BadParameter(
                f"Unknown discovery target(s): {', '.join(unknown)}. "
                f"Known: {', '.join(sorted(known))}."
            )
        targets = [target for target in targets if target.key in set(target_keys)]

    results = probe_discovery_targets(targets)
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "probe_count": len(results),
        "targets": results,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return

    for row in results:
        http = f" http={row['http_status']}" if row["http_status"] is not None else ""
        detail = row["error"] or row["status"]
        typer.echo(f"{row['checked_at']} {row['key']}: {detail}{http} — {row['url']}")
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    typer.echo(f"probed={len(results)} {summary}")
    if output is not None:
        typer.echo(f"evidence={output}")


def _previous_psgc_units(previous, store):
    """Load a previous real PSGC release from JSON or the synthetic workbook."""

    from .sources.psgc import parse_psgc_workbook

    content = store.read(previous.raw_object_uri) if previous.raw_object_uri else b""
    if content.lstrip().startswith(b"{"):
        collections = load_psgc_release_payload(content)
        units, _warnings = psgc_units(collections)
        return units
    if content:
        units, _warnings = parse_psgc_workbook(content, expected_filename="previous.xlsx")
        return units
    return []


@app.command("load-psgc-bettergov")
def load_psgc_bettergov() -> None:
    """Acquire and load the BetterGov PSGC Q2 2024 mirror as geography.

    This is supplementary geography, not the latest official PSA workbook. It is
    labelled as such in the source register and API metadata.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings) as acquirer:
            collections, responses = fetch_psgc_collections(acquirer)
        content = psgc_release_content(collections)
        units, warnings = psgc_units(collections)
        if not units:
            raise typer.BadParameter("PSGC API returned no administrative units.")
        spec = source_spec(
            REAL_SOURCES["bettergov-psgc"],
            release_label="PSGC-Q2-2024-BETTERGOV",
            filename="psgc-q2-2024-bettergov.json",
            content=content,
            source_published_at=None,
            retrieved_at=datetime.now(UTC),
            reference_period_start=date(2024, 4, 1),
            reference_period_end=date(2024, 6, 30),
        )
        result = run_geography_ingestion(
            spec=spec,
            units=units,
            warnings=warnings,
            session=session,
            settings=settings,
            previous_units_loader=_previous_psgc_units,
        )
        session.commit()
        typer.echo(
            json.dumps({**result.__dict__, "http_requests": len(responses)}, default=str, indent=2)
        )
    finally:
        session.close()
        engine.dispose()


def _philhealth_release_label(entry) -> str:
    stem = entry.filename.rsplit(".", 1)[0].upper()
    suffix = entry.date_basis.isoformat() if entry.date_basis else "UNDATED"
    return f"PHILHEALTH-{stem}-{suffix}"


def _load_one_philhealth(settings, session, acquirer, entry, *, reprocess: bool = False) -> dict:
    specimen = source_spec(
        REAL_SOURCES["philhealth"],
        dataset_slug=philhealth_dataset_slug(entry),
        dataset_name=f"PhilHealth — {entry.category}",
        release_label=_philhealth_release_label(entry),
        filename=entry.filename,
        content=b"",
        source_url=entry.url,
        reference_period_start=entry.date_basis,
        reference_period_end=entry.date_basis,
    )
    _agency, dataset, _gate = ensure_source(session, specimen)
    result = acquirer.fetch(entry.url)
    status = classify_response(result)
    record_check(
        session,
        dataset=dataset,
        result=result,
        status=status,
        message=(
            f"PhilHealth {entry.category}: HTTP {result.status_code}; "
            f"date basis: {entry.date_basis_label}."
        ),
        details={
            "source_key": "philhealth",
            "filename": entry.filename,
            "category": entry.category,
            "date_basis": entry.date_basis.isoformat() if entry.date_basis else None,
        },
    )
    session.commit()
    if result.status_code >= 400 or status != "ok":
        return {
            "dataset": dataset.slug,
            "filename": entry.filename,
            "status": status,
            "http_status": result.status_code,
        }
    try:
        validate_signature(result, filename=entry.filename)
    except AcquisitionError as exc:
        return {
            "dataset": dataset.slug,
            "filename": entry.filename,
            "status": "signature_invalid",
            "error": str(exc),
        }
    spec = source_spec(
        REAL_SOURCES["philhealth"],
        dataset_slug=philhealth_dataset_slug(entry),
        dataset_name=f"PhilHealth — {entry.category}",
        release_label=_philhealth_release_label(entry),
        filename=entry.filename,
        content=result.content,
        source_url=entry.url,
        source_published_at=(
            datetime(
                entry.date_basis.year,
                entry.date_basis.month,
                entry.date_basis.day,
                tzinfo=UTC,
            )
            if entry.date_basis
            else None
        ),
        retrieved_at=datetime.now(UTC),
        reference_period_start=entry.date_basis,
        reference_period_end=entry.date_basis,
        # Candidate generation is an explicit, separate operation. Running it per row
        # makes large PDF loads pathologically slow and would enqueue the same pairs
        # repeatedly across benefit-package files.
        enqueue_cross_source_matches=False,
        notes=(
            f"PhilHealth public provider-category PDF. {entry.date_basis_label}. "
            "Publication relies on PhilHealth's published reuse statement; attribution retained."
        ),
    )
    result_obj = run_ingestion(
        spec=spec,
        adapter=PhilHealthPdfAdapter(spec, provider_category=entry.category),
        session=session,
        settings=settings,
        reprocess=reprocess,
    )
    return {
        "dataset": spec.dataset_slug,
        "filename": entry.filename,
        "status": result_obj.status,
        "release_id": result_obj.release_id,
        "stats": result_obj.stats,
        "issues": len(result_obj.issues),
    }


@app.command("load-philhealth")
def load_philhealth(
    filename: Annotated[
        list[str] | None,
        typer.Option("--file", help="Only ingest the named catalogue PDF(s)."),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help=(
                "Reparse an already-published release with the current parser. "
                "Use only for an explicit parser repair; record IDs and links are retained."
            ),
        ),
    ] = False,
) -> None:
    """Acquire every public PhilHealth provider-category PDF and ingest it."""

    settings = get_settings()
    engine, session = _session()
    outcomes = []
    try:
        with HttpAcquirer(settings) as acquirer:
            entries = philhealth_catalog(acquirer)
            if filename:
                wanted = set(filename)
                entries = [entry for entry in entries if entry.filename in wanted]
            if not entries:
                typer.echo("No matching PhilHealth catalogue entries.", err=True)
                raise typer.Exit(code=1)
            for entry in entries:
                typer.echo(f"→ {entry.filename}: {entry.category}")
                outcome = _load_one_philhealth(
                    settings, session, acquirer, entry, reprocess=reprocess
                )
                outcomes.append(outcome)
                typer.echo(f"  {outcome['status']}")
        typer.echo(json.dumps(outcomes, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-philhealth-offices")
def load_philhealth_offices(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved PhilHealth Directory of Offices HTML artifact for controlled import.",
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the public PhilHealth office directory and ingest office identities.

    Office name, source category, region grouping and postal address are
    published. Telephone numbers, e-mail addresses and schedule text stay in the
    private raw artifact.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = "Controlled import of a preserved public PhilHealth office-directory artifact."
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                content, metadata = fetch_philhealth_offices(acquirer)
            retrieved_at = datetime.now(UTC)
            notes = f"Acquisition metadata: {json.dumps(metadata, default=str)}"
        spec = source_spec(
            REAL_SOURCES["philhealth-offices"],
            release_label=f"PHILHEALTH-OFFICES-{retrieved_at.date().isoformat()}",
            filename=f"philhealth-office-directory-{retrieved_at.date().isoformat()}.json",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=PhilHealthOfficeAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-population")
def load_population(
    dataset_id: Annotated[
        list[str] | None,
        typer.Option(
            "--dataset",
            help="BetterGov dataset id to ingest; repeatable. Defaults to all 2024 census regions.",
        ),
    ] = None,
) -> None:
    """Ingest PSA 2024 Census population snapshots from BetterGov.

    The values are saved PSA OpenSTAT snapshots, not live PSA data. They are
    stored as statistical observations with their PSA table URL, release and
    dimension codes; they are never attached to a facility as an attribute.
    """

    settings = get_settings()
    engine, session = _session()
    ids = list(dataset_id or CENSUS_2024_DATASET_IDS)
    results = []
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            for identifier in ids:
                typer.echo(f"→ {identifier}")
                snapshot, _responses = fetch_population_snapshot(acquirer, identifier)
                result = load_population_snapshot(
                    session=session, settings=settings, snapshot=snapshot
                )
                results.append(result)
                typer.echo(
                    f"  {result['status']}: {result.get('observations', 0)} observations; "
                    f"{result.get('psgc_codes', 0)} PSGC codes"
                )
    finally:
        session.close()
        engine.dispose()
    typer.echo(json.dumps(results, indent=2, default=str))


@app.command("load-osm")
def load_osm(
    domain: Annotated[
        list[str] | None,
        typer.Option("--domain", help="health, education, or both. Default both."),
    ] = None,
) -> None:
    """Acquire the HOT/OSM GeoParquet extracts and ingest named features.

    Coordinates are bbox-centre map geocodes, not verified facility locations.
    OSM features are not evidence of operational status.
    """

    domains = domain or ["health", "education"]
    settings = get_settings()
    engine, session = _session()
    outcomes = []
    try:
        with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
            for item in domains:
                if item not in {"health", "education"}:
                    raise typer.BadParameter("Domain must be 'health' or 'education'.")
                source = REAL_SOURCES[f"osm-{item}"]
                typer.echo(f"→ {source.dataset_slug}")
                result = acquirer.fetch(source.source_url, max_bytes=200 * 1024 * 1024)
                status = classify_response(result)
                dataset = ensure_source(
                    session,
                    source_spec(
                        source,
                        release_label=f"HOT-OSM-PHL-{item.upper()}-{date.today().isoformat()}",
                        filename=f"{item}_facilities.parquet",
                        content=result.content,
                    ),
                )[1]
                record_check(
                    session,
                    dataset=dataset,
                    result=result,
                    status=status,
                    message=f"OSM {item} GeoParquet: HTTP {result.status_code}.",
                    details={"source_key": source.key, "domain": item},
                )
                session.commit()
                if status != "ok":
                    outcomes.append(
                        {"domain": item, "status": status, "http_status": result.status_code}
                    )
                    continue
                validate_signature(result, filename=f"{item}_facilities.parquet")
                spec = source_spec(
                    source,
                    release_label=f"HOT-OSM-PHL-{item.upper()}-{date.today().isoformat()}",
                    filename=f"{item}_facilities.parquet",
                    content=result.content,
                    retrieved_at=datetime.now(UTC),
                    enqueue_cross_source_matches=False,
                    notes=(
                        "HOT/OSM crowd-sourced extract. Coordinates are bbox-centre map "
                        "geocodes; no operational status is inferred."
                    ),
                )
                outcome = run_ingestion(
                    spec=spec,
                    adapter=OSMParquetAdapter(spec, facility_domain=item),
                    session=session,
                    settings=settings,
                )
                outcomes.append(
                    {
                        "domain": item,
                        "status": outcome.status,
                        "release_id": outcome.release_id,
                        "stats": outcome.stats,
                        "issues": len(outcome.issues),
                    }
                )
                typer.echo(f"  {outcome.status}: {outcome.stats}")
    finally:
        session.close()
        engine.dispose()
    typer.echo(json.dumps(outcomes, indent=2, default=str))


@app.command("load-deped-ebeis")
def load_deped_ebeis(
    region: Annotated[str, typer.Option(help="Verified EBEIS region key; default ncr.")] = "ncr",
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the public EBEIS masterlist and store it internal-only.

    The result set contains school-head names and has no explicit reuse licence.
    Records are never exposed by the public API in this state.
    """

    if region not in EBEIS_REGIONS:
        raise typer.BadParameter(f"Unknown EBEIS region {region!r}; known: {sorted(EBEIS_REGIONS)}")
    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
            content, metadata = fetch_ebeis_region(acquirer, region)
        spec = source_spec(
            REAL_SOURCES["deped-ebeis"],
            release_label=f"DEPED-EBEIS-{region.upper()}-{date.today().isoformat()}",
            filename=f"deped-ebeis-masterlist-{region}-{date.today().isoformat()}.html",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=(
                f"Public EBEIS result set for {metadata['region_name']}: "
                f"{metadata['reported_rows']} rows across {metadata['fetched_pages']} pages. "
                "Aggregated acquisition artifact; internal-only pending terms/privacy review."
            ),
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=DepEdEBEISAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(
            json.dumps(
                {**outcome.__dict__, "acquisition": metadata},
                indent=2,
                default=str,
            )
        )
    finally:
        session.close()
        engine.dispose()


@app.command("load-nlp")
def load_nlp() -> None:
    """Acquire the NLP public-library directory PDF and ingest it.

    Records carry postal addresses only. No coordinates or PSGC codes are inferred.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
            result = acquirer.fetch(REAL_SOURCES["nlp"].source_url, max_bytes=100 * 1024 * 1024)
        status = classify_response(result)
        if status != "ok":
            raise AcquisitionError(
                f"NLP directory returned HTTP {result.status_code}; no release was accepted.",
                result=result,
            )
        validate_signature(result, filename="nlp-public-libraries.pdf")
        spec = source_spec(
            REAL_SOURCES["nlp"],
            release_label="NLP-PUBLIC-LIBRARIES-2025-12",
            filename="nlp-public-libraries-2025-12.pdf",
            content=result.content,
            retrieved_at=datetime.now(UTC),
            reference_period_start=date(2025, 12, 1),
            reference_period_end=date(2025, 12, 31),
            enqueue_cross_source_matches=False,
            notes=(
                "NLP Integrated Directory of Public Libraries, December 2025 edition. "
                "Institutional fields published with attribution; librarian contact fields "
                "are not published."
            ),
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=NlpPublicLibraryPdfAdapter(spec),
            session=session,
            settings=settings,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-national-museum")
def load_national_museum() -> None:
    """Acquire the NMP regional/area/site museum directory and ingest it."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            content, metadata = fetch_national_museum_directory(acquirer)
        spec = source_spec(
            REAL_SOURCES["national-museum"],
            release_label=f"NMP-MUSEUMS-{date.today().isoformat()}",
            filename=f"nmp-regional-area-site-museums-{date.today().isoformat()}.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=(
                f"Acquisition artifact: {metadata['museums']} museum cards, "
                f"{metadata['detail_pages_fetched']} detail pages fetched. "
                "Postal addresses only; no coordinates were added."
            ),
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=NationalMuseumDirectoryAdapter(spec),
            session=session,
            settings=settings,
        )
        typer.echo(
            json.dumps(
                {**outcome.__dict__, "acquisition": metadata},
                indent=2,
                default=str,
            )
        )
    finally:
        session.close()
        engine.dispose()


@app.command("load-phlpost")
def load_phlpost(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the PHLPost locator and store it internal-only.

    The site carries an explicit copyright notice. No record is published until a
    documented reuse decision exists.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            result = acquirer.fetch(REAL_SOURCES["phlpost"].source_url)
        status = classify_response(result)
        if status != "ok":
            raise AcquisitionError(
                f"PHLPost locator returned HTTP {result.status_code}; no release was accepted.",
                result=result,
            )
        spec = source_spec(
            REAL_SOURCES["phlpost"],
            release_label=f"PHLPOST-LOCATOR-{date.today().isoformat()}",
            filename=f"phlpost-post-office-locator-{date.today().isoformat()}.html",
            content=result.content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=(
                "PHLPost public locator table. Stored internal-only because the publisher "
                "displays an explicit copyright/all-rights-reserved notice."
            ),
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=PhlPostLocatorAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-bir")
def load_bir() -> None:
    """Acquire and OCR the BIR RAO 006-2025 Revenue District Office list."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
            result = acquirer.fetch(REAL_SOURCES["bir"].source_url, max_bytes=50 * 1024 * 1024)
        status = classify_response(result)
        if status != "ok":
            raise AcquisitionError(
                f"BIR RAO returned HTTP {result.status_code}; no release was accepted.",
                result=result,
            )
        validate_signature(result, filename="bir-rao-006-2025.pdf")
        spec = source_spec(
            REAL_SOURCES["bir"],
            release_label="BIR-RAO-006-2025",
            filename="bir-rao-006-2025.pdf",
            content=result.content,
            retrieved_at=datetime.now(UTC),
            reference_period_start=date(2025, 12, 9),
            reference_period_end=date(2025, 12, 9),
            enqueue_cross_source_matches=False,
            notes=(
                "Official scanned RAO No. 006-2025. Local OCR recovered the Revenue "
                "Region/RDO list; no addresses or coordinates were inferred."
            ),
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=BirRevenueDistrictOfficeAdapter(spec),
            session=session,
            settings=settings,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-ppa")
def load_ppa(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved PPA port-list PDF for controlled import when the live file is unreachable.",  # noqa: E501
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire or import the PPA list of ports covered in PPA statistics.

    The source supplies port hierarchy and RORO/NON-RORO marks only. No
    coordinates, berth capacity, owner names, public access or operational status
    are inferred.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = (
                "Controlled import of the preserved public PPA port-list PDF. "
                "Source hierarchy, RORO/NON-RORO marks and remarks are preserved."
            )
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                result = acquirer.fetch(REAL_SOURCES["ppa"].source_url, max_bytes=50 * 1024 * 1024)
            status = classify_response(result)
            if status != "ok":
                raise AcquisitionError(
                    f"PPA port list returned HTTP {result.status_code}; no release was accepted.",
                    result=result,
                )
            validate_signature(result, filename="ppa-port-list.pdf")
            content = result.content
            retrieved_at = datetime.now(UTC)
            notes = (
                "PPA List of Ports Covered in PPA Statistics. Base, TMO/OTP, other "
                "government and private ports remain separate. No coordinates, owners, "
                "public access or operational status were inferred."
            )
        spec = source_spec(
            REAL_SOURCES["ppa"],
            release_label=f"PPA-PORT-LIST-{retrieved_at.date().isoformat()}",
            filename=f"ppa-port-list-{retrieved_at.date().isoformat()}.pdf",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=PpaPortListAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-dti-negosyo")
def load_dti_negosyo(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved DTI Negosyo Center JSON artifact for controlled import.",
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the public DTI Negosyo Center directory and ingest its centers.

    The finder supplies names, postal addresses and geographic labels only. No
    coordinates, ownership, operator, hours or access conditions are inferred.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = "Controlled import of a preserved public DTI Negosyo Center JSON artifact."
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                content, metadata = fetch_negosyo_centers(acquirer)
            retrieved_at = datetime.now(UTC)
            notes = f"Acquisition metadata: {json.dumps(metadata, default=str)}"
        spec = source_spec(
            REAL_SOURCES["dti-negosyo"],
            release_label=f"DTI-NEGOSYO-{retrieved_at.date().isoformat()}",
            filename=f"dti-negosyo-centers-{retrieved_at.date().isoformat()}.json",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=DtiNegosyoCenterAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-sss-branches")
def load_sss_branches(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved SSS branch-locator JSON artifact for controlled import.",
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the public SSS branch locator and ingest branch service facilities.

    Branch name, postal address and region are published. Contact-person,
    e-mail and telephone/fax fields stay in the private raw artifact.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = "Controlled import of a preserved public SSS branch-locator JSON artifact."
        else:
            with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
                content, metadata = fetch_sss_branches(acquirer)
            retrieved_at = datetime.now(UTC)
            notes = f"Acquisition metadata: {json.dumps(metadata, default=str)}"
        spec = source_spec(
            REAL_SOURCES["sss-branches"],
            release_label=f"SSS-BRANCHES-{retrieved_at.date().isoformat()}",
            filename=f"sss-branch-locator-{retrieved_at.date().isoformat()}.json",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=SssBranchAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-pagasa-aws")
def load_pagasa_aws(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved PAGASA AWS JSON artifact for controlled import.",
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the PAGASA automated-weather-station table and ingest station identity.

    Only station ID, name and source last-updated value are published. Readings
    remain in the private dated artifact; no coordinates are present.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = "Controlled import of a preserved public PAGASA AWS JSON artifact."
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                content, metadata = fetch_pagasa_aws(acquirer)
            retrieved_at = datetime.now(UTC)
            notes = f"Acquisition metadata: {json.dumps(metadata, default=str)}"
        spec = source_spec(
            REAL_SOURCES["pagasa-aws"],
            release_label=f"PAGASA-AWS-{retrieved_at.date().isoformat()}",
            filename=f"pagasa-automated-weather-stations-{retrieved_at.date().isoformat()}.json",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=PagasaAwsAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-nbi-offices")
def load_nbi_offices(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved NBI regional/district office JSON artifact for controlled import.",
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the NBI regional/district office directory and ingest office identities.

    Office name, region, postal location and map-embed coordinates are published.
    Personal names, telephone numbers and protected e-mail values stay private.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = "Controlled import of a preserved public NBI office JSON artifact."
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                content, metadata = fetch_nbi_offices(acquirer)
            retrieved_at = datetime.now(UTC)
            notes = f"Acquisition metadata: {json.dumps(metadata, default=str)}"
        spec = source_spec(
            REAL_SOURCES["nbi-offices"],
            release_label=f"NBI-OFFICES-{retrieved_at.date().isoformat()}",
            filename=f"nbi-regional-district-offices-{retrieved_at.date().isoformat()}.json",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=NbiOfficeAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-ched-heida")
def load_ched_heida(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help="Preserved CHED HEIDA JSON artifact for controlled import.",
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the public CHED HEIDA HEI directory and ingest its institutions.

    The directory supplies institutional name, CHED code, type, address and region
    only. Contact details and institutional-head names are discarded. No
    coordinates, PSGC codes, campus counts or operational status are inferred.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = "Controlled import of a preserved public CHED HEIDA JSON artifact."
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                content, metadata = fetch_heida_directory(acquirer)
            retrieved_at = datetime.now(UTC)
            notes = f"Acquisition metadata: {json.dumps(metadata, default=str)}"
        spec = source_spec(
            REAL_SOURCES["ched-heida"],
            release_label=f"CHED-HEIDA-{retrieved_at.date().isoformat()}",
            filename=f"ched-heida-hei-directory-{retrieved_at.date().isoformat()}.json",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=ChedHeidaAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-quezon-city")
def load_quezon_city(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the Quezon City LGU directories and ingest the eligible subset."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            content, metadata = fetch_quezon_city_directory(acquirer)
        spec = source_spec(
            REAL_SOURCES["quezon-city"],
            release_label=f"QC-LGU-DIRECTORY-{date.today().isoformat()}",
            filename=f"quezon-city-lgu-directory-{date.today().isoformat()}.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=f"Acquisition metadata: {json.dumps(metadata, default=str)}",
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=QuezonCityLguAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-quezon-city-places")
def load_quezon_city_places(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the Quezon City Places to Visit park and market subset."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            content, metadata = fetch_quezon_city_places(acquirer)
        spec = source_spec(
            REAL_SOURCES["quezon-city-places"],
            release_label=f"QC-LGU-PLACES-{date.today().isoformat()}",
            filename=f"quezon-city-lgu-places-{date.today().isoformat()}.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=f"Acquisition metadata: {json.dumps(metadata, default=str)}",
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=QuezonCityPlacesAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-mandaluyong")
def load_mandaluyong(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the Mandaluyong City barangay directory and ingest its offices."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            content, metadata = fetch_mandaluyong_directory(acquirer)
        spec = source_spec(
            REAL_SOURCES["mandaluyong"],
            release_label=f"MANDALUYONG-LGU-{date.today().isoformat()}",
            filename=f"mandaluyong-lgu-barangay-directory-{date.today().isoformat()}.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=f"Acquisition metadata: {json.dumps(metadata, default=str)}",
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=MandaluyongBarangayAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-cainta-health")
def load_cainta_health(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the Cainta RHU pages and ingest their labelled health centres."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            content, metadata = fetch_cainta_health_centers(acquirer)
        spec = source_spec(
            REAL_SOURCES["cainta-health"],
            release_label=f"CAINTA-HEALTH-{date.today().isoformat()}",
            filename=f"cainta-lgu-health-centers-{date.today().isoformat()}.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=f"Acquisition metadata: {json.dumps(metadata, default=str)}",
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=CaintaHealthCenterAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-pasay-health")
def load_pasay_health(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the Pasay health-care page and ingest its health facilities."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            content, metadata = fetch_pasay_health_centers(acquirer)
        spec = source_spec(
            REAL_SOURCES["pasay-health"],
            release_label=f"PASAY-HEALTH-{date.today().isoformat()}",
            filename=f"pasay-lgu-health-centers-{date.today().isoformat()}.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=f"Acquisition metadata: {json.dumps(metadata, default=str)}",
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=PasayHealthCenterAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-dswd-crcf")
def load_dswd_crcf(
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire the DSWD CRCF directory and ingest unique facility cards."""

    settings = get_settings()
    engine, session = _session()
    try:
        with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
            result = acquirer.fetch(REAL_SOURCES["dswd-crcf"].source_url)
        status = classify_response(result)
        if status != "ok":
            raise AcquisitionError(
                f"DSWD CRCF directory returned HTTP {result.status_code}; no release was accepted.",
                result=result,
            )
        spec = source_spec(
            REAL_SOURCES["dswd-crcf"],
            release_label=f"DSWD-CRCF-{date.today().isoformat()}",
            filename=f"dswd-crcf-directory-{date.today().isoformat()}.html",
            content=result.content,
            retrieved_at=datetime.now(UTC),
            enqueue_cross_source_matches=False,
            notes=(
                "DSWD CRCF public directory. Desktop and mobile accordion layouts are "
                "deduplicated by facility name and address; postal addresses only."
            ),
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=DswdCrcfDirectoryAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


@app.command("load-nmis-naris")
def load_nmis_naris(
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            help=(
                "Preserved NARIS HTML artifact for controlled import when the live page is blocked."
            ),
        ),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess",
            help="Reprocess an already-preserved release instead of skipping its checksum.",
        ),
    ] = False,
) -> None:
    """Acquire or import the NMIS NARIS accredited meat-establishment directory."""

    settings = get_settings()
    engine, session = _session()
    try:
        if input_path is not None:
            content = input_path.read_bytes()
            retrieved_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)
            notes = (
                "Controlled import of a preserved public NARIS directory artifact. "
                "The live endpoint returned a WAF challenge or TLS failure on recheck; "
                "the artifact is the release of record."
            )
        else:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                result = acquirer.fetch(REAL_SOURCES["nmis-naris"].source_url)
            status = classify_response(result)
            if status != "ok":
                raise AcquisitionError(
                    f"NARIS returned HTTP {result.status_code}; no release was accepted.",
                    result=result,
                )
            content = result.content
            retrieved_at = datetime.now(UTC)
            notes = (
                "Public NARIS accredited-establishment directory. Duplicate LTO rows "
                "are grouped; no validity dates or operating status are inferred."
            )
        spec = source_spec(
            REAL_SOURCES["nmis-naris"],
            release_label=f"NMIS-NARIS-{retrieved_at.date().isoformat()}",
            filename=f"nmis-naris-accredited-establishments-{retrieved_at.date().isoformat()}.html",
            content=content,
            retrieved_at=retrieved_at,
            enqueue_cross_source_matches=False,
            notes=notes,
        )
        outcome = run_ingestion(
            spec=spec,
            adapter=NmisNarisDirectoryAdapter(spec),
            session=session,
            settings=settings,
            reprocess=reprocess,
        )
        typer.echo(json.dumps(outcome.__dict__, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()


def _repair_agency_metadata(session: Session) -> None:
    """Remove the synthetic-demo label from agencies that now hold real data."""

    from philfacilities_api.models import Agency

    for code, (name, publisher_type) in REAL_AGENCY_METADATA.items():
        agency = session.scalars(select(Agency).where(Agency.short_code == code)).first()
        if agency is None:
            continue
        if agency.name != name:
            agency.name = name
        if agency.publisher_type != publisher_type:
            agency.publisher_type = publisher_type
    session.flush()


@app.command("purge-synthetic")
def purge_synthetic() -> None:
    """Remove synthetic demonstration records while retaining real source data."""

    engine, session = _session()
    try:
        before = session.scalar(select(func.count()).select_from(Facility)) or 0
        _reset_demo(session)
        _repair_agency_metadata(session)
        session.commit()
        after = session.scalar(select(func.count()).select_from(Facility)) or 0
        typer.echo(f"Purged synthetic demonstration records: facilities {before} → {after}.")
    finally:
        session.close()
        engine.dispose()


@app.command("load-real")
def load_real(
    skip_osm: Annotated[bool, typer.Option(help="Skip the large OSM extracts.")] = False,
    skip_philhealth: Annotated[bool, typer.Option(help="Skip PhilHealth PDFs.")] = False,
    skip_population: Annotated[
        bool, typer.Option(help="Skip the PSA 2024 Census snapshots.")
    ] = False,
    skip_deped: Annotated[bool, typer.Option(help="Skip the internal-only EBEIS extract.")] = False,
    skip_libraries: Annotated[
        bool, typer.Option(help="Skip the NLP public-library directory.")
    ] = False,
    skip_museums: Annotated[bool, typer.Option(help="Skip the National Museum directory.")] = False,
    skip_phlpost: Annotated[
        bool, typer.Option(help="Skip the internal-only PHLPost locator.")
    ] = False,
    skip_bir: Annotated[
        bool, typer.Option(help="Skip the scanned BIR Revenue District Office list.")
    ] = False,
    skip_ppa: Annotated[bool, typer.Option(help="Skip the PPA port list.")] = False,
    skip_dti: Annotated[bool, typer.Option(help="Skip the DTI Negosyo Center directory.")] = False,
    skip_ched: Annotated[
        bool, typer.Option(help="Skip the CHED HEIDA higher-education directory.")
    ] = False,
    skip_crcf: Annotated[bool, typer.Option(help="Skip the DSWD CRCF directory.")] = False,
    purge: Annotated[bool, typer.Option(help="Purge synthetic records first.")] = True,
) -> None:
    """Run the documented real-data acquisition sequence end to end."""

    settings = get_settings()
    engine, session = _session()
    try:
        if purge:
            _reset_demo(session)
            _repair_agency_metadata(session)
            session.commit()
            typer.echo("Synthetic demonstration records purged.")
        check_sources(session)
        typer.echo("Source checks recorded.")

        with HttpAcquirer(settings) as acquirer:
            collections, _responses = fetch_psgc_collections(acquirer)
        content = psgc_release_content(collections)
        units, warnings = psgc_units(collections)
        psgc_spec = source_spec(
            REAL_SOURCES["bettergov-psgc"],
            release_label="PSGC-Q2-2024-BETTERGOV",
            filename="psgc-q2-2024-bettergov.json",
            content=content,
            retrieved_at=datetime.now(UTC),
            reference_period_start=date(2024, 4, 1),
            reference_period_end=date(2024, 6, 30),
        )
        psgc_result = run_geography_ingestion(
            spec=psgc_spec,
            units=units,
            warnings=warnings,
            session=session,
            settings=settings,
            previous_units_loader=_previous_psgc_units,
        )
        typer.echo(f"PSGC: {psgc_result.status} ({psgc_result.stats.get('units')} units)")

        if not skip_population:
            population_results = []
            for identifier in CENSUS_2024_DATASET_IDS:
                snapshot, _responses = fetch_population_snapshot(acquirer, identifier)
                result = load_population_snapshot(
                    session=session, settings=settings, snapshot=snapshot
                )
                population_results.append(result)
                typer.echo(
                    f"Population {identifier}: {result['status']} "
                    f"({result.get('observations', 0)} observations)"
                )

        if not skip_philhealth:
            with HttpAcquirer(settings) as acquirer:
                entries = philhealth_catalog(acquirer)
                for entry in entries:
                    typer.echo(f"→ PhilHealth {entry.filename}")
                    _load_one_philhealth(settings, session, acquirer, entry)

        if not skip_osm:
            for domain in ("health", "education"):
                source = REAL_SOURCES[f"osm-{domain}"]
                with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
                    payload = acquirer.fetch(source.source_url, max_bytes=200 * 1024 * 1024)
                validate_signature(payload, filename=f"{domain}_facilities.parquet")
                osm_spec = source_spec(
                    source,
                    release_label=f"HOT-OSM-PHL-{domain.upper()}-{date.today().isoformat()}",
                    filename=f"{domain}_facilities.parquet",
                    content=payload.content,
                    retrieved_at=datetime.now(UTC),
                    enqueue_cross_source_matches=False,
                )
                osm_result = run_ingestion(
                    spec=osm_spec,
                    adapter=OSMParquetAdapter(osm_spec, facility_domain=domain),
                    session=session,
                    settings=settings,
                )
                typer.echo(f"OSM {domain}: {osm_result.status} {osm_result.stats}")

        if not skip_deped:
            with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
                deped_content, metadata = fetch_ebeis_region(acquirer, "ncr")
            deped_spec = source_spec(
                REAL_SOURCES["deped-ebeis"],
                release_label=f"DEPED-EBEIS-NCR-{date.today().isoformat()}",
                filename=f"deped-ebeis-masterlist-ncr-{date.today().isoformat()}.html",
                content=deped_content,
                retrieved_at=datetime.now(UTC),
                notes=f"Acquisition metadata: {json.dumps(metadata, default=str)}",
            )
            deped_result = run_ingestion(
                spec=deped_spec,
                adapter=DepEdEBEISAdapter(deped_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"DepEd EBEIS: {deped_result.status} {deped_result.stats}")

        if not skip_libraries:
            with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
                nlp_payload = acquirer.fetch(
                    REAL_SOURCES["nlp"].source_url, max_bytes=100 * 1024 * 1024
                )
            validate_signature(nlp_payload, filename="nlp-public-libraries.pdf")
            nlp_spec = source_spec(
                REAL_SOURCES["nlp"],
                release_label="NLP-PUBLIC-LIBRARIES-2025-12",
                filename="nlp-public-libraries-2025-12.pdf",
                content=nlp_payload.content,
                retrieved_at=datetime.now(UTC),
                reference_period_start=date(2025, 12, 1),
                reference_period_end=date(2025, 12, 31),
                enqueue_cross_source_matches=False,
            )
            nlp_result = run_ingestion(
                spec=nlp_spec,
                adapter=NlpPublicLibraryPdfAdapter(nlp_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"NLP public libraries: {nlp_result.status} {nlp_result.stats}")

        if not skip_museums:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                museum_content, museum_metadata = fetch_national_museum_directory(acquirer)
            museum_spec = source_spec(
                REAL_SOURCES["national-museum"],
                release_label=f"NMP-MUSEUMS-{date.today().isoformat()}",
                filename=f"nmp-regional-area-site-museums-{date.today().isoformat()}.json",
                content=museum_content,
                retrieved_at=datetime.now(UTC),
                enqueue_cross_source_matches=False,
                notes=f"Acquisition metadata: {json.dumps(museum_metadata, default=str)}",
            )
            museum_result = run_ingestion(
                spec=museum_spec,
                adapter=NationalMuseumDirectoryAdapter(museum_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"National Museum: {museum_result.status} {museum_result.stats}")

        if not skip_phlpost:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                phlpost_payload = acquirer.fetch(REAL_SOURCES["phlpost"].source_url)
            phlpost_spec = source_spec(
                REAL_SOURCES["phlpost"],
                release_label=f"PHLPOST-LOCATOR-{date.today().isoformat()}",
                filename=f"phlpost-post-office-locator-{date.today().isoformat()}.html",
                content=phlpost_payload.content,
                retrieved_at=datetime.now(UTC),
                enqueue_cross_source_matches=False,
            )
            phlpost_result = run_ingestion(
                spec=phlpost_spec,
                adapter=PhlPostLocatorAdapter(phlpost_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"PHLPost: {phlpost_result.status} {phlpost_result.stats}")

        if not skip_bir:
            with HttpAcquirer(settings, timeout_seconds=180.0) as acquirer:
                bir_payload = acquirer.fetch(
                    REAL_SOURCES["bir"].source_url, max_bytes=50 * 1024 * 1024
                )
            validate_signature(bir_payload, filename="bir-rao-006-2025.pdf")
            bir_spec = source_spec(
                REAL_SOURCES["bir"],
                release_label="BIR-RAO-006-2025",
                filename="bir-rao-006-2025.pdf",
                content=bir_payload.content,
                retrieved_at=datetime.now(UTC),
                reference_period_start=date(2025, 12, 9),
                reference_period_end=date(2025, 12, 9),
                enqueue_cross_source_matches=False,
            )
            bir_result = run_ingestion(
                spec=bir_spec,
                adapter=BirRevenueDistrictOfficeAdapter(bir_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"BIR RDOs: {bir_result.status} {bir_result.stats}")

        if not skip_ppa:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                ppa_payload = acquirer.fetch(
                    REAL_SOURCES["ppa"].source_url, max_bytes=50 * 1024 * 1024
                )
            validate_signature(ppa_payload, filename="ppa-port-list.pdf")
            ppa_spec = source_spec(
                REAL_SOURCES["ppa"],
                release_label=f"PPA-PORT-LIST-{date.today().isoformat()}",
                filename=f"ppa-port-list-{date.today().isoformat()}.pdf",
                content=ppa_payload.content,
                retrieved_at=datetime.now(UTC),
                enqueue_cross_source_matches=False,
            )
            ppa_result = run_ingestion(
                spec=ppa_spec,
                adapter=PpaPortListAdapter(ppa_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"PPA ports: {ppa_result.status} {ppa_result.stats}")

        if not skip_dti:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                dti_content, dti_metadata = fetch_negosyo_centers(acquirer)
            dti_spec = source_spec(
                REAL_SOURCES["dti-negosyo"],
                release_label=f"DTI-NEGOSYO-{date.today().isoformat()}",
                filename=f"dti-negosyo-centers-{date.today().isoformat()}.json",
                content=dti_content,
                retrieved_at=datetime.now(UTC),
                enqueue_cross_source_matches=False,
                notes=f"Acquisition metadata: {json.dumps(dti_metadata, default=str)}",
            )
            dti_result = run_ingestion(
                spec=dti_spec,
                adapter=DtiNegosyoCenterAdapter(dti_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"DTI Negosyo Centers: {dti_result.status} {dti_result.stats}")

        if not skip_ched:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                ched_content, ched_metadata = fetch_heida_directory(acquirer)
            ched_spec = source_spec(
                REAL_SOURCES["ched-heida"],
                release_label=f"CHED-HEIDA-{date.today().isoformat()}",
                filename=f"ched-heida-hei-directory-{date.today().isoformat()}.json",
                content=ched_content,
                retrieved_at=datetime.now(UTC),
                enqueue_cross_source_matches=False,
                notes=f"Acquisition metadata: {json.dumps(ched_metadata, default=str)}",
            )
            ched_result = run_ingestion(
                spec=ched_spec,
                adapter=ChedHeidaAdapter(ched_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"CHED HEIs: {ched_result.status} {ched_result.stats}")

        if not skip_crcf:
            with HttpAcquirer(settings, timeout_seconds=120.0) as acquirer:
                crcf_payload = acquirer.fetch(REAL_SOURCES["dswd-crcf"].source_url)
            crcf_spec = source_spec(
                REAL_SOURCES["dswd-crcf"],
                release_label=f"DSWD-CRCF-{date.today().isoformat()}",
                filename=f"dswd-crcf-directory-{date.today().isoformat()}.html",
                content=crcf_payload.content,
                retrieved_at=datetime.now(UTC),
                enqueue_cross_source_matches=False,
            )
            crcf_result = run_ingestion(
                spec=crcf_spec,
                adapter=DswdCrcfDirectoryAdapter(crcf_spec),
                session=session,
                settings=settings,
            )
            typer.echo(f"DSWD CRCF: {crcf_result.status} {crcf_result.stats}")

        session.commit()
        typer.echo("Real-data acquisition sequence complete.")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    app()
