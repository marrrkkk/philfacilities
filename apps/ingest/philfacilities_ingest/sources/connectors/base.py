"""Connector contracts shared by every source acquisition route.

Connectors own discovery and acquisition. They return one or more
:class:`AcquiredRelease` objects and never touch canonical tables. The runner
turns each acquired release into a ``ReleaseSpec`` and passes it to an adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from ...acquisition import AcquisitionError, HttpAcquirer
from ...config import IngestSettings
from ...contracts import ReleaseSpec, SourceAdapter
from ...skip_reasons import SkipDecision
from ..definitions import SourceDefinition

# A facility release goes through the normal staging/apply path. Geography and
# population releases have dedicated writers because they update reference data,
# not facilities.
KIND_FACILITY = "facility"
KIND_GEOGRAPHY = "geography"
KIND_POPULATION = "population"


@dataclass
class AcquisitionContext:
    """Per-run state handed to a connector."""

    settings: IngestSettings
    acquirer: HttpAcquirer | None = None
    input_path: Path | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    today: date = field(default_factory=date.today)

    def option(self, name: str, default: Any = None) -> Any:
        return self.options.get(name, default)

    def require_acquirer(self) -> HttpAcquirer:
        if self.acquirer is None:
            raise AcquisitionError(
                "This source needs an HTTP client; the connector was called without one."
            )
        return self.acquirer

    def read_input(self) -> bytes:
        if self.input_path is None:
            raise AcquisitionError("The connector requires --input for this operation.")
        return self.input_path.read_bytes()

    def input_retrieved_at(self) -> datetime:
        if self.input_path is None:
            return datetime.now(UTC)
        return datetime.fromtimestamp(self.input_path.stat().st_mtime, UTC)


@dataclass
class AcquiredRelease:
    """A payload acquired from a source, ready for parsing."""

    content: bytes
    filename: str
    release_label: str
    source_url: str
    retrieved_at: datetime
    adapter_factory: Callable[[ReleaseSpec], SourceAdapter] | None
    source_published_at: datetime | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    dataset_slug: str | None = None
    dataset_name: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    kind: str = KIND_FACILITY

    def to_spec(
        self,
        definition: SourceDefinition,
        *,
        enqueue_cross_source_matches: bool = False,
    ) -> ReleaseSpec:
        overrides: dict[str, Any] = {
            "release_label": self.release_label,
            "filename": self.filename,
            "content": self.content,
            "source_url": self.source_url,
            "source_published_at": self.source_published_at,
            "retrieved_at": self.retrieved_at,
            "reference_period_start": self.reference_period_start,
            "reference_period_end": self.reference_period_end,
            # Cross-source matching is an explicit post-ingest operation by
            # default. ``source run --enqueue-matches`` opts one release in.
            "enqueue_cross_source_matches": enqueue_cross_source_matches,
        }
        if self.dataset_slug:
            overrides["dataset_slug"] = self.dataset_slug
        if self.dataset_name:
            overrides["dataset_name"] = self.dataset_name
        if self.notes:
            overrides["notes"] = self.notes
        return definition.release_spec(**overrides)


@dataclass
class SkippedRelease:
    """One catalogue item that could not be acquired.

    A connector that fans out over several independent items (for example one
    PDF per PhilHealth provider category) yields this for a failed item instead
    of aborting the whole source. The runner records it as a controlled skip so
    the remaining items are still attempted and the failure is not silent.
    """

    filename: str | None
    dataset_slug: str | None
    decision: SkipDecision


class SourceConnector(Protocol):
    key: str

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease | SkippedRelease]: ...


class UnavailableConnector:
    """A blocked or human-assisted source with no automated acquisition route.

    ``reason`` is surfaced verbatim. The connector never fabricates a release and
    never retries a blocked endpoint with a different identity.
    """

    def __init__(self, key: str, reason: str) -> None:
        self.key = key
        self.reason = reason

    def discover(self, _ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        raise AcquisitionError(f"{self.key}: {self.reason}")
