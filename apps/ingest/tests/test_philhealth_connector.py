"""PhilHealth catalogue fan-out must not let one dead PDF hide the rest."""

from __future__ import annotations

from datetime import date

from philfacilities_ingest.acquisition import FetchResult
from philfacilities_ingest.sources.connectors import philhealth as connector_module
from philfacilities_ingest.sources.connectors.base import (
    AcquiredRelease,
    AcquisitionContext,
    SkippedRelease,
)
from philfacilities_ingest.sources.connectors.philhealth import PhilHealthConnector
from philfacilities_ingest.sources.philhealth import PhilHealthCatalogEntry


class _FakeAcquirer:
    def __init__(self, results: dict[str, FetchResult]) -> None:
        self.results = results

    def fetch(self, url: str, **_kwargs) -> FetchResult:
        return self.results[url]


def _entry(filename: str, category: str, *, dated: bool = True) -> PhilHealthCatalogEntry:
    return PhilHealthCatalogEntry(
        filename=filename,
        url=f"https://example.gov.ph/{filename}",
        category=category,
        date_basis=date(2026, 9, 30) if dated else None,
        date_basis_label="date encoded in source file name" if dated else "undated",
    )


def test_one_missing_pdf_does_not_abort_the_catalogue(monkeypatch):
    missing = _entry("MISSING_093026.pdf", "Missing category")
    present = _entry("PRESENT_093026.pdf", "Present category")
    acquirer = _FakeAcquirer(
        {
            missing.url: FetchResult(
                url=missing.url,
                final_url=missing.url,
                status_code=404,
                content=b"not found",
            ),
            present.url: FetchResult(
                url=present.url,
                final_url=present.url,
                status_code=200,
                content=b"%PDF-1.4\nsynthetic-test-pdf\n",
                headers={"content-type": "application/pdf"},
            ),
        }
    )
    monkeypatch.setattr(
        connector_module, "philhealth_catalog", lambda _acquirer: [missing, present]
    )

    ctx = AcquisitionContext(settings=object(), acquirer=acquirer, options={})
    releases = list(PhilHealthConnector().discover(ctx))

    assert len(releases) == 2
    skipped = releases[0]
    assert isinstance(skipped, SkippedRelease)
    assert skipped.filename == missing.filename
    assert skipped.dataset_slug == "philhealth-missing"
    assert skipped.decision.reason == "HTTP_404"
    assert skipped.decision.next_retry_at

    acquired = releases[1]
    assert isinstance(acquired, AcquiredRelease)
    assert acquired.filename == present.filename
    assert acquired.dataset_slug == "philhealth-present"
    assert acquired.content.startswith(b"%PDF")
