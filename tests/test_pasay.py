"""Tests for the Pasay City health-centre directory adapter."""

from __future__ import annotations

import json

from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.pasay import (
    PasayHealthCenterAdapter,
    parse_health_cards,
)

URL = "https://pasay.gov.ph/programa/health-care/"


def _page() -> str:
    return """
    <html><body>
      <h4>Explore</h4>
      <h6>Unrelated footer heading</h6>
      <p>All Rights Reserved.</p>
      <h4>Mga Health Center ng Lungsod Pasay</h4>
      <div class="card">
        <h6>Doña Marta Health Center</h6>
        <p><strong>Super Health Center</strong></p>
        <p>Address: 37 Don Carlos Revilla St. Brgy. 147 Pasay City</p>
        <p>Tel.: 8660-7919</p>
      </div>
      <div class="card">
        <h6>Doña Marta Lying-In Clinic</h6>
        <p>Address: 37 Don Carlos Revilla St. Brgy. 147 Pasay City</p>
        <p>Tel.: 8683-0267</p>
      </div>
      <div class="card">
        <h6>Kalayaan Health Center</h6>
        <p>Address: Teacher Bliss, Barangay 201, Pasay City</p>
      </div>
      <h6>Programa ng Lungsod</h6>
      <p>Health Care</p>
    </body></html>
    """


def _spec(payload: dict) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="pasay",
        agency_name="Pasay City Government",
        dataset_slug="pasay-lgu-health-centers",
        dataset_name="Pasay City health-centre directory",
        release_label="PASAY-TEST",
        filename="pasay.json",
        content=json.dumps(payload).encode(),
    )


def _record(**overrides):
    record = {
        "record_type": "health_center",
        "name": "DOÑA MARTA HEALTH CENTER",
        "service_label": "Super Health Center",
        "address": "37 Don Carlos Revilla St. Brgy. 147 Pasay City",
        "source_url": URL,
        "page_sha256": "a" * 64,
        "fetched_at": "2026-11-16T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def test_parse_health_cards_extracts_names_labels_and_addresses() -> None:
    cards = parse_health_cards(_page(), URL)
    assert len(cards) == 3
    marta, lying_in, kalayaan = cards
    assert marta["record_type"] == "health_center"
    assert marta["name"] == "Doña Marta Health Center"
    assert marta["service_label"] == "Super Health Center"
    assert marta["address"].startswith("37 Don Carlos")
    assert marta["contact_text"] == "Tel.: 8660-7919"
    assert lying_in["record_type"] == "lying_in_clinic"
    assert kalayaan["service_label"] is None
    assert kalayaan["address"] == "Teacher Bliss, Barangay 201, Pasay City"


def test_parse_health_cards_requires_section_and_addresses() -> None:
    try:
        parse_health_cards("<html><body><h6>Health Center</h6></body></html>")
    except ValueError as exc:
        assert "section" in str(exc)
    else:  # pragma: no cover - the assertion above must fail first
        raise AssertionError("expected a section error")


def test_adapter_publishes_health_centres_and_clinic_without_contacts() -> None:
    payload = {
        "records": [
            _record(),
            _record(
                record_type="lying_in_clinic",
                name="DOÑA MARTA LYING-IN CLINIC",
                service_label=None,
            ),
        ]
    }
    spec = _spec(payload)
    adapter = PasayHealthCenterAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    assert "contact_text" not in parsed.rows[0].normalized_payload
    assert "Tel." not in json.dumps(parsed.rows[0].normalized_payload)
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 2
    centre, clinic = candidates
    assert centre.facility_type == "health_facility"
    assert centre.facility_subtype == "OTHER_HEALTH_FACILITY"
    assert clinic.facility_subtype == "CLINIC"
    assert centre.inclusion_class == "GOVERNMENT_FACILITY"
    assert centre.ownership_type == "LOCAL_GOVERNMENT"
    assert centre.operator_type == "LOCAL_GOVERNMENT"
    assert centre.public_access_class == "UNKNOWN"
    assert centre.location.precision == "unknown"
    assert centre.location.latitude is None
    assert centre.location.address_text == "37 Don Carlos Revilla St. Brgy. 147 Pasay City"
    assert centre.functions[0].function_code == "HEALTHCARE"
    assert centre.functions[0].source_value == "Super Health Center"
    assert clinic.functions[0].evidence["co_located_with"] == "Doña Marta Health Center"
    assert {role.role_type for role in centre.roles} == {"OWNER", "OPERATOR"}


def test_adapter_adds_city_to_address_when_missing() -> None:
    spec = _spec({"records": [_record(address="Leveriza St. cor. Gil Puyat Ave. Barangay 123")]})
    adapter = PasayHealthCenterAdapter(spec)
    candidates = adapter.normalize(adapter.parse(spec))
    assert candidates[0].location.address_text.endswith(", Pasay City")


def test_adapter_rejects_missing_address_duplicate_and_invalid_type() -> None:
    payload = {
        "records": [
            _record(address=""),
            _record(name="DOÑA MARTA HEALTH CENTER"),
            _record(name="OTHER PLACE", record_type="office"),
        ]
    }
    spec = _spec(payload)
    adapter = PasayHealthCenterAdapter(spec)
    validation = adapter.validate(adapter.parse(spec))
    assert validation.rejected_rows == 3
    codes = {issue.code for issue in validation.issues}
    assert codes == {"missing_address", "duplicate_source_record", "invalid_record_type"}
