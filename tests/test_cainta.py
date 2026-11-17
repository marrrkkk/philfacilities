"""Tests for the Cainta municipal health-centre directory adapter."""

from __future__ import annotations

import json

from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.cainta import (
    CaintaHealthCenterAdapter,
    parse_claimed_total,
    parse_rhu_page,
)

RHU_URL = "https://www.cainta.gov.ph/rhu1"


def _rhu_page() -> str:
    return """
    <html><body>
      <nav>Home Departments Health and Health Centers</nav>
      <h2>RHU 1 - BRGY. SAN ANDRES</h2>
      <p>PFCI HEALTH CENTER (RHU)</p>
      <p>Address: Sampaguita St., PFCI, Brgy. San Andres</p>
      <p>KABISIG HEALTH CENTER (BHS)</p>
      <p>Address: Blk. 17 Kabisig, Brgy. San Andres</p>
      <p>ONE CAINTA SATELLITE HEALTH STATION GREENWOODS</p>
      <p>Address: 6 Sherwood St., Greenwoods, Brgy. San Andres</p>
      <p>BACK</p>
    </body></html>
    """


def _landing_page() -> str:
    return """
    <html><body>
      <p>There are a total of 28 Health Centers in all of the seven (7) Barangays
      in Cainta.</p>
    </body></html>
    """


def _spec(payload: dict) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="cainta",
        agency_name="Municipality of Cainta",
        dataset_slug="cainta-lgu-health-centers",
        dataset_name="Cainta municipal health-centre directory",
        release_label="CAINTA-TEST",
        filename="cainta.json",
        content=json.dumps(payload).encode(),
    )


def _record(**overrides):
    record = {
        "record_type": "health_center",
        "name": "PFCI HEALTH CENTER",
        "level": "RHU",
        "address": "Sampaguita St., PFCI, Brgy. San Andres",
        "rhu_number": 1,
        "rhu_barangay": "SAN ANDRES",
        "source_url": RHU_URL,
        "page_sha256": "a" * 64,
        "fetched_at": "2026-11-16T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def test_parse_claimed_total() -> None:
    assert parse_claimed_total(_landing_page()) == 28
    assert parse_claimed_total("<html><body>No count here.</body></html>") is None


def test_parse_rhu_page_extracts_labelled_and_unlabelled_entries() -> None:
    parsed = parse_rhu_page(_rhu_page(), RHU_URL, 1)
    assert parsed["heading"] == "RHU 1 - BRGY. SAN ANDRES"
    assert parsed["barangay"] == "SAN ANDRES"
    assert len(parsed["entries"]) == 3
    pfci, kabisig, satellite = parsed["entries"]
    assert pfci["name"] == "PFCI HEALTH CENTER"
    assert pfci["level"] == "RHU"
    assert pfci["address"].startswith("Sampaguita")
    assert kabisig["level"] == "BHS"
    assert satellite["level"] is None
    assert satellite["name"].startswith("ONE CAINTA SATELLITE")


def test_adapter_publishes_labelled_records_and_withholds_contacts() -> None:
    payload = {"records": [_record(), _record(name="KABISIG HEALTH CENTER", level="BHS")]}
    spec = _spec(payload)
    adapter = CaintaHealthCenterAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    assert "phone" not in parsed.rows[0].normalized_payload
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 2
    ruh, bhs = candidates
    assert ruh.facility_type == "health_facility"
    assert ruh.facility_subtype == "RURAL_HEALTH_UNIT"
    assert bhs.facility_subtype == "BARANGAY_HEALTH_STATION"
    assert ruh.inclusion_class == "GOVERNMENT_FACILITY"
    assert ruh.ownership_type == "LOCAL_GOVERNMENT"
    assert ruh.public_access_class == "UNKNOWN"
    assert ruh.location.precision == "unknown"
    assert ruh.location.latitude is None
    assert ruh.location.address_text.endswith(", Cainta, Rizal")
    assert ruh.functions[0].function_code == "HEALTHCARE"


def test_adapter_rejects_missing_address_duplicate_and_invalid_level() -> None:
    payload = {
        "records": [
            _record(address=""),
            _record(name="PFCI HEALTH CENTER"),
            _record(name="OTHER CENTER", level="CLINIC"),
        ]
    }
    spec = _spec(payload)
    adapter = CaintaHealthCenterAdapter(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 3
    codes = {issue.code for issue in validation.issues}
    assert codes == {"missing_address", "duplicate_source_record", "invalid_health_centre_level"}
