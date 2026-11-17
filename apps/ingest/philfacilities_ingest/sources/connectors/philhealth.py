"""PhilHealth provider-catalogue connector.

The PhilHealth landing page publishes one PDF per provider category. Each PDF is
its own release and dataset. A controlled import of one preserved PDF is still
supported for parser repair and offline reruns.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime

from ...acquisition import (
    AcquisitionError,
    classify_response,
    validate_signature,
)
from ...skip_reasons import from_error, from_http_status
from ..philhealth import PhilHealthCatalogEntry, PhilHealthPdfAdapter, date_from_filename
from ..registry import philhealth_catalog, philhealth_dataset_slug
from .base import AcquiredRelease, AcquisitionContext, SkippedRelease

CATALOG_NOTES = (
    "PhilHealth public provider-category PDF. Publication relies on PhilHealth's "
    "published reuse statement; attribution retained."
)


# Kept importable for callers that still build a release label for a stored PDF.
def release_label_for(filename: str, basis: date | None) -> str:
    stem = filename.rsplit(".", 1)[0].upper()
    suffix = basis.isoformat() if basis else "UNDATED"
    return f"PHILHEALTH-{stem}-{suffix}"


class PhilHealthConnector:
    key = "philhealth"

    def _single(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        category = str(ctx.option("provider_category", "Hospital"))
        content = ctx.read_input()
        retrieved_at = ctx.input_retrieved_at()
        raw_name = ctx.input_path.name if ctx.input_path else "philhealth-provider.pdf"
        # Preserved raw objects are stored as "<checksum-prefix>-<original name>".
        filename = raw_name.split("-", 1)[1] if re.match(r"^[0-9a-f]{16}-", raw_name) else raw_name
        basis, basis_label = date_from_filename(filename)
        dataset_slug = philhealth_dataset_slug(
            PhilHealthCatalogEntry(
                filename=filename,
                url="",
                category=category,
                date_basis=basis,
                date_basis_label=basis_label,
            )
        )
        yield AcquiredRelease(
            content=content,
            filename=filename,
            release_label=release_label_for(filename, basis),
            source_url="",
            retrieved_at=retrieved_at,
            adapter_factory=lambda spec: PhilHealthPdfAdapter(spec, provider_category=category),
            source_published_at=(
                datetime(basis.year, basis.month, basis.day, tzinfo=UTC) if basis else None
            ),
            reference_period_start=basis,
            reference_period_end=basis,
            dataset_slug=dataset_slug,
            dataset_name=f"PhilHealth — {category}",
            notes=(
                "Controlled import of a preserved PhilHealth provider-category PDF. "
                f"Date basis: {basis_label}."
            ),
        )

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        if ctx.input_path is not None:
            yield from self._single(ctx)
            return

        acquirer = ctx.require_acquirer()
        entries = philhealth_catalog(acquirer)
        wanted = set(ctx.option("files") or [])
        if wanted:
            entries = [entry for entry in entries if entry.filename in wanted]
        if not entries:
            raise AcquisitionError("No matching PhilHealth catalogue entries.")
        for entry in entries:
            result = None
            status = None
            try:
                result = acquirer.fetch(entry.url)
                status = classify_response(result)
                if status != "ok":
                    raise AcquisitionError(
                        f"PhilHealth {entry.filename} returned HTTP {result.status_code} "
                        f"({status}).",
                        result=result,
                    )
                validate_signature(result, filename=entry.filename)
            except Exception as exc:
                # Each PDF is an independent release. One unreachable category must
                # not abort the remaining catalogue, and it must remain visible as a
                # controlled skip rather than disappearing from the run.
                if result is not None:
                    decision = from_http_status(
                        result.status_code,
                        detail=(
                            f"PhilHealth {entry.filename} could not be acquired: "
                            f"{type(exc).__name__}: {exc}"
                        )[:1000],
                        challenge=(
                            status == "access_blocked" and result.status_code not in (401, 403)
                        ),
                        alternate_route=(
                            "PhilHealth provider-category index page; retry this specific PDF."
                        ),
                    )
                else:
                    decision = from_error(
                        f"{type(exc).__name__}: {exc}",
                        alternate_route=(
                            "PhilHealth provider-category index page; retry this specific PDF."
                        ),
                    )
                yield SkippedRelease(
                    filename=entry.filename,
                    dataset_slug=philhealth_dataset_slug(entry),
                    decision=decision,
                )
                continue
            basis = entry.date_basis
            published_at = (
                datetime(basis.year, basis.month, basis.day, tzinfo=UTC) if basis else None
            )
            dataset_slug = philhealth_dataset_slug(entry)
            dataset_name = f"PhilHealth — {entry.category}"
            category = entry.category
            yield AcquiredRelease(
                content=result.content,
                filename=entry.filename,
                release_label=release_label_for(entry.filename, basis),
                source_url=entry.url,
                retrieved_at=datetime.now(UTC),
                adapter_factory=lambda spec, category=category: PhilHealthPdfAdapter(
                    spec, provider_category=category
                ),
                source_published_at=published_at,
                reference_period_start=basis,
                reference_period_end=basis,
                dataset_slug=dataset_slug,
                dataset_name=dataset_name,
                notes=(f"{CATALOG_NOTES} Date basis: {entry.date_basis_label}."),
                metadata={
                    "category": entry.category,
                    "date_basis": basis.isoformat() if basis else None,
                    "date_basis_label": entry.date_basis_label,
                },
            )
