from __future__ import annotations

from datetime import date

from philfacilities_api.rights import (
    RIGHTS_APPROVED_ATTRIBUTION,
    RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
    RIGHTS_RESTRICTED,
    RIGHTS_REVIEW_REQUIRED,
    dataset_is_publishable,
    normalize_rights,
    rights_allow_public,
)
from philfacilities_ingest.sources.philhealth import (
    _expiry_half_rows,
    _is_provider_header,
    _merge_expiry_half,
    _row_key,
    _rows_from_tables,
)


def test_philhealth_header_without_expiry_is_recognised() -> None:
    assert _is_provider_header(
        ["", "NAME OF HEALTH FACILITY", "CAT", "TEL_NO", "EMAIL", "STREET", "MUNICIPALITY"]
    )
    assert not _is_provider_header(["Region", "Total providers", "Notes"])


def test_philhealth_split_tables_inherit_provider_header() -> None:
    header = [
        "",
        "NAME OF HEALTH FACILITY",
        "CAT",
        "TEL_NO",
        "EMAIL",
        "STREET",
        "MUNICIPALITY",
    ]
    rows = _rows_from_tables(
        [
            (
                1,
                [
                    header,
                    ["CORDILLERA ADMINISTRATIVE REGION", None, None, None, None, None, None],
                    [
                        "1",
                        "BUCLOC RURAL HEALTH UNIT",
                        "EMCB-ANTE",
                        "0915",
                        "a@b",
                        "LAMAO",
                        "BUCLOC",
                    ],
                ],
            ),
            (
                1,
                [
                    [
                        "2",
                        "DAGUIOMAN RURAL HEALTH UNIT",
                        "EMCB-ANTE",
                        "0916",
                        "c@d",
                        "TUI",
                        "DAGUIOMAN",
                    ],
                ],
            ),
        ]
    )

    assert len(rows) == 2
    assert rows[0]["name_of_health_facility"] == "BUCLOC RURAL HEALTH UNIT"
    assert rows[1]["municipality"] == "DAGUIOMAN"
    assert rows[0]["_row"] == 3
    assert rows[1]["_row"] == 1


def test_philhealth_expiry_half_is_merged_only_when_aligned() -> None:
    tables = [
        (1, [["EXPIRE DATE", "SEC"], ["12/31/2026", "G"], ["12/31/2027", "P"]]),
        (2, [["EXPIRE DATE", "SEC"], ["12/31/2026", "G"]]),
    ]
    assert _expiry_half_rows(tables) == {
        1: [
            {"expire_date": "12/31/2026", "sec": "G"},
            {"expire_date": "12/31/2027", "sec": "P"},
        ],
        2: [{"expire_date": "12/31/2026", "sec": "G"}],
    }

    rows = [
        {"_page": 3, "_ordinal": 1, "name_of_health_facility": "A"},
        {"_page": 3, "_ordinal": 2, "name_of_health_facility": "B"},
        {"_page": 4, "_ordinal": 1, "name_of_health_facility": "C"},
    ]
    expiry_pages = _expiry_half_rows(tables)
    _merge_expiry_half(rows, {5: expiry_pages[1], 6: expiry_pages[2]})
    assert [row["expire_date"] for row in rows] == ["12/31/2026", "12/31/2027", "12/31/2026"]
    assert [row["sec"] for row in rows] == ["G", "P", "G"]


def test_philhealth_two_column_annex_is_not_parsed_as_providers() -> None:
    header = ["", "NAME OF HEALTH FACILITY", "CAT", "TEL_NO", "EMAIL", "STREET", "MUNICIPALITY"]
    rows = _rows_from_tables(
        [
            (1, [header, ["1", "EXAMPLE RHU", "EMCB", "0915", "a@b", "POB", "MANILA"]]),
            (2, [["EXPIRE DATE", "SEC"], ["12/31/2026", "G"]]),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["name_of_health_facility"] == "EXAMPLE RHU"


def test_philhealth_source_keys_keep_repeated_physical_rows_distinct() -> None:
    first = _row_key("Hospital", "Example Hospital", "Manila", date(2026, 9, 30), 12, 4)
    second = _row_key("Hospital", "Example Hospital", "Manila", date(2026, 9, 30), 12, 5)

    assert first != second
    assert first.startswith("philhealth:hospital:example-hospital:manila:")
    assert second.startswith("philhealth:hospital:example-hospital:manila:")


def test_rights_vocabulary_is_explicit_and_conservative() -> None:
    assert normalize_rights("allowed_with_conditions") == RIGHTS_APPROVED_ATTRIBUTION
    assert normalize_rights("restricted") == RIGHTS_RESTRICTED
    assert normalize_rights("permission_required") == RIGHTS_REVIEW_REQUIRED
    assert normalize_rights("publicly_available_verified") == RIGHTS_PUBLICLY_AVAILABLE_VERIFIED
    assert normalize_rights(None) == "unknown"
    assert normalize_rights("something_else") == "unknown"

    assert rights_allow_public(RIGHTS_APPROVED_ATTRIBUTION)
    assert rights_allow_public(RIGHTS_PUBLICLY_AVAILABLE_VERIFIED)
    assert not rights_allow_public(RIGHTS_RESTRICTED)
    assert not rights_allow_public(RIGHTS_REVIEW_REQUIRED)


def test_public_availability_still_requires_an_approved_gate() -> None:
    assert dataset_is_publishable(
        redistribution_status=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        gate_status="approved",
    )
    assert not dataset_is_publishable(
        redistribution_status=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        gate_status="blocked",
    )
    assert not dataset_is_publishable(
        redistribution_status=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        gate_status="approved",
        publication_status="internal_only",
    )


def test_publication_requires_both_permitted_rights_and_approved_gate() -> None:
    assert dataset_is_publishable(
        redistribution_status=RIGHTS_APPROVED_ATTRIBUTION,
        gate_status="approved",
    )
    assert not dataset_is_publishable(
        redistribution_status=RIGHTS_APPROVED_ATTRIBUTION,
        gate_status="blocked",
    )
    assert not dataset_is_publishable(
        redistribution_status=RIGHTS_RESTRICTED,
        gate_status="approved",
    )
    assert not dataset_is_publishable(
        redistribution_status=RIGHTS_APPROVED_ATTRIBUTION,
        gate_status="approved",
        publication_status="internal_only",
    )
    # Synthetic fixtures are the one deliberate exception: they carry no third-party rights.
    assert dataset_is_publishable(
        redistribution_status="not_applicable",
        gate_status="approved",
        is_synthetic=True,
    )
