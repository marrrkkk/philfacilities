"""Source monitoring checks driven by ``SourceDefinition.check``.

The check path never downloads a release into canonical tables. It records one
append-only observation per source and compares the fetched checksum with the
latest published release when the source supports release discovery.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from philfacilities_api.models import Dataset, Release
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..acquisition import (
    AcquisitionError,
    FetchResult,
    HttpAcquirer,
    classify_response,
    conditional_headers,
    default_next_check,
    last_check,
    record_check,
)
from .catalog import SOURCES
from .definitions import SourceDefinition
from .philhealth import parse_catalog
from .registry import (
    REAL_SOURCES,
    detect_new_release,
    monitored_dataset,
    update_discovery_mode,
)


def _check_message(definition: SourceDefinition, status: str, result: FetchResult) -> str:
    if status == "ok":
        return f"{definition.agency.name} endpoint returned HTTP {result.status_code}."
    if status == "not_modified":
        return "Conditional request returned HTTP 304; the previous release remains current."
    if status == "access_blocked":
        return (
            "The source returned an access/verification page or an authentication denial. "
            "No bypass was attempted; a human-assisted or authorized route is required."
        )
    if status == "not_found":
        return "The published link returned HTTP 404. The previous release, if any, is retained."
    if status == "source_error":
        return f"The source returned HTTP {result.status_code}; the previous release is retained."
    return f"The source returned HTTP {result.status_code}; no release was accepted."


def _check_url(
    acquirer: HttpAcquirer,
    session: Session,
    definition: SourceDefinition,
) -> tuple[FetchResult, str]:
    source = REAL_SOURCES[definition.key]
    dataset: Dataset = monitored_dataset(session, source)
    previous = last_check(session, dataset.id)
    spec = definition.check
    target = spec.url or definition.access.source_url
    result = acquirer.fetch(
        target,
        method=spec.method,
        data=spec.data,
        headers=conditional_headers(previous),
    )
    status = classify_response(result)
    message = _check_message(definition, status, result)
    mode = update_discovery_mode(source)
    latest_release = session.scalars(
        select(Release)
        .where(
            Release.dataset_id == dataset.id,
            Release.ingestion_status == "published",
        )
        .order_by(Release.retrieved_at.desc())
        .limit(1)
    ).first()
    details: dict[str, Any] = {
        "source_key": definition.key,
        "rights": definition.rights.status,
        "access_method": definition.access.method,
        "update_discovery_mode": mode,
        "latest_published_release": (
            latest_release.source_release_label if latest_release else None
        ),
    }
    if spec.catalog == "philhealth" and status in {"ok", "not_modified"} and result.content:
        try:
            entries = parse_catalog(
                result.content.decode("utf-8", errors="replace"),
                base_url=target,
            )
            details["pdf_links"] = len(entries)
            details["pdf_files"] = [entry.filename for entry in entries]
            if not entries:
                status = "schema_changed"
                message = "PhilHealth index returned no provider-category PDF links."
        except Exception as exc:  # discovery must surface, not hide, a changed index
            status = "schema_changed"
            message = f"PhilHealth index could not be parsed: {exc}"
    if (
        spec.expected_marker
        and status == "ok"
        and spec.expected_marker not in result.content.decode("utf-8", errors="replace")
    ):
        status = "schema_changed"
        message = (
            f"The endpoint returned HTTP {result.status_code} but the expected "
            f"marker {spec.expected_marker!r} was absent; schema or access state changed."
        )
    if status == "ok":
        changed = detect_new_release(
            mode,
            result.sha256,
            latest_release.sha256 if latest_release else None,
        )
        details["new_release_detected"] = changed
        details["fetched_sha256"] = result.sha256 or None
        if changed:
            status = "update_available"
            message = (
                f"Fetched content differs from {latest_release.source_release_label}; "
                "a new source release is available for authorized acquisition."
            )
    record_check(
        session,
        dataset=dataset,
        result=result,
        status=status,
        message=message,
        next_check_at=default_next_check(definition.access.update_pattern),
        details=details,
    )
    return result, status


def check_sources(
    session: Session,
    *,
    keys: Iterable[str] | None = None,
    acquirer: HttpAcquirer | None = None,
) -> dict[str, dict[str, Any]]:
    """Check registered sources and append monitoring evidence.

    A blocked source is recorded, never retried with a forged identity. A source
    check does not publish or delete any release.
    """

    selected = list(keys) if keys else list(SOURCES)
    unknown = [key for key in selected if key not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source key(s): {', '.join(unknown)}")
    own_client = acquirer is None
    client = acquirer or HttpAcquirer()
    results: dict[str, dict[str, Any]] = {}
    try:
        for key in selected:
            definition = SOURCES[key]
            try:
                result, status = _check_url(client, session, definition)
                session.commit()
                results[key] = {
                    "status": status,
                    "http_status": result.status_code,
                    "url": result.final_url,
                    "blocked": status
                    in {"access_blocked", "not_found", "schema_changed", "source_error"},
                }
            except AcquisitionError as exc:
                session.rollback()
                results[key] = {"status": "request_failed", "error": str(exc), "blocked": True}
            except Exception as exc:  # keep one source failure from hiding the others
                session.rollback()
                results[key] = {"status": "check_failed", "error": str(exc), "blocked": True}
        return results
    finally:
        if own_client:
            client.close()
