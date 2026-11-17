"""Replay preserved raw releases through the current parser and writers.

A replay is a deliberate re-derivation of one already-preserved artifact. It
never re-downloads the source: the manifest points at a stored release or raw
object, the bytes are verified against their recorded SHA-256, and the bytes are
passed through the current connector and parser. The release checksum stays the
same, so the pipeline reprocesses the existing release instead of creating a
duplicate.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from philfacilities_api.models import Agency, Dataset, Release
from sqlalchemy.orm import Session

from .config import IngestSettings
from .source_runner import _apply_release, _json_metadata
from .sources.catalog import get_connector, get_definition
from .sources.connectors.base import AcquisitionContext, SkippedRelease
from .sources.registry import EBEIS_REGIONS
from .storage import RawStore, RawStoreIntegrityError, build_store


class ReplayManifestError(ValueError):
    """Raised when a replay manifest is malformed or cannot be resolved."""


@dataclass
class ReplayOutcome:
    source: str
    filename: str
    status: str = "failed"
    release_id: str | None = None
    sha256: str | None = None
    error: str | None = None
    stats: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "source": self.source,
            "filename": self.filename,
            "status": self.status,
        }
        if self.release_id:
            document["release_id"] = self.release_id
        if self.sha256:
            document["sha256"] = self.sha256
        if self.stats:
            document["stats"] = self.stats
        if self.error:
            document["error"] = self.error
        return document


@dataclass
class _ResolvedReplay:
    source: str
    content: bytes
    filename: str
    release_label: str
    sha256: str
    retrieved_at: datetime | None = None
    source_published_at: datetime | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    dataset_slug: str | None = None
    dataset_name: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


def load_replay_manifest(path: Path) -> list[dict[str, Any]]:
    """Load and shape-check a replay manifest."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReplayManifestError(f"Cannot read replay manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReplayManifestError(f"Replay manifest {path} is not valid JSON: {exc}") from exc
    entries = document.get("releases") if isinstance(document, Mapping) else document
    if not isinstance(entries, list) or not entries:
        raise ReplayManifestError(
            "Replay manifest must contain a non-empty top-level 'releases' list."
        )
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ReplayManifestError(f"Replay entry {index} must be a JSON object.")
        source = entry.get("source") or entry.get("key")
        if not source:
            raise ReplayManifestError(f"Replay entry {index} is missing 'source'.")
        if not entry.get("release_id") and not entry.get("raw_object_uri"):
            raise ReplayManifestError(
                f"Replay entry {index} needs either 'release_id' or 'raw_object_uri'."
            )
    return [dict(entry) for entry in entries]


def replay_manifest(
    *,
    session: Session,
    settings: IngestSettings,
    manifest_path: Path,
    store: RawStore | None = None,
) -> list[dict[str, Any]]:
    """Replay every entry in a manifest and return one outcome per entry."""

    store = store or build_store(settings)
    entries = load_replay_manifest(manifest_path)
    outcomes: list[ReplayOutcome] = []
    for entry in entries:
        outcomes.append(_replay_entry(session=session, settings=settings, entry=entry, store=store))
    return [outcome.to_dict() for outcome in outcomes]


def _replay_entry(
    *,
    session: Session,
    settings: IngestSettings,
    entry: dict[str, Any],
    store: RawStore,
) -> ReplayOutcome:
    source = str(entry.get("source") or entry.get("key"))
    filename = str(entry.get("filename") or "")
    try:
        resolved = _resolve_entry(session=session, entry=entry, store=store)
    except (ReplayManifestError, RawStoreIntegrityError, ValueError, KeyError) as exc:
        return ReplayOutcome(
            source=source,
            filename=filename or "<unresolved>",
            error=f"{type(exc).__name__}: {exc}",
        )

    try:
        definition = get_definition(resolved.source)
        connector = get_connector(resolved.source)
    except KeyError as exc:
        return ReplayOutcome(
            source=resolved.source,
            filename=resolved.filename,
            sha256=resolved.sha256,
            error=f"ReplayManifestError: {exc}",
        )
    with tempfile.TemporaryDirectory(prefix="philfacilities-replay-") as directory:
        artifact = Path(directory) / Path(resolved.filename).name
        artifact.write_bytes(resolved.content)
        ctx = AcquisitionContext(
            settings=settings,
            input_path=artifact,
            options=resolved.options,
        )
        try:
            acquired = list(connector.discover(ctx))
        except Exception as exc:
            return ReplayOutcome(
                source=resolved.source,
                filename=resolved.filename,
                sha256=resolved.sha256,
                error=f"{type(exc).__name__}: {exc}",
            )
        if len(acquired) != 1:
            return ReplayOutcome(
                source=resolved.source,
                filename=resolved.filename,
                sha256=resolved.sha256,
                error=(
                    "A replay entry must resolve to exactly one release; "
                    f"the connector returned {len(acquired)}."
                ),
            )
        release = acquired[0]
        if isinstance(release, SkippedRelease):
            return ReplayOutcome(
                source=resolved.source,
                filename=resolved.filename,
                sha256=resolved.sha256,
                error=release.decision.detail,
            )
        overrides: dict[str, Any] = {
            "release_label": resolved.release_label,
            "filename": resolved.filename,
            "retrieved_at": resolved.retrieved_at,
            "source_published_at": resolved.source_published_at,
            "reference_period_start": resolved.reference_period_start,
            "reference_period_end": resolved.reference_period_end,
        }
        if resolved.dataset_slug:
            overrides["dataset_slug"] = resolved.dataset_slug
        if resolved.dataset_name:
            overrides["dataset_name"] = resolved.dataset_name
        spec = replace(release.to_spec(definition), **overrides)
        try:
            outcome = _apply_release(
                definition,
                release,
                spec,
                session=session,
                settings=settings,
                # Replay explicitly re-derives the existing release.
                reprocess=True,
            )
        except Exception as exc:
            session.rollback()
            return ReplayOutcome(
                source=resolved.source,
                filename=resolved.filename,
                sha256=resolved.sha256,
                error=f"{type(exc).__name__}: {exc}",
            )
        return ReplayOutcome(
            source=resolved.source,
            filename=resolved.filename,
            status=outcome.status,
            release_id=outcome.release_id,
            sha256=resolved.sha256,
            stats={
                **outcome.stats,
                "acquisition": _json_metadata(outcome.metadata),
            },
        )


def _resolve_entry(*, session: Session, entry: dict[str, Any], store: RawStore) -> _ResolvedReplay:
    source = str(entry.get("source") or entry.get("key"))
    definition = get_definition(source)
    release_id = entry.get("release_id")
    if release_id:
        release = session.get(Release, _as_uuid(release_id))
        if release is None:
            raise ReplayManifestError(f"Release {release_id} does not exist.")
        dataset = session.get(Dataset, release.dataset_id)
        if dataset is None:
            raise ReplayManifestError(f"Release {release_id} has no dataset.")
        # Multi-dataset connectors (EBEIS regions, PhilHealth provider
        # categories) write dataset slugs that differ from the catalogue
        # default. Validate the publisher instead of requiring slug equality,
        # then replay into the stored dataset.
        agency = session.get(Agency, dataset.agency_id)
        if agency is None or agency.short_code != definition.agency.code:
            raise ReplayManifestError(
                f"Release {release_id} belongs to agency "
                f"{(agency.short_code if agency else None)!r}, not "
                f"{definition.agency.code!r} for source {source!r}."
            )
        if not release.raw_object_uri:
            raise ReplayManifestError(f"Release {release_id} has no preserved raw object.")
        content = store.read(release.raw_object_uri)
        if hashlib.sha256(content).hexdigest() != release.sha256:
            raise RawStoreIntegrityError(
                f"Release {release_id} bytes do not match its recorded SHA-256."
            )
        filename = str(entry.get("filename") or _filename_from_uri(release.raw_object_uri))
        return _ResolvedReplay(
            source=source,
            content=content,
            filename=filename,
            release_label=release.source_release_label,
            sha256=release.sha256,
            retrieved_at=release.retrieved_at,
            source_published_at=release.source_published_at,
            reference_period_start=release.reference_period_start,
            reference_period_end=release.reference_period_end,
            dataset_slug=dataset.slug,
            dataset_name=dataset.name,
            options=_replay_options(
                source,
                dataset_slug=dataset.slug,
                dataset_name=dataset.name,
                entry=entry,
            ),
        )

    uri = str(entry["raw_object_uri"])
    content = store.read(uri)
    digest = hashlib.sha256(content).hexdigest()
    expected = str(entry.get("sha256") or "")
    if expected and expected != digest:
        raise RawStoreIntegrityError(
            f"Raw object {uri} SHA-256 mismatch: expected {expected}, got {digest}."
        )
    filename = str(entry.get("filename") or _filename_from_uri(uri))
    release_label = str(entry.get("release_label") or f"REPLAY-{digest[:12].upper()}")
    dataset_slug = str(entry["dataset_slug"]) if entry.get("dataset_slug") else None
    dataset_name = str(entry["dataset_name"]) if entry.get("dataset_name") else None
    return _ResolvedReplay(
        source=source,
        content=content,
        filename=filename,
        release_label=release_label,
        sha256=digest,
        retrieved_at=_as_datetime(entry.get("retrieved_at")),
        source_published_at=_as_datetime(entry.get("source_published_at")),
        reference_period_start=_as_date(entry.get("reference_period_start")),
        reference_period_end=_as_date(entry.get("reference_period_end")),
        dataset_slug=dataset_slug,
        dataset_name=dataset_name,
        options=_replay_options(
            source,
            dataset_slug=dataset_slug,
            dataset_name=dataset_name,
            entry=entry,
        ),
    )


EBEIS_DATASET_PREFIX = "deped-ebeis-masterlist-"
PHILHEALTH_DATASET_NAME_PREFIX = "PhilHealth — "


def _replay_options(
    source: str,
    *,
    dataset_slug: str | None,
    dataset_name: str | None,
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Recover connector options from the stored dataset.

    Replay calls the connector with ``input_path``, so connector defaults would
    silently replay every EBEIS artifact as NCR and every PhilHealth PDF as the
    Hospital category. The dataset slug/name written by the original run is the
    durable record of those per-dataset options.
    """

    raw_options = entry.get("options") or {}
    if not isinstance(raw_options, Mapping):
        raise ReplayManifestError("Replay entry 'options' must be a JSON object.")
    options = dict(raw_options)

    if source == "deped-ebeis":
        region_key = None
        if dataset_slug and dataset_slug.startswith(EBEIS_DATASET_PREFIX):
            region_key = dataset_slug.removeprefix(EBEIS_DATASET_PREFIX)
        elif dataset_name:
            base = dataset_name.casefold()
            for key, (_id, name) in EBEIS_REGIONS.items():
                if base == f"deped ebeis school masterlist ({name.casefold()} result set)":
                    region_key = key
                    break
        if region_key is not None:
            if region_key not in EBEIS_REGIONS:
                raise ReplayManifestError(
                    f"Dataset {dataset_slug!r} names unknown EBEIS region {region_key!r}."
                )
            options.setdefault("region", region_key)

    if (
        source == "philhealth"
        and dataset_name
        and dataset_name.startswith(PHILHEALTH_DATASET_NAME_PREFIX)
    ):
        category = dataset_name.removeprefix(PHILHEALTH_DATASET_NAME_PREFIX).strip()
        if category:
            options.setdefault("provider_category", category)

    return options


def _filename_from_uri(uri: str) -> str:
    name = uri.rstrip("/").rsplit("/", 1)[-1]
    if "-" in name:
        candidate = name.split("-", 1)[1]
        if "." in candidate:
            return candidate
    return name or "replay.bin"


def _as_uuid(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ReplayManifestError(f"{value!r} is not a release UUID.") from exc


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ReplayManifestError(f"{value!r} is not an ISO-8601 timestamp.") from exc


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ReplayManifestError(f"{value!r} is not an ISO-8601 date.") from exc
