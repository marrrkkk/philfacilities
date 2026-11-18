"""Normalization tests for the DOE existing-power-plant list."""

from __future__ import annotations

from philfacilities_ingest.contracts import ParsedRelease, ParsedRow, ReleaseSpec
from philfacilities_ingest.sources.doe_power import DoePowerPlantAdapter


def _spec() -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="doe",
        agency_name="Department of Energy",
        dataset_slug="doe-power-plants-luzon",
        dataset_name="DOE existing power plants — Luzon",
        release_label="DOE-POWER-LUZON-TEST",
        filename="doe-power-luzon.pdf",
        content=b"%PDF-test",
        source_url="https://example.test/doe-luzon.pdf",
        access_method="public_pdf",
    )


def _row(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "facility_code": "100000001",
        "official_name": "Anda Power Plant",
        "resource_type": "Coal",
        "technology": "CFB",
        "technology_type": "Circulating Fluidized Bed (CFB) Coal",
        "connection_type": "Grid-connected",
        "grid": "Luzon",
        "installed_mw": 83.7,
        "dependable_mw": 80.0,
        "number_of_units": "1",
        "municipality_province": "Pampanga",
        "province": "Pampanga",
        "region": "3",
        "operator": "Anda Power Corporation",
        "owner": "Anda Power Corporation",
        "owner_type": "NON-NPC/IPP",
        "contract_type": "",
        "date_commissioned": "2016",
        "operating_hours": "",
    }
    payload.update(overrides)
    return payload


def _parsed(rows: list[dict[str, object]]) -> ParsedRelease:
    entries = [
        ParsedRow(
            source_record_key=str(row["facility_code"]),
            row_reference=f"doe:test:{row['facility_code']}",
            raw_payload=row,
            normalized_payload=row,
        )
        for row in rows
    ]
    return ParsedRelease(rows=entries, parser_version="test", schema_version="test")


def test_normalize_exposes_utility_profile_fields() -> None:
    adapter = DoePowerPlantAdapter(_spec(), grid="Luzon")
    candidate = adapter.normalize(_parsed([_row()]))[0]

    assert candidate.facility_subtype == "POWER_PLANT"
    assert candidate.operator_type == "PRIVATE_UNSPECIFIED"
    assert candidate.utility is not None
    assert candidate.utility.doe_facility_code == "100000001"
    assert candidate.utility.resource_type == "Coal"
    assert candidate.utility.technology_type == "Circulating Fluidized Bed (CFB) Coal"
    assert candidate.utility.connection_type == "Grid-connected"
    assert candidate.utility.grid == "Luzon"
    assert candidate.utility.owner_type == "NON-NPC/IPP"
    assert candidate.utility.installed_mw == 83.7
    assert candidate.utility.dependable_mw == 80.0
    assert candidate.utility.number_of_units == 1
    assert candidate.utility.date_commissioned == "2016"


def test_normalize_keeps_blank_utility_values_null() -> None:
    adapter = DoePowerPlantAdapter(_spec(), grid="Mindanao")
    candidate = adapter.normalize(
        _parsed(
            [
                _row(
                    facility_code="100000002",
                    contract_type="",
                    dependable_mw=None,
                    number_of_units="",
                    date_commissioned="",
                )
            ]
        )
    )[0]

    assert candidate.utility is not None
    assert candidate.utility.contract_type is None
    assert candidate.utility.dependable_mw is None
    assert candidate.utility.number_of_units is None
    assert candidate.utility.date_commissioned is None


def test_validate_rejects_rows_without_installed_capacity() -> None:
    adapter = DoePowerPlantAdapter(_spec(), grid="Luzon")
    validated = adapter.validate(_parsed([_row(installed_mw=None)]))

    assert [issue.code for issue in validated.issues] == ["missing_installed_capacity"]
    assert validated.accepted_rows == 0
    assert validated.rejected_rows == 1
