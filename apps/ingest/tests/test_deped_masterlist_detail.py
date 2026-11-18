"""Parser and normalization tests for the DepEd masterlist tabular detail."""

from __future__ import annotations

import csv
import io
import zipfile

from philfacilities_ingest.contracts import ParsedRelease, ParsedRow, ReleaseSpec
from philfacilities_ingest.sources.deped_masterlist_detail import (
    REQUIRED_COLUMNS,
    DepEdMasterlistDetailAdapter,
    _rows_from_csv,
)

FIELDS = (
    "region",
    "division",
    "district",
    "beis_school_id",
    "school_name",
    "street_address",
    "municipality",
    "legislative_district",
    "barangay",
    "sector",
    "settlement_type",
    "school_subclassification",
    "modified_cultural_offering_classification",
)


def _csv(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "region": "Region I",
        "division": "Ilocos Norte",
        "district": "Bacarra I",
        "beis_school_id": "100001",
        "school_name": "Apaleng-Libtong ES",
        "street_address": "Brgy. 21, Libtong, Bacarra, Ilocos Norte",
        "municipality": "BACARRA",
        "legislative_district": "1st District",
        "barangay": "LIBTONG",
        "sector": "public",
        "settlement_type": "partially_urban",
        "school_subclassification": "deped_managed",
        "modified_cultural_offering_classification": "purely_es",
    }
    row.update(overrides)
    return row


def _spec(content: bytes) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-masterlist-sy2020-2021-detail",
        dataset_name="DepEd Masterlist of Schools, SY 2020-2021 — tabular detail",
        release_label="DEPED-MASTERLIST-SY2020-2021-DETAIL-TEST",
        filename="deped-masterlist-sy2020-2021-detail.csv",
        content=content,
        source_url="https://example.test/masterlist.csv",
        access_method="public_csv",
    )


def _parsed(rows: list[dict[str, str]]) -> ParsedRelease:
    return ParsedRelease(
        rows=[
            ParsedRow(
                source_record_key=row["beis_school_id"],
                row_reference=f"csv_row:{index}",
                raw_payload=dict(row),
                normalized_payload={
                    **row,
                    "school_id": row["beis_school_id"],
                    "sector_normalized": row["sector"],
                },
            )
            for index, row in enumerate(rows, start=2)
        ],
        parser_version="test",
        schema_version="test",
    )


def test_required_columns_are_explicit() -> None:
    assert "beis_school_id" in REQUIRED_COLUMNS
    assert "school_subclassification" in REQUIRED_COLUMNS


def test_rows_are_read_from_csv_and_zip() -> None:
    content = _csv([_row()])
    assert _rows_from_csv(content)[0]["division"] == "Ilocos Norte"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("basic_education_institutions.csv", content)
    assert _rows_from_csv(buffer.getvalue())[0]["beis_school_id"] == "100001"


def test_normalize_derives_only_explicit_offering_levels() -> None:
    adapter = DepEdMasterlistDetailAdapter(_spec(b"unused"))
    candidates = adapter.normalize(
        _parsed(
            [
                _row(),
                _row(
                    beis_school_id="100002",
                    school_name="Second School",
                    sector="private",
                    school_subclassification="sectarian",
                    modified_cultural_offering_classification="jhs_with_shs",
                ),
                _row(
                    beis_school_id="100003",
                    school_name="Third School",
                    modified_cultural_offering_classification="unrecognized",
                ),
            ]
        )
    )

    first, second, third = candidates
    assert first.enrichment_only is True
    assert first.ownership == "government"
    assert first.operator_type == "NATIONAL_GOVERNMENT"
    assert first.school.division == "Ilocos Norte"
    assert first.school.legislative_district == "1st District"
    assert first.school.offering_classification == "purely_es"
    assert (first.school.offers_es, first.school.offers_jhs, first.school.offers_shs) == (
        True,
        False,
        False,
    )
    assert second.ownership == "private"
    assert second.operator_type == "PRIVATE_UNSPECIFIED"
    assert (second.school.offers_es, second.school.offers_jhs, second.school.offers_shs) == (
        False,
        True,
        True,
    )
    assert (third.school.offers_es, third.school.offers_jhs, third.school.offers_shs) == (
        None,
        None,
        None,
    )


def test_validate_rejects_duplicate_and_bad_sector() -> None:
    adapter = DepEdMasterlistDetailAdapter(_spec(b"unused"))
    validated = adapter.validate(
        _parsed(
            [
                _row(),
                _row(),
                _row(beis_school_id="100004", school_name="Bad Sector", sector="municipal"),
            ]
        )
    )

    codes = [issue.code for issue in validated.issues]
    assert "duplicate_school_id" in codes
    assert "unknown_sector" in codes
    assert validated.accepted_rows == 1
    assert validated.rejected_rows == 2
