"""Parser tests for the DepEd Masterlist of Schools SY 2020-2021 PDF."""

from __future__ import annotations

import io

import pytest
from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.sources.deped_masterlist import (
    DepEdMasterlistAdapter,
    parse_masterlist_pdf,
)
from reportlab.pdfgen import canvas

HEADERS = (
    ("Region", 50.0),
    ("Division", 114.6),
    ("District", 155.9),
    ("BEIS ID", 176.0),
    ("School Name", 202.9),
    ("Street Address", 309.2),
    ("Municipality", 425.9),
    ("Legislative", 486.6),
    ("Barangay", 520.0),
    ("Sector", 591.5),
)

ROWS = (
    {
        "region": "Region I",
        "division": "Ilocos Norte",
        "district": "Bacarra I",
        "school_id": "100001",
        "school_name": "Alpha ES",
        "street": "Brgy. 1",
        "municipality": "BACARRA",
        "legislative_district": "1st District",
        "barangay": "LIBTONG",
        "sector": "Public",
    },
    {
        "region": "Region I",
        "division": "Ilocos Norte",
        "district": "Bacarra I",
        "school_id": "400001",
        "school_name": "Beta Academy",
        "street": "Poblacion",
        "municipality": "BACARRA",
        "legislative_district": "1st District",
        "barangay": "POBLACION",
        "sector": "Private",
    },
    {
        "region": "Region I",
        "division": "Ilocos Norte",
        "district": "Bacarra I",
        "school_id": "500001",
        "school_name": "Gamma College",
        "street": "National Road",
        "municipality": "BACARRA",
        "legislative_district": "1st District",
        # Deliberately blank: the column then has fewer lines than the IDs and
        # exercises the per-row band fallback.
        "barangay": "",
        "sector": "SUCs/LUCs",
    },
)


def _fixture_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(792, 612))
    # The published layout uses a very small type size; 3 pt keeps
    # "SUCs/LUCs" inside the measured Sector column at x <= 607.5.
    pdf.setFont("Helvetica", 3)
    header_y = 560
    for label, x in HEADERS:
        pdf.drawString(x, header_y, label)
    y = 554
    for row in ROWS:
        pdf.drawString(50.0, y, row["region"])
        pdf.drawString(114.6, y, row["division"])
        pdf.drawString(155.9, y, row["district"])
        pdf.drawRightString(201.6, y, row["school_id"])
        pdf.drawString(202.9, y, row["school_name"])
        pdf.drawString(309.2, y, row["street"])
        pdf.drawString(425.9, y, row["municipality"])
        pdf.drawString(486.6, y, row["legislative_district"])
        if row["barangay"]:
            pdf.drawString(520.0, y, row["barangay"])
        pdf.drawString(591.5, y, row["sector"])
        y -= 5
    pdf.save()
    return buffer.getvalue()


def _release_spec(content: bytes) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-masterlist-sy2020-2021",
        dataset_name="DepEd Masterlist of Schools, SY 2020-2021",
        release_label="DEPED-MASTERLIST-SY2020-2021-TEST",
        filename="deped-masterlist-sy2020-2021.pdf",
        content=content,
        source_url="https://example.test/masterlist.pdf",
        access_method="manual_file",
    )


def test_parse_masterlist_pdf_extracts_ids_and_sectors() -> None:
    rows = parse_masterlist_pdf(_fixture_pdf())

    assert [row["school_id"] for row in rows] == ["100001", "400001", "500001"]
    assert [row["sector"] for row in rows] == ["Public", "Private", "SUCs/LUCs"]
    assert rows[0]["school_name"] == "Alpha ES"
    assert rows[1]["barangay"] == "POBLACION"
    assert rows[2]["barangay"] == ""


def test_adapter_normalizes_sector_to_ownership_without_overwriting_names() -> None:
    adapter = DepEdMasterlistAdapter(_release_spec(_fixture_pdf()))
    parsed = adapter.parse(_release_spec(_fixture_pdf()))

    validated = adapter.validate(parsed)
    assert validated.accepted_rows == 3
    assert validated.rejected_rows == 0

    candidates = adapter.normalize(parsed)
    assert [candidate.school.sector for candidate in candidates] == [
        "public",
        "private",
        "suc_luc",
    ]
    assert [candidate.ownership for candidate in candidates] == [
        "government",
        "private",
        "government",
    ]
    assert candidates[0].inclusion_class == "GOVERNMENT_FACILITY"
    assert candidates[1].inclusion_class == "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    assert candidates[2].ownership_type == "PUBLIC_EDUCATIONAL_INSTITUTION"
    assert all(candidate.enrichment_only for candidate in candidates)


def test_parse_masterlist_pdf_rejects_non_pdf_content() -> None:
    with pytest.raises(ValueError, match="not a PDF"):
        parse_masterlist_pdf(b"<html>not a pdf</html>")
