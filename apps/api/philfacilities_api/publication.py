"""SQL predicates shared by public reads and ingestion-side selection.

The database is the contract for rights and publication. API reads and
ingestion-side fusion use these predicates so a claim cannot be public in one
path and internal in another. The module deliberately imports only models and
the controlled rights vocabulary; it has no dependency on API response schemas.
"""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select

from .models import Dataset, Release, SourceRecord
from .rights import PUBLIC_GATE_STATUSES, PUBLIC_RIGHTS


def latest_published_release_id(dataset_id_column):
    """Scalar subquery for the newest public release of a dataset.

    Public membership follows the latest published snapshot, not any release
    that once contained the record. If a later release drops a facility, the
    older link stops qualifying as current evidence. A failed newer attempt does
    not displace the last good release.
    """

    return (
        select(Release.id)
        .where(
            Release.dataset_id == dataset_id_column,
            Release.ingestion_status == "published",
            Release.publication_status.in_(tuple(PUBLIC_GATE_STATUSES)),
        )
        .order_by(Release.retrieved_at.desc(), Release.created_at.desc())
        .limit(1)
        .correlate_except(Release)
        .scalar_subquery()
    )


def public_dataset_release_condition():
    """True when the joined dataset/release pair may expose records publicly.

    Synthetic fixtures are demo data and keep their documented demo behaviour.
    A real pair must have rights-cleared redistribution and both the dataset and
    release publication gates in ``approved``/``published``.
    """

    return or_(
        Dataset.is_synthetic.is_(True),
        and_(
            Dataset.redistribution_status.in_(tuple(PUBLIC_RIGHTS)),
            Dataset.publication_status.in_(tuple(PUBLIC_GATE_STATUSES)),
            Release.publication_status.in_(tuple(PUBLIC_GATE_STATUSES)),
        ),
    )


def public_source_record_condition(record_id_column, *, require_current_release: bool = False):
    """True when a child row's source record is rights-cleared and published.

    Rows with no source record are legacy/manual canonical values and are left
    visible; rows attributable to a source must pass the same gate as source
    evidence. Synthetic fixtures keep their demo behaviour. Set
    ``require_current_release`` when only the dataset's latest published
    snapshot is acceptable evidence.
    """

    conditions = [
        SourceRecord.id == record_id_column,
        public_dataset_release_condition(),
    ]
    if require_current_release:
        conditions.append(Release.id == latest_published_release_id(Dataset.id))
    return or_(
        record_id_column.is_(None),
        exists(
            select(1)
            .select_from(SourceRecord)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .where(*conditions)
        ),
    )
