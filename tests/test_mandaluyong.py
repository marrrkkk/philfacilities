"""Tests for the Mandaluyong City barangay directory adapter."""

from __future__ import annotations

import json

from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.mandaluyong import (
    MandaluyongBarangayAdapter,
    parse_barangay_table,
    parse_page_modified_time,
)

SOURCE_URL = "https://mandaluyong.gov.ph/government/barangays/"


def _page() -> str:
    return """
    <html><head>
      <meta property="article:modified_time" content="2026-02-26T06:48:01+00:00">
    </head><body>
    <table class="magic-table">
      <thead><tr>
        <th>District</th><th>Code</th><th>Barangay</th><th>Office Address</th>
        <th>Contact Numbers</th><th>ChairPerson</th><th>Image</th>
      </tr></thead>
      <tbody>
        <tr>
          <td>District 1</td><td>01</td>
          <td><a href="/government/barangays/addition-hills/">ADDITION HILLS</a></td>
          <td>123 A. Bonifacio Avenue</td>
          <td>8-123-4567</td><td>Juan Dela Cruz</td><td></td>
        </tr>
        <tr>
          <td>District 1</td><td>02</td>
          <td><a href="/government/barangays/old-zaniga/">OLD ZANIGA</a></td>
          <td>Parada Street Covered Court</td>
          <td></td><td>Maria Santos</td><td></td>
        </tr>
      </tbody>
    </table>
    </body></html>
    """


def _spec(payload: dict) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="mandaluyong",
        agency_name="City Government of Mandaluyong",
        dataset_slug="mandaluyong-lgu-barangay-directory",
        dataset_name="Mandaluyong City Barangay Directory",
        release_label="MANDALUYONG-TEST",
        filename="mandaluyong.json",
        content=json.dumps(payload).encode(),
    )


def _record(**overrides):
    record = {
        "record_type": "barangay_office",
        "name": "Addition Hills",
        "district": "District 1",
        "code": "01",
        "address": "123 A. Bonifacio Avenue, Mandaluyong City",
        "contacts": "8-123-4567",
        "chairperson": "Juan Dela Cruz",
        "detail_url": "https://mandaluyong.gov.ph/government/barangays/addition-hills/",
        "multi_use": None,
        "source_url": SOURCE_URL,
        "page_modified_time": "2026-02-26T06:48:01+00:00",
    }
    record.update(overrides)
    return record


def test_parse_page_modified_time() -> None:
    assert parse_page_modified_time(_page()) == "2026-02-26T06:48:01+00:00"
    assert parse_page_modified_time("<html><body>no timestamp</body></html>") is None


def test_parse_barangay_table_extracts_institutional_fields() -> None:
    records = parse_barangay_table(_page())
    assert len(records) == 2
    first, covered_court = records
    assert first["name"] == "ADDITION HILLS"
    assert first["code"] == "01"
    assert first["district"] == "District 1"
    assert first["address"] == "123 A. Bonifacio Avenue"
    assert first["detail_url"].endswith("/government/barangays/addition-hills/")
    assert first["multi_use"] is None
    assert covered_court["multi_use"] == "covered_court"
    assert covered_court["address"] == "Parada Street Covered Court"


def test_adapter_withholds_contacts_and_chairperson() -> None:
    payload = {"records": [_record()]}
    spec = _spec(payload)
    adapter = MandaluyongBarangayAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert "contacts" not in row.normalized_payload
    assert "chairperson" not in row.normalized_payload
    assert row.raw_payload["contacts"] == "8-123-4567"
    assert row.raw_payload["chairperson"] == "Juan Dela Cruz"

    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.facility_type == "government_office"
    assert candidate.facility_subtype == "OTHER_GOVERNMENT_OFFICE"
    assert candidate.inclusion_class == "GOVERNMENT_FACILITY"
    assert candidate.ownership_type == "LOCAL_GOVERNMENT"
    assert candidate.public_access_class == "UNKNOWN"
    assert candidate.location.address_text == "123 A. Bonifacio Avenue, Mandaluyong City"
    assert candidate.location.precision == "unknown"
    assert candidate.location.latitude is None


def test_adapter_models_covered_court_address_as_multi_use() -> None:
    payload = {
        "records": [
            _record(
                name="Old Zaniga",
                address="Parada Street Covered Court",
                multi_use="covered_court",
            )
        ]
    }
    spec = _spec(payload)
    adapter = MandaluyongBarangayAdapter(spec)
    parsed = adapter.parse(spec)
    candidates = adapter.normalize(parsed)
    assert len(candidates) == 1
    facility = candidates[0]
    assert facility.facility_type == "community_facility"
    assert facility.facility_subtype == "COVERED_COURT"
    assert {function.function_code for function in facility.functions} == {
        "GOVERNMENT_ADMINISTRATION",
        "COVERED_COURT",
    }
    assert facility.location.address_text.endswith(", Mandaluyong City")


def test_adapter_rejects_missing_address_and_duplicate_codes() -> None:
    payload = {
        "records": [
            _record(address=""),
            _record(name="Addition Hills", code="01"),
        ]
    }
    spec = _spec(payload)
    adapter = MandaluyongBarangayAdapter(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 2
    assert any(issue.code == "missing_address" for issue in validation.issues)
    assert any(issue.code == "duplicate_source_record" for issue in validation.issues)


def test_adapter_requires_barangay_code() -> None:
    payload = {"records": [_record(code="")]}
    spec = _spec(payload)
    adapter = MandaluyongBarangayAdapter(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 1
    assert any(issue.code == "missing_barangay_code" for issue in validation.issues)
