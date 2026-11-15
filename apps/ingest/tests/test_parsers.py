"""Parser and fixture tests that do not require a database."""

from __future__ import annotations

import hashlib
import io
from datetime import date

import pytest
from openpyxl import Workbook
from philfacilities_ingest.contracts import ReleaseSpec
from philfacilities_ingest.fixtures import (
    deped_enrollment,
    deped_masterlist,
    deped_resources,
    doh_csv,
    philhealth_pdf,
    psgc_workbook,
)
from philfacilities_ingest.sources.bettergov import OSMParquetAdapter
from philfacilities_ingest.sources.common import RequiredColumnsError, normalise_code
from philfacilities_ingest.sources.deped import (
    DepEdEnrollmentAdapter,
    DepEdMasterlistAdapter,
    DepEdResourceAdapter,
)
from philfacilities_ingest.sources.doh import DOHNHFRAdapter
from philfacilities_ingest.sources.philhealth import PhilHealthPdfAdapter, _row_key, parse_catalog
from philfacilities_ingest.sources.psgc import parse_psgc_workbook


def _spec(
    *,
    agency: str,
    slug: str,
    filename: str,
    content: bytes,
    reference_end: date | None = None,
) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code=agency,
        agency_name=f"Synthetic {agency} fixture",
        dataset_slug=slug,
        dataset_name=f"Synthetic {slug}",
        release_label="SYNTHETIC-TEST-2026",
        filename=filename,
        content=content,
        source_url=None,
        source_published_at=None,
        retrieved_at=None,
        reference_period_start=None,
        reference_period_end=reference_end,
        terms_url=None,
        redistribution_status="not_applicable",
        access_method="fixture",
        is_synthetic=True,
    )


def _xlsx(rows: list[list[object]], title: str = "Masterlist") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    sink = io.BytesIO()
    workbook.save(sink)
    workbook.close()
    return sink.getvalue()


def test_fixture_bytes_are_deterministic() -> None:
    fixtures = [
        psgc_workbook,
        deped_masterlist,
        deped_enrollment,
        deped_resources,
        doh_csv,
        philhealth_pdf,
    ]
    for fixture in fixtures:
        first = fixture()
        second = fixture()
        assert first == second, fixture.__name__
        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_deped_masterlist_parses_valid_rows_and_keeps_unknown_locations_unknown() -> None:
    content = deped_masterlist()
    spec = _spec(
        agency="deped",
        slug="demo-deped-masterlist",
        filename="synthetic-deped-masterlist-2024-2025.xlsx",
        content=content,
    )
    adapter = DepEdMasterlistAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 12

    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0
    assert validation.issues == []

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 12
    assert candidates[0].school is not None
    assert candidates[0].school.deped_school_id == "SYN-DEPED-0001"
    assert candidates[0].location.precision == "source_gps"
    assert candidates[0].location.latitude is not None

    # Fourth fixture row deliberately omits coordinates; absence must not become 0,0.
    missing = candidates[3].location
    assert missing.latitude is None
    assert missing.longitude is None
    assert missing.precision == "unknown"


def test_deped_validation_keeps_leading_zero_ids_and_flags_bad_values() -> None:
    rows = [
        [
            "school_id",
            "school_name",
            "latitude",
            "longitude",
            "coordinate_precision",
        ],
        ["001234", "Leading Zero School", "14.5", "121.0", "source_gps"],
        ["001235", "", "14.5", "121.0", "source_gps"],
        ["001236", "Out Of Range School", "91.0", "121.0", "source_gps"],
        ["001237", "Partial Coordinate School", "14.5", "", "source_gps"],
    ]
    spec = _spec(
        agency="deped",
        slug="demo-deped-masterlist",
        filename="masterlist.xlsx",
        content=_xlsx(rows),
    )
    adapter = DepEdMasterlistAdapter(spec)
    parsed = adapter.parse(spec)
    assert [row.source_record_key for row in parsed.rows] == [
        "001234",
        "001235",
        "001236",
        "001237",
    ]

    validation = adapter.validate(parsed)
    codes = {issue.code for issue in validation.issues}
    assert {"missing_school_name", "latitude_range", "partial_coordinates"} <= codes
    assert validation.rejected_rows == 2
    assert validation.accepted_rows == 2


def test_deped_schema_drift_fails_closed() -> None:
    content = _xlsx([["unexpected_column"], ["value"]])
    spec = _spec(
        agency="deped",
        slug="demo-deped-masterlist",
        filename="masterlist.xlsx",
        content=content,
    )
    with pytest.raises(RequiredColumnsError):
        DepEdMasterlistAdapter(spec).parse(spec)


def test_doh_parser_keeps_unknowns_and_rejects_negative_beds() -> None:
    content = doh_csv()
    spec = _spec(
        agency="doh",
        slug="demo-doh-facilities",
        filename="doh.csv",
        content=content,
        reference_end=date(2026, 9, 30),
    )
    adapter = DOHNHFRAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 6
    assert adapter.validate(parsed).issues == []

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 6
    assert candidates[0].health is not None
    assert candidates[0].health.doh_facility_id == "SYN-DOH-0001"
    assert candidates[0].location.precision == "source_gps"
    assert candidates[0].licenses[0].license_number == "SYN-LIC-0001"

    bad_content = content.replace(b'"25"', b'"-5"', 1)
    bad_spec = _spec(
        agency="doh",
        slug="demo-doh-facilities",
        filename="doh.csv",
        content=bad_content,
    )
    bad_adapter = DOHNHFRAdapter(bad_spec)
    bad_parsed = bad_adapter.parse(bad_spec)
    validation = bad_adapter.validate(bad_parsed)
    assert [issue.code for issue in validation.issues] == ["negative_bed_count"]
    assert validation.rejected_rows == 1


def test_doh_schema_drift_fails_closed() -> None:
    content = b"wrong,columns\n1,2\n"
    spec = _spec(
        agency="doh",
        slug="demo-doh-facilities",
        filename="doh.csv",
        content=content,
    )
    with pytest.raises(RequiredColumnsError):
        DOHNHFRAdapter(spec).parse(spec)


def test_psgc_parser_preserves_leading_zero_codes() -> None:
    content = _xlsx(
        [
            ["psgc_code", "name", "geographic_level", "parent_psgc_code"],
            ["0100000000", "Leading Zero Region", "region", ""],
            ["0100100000", "Leading Zero Province", "province", "0100000000"],
        ],
        title="Regions and Provinces",
    )
    units, warnings = parse_psgc_workbook(content, expected_filename="psgc.xlsx")
    assert warnings == []
    assert [unit.psgc_code for unit in units] == ["0100000000", "0100100000"]
    assert all(unit.psgc_code.startswith("01") for unit in units)
    assert units[1].parent_psgc_code == "0100000000"


def test_normalise_code_never_strips_significant_zeros() -> None:
    assert normalise_code("001234") == "001234"
    assert normalise_code("001234.0") == "001234"
    assert normalise_code(1234) == "1234"


def test_osm_adapter_keeps_multi_valued_healthcare_within_column_limit() -> None:
    """The live OSM healthcare field can contain several semicolon-separated values."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "id": ["node/1"],
            "name": ["Synthetic Demo OSM Hospital"],
            "healthcare": ["hospital;clinic;pharmacy;laboratory;dentist;midwife;doctors"],
            "amenity": ["hospital"],
            "bbox": [{"ymin": 8.0, "ymax": 8.1, "xmin": 124.0, "xmax": 124.1}],
        }
    )
    sink = io.BytesIO()
    pq.write_table(table, sink)
    spec = _spec(
        agency="bettergov",
        slug="demo-osm-health",
        filename="synthetic-osm-health.parquet",
        content=sink.getvalue(),
    )
    adapter = OSMParquetAdapter(spec, facility_domain="health")
    parsed = adapter.parse(spec)
    assert adapter.validate(parsed).issues == []
    candidates = adapter.normalize(parsed)
    assert len(candidates) == 1
    assert candidates[0].facility_subtype == "hospital"
    assert candidates[0].location.precision == "map_geocoded"
    # The preserved raw payload still contains every source value.
    assert "pharmacy" in parsed.rows[0].raw_payload["healthcare"]


def test_philhealth_catalogue_keeps_malformed_anchor_links() -> None:
    """The live index omits </a> on some EMCB rows; those links must not be dropped."""

    html = (
        "<ul>"
        '<li><a href="HOSP_093026.pdf">Hospitals</a></li>'
        '<li><a href="EMCB-PPARTUM_093026.pdf">Postpartum</li>'
        '<li><a href="EMCB-LAB_093026.pdf">Clinical Laboratory</li>'
        "</ul>"
    )
    entries = parse_catalog(
        html, base_url="https://example.test/partners/providers/facilities/accredited/"
    )
    assert [entry.filename for entry in entries] == [
        "HOSP_093026.pdf",
        "EMCB-PPARTUM_093026.pdf",
        "EMCB-LAB_093026.pdf",
    ]
    assert entries[1].category == "Postpartum"
    assert entries[2].url == (
        "https://example.test/partners/providers/facilities/accredited/EMCB-LAB_093026.pdf"
    )


def test_philhealth_pdf_parser_extracts_accreditation_rows() -> None:
    content = philhealth_pdf()
    spec = _spec(
        agency="philhealth",
        slug="demo-philhealth-accreditations",
        filename="synthetic-philhealth-hospitals-2026-09-30.pdf",
        content=content,
        reference_end=date(2026, 9, 30),
    )
    adapter = PhilHealthPdfAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 4
    assert adapter.validate(parsed).issues == []

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 4
    first = candidates[0]
    assert first.display_name == "Synthetic Demo Accredited Hospital 01"
    assert first.facility_type == "health_facility"
    assert first.location.latitude is None
    assert first.location.longitude is None
    assert first.accreditations[0].authority == "PhilHealth"
    assert first.accreditations[0].valid_until == date(2027, 12, 31)
    assert first.accreditations[0].page_reference.startswith("page:")


def test_philhealth_row_keys_keep_repeated_rows_on_the_same_page_distinct() -> None:
    """A page can repeat a facility row; the physical row number must remain in the key."""

    common = ("GAMOT", "Same Facility", "Manila", date(2026, 9, 30), 1)
    assert _row_key(*common, 4) != _row_key(*common, 5)


def test_reprocess_rekeys_stored_records_by_page_and_row() -> None:
    from types import SimpleNamespace

    from philfacilities_ingest.pipeline import _reconcile_source_record_keys

    class _Session:
        def flush(self) -> None:
            pass

    records = [
        SimpleNamespace(source_record_key="old-a", row_number_or_page="page:1:row:4"),
        SimpleNamespace(source_record_key="old-b", row_number_or_page="page:1:row:5"),
    ]
    rows = [
        SimpleNamespace(source_record_key="new-a", row_reference="page:1:row:4"),
        SimpleNamespace(source_record_key="new-b", row_reference="page:1:row:5"),
    ]

    _reconcile_source_record_keys(existing_records=records, parsed_rows=rows, session=_Session())

    assert [record.source_record_key for record in records] == ["new-a", "new-b"]


def test_reprocess_refuses_to_orphan_a_stored_record() -> None:
    from types import SimpleNamespace

    from philfacilities_ingest.pipeline import _reconcile_source_record_keys

    class _Session:
        def flush(self) -> None:
            pass

    records = [
        SimpleNamespace(source_record_key="old-a", row_number_or_page="page:1:row:4"),
    ]
    rows = [
        SimpleNamespace(source_record_key="new-a", row_reference="page:1:row:5"),
    ]

    with pytest.raises(ValueError, match="absent"):
        _reconcile_source_record_keys(
            existing_records=records, parsed_rows=rows, session=_Session()
        )


def test_philhealth_pdf_parser_accepts_the_official_hospital_layout() -> None:
    """The observed agency PDF uses human column labels and region/province separators."""

    content = philhealth_pdf(layout="official")
    spec = _spec(
        agency="philhealth",
        slug="demo-philhealth-accreditations",
        filename="synthetic-philhealth-official-layout-2026-09-30.pdf",
        content=content,
        reference_end=date(2026, 9, 30),
    )
    adapter = PhilHealthPdfAdapter(spec)
    parsed = adapter.parse(spec)

    # The two section-header rows have no expiry or facility name and must not become records.
    assert len(parsed.rows) == 4
    assert adapter.validate(parsed).issues == []

    first = parsed.rows[0].raw_payload
    assert first["name_of_health_facility"] == "Synthetic Demo Accredited Hospital 01"
    assert first["cat"] == "Hospital"
    assert first["beds"] == "50"
    assert first["expire_date"] == "12/31/2027"
    assert first["sec"] == "G"

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 4
    assert candidates[0].accreditations[0].valid_until == date(2027, 12, 31)
    assert candidates[0].health is not None
    assert candidates[0].health.bed_capacity == 50


def test_enrollment_and_resource_parsers_preserve_observations() -> None:
    enrollment = deped_enrollment()
    enrollment_spec = _spec(
        agency="deped",
        slug="demo-deped-enrollment",
        filename="enrollment.xlsx",
        content=enrollment,
    )
    enrollment_adapter = DepEdEnrollmentAdapter(enrollment_spec)
    enrollment_parsed = enrollment_adapter.parse(enrollment_spec)
    assert len(enrollment_parsed.rows) == 24
    assert enrollment_adapter.validate(enrollment_parsed).issues == []
    enrollment_candidates = enrollment_adapter.normalize(enrollment_parsed)
    assert enrollment_candidates[0].school is not None
    assert enrollment_candidates[0].school.enrollment[0].learner_count == 100

    resources = deped_resources()
    resource_spec = _spec(
        agency="deped",
        slug="demo-deped-resources",
        filename="resources.xlsx",
        content=resources,
    )
    resource_adapter = DepEdResourceAdapter(resource_spec)
    resource_parsed = resource_adapter.parse(resource_spec)
    assert len(resource_parsed.rows) == 12
    assert resource_adapter.validate(resource_parsed).issues == []
    resource_candidates = resource_adapter.normalize(resource_parsed)
    assert resource_candidates[0].school is not None
    assert resource_candidates[0].school.resources[0].resource_code == "classrooms_total"
