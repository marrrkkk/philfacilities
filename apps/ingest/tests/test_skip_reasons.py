"""The controlled skip vocabulary and automatic classifications."""

from __future__ import annotations

import pytest
from philfacilities_ingest.skip_reasons import (
    SKIP_REASON_SET,
    SKIP_REASONS,
    SOURCE_SKIPS,
    SkipDecision,
    from_access_state,
    from_error,
    from_http_status,
    skip_for_source,
)


def test_vocabulary_is_the_data_md_list_once():
    assert SKIP_REASONS == (
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
    assert frozenset(SKIP_REASONS) == SKIP_REASON_SET


def test_unknown_skip_reason_is_rejected():
    with pytest.raises(ValueError):
        SkipDecision(reason="BLOCKED", detail="legacy state")


@pytest.mark.parametrize(
    ("status", "challenge", "expected"),
    [
        (403, False, "HTTP_403"),
        (403, True, "WAF_CHALLENGE"),
        (404, False, "HTTP_404"),
        (429, False, "HTTP_429"),
        (503, False, "HTTP_5XX"),
    ],
)
def test_http_status_mapping(status, challenge, expected):
    decision = from_http_status(status, detail="probe", challenge=challenge)
    assert decision.reason == expected
    assert decision.next_retry_at


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("SSL: CERTIFICATE_VERIFY_FAILED", "TLS_FAILURE"),
        ("getaddrinfo failed", "DNS_FAILURE"),
        ("CAPTCHA challenge", "CAPTCHA_REQUIRED"),
        ("login required", "LOGIN_REQUIRED"),
        ("agreement required", "AGREEMENT_REQUIRED"),
        ("FOI request only", "FOI_REQUIRED"),
        ("GET https://example.gov.ph returned HTTP 403", "HTTP_403"),
        ("read timed out", "TRANSFER_FAILED"),
    ],
)
def test_error_classification(error, expected):
    assert from_error(error).reason == expected


def test_access_states_never_return_blocked():
    assert from_access_state("FOI_REQUIRED", detail="").reason == "FOI_REQUIRED"
    assert from_access_state("ACCESS_BLOCKED", detail="WAF").reason == "WAF_CHALLENGE"
    assert from_access_state("HUMAN_DOWNLOAD_REQUIRED", detail="").reason == (
        "HUMAN_ACCESS_REQUIRED"
    )
    assert from_access_state("UNVERIFIED", detail="").reason == "NO_PUBLIC_RELEASE"


def test_every_registered_skip_has_a_valid_reason_and_alternate_route():
    assert set(SOURCE_SKIPS) == {
        "deped-machine-ready",
        "psa-psgc",
        "tesda-tvi",
    }
    for key, decision in SOURCE_SKIPS.items():
        assert decision.reason in SKIP_REASON_SET, key
        assert decision.detail, key
        assert decision.alternate_route, key
        assert decision.next_retry_at, key
        assert skip_for_source(key) is decision
