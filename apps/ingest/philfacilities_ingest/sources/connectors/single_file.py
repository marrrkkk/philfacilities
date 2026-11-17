"""The generic one-artifact connector.

Most sources publish one file or one aggregated directory artifact at a stable
URL. :class:`SingleFileConnector` handles that shape: request (or read a preserved
fixture), validate the response, and hand the bytes to an adapter factory.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any

from ...acquisition import (
    AcquisitionError,
    HttpAcquirer,
    classify_response,
    validate_signature,
)
from ...contracts import ReleaseSpec, SourceAdapter
from .base import (
    KIND_FACILITY,
    AcquiredRelease,
    AcquisitionContext,
)

Fetcher = Callable[[HttpAcquirer], tuple[bytes, dict[str, Any]]]
DateText = Callable[[date], str]
DateValue = Callable[[date], date | None]
NoteText = Callable[[dict[str, Any]], str]


def _date_value(value: date | DateValue | None, today: date) -> date | None:
    return value(today) if callable(value) else value


def _note(value: str | NoteText | None, metadata: dict[str, Any]) -> str | None:
    return value(metadata) if callable(value) else value


class SingleFileConnector:
    """Acquire one release from a URL, an aggregating fetcher, or a local file."""

    def __init__(
        self,
        key: str,
        *,
        filename: DateText,
        release_label: DateText,
        adapter: Callable[[ReleaseSpec], SourceAdapter],
        url: str | None = None,
        fetcher: Fetcher | None = None,
        max_bytes: int | None = None,
        signature_filename: DateText | None = None,
        validate_signature_bytes: bool = True,
        reference_period_start: date | DateValue | None = None,
        reference_period_end: date | DateValue | None = None,
        source_published_at: datetime | None = None,
        notes: str | NoteText | None = None,
        input_notes: str | None = None,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
        dataset_slug: str | None = None,
        dataset_name: str | None = None,
    ) -> None:
        if url is None and fetcher is None:
            raise ValueError(f"{key}: SingleFileConnector needs a URL or a fetcher")
        self.key = key
        self.url = url
        self.fetcher = fetcher
        self.filename = filename
        self.release_label = release_label
        self.adapter = adapter
        self.max_bytes = max_bytes
        self.signature_filename = signature_filename
        self.validate_signature_bytes = validate_signature_bytes
        self.reference_period_start = reference_period_start
        self.reference_period_end = reference_period_end
        self.source_published_at = source_published_at
        self.notes = notes
        self.input_notes = input_notes
        self.method = method
        self.data = data
        self.timeout_seconds = timeout_seconds
        self.dataset_slug = dataset_slug
        self.dataset_name = dataset_name

    def _acquire(self, ctx: AcquisitionContext) -> tuple[bytes, str, dict[str, Any], datetime]:
        if ctx.input_path is not None:
            return (
                ctx.read_input(),
                self.url or "",
                {"controlled_import": str(ctx.input_path)},
                ctx.input_retrieved_at(),
            )

        acquirer = ctx.require_acquirer()
        if self.fetcher is not None:
            content, metadata = self.fetcher(acquirer)
            source_url = self.url or ""
            return content, source_url, metadata, datetime.now(UTC)

        assert self.url is not None
        result = acquirer.fetch(
            self.url,
            method=self.method,
            data=self.data,
            max_bytes=self.max_bytes,
        )
        status = classify_response(result)
        if status != "ok":
            raise AcquisitionError(
                f"{self.key} returned HTTP {result.status_code}; no release was accepted.",
                result=result,
            )
        if self.validate_signature_bytes:
            filename = (
                self.signature_filename(ctx.today)
                if self.signature_filename is not None
                else self.filename(ctx.today)
            )
            validate_signature(result, filename=filename)
        return (
            result.content,
            result.final_url,
            {"http_status": result.status_code},
            datetime.now(UTC),
        )

    def discover(self, ctx: AcquisitionContext) -> Iterable[AcquiredRelease]:
        content, source_url, metadata, retrieved_at = self._acquire(ctx)
        filename = self.filename(ctx.today)
        notes = self.input_notes if ctx.input_path is not None else _note(self.notes, metadata)
        yield AcquiredRelease(
            content=content,
            filename=filename,
            release_label=self.release_label(ctx.today),
            source_url=source_url,
            retrieved_at=retrieved_at,
            adapter_factory=self.adapter,
            source_published_at=self.source_published_at,
            reference_period_start=_date_value(self.reference_period_start, ctx.today),
            reference_period_end=_date_value(self.reference_period_end, ctx.today),
            dataset_slug=self.dataset_slug,
            dataset_name=self.dataset_name,
            notes=notes,
            metadata=metadata,
            kind=KIND_FACILITY,
        )
