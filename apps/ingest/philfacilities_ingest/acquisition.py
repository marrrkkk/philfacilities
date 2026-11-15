"""Shared acquisition primitives for every source connector.

This module deliberately contains no agency-specific parsing. It owns the parts
that must behave identically across connectors: identified user agents, retry and
backoff, conditional requests, response validation, checksums, and the append-only
monitoring ledger.

It never bypasses an access control. A 403, CAPTCHA, login wall, or licence gate is
recorded as a blocker and escalated to an operator instead of being retried with a
forged browser identity.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from philfacilities_api.models import Dataset, SourceCheck
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import IngestSettings

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
BLOCKER_MARKERS = (
    "just a moment",
    "cf-chl-",
    "cloudflare ray id",
    "captcha",
    "access denied",
    "attention required",
)


class AcquisitionError(RuntimeError):
    """A source request failed in a way the connector must not paper over."""

    def __init__(self, message: str, *, result: FetchResult | None = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)
    sha256: str = ""
    elapsed_ms: int = 0
    not_modified: bool = False
    error: str | None = None
    retry_after_seconds: float | None = None

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")

    @property
    def etag(self) -> str | None:
        return self.headers.get("etag")

    @property
    def last_modified(self) -> str | None:
        return self.headers.get("last-modified")

    @property
    def content_length(self) -> int | None:
        try:
            return int(self.headers["content-length"])
        except (KeyError, TypeError, ValueError):
            return len(self.content) if self.content else None


def user_agent(settings: IngestSettings) -> str:
    """Identify the crawler and a real contact route; never impersonate a browser."""

    return (
        "PhilFacilitiesSourceBot/0.1 "
        f"(open civic-data catalogue; contact {settings.source_contact})"
    )


class HttpAcquirer:
    """Small, testable HTTP client for source release discovery and download."""

    def __init__(
        self,
        settings: IngestSettings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 90.0,
        retries: int = 3,
    ) -> None:
        self.settings = settings or IngestSettings()
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={
                "User-Agent": user_agent(self.settings),
                "Accept": "*/*",
                "Accept-Language": "en-PH,en;q=0.8",
            },
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpAcquirer:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> FetchResult:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            started = time.monotonic()
            try:
                response = self._client.request(
                    method, url, data=data, json=json_body, headers=headers
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise AcquisitionError(f"{method} {url} failed: {exc}") from exc

            elapsed_ms = int((time.monotonic() - started) * 1000)
            content = response.content
            digest = hashlib.sha256(content).hexdigest() if content else ""
            result = FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content=content,
                headers={key.lower(): value for key, value in response.headers.items()},
                sha256=digest,
                elapsed_ms=elapsed_ms,
                not_modified=response.status_code == 304,
                retry_after_seconds=_retry_after(response.headers.get("retry-after")),
            )
            if max_bytes is not None and len(content) > max_bytes:
                raise AcquisitionError(
                    f"{method} {url} returned {len(content)} bytes, above the {max_bytes} byte "
                    "connector limit. No data was accepted.",
                    result=result,
                )
            if response.status_code in RETRYABLE_STATUS and attempt < self.retries:
                time.sleep(min(result.retry_after_seconds or (2**attempt), 30))
                continue
            return result
        raise AcquisitionError(f"{method} {url} failed after {self.retries} attempts: {last_error}")

    def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> tuple[Any, FetchResult]:
        result = self.fetch(url, headers=headers, max_bytes=max_bytes)
        _require_success(result)
        if is_blocker_page(result):
            raise AcquisitionError(
                f"{url} returned an access/verification page instead of data.", result=result
            )
        try:
            return json.loads(result.content), result
        except json.JSONDecodeError as exc:
            raise AcquisitionError(
                f"{url} did not return valid JSON: {exc}", result=result
            ) from exc

    def post_json(
        self,
        url: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> tuple[Any, FetchResult]:
        """POST a bounded JSON request and decode a JSON response."""

        result = self.fetch(
            url, method="POST", json_body=body, headers=headers, max_bytes=max_bytes
        )
        _require_success(result)
        if is_blocker_page(result):
            raise AcquisitionError(
                f"{url} returned an access/verification page instead of data.", result=result
            )
        try:
            return json.loads(result.content), result
        except json.JSONDecodeError as exc:
            raise AcquisitionError(
                f"{url} did not return valid JSON: {exc}", result=result
            ) from exc


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _require_success(result: FetchResult) -> None:
    if result.status_code >= 400:
        raise AcquisitionError(
            f"GET {result.url} returned HTTP {result.status_code}. "
            "The response was recorded; no release was accepted.",
            result=result,
        )


def is_blocker_page(result: FetchResult) -> bool:
    content_type = (result.content_type or "").lower()
    if "text/html" not in content_type and result.status_code < 400:
        return False
    text = result.content[:200_000].decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in BLOCKER_MARKERS)


def validate_signature(result: FetchResult, *, filename: str) -> None:
    """Fail closed when a payload is not the advertised file format."""

    content = result.content
    lower = filename.lower()
    if lower.endswith(".pdf") and not content.startswith(b"%PDF"):
        raise AcquisitionError(
            f"{filename} did not begin with a PDF signature; the server may have returned "
            "an HTML block or error page.",
            result=result,
        )
    if lower.endswith((".xlsx", ".zip", ".kmz", ".gpkg")) and not content.startswith(b"PK"):
        raise AcquisitionError(f"{filename} was not a ZIP-based file.", result=result)
    if lower.endswith(".parquet") and not content.startswith(b"PAR1"):
        raise AcquisitionError(f"{filename} was not a Parquet file.", result=result)
    if lower.endswith(".csv"):
        sample = content[:4096]
        if b"\x00" in sample:
            raise AcquisitionError(f"{filename} looked binary, not CSV.", result=result)
    if lower.endswith((".json", ".geojson")):
        try:
            json.loads(content[: 2 * 1024 * 1024] if len(content) < 2 * 1024 * 1024 else content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AcquisitionError(f"{filename} was not valid JSON: {exc}", result=result) from exc
    if is_blocker_page(result):
        raise AcquisitionError(
            f"{filename} was an access/verification page, not the requested source file.",
            result=result,
        )


def conditional_headers(last: SourceCheck | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if last and last.etag:
        headers["If-None-Match"] = last.etag
    if last and last.last_modified:
        headers["If-Modified-Since"] = last.last_modified
    return headers


def last_check(session: Session, dataset_id: uuid.UUID) -> SourceCheck | None:
    return session.scalars(
        select(SourceCheck)
        .where(SourceCheck.dataset_id == dataset_id)
        .order_by(SourceCheck.checked_at.desc())
        .limit(1)
    ).first()


def last_successful_check(session: Session, dataset_id: uuid.UUID) -> SourceCheck | None:
    return session.scalars(
        select(SourceCheck)
        .where(
            SourceCheck.dataset_id == dataset_id,
            SourceCheck.status.in_(("ok", "not_modified")),
        )
        .order_by(SourceCheck.checked_at.desc())
        .limit(1)
    ).first()


def record_check(
    session: Session,
    *,
    dataset: Dataset,
    result: FetchResult | None,
    status: str,
    message: str,
    next_check_at: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> SourceCheck:
    check = SourceCheck(
        dataset_id=dataset.id,
        checked_at=datetime.now(UTC),
        status=status,
        url=result.url if result else (details or {}).get("url", dataset.source_url or ""),
        final_url=result.final_url if result else None,
        http_status=result.status_code if result else None,
        etag=result.etag if result else None,
        last_modified=result.last_modified if result else None,
        content_type=result.content_type if result else None,
        content_length=result.content_length if result else None,
        sha256=result.sha256 if result and result.sha256 else None,
        duration_ms=result.elapsed_ms if result else None,
        message=message,
        details=details,
        next_check_at=next_check_at,
    )
    session.add(check)
    return check


def default_next_check(update_pattern: str | None) -> datetime:
    pattern = (update_pattern or "").lower()
    days = 7
    if "month" in pattern:
        days = 30
    elif "day" in pattern or "daily" in pattern:
        days = 1
    elif "quarter" in pattern:
        days = 90
    return datetime.now(UTC) + timedelta(days=days)


def classify_response(result: FetchResult) -> str:
    if result.not_modified:
        return "not_modified"
    if result.status_code in (401, 403):
        return "access_blocked"
    if result.status_code == 404:
        return "not_found"
    if result.status_code >= 500:
        return "source_error"
    if is_blocker_page(result):
        return "access_blocked"
    if result.status_code >= 400:
        return "http_error"
    return "ok"


ACTIONABLE_FAILURE_STATUSES = {
    "request_failed",
    "check_failed",
    "schema_changed",
    "source_error",
    "http_error",
}


def actionable_failures(results: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return checks that require operator action.

    A known access block or a broken published link is a documented blocker, not a
    new incident; it stays visible in the monitoring ledger without generating a
    duplicate alert on every scheduled run.
    """

    return {
        key: value
        for key, value in results.items()
        if str(value.get("status")) in ACTIONABLE_FAILURE_STATUSES
    }


def send_failure_alert(
    settings: IngestSettings,
    results: dict[str, dict[str, Any]],
    *,
    command: str,
) -> bool:
    """POST an actionable failure summary to the configured webhook, if any.

    Returns ``True`` only when a webhook was configured and accepted the alert.
    The payload contains source keys and check errors, never credentials or raw
    source records. Alert delivery failure is reported but must not roll back the
    checks that were already committed to the ledger.
    """

    failures = actionable_failures(results)
    if not settings.alert_webhook_url or not failures:
        return False
    payload = {
        "service": "philfacilities-ingest",
        "command": command,
        "checked_at": datetime.now(UTC).isoformat(),
        "failures": failures,
    }
    try:
        response = httpx.post(settings.alert_webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    return True
