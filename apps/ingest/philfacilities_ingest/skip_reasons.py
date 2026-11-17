"""The single machine-readable skip vocabulary.

data.md retires the ``ACCESS_BLOCKED``/manual/blocked queue. A source that cannot
be acquired automatically is recorded as ``SKIPPED`` with one reason from this
module, the exact route tried, an official alternate route and the next automatic
retry. Adapters, the CLI and reports import this vocabulary; they never copy the
list or invent a new reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

# Controlled vocabulary from data.md section 7. Do not add synonyms here.
SKIP_REASONS: tuple[str, ...] = (
    "HTTP_403",
    "HTTP_404",
    "HTTP_429",
    "HTTP_5XX",
    "WAF_CHALLENGE",
    "LOGIN_REQUIRED",
    "AGREEMENT_REQUIRED",
    "FOI_REQUIRED",
    "CAPTCHA_REQUIRED",
    "HUMAN_ACCESS_REQUIRED",
    "TLS_FAILURE",
    "DNS_FAILURE",
    "TRANSFER_FAILED",
    "EXPLICIT_RESTRICTION",
    "PRIVACY_RESTRICTION",
    "NO_PUBLIC_RELEASE",
    "UNVERIFIED_PUBLISHER",
)

SKIP_REASON_SET = frozenset(SKIP_REASONS)

DEFAULT_RETRY_DAYS = 14


@dataclass(frozen=True)
class SkipDecision:
    """Why a source is skipped and when the public route is retried."""

    reason: str
    detail: str
    alternate_route: str | None = None
    next_retry_at: str | None = None

    def __post_init__(self) -> None:
        if self.reason not in SKIP_REASON_SET:
            raise ValueError(f"Unknown skip reason {self.reason!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "skip_reason": self.reason,
            "skip_detail": self.detail,
            "alternate_route": self.alternate_route,
            "next_retry_at": self.next_retry_at,
        }


def next_retry(days: int = DEFAULT_RETRY_DAYS, *, from_date: date | None = None) -> str:
    base = from_date or datetime.now(UTC).date()
    return (base + timedelta(days=days)).isoformat()


def from_http_status(
    status_code: int | None,
    *,
    detail: str,
    alternate_route: str | None = None,
    challenge: bool = False,
    retry_days: int = DEFAULT_RETRY_DAYS,
) -> SkipDecision:
    """Map an HTTP outcome to a controlled skip reason."""

    if challenge or status_code == 403:
        reason = "WAF_CHALLENGE" if challenge else "HTTP_403"
    elif status_code == 404:
        reason = "HTTP_404"
    elif status_code == 429:
        reason = "HTTP_429"
    elif status_code is not None and 500 <= status_code <= 599:
        reason = "HTTP_5XX"
    else:
        reason = "NO_PUBLIC_RELEASE"
    return SkipDecision(
        reason=reason,
        detail=detail,
        alternate_route=alternate_route,
        next_retry_at=next_retry(retry_days),
    )


_HTTP_RE = re.compile(r"HTTP (\d{3})")


def from_error(
    error: str,
    *,
    alternate_route: str | None = None,
    retry_days: int = DEFAULT_RETRY_DAYS,
) -> SkipDecision:
    """Classify an acquisition exception without pretending it succeeded."""

    upper = error.upper()
    match = _HTTP_RE.search(upper)
    status = int(match.group(1)) if match else None
    if "CERTIFICATE" in upper or "TLS" in upper or "SSL" in upper:
        reason = "TLS_FAILURE"
    elif (
        "NAME OR SERVICE NOT KNOWN" in upper
        or "NODENAME NOR SERVNAME" in upper
        or "DNS" in upper
        or "GETADDRINFO" in upper
    ):
        reason = "DNS_FAILURE"
    elif "CAPTCHA" in upper:
        reason = "CAPTCHA_REQUIRED"
    elif "LOGIN" in upper or "AUTHENTICATION" in upper:
        reason = "LOGIN_REQUIRED"
    elif "AGREEMENT" in upper:
        reason = "AGREEMENT_REQUIRED"
    elif "FOI" in upper:
        reason = "FOI_REQUIRED"
    elif status == 403:
        reason = "HTTP_403"
    elif status == 404:
        reason = "HTTP_404"
    elif status == 429:
        reason = "HTTP_429"
    elif status is not None and 500 <= status <= 599:
        reason = "HTTP_5XX"
    elif "TIMEOUT" in upper or "TIMED OUT" in upper or "TRANSFER" in upper or "INCOMPLETE" in upper:
        reason = "TRANSFER_FAILED"
    else:
        reason = "NO_PUBLIC_RELEASE"
    return SkipDecision(
        reason=reason,
        detail=error[:1000],
        alternate_route=alternate_route,
        next_retry_at=next_retry(retry_days),
    )


def from_access_state(
    access_state: str,
    *,
    detail: str,
    alternate_route: str | None = None,
    probe_status: str | None = None,
    retry_days: int = DEFAULT_RETRY_DAYS,
) -> SkipDecision:
    """Derive the controlled reason for a candidate-register access state."""

    upper = (access_state or "").upper()
    probe = (probe_status or "").upper()
    if upper in {"FOI_REQUIRED", "FOI_ACCESS_CONFIRMED"}:
        reason = "FOI_REQUIRED"
    elif upper == "AGREEMENT_REQUIRED":
        reason = "AGREEMENT_REQUIRED"
    elif upper in {"HUMAN_DOWNLOAD_REQUIRED", "MANUAL"}:
        reason = "HUMAN_ACCESS_REQUIRED"
    elif upper in {"RESTRICTED", "EXPLICIT_RESTRICTION"}:
        reason = "EXPLICIT_RESTRICTION"
    elif "403" in probe or upper == "ACCESS_BLOCKED":
        reason = "WAF_CHALLENGE" if "WAF" in detail.upper() else "HTTP_403"
    elif "404" in probe:
        reason = "HTTP_404"
    elif "429" in probe:
        reason = "HTTP_429"
    elif "5" in probe[:2] and probe.startswith("HTTP_5"):
        reason = "HTTP_5XX"
    elif "TLS" in probe or "TLS" in detail.upper():
        reason = "TLS_FAILURE"
    elif "DNS" in probe or "DNS" in detail.upper():
        reason = "DNS_FAILURE"
    elif "TRANSPORT" in probe:
        reason = "TRANSFER_FAILED"
    elif upper == "UNVERIFIED":
        reason = "NO_PUBLIC_RELEASE"
    else:
        reason = "NO_PUBLIC_RELEASE"
    return SkipDecision(
        reason=reason,
        detail=detail[:1500],
        alternate_route=alternate_route,
        next_retry_at=next_retry(retry_days),
    )


# Registered sources that have no automatic public release route. The detail is
# kept factual: it records the observed failure and does not claim a permission
# that the publisher did not grant.
SOURCE_SKIPS: dict[str, SkipDecision] = {
    "doh-nhfr": SkipDecision(
        reason="WAF_CHALLENGE",
        detail=(
            "The official DOH NHFR export returned HTTP 403 behind a Cloudflare "
            "challenge in the recorded probes; the public list page did not expose "
            "a downloadable release. No challenge, login or agreement was bypassed."
        ),
        alternate_route=(
            "NHA GeoServer WFS layer NHA_PH:DOH HF (partial official alternate) and "
            "PhilHealth provider-category releases (accreditation evidence only)."
        ),
        next_retry_at=next_retry(),
    ),
    "deped-machine-ready": SkipDecision(
        reason="HUMAN_ACCESS_REQUIRED",
        detail=(
            "The Machine-Ready Files route requires the publisher's download/terms "
            "flow or human file selection; no unauthenticated bulk URL was verified."
        ),
        alternate_route=(
            "DepEd EBEIS public regional masterlist result sets, already acquired as "
            "separate regional releases."
        ),
        next_retry_at=next_retry(),
    ),
    "psa-psgc": SkipDecision(
        reason="HTTP_403",
        detail=(
            "The PSA PSGC workbook and page returned HTTP 403 behind Cloudflare; the "
            "classification index returned 200 but collection endpoints require a "
            "token. No bypass was attempted."
        ),
        alternate_route=(
            "BetterGov PSGC Q2 2024 classification API is ingested as a labelled "
            "official-mirror supplement, not as the current PSA release."
        ),
        next_retry_at=next_retry(),
    ),
    "tesda-tvi": SkipDecision(
        reason="WAF_CHALLENGE",
        detail=(
            "The TESDA TVI directory response was classified as an access challenge "
            "and no public provider-level bulk release was verified."
        ),
        alternate_route=(
            "TESDA Assessment Centers and regional office pages; Philippine Geoportal "
            "TVET layer remains a catalogue candidate, not an acquired release."
        ),
        next_retry_at=next_retry(),
    ),
}


def skip_for_source(key: str) -> SkipDecision | None:
    return SOURCE_SKIPS.get(key)
