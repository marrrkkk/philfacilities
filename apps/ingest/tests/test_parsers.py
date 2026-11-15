"""Parser and fixture tests that do not require a database."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date

import pytest
from openpyxl import Workbook
from philfacilities_ingest.acquisition import FetchResult, is_blocker_page
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
from philfacilities_ingest.sources.bir import BirRevenueDistrictOfficeAdapter, parse_rao_lines
from philfacilities_ingest.sources.common import RequiredColumnsError, normalise_code
from philfacilities_ingest.sources.deped import (
    DepEdEnrollmentAdapter,
    DepEdMasterlistAdapter,
    DepEdResourceAdapter,
)
from philfacilities_ingest.sources.doh import DOHNHFRAdapter
from philfacilities_ingest.sources.dswd_crcf import DswdCrcfDirectoryAdapter
from philfacilities_ingest.sources.national_museum import NationalMuseumDirectoryAdapter
from philfacilities_ingest.sources.nlp import NlpPublicLibraryPdfAdapter
from philfacilities_ingest.sources.nmis_naris import NmisNarisDirectoryAdapter
from philfacilities_ingest.sources.philhealth import PhilHealthPdfAdapter, _row_key, parse_catalog
from philfacilities_ingest.sources.phlpost import PhlPostLocatorAdapter
from philfacilities_ingest.sources.ppa import PpaPortListAdapter
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


def _pdf_table(rows: list[list[str]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    sink = io.BytesIO()
    document = SimpleDocTemplate(sink, pagesize=letter)
    table = Table(rows)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    document.build([table])
    return sink.getvalue()


def test_nlp_public_library_pdf_parses_ids_status_and_types() -> None:
    header = [
        "NO.",
        "PHILIPPINE PUBLIC LIBRARY ID",
        "REGION",
        "LOCATION",
        "TYPE OF PUBLIC LIBRARY",
        "NAME OF LIBRARY",
        "ADDRESS",
        "TELEPHONE NUMBER",
        "STATUS",
        "DATE AFFILIATED",
    ]
    rows = [
        header,
        [
            "1",
            "000123",
            "NCR",
            "Quezon City",
            "City",
            "Synthetic City Library",
            "1 Example Street",
            "(02) 000-0000",
            "Active",
            "January 10, 2020",
        ],
        [
            "2",
            "000124",
            "Region III",
            "San Fernando",
            "Barangay Reading Center",
            "Synthetic Reading Center",
            "2 Example Street",
            "-",
            "Closed",
            "-",
        ],
    ]
    spec = _spec(
        agency="nlp",
        slug="nlp-public-libraries",
        filename="nlp-public-libraries.pdf",
        content=_pdf_table(rows),
    )
    adapter = NlpPublicLibraryPdfAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    assert parsed.rows[0].source_record_key == "000123"
    assert adapter.validate(parsed).issues == []

    candidates = adapter.normalize(parsed)
    assert candidates[0].inclusion_class == "GOVERNMENT_FACILITY"
    assert candidates[0].ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert candidates[0].facility_subtype == "CITY_LIBRARY"
    assert candidates[0].public_access_class == "PUBLIC_FREE"
    assert candidates[0].record_status == "active_in_registry"
    assert candidates[0].location.latitude is None
    assert candidates[0].location.precision == "unknown"
    assert candidates[0].functions[0].function_code == "PUBLIC_LIBRARY"
    assert candidates[1].facility_subtype == "BARANGAY_READING_CENTER"
    assert candidates[1].record_status == "inactive_in_registry"


def test_national_museum_adapter_uses_directory_artifact_without_coordinates() -> None:
    artifact = {
        "directory_url": "https://www.nationalmuseum.gov.ph/our-museums/",
        "retrieved_at": "2026-11-15T00:00:00+00:00",
        "records": [
            {
                "name": "Synthetic Area Museum",
                "url": "https://www.nationalmuseum.gov.ph/our-museums/synthetic-area-museum/",
                "detail_status": 200,
                "address": "Example Avenue, Synthetic Town",
                "telephone": None,
                "email": None,
            },
            {
                "name": "Synthetic Site Museum",
                "url": "https://www.nationalmuseum.gov.ph/our-museums/synthetic-site-museum/",
                "detail_status": 200,
                "address": None,
                "telephone": None,
                "email": None,
            },
        ],
    }
    spec = _spec(
        agency="nmp",
        slug="nmp-regional-area-site-museums",
        filename="nmp-museums.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = NationalMuseumDirectoryAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    assert parsed.rows[0].source_record_key == "synthetic-area-museum"
    assert adapter.validate(parsed).issues == []

    candidates = adapter.normalize(parsed)
    assert candidates[0].inclusion_class == "GOVERNMENT_FACILITY"
    assert candidates[0].ownership_type == "NATIONAL_GOVERNMENT"
    assert candidates[0].facility_kind == "site"
    assert candidates[0].facility_type == "museum"
    assert candidates[0].location.address_text == "Example Avenue, Synthetic Town"
    assert candidates[0].location.latitude is None
    assert candidates[0].functions[0].function_code == "MUSEUM"


def test_phlpost_locator_keeps_host_semantics_and_duplicate_rows_distinct() -> None:
    html = """
    <html><body>
    <table>
      <tr><th>Provinces</th><th>Post Offices</th><th>Addresss</th><th>Services</th></tr>
      <tr><td>Metro Manila</td><td>Example Post Office</td>
          <td>Example Mall, Quezon City</td><td>Acceptance; Delivery</td></tr>
      <tr><td>Metro Manila</td><td>Example Post Office</td>
          <td>Example Mall, Quezon City</td><td>Acceptance; Delivery</td></tr>
      <tr><td>Cebu</td><td>Standalone Post Office</td>
          <td>Main Street, Cebu City</td><td>Acceptance</td></tr>
    </table>
    </body></html>
    """
    spec = _spec(
        agency="phlpost",
        slug="phlpost-post-office-locator",
        filename="phlpost-locator.html",
        content=html.encode("utf-8"),
    )
    adapter = PhlPostLocatorAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 3
    keys = [row.source_record_key for row in parsed.rows]
    assert len(keys) == len(set(keys)) == 3
    assert "internal_only_rights" in {warning["code"] for warning in parsed.warnings}

    candidates = adapter.normalize(parsed)
    hosted = candidates[0]
    standalone = candidates[2]
    assert hosted.facility_kind == "facility_unit"
    assert hosted.public_access_class == "UNKNOWN"
    assert {role.role_type for role in hosted.roles} == {"OPERATOR", "HOST"}
    host = next(role for role in hosted.roles if role.role_type == "HOST")
    assert host.entity_name == "Example Mall"
    assert host.entity_type == "unknown"
    assert [service.service_name for service in hosted.services] == ["Acceptance", "Delivery"]
    assert standalone.facility_kind == "facility"
    assert {role.role_type for role in standalone.roles} == {"OPERATOR"}


def test_bir_rao_ocr_rows_keep_region_and_office_identity() -> None:
    from philfacilities_ingest.ocr import OcrLine

    lines = [
        OcrLine(text="RRNo.1-llocosRegion", confidence=0.99, page_number=1),
        OcrLine(text="RDONo.1-llocosNorte", confidence=0.99, page_number=1),
        OcrLine(text="RDONo.17A-NorthTarlac", confidence=0.98, page_number=2),
        OcrLine(
            text="RDONo.94-IsabelaCity(Non-BARMM)/Basilan(BARMM)",
            confidence=0.97,
            page_number=4,
        ),
        OcrLine(text="RDONo.1-llocosNorte", confidence=0.99, page_number=4),
    ]
    records, warnings = parse_rao_lines(lines)
    assert [record["rdo_code"] for record in records] == ["1", "17A", "94"]
    assert records[0]["revenue_region_name"] == "llocos Region"
    assert records[1]["rdo_name"] == "North Tarlac"
    assert warnings and "Duplicate OCR row" in warnings[0]

    spec = _spec(
        agency="bir",
        slug="bir-revenue-district-offices",
        filename="bir-rao-006-2025.pdf",
        content=b"",
    )
    adapter = BirRevenueDistrictOfficeAdapter(spec)
    from philfacilities_ingest.contracts import ParsedRelease, ParsedRow

    parsed = ParsedRelease(
        rows=[
            ParsedRow(
                source_record_key=f"RDO-{record['rdo_code']}",
                row_reference=f"rdo:{record['rdo_code']}",
                raw_payload=record,
                normalized_payload=record,
            )
            for record in records
        ],
        parser_version=adapter.parser_version,
        schema_version=adapter.schema_version,
    )
    assert adapter.validate(parsed).rejected_rows == 0
    candidates = adapter.normalize(parsed)
    assert candidates[0].facility_type == "government_office"
    assert candidates[0].facility_subtype == "REVENUE_DISTRICT_OFFICE"
    assert candidates[0].inclusion_class == "GOVERNMENT_FACILITY"
    assert candidates[0].ownership_type == "NATIONAL_GOVERNMENT"
    assert candidates[0].location.latitude is None
    assert candidates[0].functions[0].function_code == "TAX_ADMINISTRATION"
    assert candidates[0].roles[0].entity_name == "Bureau of Internal Revenue"


def test_dswd_crcf_deduplicates_desktop_and_mobile_cards_without_coordinates() -> None:
    def card(name: str, address: str) -> str:
        return (
            "<figure class='wp-caption'>"
            f"<figcaption>{name}</figcaption>"
            "</figure>"
            "<h6><strong>Field Office 1 – Example</strong><br />"  # noqa: RUF001
            f"{address}</h6>"
        )

    def block(region: str, cards: list[str]) -> str:
        return (
            "<details><summary>"
            f"<div class='e-n-accordion-item-title-text'>{region}</div>"
            "</summary>" + "".join(cards) + "</details>"
        )

    region = "REGION 1: Ilocos Region"
    desktop = [
        card("Synthetic Haven", "1 Example St., Example City"),
        card("Synthetic Home", "2 Example St., Example Town"),
    ]
    html = (
        "<html><body><p>The agency operates 77 CRCF.</p>"
        + block(region, desktop)
        + block(region, desktop)
        + "</body></html>"
    )
    spec = _spec(
        agency="dswd",
        slug="dswd-crcf-directory",
        filename="dswd-crcf-directory.html",
        content=html.encode("utf-8"),
    )
    adapter = DswdCrcfDirectoryAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    metadata = parsed.warnings[0]["metadata"]
    assert metadata["raw_cards"] == 4
    assert metadata["unique_cards"] == 2
    assert metadata["duplicate_variants"] == 2
    assert metadata["page_claim"] == 77
    warning_codes = {warning["code"] for warning in parsed.warnings}
    assert {
        "desktop_mobile_duplicate_cards",
        "no_coordinates",
        "source_count_discrepancy",
    } <= warning_codes
    assert adapter.validate(parsed).rejected_rows == 0

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 2
    first = candidates[0]
    assert first.facility_type == "social_welfare_facility"
    assert first.facility_subtype == "CRCF"
    assert first.inclusion_class == "GOVERNMENT_FACILITY"
    assert first.ownership_type == "NATIONAL_GOVERNMENT"
    assert first.location.address_text == (
        "1 Example St., Example City, Field Office 1 – Example, "  # noqa: RUF001
        "REGION 1: Ilocos Region"
    )
    assert first.location.latitude is None
    assert first.location.precision == "unknown"
    assert first.functions[0].function_code == "SOCIAL_WELFARE"
    assert {role.role_type for role in first.roles} == {"OWNER", "OPERATOR", "MANAGER"}
    manager = next(role for role in first.roles if role.role_type == "MANAGER")
    assert manager.entity_name == "Field Office 1 – Example"  # noqa: RUF001


def test_nmis_naris_groups_duplicate_ltos_and_keeps_ownership_evidence_explicit() -> None:
    payload = [
        {
            "company_name": "Example Cold Storage Inc.",
            "full_address": "1 Example St., Example City",
            "region_code": "130000000",
            "province_code": None,
            "municipality_code": "Example City",
            "barangay": "Example Barangay",
            "lto_number": "NMIS-CSW-0001-AA",
            "establishment_type": "coldstorage_warehouse",
            "geocode_address": "1 Example St., Example City, Philippines",
            "cached_lat": 14.5,
            "cached_lng": 121.0,
        },
        {
            "company_name": "Example Cold Storage Inc.",
            "full_address": "1 EXAMPLE ST., EXAMPLE CITY",
            "region_code": "130000000",
            "province_code": None,
            "municipality_code": "Example City",
            "barangay": "Example Barangay",
            "lto_number": "NMIS-CSW-0001-AA",
            "establishment_type": "coldstorage_warehouse",
            "geocode_address": "1 EXAMPLE ST., EXAMPLE CITY, Philippines",
            "cached_lat": None,
            "cached_lng": None,
        },
        {
            "company_name": "Sample Municipal Slaughterhouse",
            "full_address": "2 Example St., Sample Town",
            "region_code": "030000000",
            "province_code": "Example Province",
            "municipality_code": "Sample Town",
            "barangay": "Poblacion",
            "lto_number": "SH-0002-AA",
            "establishment_type": "slaughterhouse",
            "geocode_address": "2 Example St., Sample Town, Philippines",
            "cached_lat": None,
            "cached_lng": None,
        },
        {
            "company_name": "Private Meat Co.",
            "full_address": "3 Example St., Sample Town",
            "region_code": "030000000",
            "province_code": "Example Province",
            "municipality_code": "Sample Town",
            "barangay": "Poblacion",
            "lto_number": "SH-0003-AA",
            "establishment_type": "slaughterhouse",
            "geocode_address": "3 Example St., Sample Town, Philippines",
            "cached_lat": 15.0,
            "cached_lng": None,
        },
    ]
    html = (
        "<html><body><h1>Accredited Meat Establishments</h1>"
        f"<script>const ltoLocations = {json.dumps(payload)};</script></body></html>"
    )
    spec = _spec(
        agency="nmis",
        slug="nmis-naris-accredited-meat-establishments",
        filename="nmis-naris.html",
        content=html.encode("utf-8"),
    )
    adapter = NmisNarisDirectoryAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 3
    metadata = parsed.warnings[0]["metadata"]
    assert metadata["raw_rows"] == 4
    assert metadata["unique_lto_rows"] == 3
    assert metadata["duplicate_lto_rows"] == 1
    assert metadata["rows_with_cached_coordinates"] == 1
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0
    assert "partial_coordinates" in {issue.code for issue in validation.issues}

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 3
    cold_storage = candidates[0]
    municipal = candidates[1]
    private = candidates[2]
    assert cold_storage.facility_type == "agricultural_facility"
    assert cold_storage.facility_subtype == "COLD_STORAGE_WAREHOUSE"
    assert cold_storage.inclusion_class == "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    assert cold_storage.ownership_type == "PRIVATE_UNSPECIFIED"
    assert cold_storage.location.latitude == 14.5
    assert cold_storage.location.longitude == 121.0
    assert cold_storage.location.precision == "geocoded"
    assert cold_storage.location.method == "naris_cached_address_geocode"
    assert cold_storage.functions[0].function_code == "FOOD_SAFETY"
    assert municipal.inclusion_class == "GOVERNMENT_FACILITY"
    assert municipal.ownership_type == "LOCAL_GOVERNMENT"
    assert municipal.facility_subtype == "SLAUGHTERHOUSE"
    assert {role.role_type for role in municipal.roles} == {
        "OWNER",
        "OPERATOR",
        "LICENSOR",
    }
    assert municipal.location.latitude is None
    assert private.inclusion_class == "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    assert private.location.latitude is None
    assert {function.function_code for function in private.functions} == {
        "FOOD_SAFETY",
        "SLAUGHTERHOUSE",
    }
    assert "LTO number is registry evidence" in private.access_conditions


def test_nmis_naris_fails_closed_without_lto_payload() -> None:
    spec = _spec(
        agency="nmis",
        slug="nmis-naris-accredited-meat-establishments",
        filename="nmis-naris.html",
        content=b"<html><body><p>Busy</p></body></html>",
    )
    with pytest.raises(ValueError):
        NmisNarisDirectoryAdapter(spec).parse(spec)


def _ppa_pdf() -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    sink = io.BytesIO()
    document = SimpleDocTemplate(sink, pagesize=letter)
    story: list[object] = [
        Paragraph("2.1 MANILA/NORTHERN LUZON____", None),
        Paragraph("A. PORT MANAGEMENT OFFICE OF NCR NORTH (PMO NCN)", None),
    ]
    rows = [
        ["NAME", "RORO", "NON-RORO", "REMARKS"],
        ["BASEPORT", "", "", ""],
        ["1. PIER 2", "X", "X", ""],
        ["2. ANCHORAGE EXAMPLE", "", "X", ""],
        ["TMO - VITAS", "", "", ""],
        ["1. OTP EXAMPLE", "", "X", ""],
    ]
    table = Table(rows)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story.extend([table, PageBreak()])
    story.extend(
        [
            Paragraph("LIST OF PRIVATE PORTS", None),
            Spacer(1, 8),
            Paragraph("I. MANILA/NORTHERN LUZON", None),
            Spacer(1, 8),
            Paragraph("A. PORT MANAGEMENT OFFICE OF NCR NORTH (PMO NCN)", None),
            Spacer(1, 8),
            Paragraph("PRIVATE PORT", None),
            Spacer(1, 8),
            Paragraph("1) Example Private Port RoRo", None),
            Spacer(1, 8),
            Paragraph("2) Example Unregistered Port*", None),
        ]
    )
    document.build(story)
    return sink.getvalue()


def test_ppa_port_list_preserves_hierarchy_marks_and_private_status() -> None:
    content = _ppa_pdf()
    spec = _spec(
        agency="ppa",
        slug="ppa-port-list",
        filename="ppa-port-list.pdf",
        content=content,
    )
    adapter = PpaPortListAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 5
    assert {warning["code"] for warning in parsed.warnings} == {"no_coordinates"}
    assert adapter.validate(parsed).rejected_rows == 0

    candidates = {candidate.display_name: candidate for candidate in adapter.normalize(parsed)}
    pier = candidates["PIER 2"]
    assert pier.facility_type == "transport_facility"
    assert pier.facility_subtype == "SEAPORT"
    assert pier.facility_kind == "facility"
    assert pier.inclusion_class == "GOVERNMENT_FACILITY"
    assert pier.ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert pier.operator_type == "GOCC"
    assert pier.functions[0].function_code == "SEA_TRANSPORT"
    assert pier.roles[0].role_type == "OPERATOR"
    assert pier.roles[0].entity_name == "Philippine Ports Authority"
    assert pier.location.latitude is None
    assert pier.location.precision == "unknown"

    anchorage = candidates["ANCHORAGE EXAMPLE"]
    assert anchorage.facility_kind == "site"

    private = candidates["Example Private Port"]
    assert private.inclusion_class == "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    assert private.ownership_type == "PRIVATE_UNSPECIFIED"
    assert private.operator_type == "UNKNOWN"
    assert private.roles == []
    assert private.public_access_class == "UNKNOWN"
    assert "must not be assumed" in private.access_conditions
    evidence = private.functions[0].evidence
    assert evidence["roro_marked"] is True
    assert evidence["non_roro_marked"] is None

    unregistered = candidates["Example Unregistered Port"]
    assert unregistered.functions[0].evidence["unregistered"] is True


def test_blocker_detection_ignores_cdn_asset_hostnames() -> None:
    normal = FetchResult(
        url="https://example.gov.ph/",
        final_url="https://example.gov.ph/",
        status_code=200,
        content=(
            b'<html><link rel="stylesheet" '
            b'href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome.css"></html>'
        ),
        headers={"content-type": "text/html"},
    )
    challenge = FetchResult(
        url="https://example.gov.ph/",
        final_url="https://example.gov.ph/",
        status_code=403,
        content=b"<html><title>Just a moment...</title><div id='cf-chl-widget'></div></html>",
        headers={"content-type": "text/html"},
    )
    assert is_blocker_page(normal) is False
    assert is_blocker_page(challenge) is True
