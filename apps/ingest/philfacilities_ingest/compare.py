"""Compare two retained source releases without mutating either one."""

from __future__ import annotations

from typing import Any

from philfacilities_api.models import Dataset, FacilitySourceLink, Release, SourceRecord
from sqlalchemy import select
from sqlalchemy.orm import Session


class ReleaseComparisonError(ValueError):
    """Raised when a requested release comparison cannot be resolved."""


def _release_summary(release: Release) -> dict[str, Any]:
    return {
        "release_id": str(release.id),
        "release_label": release.source_release_label,
        "source_published_at": release.source_published_at.isoformat()
        if release.source_published_at
        else None,
        "reference_period_start": release.reference_period_start.isoformat()
        if release.reference_period_start
        else None,
        "reference_period_end": release.reference_period_end.isoformat()
        if release.reference_period_end
        else None,
        "retrieved_at": release.retrieved_at.isoformat(),
        "sha256": release.sha256,
        "row_count_reported": release.row_count_reported,
        "row_count_parsed": release.row_count_parsed,
        "ingestion_status": release.ingestion_status,
        "publication_status": release.publication_status,
        "terms_review_status": release.terms_review_status,
    }


def _release_by_label(session: Session, dataset_id: Any, label: str) -> Release:
    rows = session.scalars(
        select(Release).where(
            Release.dataset_id == dataset_id,
            Release.source_release_label == label,
        )
    ).all()
    if not rows:
        raise ReleaseComparisonError(f"Release label {label!r} was not found for this dataset.")
    if len(rows) > 1:
        raise ReleaseComparisonError(
            f"Release label {label!r} is ambiguous for this dataset; compare by release ID instead."
        )
    return rows[0]


def _record_hashes(session: Session, release_id: Any) -> dict[str, str]:
    rows = session.execute(
        select(SourceRecord.source_record_key, SourceRecord.raw_record_hash).where(
            SourceRecord.release_id == release_id
        )
    ).all()
    return {key: value for key, value in rows}


def _facility_links(session: Session, release_id: Any) -> set[tuple[str, str]]:
    rows = session.execute(
        select(SourceRecord.source_record_key, FacilitySourceLink.facility_id)
        .join(FacilitySourceLink, FacilitySourceLink.source_record_id == SourceRecord.id)
        .where(SourceRecord.release_id == release_id)
    ).all()
    return {(key, str(facility_id)) for key, facility_id in rows}


def compare_releases(
    session: Session,
    *,
    dataset_slug: str,
    from_label: str | None = None,
    to_label: str | None = None,
    sample_limit: int = 10,
) -> dict[str, Any]:
    """Return a read-only diff between two releases of one dataset.

    With no labels, the two most recent releases (by retrieval time) are compared.
    Both labels must be supplied together; a single label is rejected rather than
    guessing the other side of the comparison.
    """

    if sample_limit < 0:
        raise ReleaseComparisonError("sample_limit must be non-negative.")
    if (from_label is None) != (to_label is None):
        raise ReleaseComparisonError(
            "Provide both --from and --to, or neither to compare the two latest releases."
        )

    datasets = session.scalars(select(Dataset).where(Dataset.slug == dataset_slug)).all()
    if not datasets:
        raise ReleaseComparisonError(f"Dataset {dataset_slug!r} was not found.")
    if len(datasets) > 1:
        raise ReleaseComparisonError(f"Dataset slug {dataset_slug!r} is ambiguous across agencies.")
    dataset = datasets[0]

    if from_label is None:
        releases = session.scalars(
            select(Release)
            .where(Release.dataset_id == dataset.id)
            .order_by(Release.retrieved_at, Release.created_at)
        ).all()
        if len(releases) < 2:
            raise ReleaseComparisonError(
                f"Dataset {dataset_slug!r} has fewer than two retained releases."
            )
        from_release, to_release = releases[-2], releases[-1]
    else:
        if to_label is None:
            raise ReleaseComparisonError(
                "Provide both --from and --to, or neither to compare the two latest releases."
            )
        from_release = _release_by_label(session, dataset.id, from_label)
        to_release = _release_by_label(session, dataset.id, to_label)

    if from_release.id == to_release.id:
        raise ReleaseComparisonError("The two selected releases are the same release.")

    from_hashes = _record_hashes(session, from_release.id)
    to_hashes = _record_hashes(session, to_release.id)
    from_keys = set(from_hashes)
    to_keys = set(to_hashes)
    retained_keys = from_keys & to_keys
    added_keys = sorted(to_keys - from_keys)
    removed_keys = sorted(from_keys - to_keys)
    changed_keys = sorted(key for key in retained_keys if from_hashes[key] != to_hashes[key])

    from_links = _facility_links(session, from_release.id)
    to_links = _facility_links(session, to_release.id)
    added_links = sorted(to_links - from_links)
    removed_links = sorted(from_links - to_links)

    return {
        "dataset": {
            "slug": dataset.slug,
            "name": dataset.name,
            "publication_status": dataset.publication_status,
        },
        "from": _release_summary(from_release),
        "to": _release_summary(to_release),
        "source_records": {
            "from": len(from_keys),
            "to": len(to_keys),
            "added": len(added_keys),
            "removed": len(removed_keys),
            "retained": len(retained_keys),
            "changed_payload": len(changed_keys),
            "sample_added": added_keys[:sample_limit],
            "sample_removed": removed_keys[:sample_limit],
            "sample_changed_payload": changed_keys[:sample_limit],
        },
        "facility_links": {
            "from": len(from_links),
            "to": len(to_links),
            "added": len(added_links),
            "removed": len(removed_links),
            "retained": len(from_links & to_links),
            "sample_added": [
                {"source_record_key": key, "facility_id": facility_id}
                for key, facility_id in added_links[:sample_limit]
            ],
            "sample_removed": [
                {"source_record_key": key, "facility_id": facility_id}
                for key, facility_id in removed_links[:sample_limit]
            ],
        },
    }
