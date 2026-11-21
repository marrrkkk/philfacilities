"""Command-line entry point for PhilFacilities ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import typer
from philfacilities_api.models import (
    Dataset,
    Facility,
    IngestionRun,
    MatchCandidate,
    Release,
)
from philfacilities_api.rights import rights_allow_public
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .acquisition import (
    actionable_failures,
    send_failure_alert,
    send_ingestion_failure_alert,
)
from .aggregation import consolidate_facilities, resolve_pending_match_candidates
from .assertions import backfill_assertions
from .compare import ReleaseComparisonError, compare_releases
from .config import get_settings
from .contracts import ReleaseSpec
from .discovery import DISCOVERY_TARGETS, probe_discovery_targets
from .display_names import normalize_facility_display_names
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
from .fusion import (
    FUSION_STATUSES,
    apply_fusions,
    auto_merge_exact_duplicates,
    build_attribute_fusions,
    fusion_report,
)
from .health_refinement import (
    normalize_health_subtypes,
    refine_health_ownership,
)
from .lgu_inventory import validate_inventory
from .location_fill import fill_locations_from_osm
from .manifest import render_release_notes, write_release_manifest
from .matching import (
    MatchingError,
    accept_match_candidate,
    generate_match_candidates,
    merge_deped_prefixed_duplicates,
    merge_match_candidate,
    reject_match_candidate,
    undo_match_merge,
)
from .osm_boundaries import (
    BOUNDARY_RELEASE_LABEL,
    boundary_artifacts,
    extract_osm_boundaries,
    import_osm_boundaries,
    sha256_file,
)
from .pipeline import (
    build_engine,
    run_ingestion,
    run_psgc_ingestion,
    session_factory,
)
from .psgc_fill import fill_location_psgc
from .psgc_spatial_fill import fill_location_psgc_from_map
from .rebuild_reports import write_rebuild_pack
from .release_rollback import ReleaseRollbackError, rollback_release
from .replay import ReplayManifestError, replay_manifest
from .school_refinement import normalize_school_subtypes
from .scraper import CrawlPolicy, crawl, summary_json
from .slugs import consolidate_numeric_slugs, normalize_facility_slugs
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
from .source_report import enrich_source_inventory, validate_report_fields, write_source_reports
from .source_runner import run_selection, summarize_results, validate_source
from .sources.catalog import SOURCES, catalog_rows, select_keys
from .sources.connectors.osm import (
    DEFAULT_PBF_PATH,
    PBF_SOURCE_PUBLISHED_AT,
    PBF_SOURCE_URL,
)
from .sources.deped import DepEdEnrollmentAdapter, DepEdMasterlistAdapter, DepEdResourceAdapter
from .sources.doh import DOHNHFRAdapter
from .sources.philhealth import PhilHealthPdfAdapter
from .sources.registry import (
    apply_publication_decisions,
    check_sources,
    due_source_keys,
    latest_checks,
    source_review_rows,
)

app = typer.Typer(
    add_completion=False,
    help="Source acquisition, repeatable ingestion, reports, and status for PhilFacilities.",
)
source_app = typer.Typer(add_completion=False, help="List, check, run, and validate sources.")
demo_app = typer.Typer(add_completion=False, help="Synthetic demonstration data.")
app.add_typer(source_app, name="source")
app.add_typer(demo_app, name="demo")

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


@demo_app.command("load")
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


@source_app.command("list")
def source_list(
    group: Annotated[
        str | None,
        typer.Option("--group", help="approved or skipped."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """List every registered source and its acquisition route."""

    rows = catalog_rows()
    if group is not None:
        rows = [row for row in rows if row["group"] == group]
    if json_output:
        typer.echo(json.dumps(rows, indent=2, default=str))
        return
    typer.echo(f"{'KEY':28} {'GROUP':8} {'RIGHTS':24} {'CONNECTOR':24} DATASET")
    for row in rows:
        typer.echo(
            f"{row['key']:28} {row['group']:8} {row['rights']:24} "
            f"{row['connector']:24} {row['dataset']}"
        )


@source_app.command("check")
def source_check(
    keys: Annotated[
        list[str] | None,
        typer.Argument(help="Source keys to check; omit to check every registered source."),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", "-s", help="Repeat to check selected source keys."),
    ] = None,
    due: Annotated[
        bool,
        typer.Option("--due", help="Check only sources whose next_check_at is due."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Ignore next_check_at for selected sources."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = True,
) -> None:
    """Probe registered sources and append monitoring evidence.

    A check never downloads a release into canonical tables, never bypasses an
    access control, and never accepts a licence on the operator's behalf.
    """

    selected = list(keys or []) + list(source or [])
    settings = get_settings()
    engine, session = _session()
    try:
        if due:
            checked_keys = due_source_keys(session, keys=selected or None, force=force)
            if not checked_keys:
                typer.echo("No source checks are due.")
                return
            typer.echo(f"Checking {len(checked_keys)} due source(s): {', '.join(checked_keys)}")
            results = check_sources(session, keys=checked_keys)
            send_failure_alert(settings, results, command="source check --due")
            failures = actionable_failures(results)
            if failures:
                typer.echo(f"Actionable failures: {', '.join(sorted(failures))}", err=True)
                if json_output:
                    typer.echo(json.dumps(results, indent=2, default=str))
                raise typer.Exit(code=2)
        else:
            results = check_sources(session, keys=selected or None)
        if json_output:
            typer.echo(json.dumps(results, indent=2, default=str))
        else:
            for key, row in results.items():
                detail = row.get("error") or row.get("status")
                typer.echo(f"{key}: {detail} http={row.get('http_status')}")
    finally:
        session.close()
        engine.dispose()


@source_app.command("run")
def source_run(
    keys: Annotated[
        list[str] | None,
        typer.Argument(help="Source keys to run; omit with --group to run a group."),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option("--group", help="Run every source in approved or skipped."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Repeat to exclude a source key from the selection."),
    ] = None,
    reprocess: Annotated[
        bool,
        typer.Option("--reprocess", help="Reprocess an already-preserved release."),
    ] = False,
    force_reapply: Annotated[
        bool,
        typer.Option(
            "--force-reapply",
            help=(
                "Reapply every parsed row even when its raw payload is unchanged. "
                "Use after adding a derived child table; this re-asserts canonical "
                "fields and can churn values from competing sources."
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Acquire and validate without writing canonical or staging rows.",
        ),
    ] = False,
    input_path: Annotated[
        Path | None,
        typer.Option("--input", help="Controlled import of a preserved artifact."),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", help="EBEIS region key, or 'all'."),
    ] = None,
    provider_category: Annotated[
        str | None,
        typer.Option("--provider-category", help="Category for a preserved PhilHealth PDF."),
    ] = None,
    files: Annotated[
        list[str] | None,
        typer.Option("--file", help="PhilHealth catalogue PDF filename; repeatable."),
    ] = None,
    datasets: Annotated[
        list[str] | None,
        typer.Option("--dataset", help="BetterGov population dataset id; repeatable."),
    ] = None,
    extract_out: Annotated[
        Path | None,
        typer.Option("--extract-out", help="Write the filtered OSM PBF extract here."),
    ] = None,
    pbf_path: Annotated[
        Path | None,
        typer.Option("--pbf-path", help="Local Geofabrik .osm.pbf snapshot."),
    ] = None,
    enqueue_matches: Annotated[
        bool,
        typer.Option(
            "--enqueue-matches",
            help=(
                "Run cross-source candidate matching during ingestion. Off by default "
                "for bulk releases; the explicit matcher command is preferred."
            ),
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = True,
) -> None:
    """Acquire and ingest one or more sources through the generic runner."""

    selected = select_keys(keys, group=group, exclude=exclude)
    if not selected:
        raise typer.BadParameter("No source keys selected.")
    if input_path is not None and len(selected) != 1:
        raise typer.BadParameter("--input can only be used with one source key.")
    options: dict[str, Any] = {}
    if region is not None:
        options["region"] = region
    if provider_category is not None:
        options["provider_category"] = provider_category
    if files:
        options["files"] = files
    if datasets:
        options["datasets"] = datasets
    if extract_out is not None:
        options["extract_out"] = str(extract_out)
    if pbf_path is not None:
        options["pbf_path"] = str(pbf_path)
    settings = get_settings()
    engine, session = _session()
    try:
        results = run_selection(
            session,
            settings,
            selected,
            reprocess=reprocess,
            force_reapply=force_reapply,
            dry_run=dry_run,
            input_path=input_path,
            options=options,
            enqueue_matches=enqueue_matches,
        )
    finally:
        session.close()
        engine.dispose()
    alerted = send_ingestion_failure_alert(settings, results, command="source run")
    if alerted:
        typer.echo("Failure alert sent to the configured webhook.", err=True)
    if json_output:
        typer.echo(json.dumps(results, indent=2, default=str))
    else:
        for row in results:
            typer.echo(
                f"{row.get('key')}: {row.get('status')} "
                f"{row.get('filename') or ''} {row.get('error') or ''}".rstrip()
            )
        typer.echo(
            " ".join(f"{status}={count}" for status, count in summarize_results(results).items())
        )
    if any(row.get("status") == "failed" for row in results):
        raise typer.Exit(code=1)


@source_app.command("validate")
def source_validate(
    key: Annotated[str, typer.Argument(help="Source key to validate.")],
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Preserved raw artifact to parse; omit to acquire the current source.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", help="EBEIS region key for the fixture."),
    ] = None,
    provider_category: Annotated[
        str | None,
        typer.Option("--provider-category", help="Category for a preserved PhilHealth PDF."),
    ] = None,
) -> None:
    """Run parse -> validate -> normalize without writing to the database."""

    if key not in SOURCES:
        raise typer.BadParameter(
            f"Unknown source key {key!r}; run 'source list' to see registered keys."
        )
    options: dict[str, Any] = {}
    if region is not None:
        options["region"] = region
    if provider_category is not None:
        options["provider_category"] = provider_category
    result = validate_source(
        get_settings(),
        key,
        input_path=fixture,
        options=options,
    )
    typer.echo(json.dumps(result, indent=2, default=str))
    if any(
        release.get("status") not in {"validated", "skipped_duplicate"}
        for release in result["releases"]
    ):
        raise typer.Exit(code=1)


@source_app.command("replay")
def source_replay(
    manifest: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="JSON manifest naming preserved releases or raw object URIs.",
        ),
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = True,
) -> None:
    """Replay preserved raw releases through the current parsers.

    A replay never re-downloads a source. Each manifest entry names either a
    stored release UUID or a raw object URI; the bytes are verified against the
    recorded SHA-256 before the current connector and parser run.
    """

    settings = get_settings()
    engine, session = _session()
    try:
        results = replay_manifest(
            session=session,
            settings=settings,
            manifest_path=manifest,
        )
    except ReplayManifestError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        session.close()
        engine.dispose()
    alerted = send_ingestion_failure_alert(settings, results, command="source replay")
    if alerted:
        typer.echo("Failure alert sent to the configured webhook.", err=True)
    if json_output:
        typer.echo(json.dumps(results, indent=2, default=str))
    else:
        for row in results:
            typer.echo(
                f"{row.get('source')}: {row.get('status')} "
                f"{row.get('filename') or ''} {row.get('error') or ''}".rstrip()
            )
    if any(row.get("status") == "failed" for row in results):
        raise typer.Exit(code=1)


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
    reviewer: Annotated[
        str | None,
        typer.Option(
            help=(
                "Reviewer who accepted the rights decision. Required when the supplied "
                "rights state may publish records."
            )
        ),
    ] = None,
    review_note: Annotated[
        str | None,
        typer.Option(help="Rights-review note recorded on the publication gate."),
    ] = None,
) -> None:
    """Ingest one real or synthetic source file through its adapter.

    Manual imports are trusted-operator commands, but a public import must name
    the reviewer who accepted the rights decision. The reviewer is recorded on the
    publication gate; the command never invents a rights state.
    """

    if not is_synthetic and rights_allow_public(redistribution_status) and not reviewer:
        raise typer.BadParameter(
            "--reviewer is required when a manual import has a public redistribution "
            "status; record the person or role who reviewed the source terms."
        )
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
        rights_reviewer=reviewer,
        rights_review_note=review_note,
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


@app.command("fuse-attributes")
def fuse_attributes_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--no-apply",
            help="Apply eligible safe fields to canonical facility rows.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report what would be applied without changing facilities."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Only process the first N facilities (for a sample)."),
    ] = None,
    all_facilities: Annotated[
        bool,
        typer.Option(
            "--all/--multi-source-only",
            help=(
                "Fuse every facility, including single-source ones. The default fuses only "
                "facilities linked to more than one source record."
            ),
        ),
    ] = False,
) -> None:
    """Materialise field-level fusions and retain every conflicting value.

    Source assertions and raw releases are never rewritten. With ``--apply``,
    cross-agency agreements, conflicts with a clear authority winner, and
    single-source values that fill a missing canonical field are copied to the
    facility automatically. Equal-authority conflicts stay derived-only.
    """

    engine, session = _session()
    try:
        if limit is not None:
            facility_ids = list(
                session.scalars(select(Facility.id).order_by(Facility.id).limit(limit)).all()
            )
        else:
            facility_ids = None
        stats = build_attribute_fusions(
            session,
            facility_ids=facility_ids,
            multi_source_only=not all_facilities,
            progress=lambda current: typer.echo(
                f"  fused facilities={current.facilities_scanned} "
                f"attributes={current.attributes_written} "
                f"conflicts={current.conflict} removed={current.removed}",
                err=True,
            ),
        )
        applied = (
            apply_fusions(session, facility_ids=facility_ids, dry_run=dry_run) if apply else None
        )
        if not dry_run:
            session.commit()
        typer.echo(json.dumps({"fusion": stats.as_dict(), "applied": applied}, indent=2))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("fusion-report")
def fusion_report_command(
    as_json: Annotated[bool, typer.Option("--json", help="Emit the report as JSON.")] = False,
    status: Annotated[
        str,
        typer.Option(
            "--status",
            help="Sample status: single_source, agreed, conflict, or all.",
        ),
    ] = "conflict",
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=200, help="Maximum samples to return."),
    ] = 25,
) -> None:
    """Report fused attributes and conflicts left derived-only."""

    if status == "all":
        sample_status = None
    elif status in FUSION_STATUSES:
        sample_status = status
    else:
        raise typer.BadParameter(f"--status must be one of {FUSION_STATUSES} or 'all'.")

    engine, session = _session()
    try:
        report = fusion_report(session, status=sample_status, limit=limit)
    finally:
        session.close()
        engine.dispose()
    if as_json:
        typer.echo(json.dumps(report, indent=2, default=str))
        return
    typer.echo(json.dumps(report["by_status"], indent=2))
    typer.echo(
        f"total={report['total']} unresolved_conflicts={report['unresolved_conflicts']} "
        f"samples={len(report['samples'])}"
    )
    for row in report["samples"]:
        typer.echo(
            f"{row['facility'][:60]} · {row['attribute']}={row['selected_value']!r} "
            f"({row['distinct_values']} distinct values, confidence={row['confidence']})"
        )


@app.command("fill-locations-from-osm")
def fill_locations_from_osm_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write the OSM-derived points; without it the command is a dry run.",
        ),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="Write a machine-readable fill report (JSON) here.",
        ),
    ] = None,
) -> None:
    """Fill missing facility points from deterministic OSM name + city matches."""

    engine, session = _session()
    try:
        result = fill_locations_from_osm(session, apply=apply, report_path=report)
    finally:
        session.close()
        engine.dispose()
    typer.echo(json.dumps(result.to_dict(), indent=2, default=str))
    if not apply:
        typer.echo("dry run: pass --apply to write the community map locations.")


@app.command("fill-location-psgc")
def fill_location_psgc_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write the resolved PSGC codes; without it the command is a dry run.",
        ),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="Write a machine-readable resolution report (JSON) here.",
        ),
    ] = None,
) -> None:
    """Resolve missing location PSGC codes from linked source evidence."""

    engine, session = _session()
    try:
        result = fill_location_psgc(session, apply=apply, report_path=report)
    finally:
        session.close()
        engine.dispose()
    typer.echo(json.dumps(result.to_dict(include_rows=False), indent=2, default=str))
    if not apply:
        typer.echo("dry run: pass --apply to write the resolved PSGC codes.")


@app.command("fill-location-psgc-from-map")
def fill_location_psgc_from_map_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write the map-derived PSGC codes; without it the command is a dry run.",
        ),
    ] = False,
    refine: Annotated[
        bool,
        typer.Option(
            "--refine",
            help=(
                "Upgrade a non-null code only when the containing map unit is a "
                "descendant of the current code."
            ),
        ),
    ] = False,
    prefer_map: Annotated[
        bool,
        typer.Option(
            "--prefer-map",
            help=(
                "Treat the containing map unit as authoritative: override "
                "same-level and different-branch source codes, keeping the "
                "original source claim in its assertion."
            ),
        ),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="Write a machine-readable containment report (JSON) here.",
        ),
    ] = None,
) -> None:
    """Fill missing location PSGC codes from point-in-polygon map containment.

    ``--prefer-map`` makes the containing map unit authoritative for the
    administrative location while preserving source claims as assertions.
    """

    engine, session = _session()
    try:
        result = fill_location_psgc_from_map(
            session,
            apply=apply,
            refine=refine,
            prefer_map=prefer_map,
            report_path=report,
        )
    finally:
        session.close()
        engine.dispose()
    payload = result.to_dict(include_rows=False)
    payload.pop("conflict_samples", None)
    payload.pop("unresolved_samples", None)
    typer.echo(json.dumps(payload, indent=2, default=str))
    if not apply:
        typer.echo("dry run: pass --apply to write the map-derived PSGC codes.")


@app.command("import-osm-boundaries")
def import_osm_boundaries_command(
    pbf_path: Annotated[
        Path,
        typer.Option("--pbf-path", help="Local Geofabrik .osm.pbf snapshot."),
    ] = DEFAULT_PBF_PATH,
    extract_out: Annotated[
        Path,
        typer.Option(
            "--extract-out",
            help="Preserved boundary Parquet artifact; metadata is written beside it.",
        ),
    ] = Path("var/extracts/osm-admin-boundaries-philippines.parquet"),
    release_label: Annotated[
        str,
        typer.Option("--release-label", help="Boundary snapshot label stored with rows."),
    ] = BOUNDARY_RELEASE_LABEL,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Re-extract boundaries even when the Parquet artifact already exists.",
        ),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Replace the stored boundary layer; without it the command is a dry run.",
        ),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="Write a machine-readable boundary import report (JSON) here.",
        ),
    ] = None,
) -> None:
    """Extract OSM administrative boundaries and resolve them to current PSGC codes."""

    if refresh or not extract_out.exists():
        if not pbf_path.exists():
            raise typer.BadParameter(f"PBF snapshot not found: {pbf_path}")
        extract_stats = extract_osm_boundaries(
            pbf_path,
            extract_out,
            source_url=PBF_SOURCE_URL,
            source_sha256=sha256_file(pbf_path),
            source_published_at=PBF_SOURCE_PUBLISHED_AT,
        )
        typer.echo(json.dumps(extract_stats.to_dict(), indent=2, default=str))

    _rows, metadata = boundary_artifacts(extract_out)
    published_raw = metadata.get("source_published_at")
    retrieved_raw = metadata.get("retrieved_at")
    source_published_at = (
        datetime.fromisoformat(published_raw) if published_raw else PBF_SOURCE_PUBLISHED_AT
    )
    retrieved_at = datetime.fromisoformat(retrieved_raw) if retrieved_raw else None

    engine, session = _session()
    try:
        result = import_osm_boundaries(
            session,
            extract_out,
            release_label=release_label,
            source_url=str(metadata.get("source_url") or PBF_SOURCE_URL),
            source_sha256=metadata.get("source_sha256"),
            source_published_at=source_published_at,
            retrieved_at=retrieved_at,
            apply=apply,
            report_path=report,
        )
    finally:
        session.close()
        engine.dispose()
    typer.echo(json.dumps(result.to_dict(include_rows=False), indent=2, default=str))
    if not apply:
        typer.echo("dry run: pass --apply to replace the stored boundary layer.")


@app.command("auto-merge-duplicates")
def auto_merge_duplicates_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the deterministic merges. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[int, typer.Option(min=1, help="Maximum candidates to consider.")] = 100,
) -> None:
    """Merge only exact normalized name + PSGC + address duplicates.

    Ambiguous candidates remain unmerged and are retried automatically when new
    evidence arrives; there is no human review gate. A merge retires the source
    facility but retains its source links and claims on the survivor.
    """

    engine, session = _session()
    try:
        stats = auto_merge_exact_duplicates(session, dry_run=not apply, limit=limit)
        if apply:
            build_attribute_fusions(session)
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("consolidate-facilities")
def consolidate_facilities_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the evidence-backed merges. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to merge in this run."),
    ] = 100,
    include_synthetic: Annotated[
        bool,
        typer.Option(help="Include synthetic demo facilities."),
    ] = False,
    facility_type: Annotated[
        str | None,
        typer.Option("--facility-type", help="Limit the pass to one facility type."),
    ] = None,
    defer_fusion: Annotated[
        bool,
        typer.Option(
            "--defer-fusion",
            help=(
                "Commit merges without rebuilding field fusions. Run the fusion "
                "command once afterwards; use this for large bulk passes."
            ),
        ),
    ] = False,
    commit_every: Annotated[
        int | None,
        typer.Option(
            "--commit-every",
            min=1,
            help=(
                "Commit after roughly this many merges so a long pass keeps its "
                "completed work. The default commits once at the end."
            ),
        ),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum merge examples to include in the output."),
    ] = 20,
) -> None:
    """Aggregate every facility type from independent identity evidence.

    Names are compared with saint, legal-form and connector-order folding, but
    a name never decides identity by itself. A clique is merged only when every
    pair is eligible and at least one pair has a strong identity bridge: a
    shared official identifier, the same barangay, an address match, or points
    within 250 m. Cross-type and weaker pairs stay as pending match candidates.

    This handles all facility types. The DepEd prefixed-ID repair remains a
    separate deterministic step because it is an identifier rule, not a name
    similarity decision.
    """

    engine, session = _session()
    try:
        affected: set[uuid.UUID] = set()
        merged: set[uuid.UUID] = set()
        stats = consolidate_facilities(
            session,
            dry_run=not apply,
            limit=limit,
            include_synthetic=include_synthetic,
            example_limit=examples,
            affected_facility_ids=affected,
            facility_type=facility_type,
            commit_every=commit_every,
            defer_fusion=defer_fusion,
            merged_facility_ids=merged,
        )
        if apply:
            # Keep completed merges even if the derived fusion pass fails.
            session.commit()
            scoped = affected | merged
            if scoped:
                # A deferred pass rebuilds derived rows once for every surviving
                # facility and clears the stale rows left on retired duplicates.
                build_attribute_fusions(
                    session,
                    facility_ids=scoped,
                    multi_source_only=False,
                    batch_size=500,
                    release_objects=True,
                    commit_batches=True,
                )
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("normalize-facility-slugs")
def normalize_facility_slugs_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the slug renames. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facility slugs to rename in this run."),
    ] = 50_000,
    facility_type: Annotated[
        str | None,
        typer.Option("--facility-type", help="Limit the pass to one facility type."),
    ] = None,
    commit_every: Annotated[
        int | None,
        typer.Option(
            "--commit-every",
            min=1,
            help=(
                "Commit completed renames in batches of this size so a large "
                "pass keeps its progress. The default commits once at the end."
            ),
        ),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum rename examples to include in the output."),
    ] = 20,
) -> None:
    """Remove source suffixes from public facility slugs.

    ``-osm``, ``-doh``, ``-nha`` and similar suffixes describe the dataset that
    first reported a facility, not the facility itself. Every rename keeps the
    old slug as an alias so existing links continue to resolve, and records a
    change event for audit.
    """

    engine, session = _session()
    try:
        stats = normalize_facility_slugs(
            session,
            dry_run=not apply,
            limit=limit,
            facility_type=facility_type,
            example_limit=examples,
            commit_every=commit_every,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("consolidate-numeric-slugs")
def consolidate_numeric_slugs_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the slug renames. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facility slugs to rename in this run."),
    ] = 50_000,
    facility_type: Annotated[
        str | None,
        typer.Option("--facility-type", help="Limit the pass to one facility type."),
    ] = None,
    commit_every: Annotated[
        int | None,
        typer.Option("--commit-every", min=1, help="Commit after roughly this many renames."),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum rename examples to include in the output."),
    ] = 20,
) -> None:
    """Move a consolidated facility's clean base slug from a merged tombstone.

    Numbered slugs were assigned before duplicates were merged. A survivor keeps
    the numbered slug while the tombstone holds the clean one, so the clean URL
    redirects. This pass gives the clean slug to the survivor and keeps the old
    numbered slug as a bookmark alias.
    """

    engine, session = _session()
    try:
        stats = consolidate_numeric_slugs(
            session,
            dry_run=not apply,
            limit=limit,
            facility_type=facility_type,
            example_limit=examples,
            commit_every=commit_every,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("normalize-display-names")
def normalize_display_names_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the display-name normalization. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum display names to normalize in this run."),
    ] = 100_000,
    commit_every: Annotated[
        int | None,
        typer.Option(
            "--commit-every",
            min=1,
            help=(
                "Commit completed batches in this size so a large pass keeps its "
                "progress. The default commits once at the end."
            ),
        ),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum change examples to include in the output."),
    ] = 20,
) -> None:
    """Title-case display names published entirely in capitals.

    Abbreviations, Roman numerals, ordinals, single letters and consonant-only
    initialisms keep their uppercase form. The source spelling is retained in
    ``official_name``, the source payload, and the field assertions.
    """

    engine, session = _session()
    try:
        stats = normalize_facility_display_names(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
            commit_every=commit_every,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("refine-health-ownership")
def refine_health_ownership_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the ownership refinements. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to update in this run."),
    ] = 50_000,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum examples to include in the output."),
    ] = 20,
) -> None:
    """Apply the DOH NHFR ownership sub-classification.

    Only broad ``GOVERNMENT_UNSPECIFIED`` / ``PRIVATE_UNSPECIFIED`` / unknown
    values are refined, and only within the facility's existing government or
    private major class. The subclassification and DOH facility code remain on
    the health profile as evidence.
    """

    engine, session = _session()
    try:
        stats = refine_health_ownership(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("normalize-health-subtypes")
def normalize_health_subtypes_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the subtype normalization. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to update in this run."),
    ] = 50_000,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum examples to include in the output."),
    ] = 20,
) -> None:
    """Replace raw accreditation labels with controlled health subtypes.

    PhilHealth benefit-package categories (``Postpartum``, ``GAMOT Package
    Providers``, ``LEVEL 1``) describe a package or a hospital level, not a
    physical facility class. Explicit facility labels are mapped; non-facility
    labels are cleared; unrecognised labels are reported and left unchanged.
    The raw value remains on the health profile and the source record.
    """

    engine, session = _session()
    try:
        stats = normalize_health_subtypes(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("normalize-school-subtypes")
def normalize_school_subtypes_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the subtype normalization. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to update in this run."),
    ] = 50_000,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum examples to include in the output."),
    ] = 20,
) -> None:
    """Replace raw map tags with controlled school subtypes.

    OpenStreetMap education layers publish ``school``, ``university`` or
    ``kindergarten`` as the subtype. Explicit school labels are mapped to the
    controlled vocabulary; labels that belong to another facility category are
    cleared; unrecognised labels are reported and left unchanged. The raw tag
    remains on the source record and the facility type is never changed.
    """

    engine, session = _session()
    try:
        stats = normalize_school_subtypes(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@app.command("merge-deped-prefixed-ids")
def merge_deped_prefixed_ids_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the verified merges. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum merges to apply in this run."),
    ] = 1000,
) -> None:
    """Merge EBEIS seven-digit prefixed IDs into their six-digit school.

    The EBEIS result set can list the same school under its official six-digit
    BEIS ID and a seven-digit level-prefixed variant (for example 403263 and
    1403263). The prefixed row is retained as source evidence but is not a
    second real-world school. Each merge is recorded as an accepted
    ``deped_prefixed_school_id`` candidate and can be undone with
    ``match-candidates-undo-merge``.
    """

    engine, session = _session()
    try:
        affected: set[uuid.UUID] = set()
        stats = merge_deped_prefixed_duplicates(
            session,
            dry_run=not apply,
            limit=limit,
            affected_facility_ids=affected,
        )
        if apply:
            if affected:
                build_attribute_fusions(session, facility_ids=affected)
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
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
            help="Candidate registry JSON. Defaults to data/sources/source-candidates.json.",
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
            help="Source register Markdown. Defaults to docs/sources.md.",
        ),
    ] = None,
    candidates: Annotated[
        Path | None,
        typer.Option(
            "--candidates",
            help="Candidate registry JSON. Defaults to data/sources/source-candidates.json.",
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
    if not errors:
        enrich_source_inventory(payload)
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


@app.command("source-report")
def source_report_command(
    register: Annotated[
        Path | None,
        typer.Option(
            "--register",
            help="Source register Markdown. Defaults to docs/sources.md.",
        ),
    ] = None,
    candidates: Annotated[
        Path | None,
        typer.Option(
            "--candidates",
            help="Candidate registry JSON. Defaults to data/sources/source-candidates.json.",
        ),
    ] = None,
    probes: Annotated[
        Path | None,
        typer.Option(
            "--probes",
            help="Probe ledger. Defaults to the 16 Nov 2026 category-search ledger.",
        ),
    ] = None,
    region_ledger: Annotated[
        Path | None,
        typer.Option(
            "--region-ledger",
            help="Region search ledger JSON. Defaults to data/sources/region-search-ledger.json.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Directory for probe-ledger.jsonl, gap-report.md and acquisition-plan.md. "
            "Defaults to var/reports.",
        ),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="Also write the enriched inventory JSON here."),
    ] = None,
    csv_output: Annotated[
        Path | None,
        typer.Option("--csv-output", help="Also write the enriched inventory CSV here."),
    ] = None,
) -> None:
    """Emit the data.md research deliverables from the merged source inventory.

    The command enriches the inventory with the required output fields, validates
    it, and writes the probe ledger, gap report and acquisition plan. It does not
    acquire a source, approve rights or publish records.
    """

    payload = build_source_inventory(register, candidates, probes)
    enrich_source_inventory(payload)
    errors = validate_report_fields(payload)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    written = write_source_reports(payload, output_dir=output_dir, region_ledger_path=region_ledger)
    inventory_written: list[Path] = []
    if json_output is not None or csv_output is not None:
        inventory_written = list(write_source_inventory(payload, json_output, csv_output))

    typer.echo(f"sources={len(payload.get('sources') or [])}")
    typer.echo(f"probe_ledger={written.probe_ledger}")
    typer.echo(f"gap_report={written.gap_report}")
    typer.echo(f"acquisition_plan={written.acquisition_plan}")
    for path in inventory_written:
        typer.echo(f"inventory={path}")


@app.command("rebuild-report")
def rebuild_report_command(
    register: Annotated[
        Path | None,
        typer.Option(
            "--register",
            help="Source register Markdown. Defaults to docs/sources.md.",
        ),
    ] = None,
    candidates: Annotated[
        Path | None,
        typer.Option(
            "--candidates",
            help="Candidate registry JSON. Defaults to data/sources/source-candidates.json.",
        ),
    ] = None,
    probes: Annotated[
        Path | None,
        typer.Option(
            "--probes",
            help="Fresh probe text ledger. Defaults to the newest probes-*.txt in "
            "var/reports/rebuild, then the register evidence ledger.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Directory for the data.md section 11.1 evidence pack. "
            "Defaults to var/reports/rebuild.",
        ),
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="Pre-rebuild counts JSON. Defaults to rebuild-baseline.json in the output dir.",
        ),
    ] = None,
    region_ledger: Annotated[
        Path | None,
        typer.Option(
            "--region-ledger",
            help="Region search ledger JSON. Defaults to data/sources/region-search-ledger.json.",
        ),
    ] = None,
    osm_fill: Annotated[
        Path | None,
        typer.Option(
            "--osm-fill",
            help="JSON report from fill-locations-from-osm. Defaults to "
            "osm-location-fills.json in the output dir.",
        ),
    ] = None,
    lgu_probe: Annotated[
        Path | None,
        typer.Option(
            "--lgu-probe",
            help="JSON evidence from the province/HUC official-domain sweep. "
            "Defaults to lgu-domain-probes.json in the output dir.",
        ),
    ] = None,
) -> None:
    """Write the complete data.md section 11.1 rebuild evidence pack.

    Every fact is read from the database, the retained releases, the merged source
    inventory or the supplied ledgers. Values that cannot be verified are written
    as UNKNOWN/NOT_VERIFIED; this command never invents coverage.
    """

    from .rebuild_reports import DEFAULT_OUTPUT_DIR

    target = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    if probes is None:
        fresh = sorted(target.glob("probes-*.txt"))
        if fresh:
            probes = fresh[-1]
    payload = build_source_inventory(register, candidates, probes)
    engine, session = _session()
    try:
        paths = write_rebuild_pack(
            session,
            payload,
            output_dir=target,
            baseline_path=baseline or target / "rebuild-baseline.json",
            region_ledger_path=region_ledger,
            osm_fill_path=osm_fill or target / "osm-location-fills.json",
            probe_ledger_path=target / "probe-ledger.jsonl",
            lgu_probe_path=lgu_probe or target / "lgu-domain-probes.json",
        )
    finally:
        session.close()
        engine.dispose()

    typer.echo(f"source_inventory={paths.source_inventory_json}")
    typer.echo(f"source_inventory_csv={paths.source_inventory_csv}")
    typer.echo(f"probe_ledger={paths.probe_ledger}")
    typer.echo(f"gap_report={paths.gap_report}")
    typer.echo(f"skipped_sources={paths.skipped_sources}")
    typer.echo(f"download_manifest={paths.download_manifest}")
    typer.echo(f"schema_observations={paths.schema_observations}")
    typer.echo(f"rights_register={paths.rights_register}")
    typer.echo(f"field_matrix={paths.field_matrix}")
    typer.echo(f"crosswalk_candidates={paths.crosswalk_candidates}")
    typer.echo(f"community_fallback={paths.community_fallback}")
    typer.echo(f"osm_location_fills={paths.osm_location_fills}")
    typer.echo(f"overlap_report={paths.overlap_report}")
    typer.echo(f"agency_domain_census={paths.agency_domain_census}")
    typer.echo(f"lgu_search_ledger={paths.lgu_search_ledger}")
    typer.echo(f"region_search_ledger={paths.region_search_ledger}")
    typer.echo(f"unresolved={paths.unresolved}")
    typer.echo(f"final_report={paths.final_report}")


@app.command("probe-sources")
def probe_sources_command(
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Directory for the dated text ledger and probe-ledger.jsonl. "
            "Defaults to var/reports/rebuild.",
        ),
    ] = None,
    include_candidates: Annotated[
        bool,
        typer.Option(
            "--candidates/--no-candidates",
            help="Probe every URL in data/sources/source-candidates.json.",
        ),
    ] = True,
    include_register: Annotated[
        bool,
        typer.Option(
            "--register/--no-register",
            help="Probe every URL in the docs/sources.md evidence register.",
        ),
    ] = True,
    delay: Annotated[
        float,
        typer.Option("--delay", help="Minimum seconds between requests to the same host."),
    ] = 1.5,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Per-request timeout in seconds."),
    ] = 45.0,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Probe only the first N targets (investigation aid)."),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the probe summary as JSON."),
    ] = False,
) -> None:
    """Fresh, polite re-probe of every registered source and candidate URL.

    One unauthenticated GET per URL, a truthful crawler user agent, a per-host
    delay, and no retry or access-control bypass. Failures and negative results
    are preserved in both the text ledger and probe-ledger.jsonl.
    """

    from .probe import collect_targets, probe_targets

    targets = collect_targets(
        include_candidates=include_candidates,
        include_register=include_register,
    )
    summary = probe_targets(
        targets,
        output_dir=output_dir,
        delay_seconds=delay,
        timeout_seconds=timeout,
        limit=limit,
    )
    if as_json:
        typer.echo(json.dumps(summary, indent=2))
    else:
        typer.echo(f"targets={summary['targets']}")
        typer.echo(f"outcomes={summary['by_outcome']}")
        typer.echo(f"origins={summary['by_origin']}")
        typer.echo(f"skip_reasons={summary['by_skip_reason']}")
        typer.echo(f"text_ledger={summary['text_ledger']}")
        typer.echo(f"jsonl_ledger={summary['jsonl_ledger']}")


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
    """List identity-match candidates and their automatic match state."""

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


@app.command("match-candidates-resolve")
def match_candidates_resolve(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the resolutions. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum pending candidates to resolve in this run."),
    ] = 10_000,
    reviewer: Annotated[
        str,
        typer.Option(help="Reviewer recorded on automatic merges and rejections."),
    ] = "system:match-candidate-resolution",
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum resolution examples to include in the output."),
    ] = 20,
) -> None:
    """Resolve every pending candidate against current evidence.

    A stale, cross-type, conflicting or weak pair is rejected and kept as
    audit history so it is not queued again. A pair that still meets the
    automatic consolidation rule is merged into its candidate target.
    """

    engine, session = _session()
    try:
        stats = resolve_pending_match_candidates(
            session,
            dry_run=not apply,
            limit=limit,
            reviewer=reviewer,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
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
    allow_facility_type_mismatch: Annotated[
        bool,
        typer.Option(
            "--allow-facility-type-mismatch",
            help=(
                "Explicitly merge a reviewed cross-type candidate. The surviving "
                "facility keeps its own type."
            ),
        ),
    ] = False,
) -> None:
    """Apply an accepted candidate: retire the source facility into the candidate facility."""

    _review_candidate(
        partial(
            merge_match_candidate,
            allow_facility_type_mismatch=allow_facility_type_mismatch,
        ),
        candidate_id,
        reviewer,
        note,
    )


@app.command("match-candidates-undo-merge")
def match_candidates_undo_merge(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for undoing the merge.")] = None,
) -> None:
    """Undo a merge and restore the source facility and its linked evidence."""

    _review_candidate(undo_match_merge, candidate_id, reviewer, note)


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
    reviewer: Annotated[
        str | None,
        typer.Option(
            help=(
                "Reviewer who accepted the registry rights decision. Required for any "
                "source that becomes public."
            )
        ),
    ] = None,
    note: Annotated[
        str | None,
        typer.Option(help="Rights-review note recorded on the publication gate."),
    ] = None,
) -> None:
    """Reconcile stored dataset rights/gates with the reviewed source registry.

    This does not ingest or publish records. Reprocess the affected releases
    afterwards so their records inherit the updated gate. A reviewer is required
    when the reconciliation makes a dataset public.
    """

    engine, session = _session()
    try:
        results = apply_publication_decisions(session, keys=source, reviewer=reviewer, note=note)
        typer.echo(json.dumps(results, indent=2, default=str))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
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
            typer.echo("No source checks recorded. Run 'philfacilities-ingest source check'.")
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


if __name__ == "__main__":
    app()
