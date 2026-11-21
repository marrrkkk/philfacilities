"""CLI pipeline commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer
from philfacilities_api.models import (
    Facility,
)
from philfacilities_api.rights import rights_allow_public
from sqlalchemy import select

from ..assertions import backfill_assertions
from ..config import get_settings
from ..contracts import ReleaseSpec
from ..fusion import (
    FUSION_STATUSES,
    apply_fusions,
    build_attribute_fusions,
    fusion_report,
)
from ..location_fill import fill_locations_from_osm
from ..osm_boundaries import (
    BOUNDARY_RELEASE_LABEL,
    boundary_artifacts,
    extract_osm_boundaries,
    import_osm_boundaries,
    sha256_file,
)
from ..pipeline import (
    run_ingestion,
    run_psgc_ingestion,
)
from ..psgc_fill import fill_location_psgc
from ..psgc_spatial_fill import fill_location_psgc_from_map
from ..sources.connectors.osm import (
    DEFAULT_PBF_PATH,
    PBF_SOURCE_PUBLISHED_AT,
    PBF_SOURCE_URL,
)
from ..sources.deped import DepEdEnrollmentAdapter, DepEdMasterlistAdapter, DepEdResourceAdapter
from ..sources.doh import DOHNHFRAdapter
from ..sources.philhealth import PhilHealthPdfAdapter
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
