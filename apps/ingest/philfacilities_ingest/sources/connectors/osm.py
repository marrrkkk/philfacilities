"""OpenStreetMap connectors.

Two acquisition routes exist:

* the HOT/BetterGov GeoParquet layers, one release per facility domain; and
* a local Geofabrik PBF snapshot filtered into a preserved Parquet extract for
  categories the hosted layers do not cover.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from ...acquisition import (
    AcquisitionError,
    classify_response,
    validate_signature,
)
from ..bettergov import OSMParquetAdapter
from ..osm_facilities import LAYER_FILES, OsmFacilityLayerAdapter
from ..osm_pbf import OsmPbfFacilityAdapter, extract_pbf_features
from .base import AcquiredRelease, AcquisitionContext

OSM_NOTES = (
    "HOT/OSM crowd-sourced extract. Coordinates are bbox-centre map geocodes; "
    "no operational status is inferred."
)
PBF_SOURCE_URL = "https://download.geofabrik.de/asia/philippines-261115.osm.pbf"
PBF_SOURCE_PUBLISHED_AT = datetime(2026, 11, 15, tzinfo=UTC)
DEFAULT_PBF_PATH = Path("/tmp/opencode/philippines.osm.pbf")
DEFAULT_EXTRACT_PATH = Path("var/extracts/osm-pbf-philippines.parquet")


class OsmParquetConnector:
    """Acquire one HOT/BetterGov GeoParquet layer."""

    def __init__(self, key: str, *, domain: str, url: str) -> None:
        self.key = key
        self.domain = domain
        self.url = url
        if domain in {"health", "education"}:
            self.filename = f"{domain}_facilities.parquet"
        else:
            self.filename = LAYER_FILES[domain]

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        if ctx.input_path is not None:
            content = ctx.read_input()
            retrieved_at = ctx.input_retrieved_at()
            notes = f"Controlled import of a preserved OSM {self.domain} GeoParquet artifact."
        else:
            acquirer = ctx.require_acquirer()
            result = acquirer.fetch(self.url, max_bytes=200 * 1024 * 1024)
            status = classify_response(result)
            if status != "ok":
                raise AcquisitionError(
                    f"OSM {self.domain} returned HTTP {result.status_code}.",
                    result=result,
                )
            validate_signature(result, filename=self.filename)
            content = result.content
            retrieved_at = datetime.now(UTC)
            notes = OSM_NOTES

        if self.domain in {"health", "education"}:
            adapter = lambda spec: OSMParquetAdapter(  # noqa: E731
                spec, facility_domain=self.domain
            )
        else:
            adapter = lambda spec: OsmFacilityLayerAdapter(spec, layer=self.domain)  # noqa: E731
        yield AcquiredRelease(
            content=content,
            filename=self.filename,
            release_label=f"HOT-OSM-PHL-{self.domain.upper()}-{ctx.today.isoformat()}",
            source_url=self.url,
            retrieved_at=retrieved_at,
            adapter_factory=adapter,
            notes=notes,
            metadata={"domain": self.domain},
        )


class OsmPbfConnector:
    """Filter a local OSM PBF snapshot and ingest the preserved extract."""

    key = "osm-pbf-facilities"

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        input_path = ctx.input_path or Path(str(ctx.option("pbf_path", DEFAULT_PBF_PATH)))
        extract_path = Path(str(ctx.option("extract_out", DEFAULT_EXTRACT_PATH)))
        reprocess = bool(ctx.option("reprocess", False))
        retrieved_at = datetime.now(UTC)

        if input_path.suffix.lower() == ".parquet" and input_path.exists():
            content = input_path.read_bytes()
            source_sha256 = ""
            extract_path = input_path
        else:
            if not input_path.exists():
                raise AcquisitionError(
                    f"OSM PBF input {input_path} does not exist. Pass --input with a local "
                    "Geofabrik .osm.pbf snapshot."
                )
            digest = hashlib.sha256()
            with input_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            source_sha256 = digest.hexdigest()
            if reprocess or not extract_path.exists():
                extract_path.parent.mkdir(parents=True, exist_ok=True)
                extract_pbf_features(
                    input_path,
                    extract_path,
                    source_url=PBF_SOURCE_URL,
                    source_sha256=source_sha256,
                )
            content = extract_path.read_bytes()

        yield AcquiredRelease(
            content=content,
            filename=extract_path.name,
            release_label=f"OSM-PBF-PHL-{ctx.today.isoformat()}",
            source_url=PBF_SOURCE_URL,
            retrieved_at=retrieved_at,
            adapter_factory=OsmPbfFacilityAdapter,
            source_published_at=PBF_SOURCE_PUBLISHED_AT,
            notes=(
                "Filtered extract of Geofabrik Philippines PBF snapshot dated 2026-11-15 "
                f"(sha256 {source_sha256}). Crowd-sourced map features; way coordinates "
                "are means of mapped nodes and no ownership, opening or operational "
                "status is inferred."
            ),
            metadata={"source_sha256": source_sha256, "extract": str(extract_path)},
        )
