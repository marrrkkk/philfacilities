"""Geography presentation rules that do not need a database."""

from __future__ import annotations

from philfacilities_api.services import _urban_rural


def test_psgc_urban_rural_codes_are_normalised() -> None:
    assert _urban_rural("U") == "urban"
    assert _urban_rural("R") == "rural"
    assert _urban_rural("u") == "urban"
    assert _urban_rural(" r ") == "rural"


def test_missing_or_placeholder_classification_stays_unknown() -> None:
    for value in (None, "", "-", "X", "  "):
        assert _urban_rural(value) is None
