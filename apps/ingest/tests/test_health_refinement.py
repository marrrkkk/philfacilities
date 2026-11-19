"""Health subtype and ownership refinement evidence."""

from __future__ import annotations

from philfacilities_ingest.health_refinement import (
    CANONICAL_HEALTH_SUBTYPES,
    classify_health_subtype,
)
from philfacilities_ingest.identity import subtypes_compatible


def test_canonical_subtypes_pass_through() -> None:
    for subtype in CANONICAL_HEALTH_SUBTYPES:
        known, target = classify_health_subtype(subtype)
        assert known is True
        assert target == subtype


def test_lowercase_and_underscore_labels_are_mapped() -> None:
    assert classify_health_subtype("pharmacy") == (True, "PHARMACY")
    assert classify_health_subtype("Clinical Laboratory") == (True, "LABORATORY")
    assert classify_health_subtype("Barangay_Health_Station") == (
        True,
        "BARANGAY_HEALTH_STATION",
    )
    assert classify_health_subtype("Yakap Clinics") == (True, "CLINIC")


def test_accreditation_and_profession_labels_are_cleared() -> None:
    for label in ("Postpartum", "GAMOT Package Providers", "LEVEL 1", "yes", "dentist"):
        assert classify_health_subtype(label) == (True, None)


def test_ambiguous_source_labels_are_cleared_without_guessing() -> None:
    assert classify_health_subtype("INF/DISP") == (True, None)
    assert classify_health_subtype("centre") == (True, None)


def test_building_and_service_labels_are_cleared() -> None:
    for label in (
        "school",
        "university",
        "vaccination_centre",
        "office_and_rescue",
        "LOCAL_GOVERNMENT_OFFICE",
    ):
        assert classify_health_subtype(label) == (True, None)


def test_infirmary_is_a_canonical_health_subtype() -> None:
    assert "INFIRMARY" in CANONICAL_HEALTH_SUBTYPES


def test_explicit_primary_care_and_specialty_labels_are_mapped() -> None:
    assert classify_health_subtype("Community Health Center") == (True, "CLINIC")
    assert classify_health_subtype("Primary_Health_Care_Center") == (True, "CLINIC")
    assert classify_health_subtype("Puericulture Centre") == (True, "CLINIC")
    assert classify_health_subtype(
        "Otorhinolaryngology-Head and Neck Surgery Specialty Clinic"
    ) == (True, "CLINIC")
    assert classify_health_subtype("Drug Abuse Treatment and Rehab Centers") == (
        True,
        "OTHER_HEALTH_FACILITY",
    )
    assert classify_health_subtype("Hospice") == (True, "OTHER_HEALTH_FACILITY")


def test_unrecognised_label_is_not_silently_cleared() -> None:
    assert classify_health_subtype("Some New Facility Class") == (False, None)


def test_nhfr_facility_classes_are_mapped() -> None:
    assert classify_health_subtype("Dialysis Clinic") == (True, "DIALYSIS_CENTER")
    assert classify_health_subtype("Dental Laboratory") == (True, "LABORATORY")
    assert classify_health_subtype("Medical Outpatient Clinic") == (True, "CLINIC")
    assert classify_health_subtype("Blood Service Facility") == (
        True,
        "OTHER_HEALTH_FACILITY",
    )
    assert classify_health_subtype("Bagong Urgent Care and Ambulatory Service") == (
        True,
        "CLINIC",
    )


def test_empty_and_unknown_values_are_empty() -> None:
    assert classify_health_subtype(None) == (True, None)
    assert classify_health_subtype("  ") == (True, None)


def test_health_subtype_families_allow_agency_level_differences() -> None:
    assert subtypes_compatible("health_facility", "CLINIC", "RURAL_HEALTH_UNIT")
    assert subtypes_compatible("health_facility", "CLINIC", "BARANGAY_HEALTH_STATION")
    assert not subtypes_compatible("health_facility", "HOSPITAL", "CLINIC")
    assert not subtypes_compatible("health_facility", "LABORATORY", "CLINIC")
    assert not subtypes_compatible("health_facility", "PHARMACY", "CLINIC")
