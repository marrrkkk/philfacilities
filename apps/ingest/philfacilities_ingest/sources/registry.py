"""Real source registry, discovery, and acquisition orchestration.

This module is the single place that records what a real connector is allowed to
do. It contains no parsing logic of its own; it wires the shared acquisition
client to the source-specific adapters and refuses to fake a release when a
source is blocked, changed shape, or has no publication permission.

Every source defined here carries its actual rights evidence. A source with
``review_required`` or ``restricted_non_redistributable`` rights is still checked
and may be stored privately, but its records are never published by the API.
"""

from __future__ import annotations

import html
import re
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from philfacilities_api.models import Dataset, SourceCheck
from philfacilities_api.rights import (
    PUBLICATION_APPROVED,
    PUBLICATION_BLOCKED,
    PUBLICATION_INTERNAL_ONLY,
    RIGHTS_APPROVED_ATTRIBUTION,
    RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
    RIGHTS_REVIEW_REQUIRED,
    normalize_rights,
    rights_allow_public,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..acquisition import (
    AcquisitionError,
    FetchResult,
    HttpAcquirer,
    is_blocker_page,
)
from ..contracts import (
    DEFAULT_MINIMUM_ACCEPTANCE_RATE,
    DEFAULT_MINIMUM_ACCEPTANCE_ROWS,
    ReleaseSpec,
)
from ..pipeline import ensure_source
from .bettergov import build_psgc_release_payload, parse_psgc_api_payload
from .deped_ebeis import parse_masterlist_html
from .philhealth import PhilHealthCatalogEntry, parse_catalog

# ---------------------------------------------------------------------------
# Rights evidence
# ---------------------------------------------------------------------------

PHILHEALTH_INDEX_URL = "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/"
EBEIS_MASTERLIST_URL = "https://ebeis.deped.gov.ph/beis/reports_info/masterlist"
PHILHEALTH_RIGHTS_BASIS = (
    "PhilHealth's published site disclaimer states that its information may be used "
    "for educational or informative purposes and may be reproduced, copied or "
    "downloaded without written permission from PhilHealth. This is a terms-based "
    "publication decision, not a completed legal review; attribution is retained."
)
PHILHEALTH_ATTRIBUTION = (
    "Philippine Health Insurance Corporation (PhilHealth) — Accredited Healthcare "
    "Facilities directory"
)
PHILHEALTH_OFFICE_DIRECTORY_URL = "https://www.philhealth.gov.ph/about_us/directory/"
PHILHEALTH_OFFICE_RIGHTS_BASIS = (
    "The PhilHealth Directory of Offices is a public information page of the Philippine "
    "Health Insurance Corporation, a government-owned and controlled corporation. "
    "PhilHealth's published site disclaimer states that its information may be used for "
    "educational or informative purposes and may be reproduced, copied or downloaded "
    "without written permission from PhilHealth. PhilFacilities publishes only the "
    "institutional office name, source category, region grouping and postal address with "
    "attribution. Telephone numbers, e-mail addresses and schedule text are withheld from "
    "the public record and retained only in the private preserved artifact. This is a "
    "terms-based publication decision, not a completed legal review."
)
PHILHEALTH_OFFICE_ATTRIBUTION = (
    "Philippine Health Insurance Corporation (PhilHealth) — Directory of Offices"
)
BETTERGOV_PSGC_URL = "https://statistics.bettergov.ph/api/classification/psgc"
BETTERGOV_PSGC_RIGHTS_BASIS = (
    "BetterGov.PH publishes the classification API under CC BY-SA 4.0. The snapshot "
    "mirrors PSA PSGC Q2 2024; it is supplementary and is not the latest official PSA "
    "workbook. Attribution is retained and adaptations share the same licence."
)
BETTERGOV_PSGC_ATTRIBUTION = (
    "BetterGov.PH Classification API (CC BY-SA 4.0), derived from PSA PSGC Q2 2024"
)
BETTERGOV_STATISTICS_URL = "https://statistics.bettergov.ph/api"
BETTERGOV_POPULATION_RIGHTS_BASIS = (
    "BetterGov.PH publishes the Philippine Data Explorer's original material under "
    "CC BY-SA 4.0. The population values are saved PSA OpenSTAT snapshots reproduced "
    "without aggregation; PSA remains the authoritative source. BetterGov.PH states "
    "that its preview does not itself establish redistribution rights, so this "
    "publication decision relies on the CC BY-SA 4.0 licence for the compilation and "
    "retains the PSA table URL, release identifier and attribution. No new PSA terms "
    "review is claimed."
)
BETTERGOV_POPULATION_ATTRIBUTION = (
    "BetterGov.PH Philippine Data Explorer (CC BY-SA 4.0), sourced from PSA OpenSTAT; "
    "Philippine Statistics Authority remains the authoritative source"
)
OSM_RIGHTS_BASIS = (
    "OpenStreetMap data is made available under the Open Database License (ODbL) "
    "1.0. Attribution to OpenStreetMap contributors and the HOT/BetterGov extract is "
    "required; derivative databases remain share-alike."
)
OSM_ATTRIBUTION = "© OpenStreetMap contributors, via HOT and BetterGov.PH"
DEPED_EBEIS_RIGHTS_BASIS = (
    "The EBEIS masterlist is a public result set of the Department of Education, a "
    "government agency. RA 8293 section 176 provides that no copyright subsists in a "
    "work of the Government of the Philippines, while prior approval may be required "
    "for commercial use. PhilFacilities publishes institution-level school fields with "
    "attribution for non-commercial public-interest use. School-head names and other "
    "personal fields remain in the private source store and are not exposed by the "
    "public API. This is a documented publication decision, not a legal opinion."
)
OFFICIAL_BLOCKED_BASIS = (
    "The official endpoint was reachable only through a human terms/access flow or "
    "returned an access-control challenge. No redistribution decision exists; the "
    "dataset remains blocked."
)
NLP_LIBRARIES_URL = (
    "https://web.nlp.gov.ph/wp-content/uploads/2026/01/"
    "OFFICIAL-Integrated-Directory-of-Public-Libraries-as-of-December-2025.pdf"
)
NLP_RIGHTS_BASIS = (
    "The directory is a work of the Government of the Philippines. RA 8293 section 176 "
    "provides that no copyright subsists in a government work, while prior approval may "
    "be required for commercial use. PhilFacilities publishes the institutional library "
    "fields with attribution for non-commercial public-interest use and excludes personal "
    "librarian contact fields. This is a documented publication decision, not a legal "
    "opinion."
)
NLP_ATTRIBUTION = (
    "National Library of the Philippines, Public Libraries Division — Directory of "
    "Affiliated Public Libraries in the Philippines, December 2025"
)
NATIONAL_MUSEUM_URL = (
    "https://www.nationalmuseum.gov.ph/our-museums/regional-area-and-site-museums/"
)
NATIONAL_MUSEUM_RIGHTS_BASIS = (
    "The National Museum directory and site pages are works of the Government of the "
    "Philippines. RA 8293 section 176 provides that no copyright subsists in a government "
    "work, while prior approval may be required for commercial use. PhilFacilities "
    "publishes institutional museum fields with attribution for non-commercial "
    "public-interest use. This is a documented publication decision, not a legal opinion."
)
NATIONAL_MUSEUM_ATTRIBUTION = (
    "National Museum of the Philippines — Regional, Area and Site Museums directory"
)
PHLPOST_URL = "https://phlpost.gov.ph/post-office-locator/"
PHLPOST_RIGHTS_BASIS = (
    "PHLPost is a government-owned and controlled corporation. Its public locator page "
    "carries an explicit copyright/all-rights-reserved notice. Under the product owner's "
    "public-record inclusion decision, PhilFacilities publishes only the factual locator "
    "fields needed for facility discovery (office name, province, address and listed "
    "services) with attribution, and does not republish the page's expressive content. "
    "This is a documented product decision, not a legal opinion; the source notice and a "
    "takedown route remain recorded."
)
BIR_RAO_URL = "https://bir-cdn.bir.gov.ph/BIR/pdf/RAO%20No.%206-2025.pdf"
BIR_RIGHTS_BASIS = (
    "RAO No. 006-2025 is an official issuance of the Bureau of Internal Revenue, a "
    "government agency. RA 8293 section 176 provides that no copyright subsists in a "
    "work of the Government of the Philippines, while prior approval may be required "
    "for commercial use. PhilFacilities publishes the institutional office list with "
    "attribution for non-commercial public-interest use. The PDF is image-only; OCR "
    "recovered text is stored alongside the original file and is not treated as a "
    "replacement for the official document. This is a documented publication decision, "
    "not a legal opinion."
)
BIR_ATTRIBUTION = (
    "Bureau of Internal Revenue — Revenue Administrative Order No. 006-2025, "
    "List of Revenue Regions and Revenue District Offices (9 December 2025)"
)
DSWD_CRCF_URL = "https://www.dswd.gov.ph/crcf/"
DSWD_CRCF_RIGHTS_BASIS = (
    "The DSWD Centers and Residential Care Facilities directory is a work of the "
    "Department of Social Welfare and Development, a government agency. RA 8293 "
    "section 176 provides that no copyright subsists in a work of the Government of "
    "the Philippines, while prior approval may be required for commercial use. "
    "PhilFacilities publishes institutional facility name, responsible field office "
    "and postal address with attribution for non-commercial public-interest use. No "
    "coordinates, admission rules or operational status are inferred. This is a "
    "documented publication decision, not a legal opinion."
)
DSWD_CRCF_ATTRIBUTION = (
    "Department of Social Welfare and Development — Centers and Residential Care "
    "Facilities (CRCF) directory"
)
SSS_BRANCH_LOCATOR_URL = "https://www.sss.gov.ph/sss-branch-locator/"
SSS_RIGHTS_BASIS = (
    "The SSS branch locator is a public directory published by the Social Security "
    "System, a government-owned and controlled corporation. No explicit prohibition, "
    "access control or terms-of-use restriction was found on the locator or its JSON "
    "endpoints. RA 8293 section 176 provides that no copyright subsists in a work of "
    "the Government of the Philippines, while prior approval may be required for "
    "commercial use. PhilFacilities publishes the factual branch name, postal address "
    "and region for non-commercial public-interest use with attribution and "
    "takedown-on-notice. Contact-person names, e-mail addresses and telephone/fax "
    "strings remain in the private preserved artifact and are not exposed. This is a "
    "documented publication decision, not a legal opinion."
)
SSS_ATTRIBUTION = "Social Security System — SSS Branch Locator"
PAGASA_AWS_URL = "https://bagong.pagasa.dost.gov.ph/automated-weather-station"
PAGASA_AWS_RIGHTS_BASIS = (
    "The PAGASA automated-weather-station page is a public information service of the "
    "Philippine Atmospheric, Geophysical and Astronomical Services Administration, a "
    "government agency under DOST. No explicit prohibition or access control was found "
    "on the page. RA 8293 section 176 provides that no copyright subsists in a work of "
    "the Government of the Philippines, while prior approval may be required for "
    "commercial use. PhilFacilities publishes only the factual station identity (site "
    "ID, site name and source last-updated value) with attribution for non-commercial "
    "public-interest use. The live readings are preserved in the private release "
    "artifact as acquisition evidence and are not presented as a real-time service or "
    "as current weather. No coordinates are present in the source. This is a documented "
    "publication decision, not a legal opinion."
)
PAGASA_AWS_ATTRIBUTION = (
    "Philippine Atmospheric, Geophysical and Astronomical Services Administration "
    "(PAGASA) — Automated Weather Station network"
)
NBI_OFFICES_URL = "https://nbi.gov.ph/regional-district-offices/"
NBI_RIGHTS_BASIS = (
    "The NBI Regional & District Offices page is a public directory published by the "
    "National Bureau of Investigation, an agency under the Department of Justice. The "
    "page footer states that all content is in the public domain unless otherwise "
    "stated. PhilFacilities publishes only the factual office name, region, postal "
    "location and map-embed coordinates with attribution. Regional director/agent-in-"
    "charge names, telephone numbers and protected e-mail values are personal or "
    "contact data and are retained only in the private source artifact. Map coordinates "
    "are approximate and are not presented as field-verified building coordinates. This "
    "is a documented publication decision, not a legal opinion."
)
NBI_ATTRIBUTION = "National Bureau of Investigation — Regional & District Offices"
NHA_DOH_HF_URL = (
    "https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=NHA_PH:DOH%20HF&outputFormat=application/json"
)
NHA_PROJECT_URL = (
    "https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=NHA_PH:NHA_Project_Loc&outputFormat=application/json"
)
NHA_LANDHOLDINGS_URL = (
    "https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=NHA_PH:NHA%20LANDHOLDINGS&outputFormat=application/json"
)
NHA_RIGHTS_BASIS = (
    "The National Housing Authority publishes this GeoServer WFS layer on a public, "
    "unauthenticated endpoint. No explicit prohibition, login, form or licence gate was "
    "found on the endpoint or the NHA site. Under the product owner's public-record "
    "inclusion decision, PhilFacilities publishes the institutional facility fields with "
    "provenance and attribution, and records a takedown-on-notice route. This is a "
    "documented publication decision, not a legal opinion; the layer is labelled a "
    "partial alternate route for the blocked DOH NHFR, not the official registry."
)
NHA_ATTRIBUTION = (
    "National Housing Authority — NHA_PH GeoServer, 'DOH HF' layer (accessed 16 November "
    "2026); an official but partial alternate route for the DOH National Health Facility "
    "Registry"
)
LRTA_DISTANCE_URL = "https://www.lrta.gov.ph/distance-between-stations/"
LRTA_RIGHTS_BASIS = (
    "The Light Rail Transit Authority is a government-owned and controlled corporation. "
    "Its public Distance Between Stations page is an official government work. RA 8293 "
    "section 176 provides that no copyright subsists in a work of the Government of the "
    "Philippines, while prior approval may be required for commercial use. PhilFacilities "
    "publishes the derived station names and interval distances with attribution for "
    "non-commercial public-interest use. The page is not a complete station inventory and "
    "supplies no coordinates, opening dates or operating status."
)
LRTA_ATTRIBUTION = (
    "Light Rail Transit Authority — Distance Between Stations, Line 1 and Line 2 "
    "(page modified 15 October 2026)"
)
MRT3_STATIONS_URL = "https://www.mrt3.com/index.php/menu-stations"
MRT3_RIGHTS_BASIS = (
    "The MRT-3 official site publishes its station carousel as a public information "
    "service for a government-owned rail line. The page names 13 stations and gives "
    "landmark descriptions, but is not dated as a current station inventory and carries "
    "older station labels. PhilFacilities publishes the station names with attribution "
    "for non-commercial public-interest use and preserves the source labels; no "
    "coordinates, addresses, fares, opening dates or operating status are inferred."
)
MRT3_ATTRIBUTION = "Metro Rail Transit Line 3 — MRT-3 Stations (official site)"
BUCOR_OPPF_URL = "https://bucor.gov.ph/?page_id=303"
BUCOR_RIGHTS_BASIS = (
    "The Bureau of Corrections publishes the OPPF facilities page as a public "
    "information service. The site footer states that all content is in the public "
    "domain unless otherwise stated. PhilFacilities publishes only the facility name "
    "and the official detail-page link. No addresses, coordinates, population, "
    "security arrangements or personal data are extracted. The page is a seven-"
    "facility directory subset, not a national corrections register."
)
BUCOR_ATTRIBUTION = "Bureau of Corrections — OPPF facilities"
PRC_LOCATOR_URL = "https://info.prc.gov.ph/prc-office-locator/regional-offices"
PRC_RIGHTS_BASIS = (
    "The Professional Regulation Commission publishes its office locator as a public "
    "information service on an official government subdomain. The page supplies "
    "office names, short address labels and embedded map pins. No login, form, "
    "licence gate or explicit prohibition was found. RA 8293 section 176 provides "
    "that no copyright subsists in a work of the Government of the Philippines, "
    "while prior approval may be required for commercial use. PhilFacilities "
    "publishes the factual office name, address label and map-pin coordinates with "
    "attribution for non-commercial public-interest use. The page is a regional-"
    "office directory subset, not a complete service-counter inventory, and the map "
    "pin is not a surveyed building location."
)
PRC_ATTRIBUTION = (
    "Professional Regulation Commission — Office Locator, Regional Offices "
    "(accessed 16 November 2026)"
)
DOE_LOEPP_RIGHTS_BASIS = (
    "The Department of Energy publishes dated 'List of Existing Power Plants' PDFs "
    "through its official website and public media endpoint. No login, form, licence "
    "gate or explicit prohibition was found on the list page or the linked files. "
    "RA 8293 section 176 provides that no copyright subsists in a work of the "
    "Government of the Philippines, while prior approval may be required for "
    "commercial use. PhilFacilities publishes the factual facility name, DOE code, "
    "resource/technology, capacity, location labels, operator/owner labels and "
    "commissioning date with attribution for non-commercial public-interest use. "
    "Inclusion in the list is registry evidence only and is not an operating-status "
    "claim. No coordinates, PSGC codes or legal-ownership conclusions are inferred."
)
DOE_LOEPP_ATTRIBUTION = (
    "Department of Energy — List of Existing Power Plants (grid-connected Luzon, "
    "Visayas and Mindanao as of 30 September 2026; off-grid as of 30 April 2026)"
)
NMIS_NARIS_URL = "https://naris.nmis.gov.ph/"
NMIS_NARIS_RIGHTS_BASIS = (
    "NARIS is the National Meat Inspection Service's public accreditation directory. "
    "The page carries an 'All rights reserved' notice but publishes factual "
    "establishment name, LTO number, establishment type and postal address. Under "
    "docs/14 and ADR 0008, PhilFacilities publishes only those factual fields with "
    "attribution and takedown-on-notice; it does not copy expressive page content and "
    "does not treat the notice as an automatic bar. The page currently returns a WAF "
    "challenge or TLS failure on recheck, so the verified 15 November 2026 artifact is "
    "the release of record. This is a documented product decision, not a legal opinion."
)
NMIS_NARIS_ATTRIBUTION = "National Meat Inspection Service — NARIS Accredited Meat Establishments"
QUEZON_CITY_DIRECTORY_URL = "https://quezoncity.gov.ph/qc-barangays/"
QUEZON_CITY_RIGHTS_BASIS = (
    "The Quezon City Government, a local government unit, publishes its health-centre "
    "and barangay directories as public web pages. No explicit prohibition, access "
    "control or terms-of-use restriction was found on the inspected pages. RA 8293 "
    "section 176 provides that no copyright subsists in a work of the Government of the "
    "Philippines, while prior approval may be required for commercial use. "
    "PhilFacilities publishes only reviewed institutional fields (facility or barangay "
    "name, category, postal address, district and, where the LGU itself publishes a "
    "Google Maps place link, map-geocoded coordinates) for non-commercial "
    "public-interest use with attribution and takedown-on-notice. Health-centre "
    "telephone numbers, barangay officials, e-mail addresses and social-media links are "
    "withheld. COVID-19 swab-testing designations, administrative health offices and "
    "barangay pages without explicit Barangay Hall evidence are not converted into "
    "facility records. This is a documented publication decision, not a legal opinion."
)
QUEZON_CITY_ATTRIBUTION = "Quezon City Government — Health Center directory and Barangay Directory"
QUEZON_CITY_PLACES_URL = "https://quezoncity.gov.ph/places/"
QUEZON_CITY_PLACES_RIGHTS_BASIS = (
    "The Quezon City Government publishes its Places to Visit directory as public web "
    "pages and exposes the same public place entries through its search endpoint. No "
    "explicit prohibition, access control or terms-of-use restriction was found on the "
    "inspected pages. RA 8293 section 176 provides that no copyright subsists in a work "
    "of the Government of the Philippines, while prior approval may be required for "
    "commercial use. PhilFacilities publishes only reviewed institutional fields "
    "(facility name, postal address, published operating hours, admission-fee text and "
    "coordinates from a Google Maps link embedded on the official page) for "
    "non-commercial public-interest use with attribution and takedown-on-notice. "
    "Telephone numbers, e-mail addresses, contact-person names and social-media links "
    "are withheld. Library pages are not re-ingested because the National Library of the "
    "Philippines directory already covers those branches; museum, church, commercial, "
    "campus and monument pages are outside this release's scope. This is a documented "
    "publication decision, not a legal opinion."
)
QUEZON_CITY_PLACES_ATTRIBUTION = (
    "Quezon City Government — Places to Visit directory (parks and public market subset)"
)
MANDALUYONG_DIRECTORY_URL = "https://mandaluyong.gov.ph/government/barangays/"
MANDALUYONG_RIGHTS_BASIS = (
    "The Mandaluyong City Government, a local government unit, publishes its barangay "
    "directory as a public web page. No explicit prohibition, access control or "
    "terms-of-use restriction was found on the inspected page. RA 8293 section 176 "
    "provides that no copyright subsists in a work of the Government of the Philippines, "
    "while prior approval may be required for commercial use. PhilFacilities publishes "
    "only reviewed institutional fields (barangay name, district, published barangay "
    "code and office address) for non-commercial public-interest use with attribution "
    "and takedown-on-notice. Telephone numbers and chairperson names are withheld. The "
    "source labels an office address, not a barangay hall; no hall subtype or walk-in "
    "access is inferred. This is a documented publication decision, not a legal opinion."
)
MANDALUYONG_ATTRIBUTION = "City Government of Mandaluyong — Barangay Directory"
CAINTA_HEALTH_URL = "https://www.cainta.gov.ph/healthcentersandservices2025"
CAINTA_RIGHTS_BASIS = (
    "The Municipality of Cainta, a local government unit, publishes its health-centre "
    "landing page and six Rural Health Unit pages as public web pages. No explicit "
    "prohibition, access control or terms-of-use restriction was found on the inspected "
    "pages. RA 8293 section 176 provides that no copyright subsists in a work of the "
    "Government of the Philippines, while prior approval may be required for commercial "
    "use. PhilFacilities publishes only reviewed institutional fields (health-centre "
    "name, RHU/BHS source label, barangay and postal address) for non-commercial "
    "public-interest use with attribution and takedown-on-notice. Telephone numbers, "
    "e-mail addresses and personal names are withheld. No coordinates, office hours, "
    "walk-in access rules or current operating status are inferred. This is a documented "
    "publication decision, not a legal opinion."
)
CAINTA_ATTRIBUTION = "Municipality of Cainta, Rizal — Health Centers and Other Services"
PASAY_HEALTH_URL = "https://pasay.gov.ph/programa/health-care/"
PASAY_RIGHTS_BASIS = (
    "The Pasay City Government, a local government unit, publishes its health-care "
    "programme page as a public web page. No explicit prohibition, access control or "
    "terms-of-use restriction was found on the inspected page. RA 8293 section 176 "
    "provides that no copyright subsists in a work of the Government of the Philippines, "
    "while prior approval may be required for commercial use. PhilFacilities publishes "
    "only reviewed institutional fields (facility name, published service label and "
    "postal address) for non-commercial public-interest use with attribution and "
    "takedown-on-notice. Telephone numbers are withheld. No coordinates, office hours, "
    "walk-in access rules or current operating status are inferred. This is a documented "
    "publication decision, not a legal opinion."
)
PASAY_ATTRIBUTION = "Pasay City Government — Mga Health Center ng Lungsod Pasay"
PPA_PORT_LIST_URL = (
    "https://ppa.com.ph/sites/default/files/List%20of%20Ports%20covered%20in%20PPA%20Statistics.pdf"
)
PPA_RIGHTS_BASIS = (
    "The List of Ports Covered in PPA Statistics is a published work of the Philippine "
    "Ports Authority, a government-owned and controlled corporation. RA 8293 section "
    "176 provides that no copyright subsists in a work of the Government of the "
    "Philippines, while prior approval may be required for commercial use. "
    "PhilFacilities publishes the factual port name, PMO/region hierarchy, RORO and "
    "NON-RORO marks, remarks and private/government group with attribution for "
    "non-commercial public-interest use. No coordinates, berth capacity, owner names "
    "or operational status are inferred. This is a documented publication decision, "
    "not a legal opinion."
)
PPA_ATTRIBUTION = "Philippine Ports Authority — List of Ports Covered in PPA Statistics"
DTI_NEGOSYO_FINDER_URL = "https://negosyocenter.dti.gov.ph/negosyo-center-directory"
DTI_NEGOSYO_API_URL = "https://negosyocenter.dti.gov.ph/api/negosyo-centers/regions-overview"
DTI_NEGOSYO_TERMS_URL = "https://negosyocenter.dti.gov.ph/terms-and-conditions"
DTI_NEGOSYO_RIGHTS_BASIS = (
    "The DTI Negosyo Center finder and its public JSON endpoints publish the official "
    "center directory. DTI's Terms and Conditions state that information posted on the "
    "DTI Web may be quoted or reproduced in whole or in part provided that DTI is duly "
    "informed/credited, while reselling, redistributing or creating derivative works for "
    "commercial purposes requires DTI's written consent. PhilFacilities publishes the "
    "factual center name, postal address, region/province/city labels and source active "
    "flag for non-commercial public-interest use with attribution and takedown-on-notice. "
    "Phone and email values are withheld from the public record. This is a documented "
    "product decision, not a legal opinion."
)
DTI_NEGOSYO_ATTRIBUTION = "Department of Trade and Industry — Negosyo Center finder"
CHED_HEIDA_DIRECTORY_URL = "https://heida.ched.gov.ph/hei-directory"
CHED_HEIDA_RIGHTS_BASIS = (
    "The CHED HEIDA public HEI directory is a publicly available, server-rendered "
    "directory published by the Commission on Higher Education, a government agency. "
    "No explicit prohibition, access control or terms-of-use restriction was found on "
    "the directory pages. RA 8293 section 176 provides that no copyright subsists in a "
    "work of the Government of the Philippines, while prior approval may be required "
    "for commercial use. PhilFacilities publishes only reviewed institutional fields "
    "(name, CHED code, institutional type, address and region) for non-commercial "
    "public-interest use with attribution and takedown-on-notice. Contact details and "
    "institutional-head names are discarded during acquisition. This is a documented "
    "publication decision under the root inclusion policy, not a legal opinion."
)
CHED_HEIDA_ATTRIBUTION = (
    "Commission on Higher Education — HEIDA Higher Education Institution Directory"
)


@dataclass(frozen=True)
class RealSource:
    key: str
    agency_code: str
    agency_name: str
    dataset_slug: str
    dataset_name: str
    source_url: str
    access_method: str
    update_pattern: str
    rights: str
    rights_basis: str
    attribution_text: str | None = None
    personal_data_status: str | None = None
    requested_publication_status: str | None = None
    license_identifier: str | None = None
    terms_url: str | None = None
    authority_level: str | None = None
    coverage_scope: str | None = None
    coverage_note: str | None = None
    is_geography: bool = False
    note: str | None = None
    minimum_acceptance_rate: float = DEFAULT_MINIMUM_ACCEPTANCE_RATE
    minimum_acceptance_rows: int = DEFAULT_MINIMUM_ACCEPTANCE_ROWS


REAL_SOURCES: dict[str, RealSource] = {
    "psa-psgc": RealSource(
        key="psa-psgc",
        agency_code="psa",
        agency_name="Philippine Statistics Authority",
        dataset_slug="psgc-official",
        dataset_name="Philippine Standard Geographic Code (official PSA workbook)",
        source_url="https://psa.gov.ph/classification/psgc",
        access_method="official_workbook",
        update_pattern="quarterly",
        rights=RIGHTS_REVIEW_REQUIRED,
        rights_basis=OFFICIAL_BLOCKED_BASIS,
        requested_publication_status=PUBLICATION_BLOCKED,
        note="Official Q3 2026 workbook returned HTTP 403 behind Cloudflare on 15 Nov 2026.",
    ),
    "bettergov-psgc": RealSource(
        key="bettergov-psgc",
        agency_code="bettergov",
        agency_name="BetterGov.PH",
        dataset_slug="psgc-bettergov-q2-2024",
        dataset_name="PSGC Q2 2024 snapshot (BetterGov Classification API)",
        source_url=BETTERGOV_PSGC_URL,
        access_method="public_api",
        update_pattern="quarterly snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=BETTERGOV_PSGC_RIGHTS_BASIS,
        attribution_text=BETTERGOV_PSGC_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="CC-BY-SA-4.0",
        terms_url="https://statistics.bettergov.ph/api",
        is_geography=True,
        note=(
            "Supplementary mirror of PSA PSGC Q2 2024, not the latest official PSA "
            "release. Codes are preserved as strings."
        ),
    ),
    "bettergov-population": RealSource(
        key="bettergov-population",
        agency_code="bettergov",
        agency_name="BetterGov.PH / Philippine Statistics Authority",
        dataset_slug="psa-census-2024-population",
        dataset_name=(
            "2024 Census of Population: total population, household population and "
            "number of households by province, city, municipality and barangay"
        ),
        source_url=BETTERGOV_STATISTICS_URL,
        access_method="public_json_api",
        update_pattern="saved PSA OpenSTAT snapshot; checked periodically",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=BETTERGOV_POPULATION_RIGHTS_BASIS,
        attribution_text=BETTERGOV_POPULATION_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="CC-BY-SA-4.0",
        terms_url="https://statistics.bettergov.ph/about",
        note=(
            "One statistical release per region. Values are saved PSA OpenSTAT "
            "snapshots; PSA remains the authoritative source. Counts are persons "
            "or households as labelled, not facility attributes."
        ),
    ),
    "philhealth": RealSource(
        key="philhealth",
        agency_code="philhealth",
        agency_name="Philippine Health Insurance Corporation",
        dataset_slug="philhealth-accredited-providers",
        dataset_name="PhilHealth accredited healthcare facilities (provider catalogue)",
        source_url=PHILHEALTH_INDEX_URL,
        access_method="public_html_index",
        update_pattern="monthly",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PHILHEALTH_RIGHTS_BASIS,
        attribution_text=PHILHEALTH_ATTRIBUTION,
        personal_data_status="business_contact_information",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=PHILHEALTH_INDEX_URL,
        note="One dataset release is created per provider-category PDF.",
    ),
    "philhealth-offices": RealSource(
        key="philhealth-offices",
        agency_code="philhealth",
        agency_name="Philippine Health Insurance Corporation",
        dataset_slug="philhealth-office-directory",
        dataset_name="PhilHealth Directory of Offices",
        source_url=PHILHEALTH_OFFICE_DIRECTORY_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PHILHEALTH_OFFICE_RIGHTS_BASIS,
        attribution_text=PHILHEALTH_OFFICE_ATTRIBUTION,
        personal_data_status="phone_email_and_schedule_withheld_from_public_record",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=PHILHEALTH_OFFICE_DIRECTORY_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The official Directory of Offices lists 19 regional-office groups with "
            "regional/branch offices, LHIOs, satellite offices, PhilHealth Express "
            "counters, service desks, business centres and one-stop service centres. "
            "The page does not state that every office, partner counter or extension "
            "point is included, and it supplies no coordinates, PSGC codes, office "
            "hours or current operating status."
        ),
        note=(
            "Server-rendered accordion directory. Office name, source section/category, "
            "region grouping and postal address are published; telephone numbers, e-mail "
            "addresses and schedule text stay in the private raw artifact. Entries with no "
            "postal address remain published with a missing-address warning rather than an "
            "invented location. Express counters and service desks are modelled as facility "
            "units; regional/branch/LHIO offices as facilities."
        ),
    ),
    "osm-health": RealSource(
        key="osm-health",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via HOT and BetterGov.PH)",
        dataset_slug="osm-health-facilities",
        dataset_name="OpenStreetMap health facilities (HOT Philippines extract)",
        source_url=(
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/"
            "health_facilities.parquet"
        ),
        access_method="public_geoparquet",
        update_pattern="irregular snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text=OSM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        note=(
            "Crowd-sourced map features, not an official government registry. Coordinates "
            "are bbox-centre map geocodes and record status is unknown."
        ),
    ),
    "osm-education": RealSource(
        key="osm-education",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via HOT and BetterGov.PH)",
        dataset_slug="osm-education-facilities",
        dataset_name="OpenStreetMap education facilities (HOT Philippines extract)",
        source_url=(
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/"
            "education_facilities.parquet"
        ),
        access_method="public_geoparquet",
        update_pattern="irregular snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text=OSM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        note=(
            "Crowd-sourced map features, not an official DepEd list. Coordinates are "
            "bbox-centre map geocodes and record status is unknown."
        ),
    ),
    "osm-points-of-interest": RealSource(
        key="osm-points-of-interest",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via HOT and BetterGov.PH)",
        dataset_slug="osm-public-service-facilities",
        dataset_name=(
            "OpenStreetMap public-service facilities (HOT Philippines points-of-interest layer)"
        ),
        source_url=(
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/"
            "points_of_interest.parquet"
        ),
        access_method="public_geoparquet",
        update_pattern="irregular snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text=OSM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Named features only. Selected tags: fire station, police, town hall, "
            "public building, post office, courthouse, prison, marketplace, library, "
            "community centre, social facility, arts centre, bus station, museum and "
            "gallery. Coverage and completeness are crowd-sourced and unknown."
        ),
        note=(
            "Crowd-sourced map features used as an alternate route where official "
            "registries are blocked. Coordinates are bbox-centre map geocodes and "
            "operational status is unknown."
        ),
    ),
    "osm-pbf-facilities": RealSource(
        key="osm-pbf-facilities",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via Geofabrik)",
        dataset_slug="osm-pbf-facilities",
        dataset_name=("OpenStreetMap filtered facility features (Geofabrik Philippines extract)"),
        source_url="https://download.geofabrik.de/asia/philippines-latest.osm.pbf",
        access_method="public_pbf",
        update_pattern="daily snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text="© OpenStreetMap contributors, via Geofabrik",
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Named government, public-space/recreation, emergency/DRM, healthcare, "
            "library, market, justice and selected civic features. A filtered extract "
            "of a Geofabrik Philippines PBF snapshot; crowd-sourced coverage is "
            "incomplete and not an official registry."
        ),
        note=(
            "Alternate coverage for blocked official registers. Way coordinates are "
            "means of mapped nodes and are labelled map_geocoded. Ownership, opening "
            "and operational status are never inferred."
        ),
    ),
    "osm-airports": RealSource(
        key="osm-airports",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via HOT and BetterGov.PH)",
        dataset_slug="osm-airports",
        dataset_name="OpenStreetMap airports, heliports and terminals (HOT Philippines extract)",
        source_url=(
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/airports.parquet"
        ),
        access_method="public_geoparquet",
        update_pattern="irregular snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text=OSM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Named aerodromes, helipads and airport terminals only; runways, taxiways "
            "and navigation aids are excluded. Crowd-sourced coverage is incomplete."
        ),
        note=(
            "Alternate coverage for blocked CAAP/DOTr sources. Not an official aerodrome "
            "registry; operator and operating status are not inferred."
        ),
    ),
    "osm-sea-ports": RealSource(
        key="osm-sea-ports",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via HOT and BetterGov.PH)",
        dataset_slug="osm-sea-ports",
        dataset_name="OpenStreetMap sea ports and ferry terminals (HOT Philippines extract)",
        source_url=(
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/"
            "sea_ports.parquet"
        ),
        access_method="public_geoparquet",
        update_pattern="irregular snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text=OSM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Named ferry terminals and port/harbour features only. Crowd-sourced "
            "coverage is incomplete and ownership/operator is often unrecorded."
        ),
        note=(
            "Alternate transport coverage alongside the official PPA port list. Not a "
            "port census; no berth, capacity or operating-status claim is made."
        ),
    ),
    "osm-railways": RealSource(
        key="osm-railways",
        agency_code="osm",
        agency_name="OpenStreetMap contributors (via HOT and BetterGov.PH)",
        dataset_slug="osm-railway-stations",
        dataset_name="OpenStreetMap railway stations (HOT Philippines extract)",
        source_url=(
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/PHL/_layers/osm/railways.parquet"
        ),
        access_method="public_geoparquet",
        update_pattern="irregular snapshot",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=OSM_RIGHTS_BASIS,
        attribution_text=OSM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        license_identifier="ODbL-1.0",
        terms_url="https://opendatacommons.org/licenses/odbl/1-0/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Named railway stations and halts only; rail lines and unnamed features are "
            "excluded. Crowd-sourced coverage is incomplete."
        ),
        note=(
            "Alternate coverage for blocked PNR/DOTr station sources. Not an official "
            "rail inventory; operating status and current station names are not inferred."
        ),
    ),
    "deped-ebeis": RealSource(
        key="deped-ebeis",
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-ebeis-masterlist-ncr",
        dataset_name="DepEd EBEIS school masterlist (NCR result set)",
        source_url=EBEIS_MASTERLIST_URL,
        access_method="public_html_form",
        update_pattern="school year",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DEPED_EBEIS_RIGHTS_BASIS,
        attribution_text=(
            "Department of Education — Enhanced Basic Education Information System "
            "(EBEIS) school masterlist"
        ),
        personal_data_status="school_head_names_retained_privately_not_published",
        requested_publication_status=PUBLICATION_APPROVED,
        note=(
            "NCR is the verified result set (5,055 rows on 15 Nov 2026). The public "
            "result page has no explicit reuse licence and contains school-head names; "
            "only institution-level fields are published under the government-work "
            "basis, while the raw acquisition artifact remains private."
        ),
    ),
    "deped-machine-ready": RealSource(
        key="deped-machine-ready",
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-machine-ready-files",
        dataset_name="DepEd Machine-Ready Files",
        source_url="https://www.deped.gov.ph/machine-ready-files/",
        access_method="human_download",
        update_pattern="school year",
        rights=RIGHTS_REVIEW_REQUIRED,
        rights_basis=OFFICIAL_BLOCKED_BASIS,
        requested_publication_status=PUBLICATION_BLOCKED,
        note="Official download flow is not automated; terms/feedback flow was not completed.",
    ),
    "doh-nhfr": RealSource(
        key="doh-nhfr",
        agency_code="doh",
        agency_name="Department of Health",
        dataset_slug="doh-nhfr",
        dataset_name="DOH National Health Facility Registry",
        source_url="https://nhfr.doh.gov.ph/VActivefacilitiesList",
        access_method="official_registry",
        update_pattern="weekly",
        rights=RIGHTS_REVIEW_REQUIRED,
        rights_basis=OFFICIAL_BLOCKED_BASIS,
        requested_publication_status=PUBLICATION_BLOCKED,
        note=(
            "HTTP 403 Cloudflare challenge on 15 Nov 2026. Existing FOI disclosures may "
            "carry a Data Release and Use Agreement; no agreement was accepted."
        ),
    ),
    "ched-heida": RealSource(
        key="ched-heida",
        agency_code="ched",
        agency_name="Commission on Higher Education",
        dataset_slug="ched-heida-hei-directory",
        dataset_name="CHED HEIDA Higher Education Institution Directory",
        source_url=CHED_HEIDA_DIRECTORY_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        rights_basis=CHED_HEIDA_RIGHTS_BASIS,
        attribution_text=CHED_HEIDA_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=CHED_HEIDA_DIRECTORY_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "CHED's public HEI directory lists recognized higher-education institutions "
            "under each of the 18 regional offices. It does not state that every campus, "
            "satellite, extension site or institution is included, and it supplies no "
            "coordinates or PSGC codes. Ownership is classified only from the published "
            "institutional type; 'Others', 'CHED-Supervised Institution' and unrecognised "
            "types remain internal."
        ),
        note=(
            "Server-rendered public directory with region pages and 10-row pagination. "
            "The adapter retains only institutional name, CHED code, type, address and "
            "region; contact details and institutional-head names are discarded. "
            "Chartered state colleges/universities are classified as public educational "
            "institutions, local government colleges/universities as local-government "
            "facilities, and private institutions as private public-service providers. "
            "Directory presence is not proof of current operation or public access."
        ),
    ),
    "tesda-tvi": RealSource(
        key="tesda-tvi",
        agency_code="tesda",
        agency_name="Technical Education and Skills Development Authority",
        dataset_slug="tesda-tvi-directory",
        dataset_name="TESDA registered training institutions directory",
        source_url="https://www.tesda.gov.ph/TVI",
        access_method="public_html_directory",
        update_pattern="unknown",
        rights=RIGHTS_REVIEW_REQUIRED,
        rights_basis=OFFICIAL_BLOCKED_BASIS,
        requested_publication_status=PUBLICATION_BLOCKED,
        note="Public directory exists; no verified bulk export or reuse terms recorded.",
    ),
    "nlp": RealSource(
        key="nlp",
        agency_code="nlp",
        agency_name="National Library of the Philippines",
        dataset_slug="nlp-public-libraries",
        dataset_name="NLP Integrated Directory of Public Libraries",
        source_url=NLP_LIBRARIES_URL,
        access_method="public_pdf",
        update_pattern="annual",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=NLP_RIGHTS_BASIS,
        attribution_text=NLP_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=NLP_LIBRARIES_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Nationwide directory of public libraries affiliated with the NLP Public "
            "Libraries Division as of December 2025. It is not a census of every library "
            "and excludes private and school libraries that are not affiliated."
        ),
        note=(
            "Source PDF is the December 2025 edition (220 pages, 1,752 rows). It supplies "
            "postal addresses but no coordinates or PSGC codes. Librarian contact fields "
            "are preserved in the raw release but not published."
        ),
    ),
    "national-museum": RealSource(
        key="national-museum",
        agency_code="nmp",
        agency_name="National Museum of the Philippines",
        dataset_slug="nmp-regional-area-site-museums",
        dataset_name="NMP regional, area and site museums directory",
        source_url=NATIONAL_MUSEUM_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=NATIONAL_MUSEUM_RIGHTS_BASIS,
        attribution_text=NATIONAL_MUSEUM_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=NATIONAL_MUSEUM_URL,
        coverage_scope="DIRECTORY_SUBSET",
        coverage_note=(
            "Directory of NMP-run regional, area and site museums outside Metro Manila. "
            "It is not a list of all museums in the Philippines."
        ),
        note=(
            "Directory cards link to official detail pages. Postal addresses are published "
            "where the detail page supplies them; the source supplies no coordinates."
        ),
    ),
    "phlpost": RealSource(
        key="phlpost",
        agency_code="phlpost",
        agency_name="Philippine Postal Corporation",
        dataset_slug="phlpost-post-office-locator",
        dataset_name="PHLPost post-office locator",
        source_url=PHLPOST_URL,
        access_method="public_html_table",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PHLPOST_RIGHTS_BASIS,
        attribution_text=("Philippine Postal Corporation — Post Office Locator"),
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=PHLPOST_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Locator table of PHLPost offices and service counters. Completeness against "
            "the agency's full office network has not been established."
        ),
        note=(
            "Single HTML table with columns Provinces, Post Offices, Addresss and Services. "
            "Only factual locator fields are published with attribution; the publisher's "
            "copyright notice is recorded in the rights basis."
        ),
    ),
    "bir": RealSource(
        key="bir",
        agency_code="bir",
        agency_name="Bureau of Internal Revenue",
        dataset_slug="bir-revenue-district-offices",
        dataset_name="BIR Revenue Regions and Revenue District Offices",
        source_url=BIR_RAO_URL,
        access_method="public_scanned_pdf_local_ocr",
        update_pattern="issuance-based",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=BIR_RIGHTS_BASIS,
        attribution_text=BIR_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=BIR_RAO_URL,
        coverage_scope="NATIONAL_OFFICIAL_INVENTORY",
        coverage_note=(
            "RAO No. 006-2025 lists the Revenue Regions and Revenue District Offices "
            "of the Bureau of Internal Revenue. It is an office/jurisdiction list, "
            "not a street-address, coordinate or service-hours dataset."
        ),
        note=(
            "Official 4-page image-only PDF dated 9 December 2025. Local OCR recovered "
            "128 RDO rows and 19 revenue-region headings; raw OCR lines and confidence "
            "are retained with each record. No addresses or coordinates are inferred. "
            "The separate 523-page Citizen's Charter is not merged into this release."
        ),
    ),
    "dswd-crcf": RealSource(
        key="dswd-crcf",
        agency_code="dswd",
        agency_name="Department of Social Welfare and Development",
        dataset_slug="dswd-crcf-directory",
        dataset_name="DSWD Centers and Residential Care Facilities (CRCF) directory",
        source_url=DSWD_CRCF_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DSWD_CRCF_RIGHTS_BASIS,
        attribution_text=DSWD_CRCF_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=DSWD_CRCF_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "Directory of DSWD-operated Centers and Residential Care Facilities. The "
            "page states 77 CRCFs but exposes 76 unique facility cards after exact "
            "desktop/mobile deduplication; the missing card is not invented."
        ),
        note=(
            "Elementor directory with desktop and mobile accordion layouts. 152 raw "
            "cards collapse to 76 unique facility cards by facility name and address. "
            "Cards supply a facility name, DSWD Field Office and postal address only; "
            "no coordinates, PSGC codes, walk-in access rules or operational status."
        ),
    ),
    "quezon-city": RealSource(
        key="quezon-city",
        agency_code="quezon-city",
        agency_name="Quezon City Government",
        dataset_slug="quezon-city-lgu-directory",
        dataset_name="Quezon City health-centre and barangay directories",
        source_url=QUEZON_CITY_DIRECTORY_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=QUEZON_CITY_RIGHTS_BASIS,
        attribution_text=QUEZON_CITY_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=QUEZON_CITY_DIRECTORY_URL,
        coverage_scope="SINGLE_LGU",
        coverage_note=(
            "Official Quezon City Government directories acquired on 16 November 2026: "
            "81 health-centre sitemap pages and 142 barangay directory pages. The release "
            "publishes 68 barangay health centres and the 40 barangay pages whose address "
            "link explicitly names a Barangay Hall. Remaining pages are retained in the "
            "private payload but are not converted into facilities. This is Quezon City "
            "coverage only; it is not a national or complete LGU inventory."
        ),
        note=(
            "Two server-rendered directories. Health pages supply name, WordPress health "
            "category, postal address and telephone; barangay pages supply an official "
            "address, contact fields, officials and schools. The adapter withholds phone, "
            "e-mail, social-media and personal-name fields; health-centre records have no "
            "coordinates. Barangay-hall coordinates come from Google Maps links embedded "
            "on the LGU page and are labelled map_geocoded. COVID-19 swab-testing pages, "
            "health administrative offices and barangay pages without a hall-labelled map "
            "place are excluded with warnings."
        ),
    ),
    "quezon-city-places": RealSource(
        key="quezon-city-places",
        agency_code="quezon-city",
        agency_name="Quezon City Government",
        dataset_slug="quezon-city-lgu-places",
        dataset_name="Quezon City Places to Visit directory (park and market subset)",
        source_url=QUEZON_CITY_PLACES_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=QUEZON_CITY_PLACES_RIGHTS_BASIS,
        attribution_text=QUEZON_CITY_PLACES_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=QUEZON_CITY_PLACES_URL,
        coverage_scope="SINGLE_LGU",
        coverage_note=(
            "Official Quezon City Places to Visit directory acquired on 16 November 2026. "
            "The public search endpoint advertises 65 place pages. This release publishes "
            "only Kamuning Market and four park/open-space pages; 23 Quezon City Public "
            "Library pages are already covered by the NLP public-library directory and "
            "are not re-ingested. Museum, church, commercial, campus and monument pages "
            "are excluded. This is Quezon City coverage only; it is not a national or "
            "complete LGU inventory."
        ),
        note=(
            "Server-rendered public place pages discovered through the site's public search "
            "endpoint. Pages supply a name, postal address, operating hours, admission-fee "
            "text and, on some pages, a Google Maps link. The adapter withholds telephone "
            "numbers, e-mail addresses, contact-person names and social-media links. "
            "Coordinates are labelled map_geocoded; presence in a visitor directory is not "
            "proof of current operation, ownership or service availability."
        ),
    ),
    "mandaluyong": RealSource(
        key="mandaluyong",
        agency_code="mandaluyong",
        agency_name="City Government of Mandaluyong",
        dataset_slug="mandaluyong-lgu-barangay-directory",
        dataset_name="Mandaluyong City Barangay Directory",
        source_url=MANDALUYONG_DIRECTORY_URL,
        access_method="public_html_table",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=MANDALUYONG_RIGHTS_BASIS,
        attribution_text=MANDALUYONG_ATTRIBUTION,
        personal_data_status="phone_and_chairperson_withheld_from_public_record",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=MANDALUYONG_DIRECTORY_URL,
        coverage_scope="SINGLE_LGU",
        coverage_note=(
            "Official Mandaluyong City barangay directory acquired on 16 November 2026. "
            "The page table lists all 27 barangays with district, published barangay "
            "code, office address, contact numbers, chairperson and an optional image. "
            "This is Mandaluyong City coverage only; it is not a national or complete "
            "LGU inventory. The directory supplies postal office addresses but no "
            "coordinates, office hours, walk-in access rules or current operating status."
        ),
        note=(
            "Server-rendered public table (28 rows including the header). The adapter "
            "publishes barangay name, district, published code and office address, and "
            "withholds telephone numbers and chairperson names. The source does not call "
            "the location a barangay hall, so records are modelled as barangay government "
            "offices rather than halls. The one address that explicitly names a covered "
            "court is modelled as a community facility with barangay-office and "
            "covered-court functions. No geocoding was performed."
        ),
    ),
    "cainta-health": RealSource(
        key="cainta-health",
        agency_code="cainta",
        agency_name="Municipality of Cainta",
        dataset_slug="cainta-lgu-health-centers",
        dataset_name="Cainta municipal health-centre directory",
        source_url=CAINTA_HEALTH_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=CAINTA_RIGHTS_BASIS,
        attribution_text=CAINTA_ATTRIBUTION,
        personal_data_status="no_personal_or_contact_fields_published",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=CAINTA_HEALTH_URL,
        coverage_scope="SINGLE_LGU",
        coverage_note=(
            "Official Cainta, Rizal health-services page and six RHU pages acquired on "
            "16 November 2026. The landing page states 28 health centres across seven "
            "barangays; the six RHU pages supply 28 explicitly labelled RHU/BHS records "
            "plus three unlabelled entries that are retained privately and excluded. "
            "This is Cainta coverage only; it is not a national or complete LGU "
            "inventory. The pages supply postal addresses but no coordinates, office "
            "hours, walk-in access rules or current operating status."
        ),
        note=(
            "Wix-rendered public pages. The adapter publishes only records explicitly "
            "labelled RHU or BHS, using RURAL_HEALTH_UNIT and BARANGAY_HEALTH_STATION "
            "subtypes. The unlabelled RHU 5 entries and the One Cainta satellite health "
            "station are preserved in the raw artifact and excluded. No geocoding was "
            "performed."
        ),
    ),
    "pasay-health": RealSource(
        key="pasay-health",
        agency_code="pasay",
        agency_name="Pasay City Government",
        dataset_slug="pasay-lgu-health-centers",
        dataset_name="Pasay City health-centre directory",
        source_url=PASAY_HEALTH_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PASAY_RIGHTS_BASIS,
        attribution_text=PASAY_ATTRIBUTION,
        personal_data_status="telephone_numbers_withheld_from_public_record",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=PASAY_HEALTH_URL,
        coverage_scope="SINGLE_LGU",
        coverage_note=(
            "Official Pasay City health-care programme page acquired on 16 November 2026. "
            "The 'Mga Health Center ng Lungsod Pasay' section lists 13 city health centres "
            "and the Doña Marta Lying-In Clinic with printed postal addresses and some "
            "service labels. This is Pasay City coverage only; it is not a national or "
            "complete LGU inventory. The page supplies no coordinates, office hours, "
            "walk-in access rules or current operating status."
        ),
        note=(
            "Elementor-rendered public page. The adapter publishes the 13 health centres "
            "as OTHER_HEALTH_FACILITY because the source does not state RHU/BHS level, and "
            "the lying-in clinic as a separate CLINIC with co-location evidence. Telephone "
            "numbers are withheld and are not stored in the artifact. No geocoding was "
            "performed."
        ),
    ),
    "nmis-naris": RealSource(
        key="nmis-naris",
        agency_code="nmis",
        agency_name="National Meat Inspection Service",
        dataset_slug="nmis-naris-accredited-meat-establishments",
        dataset_name="NMIS NARIS accredited meat establishments",
        source_url=NMIS_NARIS_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=NMIS_NARIS_RIGHTS_BASIS,
        attribution_text=NMIS_NARIS_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=NMIS_NARIS_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "NARIS accredited-establishment list as rendered on 15 November 2026. The "
            "page reports 362 rows but exposes 357 unique LTO numbers after grouping "
            "five duplicate rows; completeness against all NMIS-issued LTOs and LTO "
            "validity dates are not stated."
        ),
        note=(
            "Server-rendered page with a 362-entry ltoLocations JSON array. Fields are "
            "company name, LTO number, establishment type, address parts and optional "
            "cached address geocode. No validity dates or operating status. 17 "
            "municipal-named establishments are classified as local-government operated "
            "from the source name; all other LTO holders remain private providers. The "
            "live endpoint returned a WAF challenge or TLS failure on 15 November 2026 "
            "recheck; the preserved public artifact is the release of record."
        ),
    ),
    "ppa": RealSource(
        key="ppa",
        agency_code="ppa",
        agency_name="Philippine Ports Authority",
        dataset_slug="ppa-port-list",
        dataset_name="PPA List of Ports Covered in PPA Statistics",
        source_url=PPA_PORT_LIST_URL,
        access_method="public_pdf",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PPA_RIGHTS_BASIS,
        attribution_text=PPA_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=PPA_PORT_LIST_URL,
        coverage_scope="DIRECTORY_SUBSET",
        coverage_note=(
            "PPA's published statistics list of ports under its Port Management Offices, "
            "other government ports and the separate private-port list. It is not a "
            "census of every port, terminal, berth or landing place in the Philippines, "
            "and it supplies no coordinates or public-access rules."
        ),
        note=(
            "22-page PDF retrieved 15 November 2026. 574 source rows: 54 base ports, 94 "
            "TMO/OTP entries, 155 other government ports and 271 private ports. RORO and "
            "NON-RORO marks are preserved; blank marks remain unknown rather than false. "
            "The separate MICT note outside the tables is retained as evidence and not "
            "ingested because its hierarchy and ownership are not stated."
        ),
    ),
    "dti-negosyo": RealSource(
        key="dti-negosyo",
        agency_code="dti",
        agency_name="Department of Trade and Industry",
        dataset_slug="dti-negosyo-centers",
        dataset_name="DTI Negosyo Center directory",
        source_url=DTI_NEGOSYO_FINDER_URL,
        access_method="public_json_api",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DTI_NEGOSYO_RIGHTS_BASIS,
        attribution_text=DTI_NEGOSYO_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=DTI_NEGOSYO_TERMS_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The DTI Negosyo Center finder returned 1,427 active center records across "
            "all 17 regions on 15 November 2026. The finder does not state that the list "
            "is a complete census, does not identify each center's owner/operator/host, "
            "and supplies no coordinates, PSGC codes, hours or public-access conditions. "
            "Presence in the directory is not proof of current operation."
        ),
        note=(
            "Two unauthenticated public JSON endpoints back the finder: regions-overview "
            "and by-region. Records contain center name, postal address, region/province/"
            "city labels, optional institutional phone/email and an is_active flag. The "
            "adapter stores each center as a government facility unit under the DTI "
            "business-advisory programme with unspecified ownership/operator; it does not "
            "classify a host city hall, SUC or other premises. Contact fields stay in the "
            "private raw artifact and out of the public record."
        ),
    ),
    "sss-branches": RealSource(
        key="sss-branches",
        agency_code="sss",
        agency_name="Social Security System",
        dataset_slug="sss-branch-locator",
        dataset_name="SSS Branch Locator",
        source_url=SSS_BRANCH_LOCATOR_URL,
        access_method="public_json_api",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=SSS_RIGHTS_BASIS,
        attribution_text=SSS_ATTRIBUTION,
        personal_data_status="contact_person_email_and_phone_withheld_from_public_record",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=SSS_BRANCH_LOCATOR_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The official SSS branch locator returned 323 branch records across the "
            "National Capital Region, Luzon, Visayas, Mindanao and Foreign region groups "
            "on 15 November 2026. The locator does not state that every service desk, "
            "partner counter or extension office is listed, and supplies no coordinates, "
            "PSGC codes, office hours or current operating status."
        ),
        note=(
            "Three unauthenticated JSON endpoints back the public locator: region list, "
            "per-region branch list and per-branch details. The list carries null address "
            "fields, so each branch detail was fetched. Branch name, postal address and "
            "region are published; contact-person, e-mail and telephone/fax strings stay "
            "in the private raw artifact. Branches are classified as GOCC government "
            "service facilities, not as private providers."
        ),
    ),
    "pagasa-aws": RealSource(
        key="pagasa-aws",
        agency_code="pagasa",
        agency_name="Philippine Atmospheric, Geophysical and Astronomical Services Administration",
        dataset_slug="pagasa-automated-weather-stations",
        dataset_name="PAGASA Automated Weather Station network",
        source_url=PAGASA_AWS_URL,
        access_method="public_html_table",
        update_pattern="live",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PAGASA_AWS_RIGHTS_BASIS,
        attribution_text=PAGASA_AWS_ATTRIBUTION,
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=PAGASA_AWS_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The live PAGASA AWS page listed 113 station rows on 15 November 2026. The "
            "page is an operational display, not a dated station inventory, and does not "
            "state that every AWS or synoptic station is present. It supplies no "
            "coordinates, PSGC codes, commissioning dates or access rules."
        ),
        note=(
            "The AWS table mixes automated weather stations and synoptic stations and "
            "carries live readings plus a per-station last-updated value. Only station "
            "identity (site ID, site name, source last-updated) is published; readings "
            "stay in the private dated artifact and are not presented as current weather. "
            "Stations are classified as national-government environmental monitoring "
            "facilities operated by PAGASA."
        ),
    ),
    "nbi-offices": RealSource(
        key="nbi-offices",
        agency_code="nbi",
        agency_name="National Bureau of Investigation",
        dataset_slug="nbi-regional-district-offices",
        dataset_name="NBI Regional and District Offices",
        source_url=NBI_OFFICES_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=NBI_RIGHTS_BASIS,
        attribution_text=NBI_ATTRIBUTION,
        personal_data_status="personal_names_phone_and_email_withheld_from_public_record",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url=NBI_OFFICES_URL,
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The official page listed 52 regional/district office records on 15 November "
            "2026, 43 of which carried an embedded map frame. It is a directory of "
            "regional and district offices, not every clearance center, satellite desk or "
            "service point, and it supplies no office hours or current operating status."
        ),
        note=(
            "Office name, region, postal location and map-embed coordinates are published. "
            "Map coordinates are extracted from the official page's Google Maps iframes "
            "and labelled 'map_geocoded'; they are not field-verified. Regional director/"
            "agent-in-charge names, telephone numbers and protected e-mail values remain "
            "in the private raw artifact."
        ),
    ),
    "nha-doh-hf": RealSource(
        key="nha-doh-hf",
        agency_code="nha",
        agency_name="National Housing Authority",
        dataset_slug="nha-doh-health-facilities",
        dataset_name="NHA GeoServer — DOH health facility layer (partial NHFR alternate)",
        source_url=NHA_DOH_HF_URL,
        access_method="public_wfs",
        update_pattern="irregular",
        rights=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        rights_basis=NHA_RIGHTS_BASIS,
        attribution_text=NHA_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://nha.gov.ph/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The public WFS layer returned 31,016 health-facility features on 16 November "
            "2026: barangay health stations, rural health units, birthing homes, hospitals, "
            "infirmaries, laboratories, drug-treatment centres and blood centres. It is an "
            "official alternate route for the blocked DOH NHFR, but it is a partial layer "
            "with no stated release date, completeness note or operating-status field."
        ),
        note=(
            "Preserves the source facility code, name, type, ownership label, PSGC labels "
            "and codes, coordinates and prec_latlo flag. The layer uses the older ARMM PSGC "
            "series for the Bangsamoro region; codes are not remapped to current BARMM "
            "codes. Presence is registry evidence only and does not prove an operating "
            "status or building-level precision."
        ),
    ),
    "nha-housing-projects": RealSource(
        key="nha-housing-projects",
        agency_code="nha",
        agency_name="National Housing Authority",
        dataset_slug="nha-housing-project-locations",
        dataset_name="NHA GeoServer — housing project locations",
        source_url=NHA_PROJECT_URL,
        access_method="public_wfs",
        update_pattern="irregular",
        rights=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        rights_basis=NHA_RIGHTS_BASIS,
        attribution_text=(
            "National Housing Authority — NHA_PH GeoServer, 'NHA_Project_Loc' layer "
            "(accessed 16 November 2026)"
        ),
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://nha.gov.ph/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The public WFS layer returned 946 project-location features on 16 November "
            "2026. These are NHA project sites, not operating facilities; the layer does "
            "not state completion, occupancy or current status and carries NHA place "
            "labels rather than standard PSGC codes."
        ),
        note=(
            "Preserves project code, name, class, office/place labels, unit count and "
            "developer where supplied. No PSGC code, occupancy or operational status is "
            "inferred. Point geometry is labelled as the source project location."
        ),
    ),
    "nha-landholdings": RealSource(
        key="nha-landholdings",
        agency_code="nha",
        agency_name="National Housing Authority",
        dataset_slug="nha-landholdings",
        dataset_name="NHA GeoServer — landholdings",
        source_url=NHA_LANDHOLDINGS_URL,
        access_method="public_wfs",
        update_pattern="irregular",
        rights=RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        rights_basis=NHA_RIGHTS_BASIS,
        attribution_text=(
            "National Housing Authority — NHA_PH GeoServer, 'NHA LANDHOLDINGS' layer "
            "(accessed 16 November 2026)"
        ),
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://nha.gov.ph/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The public WFS layer returned 169 property features on 16 November 2026 "
            "(160 with point geometry). These are NHA landholdings, not facilities; no "
            "occupancy, tenancy or operating status is published."
        ),
        note=(
            "Preserves property name, layer/classification, region label, source area in "
            "square metres and location text. Area values are not recalculated."
        ),
    ),
    "doe-power-luzon": RealSource(
        key="doe-power-luzon",
        agency_code="doe",
        agency_name="Department of Energy",
        dataset_slug="doe-power-plants-luzon",
        dataset_name="DOE List of Existing Power Plants — Luzon grid (September 2026)",
        source_url=(
            "https://d24qbtp4vooyzi.cloudfront.net/api/media/file/"
            "DOE-EPIMB_LoEPP%20as%20of%20September%202026_Luzon%20Grid.pdf"
            "?prefix=dev%2Fmedia"
        ),
        access_method="public_pdf",
        update_pattern="monthly/quarterly",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DOE_LOEPP_RIGHTS_BASIS,
        attribution_text=DOE_LOEPP_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://doe.gov.ph/",
        coverage_scope="REGIONAL",
        coverage_note=(
            "The Luzon-grid list covers existing grid-connected power plants in the "
            "Luzon grid as of 30 September 2026. It is a generation-facility list, not "
            "a complete energy-infrastructure register, and supplies no coordinates."
        ),
        note=(
            "Preserves DOE facility code, official name, resource/technology, "
            "connection, installed/dependable capacity, unit count, place labels, "
            "operator/owner/IPPA, owner type, contract type and commissioning date. "
            "Unit rows are preserved separately; blanks are not back-filled."
        ),
    ),
    "doe-power-visayas": RealSource(
        key="doe-power-visayas",
        agency_code="doe",
        agency_name="Department of Energy",
        dataset_slug="doe-power-plants-visayas",
        dataset_name="DOE List of Existing Power Plants — Visayas grid (September 2026)",
        source_url=(
            "https://d24qbtp4vooyzi.cloudfront.net/api/media/file/"
            "DOE-EPIMB_LoEPP%20as%20of%20September%202026_Visayas%20Grid.pdf"
            "?prefix=dev%2Fmedia"
        ),
        access_method="public_pdf",
        update_pattern="monthly/quarterly",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DOE_LOEPP_RIGHTS_BASIS,
        attribution_text=DOE_LOEPP_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://doe.gov.ph/",
        coverage_scope="REGIONAL",
        coverage_note=(
            "The Visayas-grid list covers existing grid-connected power plants in the "
            "Visayas grid as of 30 September 2026. It supplies no coordinates."
        ),
        note=(
            "Preserves the DOE coding, source labels, capacities, place labels and "
            "operator/owner evidence; no legal-ownership or operating-status inference."
        ),
    ),
    "doe-power-mindanao": RealSource(
        key="doe-power-mindanao",
        agency_code="doe",
        agency_name="Department of Energy",
        dataset_slug="doe-power-plants-mindanao",
        dataset_name="DOE List of Existing Power Plants — Mindanao grid (September 2026)",
        source_url=(
            "https://d24qbtp4vooyzi.cloudfront.net/api/media/file/"
            "DOE-EPIMB_LoEPP%20as%20of%20September%202026_Mindanao%20Grid.pdf"
            "?prefix=dev%2Fmedia"
        ),
        access_method="public_pdf",
        update_pattern="monthly/quarterly",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DOE_LOEPP_RIGHTS_BASIS,
        attribution_text=DOE_LOEPP_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://doe.gov.ph/",
        coverage_scope="REGIONAL",
        coverage_note=(
            "The Mindanao-grid list covers existing grid-connected power plants in the "
            "Mindanao grid as of 30 September 2026. It supplies no coordinates."
        ),
        note=(
            "Preserves the DOE coding, source labels, capacities, place labels and "
            "operator/owner evidence; no legal-ownership or operating-status inference."
        ),
    ),
    "doe-power-offgrid": RealSource(
        key="doe-power-offgrid",
        agency_code="doe",
        agency_name="Department of Energy",
        dataset_slug="doe-power-plants-offgrid",
        dataset_name="DOE List of Existing Power Plants — off-grid (April 2026)",
        source_url=(
            "https://d24qbtp4vooyzi.cloudfront.net/api/media/file/"
            "List%20of%20Existing%20Power%20Plants%20Off-Grid%20as%20of%2030%20April%202026.pdf"
            "?prefix=dev%2Fmedia"
        ),
        access_method="public_pdf",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=DOE_LOEPP_RIGHTS_BASIS,
        attribution_text=DOE_LOEPP_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://doe.gov.ph/",
        coverage_scope="NATIONAL_PARTIAL",
        coverage_note=(
            "The off-grid list covers existing off-grid power plants in Luzon, Visayas "
            "and Mindanao as of 30 April 2026. It is not a complete electrification or "
            "microgrid register and supplies no coordinates."
        ),
        note=(
            "Preserves facility name, subtype, installed/dependable capacity, place and "
            "region labels, operator, owner type, operating hours and commissioning "
            "date. Off-grid rows have no official-name or unit-count column."
        ),
    ),
    "lrta-stations": RealSource(
        key="lrta-stations",
        agency_code="lrta",
        agency_name="Light Rail Transit Authority",
        dataset_slug="lrta-lrt-stations",
        dataset_name="LRTA Line 1 and Line 2 station distances (derived station list)",
        source_url=LRTA_DISTANCE_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=LRTA_RIGHTS_BASIS,
        attribution_text=LRTA_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://www.lrta.gov.ph/website-privacy-policy/",
        coverage_scope="SELECTED_LGUS",
        coverage_note=(
            "Covers the Line 1 and Line 2 stations named in the official interval table "
            "(Metro Manila). The page is not a complete LRT inventory, is not dated as a "
            "station list, and supplies no coordinates, addresses or operating status."
        ),
        note=(
            "The page lists station pairs and interval distances. Unique station names are "
            "derived from the intervals and labelled as derived; no coordinate or "
            "opening-status claim is made."
        ),
    ),
    "mrt3-stations": RealSource(
        key="mrt3-stations",
        agency_code="dotr",
        agency_name="Department of Transportation — MRT-3",
        dataset_slug="mrt3-stations",
        dataset_name="MRT-3 station directory (official station page)",
        source_url=MRT3_STATIONS_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=MRT3_RIGHTS_BASIS,
        attribution_text=MRT3_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        coverage_scope="SELECTED_LGUS",
        coverage_note=(
            "Covers the 13 station names listed on the MRT-3 site along EDSA in Metro "
            "Manila. The page is not a dated station inventory, carries older station "
            "labels, and supplies no coordinates, addresses or operating status."
        ),
        note=(
            "Station names are preserved verbatim. The page is an older public "
            "information page; no current-name crosswalk, coordinate or operating-status "
            "claim is made."
        ),
    ),
    "bucor-oppf": RealSource(
        key="bucor-oppf",
        agency_code="bucor",
        agency_name="Bureau of Corrections",
        dataset_slug="bucor-oppf-facilities",
        dataset_name="Bureau of Corrections — OPPF operating prison and penal facilities",
        source_url=BUCOR_OPPF_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=BUCOR_RIGHTS_BASIS,
        attribution_text=BUCOR_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://bucor.gov.ph/",
        coverage_scope="DIRECTORY_SUBSET",
        coverage_note=(
            "The OPPF page lists seven BuCor operating prison and penal facilities with "
            "links to one detail page each. It is not a national corrections register: "
            "BJMP, provincial and sub-provincial jails are separate custodians."
        ),
        note=(
            "Only the facility name and official detail-page link are published. No "
            "address, coordinate, capacity, population, operating status or security "
            "information is present or inferred."
        ),
    ),
    "prc-offices": RealSource(
        key="prc-offices",
        agency_code="prc",
        agency_name="Professional Regulation Commission",
        dataset_slug="prc-regional-offices",
        dataset_name="PRC regional offices (official office locator)",
        source_url=PRC_LOCATOR_URL,
        access_method="public_html_directory",
        update_pattern="irregular",
        rights=RIGHTS_APPROVED_ATTRIBUTION,
        rights_basis=PRC_RIGHTS_BASIS,
        attribution_text=PRC_ATTRIBUTION,
        personal_data_status="institutional_fields_only",
        requested_publication_status=PUBLICATION_APPROVED,
        terms_url="https://www.prc.gov.ph/",
        coverage_scope="REGIONAL",
        coverage_note=(
            "The official locator page enumerates PRC regional offices with embedded "
            "map pins and short address labels. It is not a complete inventory of "
            "satellite, mall-based or host-agency service counters."
        ),
        note=(
            "Publishes office name, address label and embedded map-pin coordinates. "
            "Coordinates are labelled map_geocoded, not survey-grade GPS. No PSGC "
            "code, building ownership, office hours or operating status is inferred."
        ),
    ),
}


def source_spec(source: RealSource, **overrides: Any) -> ReleaseSpec:
    """Build a release specification with the registry's rights metadata."""

    values: dict[str, Any] = {
        "agency_code": source.agency_code,
        "agency_name": source.agency_name,
        "dataset_slug": source.dataset_slug,
        "dataset_name": source.dataset_name,
        "release_label": "",
        "filename": "",
        "content": b"",
        "source_url": source.source_url,
        "terms_url": source.terms_url,
        "redistribution_status": source.rights,
        "rights_basis": source.rights_basis,
        "attribution_text": source.attribution_text,
        "personal_data_status": source.personal_data_status,
        "requested_publication_status": source.requested_publication_status,
        "access_method": source.access_method,
        "update_pattern": source.update_pattern,
        "license_identifier": source.license_identifier,
        "coverage_scope": source.coverage_scope,
        "coverage_note": source.coverage_note,
        "notes": source.note,
        "minimum_acceptance_rate": source.minimum_acceptance_rate,
        "minimum_acceptance_rows": source.minimum_acceptance_rows,
    }
    values.update(overrides)
    return ReleaseSpec(**values)


def apply_publication_decisions(
    session: Session,
    keys: Iterable[str] | None = None,
    *,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Apply the reviewed registry publication decision to stored datasets.

    A rights review changes the code registry, but an existing database keeps its
    old publication gate until an explicit action reconciles it. This function is
    that action: it updates the dataset rights metadata and gate to match the
    reviewed registry entry. It never ingests, publishes or deletes records by
    itself; a release becomes public only when it is reprocessed under the updated
    gate. Callers must name the reviewer for any decision that makes a dataset
    public.
    """

    selected = list(keys) if keys else []
    unknown = [key for key in selected if key not in REAL_SOURCES]
    if unknown:
        raise ValueError(f"Unknown source key(s): {', '.join(unknown)}")

    results: dict[str, dict[str, Any]] = {}
    if selected:
        candidates = [REAL_SOURCES[key] for key in selected]
    else:
        # Do not create empty dataset rows merely to update a decision. An
        # unqualified invocation reconciles only sources already registered in
        # the database.
        existing_slugs = set(session.scalars(select(Dataset.slug)).all())
        candidates = [
            source for source in REAL_SOURCES.values() if source.dataset_slug in existing_slugs
        ]

    for source in candidates:
        spec = source_spec(source)
        _agency, dataset, gate = ensure_source(session, spec)
        rights = normalize_rights(spec.redistribution_status)
        requested = spec.requested_publication_status or (
            PUBLICATION_APPROVED if rights_allow_public(rights) else PUBLICATION_BLOCKED
        )
        if requested == PUBLICATION_APPROVED and rights_allow_public(rights):
            if not reviewer:
                raise ValueError(
                    f"Source {source.key!r} would become public; pass a reviewer to "
                    "record the rights decision."
                )
            gate_status = PUBLICATION_APPROVED
            dataset_status = PUBLICATION_APPROVED
        elif requested == PUBLICATION_INTERNAL_ONLY:
            gate_status = PUBLICATION_INTERNAL_ONLY
            dataset_status = PUBLICATION_INTERNAL_ONLY
        else:
            gate_status = PUBLICATION_BLOCKED
            dataset_status = PUBLICATION_BLOCKED
        dataset.redistribution_status = rights
        dataset.publication_status = dataset_status
        gate.status = gate_status
        gate.reviewer = reviewer or "registry-policy"
        gate.reviewed_at = datetime.now(UTC)
        gate.notes = note or spec.rights_basis or "Reviewed registry publication decision."
        results[source.key] = {
            "dataset": dataset.slug,
            "rights": rights,
            "dataset_publication_status": dataset_status,
            "gate_status": gate_status,
        }
    session.commit()
    return results


def monitored_dataset(session: Session, source: RealSource) -> Dataset:
    """Create or fetch the dataset row used by the monitoring ledger."""

    _agency, dataset, _gate = ensure_source(session, source_spec(source))
    return dataset


# ---------------------------------------------------------------------------
# Source checks
# ---------------------------------------------------------------------------


FILE_UPDATE_METHODS = {
    "official_workbook",
    "public_pdf",
    "public_scanned_pdf_local_ocr",
    "public_geoparquet",
}
PAYLOAD_UPDATE_METHODS = {
    "public_api",
    "public_json_api",
    "public_html_directory",
    "public_html_index",
    "public_html_table",
    "public_html_form",
}
VOLATILE_OBSERVATION_SOURCES = {
    # Live readings change independently of the station-identity release.
    "pagasa-aws",
}


def update_discovery_mode(source: RealSource) -> str:
    """Describe how a source check can discover a new release.

    ``file_checksum`` and ``payload_checksum`` compare the fetched bytes with the
    latest published release. ``manual`` sources require a human download and cannot
    be auto-detected. ``observations_only`` sources change continuously and must not
    be presented as a new facility release.
    """

    if source.key in VOLATILE_OBSERVATION_SOURCES:
        return "observations_only"
    if source.access_method == "human_download" or source.access_method == "official_registry":
        return "manual"
    if source.access_method in FILE_UPDATE_METHODS:
        return "file_checksum"
    if source.access_method in PAYLOAD_UPDATE_METHODS:
        return "payload_checksum"
    return "manual"


def detect_new_release(
    mode: str,
    fetched_sha256: str | None,
    published_sha256: str | None,
) -> bool | None:
    """Return whether the fetched payload differs from the latest published release."""

    if mode not in {"file_checksum", "payload_checksum"}:
        return None
    if not fetched_sha256 or not published_sha256:
        return None
    return fetched_sha256 != published_sha256


def check_sources(
    session: Session,
    *,
    keys: Iterable[str] | None = None,
    acquirer: HttpAcquirer | None = None,
) -> dict[str, dict[str, Any]]:
    """Compatibility wrapper around the CheckSpec-driven checker."""

    from .checks import check_sources as _check_sources

    return _check_sources(session, keys=keys, acquirer=acquirer)


# ---------------------------------------------------------------------------
# PhilHealth catalogue
# ---------------------------------------------------------------------------


def philhealth_catalog(acquirer: HttpAcquirer) -> list[PhilHealthCatalogEntry]:
    result = acquirer.fetch(PHILHEALTH_INDEX_URL)
    if result.status_code >= 400 or is_blocker_page(result):
        raise AcquisitionError(
            f"PhilHealth index returned HTTP {result.status_code}; no catalogue was accepted.",
            result=result,
        )
    return parse_catalog(
        result.content.decode("utf-8", errors="replace"), base_url=PHILHEALTH_INDEX_URL
    )


def philhealth_dataset_slug(entry: PhilHealthCatalogEntry) -> str:
    stem = entry.filename.rsplit(".", 1)[0]
    stable = re.sub(r"_\d{6}$", "", stem).lower()
    stable = re.sub(r"[^a-z0-9]+", "-", stable).strip("-") or "provider"
    return f"philhealth-{stable}"


# ---------------------------------------------------------------------------
# PSGC
# ---------------------------------------------------------------------------


def fetch_psgc_collections(
    acquirer: HttpAcquirer, version: str = "Q2_2024"
) -> tuple[dict[str, list[dict[str, Any]]], list[FetchResult]]:
    """Read every paginated PSGC collection from the BetterGov API."""

    base = f"{BETTERGOV_PSGC_URL}/{version}"
    collections: dict[str, list[dict[str, Any]]] = {}
    responses: list[FetchResult] = []
    for collection in ("regions", "provinces", "municipalities", "barangays"):
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            payload, result = acquirer.get_json(f"{base}/{collection}?page={page}")
            responses.append(result)
            if isinstance(payload, dict) and "results" in payload:
                batch = payload["results"]
            elif isinstance(payload, list):
                batch = payload
            else:
                raise AcquisitionError(
                    f"PSGC {collection} response did not contain a results collection."
                )
            rows.extend(batch)
            next_page = payload.get("next") if isinstance(payload, dict) else None
            if not next_page or page >= 200:
                break
            page += 1
        collections[collection] = rows
    return collections, responses


def psgc_release_content(
    collections: dict[str, list[dict[str, Any]]],
) -> bytes:
    return build_psgc_release_payload(
        version="Q2_2024",
        fetched_at=datetime.now(UTC).isoformat(),
        collections=collections,
    )


def psgc_units(collections: dict[str, list[dict[str, Any]]]):
    return parse_psgc_api_payload(collections)


# ---------------------------------------------------------------------------
# DepEd EBEIS
# ---------------------------------------------------------------------------

EBEIS_URL = "https://ebeis.deped.gov.ph/beis/reports_info/viewMasterList"
EBEIS_REGIONS = {
    "region-i": ("1", "Region I"),
    "region-ii": ("2", "Region II"),
    "region-iii": ("3", "Region III"),
    "region-iva": ("4", "Region IV-A"),
    "mimaropa": ("17", "MIMAROPA"),
    "region-v": ("5", "Region V"),
    "region-vi": ("6", "Region VI"),
    "region-vii": ("7", "Region VII"),
    "region-viii": ("8", "Region VIII"),
    "region-ix": ("9", "Region IX"),
    "region-x": ("10", "Region X"),
    "region-xi": ("11", "Region XI"),
    "region-xii": ("12", "Region XII"),
    "caraga": ("16", "CARAGA"),
    "barmm": ("15", "BARMM"),
    "car": ("14", "CAR"),
    "ncr": ("13", "NCR"),
    "nir": ("18", "NIR"),
    "pso": ("19", "PSO"),
}
EBEIS_PAGE_SIZE = 30
# Minimum spacing between request *starts* across all worker threads. The form
# is a small government application, so concurrency is capped and paced rather
# than replaced by an unbounded burst.
EBEIS_PAGE_DELAY_SECONDS = 0.4
EBEIS_FETCH_WORKERS = 4


class _EbeisPacer:
    """Space request starts by a minimum interval across worker threads."""

    def __init__(self, interval: float) -> None:
        self._interval = max(0.0, interval)
        self._lock = threading.Lock()
        self._next_start = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start)
            self._next_start = start + self._interval
            delay = start - now
        if delay > 0:
            time.sleep(delay)


def _ebeis_page(acquirer: HttpAcquirer, region_id: str, page: int) -> FetchResult:
    result = acquirer.fetch(
        EBEIS_URL,
        method="POST",
        data={
            "page": str(page),
            "region_id": region_id,
            "user_id": "",
            "school_head": "",
        },
    )
    if result.status_code >= 400 or is_blocker_page(result):
        raise AcquisitionError(
            f"DepEd EBEIS page {page} returned HTTP {result.status_code}.", result=result
        )
    return result


def _fetch_ebeis_pages(
    acquirer: HttpAcquirer,
    region_id: str,
    pages: range,
    pacer: _EbeisPacer,
    workers: int,
) -> dict[int, FetchResult]:
    """Fetch one contiguous page range concurrently, keyed by page number."""

    def fetch(page: int) -> tuple[int, FetchResult]:
        pacer.wait()
        return page, _ebeis_page(acquirer, region_id, page)

    results: dict[int, FetchResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, page) for page in pages]
        try:
            for future in as_completed(futures):
                page, result = future.result()
                results[page] = result
        except Exception:
            for future in futures:
                future.cancel()
            raise
    return results


def fetch_ebeis_region(
    acquirer: HttpAcquirer, region_key: str = "ncr"
) -> tuple[bytes, dict[str, Any]]:
    """Fetch every page of one EBEIS result set and return one HTML table.

    The form returns 30 rows per page. Building a single table keeps the source
    record keys stable and lets the existing adapter parse the complete result
    set. The original per-page HTML is not claimed to be an official file; the
    aggregated table is labelled as an acquisition artifact.
    """

    if region_key not in EBEIS_REGIONS:
        raise ValueError(f"Unknown EBEIS region {region_key!r}")
    region_id, region_name = EBEIS_REGIONS[region_key]
    first = _ebeis_page(acquirer, region_id, 1)
    document = first.content.decode("utf-8", errors="replace")
    match = re.search(r"(\d[\d,]*)\s+results found", document)
    if not match:
        raise AcquisitionError("DepEd EBEIS response did not state a result count.")
    total = int(match.group(1).replace(",", ""))
    pages = max(1, (total + EBEIS_PAGE_SIZE - 1) // EBEIS_PAGE_SIZE)
    header, rows = parse_masterlist_html(document)
    all_rows: list[dict[str, Any]] = list(rows)
    page_results = [first]
    # Pages are fetched in small concurrent chunks. Results are still consumed
    # in page order, so a changed header stops the release before later chunks
    # are requested and the aggregate stays deterministic.
    workers = max(1, min(EBEIS_FETCH_WORKERS, pages - 1))
    pacer = _EbeisPacer(EBEIS_PAGE_DELAY_SECONDS)
    for chunk_start in range(2, pages + 1, workers):
        chunk = range(chunk_start, min(chunk_start + workers, pages + 1))
        chunk_results = _fetch_ebeis_pages(acquirer, region_id, chunk, pacer, workers)
        for page in chunk:
            result = chunk_results[page]
            page_results.append(result)
            _header, batch = parse_masterlist_html(result.content.decode("utf-8", errors="replace"))
            if _header != header:
                raise AcquisitionError(
                    f"DepEd EBEIS page {page} changed its table header; acquisition stopped."
                )
            all_rows.extend(batch)
    if len(all_rows) != total:
        raise AcquisitionError(
            f"DepEd EBEIS reported {total} rows but {len(all_rows)} were parsed; "
            "the release was not accepted."
        )
    out = [
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>PhilFacilities EBEIS acquisition artifact</title></head><body>",
        "<p>Aggregated from the public DepEd EBEIS result pages for "
        f"{html.escape(region_name)}. Downloaded {datetime.now(UTC).isoformat()}. "
        "This concatenated table is an acquisition artifact, not an official DepEd file.</p>",
        "<table><thead><tr>",
    ]
    out.extend(f"<th>{html.escape(column)}</th>" for column in header)
    out.append("</tr></thead><tbody>")
    for row in all_rows:
        out.append("<tr>")
        for column in header:
            out.append(f"<td>{html.escape(str(row.get(column) or ''))}</td>")
        out.append("</tr>")
    out.append("</tbody></table></body></html>")
    metadata = {
        "region_key": region_key,
        "region_id": region_id,
        "region_name": region_name,
        "reported_rows": total,
        "fetched_pages": pages,
        "parser_header": header,
    }
    return "".join(out).encode("utf-8"), metadata


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def source_check_payload(dataset: Dataset, check) -> dict[str, Any]:
    return {
        "dataset_id": str(dataset.id),
        "dataset_slug": dataset.slug,
        "checked_at": check.checked_at,
        "status": check.status,
        "url": check.url,
        "http_status": check.http_status,
        "content_type": check.content_type,
        "content_length": check.content_length,
        "sha256": check.sha256,
        "message": check.message,
        "details": check.details,
        "next_check_at": check.next_check_at,
    }


def latest_checks(session: Session) -> list[dict[str, Any]]:
    from philfacilities_api.models import SourceCheck

    rows = session.execute(
        select(SourceCheck, Dataset)
        .join(Dataset, SourceCheck.dataset_id == Dataset.id)
        .order_by(SourceCheck.checked_at.desc())
    ).all()
    seen: set[Any] = set()
    payload = []
    for check, dataset in rows:
        if dataset.id in seen:
            continue
        seen.add(dataset.id)
        payload.append(source_check_payload(dataset, check))
    return payload


def source_review_rows(
    session: Session,
    *,
    days: int = 30,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return the monthly source-register review state for every registered source."""

    moment = now or datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for key, source in sorted(REAL_SOURCES.items()):
        dataset = session.scalars(
            select(Dataset).where(Dataset.slug == source.dataset_slug)
        ).first()
        latest = None
        if dataset is not None:
            latest = session.scalars(
                select(SourceCheck)
                .where(SourceCheck.dataset_id == dataset.id)
                .order_by(SourceCheck.checked_at.desc())
                .limit(1)
            ).first()
        days_since = max((moment - latest.checked_at).days, 0) if latest is not None else None
        rows.append(
            {
                "source_key": key,
                "dataset_slug": source.dataset_slug,
                "agency": source.agency_name,
                "source_url": source.source_url,
                "access_method": source.access_method,
                "update_pattern": source.update_pattern,
                "rights": source.rights,
                "publication_status": source.requested_publication_status,
                "last_checked_at": latest.checked_at.isoformat() if latest else None,
                "last_check_status": latest.status if latest else None,
                "next_check_at": (
                    latest.next_check_at.isoformat()
                    if latest is not None and latest.next_check_at
                    else None
                ),
                "days_since_check": days_since,
                "review_due": days_since is None or days_since >= days,
            }
        )
    return rows


def due_source_keys(
    session: Session,
    *,
    keys: Iterable[str] | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> list[str]:
    """Return registered sources whose next scheduled check is due.

    The schedule is not hardcoded in the command: every check records
    ``next_check_at`` from the source's declared update pattern. Sources with no
    recorded check (or no dataset row yet) are due immediately. ``force`` ignores
    the schedule without changing it.
    """

    moment = now or datetime.now(UTC)
    selected = list(keys) if keys else list(REAL_SOURCES)
    unknown = [key for key in selected if key not in REAL_SOURCES]
    if unknown:
        raise ValueError(f"Unknown source key(s): {', '.join(unknown)}")
    due: list[str] = []
    for key in selected:
        source = REAL_SOURCES[key]
        dataset = session.scalars(
            select(Dataset).where(Dataset.slug == source.dataset_slug)
        ).first()
        if dataset is None:
            due.append(key)
            continue
        latest = session.scalars(
            select(SourceCheck)
            .where(SourceCheck.dataset_id == dataset.id)
            .order_by(SourceCheck.checked_at.desc())
            .limit(1)
        ).first()
        if (
            force
            or latest is None
            or latest.next_check_at is None
            or latest.next_check_at <= moment
        ):
            due.append(key)
    return due
