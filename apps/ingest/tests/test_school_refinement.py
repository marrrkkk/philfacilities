"""School subtype classifier evidence."""

from __future__ import annotations

from philfacilities_ingest.school_labels import (
    CANONICAL_SCHOOL_SUBTYPES,
    classify_school_subtype,
)


def test_canonical_subtypes_pass_through() -> None:
    for subtype in CANONICAL_SCHOOL_SUBTYPES:
        known, target = classify_school_subtype(subtype)
        assert known is True
        assert target == subtype


def test_raw_map_tags_are_mapped() -> None:
    assert classify_school_subtype("school") == (True, "OTHER_SCHOOL")
    assert classify_school_subtype("kindergarten") == (True, "OTHER_SCHOOL")
    assert classify_school_subtype("university") == (True, "HIGHER_EDUCATION_INSTITUTION")
    assert classify_school_subtype("college") == (True, "HIGHER_EDUCATION_INSTITUTION")
    assert classify_school_subtype("vocational_school") == (True, "TRAINING_INSTITUTION")


def test_non_school_labels_are_cleared() -> None:
    for label in (
        "fast_food",
        "place_of_worship",
        "toilets",
        "Data Facility",
        "PUBLIC_LIBRARY",
        "LOCAL_GOVERNMENT_OFFICE",
    ):
        assert classify_school_subtype(label) == (True, None)


def test_unrecognised_label_is_not_silently_cleared() -> None:
    assert classify_school_subtype("Some New School Class") == (False, None)


def test_empty_values_are_empty() -> None:
    assert classify_school_subtype(None) == (True, None)
    assert classify_school_subtype("  ") == (True, None)
