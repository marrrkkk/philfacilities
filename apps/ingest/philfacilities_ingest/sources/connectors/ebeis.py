"""DepEd EBEIS multi-region connector.

Each region is a separate dataset and release. ``--region all`` walks every
verified region sequentially; pagination and pacing stay inside the existing
fetcher. A preserved aggregated HTML fixture can be imported with ``--input``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from ...acquisition import AcquisitionError
from ...skip_reasons import from_error
from ..deped_ebeis import DepEdEBEISAdapter
from ..registry import EBEIS_MASTERLIST_URL, EBEIS_REGIONS, fetch_ebeis_region
from .base import AcquiredRelease, AcquisitionContext, SkippedRelease


class EbeisConnector:
    key = "deped-ebeis"

    def _dataset(self, region_key: str) -> tuple[str, str, str]:
        _region_id, region_name = EBEIS_REGIONS[region_key]
        if region_key == "ncr":
            return (
                "deped-ebeis-masterlist-ncr",
                "DepEd EBEIS school masterlist (NCR result set)",
                region_name,
            )
        return (
            f"deped-ebeis-masterlist-{region_key}",
            f"DepEd EBEIS school masterlist ({region_name} result set)",
            region_name,
        )

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        region = str(ctx.option("region", "ncr"))
        keys = list(EBEIS_REGIONS) if region == "all" else [region]
        unknown = [key for key in keys if key not in EBEIS_REGIONS]
        if unknown:
            raise AcquisitionError(
                f"Unknown EBEIS region(s) {unknown}; known: {sorted(EBEIS_REGIONS)}; use 'all'"
            )

        if ctx.input_path is not None:
            if len(keys) != 1:
                raise AcquisitionError("--input requires a single --region for EBEIS.")
            region_key = keys[0]
            region_id, region_name = EBEIS_REGIONS[region_key]
            slug, name, _ = self._dataset(region_key)
            content = ctx.read_input()
            retrieved_at = ctx.input_retrieved_at()
            yield AcquiredRelease(
                content=content,
                filename=(
                    f"deped-ebeis-masterlist-{region_key}-{retrieved_at.date().isoformat()}.html"
                ),
                release_label=(
                    f"DEPED-EBEIS-{region_key.upper()}-{retrieved_at.date().isoformat()}"
                ),
                source_url=EBEIS_MASTERLIST_URL,
                retrieved_at=retrieved_at,
                adapter_factory=DepEdEBEISAdapter,
                dataset_slug=slug,
                dataset_name=name,
                notes="Controlled import of a preserved EBEIS aggregated result set.",
                metadata={"region": region_key, "region_id": region_id, "region_name": region_name},
            )
            return

        acquirer = ctx.require_acquirer()
        for region_key in keys:
            region_id, region_name = EBEIS_REGIONS[region_key]
            slug, name, _ = self._dataset(region_key)
            try:
                content, metadata = fetch_ebeis_region(acquirer, region_key)
            except Exception as exc:
                # Each region is an independent dataset. A failed result set is
                # recorded as a controlled skip; the remaining regions still run.
                yield SkippedRelease(
                    filename=f"deped-ebeis-masterlist-{region_key}",
                    dataset_slug=slug,
                    decision=from_error(
                        f"{type(exc).__name__}: {exc}",
                        alternate_route=(
                            "Retry the public EBEIS masterlist form for this region; "
                            "other regional result sets remain independent."
                        ),
                    ),
                )
                continue
            yield AcquiredRelease(
                content=content,
                filename=(f"deped-ebeis-masterlist-{region_key}-{ctx.today.isoformat()}.html"),
                release_label=f"DEPED-EBEIS-{region_key.upper()}-{ctx.today.isoformat()}",
                source_url=EBEIS_MASTERLIST_URL,
                retrieved_at=datetime.now(UTC),
                adapter_factory=DepEdEBEISAdapter,
                dataset_slug=slug,
                dataset_name=name,
                notes=(
                    f"Public EBEIS result set for {region_name} (region_id {region_id}): "
                    f"{metadata.get('reported_rows')} rows across "
                    f"{metadata.get('fetched_pages')} pages. Aggregated acquisition "
                    "artifact; internal-only pending terms/privacy review."
                ),
                metadata={"region": region_key, "region_id": region_id, **metadata},
            )
