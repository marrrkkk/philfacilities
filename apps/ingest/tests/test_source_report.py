"""data.md report generation: required fields, blocks and region coverage."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace

from philfacilities_ingest.source_inventory import (
    CSV_FIELDS,
    REQUIRED_OUTPUT_FIELDS,
    _apply_source_links,
    _merge_alias_row,
    summarize_source_inventory,
    write_source_inventory,
)
from philfacilities_ingest.source_report import (
    attach_published_release_evidence,
    build_acquisition_queue,
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


def test_enrichment_retires_legacy_access_states():
    payload = enrich_source_inventory(_payload())
    blocked, open_source = payload["sources"]
    assert blocked["access_state"] == "SKIPPED"
    assert blocked["access_state_raw"] == "ACCESS_BLOCKED"
    assert blocked["skip_reason"] in {"HTTP_403", "WAF_CHALLENGE"}
    assert blocked["alternate_route"]
    assert blocked["next_retry_at"]
    assert blocked["rights_state"] == "unknown"
    assert blocked["publication_state"] == "internal_only"
    assert open_source["access_state"] == "OPEN"
    assert open_source["access_state_raw"] == "OPEN"
    assert open_source["rights_state"] == "review_required"
    assert validate_report_fields(payload) == []


def test_published_raw_rights_maps_to_publicly_available_verified():
    payload = _payload()
    source = payload["sources"][1]
    source["rights_state"] = "PUBLISHED"
    payload = enrich_source_inventory(payload)
    enriched = payload["sources"][1]
    assert enriched["access_state"] == "OPEN"
    assert enriched["rights_state_raw"] == "PUBLISHED"
    assert enriched["rights_state"] == "publicly_available_verified"
    assert enriched["publication_state"] == "published"
    assert validate_report_fields(payload) == []


def test_published_release_evidence_supersedes_stale_register_skip():
    payload = _payload()
    blocked = payload["sources"][0]
    blocked["published_release_count"] = 2
    blocked["published_dataset_slugs"] = ["doh-nhfr"]
    blocked["published_release_labels"] = ["NHFR-2026-11-17"]
    blocked["published_rights_states"] = ["approved_with_attribution"]
    payload = enrich_source_inventory(payload)

    source = payload["sources"][0]
    assert source["access_state"] == "OPEN"
    assert source["publication_state"] == "published"
    assert source["rights_state"] == "approved_with_attribution"
    assert source["skip_reason"] is None
    assert source["skip_detail"] is None
    assert source["register_access_state"] == "ACCESS_BLOCKED"
    assert source["register_skip_reason"] in {"HTTP_403", "WAF_CHALLENGE"}
    assert source["publication_evidence"] == "published_release_exact_source_url"
    assert validate_report_fields(payload) == []

    # Enrichment runs more than once in report generation. It must stay stable
    # and must not overwrite the preserved register decision.
    enrich_source_inventory(payload)
    assert source["access_state"] == "OPEN"
    assert source["register_access_state"] == "ACCESS_BLOCKED"
    assert source["register_skip_reason"] in {"HTTP_403", "WAF_CHALLENGE"}


def test_release_evidence_matches_primary_and_unique_alternate_urls():
    class _Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class _Session:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, _statement):
            return _Result(self.rows)

    def published(url, slug, label="REL-1", rights="approved_with_attribution"):
        return (
            SimpleNamespace(source_release_label=label, retrieved_at=None),
            SimpleNamespace(
                slug=slug,
                source_url=url,
                publication_status="published",
                redistribution_status=rights,
            ),
            SimpleNamespace(short_code="agency"),
        )

    payload = {
        "sources": [
            {
                "source_id": "primary",
                "official_urls": ["https://one.gov.ph/releases"],
                "urls": ["https://one.gov.ph/releases"],
            },
            {
                "source_id": "alternate",
                "official_urls": ["https://two.gov.ph/", "https://two.gov.ph/list"],
                "urls": ["https://two.gov.ph/", "https://two.gov.ph/list"],
            },
            {
                "source_id": "claimed-alternate",
                "official_urls": ["https://three.gov.ph/", "https://one.gov.ph/releases"],
                "urls": ["https://three.gov.ph/", "https://one.gov.ph/releases"],
            },
        ]
    }
    annotated = attach_published_release_evidence(
        payload,
        _Session(
            [
                published("https://one.gov.ph/releases", "one-dataset"),
                published("https://two.gov.ph/list", "two-dataset"),
            ]
        ),
    )

    assert annotated == ["primary", "alternate"]
    assert payload["sources"][0]["published_dataset_slugs"] == ["one-dataset"]
    assert payload["sources"][1]["published_dataset_slugs"] == ["two-dataset"]
    assert "published_release_count" not in payload["sources"][2]


def test_summary_counts_enriched_lowercase_publication_states():
    payload = _payload()
    payload["sources"][1]["rights_state"] = "PUBLISHED"
    payload = enrich_source_inventory(payload)
    summary = summarize_source_inventory(payload)
    assert summary["published"] == 1
    assert summary["internal_only"] == 1


def test_validator_rejects_uncontrolled_states():
    payload = enrich_source_inventory(_payload())
    payload["sources"][0]["access_state"] = "ACCESS_BLOCKED"
    payload["sources"][1]["rights_state"] = "REVIEW_REQUIRED"
    errors = validate_report_fields(payload)
    assert any("access_state must be OPEN or SKIPPED" in error for error in errors)
    assert any("rights_state is not a controlled value" in error for error in errors)


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


def test_gap_report_counts_normalized_publication_states():
    payload = _payload()
    payload["sources"][1]["rights_state"] = "PUBLISHED"
    payload = enrich_source_inventory(payload)
    text = build_gap_report(payload)
    health = text.split("### HEALTH", 1)[1].split("###", 1)[0]
    transport = text.split("### TRANSPORT", 1)[1]
    assert "recorded publication or internal-only release: **1**" in health
    assert "recorded publication or internal-only release: **1**" in transport


def test_acquisition_queue_excludes_normalized_published_sources():
    payload = _payload()
    payload["sources"][1]["rights_state"] = "PUBLISHED"
    payload = enrich_source_inventory(payload)
    text = build_acquisition_queue(payload)
    assert "lrta.stations" not in text
    assert "doh.nhfr" in text


def test_report_fields_reject_invented_count():
    payload = enrich_source_inventory(_payload())
    payload["sources"][0]["record_count_observed"] = "many"
    errors = validate_report_fields(payload)
    assert any("record_count_observed" in error for error in errors)


def test_json_serialisable_probe_ledger():
    ledger = build_probe_ledger(enrich_source_inventory(_payload()))
    json.dumps(ledger)


def test_csv_fields_keep_the_25_field_core_schema_without_duplicates():
    assert tuple(REQUIRED_OUTPUT_FIELDS) == (
        "source_id",
        "custodian",
        "agency_level",
        "category",
        "title",
        "description",
        "official_urls",
        "alternate_urls",
        "access_method",
        "format",
        "coverage_scope",
        "geographic_scope",
        "evidence_state",
        "access_state",
        "rights_state",
        "publication_state",
        "probe_status",
        "probe_date",
        "probe_notes",
        "data_fields_observed",
        "record_count_observed",
        "ownership_semantics",
        "tracker_ids",
        "next_action",
        "notes",
    )
    assert len(CSV_FIELDS) == len(set(CSV_FIELDS))


def test_inventory_csv_emits_each_core_field_once(tmp_path):
    payload = enrich_source_inventory(_payload())
    _json_path, csv_path = write_source_inventory(
        payload,
        tmp_path / "source-inventory.json",
        tmp_path / "source-inventory.csv",
    )
    with csv_path.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    for field in REQUIRED_OUTPUT_FIELDS:
        assert header.count(field) == 1
    assert "alias_source_ids" in header
    assert len(header) == len(set(header))


def test_duplicate_portal_alias_merges_urls_and_keeps_alias_id():
    canonical = {
        "source_id": "dpwh.infrastructure_projects",
        "title": "DPWH infrastructure and public-building project records",
        "urls": ["https://transparency.dpwh.gov.ph/", "https://www.dpwh.gov.ph/"],
        "evidence_state": "OFFICIAL_PORTAL_VERIFIED",
        "tracker_ids": ["P1"],
    }
    alias = {
        "source_id": "dpwh.transparency_projects",
        "title": "DPWH Transparency Portal",
        "urls": ["https://transparency.dpwh.gov.ph/"],
        "evidence_state": "DISCOVERED",
        "tracker_ids": ["P2"],
    }
    _merge_alias_row(canonical, alias, alias["source_id"])
    assert canonical["alias_source_ids"] == ["dpwh.transparency_projects"]
    assert canonical["urls"] == [
        "https://transparency.dpwh.gov.ph/",
        "https://www.dpwh.gov.ph/",
    ]
    # The canonical row keeps its richer evidence and title.
    assert canonical["evidence_state"] == "OFFICIAL_PORTAL_VERIFIED"
    assert canonical["title"].startswith("DPWH infrastructure")
    assert canonical["tracker_ids"] == ["P1", "P2"]


def test_shared_portal_source_links_to_parent_catalogue():
    sources = [
        {"source_id": "geoportal.facility_layers", "urls": ["https://geoportal.gov.ph/"]},
        {
            "source_id": "dti.shared_service_facilities",
            "urls": ["https://geoportal.gov.ph/", "https://www.dti.gov.ph/"],
        },
    ]
    _apply_source_links(sources)
    assert sources[0].get("parent_source_id") is None
    assert sources[1]["parent_source_id"] == "geoportal.facility_layers"
    # The owner's site becomes the canonical URL, so primary URLs stay unique.
    assert sources[1]["urls"][0] == "https://www.dti.gov.ph/"
    assert sources[0]["urls"][0] == "https://geoportal.gov.ph/"
