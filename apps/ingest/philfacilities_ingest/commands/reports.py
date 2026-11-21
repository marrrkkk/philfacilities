"""CLI reports commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from philfacilities_api.models import (
    Dataset,
    Facility,
    IngestionRun,
    Release,
)
from sqlalchemy import func, select

from ..rebuild_reports import write_rebuild_pack
from ..source_candidates import (
    load_source_candidates,
    summarize_source_candidates,
    validate_source_candidates,
)
from ..source_inventory import (
    build_source_inventory,
    summarize_source_inventory,
    validate_source_inventory,
    write_source_inventory,
)
from ..source_report import enrich_source_inventory, validate_report_fields, write_source_reports
from .support import (
    SYNTHETIC_AGENCY_NAMES as SYNTHETIC_AGENCY_NAMES,
)
from .support import (
    _fixture_spec as _fixture_spec,
)
from .support import (
    _repair_agency_metadata as _repair_agency_metadata,
)
from .support import (
    _reset_demo as _reset_demo,
)
from .support import (
    _review_candidate as _review_candidate,
)
from .support import (
    _session as _session,
)
from .support import (
    demo_specs as demo_specs,
)


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
