"""Pure slug-normalization rules that do not need a database."""

from __future__ import annotations

from philfacilities_ingest.slugs import _suffix_is_part_of_name


def test_agency_code_in_the_name_is_not_stripped() -> None:
    assert _suffix_is_part_of_name(
        "maydolong-nas-under-ched",
        "Maydolong NAS (Under CHED)",
    )
    # A numeric collision suffix on the name slug is still the name.
    assert _suffix_is_part_of_name(
        "maydolong-nas-under-ched-2",
        "Maydolong NAS (Under CHED)",
    )


def test_trailing_agency_token_after_a_name_is_stripped() -> None:
    assert not _suffix_is_part_of_name("alpha-clinic-osm", "Alpha Clinic")
    assert not _suffix_is_part_of_name("alpha-clinic-doh-2", "Alpha Clinic")
