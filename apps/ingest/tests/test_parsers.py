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
from philfacilities_ingest.sources.ched_heida import (
    ChedHeidaAdapter,
    parse_hei_rows,
    parse_records_found,
    parse_region_links,
)
from philfacilities_ingest.sources.common import RequiredColumnsError, normalise_code
from philfacilities_ingest.sources.deped import (
    DepEdEnrollmentAdapter,
    DepEdMasterlistAdapter,
    DepEdResourceAdapter,
)
from philfacilities_ingest.sources.deped_ebeis import (
    DepEdEBEISAdapter,
    parse_masterlist_html,
    school_levels,
)
from philfacilities_ingest.sources.doh import DOHNHFRAdapter
from philfacilities_ingest.sources.dswd_crcf import DswdCrcfDirectoryAdapter
from philfacilities_ingest.sources.dti_negosyo import DtiNegosyoCenterAdapter
from philfacilities_ingest.sources.national_museum import NationalMuseumDirectoryAdapter
from philfacilities_ingest.sources.nbi import NbiOfficeAdapter, parse_office_html
from philfacilities_ingest.sources.nlp import NlpPublicLibraryPdfAdapter
from philfacilities_ingest.sources.nmis_naris import NmisNarisDirectoryAdapter
from philfacilities_ingest.sources.pagasa_aws import PagasaAwsAdapter, parse_aws_html
from philfacilities_ingest.sources.philhealth import PhilHealthPdfAdapter, _row_key, parse_catalog
from philfacilities_ingest.sources.phlpost import PhlPostLocatorAdapter
from philfacilities_ingest.sources.ppa import PpaPortListAdapter
from philfacilities_ingest.sources.psgc import parse_psgc_workbook
from philfacilities_ingest.sources.sss_branch import SssBranchAdapter


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


def test_dti_negosyo_centers_preserve_geography_and_withhold_contacts() -> None:
    artifact = {
        "finder_url": "https://negosyocenter.dti.gov.ph/negosyo-center-directory",
        "retrieved_at": "2026-11-15T13:40:00+00:00",
        "records": [
            {
                "id": 1434,
                "region": "NCR - National Capital Region",
                "province": "Metro Manila",
                "city": "Mandaluyong",
                "name": "Negosyo Center Mandaluyong",
                "address": "Mandaluyong City Hall Complex, Maysilo Circle, Mandaluyong City",
                "phone": None,
                "hours": None,
                "email": "NCMandaluyong_LGU@dti.gov.ph",
                "is_active": True,
            },
            {
                "id": 1435,
                "region": "NCR - National Capital Region",
                "province": "Metro Manila",
                "city": "Parañaque City",
                "name": "Parañaque City Negosyo Center",
                "address": "4F Paranaque City Hall, Paranaque City",
                "phone": "02-0000-0000",
                "hours": "08:00-17:00",
                "email": "person@example.test",
                "is_active": False,
            },
        ],
    }
    spec = _spec(
        agency="dti",
        slug="dti-negosyo-centers",
        filename="dti-negosyo-centers.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = DtiNegosyoCenterAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    assert "phone" not in parsed.rows[0].normalized_payload
    assert "email" not in parsed.rows[0].normalized_payload
    assert "hours" not in parsed.rows[0].normalized_payload
    assert adapter.validate(parsed).rejected_rows == 0

    candidates = {candidate.display_name: candidate for candidate in adapter.normalize(parsed)}
    mandaluyong = candidates["Negosyo Center Mandaluyong"]
    assert mandaluyong.facility_type == "government_office"
    assert mandaluyong.facility_subtype == "NEGOSYO_CENTER"
    assert mandaluyong.facility_kind == "facility_unit"
    assert mandaluyong.inclusion_class == "GOVERNMENT_FACILITY"
    assert mandaluyong.ownership_type == "GOVERNMENT_UNSPECIFIED"
    assert mandaluyong.operator_type == "GOVERNMENT_UNSPECIFIED"
    assert mandaluyong.public_access_class == "UNKNOWN"
    assert mandaluyong.record_status == "active_in_registry"
    assert mandaluyong.location.latitude is None
    assert mandaluyong.location.precision == "unknown"
    assert mandaluyong.functions[0].function_code == "BUSINESS_ADVISORY"
    assert mandaluyong.functions[0].evidence["source_is_active"] is True
    assert "person@example.test" not in json.dumps(
        [candidate.__dict__ for candidate in candidates.values()], default=str
    )

    paranaque = candidates["Parañaque City Negosyo Center"]
    assert paranaque.record_status == "inactive_in_registry"
    assert paranaque.functions[0].designation_status == "unknown"


def test_dti_negosyo_centers_reject_missing_names_and_duplicate_ids() -> None:
    artifact = {
        "records": [
            {"id": 1, "name": "", "region": "NCR", "province": "Metro Manila", "city": "Manila"},
            {
                "id": 2,
                "name": "Duplicate Center",
                "region": "NCR",
                "province": "Metro Manila",
                "city": "Manila",
            },
            {
                "id": 2,
                "name": "Duplicate Center",
                "region": "NCR",
                "province": "Metro Manila",
                "city": "Manila",
            },
        ]
    }
    spec = _spec(
        agency="dti",
        slug="dti-negosyo-centers",
        filename="dti-negosyo-centers.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = DtiNegosyoCenterAdapter(spec)
    parsed = adapter.parse(spec)
    result = adapter.validate(parsed)
    assert result.rejected_rows == 2
    assert {issue.code for issue in result.issues} == {
        "missing_center_name",
        "duplicate_center_id",
        "missing_address",
    }


def test_ched_heida_parser_extracts_institutional_fields_only() -> None:
    directory_html = """
    <a href="https://heida.ched.gov.ph/hei-directory/1" class="group">
      <h3 class="text-xl font-bold">Region I (Ilocos Region)</h3>
      <div>Browse Directory</div>
    </a>
    <a href="https://heida.ched.gov.ph/hei-directory/2" class="group">
      <h3 class="text-xl font-bold">Region II (Cagayan Valley)</h3>
      <div>Browse Directory</div>
    </a>
    """
    assert parse_region_links(directory_html) == [
        {"id": "1", "name": "Region I (Ilocos Region)"},
        {"id": "2", "name": "Region II (Cagayan Valley)"},
    ]

    region_html = """
    <div>153 Records Found</div>
    <table>
      <thead><tr>
        <th>HEI Name &amp; Code</th><th>Type</th><th>Contact Info</th>
        <th>Address</th><th>Institutional Head</th>
      </tr></thead>
      <tbody>
        <tr>
          <td><div><span class="text-sm font-bold text-gray-900">Example Private College</span>
            <span class="mt-1 text-xs font-mono text-gray-400">1122</span></div></td>
          <td><span class="inline-flex uppercase text-orange-600">
            Private Non-Sectarian Stock</span></td>
          <td><a href="mailto:person@example.test">person@example.test</a>
            <div>075-000-0000</div></td>
          <td>Mc Arthur Highway, Urdaneta City, Pangasinan</td>
          <td><span>Dr. Person Name</span></td>
        </tr>
        <tr>
          <td><div><span class="text-sm font-bold text-gray-900">Example State University</span>
            <span class="mt-1 text-xs font-mono text-gray-400">1001</span></div></td>
          <td><span class="inline-flex uppercase text-blue-600">
            Chartered State College/University (Main)</span></td>
          <td><div></div></td>
          <td>Batac, Ilocos Norte</td>
          <td><span>Not available</span></td>
        </tr>
      </tbody>
    </table>
    """
    assert parse_records_found(region_html) == 153
    rows = parse_hei_rows(region_html)
    assert rows == [
        {
            "name": "Example Private College",
            "code": "1122",
            "type": "Private Non-Sectarian Stock",
            "address": "Mc Arthur Highway, Urdaneta City, Pangasinan",
        },
        {
            "name": "Example State University",
            "code": "1001",
            "type": "Chartered State College/University (Main)",
            "address": "Batac, Ilocos Norte",
        },
    ]
    serialized = json.dumps(rows)
    assert "person@example.test" not in serialized
    assert "075-000-0000" not in serialized
    assert "Dr. Person Name" not in serialized


def test_ched_heida_normalizes_public_private_and_unknown_types() -> None:
    artifact = {
        "directory_url": "https://heida.ched.gov.ph/hei-directory",
        "retrieved_at": "2026-11-15T14:00:00+00:00",
        "records": [
            {
                "region_id": "1",
                "region": "Region I (Ilocos Region)",
                "name": "Example Private College",
                "code": "1122",
                "type": "Private Non-Sectarian Stock",
                "address": "Urdaneta City, Pangasinan",
                "source_page": "https://heida.ched.gov.ph/hei-directory/1?page=1",
            },
            {
                "region_id": "1",
                "region": "Region I (Ilocos Region)",
                "name": "Example State University",
                "code": "1001",
                "type": "Chartered State College/University (Main)",
                "address": "Batac, Ilocos Norte",
                "source_page": "https://heida.ched.gov.ph/hei-directory/1?page=1",
            },
            {
                "region_id": "1",
                "region": "Region I (Ilocos Region)",
                "name": "Example Local College",
                "code": "1156",
                "type": "Local Government College/University",
                "address": "Bayambang, Pangasinan",
                "source_page": "https://heida.ched.gov.ph/hei-directory/1?page=2",
            },
            {
                "region_id": "1",
                "region": "Region I (Ilocos Region)",
                "name": "Example Other Institution",
                "code": None,
                "type": "Others, please specify",
                "address": "Laoag City, Ilocos Norte",
                "source_page": "https://heida.ched.gov.ph/hei-directory/1?page=2",
            },
        ],
    }
    spec = _spec(
        agency="ched",
        slug="ched-heida-hei-directory",
        filename="ched-heida.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = ChedHeidaAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 4
    assert "contact" not in parsed.rows[0].normalized_payload
    assert "head" not in parsed.rows[0].normalized_payload
    result = adapter.validate(parsed)
    assert result.rejected_rows == 0
    assert {issue.code for issue in result.issues} == {"ownership_not_established"}

    candidates = {candidate.display_name: candidate for candidate in adapter.normalize(parsed)}
    private = candidates["Example Private College"]
    assert private.facility_type == "school"
    assert private.facility_subtype == "HIGHER_EDUCATION_INSTITUTION"
    assert private.inclusion_class == "PRIVATE_PUBLIC_SERVICE_PROVIDER"
    assert private.ownership_type == "PRIVATE_CORPORATE"
    assert private.operator_type == "PRIVATE_CORPORATE"
    assert private.public_access_class == "UNKNOWN"
    assert private.record_status == "active_in_registry"
    assert private.location.latitude is None
    assert private.location.precision == "unknown"
    assert private.functions[0].function_code == "EDUCATION"
    assert private.functions[0].evidence["institution_type"] == "Private Non-Sectarian Stock"

    state = candidates["Example State University"]
    assert state.inclusion_class == "GOVERNMENT_FACILITY"
    assert state.ownership_type == "PUBLIC_EDUCATIONAL_INSTITUTION"
    assert state.operator_type == "PUBLIC_EDUCATIONAL_INSTITUTION"

    local = candidates["Example Local College"]
    assert local.inclusion_class == "GOVERNMENT_FACILITY"
    assert local.ownership_type == "LOCAL_GOVERNMENT"
    assert local.operator_type == "LOCAL_GOVERNMENT"

    other = candidates["Example Other Institution"]
    assert other.inclusion_class == "DISCOVERY_CANDIDATE"
    assert other.ownership_type == "UNKNOWN"
    assert other.operator_type == "UNKNOWN"


def test_ched_heida_rejects_duplicate_codes_and_missing_names() -> None:
    artifact = {
        "records": [
            {
                "region_id": "1",
                "region": "Region I",
                "name": "",
                "code": "1001",
                "type": "Private Non-Sectarian Stock",
                "address": "Address",
            },
            {
                "region_id": "1",
                "region": "Region I",
                "name": "Duplicate College",
                "code": "2002",
                "type": "Private Non-Sectarian Stock",
                "address": "Address",
            },
            {
                "region_id": "1",
                "region": "Region I",
                "name": "Duplicate College",
                "code": "2002",
                "type": "Private Non-Sectarian Stock",
                "address": "Address",
            },
        ]
    }
    spec = _spec(
        agency="ched",
        slug="ched-heida-hei-directory",
        filename="ched-heida.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = ChedHeidaAdapter(spec)
    parsed = adapter.parse(spec)
    result = adapter.validate(parsed)
    assert result.rejected_rows == 2
    assert {issue.code for issue in result.issues} == {
        "missing_institution_name",
        "duplicate_institution_key",
    }


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


def test_sss_branch_locator_withholds_contact_person_and_publishes_institution_fields() -> None:
    artifact = {
        "locator_url": "https://www.sss.gov.ph/sss-branch-locator/",
        "records": [
            {
                "branchCode": "C5",
                "branchName": "ALABANG-MUNTINLUPA",
                "branchAddr": (
                    "22 GF & 2F, NORFIL BUILDING NATIONAL HIGHWAY PUTATAN "
                    "CITY OF MUNTINLUPA NCR, FOURTH DISTRICT"
                ),
                "branchContact": "Tel No. : +63 (02) 88072608",
                "branchContactPerson": "JUAN DELA CRUZ",
                "branchEmail": "alabang@sss.gov.ph",
                "regionCode": "N",
                "regionName": "National Capital Region",
            },
            {
                "branchCode": "NA",
                "branchName": "BICUTAN-SUN VALLEY",
                "branchAddr": None,
                "branchContact": None,
                "branchContactPerson": None,
                "branchEmail": None,
                "regionCode": "N",
                "regionName": "National Capital Region",
            },
        ],
    }
    spec = _spec(
        agency="sss",
        slug="sss-branch-locator",
        filename="sss-branch-locator.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = SssBranchAdapter(spec)
    parsed = adapter.parse(spec)
    assert len(parsed.rows) == 2
    assert parsed.rows[0].normalized_payload == {
        "branchCode": "C5",
        "branchName": "ALABANG-MUNTINLUPA",
        "branchAddr": (
            "22 GF & 2F, NORFIL BUILDING NATIONAL HIGHWAY PUTATAN "
            "CITY OF MUNTINLUPA NCR, FOURTH DISTRICT"
        ),
        "regionCode": "N",
        "regionName": "National Capital Region",
    }
    assert "JUAN DELA CRUZ" not in json.dumps(parsed.rows[0].normalized_payload)
    assert "alabang@sss.gov.ph" not in json.dumps(parsed.rows[0].normalized_payload)
    result = adapter.validate(parsed)
    assert result.rejected_rows == 0
    assert {issue.code for issue in result.issues} == {"missing_branch_address"}

    candidates = {candidate.source_record_key: candidate for candidate in adapter.normalize(parsed)}
    alabang = candidates["SSS:C5"]
    assert alabang.display_name == "SSS ALABANG-MUNTINLUPA Branch"
    assert alabang.facility_type == "government_office"
    assert alabang.facility_subtype == "PUBLIC_SERVICE_CENTER"
    assert alabang.inclusion_class == "GOVERNMENT_FACILITY"
    assert alabang.ownership_type == "GOCC"
    assert alabang.operator_type == "GOCC"
    assert alabang.public_access_class == "SERVICE_USERS_ONLY"
    assert alabang.record_status == "unknown"
    assert alabang.location.latitude is None
    assert alabang.functions[0].function_code == "SOCIAL_SECURITY_SERVICE"
    assert alabang.roles[0].role_type == "OPERATOR"
    assert alabang.roles[0].entity_type == "GOCC"
    assert "JUAN DELA CRUZ" not in json.dumps(
        [candidate.__dict__ for candidate in candidates.values()], default=str
    )


def test_pagasa_aws_parser_publishes_station_identity_not_readings() -> None:
    html = """
    <table class="table">
      <thead><tr>
        <th>Site ID</th><th>Site Name</th><th>Temperature</th><th>Humidity</th>
        <th>Wind Speed</th><th>Wind Direction</th><th>Precipitation</th>
        <th>Pressure</th><th>Solar Radiation</th><th>Last Updated</th>
      </tr></thead>
      <tbody>
        <tr><td>98</td><td>Science Garden, Quezon City</td><td>25 °C</td>
        <td>82 %</td><td>3.6 km/hr</td><td>NNE</td><td>0 mm/hr</td>
        <td>1008</td><td>1.1</td><td>November 15, 2026, 11:50 pm</td></tr>
      </tbody>
    </table>
    """
    header, records = parse_aws_html(html)
    assert "Site ID" in header
    assert records[0]["Site Name"] == "Science Garden, Quezon City"

    artifact = {
        "source_url": "https://bagong.pagasa.dost.gov.ph/automated-weather-station",
        "records": [
            {
                "site_id": "98",
                "site_name": "Science Garden, Quezon City",
                "readings": {"Temperature": "25 °C", "Humidity": "82 %"},
                "last_updated": "November 15, 2026, 11:50 pm",
                "row_reference": "pagasa-aws-html:1",
            }
        ],
    }
    spec = _spec(
        agency="pagasa",
        slug="pagasa-automated-weather-stations",
        filename="pagasa-aws.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = PagasaAwsAdapter(spec)
    parsed = adapter.parse(spec)
    assert parsed.rows[0].normalized_payload == {
        "site_id": "98",
        "site_name": "Science Garden, Quezon City",
        "last_updated": "November 15, 2026, 11:50 pm",
    }
    assert "Temperature" not in json.dumps(parsed.rows[0].normalized_payload)
    assert adapter.validate(parsed).rejected_rows == 0
    candidate = adapter.normalize(parsed)[0]
    assert candidate.facility_type == "environmental_monitoring"
    assert candidate.facility_subtype == "WEATHER_STATION"
    assert candidate.inclusion_class == "GOVERNMENT_FACILITY"
    assert candidate.ownership_type == "NATIONAL_GOVERNMENT"
    assert candidate.operator_type == "NATIONAL_GOVERNMENT"
    assert candidate.location.latitude is None
    assert candidate.functions[0].function_code == "ENVIRONMENTAL_MONITORING"
    assert candidate.roles[0].entity_type == "NATIONAL_GOVERNMENT"
    assert "25 °C" not in json.dumps(candidate.__dict__, default=str)


def test_nbi_office_parser_withholds_personal_fields_and_keeps_map_precision() -> None:
    html = """
    <ul class="reg-offices"><div class="blueBar">National Capital Region</div>
      <li>
        <div class="fancybox-hidden">
          <div class="blueBar"><p>NATIONAL CAPITAL REGIONAL (NCR)</p></div>
          <div><b>Location</b><p>NBI HQ,<br /> Pasay City, Metro Manila</p></div>
          <div><p><iframe src="https://www.google.com/maps/embed?pb=!1m18!2d120.98282531484006!3d14.580946989815038"></iframe></p></div>
          <div><b>Contact Details</b><p>Trunkline.: 523-8231 to 38</p></div>
          <div><b>Email Address</b><p><a data-cfemail="abc">[email protected]</a></p></div>
          <div><b>Regional Director</b><p>EMETERIO A. DONGALLO, JR.</p></div>
        </div>
      </li>
    </ul>
    """
    records = parse_office_html(html)
    assert len(records) == 1
    assert records[0]["office_name"] == "NATIONAL CAPITAL REGIONAL (NCR)"
    assert records[0]["region"] == "National Capital Region"
    assert records[0]["location"] == "NBI HQ, Pasay City, Metro Manila"
    assert records[0]["latitude"] == 14.580946989815038
    assert records[0]["longitude"] == 120.98282531484006

    artifact = {
        "records": [
            {
                **records[0],
                "office_key": "NATIONAL-CAPITAL-REGIONAL-NCR",
            }
        ]
    }
    spec = _spec(
        agency="nbi",
        slug="nbi-regional-district-offices",
        filename="nbi-offices.json",
        content=json.dumps(artifact).encode("utf-8"),
    )
    adapter = NbiOfficeAdapter(spec)
    parsed = adapter.parse(spec)
    assert "EMETERIO A. DONGALLO, JR." not in json.dumps(parsed.rows[0].normalized_payload)
    assert "523-8231" not in json.dumps(parsed.rows[0].normalized_payload)
    assert adapter.validate(parsed).rejected_rows == 0
    candidate = adapter.normalize(parsed)[0]
    assert candidate.facility_type == "government_office"
    assert candidate.facility_subtype == "NATIONAL_AGENCY_OFFICE"
    assert candidate.inclusion_class == "GOVERNMENT_FACILITY"
    assert candidate.ownership_type == "NATIONAL_GOVERNMENT"
    assert candidate.location.precision == "map_geocoded"
    assert candidate.location.method == "google_maps_embed_on_official_page"
    assert candidate.location.latitude == 14.580946989815038
    assert candidate.functions[0].function_code == "PUBLIC_SERVICE_COUNTER"


def test_ebeis_withholds_head_names_and_maps_grade_bands():
    html = """
    <table>
      <tr><th>School ID</th><th>School Name</th><th>Head / Position</th>
          <th>Address</th><th>School Type</th></tr>
      <tr><td>123456</td><td>Sample Central School</td>
          <td>JUAN DELA CRUZ - Principal</td>
          <td>Poblacion, Sample City</td>
          <td>Kinder, Grade 1-6, Grade 7-10 &amp; Grade 11-12</td></tr>
      <tr><td>654321</td><td>Sample Elementary School</td>
          <td>MARIA SANTOS - Head Teacher</td>
          <td>Barangay Sample</td>
          <td>Kinder &amp; Grade 1-6</td></tr>
    </table>
    """
    header, rows = parse_masterlist_html(html)
    assert header[-1] == "School Type"
    assert len(rows) == 2

    spec = _spec(
        agency="deped",
        slug="deped-ebeis-masterlist-ncr",
        filename="ebeis.html",
        content=html.encode("utf-8"),
    )
    adapter = DepEdEBEISAdapter(spec)
    parsed = adapter.parse(spec)
    assert "Head / Position" in parsed.rows[0].raw_payload
    assert "Head / Position" not in parsed.rows[0].normalized_payload
    assert "JUAN DELA CRUZ" not in json.dumps(parsed.rows[0].normalized_payload)
    assert {warning["code"] for warning in parsed.warnings} == {
        "withheld_school_head_names",
        "ownership_not_in_source",
    }
    validation = adapter.validate(parsed)
    assert validation.rejected_rows == 0
    assert validation.issues == []

    candidates = adapter.normalize(parsed)
    first, second = candidates
    assert first.facility_subtype == "OTHER_SCHOOL"
    assert first.ownership == "unknown"
    assert first.inclusion_class is None
    assert first.school.offers_es is True
    assert first.school.offers_jhs is True
    assert first.school.offers_shs is True
    assert second.school.offers_es is True
    assert second.school.offers_jhs is None
    assert second.school.offers_shs is None
    assert "JUAN DELA CRUZ" not in repr(first)


def test_ebeis_school_levels_does_not_guess():
    assert school_levels("Kinder, Grade 1-6") == (True, None, None)
    assert school_levels("Grade 7-10 & Grade 11-12") == (None, True, True)
    assert school_levels("Ungraded special program") == (None, None, None)
    assert school_levels(None) == (None, None, None)
