"""The one source catalogue.

Every acquisition route is declared here once. The CLI, checks, and runner read
this mapping; adding a source does not require editing the CLI or the pipeline.
Adapter modules still own parsing, validation, and normalization.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from ..contracts import ReleaseSpec
from .bir import BirRevenueDistrictOfficeAdapter
from .bucor import BucorFacilityAdapter
from .cainta import CaintaHealthCenterAdapter, fetch_cainta_health_centers
from .ched_heida import ChedHeidaAdapter, fetch_heida_directory
from .connectors.base import SourceConnector, UnavailableConnector
from .connectors.ebeis import EbeisConnector
from .connectors.geography import GeographyConnector, PopulationConnector
from .connectors.osm import OsmParquetConnector, OsmPbfConnector
from .connectors.philhealth import PhilHealthConnector
from .connectors.single_file import SingleFileConnector
from .definitions import (
    GROUP_APPROVED,
    GROUP_SKIPPED,
    SOURCE_GROUPS,
    AccessSpec,
    AgencyRef,
    CheckSpec,
    DatasetRef,
    RightsDecision,
    SourceDefinition,
    publisher_type_for,
)
from .deped_bukas import (
    ARCHIVE_ZIP_URL as DEPED_BUKAS_ARCHIVE_URL,
)
from .deped_bukas import (
    MAX_ZIP_BYTES as DEPED_BUKAS_MAX_BYTES,
)
from .deped_bukas import (
    DepEdBukasEnrollmentAdapter,
    fetch_deped_bukas_enrollment,
)
from .deped_mapaaralan import (
    MAX_BYTES as DEPED_MAPAARALAN_MAX_BYTES,
)
from .deped_mapaaralan import (
    SOURCE_URL as DEPED_MAPAARALAN_URL,
)
from .deped_mapaaralan import (
    DepEdMapaaralanAdapter,
    fetch_deped_mapaaralan,
)
from .deped_masterlist import (
    ARCHIVE_PDF_URL,
    MAX_PDF_BYTES,
    DepEdMasterlistAdapter,
    fetch_deped_masterlist,
)
from .deped_masterlist_detail import (
    BETTERGOV_DATASET_URL,
    KAGGLE_DOWNLOAD_URL,
    DepEdMasterlistDetailAdapter,
    fetch_deped_masterlist_detail,
)
from .deped_shs_arcgis import (
    LAYER_URL as DEPED_SHS_LAYER_URL,
)
from .deped_shs_arcgis import (
    DepEdShsArcgisAdapter,
    fetch_deped_shs_arcgis,
)
from .doe_power import DoePowerPlantAdapter
from .doh_nhfr import (
    MAX_XLSX_BYTES as DOH_NHFR_MAX_BYTES,
)
from .doh_nhfr import (
    MIRROR_XLSX_URL as DOH_NHFR_XLSX_URL,
)
from .doh_nhfr import (
    DohNhfrAdapter,
    fetch_doh_nhfr,
)
from .dswd_crcf import DswdCrcfDirectoryAdapter
from .dti_negosyo import DtiNegosyoCenterAdapter, fetch_negosyo_centers
from .lrta import LrtaStationAdapter, fetch_distance_page
from .mandaluyong import MandaluyongBarangayAdapter, fetch_mandaluyong_directory
from .mrt3 import Mrt3StationAdapter, fetch_mrt3_stations
from .national_museum import NationalMuseumDirectoryAdapter, fetch_national_museum_directory
from .nbi import NbiOfficeAdapter, fetch_nbi_offices
from .nha_wfs import NhaDohFacilityAdapter, NhaHousingProjectAdapter, NhaLandholdingAdapter
from .nlp import NlpPublicLibraryPdfAdapter
from .nmis_naris import NmisNarisDirectoryAdapter
from .osm_facilities import LAYER_FILES
from .pagasa_aws import PagasaAwsAdapter, fetch_pagasa_aws
from .pasay import PasayHealthCenterAdapter, fetch_pasay_health_centers
from .philhealth_offices import PhilHealthOfficeAdapter, fetch_philhealth_offices
from .phlpost import PhlPostLocatorAdapter
from .ppa import PpaPortListAdapter
from .prc import PrcOfficeAdapter
from .quezon_city import QuezonCityLguAdapter, fetch_quezon_city_directory
from .quezon_city_places import QuezonCityPlacesAdapter, fetch_quezon_city_places
from .registry import (
    BETTERGOV_PSGC_URL,
    DTI_NEGOSYO_API_URL,
    EBEIS_URL,
    PHILHEALTH_INDEX_URL,
    REAL_SOURCES,
    RealSource,
)
from .sss_branch import SssBranchAdapter, fetch_sss_branches

MANUAL_ACCESS_METHODS = {
    "human_download",
    "official_registry",
    "official_workbook",
}


def _group_for(source: RealSource) -> str:
    from philfacilities_api.rights import PUBLICATION_BLOCKED

    from ..skip_reasons import skip_for_source

    if (
        source.requested_publication_status == PUBLICATION_BLOCKED
        or source.access_method in MANUAL_ACCESS_METHODS
        or skip_for_source(source.key) is not None
    ):
        return GROUP_SKIPPED
    return GROUP_APPROVED


def definition_from_registry(
    source: RealSource,
    *,
    connector: str,
    check: CheckSpec | None = None,
) -> SourceDefinition:
    publisher_type = publisher_type_for(source.agency_code)
    authority_level = source.authority_level or (
        "community" if publisher_type == "community" else "official"
    )
    return SourceDefinition(
        key=source.key,
        group=_group_for(source),
        agency=AgencyRef(
            code=source.agency_code,
            name=source.agency_name,
            publisher_type=publisher_type,
        ),
        dataset=DatasetRef(
            slug=source.dataset_slug,
            name=source.dataset_name,
            authority_level=authority_level,
            coverage_scope=source.coverage_scope,
            coverage_note=source.coverage_note,
        ),
        rights=RightsDecision(
            status=source.rights,
            basis=source.rights_basis,
            attribution_text=source.attribution_text,
            personal_data_status=source.personal_data_status,
            requested_publication_status=source.requested_publication_status,
            license_identifier=source.license_identifier,
            terms_url=source.terms_url,
        ),
        access=AccessSpec(
            source_url=source.source_url,
            method=source.access_method,
            update_pattern=source.update_pattern,
        ),
        check=check or CheckSpec(),
        connector=connector,
        is_geography=source.is_geography,
        note=source.note,
        minimum_acceptance_rate=source.minimum_acceptance_rate,
        minimum_acceptance_rows=source.minimum_acceptance_rows,
    )


def _single(
    key: str,
    *,
    url: str | None = None,
    fetcher: Callable[..., Any] | None = None,
    adapter: Callable[[ReleaseSpec], Any],
    filename: Callable[[date], str],
    release_label: Callable[[date], str],
    **kwargs: Any,
) -> SingleFileConnector:
    return SingleFileConnector(
        key,
        url=url,
        fetcher=fetcher,
        adapter=adapter,
        filename=filename,
        release_label=release_label,
        **kwargs,
    )


def _dated(prefix: str, suffix: str) -> Callable[[date], str]:
    return lambda today: f"{prefix}-{today.isoformat()}.{suffix}"


def _label(prefix: str) -> Callable[[date], str]:
    return lambda today: f"{prefix}-{today.isoformat()}"


def _fixed(value: str) -> Callable[[date], str]:
    return lambda _today: value


def _build_catalog() -> tuple[dict[str, SourceDefinition], dict[str, SourceConnector]]:
    check_specs: dict[str, CheckSpec] = {
        "psa-psgc": CheckSpec(
            url=("https://psa.gov.ph/system/files/scd/PSGC-3Q-2026-Publication-Datafile.xlsx")
        ),
        "philhealth": CheckSpec(url=PHILHEALTH_INDEX_URL, catalog="philhealth"),
        "deped-ebeis": CheckSpec(
            url=EBEIS_URL,
            method="POST",
            data={"page": "1", "region_id": "13", "user_id": "", "school_head": ""},
            expected_marker="School ID",
        ),
        "deped-masterlist-2020": CheckSpec(
            url=ARCHIVE_PDF_URL,
            expected_marker="%PDF",
        ),
        "deped-masterlist-2020-detail": CheckSpec(
            url=KAGGLE_DOWNLOAD_URL,
            expected_marker="PK",
        ),
        "deped-bukas-enrollment": CheckSpec(
            url=DEPED_BUKAS_ARCHIVE_URL,
            expected_marker="PK",
        ),
        "deped-shs-arcgis": CheckSpec(
            url=f"{DEPED_SHS_LAYER_URL}/query?where=1%3D1&returnCountOnly=true&f=json",
            expected_marker="count",
        ),
        "deped-mapaaralan": CheckSpec(
            url=DEPED_MAPAARALAN_URL,
            expected_marker="latitude",
        ),
        "doh-nhfr": CheckSpec(
            url=DOH_NHFR_XLSX_URL,
            expected_marker="PK",
        ),
        "bettergov-psgc": CheckSpec(url=f"{BETTERGOV_PSGC_URL}/Q2_2024/regions"),
        "nlp": CheckSpec(expected_marker="%PDF"),
        "ppa": CheckSpec(expected_marker="%PDF"),
        "dti-negosyo": CheckSpec(url=DTI_NEGOSYO_API_URL, expected_marker="region"),
        "ched-heida": CheckSpec(expected_marker="HEI Directory"),
        "national-museum": CheckSpec(expected_marker="uk-card"),
        "phlpost": CheckSpec(expected_marker="Post Offices"),
        "dswd-crcf": CheckSpec(expected_marker="Centers and Residential Care Facilities"),
        "nmis-naris": CheckSpec(expected_marker="Accredited Meat Establishments"),
    }
    for key in REAL_SOURCES:
        if key.startswith("osm-"):
            check_specs[key] = CheckSpec(method="HEAD")

    connectors: dict[str, SourceConnector] = {}

    # Reference data -----------------------------------------------------
    connectors["bettergov-psgc"] = GeographyConnector()
    connectors["bettergov-population"] = PopulationConnector()

    # PhilHealth ---------------------------------------------------------
    connectors["philhealth"] = PhilHealthConnector()

    # OSM ----------------------------------------------------------------
    for key in (
        "osm-health",
        "osm-education",
        "osm-points-of-interest",
        "osm-airports",
        "osm-sea-ports",
        "osm-railways",
    ):
        domain = key.removeprefix("osm-")
        if domain not in {"health", "education"} and domain not in LAYER_FILES:
            raise ValueError(f"Unknown OSM layer {domain!r}")
        connectors[key] = OsmParquetConnector(key, domain=domain, url=REAL_SOURCES[key].source_url)
    connectors["osm-pbf-facilities"] = OsmPbfConnector()

    # DepEd --------------------------------------------------------------
    connectors["deped-ebeis"] = EbeisConnector()
    connectors["deped-masterlist-2020"] = _single(
        "deped-masterlist-2020",
        url=REAL_SOURCES["deped-masterlist-2020"].source_url,
        fetcher=fetch_deped_masterlist,
        adapter=DepEdMasterlistAdapter,
        filename=_fixed("deped-masterlist-sy2020-2021.pdf"),
        release_label=_fixed("DEPED-MASTERLIST-SY2020-2021"),
        max_bytes=MAX_PDF_BYTES,
        source_published_at=datetime(2021, 6, 9, tzinfo=UTC),
        reference_period_start=date(2020, 6, 1),
        reference_period_end=date(2021, 1, 15),
        timeout_seconds=180.0,
        notes=(
            "Official DepEd PDF; acquisition falls back to the preserved Wayback "
            "copy when the DepEd host returns HTTP 403."
        ),
    )
    connectors["deped-masterlist-2020-detail"] = _single(
        "deped-masterlist-2020-detail",
        # The declared source is the BetterGov catalogue page. The fetcher uses
        # the public Kaggle mirror and records that acquisition URL in metadata.
        url=BETTERGOV_DATASET_URL,
        fetcher=fetch_deped_masterlist_detail,
        adapter=DepEdMasterlistDetailAdapter,
        filename=_fixed("deped-masterlist-sy2020-2021-detail.zip"),
        release_label=_fixed("DEPED-MASTERLIST-SY2020-2021-DETAIL"),
        max_bytes=20 * 1024 * 1024,
        source_published_at=datetime(2021, 6, 9, tzinfo=UTC),
        reference_period_start=date(2020, 6, 1),
        reference_period_end=date(2021, 1, 15),
        timeout_seconds=120.0,
        notes=(
            "BetterGov Open Data Portal dataset 41 (CC BY 4.0), a machine-readable "
            "transcription of the official DepEd masterlist. The CSV SHA-256 is "
            "pinned; any artifact change is rejected."
        ),
    )
    connectors["deped-bukas-enrollment"] = _single(
        "deped-bukas-enrollment",
        url=REAL_SOURCES["deped-bukas-enrollment"].source_url,
        fetcher=fetch_deped_bukas_enrollment,
        adapter=DepEdBukasEnrollmentAdapter,
        filename=_fixed("deped-project-bukas-enrollment-sy2024-2025.zip"),
        release_label=_fixed("DEPED-PROJECT-BUKAS-ENROLLMENT-SY2024-2025"),
        max_bytes=DEPED_BUKAS_MAX_BYTES,
        source_published_at=None,
        reference_period_start=date(2024, 6, 1),
        reference_period_end=date(2025, 3, 31),
        timeout_seconds=180.0,
        notes=(
            "Official DepEd Project Bukas enrollment module, SY 2024-2025. The "
            "official deped.gov.ph URL returns HTTP 403 to automated clients; "
            "acquisition falls back to the preserved Wayback ZIP and verifies its "
            "pinned SHA-256. No coordinates or PSGC codes are present."
        ),
    )

    connectors["deped-shs-arcgis"] = _single(
        "deped-shs-arcgis",
        url=REAL_SOURCES["deped-shs-arcgis"].source_url,
        fetcher=fetch_deped_shs_arcgis,
        adapter=DepEdShsArcgisAdapter,
        filename=_dated("deped-shs-arcgis", "json"),
        release_label=_label("DEPED-SHS-ARCGIS"),
        max_bytes=16 * 1024 * 1024,
        source_published_at=None,
        reference_period_start=None,
        reference_period_end=None,
        timeout_seconds=180.0,
        notes=(
            "Public CHED GIS feature service containing the DepEd Senior High "
            "School point layer. The connector pages through the feature service, "
            "verifies the reported feature count, and excludes the G11/G12 "
            "enrollment columns. No reference school year is published."
        ),
    )

    connectors["deped-mapaaralan"] = _single(
        "deped-mapaaralan",
        url=DEPED_MAPAARALAN_URL,
        fetcher=fetch_deped_mapaaralan,
        adapter=DepEdMapaaralanAdapter,
        filename=_fixed("deped-mapaaralan-2019-osmph.tsv"),
        release_label=_fixed("DEPED-MAPAARALAN-2019-OSMPH"),
        max_bytes=DEPED_MAPAARALAN_MAX_BYTES,
        source_published_at=None,
        reference_period_start=date(2019, 1, 1),
        reference_period_end=date(2019, 12, 31),
        timeout_seconds=120.0,
        notes=(
            "Pinned OSMPH copy of the DepEd MaPaaralan 2019 school points. The "
            "connector rejects any SHA-256 change. Rows link only to existing "
            "facilities by exact six-digit school ID and fill a missing point; "
            "they never create or rename a facility."
        ),
    )

    # DOH ----------------------------------------------------------------
    connectors["doh-nhfr"] = _single(
        "doh-nhfr",
        url=REAL_SOURCES["doh-nhfr"].source_url,
        fetcher=fetch_doh_nhfr,
        adapter=DohNhfrAdapter,
        filename=_fixed("doh-nhfr-2026-09.xlsx"),
        release_label=_fixed("DOH-NHFR-2026-09"),
        max_bytes=DOH_NHFR_MAX_BYTES,
        # The export states only "as of September 2026"; no official publication
        # day is given, so the publication timestamp stays null rather than
        # inventing month-end precision.
        source_published_at=None,
        reference_period_start=date(2026, 9, 1),
        reference_period_end=date(2026, 9, 30),
        timeout_seconds=180.0,
        notes=(
            "Official NHFR XLSX export. The official site returns HTTP 403 to "
            "automated clients; acquisition reads the preserved public copy of the "
            "same export and verifies its pinned SHA-256."
        ),
    )

    # Single-artifact sources -------------------------------------------
    connectors["philhealth-offices"] = _single(
        "philhealth-offices",
        url=REAL_SOURCES["philhealth-offices"].source_url,
        fetcher=fetch_philhealth_offices,
        adapter=PhilHealthOfficeAdapter,
        filename=_dated("philhealth-office-directory", "json"),
        release_label=_label("PHILHEALTH-OFFICES"),
        timeout_seconds=120.0,
        input_notes=(
            "Controlled import of a preserved public PhilHealth office-directory artifact."
        ),
        notes=lambda metadata: f"Acquisition metadata: {metadata}",
    )

    connectors["ched-heida"] = _single(
        "ched-heida",
        url=REAL_SOURCES["ched-heida"].source_url,
        fetcher=fetch_heida_directory,
        adapter=ChedHeidaAdapter,
        filename=_dated("ched-heida-hei-directory", "json"),
        release_label=_label("CHED-HEIDA"),
        timeout_seconds=120.0,
        input_notes="Controlled import of a preserved public CHED HEIDA JSON artifact.",
        notes=lambda metadata: f"Acquisition metadata: {metadata}",
    )

    connectors["nlp"] = _single(
        "nlp",
        url=REAL_SOURCES["nlp"].source_url,
        adapter=NlpPublicLibraryPdfAdapter,
        filename=_fixed("nlp-public-libraries-2025-12.pdf"),
        release_label=_fixed("NLP-PUBLIC-LIBRARIES-2025-12"),
        max_bytes=100 * 1024 * 1024,
        reference_period_start=date(2025, 12, 1),
        reference_period_end=date(2025, 12, 31),
        timeout_seconds=180.0,
        notes=(
            "NLP Integrated Directory of Public Libraries, December 2025 edition. "
            "Institutional fields published with attribution; librarian contact fields "
            "are not published."
        ),
    )

    connectors["national-museum"] = _single(
        "national-museum",
        url=REAL_SOURCES["national-museum"].source_url,
        fetcher=fetch_national_museum_directory,
        adapter=NationalMuseumDirectoryAdapter,
        filename=_dated("nmp-regional-area-site-museums", "json"),
        release_label=_label("NMP-MUSEUMS"),
        timeout_seconds=120.0,
        notes=lambda metadata: (
            f"Acquisition artifact: {metadata.get('museums')} museum cards, "
            f"{metadata.get('detail_pages_fetched')} detail pages fetched. "
            "Postal addresses only; no coordinates were added."
        ),
    )

    connectors["phlpost"] = _single(
        "phlpost",
        url=REAL_SOURCES["phlpost"].source_url,
        adapter=PhlPostLocatorAdapter,
        filename=_dated("phlpost-post-office-locator", "html"),
        release_label=_label("PHLPOST-LOCATOR"),
        timeout_seconds=120.0,
        notes=(
            "PHLPost public locator table. Stored internal-only because the publisher "
            "displays an explicit copyright/all-rights-reserved notice."
        ),
    )

    connectors["bir"] = _single(
        "bir",
        url=REAL_SOURCES["bir"].source_url,
        adapter=BirRevenueDistrictOfficeAdapter,
        filename=_fixed("bir-rao-006-2025.pdf"),
        release_label=_fixed("BIR-RAO-006-2025"),
        max_bytes=50 * 1024 * 1024,
        reference_period_start=date(2025, 12, 9),
        reference_period_end=date(2025, 12, 9),
        timeout_seconds=180.0,
        notes=(
            "Official scanned RAO No. 006-2025. Local OCR recovered the Revenue "
            "Region/RDO list; no addresses or coordinates were inferred."
        ),
    )

    connectors["dswd-crcf"] = _single(
        "dswd-crcf",
        url=REAL_SOURCES["dswd-crcf"].source_url,
        adapter=DswdCrcfDirectoryAdapter,
        filename=_dated("dswd-crcf-directory", "html"),
        release_label=_label("DSWD-CRCF"),
        timeout_seconds=120.0,
        notes=(
            "DSWD CRCF public directory. Desktop and mobile accordion layouts are "
            "deduplicated by facility name and address; postal addresses only."
        ),
    )

    for key, label_prefix, adapter in (
        ("quezon-city", "QC-LGU-DIRECTORY", QuezonCityLguAdapter),
        ("quezon-city-places", "QC-LGU-PLACES", QuezonCityPlacesAdapter),
        ("mandaluyong", "MANDALUYONG-LGU", MandaluyongBarangayAdapter),
        ("cainta-health", "CAINTA-HEALTH", CaintaHealthCenterAdapter),
        ("pasay-health", "PASAY-HEALTH", PasayHealthCenterAdapter),
    ):
        fetchers = {
            "quezon-city": fetch_quezon_city_directory,
            "quezon-city-places": fetch_quezon_city_places,
            "mandaluyong": fetch_mandaluyong_directory,
            "cainta-health": fetch_cainta_health_centers,
            "pasay-health": fetch_pasay_health_centers,
        }
        filenames = {
            "quezon-city": "quezon-city-lgu-directory",
            "quezon-city-places": "quezon-city-lgu-places",
            "mandaluyong": "mandaluyong-lgu-barangay-directory",
            "cainta-health": "cainta-lgu-health-centers",
            "pasay-health": "pasay-lgu-health-centers",
        }
        connectors[key] = _single(
            key,
            url=REAL_SOURCES[key].source_url,
            fetcher=fetchers[key],
            adapter=adapter,
            filename=_dated(filenames[key], "json"),
            release_label=_label(label_prefix),
            timeout_seconds=120.0,
            notes=lambda metadata: f"Acquisition metadata: {metadata}",
        )

    connectors["nmis-naris"] = _single(
        "nmis-naris",
        url=REAL_SOURCES["nmis-naris"].source_url,
        adapter=NmisNarisDirectoryAdapter,
        filename=_dated("nmis-naris-accredited-establishments", "html"),
        release_label=_label("NMIS-NARIS"),
        timeout_seconds=120.0,
        input_notes=(
            "Controlled import of a preserved public NARIS directory artifact. The live "
            "endpoint returned a WAF challenge or TLS failure on recheck; the artifact is "
            "the release of record."
        ),
        notes=(
            "Public NARIS accredited-establishment directory. Duplicate LTO rows are "
            "grouped; no validity dates or operating status are inferred."
        ),
    )

    connectors["ppa"] = _single(
        "ppa",
        url=REAL_SOURCES["ppa"].source_url,
        adapter=PpaPortListAdapter,
        filename=_dated("ppa-port-list", "pdf"),
        release_label=_label("PPA-PORT-LIST"),
        max_bytes=50 * 1024 * 1024,
        timeout_seconds=120.0,
        input_notes=(
            "Controlled import of the preserved public PPA port-list PDF. Source "
            "hierarchy, RORO/NON-RORO marks and remarks are preserved."
        ),
        notes=(
            "PPA List of Ports Covered in PPA Statistics. Base, TMO/OTP, other government "
            "and private ports remain separate. No coordinates, owners, public access or "
            "operational status were inferred."
        ),
    )

    connectors["dti-negosyo"] = _single(
        "dti-negosyo",
        url=REAL_SOURCES["dti-negosyo"].source_url,
        fetcher=fetch_negosyo_centers,
        adapter=DtiNegosyoCenterAdapter,
        filename=_dated("dti-negosyo-centers", "json"),
        release_label=_label("DTI-NEGOSYO"),
        timeout_seconds=120.0,
        input_notes=("Controlled import of a preserved public DTI Negosyo Center JSON artifact."),
        notes=lambda metadata: f"Acquisition metadata: {metadata}",
    )

    for key, adapter, filename, label, fetcher in (
        (
            "sss-branches",
            SssBranchAdapter,
            "sss-branch-locator",
            "SSS-BRANCHES",
            fetch_sss_branches,
        ),
        (
            "pagasa-aws",
            PagasaAwsAdapter,
            "pagasa-automated-weather-stations",
            "PAGASA-AWS",
            fetch_pagasa_aws,
        ),
        (
            "nbi-offices",
            NbiOfficeAdapter,
            "nbi-regional-district-offices",
            "NBI-OFFICES",
            fetch_nbi_offices,
        ),
    ):
        connectors[key] = _single(
            key,
            url=REAL_SOURCES[key].source_url,
            fetcher=fetcher,
            adapter=adapter,
            filename=_dated(filename, "json"),
            release_label=_label(label),
            timeout_seconds=120.0,
            notes=lambda metadata: f"Acquisition metadata: {metadata}",
        )

    for key, adapter, prefix, filename in (
        ("nha-doh-hf", NhaDohFacilityAdapter, "NHA-DOH-HF", "nha-doh-hf"),
        (
            "nha-housing-projects",
            NhaHousingProjectAdapter,
            "NHA-PROJECTS",
            "nha-housing-projects",
        ),
        ("nha-landholdings", NhaLandholdingAdapter, "NHA-LANDHOLDINGS", "nha-landholdings"),
    ):
        connectors[key] = _single(
            key,
            url=REAL_SOURCES[key].source_url,
            adapter=adapter,
            filename=_dated(filename, "geojson"),
            release_label=_label(prefix),
            timeout_seconds=180.0,
            input_notes="Controlled import of a preserved NHA WFS GeoJSON artifact.",
            notes=lambda _metadata: "NHA WFS GeoJSON; source geometry retained as published.",
        )

    doe_layers = {
        "doe-power-luzon": ("Luzon", "DOE-LOEPP-LUZON", date(2026, 9, 30)),
        "doe-power-visayas": ("Visayas", "DOE-LOEPP-VISAYAS", date(2026, 9, 30)),
        "doe-power-mindanao": ("Mindanao", "DOE-LOEPP-MINDANAO", date(2026, 9, 30)),
        "doe-power-offgrid": ("Off-grid", "DOE-LOEPP-OFFGRID", date(2026, 4, 30)),
    }
    for key, (grid, prefix, reference_end) in doe_layers.items():
        connectors[key] = _single(
            key,
            url=REAL_SOURCES[key].source_url,
            adapter=lambda spec, grid=grid: DoePowerPlantAdapter(spec, grid=grid),
            filename=_fixed(f"{key}-{reference_end.isoformat()}.pdf"),
            release_label=_fixed(f"{prefix}-{reference_end.isoformat()}"),
            reference_period_end=reference_end,
            timeout_seconds=180.0,
            input_notes="Controlled import of a preserved DOE LoEPP PDF artifact.",
            notes=lambda _metadata: (
                "DOE LoEPP existing-power-plant registry list; no operating status, "
                "coordinates or legal-ownership conclusion is inferred."
            ),
        )

    for key, adapter, prefix, filename, fetcher in (
        (
            "lrta-stations",
            LrtaStationAdapter,
            "LRTA-STATIONS",
            "lrta-distance-stations",
            fetch_distance_page,
        ),
        (
            "mrt3-stations",
            Mrt3StationAdapter,
            "MRT3-STATIONS",
            "mrt3-stations",
            fetch_mrt3_stations,
        ),
    ):
        connectors[key] = _single(
            key,
            url=REAL_SOURCES[key].source_url,
            fetcher=fetcher,
            adapter=adapter,
            filename=_dated(filename, "html"),
            release_label=_label(prefix),
            timeout_seconds=60.0,
            notes=lambda metadata: f"Acquisition metadata: {metadata}",
        )

    connectors["bucor-oppf"] = _single(
        "bucor-oppf",
        url=REAL_SOURCES["bucor-oppf"].source_url,
        adapter=BucorFacilityAdapter,
        filename=_dated("bucor-oppf", "html"),
        release_label=_label("BUCOR-OPPF"),
        timeout_seconds=60.0,
        input_notes="Controlled import of a preserved BuCor OPPF HTML artifact.",
        notes=(
            "BuCor OPPF seven-facility directory subset. Only facility names and official "
            "detail-page links are published; no address, coordinate, capacity or operating "
            "status is present or inferred."
        ),
    )

    connectors["prc-offices"] = _single(
        "prc-offices",
        url=REAL_SOURCES["prc-offices"].source_url,
        adapter=PrcOfficeAdapter,
        filename=_dated("prc-offices", "html"),
        release_label=_label("PRC-OFFICES"),
        timeout_seconds=60.0,
        input_notes="Controlled import of a preserved PRC office-locator HTML artifact.",
        notes=(
            "PRC regional-office locator subset. Embedded map pins are map_geocoded, not "
            "surveyed building locations; no PSGC code or operating status is inferred."
        ),
    )

    # Blocked or human-assisted sources ---------------------------------
    unavailable = {
        "psa-psgc": (
            "The official PSA PSGC workbook is behind an access block and has no "
            "documented reuse decision. Use the BetterGov mirror or supply an authorised "
            "workbook through a documented process."
        ),
        "deped-machine-ready": (
            "DepEd machine-ready files require a human download and a documented rights "
            "decision; no automated connector is configured."
        ),
        "tesda-tvi": (
            "The TESDA TVI directory has no verified access or reuse decision; no "
            "automated connector is configured."
        ),
    }
    for key, reason in unavailable.items():
        connectors[key] = UnavailableConnector(key, reason)

    definitions = {
        key: definition_from_registry(
            source,
            connector=type(connectors.get(key, UnavailableConnector(key, ""))).__name__,
            check=check_specs.get(key),
        )
        for key, source in REAL_SOURCES.items()
    }
    return definitions, connectors


SOURCES, CONNECTORS = _build_catalog()
CONNECTOR_NAMES = {key: _definition.connector for key, _definition in SOURCES.items()}


def get_definition(key: str) -> SourceDefinition:
    try:
        return SOURCES[key]
    except KeyError as exc:
        raise KeyError(f"Unknown source key {key!r}") from exc


def get_connector(key: str) -> SourceConnector:
    try:
        return CONNECTORS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown source key {key!r}") from exc


def select_keys(
    keys: list[str] | tuple[str, ...] | None = None,
    *,
    group: str | None = None,
    exclude: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    if group is not None and group not in SOURCE_GROUPS:
        raise ValueError(f"Unknown source group {group!r}; choose from {SOURCE_GROUPS}")
    selected = list(keys) if keys else list(SOURCES)
    unknown = [key for key in selected if key not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source key(s): {', '.join(sorted(unknown))}")
    if group is not None:
        selected = [key for key in selected if SOURCES[key].group == group]
    excluded = set(exclude or ())
    unknown_excluded = [key for key in excluded if key not in SOURCES]
    if unknown_excluded:
        raise ValueError(f"Unknown excluded source key(s): {', '.join(sorted(unknown_excluded))}")
    return [key for key in selected if key not in excluded]


def catalog_rows() -> list[dict[str, Any]]:
    return [SOURCES[key].to_dict() for key in sorted(SOURCES)]
