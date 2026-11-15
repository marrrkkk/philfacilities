"""The candidate inventory must stay complete and internally consistent."""

from __future__ import annotations

from philfacilities_ingest.source_candidates import (
    DEFAULT_PATH,
    load_source_candidates,
    summarize_source_candidates,
    validate_source_candidates,
)


def test_source_candidate_registry_validates() -> None:
    payload = load_source_candidates(DEFAULT_PATH)
    assert validate_source_candidates(payload) == []
    summary = summarize_source_candidates(payload)
    assert summary["total"] >= 41


def test_source_candidate_ids_and_evidence_are_unique_and_conservative() -> None:
    payload = load_source_candidates(DEFAULT_PATH)
    sources = payload["sources"]
    ids = [source["source_id"] for source in sources]
    assert len(ids) == len(set(ids))
    assert "nha.wfs_health_facilities" in ids
    assert all(source["urls"] for source in sources)
    assert all(source["tracker_ids"] for source in sources)
    assert all(source["last_verified"] for source in sources)
    # A candidate cannot claim publication without a published rights state.
    for source in sources:
        if source["evidence_state"] == "PUBLISHED":
            assert source["rights_state"] == "PUBLISHED"


def test_source_candidate_validator_rejects_bad_states_and_duplicate_ids() -> None:
    payload = load_source_candidates(DEFAULT_PATH)
    broken = {
        **payload,
        "sources": [
            {
                **payload["sources"][0],
                "source_id": "duplicate.id",
                "access_state": "ANYONE_CAN_DOWNLOAD",
                "urls": ["not-a-url"],
            },
            {
                **payload["sources"][1],
                "source_id": "duplicate.id",
            },
        ],
    }
    errors = validate_source_candidates(broken)
    assert any("invalid URL" in error for error in errors)
    assert any("not an allowed state" in error for error in errors)
    assert any("duplicate source_id" in error for error in errors)
