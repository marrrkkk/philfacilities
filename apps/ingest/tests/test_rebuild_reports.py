"""Rebuild-pack helpers that merge preserved LGU probe evidence."""

from __future__ import annotations

import json
from collections import Counter

from philfacilities_ingest.rebuild_reports import (
    _agency_inventory_hosts,
    _crosswalk_rows,
    _inventory_domain_index,
    _markdown_delta,
    _name_tokens,
    _preferred_domains,
    _probe_outcome_counts,
    load_lgu_probes,
)


def test_load_lgu_probes_indexes_by_psgc_and_ignores_missing_file(tmp_path):
    assert load_lgu_probes(tmp_path / "missing.json") == {}
    path = tmp_path / "lgu-domain-probes.json"
    path.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "psgc_code": "0102800000",
                        "name": "Ilocos Norte",
                        "state": "OFFICIAL_DOMAIN_PROBED",
                        "official_domain": "ilocosnorte.gov.ph",
                    },
                    {"name": "No code row"},
                ]
            }
        ),
        encoding="utf-8",
    )
    probes = load_lgu_probes(path)
    assert list(probes) == ["0102800000"]
    assert probes["0102800000"]["official_domain"] == "ilocosnorte.gov.ph"


def test_inventory_domain_index_matches_custodian_names_and_source_prefixes():
    sources = [
        {
            "source_id": "ched.heida",
            "custodian": "CHED",
            "official_urls": ["https://heida.ched.gov.ph/"],
        },
        {
            "source_id": "mrt3.stations",
            "custodian": "MRT-3 / Department of Transportation",
            "official_urls": ["https://www.mrt3.com/"],
        },
        {
            "source_id": "dotr.transport_facilities",
            "custodian": "Department of Transportation",
            "official_urls": ["https://www.dotr.gov.ph/"],
        },
    ]
    by_custodian, by_prefix = _inventory_domain_index(sources)

    # A unique source-ID prefix maps its hosts for acronym-only custodians.
    assert by_prefix["ched"] == ["heida.ched.gov.ph"]
    assert _agency_inventory_hosts(
        "Commission on Higher Education", "ched", by_custodian, by_prefix
    ) == ["heida.ched.gov.ph"]
    # Custodian token matching handles reordered names without the prefix rule.
    assert by_custodian[_name_tokens("Department of Transportation — MRT-3")] == ["mrt3.com"]
    # A custodian match wins over an ambiguous parent-department short code.
    assert _agency_inventory_hosts(
        "Department of Transportation — MRT-3", "dotr", by_custodian, by_prefix
    ) == ["mrt3.com"]


def test_inventory_domain_index_keeps_hosts_for_shared_source_prefixes():
    sources = [
        {
            "source_id": "shared.one",
            "custodian": "Alpha Agency",
            "official_urls": ["https://alpha.gov.ph/"],
        },
        {
            "source_id": "shared.two",
            "custodian": "Alpha Agency / Catalogue",
            "official_urls": ["https://catalogue.gov.ph/"],
        },
    ]
    _, by_prefix = _inventory_domain_index(sources)
    # The prefix keeps both hosts; custodian-name matching still wins when the
    # agency name matches one custodian exactly.
    assert by_prefix["shared"] == ["alpha.gov.ph", "catalogue.gov.ph"]


def test_preferred_domains_keeps_shortest_publisher_host():
    assert _preferred_domains(["negosyocenter.dti.gov.ph", "dti.gov.ph", "geoportal.gov.ph"]) == [
        "dti.gov.ph",
        "geoportal.gov.ph",
    ]
    assert _preferred_domains(["heida.ched.gov.ph"]) == ["heida.ched.gov.ph"]
    assert _preferred_domains(["bagong.pagasa.dost.gov.ph", "pagasa.dost.gov.ph"]) == [
        "pagasa.dost.gov.ph"
    ]


def test_probe_outcome_counts_deduplicates_attachments_and_prefers_ledger(tmp_path):
    payload = {
        "sources": [
            {
                "probes": [
                    {
                        "probe_key": "shared",
                        "url": "https://shared.gov.ph/",
                        "observed_at": "2026-11-17",
                        "outcome": "HTTP_200",
                    }
                ]
            },
            {
                "probes": [
                    {
                        "probe_key": "shared",
                        "url": "https://shared.gov.ph/",
                        "observed_at": "2026-11-17",
                        "outcome": "HTTP_200",
                    }
                ]
            },
        ],
        "unmatched_probes": [
            {
                "probe_key": "download",
                "url": "https://download.gov.ph/",
                "observed_at": "2026-11-17",
                "outcome": "HTTP_403",
            }
        ],
    }
    assert _probe_outcome_counts(payload) == Counter({"HTTP_200": 1, "HTTP_403": 1})

    ledger = tmp_path / "probe-ledger.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps({"url": "https://shared.gov.ph/", "outcome": "WAF_CHALLENGE"}),
                json.dumps({"url": "https://download.gov.ph/", "outcome": "HTTP_403"}),
            ]
        ),
        encoding="utf-8",
    )
    assert _probe_outcome_counts(payload, ledger) == Counter({"WAF_CHALLENGE": 1, "HTTP_403": 1})


def test_crosswalk_adds_explicit_no_key_finding_for_skipped_sources():
    rows = _crosswalk_rows(
        [],
        [
            {
                "source_id": "doh.nhfr",
                "title": "National Health Facility Registry",
                "access_state": "SKIPPED",
            },
            {
                "source_id": "dti.negosyo_centers",
                "title": "DTI Negosyo Center directory",
                "access_state": "OPEN",
            },
        ],
    )
    assert len(rows) == 1
    assert rows[0]["source_key"] == "doh.nhfr"
    assert rows[0]["key_name"] == "NO_ACQUIRED_RELEASE"
    assert rows[0]["observed_in"] == "no acquired artifact"


def test_delta_report_includes_section_8_4_metrics_and_preserves_unknown():
    baseline = {
        "captured_at": "2026-11-16T22:27:06Z",
        "facilities": 100,
        "public_facilities": 50,
        "datasets": 2,
        "releases": 3,
        "source_records": 200,
        "facility_source_links": 150,
        "current_locations": 90,
        "locations_with_coordinates": 80,
        "locations_address_only": 10,
        "match_candidates": 5,
        "attribute_fusions": 25,
        "administrative_units": 10,
        "facilities_by_type": {"school": 60},
    }
    current = {
        "captured_at": "2026-11-17T00:00:00Z",
        "facilities": 110,
        "public_facilities": 55,
        "datasets": 1,
        "releases": 2,
        "source_records": 220,
        "facility_source_links": 160,
        "current_locations": 100,
        "locations_with_coordinates": 70,
        "locations_address_only": 30,
        "match_candidates": 0,
        "attribute_fusions": 40,
        "administrative_units": 10,
    }
    metrics = {
        "facilities_by_type": {"school": 70, "health_facility": 40},
        "facilities_by_inclusion": {"GOVERNMENT_FACILITY": 50},
        "facilities_by_publication": {"public": 40},
        "facilities_by_region": {"UNKNOWN": 100},
        "locations_by_precision": {"unknown": 30, "map_geocoded": 70},
        "location_methods": [
            {"method": "openstreetmap_match", "precision": "map_geocoded", "count": 3}
        ],
        "psgc": {"current_locations": 100, "locations_with_psgc": 50},
        "preflight_run_totals": {
            "one": {
                "parsed_rows": 10,
                "accepted_rows": 9,
                "rejected_rows": 1,
                "psgc_provided": 5,
                "psgc_matched": 4,
                "duplicate_source_ids": 1,
            }
        },
        "run_totals": {
            "one": {
                "parsed_rows": 12,
                "accepted_rows": 11,
                "rejected_rows": 1,
                "psgc_provided": 10,
                "psgc_matched": 9,
                "duplicate_source_ids": 0,
            }
        },
        "match": {"created": 0, "facilities_scanned": 10},
        "fusion": {"attributes_written": 40},
        "preflight_parser_versions": {"old-1.0": 1},
        "current_parser_versions": {"new-2.0": 1},
        "current_schema_versions": {"schema-v2": 1},
        "preflight_dataset_authority": {"official": 2},
        "datasets_by_authority": {"official": 1},
        "preflight_dataset_publication": {"published": 2},
        "datasets_by_publication": {"published": 1},
        "preflight_dataset_rights": {"approved_with_attribution": 2},
        "datasets_by_rights": {"approved_with_attribution": 1},
        "added_datasets": ["new-dataset"],
        "field_matrix_rows": 3,
        "field_matrix_sources": 1,
        "schema_rows": 2,
        "inventory": {
            "baseline": {"total": 2},
            "current": {"total": 2, "OPEN": 1, "SKIPPED": 1},
            "skipped_rows": 1,
            "reconciled": 0,
        },
    }
    text = _markdown_delta(baseline, current, metrics=metrics)
    for heading in (
        "### Change summary",
        "## Coverage",
        "## Coordinate precision and method",
        "## PSGC matching",
        "## Per-source record retention",
        "## Matching and fusion",
        "## Parser and schema versions",
        "## Schema and field changes",
        "## Dataset decisions",
        "## Source inventory",
    ):
        assert heading in text
    # A breakdown with no preserved baseline must not invent a pre-rebuild count.
    assert "| `GOVERNMENT_FACILITY` | UNKNOWN | 50 | UNKNOWN |" in text
    assert "| `health_facility` | UNKNOWN | 40 | UNKNOWN |" in text
    # A preserved parser-version baseline produces a real delta.
    assert "| `old-1.0` | 1 | 0 | -1 |" in text
    assert "| `new-2.0` | UNKNOWN | 1 | UNKNOWN |" in text
    assert "| `one` | 10 | 12 | 9 | 11 | 1 | 1 |" in text
    assert "| PSGC match rate | 80.00% | 90.00% |" in text
    assert "| Duplicate source identifiers | 1 | 0 | -1 |" in text
    assert "`field-matrix.csv` records 3 source/field rows across 1 sources." in text
    assert (
        "Datasets present after the rebuild but absent from the preflight export: `new-dataset`."
        in text
    )
    assert "- Datasets present after rebuild but absent from the preflight export: 1." in text
    assert "Skipped-source rows written: 1." in text


def test_inventory_domain_index_skips_hosts_of_linked_layers():
    sources = [
        {
            "source_id": "catalogue.layers",
            "custodian": "Catalogue",
            "official_urls": ["https://catalogue.gov.ph/"],
        },
        {
            "source_id": "agency.layer",
            "custodian": "Agency",
            "official_urls": ["https://catalogue.gov.ph/", "https://agency.gov.ph/"],
            "parent_source_id": "catalogue.layers",
        },
    ]
    by_custodian, by_prefix = _inventory_domain_index(sources)
    # Only the shared catalogue host is excluded; the layer owner's own host
    # remains publisher evidence.
    assert by_custodian[_name_tokens("Agency")] == ["agency.gov.ph"]
    assert by_prefix["agency"] == ["agency.gov.ph"]
