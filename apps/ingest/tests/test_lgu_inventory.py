from __future__ import annotations

import csv
from pathlib import Path

from philfacilities_ingest.lgu_inventory import (
    ALL_COLUMNS,
    LguInventoryValidation,
    read_inventory,
    validate_inventory,
)

HEADER = list(ALL_COLUMNS)


def write_csv(path: Path, rows: list[dict[str, str]], *, headers: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers or HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def valid_row(**overrides: str) -> dict[str, str]:
    row = dict.fromkeys(HEADER, "")
    row.update(
        lgu_psgc_code="0102802000",
        lgu_name="Bacarra",
        facility_name="Bacarra Municipal Hall",
        facility_type="government_office",
        facility_subtype="CITY_MUNICIPAL_HALL",
        facility_kind="building",
        ownership_type="LOCAL_GOVERNMENT",
        operator_type="LOCAL_GOVERNMENT",
        address_text="Municipal Hall, Bacarra",
        reference_date="2026-11-16",
        source_reference="Official LGU inventory 2026",
    )
    row.update(overrides)
    return row


def codes(result: LguInventoryValidation) -> set[str]:
    return {issue.code for issue in result.issues}


def test_template_passes_validation() -> None:
    template = Path(__file__).resolve().parents[3] / "data/templates/lgu-inventory-template.csv"
    result = validate_inventory(template)
    assert result.rows == 3
    assert result.accepted == 3
    assert result.rejected == 0
    assert result.issues == []


def test_valid_row_is_accepted(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "inventory.csv", [valid_row()])
    result = validate_inventory(path)
    assert result.accepted == 1
    assert result.rejected == 0


def test_missing_required_column_is_fatal(tmp_path: Path) -> None:
    headers = [column for column in HEADER if column != "source_reference"]
    row = {key: value for key, value in valid_row().items() if key != "source_reference"}
    path = write_csv(tmp_path / "inventory.csv", [row], headers=headers)
    result = validate_inventory(path)
    assert result.rejected == 1
    assert "missing_columns" in codes(result)


def test_personal_and_security_columns_are_rejected(tmp_path: Path) -> None:
    headers = [*HEADER, "contact_person", "cctv"]
    row = valid_row(contact_person="Juan Dela Cruz", cctv="camera layout")
    path = write_csv(tmp_path / "inventory.csv", [row], headers=headers)
    result = validate_inventory(path)
    assert result.rejected == 1
    assert "personal_field_not_accepted" in codes(result)
    assert "sensitive_security_field_not_accepted" in codes(result)


def test_invalid_taxonomy_and_psgc_are_rejected(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "inventory.csv",
        [
            valid_row(
                lgu_psgc_code="123",
                ownership_type="SOMETHING_ELSE",
                operator_type="NOT_A_TYPE",
                facility_type="retail",
                facility_kind="project",
            )
        ],
    )
    result = validate_inventory(path)
    assert result.rejected == 1
    assert {
        "invalid_lgu_psgc",
        "invalid_ownership_type",
        "invalid_operator_type",
        "invalid_facility_type",
        "invalid_facility_kind",
    } <= codes(result)


def test_invalid_reference_date_is_rejected(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "inventory.csv", [valid_row(reference_date="16/11/2026")])
    result = validate_inventory(path)
    assert result.rejected == 1
    assert "invalid_reference_date" in codes(result)


def test_project_and_infrastructure_asset_kinds_are_rejected(tmp_path: Path) -> None:
    for kind in ("project", "infrastructure_asset"):
        path = write_csv(tmp_path / f"{kind}.csv", [valid_row(facility_kind=kind)])
        result = validate_inventory(path)
        assert result.rejected == 1
        assert "invalid_facility_kind" in codes(result)


def test_barangay_psgc_must_belong_to_lgu(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "inventory.csv",
        [valid_row(barangay_psgc_code="0102803001")],
    )
    result = validate_inventory(path)
    assert result.rejected == 1
    assert "invalid_barangay_psgc" in codes(result)


def test_coordinate_pair_and_bounds_are_checked(tmp_path: Path) -> None:
    incomplete = write_csv(tmp_path / "incomplete.csv", [valid_row(latitude="18.0", longitude="")])
    assert "incomplete_coordinates" in codes(validate_inventory(incomplete))

    outside = write_csv(
        tmp_path / "outside.csv",
        [
            valid_row(
                latitude="40.0",
                longitude="120.0",
                coordinate_precision="map_geocoded",
            )
        ],
    )
    assert "coordinates_outside_philippines" in codes(validate_inventory(outside))

    valid = write_csv(
        tmp_path / "valid.csv",
        [
            valid_row(
                latitude="18.05",
                longitude="120.56",
                coordinate_precision="map_geocoded",
                coordinate_method="address geocoding",
            )
        ],
    )
    assert validate_inventory(valid).accepted == 1


def test_duplicate_name_is_a_warning_not_a_rejection(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "inventory.csv",
        [valid_row(), valid_row(lgu_facility_id="SECOND")],
    )
    result = validate_inventory(path)
    assert result.accepted == 2
    assert result.rejected == 0
    assert "duplicate_facility_name_in_lgu" in codes(result)


def test_invalid_inclusion_and_access_classes_are_rejected(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "inventory.csv",
        [valid_row(inclusion_class="GOVERNMENT_OWNED", public_access_class="OPEN")],
    )
    result = validate_inventory(path)
    assert result.rejected == 1
    assert "invalid_inclusion_class" in codes(result)
    assert "invalid_public_access_class" in codes(result)


def test_read_inventory_strips_bom_and_headers(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_text(
        "\ufeff"
        + ",".join(HEADER)
        + "\n"
        + ",".join(valid_row().get(column, "") for column in HEADER)
        + "\n",
        encoding="utf-8",
    )
    headers, rows = read_inventory(path)
    assert headers[0] == "lgu_psgc_code"
    assert rows[0]["lgu_name"] == "Bacarra"
