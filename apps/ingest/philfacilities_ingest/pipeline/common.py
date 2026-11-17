"""Shared primitives for the ingestion pipeline package.

``IngestResult``, engine helpers, and the small JSON/slug utilities are used by
every stage. Keeping them here prevents the stage modules from importing each
other for incidental helpers.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import IngestSettings
from .stats import IngestStats

# Flush pending canonical objects every N candidates. This is large enough that
# SQLAlchemy emits multi-row INSERT batches, and small enough that an 83k-row
# release does not hold every ORM object in memory at once.
APPLY_FLUSH_BATCH_SIZE = 2000


@dataclass
class IngestResult:
    dataset: str
    release_label: str
    release_id: str | None
    status: str
    report_json: str | None = None
    report_markdown: str | None = None
    stats: IngestStats = field(default_factory=IngestStats)
    issues: list[dict[str, Any]] = field(default_factory=list)


def build_engine(settings: IngestSettings):
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:120] or "record"


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _json(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value
