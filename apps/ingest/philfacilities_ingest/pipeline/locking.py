"""Per-dataset ingestion locks.

Two scheduled runs of the same dataset must never stage or apply rows at the
same time. The release row's checksum constraint catches a duplicate insert,
but it does not stop two different files from interleaving canonical writes.
A transaction-scoped lock is not sufficient because the runner commits several
times during one release (preserve, stage, apply, report), so this module holds
a PostgreSQL session-level advisory lock on a dedicated connection for the whole
release lifecycle.

A second process fails fast instead of waiting: the caller records a failed
outcome and the next scheduled run retries. A crashed process releases the lock
when its database connection closes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

LOCK_NAMESPACE = "philfacilities:ingest"


class IngestionLockError(RuntimeError):
    """Raised when another process is already ingesting the same dataset."""


def ingestion_lock_key(agency_code: str, dataset_slug: str) -> str:
    """Return the stable advisory-lock key for one agency dataset."""

    return f"{LOCK_NAMESPACE}:{agency_code}:{dataset_slug}"


@contextmanager
def dataset_ingestion_lock(
    session: Session, *, agency_code: str, dataset_slug: str
) -> Iterator[None]:
    """Hold the dataset lock for the duration of the context.

    The lock uses a dedicated connection so the runner's intermediate commits do
    not release it. It is always unlocked before the connection is returned to
    the pool; PostgreSQL session-level locks would otherwise outlive the caller.
    """

    bind = session.get_bind()
    engine = getattr(bind, "engine", bind)
    if not isinstance(engine, Engine):
        raise RuntimeError("dataset ingestion locks require an engine-bound session")
    connection: Connection = engine.connect()
    key = ingestion_lock_key(agency_code, dataset_slug)
    acquired = False
    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": key},
            ).scalar()
        )
        if not acquired:
            raise IngestionLockError(
                f"Dataset {agency_code}/{dataset_slug} is already being ingested by "
                "another process; refusing to interleave canonical writes."
            )
        yield
    finally:
        if acquired:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": key},
            )
            connection.commit()
        connection.close()
