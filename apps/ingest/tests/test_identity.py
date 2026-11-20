"""Pure identity-text helpers used by aggregation."""

from __future__ import annotations

from philfacilities_ingest.identity import (
    address_overlap,
    address_tokens,
    normalize_display_name,
)


def test_address_tokens_drops_stopwords_and_short_tokens() -> None:
    tokens = address_tokens("12 Mabini Street, Brgy. San Isidro")
    assert "12" not in tokens
    assert "mabini" in tokens
    assert "street" not in tokens


def test_administrative_names_are_removed_per_call() -> None:
    hierarchy = frozenset({"lucena", "quezon"})
    tokens = address_tokens(
        "Mabini Street, Lucena City, Quezon",
        administrative_names=hierarchy,
    )
    assert tokens == {"mabini"}


def test_shared_street_tokens_remain_distinctive() -> None:
    assert address_overlap("12 Mabini Street", "14 Mabini Street") == 1
    assert address_overlap("12 Mabini Street", "12 Rizal Avenue") == 0


def test_cache_matches_uncached_result() -> None:
    # Repeated calls must not leak one caller's administrative hierarchy into
    # another caller's token set.
    hierarchy = frozenset({"lucena"})
    first = address_tokens("Mabini Street, Lucena", administrative_names=hierarchy)
    second = address_tokens("Mabini Street, Lucena")
    assert first == {"mabini"}
    assert second == {"mabini", "lucena"}


def test_uppercase_display_name_is_title_cased() -> None:
    assert (
        normalize_display_name("SANTA TERESITA BARANGAY HEALTH STATION")
        == "Santa Teresita Barangay Health Station"
    )
    assert (
        normalize_display_name("GENERAL SANTOS DOCTORS HOSPITAL, INC.")
        == "General Santos Doctors Hospital, Inc."
    )
    assert normalize_display_name("THE MEDICAL CITY CLARK, INC.") == "The Medical City Clark, Inc."


def test_display_name_preserves_abbreviations_codes_and_numerals() -> None:
    assert normalize_display_name("TUPAS ES") == "Tupas ES"
    assert normalize_display_name("RHU") == "RHU"
    assert normalize_display_name("NHS") == "NHS"
    assert (
        normalize_display_name("BULA RURAL HEALTH UNIT II-BALAOGAN")
        == "Bula Rural Health Unit II-Balaogan"
    )
    assert normalize_display_name("TB-DOTS CENTER") == "TB-DOTS Center"
    assert normalize_display_name("HWN DIAGNOSTIC CLINIC CORP.") == "HWN Diagnostic Clinic Corp."
    assert normalize_display_name("1ST DISTRICT HEALTH OFFICE") == "1ST District Health Office"
    assert normalize_display_name("BGY. 18, SAN QUIRINO (POB.)") == ("Bgy. 18, San Quirino (Pob.)")


def test_display_name_keeps_mixed_case_source_spelling() -> None:
    name = "Our Lady of Perpetual Succor College"
    assert normalize_display_name(name) == name


def test_display_name_handles_apostrophes_and_entities() -> None:
    assert (
        normalize_display_name("REGION 8 HEALER'S INITIATIVE DIAGNOSTIC LABORATORY")
        == "Region 8 Healer's Initiative Diagnostic Laboratory"
    )
    assert (
        normalize_display_name("REPRODUCTIVE HEALTH &AMP; WELLNESS CENTER")
        == "Reproductive Health & Wellness Center"
    )
    assert (
        normalize_display_name("R.G.O. LABORATORY &AMP; INDUSTRIAL CENTER INC.")
        == "R.G.O. Laboratory & Industrial Center Inc."
    )


def test_display_name_handles_unicode_letters_and_single_letter_initials() -> None:
    assert (
        normalize_display_name("STO. NIÑO DIALYSIS CENTER, INC.")
        == "Sto. Niño Dialysis Center, Inc."
    )
    assert (
        normalize_display_name("SANTO NIÑO BARANGAY HEALTH STATION")
        == "Santo Niño Barangay Health Station"
    )
    assert (
        normalize_display_name("CONCEPCION A RURAL HEALTH UNIT") == "Concepcion A Rural Health Unit"
    )
    assert (
        normalize_display_name("SANTO NI\ufffdO BARANGAY HEALTH STATION")
        == "Santo Ni\ufffdo Barangay Health Station"
    )


def test_display_name_keeps_domain_and_brand_acronyms() -> None:
    assert normalize_display_name("PAG-IBIG") == "Pag-IBIG"
    assert normalize_display_name("ACLC") == "ACLC"
    assert (
        normalize_display_name("ABC HEALTH HUB & MULTI-SPECIALTY CLINIC")
        == "ABC Health Hub & Multi-Specialty Clinic"
    )
    assert normalize_display_name("OTP ABRA DE ILOG") == "OTP Abra de Ilog"
    assert (
        normalize_display_name("CALAMBA CHO ANIMAL BITE TREATMENT CENTER")
        == "Calamba CHO Animal Bite Treatment Center"
    )
    assert normalize_display_name("BALILIHAN MHO BIRTHING HOME") == "Balilihan MHO Birthing Home"
    assert (
        normalize_display_name("AGOO MUNICIPAL HEALTH OFFICE ABTC")
        == "Agoo Municipal Health Office ABTC"
    )
    assert (
        normalize_display_name("DULAG UCCP BIRTHING CLINIC, INC.")
        == "Dulag UCCP Birthing Clinic, Inc."
    )
    assert (
        normalize_display_name("1 SEALANDERS MEDICAL CLINIC OPC")
        == "1 Sealanders Medical Clinic OPC"
    )
    assert (
        normalize_display_name("ARC (CDO) MEDCARE SOLUTIONS AND SERVICES INC.")
        == "Arc (CDO) Medcare Solutions and Services Inc."
    )
