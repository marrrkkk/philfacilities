"""Record current URL evidence for acquired artifacts.

`data.md` section 11.1 requires the download manifest to record the URL, final
URL and HTTP status of every acquired artifact. Most sources also get a
`source_checks` row from `probe-sources`, but dynamically discovered datasets
(for example one PhilHealth PDF per provider category) may have a release and no
check. This script fills that gap with one unauthenticated HEAD request per
artifact URL and appends the real result. It never downloads or changes a
release, and it never invents a status.

Usage:
    uv run python scripts/verify_release_urls.py
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from philfacilities_api.models import Dataset, Release, SourceCheck
from philfacilities_ingest.acquisition import (
    HttpAcquirer,
    classify_response,
    record_check,
)
from philfacilities_ingest.cli import _session
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check every dataset with a published release, including checked ones.",
    )
    args = parser.parse_args()

    engine, session = _session()
    client = HttpAcquirer()
    recorded: list[tuple[str, int, str | None, str | None]] = []
    try:
        checked_ids = set(session.scalars(select(SourceCheck.dataset_id)))
        datasets = session.execute(
            select(Dataset)
            .join(Release, Release.dataset_id == Dataset.id)
            .where(Release.ingestion_status == "published")
            .group_by(Dataset.id)
            .order_by(Dataset.slug)
        ).scalars()
        targets = [dataset for dataset in datasets if args.all or dataset.id not in checked_ids]
        print(f"artifact URLs to check: {len(targets)}")
        for dataset in targets:
            if not dataset.source_url:
                print(f"SKIP {dataset.slug}: no source_url")
                continue
            result = client.fetch(dataset.source_url, method="HEAD")
            status = classify_response(result)
            latest = session.scalars(
                select(Release)
                .where(
                    Release.dataset_id == dataset.id,
                    Release.ingestion_status == "published",
                )
                .order_by(Release.retrieved_at.desc())
                .limit(1)
            ).first()
            record_check(
                session,
                dataset=dataset,
                result=result,
                status=status,
                message=(
                    "Dated HEAD verification of the acquired artifact URL; "
                    "no download was performed and no release was changed."
                ),
                details={
                    "verification": "post_rebuild_head",
                    "release_label": latest.source_release_label if latest else None,
                },
            )
            session.commit()
            recorded.append(
                (
                    dataset.slug,
                    result.status_code,
                    result.final_url,
                    result.content_type,
                )
            )
            print(
                f"{dataset.slug}: http={result.status_code} "
                f"type={result.content_type} final_url={result.final_url}"
            )
    finally:
        client.close()
        session.close()
        engine.dispose()

    print(f"recorded={len(recorded)} at {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    main()
