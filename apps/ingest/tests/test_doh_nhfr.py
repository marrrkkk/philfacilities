"""Parser and normalization tests for the DOH NHFR September 2026 export."""

from __future__ import annotations

import io

import openpyxl
from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.doh_nhfr import (
    DohNhfrAdapter,
    parse_nhfr_workbook,
)

HEADERS = (
    "Health Facility Code",
    "Health Facility Code Short",
    "Facility Name",
    "Facility Major Type",
    "Health Facility Type",
    "Ownership Major Classification",
    "Ownership Sub-Classification for Government facilities",
    "Ownership Sub-Classification for private facilities",
    "Street Name and #",
    "Building name and #",
    "Region Name",
    "Region PSGC",
    "Province Name",
    "Province PSGC",
    "City/Municipality Name",
    "City/Municipality PSGC",
    "Barangay Name",
    "Barangay PSGC",
    "Zip Code",
    "Landline Number",
    "Landline Number 2",
    "Fax Number",
    "Email Address",
    "Alternate Email Address",
    "Official Website",
    "Service Capability",
    "Bed Capacity",
    "Licensing Status",
    "License Validity Date",
)

ROWS = (
    {
        "Health Facility Code": "DOH000000000000001",
        "Facility Name": "Alpha Provincial Hospital",
        "Facility Major Type": "Health Facility",
        "Health Facility Type": "Hospital",
        "Ownership Major Classification": "Government",
        "Ownership Sub-Classification for Government facilities": "Local Government Unit",
        "Street Name and #": "1 Main Street",
        "Region Name": "REGION I (ILOCOS REGION)",
        "Region PSGC": "0100000000",
        "Province Name": "ILOCOS NORTE",
        "Province PSGC": "0128000000",
        "City/Municipality Name": "BACARRA",
        "City/Municipality PSGC": "0128010000",
        "Barangay Name": "LIBTONG",
        # Stored as a number by the source export; the leading zero must be
        # restored rather than accepted as a nine-digit code.
        "Barangay PSGC": 128010010,
        "Bed Capacity": 150,
        "Licensing Status": "Licensing Status:With License",
        "License Validity Date": "12/31/2026",
    },
    {
        "Health Facility Code": "DOH000000000000002",
        "Facility Name": "Beta Medical Center",
        "Facility Major Type": "Health Facility",
        "Health Facility Type": "Hospital",
        "Ownership Major Classification": "Private",
        "Ownership Sub-Classification for private facilities": "Corporation",
        "Region Name": "REGION I (ILOCOS REGION)",
        "Region PSGC": "0100000000",
        "Province Name": "ILOCOS NORTE",
        "Province PSGC": "0128000000",
        "City/Municipality Name": "BACARRA",
        "City/Municipality PSGC": "0128010000",
        "Barangay Name": "POBLACION",
        "Barangay PSGC": "012801002",
        "Bed Capacity": 0,
        "Licensing Status": None,
        "License Validity Date": None,
    },
    {
        "Health Facility Code": "DOH000000000000003",
        "Facility Name": "Gamma Wellness Store",
        "Facility Major Type": "Health Related Facility",
        "Health Facility Type": "Central Warehouse - Ambient",
        "Ownership Major Classification": "Private",
        "Ownership Sub-Classification for private facilities": "Single Proprietorship",
        "Region Name": "REGION I (ILOCOS REGION)",
        "Region PSGC": "0100000000",
        "Province Name": "ILOCOS NORTE",
        "Province PSGC": "0128000000",
        "City/Municipality Name": "BACARRA",
        "City/Municipality PSGC": "0128010000",
        "Barangay Name": "POBLACION",
        "Barangay PSGC": "012801002",
        "Bed Capacity": None,
        "Licensing Status": "Licensing Status:Without License",
        "License Validity Date": None,
    },
)


def _fixture_workbook(rows: tuple[dict[str, object], ...] = ROWS) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(list(HEADERS))
    for row in rows:
        worksheet.append([row.get(header) for header in HEADERS])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _release_spec(content: bytes) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="doh",
        agency_name="Department of Health",
        dataset_slug="doh-nhfr",
        dataset_name="DOH National Health Facility Registry",
        release_label="DOH-NHFR-2026-09-TEST",
        filename="doh-nhfr-2026-09.xlsx",
        content=content,
        source_url="https://example.test/nhfr.xlsx",
        access_method="manual_file",
    )


def test_parse_nhfr_workbook_keeps_institutional_fields_and_leading_zero_psgc() -> None:
    rows = parse_nhfr_workbook(_fixture_workbook())

    assert [row["health_facility_code"] for row in rows] == [
        "DOH000000000000001",
        "DOH000000000000002",
        "DOH000000000000003",
    ]
    assert rows[0]["barangay_psgc"] == "0128010010"
    assert rows[0]["ownership_subclassification"] == "Local Government Unit"
    assert rows[0]["bed_capacity"] == 150
    assert rows[1]["ownership_subclassification"] == "Corporation"
    assert rows[1]["bed_capacity"] == 0
    assert rows[2]["bed_capacity"] is None


def test_adapter_maps_ownership_licensing_and_unmapped_facility_types() -> None:
    spec = _release_spec(_fixture_workbook())
    adapter = DohNhfrAdapter(spec)
    parsed = adapter.parse(spec)

    validated = adapter.validate(parsed)
    assert validated.accepted_rows == 3
    assert validated.rejected_rows == 0
    assert validated.failed is False

    candidates = adapter.normalize(parsed)
    assert [candidate.ownership for candidate in candidates] == [
        "government",
        "private",
        "private",
    ]
    assert [candidate.ownership_type for candidate in candidates] == [
        "LOCAL_GOVERNMENT",
        "PRIVATE_CORPORATE",
        "PRIVATE_INDIVIDUAL_OR_PARTNERSHIP",
    ]
    assert [candidate.facility_subtype for candidate in candidates] == [
        "HOSPITAL",
        "HOSPITAL",
        "OTHER_HEALTH_FACILITY",
    ]
    assert all(candidate.enrichment_only for candidate in candidates)

    hospital = candidates[0]
    assert hospital.health is not None
    assert hospital.health.doh_facility_id == "DOH000000000000001"
    assert hospital.health.facility_major_type == "Health Facility"
    assert hospital.health.facility_type_detail == "Hospital"
    assert hospital.health.ownership_subclassification == "Local Government Unit"
    assert hospital.health.licensing_status == "With License"
    assert hospital.health.bed_capacity == 150
    assert hospital.location.psgc_code == "0128010010"
    assert hospital.location.address_text == "LIBTONG, BACARRA, ILOCOS NORTE"
    assert len(hospital.licenses) == 1
    assert hospital.licenses[0].source_status == "With License"
    assert hospital.licenses[0].valid_until.isoformat() == "2026-12-31"

    assert candidates[1].health is not None
    assert candidates[1].health.bed_capacity == 0
    assert candidates[1].health.licensing_status is None
    assert candidates[1].licenses == []
    assert candidates[2].health is not None
    assert candidates[2].health.licensing_status == "Without License"
    assert candidates[2].licenses == []


def test_adapter_rejects_invalid_codes_duplicates_and_missing_psgc() -> None:
    rows = (
        ROWS[0],
        {**ROWS[0]},
        {
            **ROWS[1],
            "Health Facility Code": "DOH000000000000004",
            "Region PSGC": None,
        },
    )
    spec = _release_spec(_fixture_workbook(rows))
    adapter = DohNhfrAdapter(spec)
    parsed = adapter.parse(spec)
    validated = adapter.validate(parsed)

    codes = [issue.code for issue in validated.issues]
    assert "duplicate_facility_code" in codes
    assert "invalid_psgc" in codes
    assert validated.accepted_rows == 1
    assert validated.rejected_rows == 2
    assert validated.failed is False


def test_parse_rejects_non_xlsx_content() -> None:
    try:
        parse_nhfr_workbook(b"<html>not a workbook</html>")
    except ValueError as exc:
        assert "not an XLSX workbook" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("non-XLSX content was accepted")
