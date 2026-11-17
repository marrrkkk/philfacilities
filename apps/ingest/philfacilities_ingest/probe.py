"""Polite, dated re-probing of every registered source and candidate URL.

data.md section 6.5 requires a fresh probe of every source in the candidate
register and every registered source before a rebuild. This module makes one
normal, unauthenticated GET per URL, records the result even when it is a
failure, and never retries or bypasses an access control. The text ledger is
compatible with :mod:`philfacilities_ingest.source_inventory`; the JSONL ledger
keeps the richer provenance for the rebuild pack.
"""

from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .acquisition import FetchResult, is_blocker_page, user_agent
from .config import IngestSettings
from .skip_reasons import (
    DEFAULT_RETRY_DAYS,
    from_error,
    from_http_status,
    next_retry,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "var" / "reports" / "rebuild"


@dataclass
class ProbeTarget:
    key: str
    url: str
    custodian: str | None = None
    title: str | None = None
    alternate_route: str | None = None
    origin: str = "source"


@dataclass
class ProbeRecord:
    key: str
    url: str
    observed_at: str
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    received_bytes: int | None = None
    content_truncated: bool = False
    elapsed_ms: int | None = None
    error: str | None = None
    outcome: str = "TRANSPORT_ERROR"
    challenge_detected: bool = False
    skip_reason: str | None = None
    skip_detail: str | None = None
    alternate_route: str | None = None
    next_retry_at: str | None = None
    custodian: str | None = None
    title: str | None = None
    origin: str = "source"
    headers: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def _add(
    targets: dict[str, ProbeTarget],
    *,
    key: str,
    url: str | None,
    custodian: str | None = None,
    title: str | None = None,
    alternate_route: str | None = None,
    origin: str = "source",
) -> None:
    if not url or not url.startswith(("http://", "https://")):
        return
    clean = url.split("#", 1)[0].strip()
    if not clean or clean in targets:
        return
    targets[clean] = ProbeTarget(
        key=key,
        url=clean,
        custodian=custodian,
        title=title,
        alternate_route=alternate_route,
        origin=origin,
    )


def collect_targets(
    *,
    include_candidates: bool = True,
    include_register: bool = True,
) -> list[ProbeTarget]:
    """Every registered source and candidate URL, deduplicated by exact URL."""

    from .skip_reasons import skip_for_source
    from .source_inventory import load_source_candidates, parse_register
    from .sources.catalog import SOURCES

    targets: dict[str, ProbeTarget] = {}
    for key, definition in sorted(SOURCES.items()):
        decision = skip_for_source(key)
        alternate = decision.alternate_route if decision else None
        _add(
            targets,
            key=key,
            url=definition.check.url or definition.access.source_url,
            custodian=definition.agency.name,
            title=definition.dataset.name,
            alternate_route=alternate,
            origin="registered",
        )

    if include_candidates:
        for candidate in load_source_candidates().get("sources") or []:
            key = str(candidate.get("source_id") or "")
            for url in candidate.get("urls") or []:
                _add(
                    targets,
                    key=key,
                    url=url,
                    custodian=candidate.get("custodian"),
                    title=candidate.get("title"),
                    alternate_route=candidate.get("next_action"),
                    origin="candidate",
                )

    if include_register:
        rows, _baseline = parse_register()
        for row in rows:
            for url in row.urls:
                _add(
                    targets,
                    key=row.source_id,
                    url=url,
                    custodian=row.custodian,
                    title=row.title,
                    origin="register",
                )

    return list(targets.values())


def _probe_one(
    target: ProbeTarget,
    *,
    client: httpx.Client,
    timeout_seconds: float,
    max_bytes: int,
) -> ProbeRecord:
    observed_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    try:
        with client.stream("GET", target.url) as response:
            declared = response.headers.get("content-length")
            chunks: list[bytes] = []
            received = 0
            truncated = False
            for chunk in response.iter_bytes():
                remaining = max_bytes - received
                if remaining <= 0:
                    truncated = True
                    break
                if len(chunk) > remaining:
                    chunks.append(chunk[:remaining])
                    received += remaining
                    truncated = True
                    break
                chunks.append(chunk)
                received += len(chunk)
            content = b"".join(chunks)
            status_code = response.status_code
            final_url = str(response.url)
            content_type = response.headers.get("content-type")
            headers = {
                name: response.headers.get(name)
                for name in ("server", "cf-ray", "via", "x-cache", "location")
                if response.headers.get(name)
            }
    except httpx.HTTPError as exc:
        message = f"{type(exc).__name__}: {exc}"
        decision = from_error(message, alternate_route=target.alternate_route)
        return ProbeRecord(
            key=target.key,
            url=target.url,
            observed_at=observed_at,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            error=message,
            outcome="TRANSPORT_ERROR",
            skip_reason=decision.reason,
            skip_detail=decision.detail,
            alternate_route=decision.alternate_route,
            next_retry_at=decision.next_retry_at,
            custodian=target.custodian,
            title=target.title,
            origin=target.origin,
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    declared_size = int(declared) if declared and declared.isdigit() else None
    record = ProbeRecord(
        key=target.key,
        url=target.url,
        observed_at=observed_at,
        status_code=status_code,
        final_url=final_url,
        content_type=content_type,
        size_bytes=declared_size if declared_size is not None else received,
        received_bytes=received,
        content_truncated=truncated,
        elapsed_ms=elapsed_ms,
        custodian=target.custodian,
        title=target.title,
        origin=target.origin,
        headers=headers,
    )
    if response.status_code == 200:
        challenge = is_blocker_page(
            FetchResult(
                url=target.url,
                final_url=str(response.url),
                status_code=response.status_code,
                content=content,
                headers={key.lower(): value for key, value in response.headers.items()},
            )
        )
        if challenge:
            record.challenge_detected = True
            record.outcome = "WAF_CHALLENGE"
            decision = from_http_status(
                403,
                detail="HTTP 200 access/verification page detected (WAF challenge).",
                alternate_route=target.alternate_route,
                challenge=True,
            )
        else:
            record.outcome = "HTTP_200"
            return record
    elif response.status_code == 403:
        record.outcome = "HTTP_403"
        record.challenge_detected = True
        decision = from_http_status(
            403,
            detail=f"HTTP 403 from {target.url}",
            alternate_route=target.alternate_route,
            challenge=True,
        )
    else:
        record.outcome = f"HTTP_{response.status_code}"
        decision = from_http_status(
            response.status_code,
            detail=f"HTTP {response.status_code} from {target.url}",
            alternate_route=target.alternate_route,
        )
    record.skip_reason = decision.reason
    record.skip_detail = decision.detail
    record.alternate_route = decision.alternate_route
    record.next_retry_at = decision.next_retry_at
    return record


def probe_targets(
    targets: list[ProbeTarget],
    *,
    output_dir: str | Path | None = None,
    settings: IngestSettings | None = None,
    delay_seconds: float = 1.5,
    timeout_seconds: float = 45.0,
    max_bytes: int = 2_000_000,
    limit: int | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Probe each URL once, respecting a per-host delay, and write both ledgers."""

    target_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    settings = settings or IngestSettings()
    selected = targets[:limit] if limit is not None else targets

    last_by_host: dict[str, float] = defaultdict(float)
    records: list[ProbeRecord] = []
    own_client = client is None
    active_client = client or httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={
            "User-Agent": user_agent(settings),
            "Accept": "*/*",
            "Accept-Language": "en-PH,en;q=0.8",
        },
    )
    try:
        for target in selected:
            host = _host(target.url)
            wait = delay_seconds - (time.monotonic() - last_by_host[host])
            if wait > 0:
                time.sleep(wait)
            records.append(
                _probe_one(
                    target,
                    client=active_client,
                    timeout_seconds=timeout_seconds,
                    max_bytes=max_bytes,
                )
            )
            last_by_host[host] = time.monotonic()
    finally:
        if own_client:
            active_client.close()

    observed_at = datetime.now(UTC)
    observed = observed_at.date().isoformat()
    stamp = observed_at.strftime("%Y-%m-%dT%H%M%SZ")
    text_path = target_dir / f"probes-{stamp}.txt"
    lines: list[str] = [
        f"# PhilFacilities fresh source probes, {observed}",
        "# One normal unauthenticated GET per URL. No retries, no bypass.",
        f"# targets={len(selected)}",
    ]
    for record in records:
        final_url = record.final_url or record.url
        if record.status_code:
            lines.append(
                f"{record.key}\t{record.url}\t{record.status_code}\t"
                f"{record.content_type or ''}\t{final_url}\t{record.size_bytes or 0}"
            )
        else:
            lines.append(f"{record.key}\t{record.url}\tTRANSPORT_ERROR: {record.error}")
            lines.append(f"000\t\t{final_url}\t0")
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    canonical_ledger = target_dir / "probe-ledger.jsonl"
    if canonical_ledger.exists():
        previous_stamp = datetime.fromtimestamp(canonical_ledger.stat().st_mtime, UTC).strftime(
            "%Y-%m-%dT%H%M%SZ"
        )
        previous = target_dir / f"probe-ledger-prev-{previous_stamp}.jsonl"
        if not previous.exists():
            shutil.copyfile(canonical_ledger, previous)
    ledger_path = target_dir / f"probe-ledger-{stamp}.jsonl"
    rows = [json.dumps(record.as_dict(), ensure_ascii=False) + "\n" for record in records]
    for path in (ledger_path, canonical_ledger):
        path.write_text("".join(rows), encoding="utf-8")

    summary = {
        "observed_at": observed_at.isoformat(),
        "observed_date": observed,
        "targets": len(selected),
        "by_outcome": _count(records, "outcome"),
        "by_origin": _count(records, "origin"),
        "by_skip_reason": _count(records, "skip_reason", skip_none=True),
        "text_ledger": str(text_path),
        "jsonl_ledger": str(ledger_path),
        "next_retry_at": next_retry(DEFAULT_RETRY_DAYS),
    }
    (target_dir / "probe-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _count(
    records: list[ProbeRecord], attribute: str, *, skip_none: bool = False
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = getattr(record, attribute)
        if value is None and skip_none:
            continue
        label = str(value if value is not None else "none")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))
