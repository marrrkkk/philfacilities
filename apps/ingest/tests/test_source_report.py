"""data.md report generation: required fields, blocks and region coverage."""

from __future__ import annotations

import json

from philfacilities_ingest.source_report import (
    build_blocked_register,
    build_gap_report,
    build_probe_ledger,
    enrich_source_inventory,
    validate_report_fields,
)


def _payload():
    return {
        "as_of": "2026-11-16",
        "taxonomy_categories": ["HEALTH", "TRANSPORT"],
        "sources": [
            {
                "source_id": "doh.nhfr",
                "custodian": "Department of Health",
                "title": "National Health Facility Registry",
                "category": "HEALTH",
                "urls": ["https://nhfr.doh.gov.ph/"],
                "evidence_state": "DISCOVERY_ONLY",
                "access_state": "ACCESS_BLOCKED",
                "rights_state": "UNKNOWN",
                "coverage_scope": "NATIONAL_OFFICIAL_INVENTORY",
                "priority": "P0",
                "next_action": "Find an official alternate route.",
                "tracker_ids": ["AF1-1"],
                "last_verified": "2026-11-16",
                "provenance": {"register": True, "candidates": False, "probe": True},
                "probes": [
                    {
                        "probe_key": "doh",
                        "observed_at": "2026-11-16",
                        "url": "https://nhfr.doh.gov.ph/",
                        "http_status": 403,
                        "content_type": "text/html",
                        "final_url": "https://nhfr.doh.gov.ph/",
                        "size_bytes": 123,
                        "error": None,
                        "outcome": "HTTP_403",
                    }
                ],
            },
            {
                "source_id": "lrta.stations",
                "custodian": "Light Rail Transit Authority",
                "title": "LRTA station distance table",
                "category": "TRANSPORT",
                "urls": ["https://lrta.gov.ph/"],
                "evidence_state": "DIRECTORY_CONTENT_VERIFIED",
                "access_state": "OPEN",
                "rights_state": "REVIEW_REQUIRED",
                "coverage_scope": "DIRECTORY_SUBSET",
                "priority": "P1",
                "next_action": "Parse the public distance table.",
                "tracker_ids": [],
                "last_verified": "2026-11-16",
                "provenance": {"register": False, "candidates": True, "probe": False},
                "probes": [],
            },
        ],
        "unmatched_probes": [
            {
                "probe_key": "unknown",
                "observed_at": "2026-11-16",
                "url": "https://example.gov.ph/",
                "http_status": None,
                "outcome": "TRANSPORT_ERROR",
            }
        ],
    }


def test_enrichment_adds_every_required_field():
    payload = enrich_source_inventory(_payload())
    assert validate_report_fields(payload) == []
    for source in payload["sources"]:
        assert source["official_urls"]
        assert isinstance(source["data_fields_observed"], list)
    assert payload["sources"][0]["probe_date"] == "2026-11-16"
    assert payload["sources"][1]["probe_date"] is None


def test_probe_ledger_keeps_blocks_and_unmatched():
    ledger = build_probe_ledger(enrich_source_inventory(_payload()))
    assert len(ledger) == 2
    assert {entry["outcome"] for entry in ledger} == {"HTTP_403", "TRANSPORT_ERROR"}
    assert next(entry for entry in ledger if entry["probe_key"] == "unknown")["source_id"] is None


def test_blocked_register_names_official_alternate():
    payload = enrich_source_inventory(_payload())
    text = build_blocked_register(payload)
    assert "doh.nhfr" in text
    assert "NHA GeoServer" in text
    assert "Cloudflare" in text


def test_gap_report_covers_all_regions_and_categories():
    payload = enrich_source_inventory(_payload())
    region_ledger = {
        "searches": [
            {
                "region_psgc": "1300000000",
                "url": "https://quezoncity.gov.ph/",
                "http_status": 200,
                "outcome": "HTTP_200",
            }
        ]
    }
    text = build_gap_report(payload, region_ledger)
    assert "Category by region matrix" in text
    assert "HEALTH" in text and "TRANSPORT" in text
    for short in ("NCR", "CAR", "BARMM", "NIR"):
        assert short in text
    assert "Remaining unknowns" in text


def test_report_fields_reject_invented_count():
    payload = enrich_source_inventory(_payload())
    payload["sources"][0]["record_count_observed"] = "many"
    errors = validate_report_fields(payload)
    assert any("record_count_observed" in error for error in errors)


def test_json_serialisable_probe_ledger():
    ledger = build_probe_ledger(enrich_source_inventory(_payload()))
    json.dumps(ledger)
