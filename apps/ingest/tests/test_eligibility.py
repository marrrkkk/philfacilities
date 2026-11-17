"""Unit tests for the binding inclusion/exclusion policy."""

from __future__ import annotations

from philfacilities_ingest.contracts import FacilityCandidate, FunctionData, LocationData
from philfacilities_ingest.eligibility import exclusion_reason


def _candidate(**overrides) -> FacilityCandidate:
    values = {
        "source_record_key": "row-1",
        "row_reference": "row:1",
        "display_name": "Sample Facility",
        "facility_type": "government_office",
        "facility_subtype": "PUBLIC_SERVICE_CENTER",
        "ownership": "national_government",
        "record_status": "active_in_registry",
        "inclusion_class": "GOVERNMENT_FACILITY",
        "location": LocationData(),
    }
    values.update(overrides)
    return FacilityCandidate(**values)


def test_ordinary_commercial_and_residential_labels_are_excluded() -> None:
    cases = [
        {"facility_type": "retail", "facility_subtype": "SHOP"},
        {"facility_type": "commercial", "facility_subtype": "MALL"},
        {"facility_type": "industrial", "facility_subtype": "FACTORY"},
        {"facility_type": "agricultural_facility", "facility_subtype": "WAREHOUSE"},
        {"facility_type": "residential", "facility_subtype": "HOUSE"},
        {"facility_type": "government_office", "facility_subtype": "MALL"},
    ]
    for case in cases:
        reason = exclusion_reason(_candidate(**case))
        assert reason, case


def test_projects_and_infrastructure_assets_are_not_facility_records() -> None:
    assert exclusion_reason(_candidate(facility_kind="project"))
    assert exclusion_reason(_candidate(facility_kind="infrastructure_asset"))


def test_generic_company_record_needs_a_documented_public_role() -> None:
    candidate = _candidate(
        facility_type="other_qualifying_facility",
        facility_subtype="OTHER_QUALIFYING_FACILITY",
    )
    assert exclusion_reason(candidate)
    candidate.functions.append(FunctionData(function_code="PUBLIC_SERVICE_COUNTER"))
    assert exclusion_reason(candidate) is None


def test_mall_host_does_not_exclude_a_government_service_unit() -> None:
    candidate = _candidate(
        display_name="PRC Service Center - SM Manila",
        facility_type="government_office",
        facility_subtype="PUBLIC_SERVICE_CENTER",
        facility_kind="facility_unit",
    )
    assert exclusion_reason(candidate) is None


def test_regulated_cold_storage_is_not_rejected_as_an_ordinary_warehouse() -> None:
    candidate = _candidate(
        facility_type="agricultural_facility",
        facility_subtype="COLD_STORAGE_WAREHOUSE",
        ownership="private",
        inclusion_class="PRIVATE_PUBLIC_SERVICE_PROVIDER",
    )
    assert exclusion_reason(candidate) is None


def test_qualifying_public_and_private_facilities_are_allowed() -> None:
    assert (
        exclusion_reason(
            _candidate(
                facility_type="school",
                facility_subtype="PUBLIC_ELEMENTARY_SCHOOL",
            )
        )
        is None
    )
    assert (
        exclusion_reason(
            _candidate(
                facility_type="health_facility",
                facility_subtype="HOSPITAL",
                ownership="private",
                inclusion_class="PRIVATE_PUBLIC_SERVICE_PROVIDER",
            )
        )
        is None
    )
