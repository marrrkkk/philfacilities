"""Parser and normalization tests for DepEd Project Bukas enrollment."""

from __future__ import annotations

import csv
import io
import zipfile

from philfacilities_ingest.contracts import ParsedRelease, ParsedRow, ReleaseSpec
from philfacilities_ingest.sources.deped_bukas import (
    ENROLLMENT_COLUMNS,
    MANAGEMENT_NORMALIZED,
    REQUIRED_COLUMNS,
    SECTOR_NORMALIZED_BUKAS,
    DepEdBukasEnrollmentAdapter,
    _rows_from_csv,
)

FIELDS = (
    "school_id",
    "school_name",
    "region",
    "division",
    "province",
    "school_district",
    "legislative_district",
    "municipality",
    "barangay",
    "street_address",
    "sector",
    "school_management",
    "annex_status",
    "offers_es",
    "offers_jhs",
    "offers_shs",
    *ENROLLMENT_COLUMNS,
)


def _csv(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "school_id": "100001",
        "school_name": "Apaleng-Libtong ES",
        "region": "Region I",
        "division": "Ilocos Norte",
        "province": "ILOCOS NORTE",
        "school_district": "Bacarra I",
        "legislative_district": "1st District",
        "municipality": "BACARRA",
        "barangay": "LIBTONG",
        "street_address": "Brgy. 21, Libtong, Bacarra, Ilocos Norte",
        "sector": "Public",
        "school_management": "DepEd",
        "annex_status": "Standalone School",
        "offers_es": "True",
        "offers_jhs": "False",
        "offers_shs": "False",
    }
    row.update({column: "0" for column in ENROLLMENT_COLUMNS})
    row.update(overrides)
    return row


def _spec(content: bytes = b"unused") -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-project-bukas-enrollment-sy2024-2025",
        dataset_name="DepEd Project Bukas — Enrollment in SY 2024-2025",
        release_label="DEPED-PROJECT-BUKAS-ENROLLMENT-SY2024-2025-TEST",
        filename="deped-project-bukas-enrollment-sy2024-2025.zip",
        content=content,
        source_url="https://example.test/enrollment.zip",
        access_method="public_archived_zip",
    )


def _parsed(rows: list[dict[str, str]]) -> ParsedRelease:
    return ParsedRelease(
        rows=[
            ParsedRow(
                source_record_key=row["school_id"],
                row_reference=f"csv_row:{index}",
                raw_payload=dict(row),
                normalized_payload={
                    **row,
                    "school_id": row["school_id"],
                    "sector_normalized": SECTOR_NORMALIZED_BUKAS.get(row["sector"].casefold()),
                    "management_normalized": MANAGEMENT_NORMALIZED.get(
                        row["school_management"].casefold()
                    ),
                },
            )
            for index, row in enumerate(rows, start=2)
        ],
        parser_version="test",
        schema_version="test",
    )


def test_required_columns_and_enrollment_columns_are_explicit() -> None:
    assert "school_id" in REQUIRED_COLUMNS
    assert "offers_shs" in REQUIRED_COLUMNS
    assert len(ENROLLMENT_COLUMNS) == 62
    assert "g11_abm_male" in ENROLLMENT_COLUMNS
    assert "g12_unique_female" in ENROLLMENT_COLUMNS


def test_rows_are_read_from_csv_and_zip() -> None:
    content = _csv([_row()])
    assert _rows_from_csv(content)[0]["division"] == "Ilocos Norte"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "Enrollment in SY 2024-2025/enrollment_2024-25.csv",
            content,
        )
    assert _rows_from_csv(buffer.getvalue())[0]["school_id"] == "100001"


def test_normalize_fills_profile_and_keeps_offered_zeroes() -> None:
    adapter = DepEdBukasEnrollmentAdapter(_spec())
    candidates = adapter.normalize(
        _parsed(
            [
                _row(
                    kinder_male="4",
                    kinder_female="7",
                    g1_male="0",
                    g1_female="0",
                    g11_abm_male="9",
                ),
                _row(
                    school_id="200001",
                    school_name="Second School",
                    sector="Private",
                    school_management="Sectarian",
                    offers_es="False",
                    offers_jhs="True",
                    offers_shs="True",
                    g7_male="0",
                    g11_stem_female="5",
                ),
            ]
        )
    )

    first, second = candidates
    assert first.enrichment_only is True
    assert first.ownership == "government"
    assert first.ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert first.operator_type == "NATIONAL_GOVERNMENT"
    assert first.school.sector == "public"
    assert first.school.school_management == "deped_managed"
    assert first.school.division == "Ilocos Norte"
    assert first.school.district == "Bacarra I"
    assert first.location.address_text == "Brgy. 21, Libtong, Bacarra, Ilocos Norte"
    by_grade_sex = {
        (row.grade_level, row.sex): row.learner_count for row in first.school.enrollment
    }
    assert by_grade_sex[("kinder", "male")] == 4
    assert by_grade_sex[("kinder", "female")] == 7
    # ES is offered, so a zero grade count is retained as a real zero.
    assert by_grade_sex[("g1", "male")] == 0
    # SHS is not offered, so its zero is non-applicable and omitted.
    assert ("g12", "female") not in by_grade_sex
    # A positive count is retained even when its offering flag is false.
    assert by_grade_sex[("g11_abm", "male")] == 9

    assert second.ownership == "private"
    assert second.operator_type == "PRIVATE_UNSPECIFIED"
    assert second.school.sector == "private"
    assert second.school.school_management == "sectarian"
    assert ("g7", "male") in {(row.grade_level, row.sex) for row in second.school.enrollment}
    assert ("g11_stem", "female") in {
        (row.grade_level, row.sex) for row in second.school.enrollment
    }


def test_pso_sector_is_not_turned_into_an_ownership_guess() -> None:
    adapter = DepEdBukasEnrollmentAdapter(_spec())
    (candidate,) = adapter.normalize(
        _parsed(
            [
                _row(
                    school_id="900001",
                    school_name="Philippine School Overseas",
                    region="PSO",
                    division="QATAR",
                    province="PSO",
                    school_district="DOHA",
                    legislative_district="PSO",
                    municipality="PSO",
                    barangay="",
                    street_address="",
                    sector="PSO",
                    school_management="PSO",
                )
            ]
        )
    )

    assert candidate.school.sector == "pso"
    assert candidate.school.school_management == "pso"
    assert candidate.ownership == "unknown"
    assert candidate.ownership_type == "UNKNOWN"
    assert candidate.inclusion_class == "DISCOVERY_CANDIDATE"
    assert candidate.location.address_text == "DOHA, QATAR"


def test_validate_rejects_duplicates_bad_sector_and_invalid_count() -> None:
    adapter = DepEdBukasEnrollmentAdapter(_spec())
    validated = adapter.validate(
        _parsed(
            [
                _row(),
                _row(),
                _row(school_id="100004", school_name="Bad Sector", sector="Municipal"),
                _row(school_id="100005", g1_male="-1"),
            ]
        )
    )

    codes = [issue.code for issue in validated.issues]
    assert "duplicate_school_id" in codes
    assert "unknown_sector" in codes
    assert "invalid_learner_count" in codes
    assert validated.accepted_rows == 1
    assert validated.rejected_rows == 3
