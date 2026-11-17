"""A failed EBEIS region must not hide the remaining regional result sets."""

from __future__ import annotations

from philfacilities_ingest.acquisition import AcquisitionError
from philfacilities_ingest.sources.connectors import ebeis as connector_module
from philfacilities_ingest.sources.connectors.base import (
    AcquiredRelease,
    AcquisitionContext,
    SkippedRelease,
)
from philfacilities_ingest.sources.connectors.ebeis import EbeisConnector


def test_one_failed_region_does_not_abort_remaining_regions(monkeypatch):
    monkeypatch.setattr(
        connector_module,
        "EBEIS_REGIONS",
        {"region-i": ("1", "Region I"), "region-ii": ("2", "Region II")},
    )

    def fake_fetch(_acquirer, region_key):
        if region_key == "region-i":
            raise AcquisitionError("DepEd EBEIS page 1 returned HTTP 503.")
        return b"<table><tr><th>School ID</th></tr></table>", {
            "reported_rows": 0,
            "fetched_pages": 1,
        }

    monkeypatch.setattr(connector_module, "fetch_ebeis_region", fake_fetch)
    ctx = AcquisitionContext(settings=object(), acquirer=object(), options={"region": "all"})
    releases = list(EbeisConnector().discover(ctx))

    assert len(releases) == 2
    skipped = releases[0]
    assert isinstance(skipped, SkippedRelease)
    assert skipped.dataset_slug == "deped-ebeis-masterlist-region-i"
    assert skipped.decision.reason == "HTTP_5XX"
    assert skipped.decision.next_retry_at

    acquired = releases[1]
    assert isinstance(acquired, AcquiredRelease)
    assert acquired.dataset_slug == "deped-ebeis-masterlist-region-ii"
    assert acquired.filename.endswith(".html")
    assert acquired.source_url == connector_module.EBEIS_MASTERLIST_URL
