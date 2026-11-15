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
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from philfacilities_api.models import Dataset, SourceCheck
from philfacilities_api.rights import (
    PUBLICATION_APPROVED,
    PUBLICATION_BLOCKED,
    PUBLICATION_INTERNAL_ONLY,
    RIGHTS_APPROVED_ATTRIBUTION,
    RIGHTS_RESTRICTED,
    RIGHTS_REVIEW_REQUIRED,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..acquisition import (
    AcquisitionError,
    FetchResult,
    HttpAcquirer,
    classify_response,
    conditional_headers,
    default_next_check,
    is_blocker_page,
    last_check,
    record_check,
)
from ..contracts import ReleaseSpec
from ..pipeline import ensure_source
from .bettergov import build_psgc_release_payload, parse_psgc_api_payload
from .deped_ebeis import parse_masterlist_html
from .philhealth import PhilHealthCatalogEntry, parse_catalog

# ---------------------------------------------------------------------------
# Rights evidence
# ---------------------------------------------------------------------------

PHILHEALTH_INDEX_URL = "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/"
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
    "The public EBEIS masterlist has no explicit reuse licence and includes school-head "
    "personal names. It is stored privately for identity/provenance work and is "
    "internal-only pending DepEd terms and privacy review."
)
OFFICIAL_BLOCKED_BASIS = (
    "The official endpoint was reachable only through a human terms/access flow or "
    "returned an access-control challenge. No redistribution decision exists; the "
    "dataset remains blocked."
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
    is_geography: bool = False
    note: str | None = None


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
    "deped-ebeis": RealSource(
        key="deped-ebeis",
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-ebeis-masterlist-ncr",
        dataset_name="DepEd EBEIS school masterlist (NCR result set)",
        source_url="https://ebeis.deped.gov.ph/beis/reports_info/masterlist",
        access_method="public_html_form",
        update_pattern="school year",
        rights=RIGHTS_RESTRICTED,
        rights_basis=DEPED_EBEIS_RIGHTS_BASIS,
        personal_data_status="contains_school_head_names",
        requested_publication_status=PUBLICATION_INTERNAL_ONLY,
        note=(
            "NCR is the verified result set (5,055 rows on 15 Nov 2026). The page has no "
            "explicit reuse terms and contains school-head names."
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
        dataset_slug="ched-hei-directory",
        dataset_name="CHED HEIDA higher-education institution directory",
        source_url="https://heida.ched.gov.ph/hei-directory",
        access_method="public_html_directory",
        update_pattern="unknown",
        rights=RIGHTS_REVIEW_REQUIRED,
        rights_basis=OFFICIAL_BLOCKED_BASIS,
        requested_publication_status=PUBLICATION_BLOCKED,
        note="Public directory pages exist; no verified bulk export or documented API.",
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
        "notes": source.note,
    }
    values.update(overrides)
    return ReleaseSpec(**values)


def monitored_dataset(session: Session, source: RealSource) -> Dataset:
    """Create or fetch the dataset row used by the monitoring ledger."""

    _agency, dataset, _gate = ensure_source(session, source_spec(source))
    return dataset


def registry_dataset_slugs() -> dict[str, str]:
    return {key: source.dataset_slug for key, source in REAL_SOURCES.items()}


# ---------------------------------------------------------------------------
# Source checks
# ---------------------------------------------------------------------------


def _check_url(
    acquirer: HttpAcquirer,
    session: Session,
    source: RealSource,
    *,
    url: str | None = None,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    expected_marker: str | None = None,
) -> tuple[FetchResult, str]:
    dataset = monitored_dataset(session, source)
    previous = last_check(session, dataset.id)
    target = url or source.source_url
    result = acquirer.fetch(
        target,
        method=method,
        data=data,
        headers=conditional_headers(previous),
    )
    status = classify_response(result)
    message = _check_message(source, status, result)
    details: dict[str, Any] = {
        "source_key": source.key,
        "rights": source.rights,
        "access_method": source.access_method,
    }
    if source.key == "philhealth" and status in {"ok", "not_modified"} and result.content:
        try:
            entries = parse_catalog(
                result.content.decode("utf-8", errors="replace"), base_url=url or source.source_url
            )
            details["pdf_links"] = len(entries)
            details["pdf_files"] = [entry.filename for entry in entries]
            if not entries:
                status = "schema_changed"
                message = "PhilHealth index returned no provider-category PDF links."
        except Exception as exc:  # discovery must surface, not hide, a changed index
            status = "schema_changed"
            message = f"PhilHealth index could not be parsed: {exc}"
    if (
        expected_marker
        and status == "ok"
        and expected_marker not in result.content.decode("utf-8", errors="replace")
    ):
        status = "schema_changed"
        message = (
            f"The endpoint returned HTTP {result.status_code} but the expected "
            f"marker {expected_marker!r} was absent; schema or access state changed."
        )
    record_check(
        session,
        dataset=dataset,
        result=result,
        status=status,
        message=message,
        next_check_at=default_next_check(source.update_pattern),
        details=details,
    )
    return result, status


def _check_message(source: RealSource, status: str, result: FetchResult) -> str:
    if status == "ok":
        return f"{source.agency_name} endpoint returned HTTP {result.status_code}."
    if status == "not_modified":
        return "Conditional request returned HTTP 304; the previous release remains current."
    if status == "access_blocked":
        return (
            "The source returned an access/verification page or an authentication denial. "
            "No bypass was attempted; a human-assisted or authorized route is required."
        )
    if status == "not_found":
        return "The published link returned HTTP 404. The previous release, if any, is retained."
    if status == "source_error":
        return f"The source returned HTTP {result.status_code}; the previous release is retained."
    return f"The source returned HTTP {result.status_code}; no release was accepted."


def check_sources(
    session: Session,
    *,
    keys: Iterable[str] | None = None,
    acquirer: HttpAcquirer | None = None,
) -> dict[str, dict[str, Any]]:
    """Check registered sources and append monitoring evidence.

    A blocked source is recorded, never retried with a forged identity. A source
    check does not publish or delete any release.
    """

    selected = list(keys) if keys else list(REAL_SOURCES)
    unknown = [key for key in selected if key not in REAL_SOURCES]
    if unknown:
        raise ValueError(f"Unknown source key(s): {', '.join(unknown)}")
    own_client = acquirer is None
    client = acquirer or HttpAcquirer()
    results: dict[str, dict[str, Any]] = {}
    try:
        for key in selected:
            source = REAL_SOURCES[key]
            try:
                if key == "philhealth":
                    result, status = _check_url(client, session, source)
                elif key == "deped-ebeis":
                    result, status = _check_url(
                        client,
                        session,
                        source,
                        url="https://ebeis.deped.gov.ph/beis/reports_info/viewMasterList",
                        method="POST",
                        data={"page": "1", "region_id": "13", "user_id": "", "school_head": ""},
                        expected_marker="School ID",
                    )
                elif key == "bettergov-psgc":
                    result, status = _check_url(
                        client,
                        session,
                        source,
                        url=f"{BETTERGOV_PSGC_URL}/Q2_2024/regions",
                    )
                elif key == "psa-psgc":
                    result, status = _check_url(
                        client,
                        session,
                        source,
                        url=(
                            "https://psa.gov.ph/system/files/scd/"
                            "PSGC-3Q-2026-Publication-Datafile.xlsx"
                        ),
                    )
                elif key.startswith("osm-"):
                    result, status = _check_url(client, session, source, method="HEAD")
                else:
                    result, status = _check_url(client, session, source)
                session.commit()
                results[key] = {
                    "status": status,
                    "http_status": result.status_code,
                    "url": result.final_url,
                    "blocked": status
                    in {"access_blocked", "not_found", "schema_changed", "source_error"},
                }
            except AcquisitionError as exc:
                session.rollback()
                results[key] = {"status": "request_failed", "error": str(exc), "blocked": True}
            except Exception as exc:  # keep one source failure from hiding the others
                session.rollback()
                results[key] = {"status": "check_failed", "error": str(exc), "blocked": True}
        return results
    finally:
        if own_client:
            client.close()


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


def _dated_midnight(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


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
    "ncr": ("13", "National Capital Region"),
}
EBEIS_PAGE_SIZE = 30


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
    for page in range(2, pages + 1):
        result = _ebeis_page(acquirer, region_id, page)
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
