"""CLI discovery commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ..discovery import DISCOVERY_TARGETS, probe_discovery_targets
from ..lgu_inventory import validate_inventory
from ..scraper import CrawlPolicy, crawl, summary_json
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
