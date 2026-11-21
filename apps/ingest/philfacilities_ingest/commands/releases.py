"""CLI releases commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from philfacilities_api.models import (
    Facility,
)
from sqlalchemy import func, select

from ..compare import ReleaseComparisonError, compare_releases
from ..manifest import render_release_notes, write_release_manifest
from ..release_rollback import ReleaseRollbackError, rollback_release
from ..sources.registry import (
    apply_publication_decisions,
    latest_checks,
    source_review_rows,
)
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
