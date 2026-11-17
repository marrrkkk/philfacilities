"""Reference-data connectors: PSGC geography and census population snapshots.

These releases do not create facilities. They produce ``AcquiredRelease`` objects
with ``kind`` set so the runner can call the geography or population writer.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from ...acquisition import AcquisitionError
from ..bettergov import load_psgc_release_payload
from ..bettergov_stats import (
    CENSUS_2024_DATASET_IDS,
    PopulationSnapshot,
    fetch_population_snapshot,
)
from ..registry import fetch_psgc_collections, psgc_release_content, psgc_units
from .base import KIND_GEOGRAPHY, KIND_POPULATION, AcquiredRelease, AcquisitionContext

PSGC_URL = "https://statistics.bettergov.ph/api/classification/psgc"
PSGC_RELEASE_LABEL = "PSGC-Q2-2024-BETTERGOV"
PSGC_FILENAME = "psgc-q2-2024-bettergov.json"


def population_snapshot_from_document(content: bytes) -> PopulationSnapshot:
    """Rebuild a snapshot from a preserved BetterGov raw artifact."""

    document = json.loads(content)
    return PopulationSnapshot(
        dataset_id=str(document.get("dataset_id", "preserved")),
        title=str(document.get("title", "Preserved population snapshot")),
        release=str(document.get("release", "")),
        psa_source_url=str(document.get("psa_source", "")),
        source_updated_at=_parse_datetime(document.get("source_updated_at")),
        retrieved_at=_parse_datetime(document.get("retrieved_at")),
        unit=document.get("unit"),
        dimensions=list(document.get("dimensions") or []),
        geographic_values=list(document.get("geographic_values") or []),
        parameter_values=list(document.get("parameter_values") or []),
        rows=list(document.get("rows") or []),
        reported_cells=None,
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class GeographyConnector:
    key = "bettergov-psgc"

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        if ctx.input_path is not None:
            content = ctx.read_input()
            collections = load_psgc_release_payload(content)
            units, warnings = psgc_units(collections)
            responses: list[Any] = []
            retrieved_at = ctx.input_retrieved_at()
            notes = "Controlled import of a preserved BetterGov PSGC Q2 2024 artifact."
        else:
            acquirer = ctx.require_acquirer()
            collections, responses = fetch_psgc_collections(acquirer)
            content = psgc_release_content(collections)
            units, warnings = psgc_units(collections)
            retrieved_at = datetime.now()
            notes = (
                "BetterGov mirror of the PSA PSGC Q2 2024 release. Supplementary "
                "geography, not the latest official PSA workbook."
            )
        if not units:
            raise AcquisitionError("PSGC API returned no administrative units.")
        yield AcquiredRelease(
            content=content,
            filename=PSGC_FILENAME,
            release_label=PSGC_RELEASE_LABEL,
            source_url=PSGC_URL,
            retrieved_at=retrieved_at,
            adapter_factory=None,
            reference_period_start=date(2024, 4, 1),
            reference_period_end=date(2024, 6, 30),
            notes=notes,
            metadata={
                "units": units,
                "warnings": warnings,
                "http_requests": len(responses),
            },
            kind=KIND_GEOGRAPHY,
        )


class PopulationConnector:
    key = "bettergov-population"

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        if ctx.input_path is not None:
            content = ctx.read_input()
            snapshot = population_snapshot_from_document(content)
            yield self._release(ctx, snapshot, content)
            return

        acquirer = ctx.require_acquirer()
        identifiers = list(ctx.option("datasets") or CENSUS_2024_DATASET_IDS)
        for identifier in identifiers:
            snapshot, _responses = fetch_population_snapshot(acquirer, identifier)
            yield self._release(ctx, snapshot, b"")

    def _release(
        self,
        _ctx: AcquisitionContext,
        snapshot: PopulationSnapshot,
        content: bytes,
    ) -> AcquiredRelease:
        token = _token(snapshot.region_label)
        return AcquiredRelease(
            content=content,
            filename=f"psa-2024-census-{token.lower()}.json",
            release_label=f"PSA-2024-CENSUS-{token}-2024-07-01",
            source_url=snapshot.psa_source_url,
            retrieved_at=snapshot.retrieved_at or datetime.now(),
            adapter_factory=None,
            reference_period_start=date(2024, 7, 1),
            reference_period_end=date(2024, 7, 1),
            notes=(
                f"PSA OpenSTAT table {snapshot.psa_source_url}; "
                f"BetterGov release {snapshot.release}."
            ),
            metadata={"snapshot": snapshot},
            kind=KIND_POPULATION,
        )


def _token(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")[:60] or "POPULATION"
