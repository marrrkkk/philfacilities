"""Pure name and address evidence used by general facility aggregation."""

from __future__ import annotations

from philfacilities_ingest.identity import (
    address_overlap,
    facility_name_key,
    name_similarity,
    psgc_barangay_code,
    psgc_city_code,
    school_name_key,
    subtype_family,
    subtypes_compatible,
)


def test_school_name_key_expands_uppercase_type_abbreviations():
    assert school_name_key("Awag IS") == school_name_key("Awag Integrated School")
    assert school_name_key("Bunga ES") == "bunga elementary school"
    assert school_name_key("Bambang CS SPED Center") == (
        "bambang central school special education center"
    )
    # Only uppercase school-type tokens expand, so ordinary words survive.
    assert school_name_key("This is a School") == "this is a school"
    assert name_similarity(
        "Awag IS",
        "Awag Integrated School",
        school=True,
    ) == (1.0, "exact")


def test_name_key_folds_saint_legal_form_and_ampersand():
    assert facility_name_key("St. Anne College Lucena, Inc.") == "saint anne college lucena"
    assert facility_name_key("Saint Anne College Lucena") == "saint anne college lucena"
    assert facility_name_key("St. Louis Anne Colleges - Annex") == (
        "saint louis anne colleges annex"
    )
    assert facility_name_key("St. Adrianne Medical & Lying-In Clinic") == (
        "saint adrianne medical and lying in clinic"
    )


def test_name_key_decodes_html_entity_ampersands():
    expected = "saint adrianne medical and lying in clinic"
    assert facility_name_key("St. Adrianne Medical &AMP; Lying-In Clinic") == expected
    assert facility_name_key("St. Adrianne Medical &amp; Lying-In Clinic") == expected
    assert facility_name_key("St. Adrianne Medical &#38; Lying-In Clinic") == expected


def test_name_similarity_distinguishes_variants_from_branches():
    assert name_similarity("St. Anne College Lucena, Inc.", "Saint Anne College Lucena") == (
        1.0,
        "exact",
    )
    score, reason = name_similarity("St. Louis Anne Colleges", "St. Louis Anne Colleges - Annex")
    assert score < 0.9
    assert reason == "distinguishing"
    score, reason = name_similarity("St. Anne College Lucena", "St. Anne College of Lucena")
    assert score >= 0.8
    assert reason in {"containment", "token_overlap"}
    assert name_similarity("Mercury Drug", "Watsons") == (0.0, "different")


def test_address_overlap_ignores_city_and_generic_street_words():
    administrative = {"lucena", "quezon", "gulang"}
    assert (
        address_overlap(
            "Diversion Road, Brgy. Gulang-gulang, Lucena City",
            "Lucena City, Quezon",
            administrative_names=administrative,
        )
        == 0
    )
    assert (
        address_overlap(
            "Diversion Road, Brgy. Gulang-gulang, Lucena City",
            "12 Diversion Road, Lucena City",
            administrative_names=administrative,
        )
        == 1
    )


def test_subtype_families_compare_across_agency_vocabularies():
    assert subtype_family("school", "HIGHER_EDUCATION_INSTITUTION") == "tertiary"
    assert subtype_family("school", "college") == "tertiary"
    assert subtype_family("school", "OTHER_SCHOOL") is None
    assert subtype_family("school", "school") is None

    assert subtypes_compatible("school", "college", "HIGHER_EDUCATION_INSTITUTION")
    assert subtypes_compatible("school", "HIGHER_EDUCATION_INSTITUTION", "OTHER_SCHOOL")
    assert subtypes_compatible("school", "school", "kindergarten")
    assert not subtypes_compatible("school", "elementary school", "college")
    assert not subtypes_compatible("school", "fast_food", "college")

    # Missing and explicit "other" labels do not assert a kind of place.
    assert subtypes_compatible("school", None, "college")
    assert subtypes_compatible("health_facility", "OTHER_HEALTH_FACILITY", "HOSPITAL")
    # Exact normalized labels still work for types without a family mapping.
    assert subtypes_compatible("health_facility", "HOSPITAL", "hospital")
    assert not subtypes_compatible("health_facility", "HOSPITAL", "CLINIC")


def test_psgc_helpers_reject_region_and_province_codes():
    assert psgc_city_code("0431200017") == "0431200"
    assert psgc_city_code("0431200000") == "0431200"
    assert psgc_city_code("0400000000") is None
    assert psgc_barangay_code("0431200017") == "0431200017"
    assert psgc_barangay_code("0431200000") is None
