"""The merged source inventory must preserve register, candidate and probe evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from philfacilities_ingest.source_inventory import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_PROBES_PATH,
    DEFAULT_REGISTER_PATH,
    TAXONOMY_CATEGORIES,
    build_source_inventory,
    parse_probes,
    parse_register,
    summarize_source_inventory,
    validate_source_inventory,
    write_source_inventory,
)

REGISTER = "\n".join(
    [
        "# Test register",
        "",
        "**Research baseline:** 16 November 2026",
        "",
        "# A. Primary facility registries",
        "",
        "| Source ID / custodian | Resource | Coverage | Evidence / access | Priority |",
        "|---|---|---|---|---|",
        "| `alpha.registry` — Alpha Agency | [Alpha](https://alpha.gov.ph/data) "
        "| National. | `DIRECTORY CONTENT VERIFIED`. HTTP 200. "
        "| **P0.** Acquire. |",
        "| `beta.blocked` — Beta Agency | [Beta](https://beta.gov.ph/) "
        "| Unknown. | `DISCOVERED`. HTTP 403. `ACCESS_BLOCKED`. "
        "| **P1.** Request access. |",
        "| `epsilon.internal` — Epsilon Agency | [Release](https://epsilon.gov.ph/release) "
        "| Directory subset. | `ACQUIRED AND PUBLISHED AS AN INTERNAL CANONICAL SET`. "
        "| **P2.** Resolve ownership. |",
        "",
    ]
)

PROBES = "\n".join(
    [
        "alpha\thttps://alpha.gov.ph/data\t200\ttext/html\thttps://alpha.gov.ph/data\t1234",
        "beta\thttps://beta.gov.ph/\t403\ttext/html\thttps://beta.gov.ph/\t5522",
        "gamma\thttps://gamma.gov.ph/\tcurl: (6) Could not resolve host: gamma.gov.ph",
        "000\t\thttps://gamma.gov.ph/\t0",
        "delta\thttps://delta.gov.ph/\tcurl: (35) TLS connect error: "
        "error:0A000126:SSL routines::unexpected eof while reading",
        "000\t\thttps://delta.gov.ph/\t0",
        "",
    ]
)


def _candidate_payload() -> dict:
    return {
        "version": 1,
        "as_of": "2026-11-16",
        "allowed_states": {
            "evidence": [
                "DISCOVERED",
                "DIRECTORY_CONTENT_VERIFIED",
                "FILE_DOCUMENT_VERIFIED",
                "ACQUIRED",
                "PUBLISHED",
            ],
            "access": [
                "OPEN",
                "HUMAN_DOWNLOAD_REQUIRED",
                "FOI_REQUIRED",
                "ACCESS_BLOCKED",
                "UNVERIFIED",
                "PUBLISHED",
            ],
            "rights": ["UNKNOWN", "REVIEW_REQUIRED", "PUBLICLY_AVAILABLE_VERIFIED", "PUBLISHED"],
            "coverage": [
                "NATIONAL_PARTIAL",
                "DIRECTORY_SUBSET",
                "UNKNOWN_COVERAGE",
                "SINGLE_LGU",
            ],
        },
        "sources": [
            {
                "source_id": "alpha.registry",
                "custodian": "Alpha Agency",
                "title": "Alpha facility registry",
                "urls": ["https://alpha.gov.ph/data"],
                "evidence_state": "FILE_DOCUMENT_VERIFIED",
                "access_state": "HUMAN_DOWNLOAD_REQUIRED",
                "rights_state": "REVIEW_REQUIRED",
                "coverage_scope": "NATIONAL_PARTIAL",
                "priority": "P0/P1",
                "next_action": "Download the official file.",
                "tracker_ids": ["AF1-01"],
                "last_verified": "2026-11-16",
            },
            {
                "source_id": "gamma.only",
                "custodian": "Gamma Agency",
                "title": "Gamma source",
                "urls": ["https://gamma.gov.ph/"],
                "evidence_state": "DISCOVERED",
                "access_state": "UNVERIFIED",
                "rights_state": "UNKNOWN",
                "coverage_scope": "UNKNOWN_COVERAGE",
                "priority": "P2",
                "next_action": "Probe the official page.",
                "tracker_ids": [],
                "last_verified": "2026-11-16",
            },
        ],
    }


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    register = tmp_path / "register.md"
    register.write_text(REGISTER, encoding="utf-8")
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps(_candidate_payload()), encoding="utf-8")
    probes = tmp_path / "probes-2026-11-16.txt"
    probes.write_text(PROBES, encoding="utf-8")
    return register, candidates, probes


def test_parse_register_reads_sections_ids_links_and_dates() -> None:
    rows, baseline = parse_register(DEFAULT_REGISTER_PATH)
    assert baseline == "2026-11-15"
    assert len(rows) >= 80
    by_id = {row.source_id: row for row in rows}
    assert by_id["deped.school_masterlist"].section.startswith("A.")
    assert by_id["deped.school_masterlist"].custodian == "DepEd"
    assert any("deped.gov.ph" in url for url in by_id["deped.school_masterlist"].urls)
    assert by_id["dilg.subaybayan_lime20"].urls
    assert all(row.urls for row in rows)


def test_parse_probes_handles_single_line_and_multiline_failures() -> None:
    probes = parse_probes(DEFAULT_PROBES_PATH)
    assert len(probes) == 35
    by_key = {probe.probe_key: probe for probe in probes}
    assert by_key["marina"].status_code == 200
    assert by_key["caap"].status_code == 403
    assert by_key["pais"].status_code == 0
    assert by_key["pais"].error and "TLS" in by_key["pais"].error
    assert by_key["judiciary"].status_code == 0


def test_build_inventory_merges_candidate_states_and_attaches_probes(tmp_path: Path) -> None:
    register, candidates, probes = _write_fixtures(tmp_path)
    payload = build_source_inventory(register, candidates, probes)
    assert validate_source_inventory(payload) == []
    by_id = {source["source_id"]: source for source in payload["sources"]}

    alpha = by_id["alpha.registry"]
    assert alpha["evidence_state"] == "FILE_DOCUMENT_VERIFIED"
    assert alpha["access_state"] == "HUMAN_DOWNLOAD_REQUIRED"
    assert alpha["priority"] == "P0"
    assert alpha["provenance"] == {"register": True, "candidates": True, "probe": True}
    assert alpha["observed_access_state"] == "OPEN"
    assert alpha["probes"][0]["outcome"] == "HTTP_200"

    beta = by_id["beta.blocked"]
    assert beta["access_state"] == "ACCESS_BLOCKED"
    assert beta["observed_access_state"] == "ACCESS_BLOCKED"

    gamma = by_id["gamma.only"]
    assert gamma["provenance"] == {"register": False, "candidates": True, "probe": True}
    assert gamma["observed_access_state"] == "ACCESS_BLOCKED"
    assert gamma["probes"][0]["outcome"] == "TRANSPORT_ERROR"

    epsilon = by_id["epsilon.internal"]
    assert epsilon["publication_state"] == "INTERNAL_ONLY"

    assert [probe["probe_key"] for probe in payload["unmatched_probes"]] == ["delta"]
    summary = summarize_source_inventory(payload)
    assert summary["total"] == 4
    assert summary["probed"] == 3
    assert summary["unmatched_probes"] == 1


def test_validator_rejects_duplicates_bad_categories_and_states(tmp_path: Path) -> None:
    payload = build_source_inventory(*_write_fixtures(tmp_path))
    broken = json.loads(json.dumps(payload))
    broken["sources"][0]["category"] = "NOT_A_CATEGORY"
    broken["sources"][0]["access_state"] = "ANYONE_CAN_DOWNLOAD"
    broken["sources"].append(json.loads(json.dumps(broken["sources"][1])))

    errors = validate_source_inventory(broken)
    assert any("is not in the taxonomy" in error for error in errors)
    assert any("is not an allowed state" in error for error in errors)
    assert any("duplicate source_id" in error for error in errors)


def test_write_inventory_round_trips_json_and_csv(tmp_path: Path) -> None:
    register, candidates, probes = _write_fixtures(tmp_path)
    payload = build_source_inventory(register, candidates, probes)
    json_path = tmp_path / "inventory.json"
    csv_path = tmp_path / "inventory.csv"
    written_json, written_csv = write_source_inventory(payload, json_path, csv_path)
    assert written_json == json_path and written_csv == csv_path

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["sources"] == payload["sources"]
    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(payload["sources"])
    assert {row["source_id"] for row in rows} == {
        source["source_id"] for source in payload["sources"]
    }
    alpha = next(row for row in rows if row["source_id"] == "alpha.registry")
    assert alpha["probe_outcomes"] == "alpha=HTTP_200"


def test_real_inventory_covers_register_candidates_and_probe_ledger() -> None:
    payload = build_source_inventory(
        DEFAULT_REGISTER_PATH, DEFAULT_CANDIDATES_PATH, DEFAULT_PROBES_PATH
    )
    assert validate_source_inventory(payload) == []
    summary = summarize_source_inventory(payload)
    assert summary["total"] >= 80
    assert summary["from_register"] >= 80
    assert summary["from_candidates"] >= 42
    assert summary["probed"] >= 20
    assert summary["unmatched_probes"] == 0
    assert summary["by_access_state"]["ACCESS_BLOCKED"] >= 25

    ids = {source["source_id"] for source in payload["sources"]}
    assert {"deped.school_masterlist", "doh.nhfr", "lgu.pasay_health_centers"} <= ids
    assert {"lrta.stations", "marina.ports", "dswd.standards_directories"} <= ids
    for source in payload["sources"]:
        assert source["category"] in TAXONOMY_CATEGORIES
        assert source["urls"]
        assert source["last_verified"] >= "2026-11-15"
    for source in payload["sources"]:
        if source["publication_state"] == "PUBLISHED":
            assert source["rights_state"] in {"PUBLISHED", "PUBLICLY_AVAILABLE_VERIFIED"}
