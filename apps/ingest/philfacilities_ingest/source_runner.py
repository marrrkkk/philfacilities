"""Generic source execution for the CLI and scheduled jobs.

One runner handles every source: acquire through its connector, build a release
spec from the reviewed definition, then either validate in memory or apply
through the existing pipeline. Geography and population releases use their
dedicated writers; facility releases use the normal staging/apply path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .acquisition import HttpAcquirer
from .config import IngestSettings
from .pipeline import (
    IngestResult,
    run_geography_ingestion,
    run_ingestion,
)
from .skip_reasons import skip_for_source
from .sources.bettergov import load_psgc_release_payload
from .sources.bettergov_stats import load_population_snapshot
from .sources.catalog import get_connector, get_definition, select_keys
from .sources.connectors.base import (
    KIND_GEOGRAPHY,
    KIND_POPULATION,
    AcquiredRelease,
    AcquisitionContext,
    SkippedRelease,
)
from .sources.definitions import SourceDefinition


@dataclass
class SourceOutcome:
    key: str
    filename: str | None = None
    dataset: str | None = None
    status: str = "failed"
    release_id: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    issues: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    skip: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "key": self.key,
            "filename": self.filename,
            "dataset": self.dataset,
            "status": self.status,
        }
        if self.release_id:
            document["release_id"] = self.release_id
        if self.stats:
            document["stats"] = self.stats
        if self.issues:
            document["issues"] = self.issues
        if self.metadata:
            document["acquisition"] = self.metadata
        if self.error:
            document["error"] = self.error
        if self.skip:
            document["skip"] = self.skip
        return document


def previous_psgc_units(previous: Any, store: Any) -> list[Any]:
    """Load a previous real PSGC release from JSON or the synthetic workbook."""

    from .sources.psgc import parse_psgc_workbook

    content = store.read(previous.raw_object_uri) if previous.raw_object_uri else b""
    if content.lstrip().startswith(b"{"):
        collections = load_psgc_release_payload(content)
        units, _warnings = _psgc_units(collections)
        return units
    if content:
        units, _warnings = parse_psgc_workbook(content)
        return units
    return []


def _psgc_units(collections: dict[str, list[dict[str, Any]]]) -> tuple[list[Any], list[str]]:
    from .sources.registry import psgc_units

    return psgc_units(collections)


def _json_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop large in-memory payloads that are not meaningful in a CLI report."""

    return {
        key: value
        for key, value in metadata.items()
        if key not in {"units", "warnings", "snapshot"}
    }


def _spec_summary(spec: Any) -> dict[str, Any]:
    return {
        "dataset": spec.dataset_slug,
        "release_label": spec.release_label,
        "filename": spec.filename,
        "bytes": len(spec.content),
        "source_url": spec.source_url,
        "rights": spec.redistribution_status,
        "publication": spec.requested_publication_status,
    }


def _validate_release(
    definition: SourceDefinition,
    acquired: AcquiredRelease,
    spec: Any,
) -> SourceOutcome:
    if acquired.kind == KIND_GEOGRAPHY:
        units = acquired.metadata.get("units") or []
        warnings = acquired.metadata.get("warnings") or []
        return SourceOutcome(
            key=definition.key,
            filename=acquired.filename,
            dataset=spec.dataset_slug,
            status="validated",
            stats={"units": len(units), "warnings": len(warnings)},
            metadata=_json_metadata(acquired.metadata),
        )
    if acquired.kind == KIND_POPULATION:
        snapshot = acquired.metadata.get("snapshot")
        rows = len(snapshot.rows) if snapshot is not None else 0
        return SourceOutcome(
            key=definition.key,
            filename=acquired.filename,
            dataset=spec.dataset_slug,
            status="validated",
            stats={"observations": rows},
            metadata=_json_metadata(acquired.metadata),
        )
    if acquired.adapter_factory is None:
        return SourceOutcome(
            key=definition.key,
            filename=acquired.filename,
            dataset=spec.dataset_slug,
            status="failed",
            error="The acquired release has no adapter factory.",
        )
    adapter = acquired.adapter_factory(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    candidates = adapter.normalize(parsed)
    return SourceOutcome(
        key=definition.key,
        filename=acquired.filename,
        dataset=spec.dataset_slug,
        status="validated",
        stats={
            "parsed_rows": len(parsed.rows),
            "accepted_rows": validation.accepted_rows,
            "rejected_rows": validation.rejected_rows,
            "issues": len(validation.issues),
            "candidates": len(candidates),
        },
        issues=len(validation.issues),
        metadata=_json_metadata(acquired.metadata),
    )


def _apply_release(
    definition: SourceDefinition,
    acquired: AcquiredRelease,
    spec: Any,
    *,
    session: Session,
    settings: IngestSettings,
    reprocess: bool,
    force_reapply: bool = False,
) -> SourceOutcome:
    if acquired.kind == KIND_GEOGRAPHY:
        result: IngestResult = run_geography_ingestion(
            spec=spec,
            units=acquired.metadata.get("units") or [],
            warnings=acquired.metadata.get("warnings") or [],
            session=session,
            settings=settings,
            previous_units_loader=previous_psgc_units,
        )
        return SourceOutcome(
            key=definition.key,
            filename=acquired.filename,
            dataset=result.dataset,
            status=result.status,
            release_id=result.release_id,
            stats=result.stats,
            metadata=_json_metadata(acquired.metadata),
        )
    if acquired.kind == KIND_POPULATION:
        snapshot = acquired.metadata.get("snapshot")
        if snapshot is None:
            raise ValueError("Population acquisition did not provide a snapshot.")
        result = load_population_snapshot(
            session=session,
            settings=settings,
            snapshot=snapshot,
        )
        return SourceOutcome(
            key=definition.key,
            filename=acquired.filename,
            dataset=result.get("dataset"),
            status=result.get("status", "published"),
            release_id=result.get("release_id"),
            stats={
                key: value
                for key, value in result.items()
                if key not in {"dataset", "release_id", "status"}
            },
            metadata=_json_metadata(acquired.metadata),
        )
    if acquired.adapter_factory is None:
        raise ValueError("The acquired release has no adapter factory.")
    result = run_ingestion(
        spec=spec,
        adapter=acquired.adapter_factory(spec),
        session=session,
        settings=settings,
        reprocess=reprocess,
        force_reapply=force_reapply,
    )
    return SourceOutcome(
        key=definition.key,
        filename=acquired.filename,
        dataset=result.dataset,
        status=result.status,
        release_id=result.release_id,
        stats=result.stats,
        issues=len(result.issues),
        metadata=_json_metadata(acquired.metadata),
    )


def run_source(
    session: Session,
    settings: IngestSettings,
    key: str,
    *,
    reprocess: bool = False,
    force_reapply: bool = False,
    dry_run: bool = False,
    input_path: Path | None = None,
    options: dict[str, Any] | None = None,
    acquirer: HttpAcquirer | None = None,
    enqueue_matches: bool = False,
) -> list[SourceOutcome]:
    definition = get_definition(key)
    connector = get_connector(key)
    skip = skip_for_source(key)
    if skip is not None:
        return [
            SourceOutcome(
                key=key,
                dataset=definition.dataset.slug,
                status="skipped",
                skip=skip.as_dict(),
            )
        ]
    own_client = acquirer is None
    client = acquirer or HttpAcquirer(settings)
    acquired_options = dict(options or {})
    if reprocess:
        acquired_options["reprocess"] = True
    ctx = AcquisitionContext(
        settings=settings,
        acquirer=client,
        input_path=input_path,
        options=acquired_options,
    )
    outcomes: list[SourceOutcome] = []
    try:
        for acquired in connector.discover(ctx):
            if isinstance(acquired, SkippedRelease):
                outcomes.append(
                    SourceOutcome(
                        key=key,
                        filename=acquired.filename,
                        dataset=acquired.dataset_slug or definition.dataset.slug,
                        status="skipped",
                        error=acquired.decision.detail,
                        skip=acquired.decision.as_dict(),
                    )
                )
                continue
            spec = acquired.to_spec(definition, enqueue_cross_source_matches=enqueue_matches)
            try:
                if dry_run:
                    outcome = _validate_release(definition, acquired, spec)
                else:
                    outcome = _apply_release(
                        definition,
                        acquired,
                        spec,
                        session=session,
                        settings=settings,
                        reprocess=reprocess,
                        force_reapply=force_reapply,
                    )
            except Exception as exc:  # one release failure keeps the rest of a group running
                session.rollback()
                outcomes.append(
                    SourceOutcome(
                        key=key,
                        filename=acquired.filename,
                        dataset=spec.dataset_slug,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                        metadata=_json_metadata(acquired.metadata),
                    )
                )
                continue
            outcomes.append(outcome)
    except Exception as exc:
        session.rollback()
        message = f"{type(exc).__name__}: {exc}"
        # Discovery exceptions are unexpected failures, not controlled skips.
        # Reporting them as "skipped" hid them from actionable failure alerts.
        outcomes.append(
            SourceOutcome(
                key=key,
                dataset=definition.dataset.slug,
                status="failed",
                error=message,
            )
        )
    finally:
        if own_client:
            client.close()
    return outcomes


def validate_source(
    settings: IngestSettings,
    key: str,
    *,
    input_path: Path | None = None,
    options: dict[str, Any] | None = None,
    acquirer: HttpAcquirer | None = None,
) -> dict[str, Any]:
    """Run parse -> validate -> normalize with no database writes."""

    definition = get_definition(key)
    connector = get_connector(key)
    own_client = acquirer is None
    client = acquirer or HttpAcquirer(settings)
    ctx = AcquisitionContext(
        settings=settings,
        acquirer=client,
        input_path=input_path,
        options=dict(options or {}),
    )
    releases: list[dict[str, Any]] = []
    try:
        for acquired in connector.discover(ctx):
            spec = acquired.to_spec(definition)
            outcome = _validate_release(definition, acquired, spec)
            releases.append(
                {
                    **outcome.to_dict(),
                    "spec": _spec_summary(spec),
                }
            )
    except Exception as exc:
        releases.append(
            {
                "key": key,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    finally:
        if own_client:
            client.close()
    return {
        "key": key,
        "group": definition.group,
        "dataset": definition.dataset.slug,
        "rights": definition.rights.status,
        "publication": definition.rights.requested_publication_status,
        "fixture": str(input_path) if input_path else None,
        "releases": releases,
        "validated_at": datetime.now().isoformat(),
    }


def run_selection(
    session: Session,
    settings: IngestSettings,
    keys: list[str] | tuple[str, ...] | None = None,
    *,
    group: str | None = None,
    exclude: list[str] | tuple[str, ...] | None = None,
    reprocess: bool = False,
    force_reapply: bool = False,
    dry_run: bool = False,
    input_path: Path | None = None,
    options: dict[str, Any] | None = None,
    enqueue_matches: bool = False,
) -> list[dict[str, Any]]:
    selected = select_keys(keys, group=group, exclude=exclude)
    results: list[dict[str, Any]] = []
    for key in selected:
        outcomes = run_source(
            session,
            settings,
            key,
            reprocess=reprocess,
            force_reapply=force_reapply,
            dry_run=dry_run,
            input_path=input_path,
            options=options,
            enqueue_matches=enqueue_matches,
        )
        results.extend(outcome.to_dict() for outcome in outcomes)
    return results


def summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def dumps(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)
