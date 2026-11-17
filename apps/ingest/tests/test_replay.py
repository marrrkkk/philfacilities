"""Replay must recover per-dataset connector options from stored metadata."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from philfacilities_api.models import Agency, Dataset, Release
from philfacilities_ingest.replay import ReplayManifestError, _replay_options, _resolve_entry


class _FakeSession:
    def __init__(self, objects):
        self.objects = objects

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


class _FakeStore:
    def __init__(self, content: bytes = b"replay-bytes"):
        self.content = content

    def read(self, _uri: str) -> bytes:
        return self.content


def _release_objects(
    *,
    agency_code: str,
    dataset_slug: str,
    dataset_name: str,
) -> tuple[Release, Dataset, Agency, _FakeSession]:
    agency_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    release_id = uuid.uuid4()
    agency = SimpleNamespace(id=agency_id, short_code=agency_code)
    dataset = SimpleNamespace(
        id=dataset_id,
        agency_id=agency_id,
        slug=dataset_slug,
        name=dataset_name,
    )
    release = SimpleNamespace(
        id=release_id,
        dataset_id=dataset_id,
        raw_object_uri="raw/object.bin",
        sha256="0" * 64,
        source_release_label="REPLAY-RELEASE",
        retrieved_at=None,
        source_published_at=None,
        reference_period_start=None,
        reference_period_end=None,
    )
    session = _FakeSession(
        {
            (Release, release_id): release,
            (Dataset, dataset_id): dataset,
            (Agency, agency_id): agency,
        }
    )
    return release, dataset, agency, session


def test_replay_options_recover_ebeis_region_from_stored_dataset() -> None:
    options = _replay_options(
        "deped-ebeis",
        dataset_slug="deped-ebeis-masterlist-region-ii",
        dataset_name="DepEd EBEIS school masterlist (Region II result set)",
        entry={},
    )

    assert options == {"region": "region-ii"}
    # Explicit manifest options stay authoritative.
    assert _replay_options(
        "deped-ebeis",
        dataset_slug="deped-ebeis-masterlist-region-ii",
        dataset_name=None,
        entry={"options": {"region": "ncr"}},
    ) == {"region": "ncr"}
    with pytest.raises(ReplayManifestError, match="unknown EBEIS region"):
        _replay_options(
            "deped-ebeis",
            dataset_slug="deped-ebeis-masterlist-not-a-region",
            dataset_name=None,
            entry={},
        )


def test_replay_options_recover_philhealth_category_from_dataset_name() -> None:
    options = _replay_options(
        "philhealth",
        dataset_slug="philhealth-synthetic-clinic",
        dataset_name="PhilHealth — Clinic",
        entry={},
    )

    assert options == {"provider_category": "Clinic"}


def test_replay_resolves_a_regional_dataset_by_agency_not_catalogue_slug(monkeypatch) -> None:
    release, dataset, _agency, session = _release_objects(
        agency_code="deped",
        dataset_slug="deped-ebeis-masterlist-region-ii",
        dataset_name="DepEd EBEIS school masterlist (Region II result set)",
    )
    content = b"synthetic-ebeis"
    monkeypatch.setattr(
        "philfacilities_ingest.replay.hashlib.sha256",
        lambda _content: SimpleNamespace(hexdigest=lambda: release.sha256),
    )

    resolved = _resolve_entry(
        session=session,
        entry={"source": "deped-ebeis", "release_id": str(release.id)},
        store=_FakeStore(content),
    )

    assert resolved.dataset_slug == dataset.slug
    assert resolved.dataset_name == dataset.name
    assert resolved.options == {"region": "region-ii"}
    assert resolved.content == content


def test_replay_rejects_a_release_from_another_publisher(monkeypatch) -> None:
    release, _dataset, _agency, session = _release_objects(
        agency_code="doh",
        dataset_slug="deped-ebeis-masterlist-region-ii",
        dataset_name="DepEd EBEIS school masterlist (Region II result set)",
    )
    monkeypatch.setattr(
        "philfacilities_ingest.replay.hashlib.sha256",
        lambda _content: SimpleNamespace(hexdigest=lambda: release.sha256),
    )

    with pytest.raises(ReplayManifestError, match="belongs to agency 'doh'"):
        _resolve_entry(
            session=session,
            entry={"source": "deped-ebeis", "release_id": str(release.id)},
            store=_FakeStore(),
        )
