"""CLI source commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from ..acquisition import (
    actionable_failures,
    send_failure_alert,
    send_ingestion_failure_alert,
)
from ..config import get_settings
from ..replay import ReplayManifestError, replay_manifest
from ..source_runner import run_selection, summarize_results, validate_source
from ..sources.catalog import SOURCES, catalog_rows, select_keys
from ..sources.registry import (
    check_sources,
    due_source_keys,
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
