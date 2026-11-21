"""Real source registry, discovery, and acquisition orchestration.

This module is the single place that records what a real connector is allowed to
do. It contains no parsing logic of its own; it wires the shared acquisition
client to the source-specific adapters and refuses to fake a release when a
source is blocked, changed shape, or has no publication permission.

The declared source metadata lives in :mod:`.registry_data`; this module owns
runtime orchestration and re-exports every data name for backward-compatible
imports such as ``from .registry import REAL_SOURCES``.

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
from datetime import UTC, datetime
from typing import Any

from philfacilities_api.models import Dataset, SourceCheck
from philfacilities_api.rights import (
    PUBLICATION_APPROVED,
    PUBLICATION_BLOCKED,
    PUBLICATION_INTERNAL_ONLY,
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
from ..pipeline import ensure_source
from .bettergov import build_psgc_release_payload, parse_psgc_api_payload
from .deped_ebeis import parse_masterlist_html
from .philhealth import PhilHealthCatalogEntry, parse_catalog
from .registry_data import (
    BETTERGOV_POPULATION_ATTRIBUTION as BETTERGOV_POPULATION_ATTRIBUTION,
)
from .registry_data import (
    BETTERGOV_POPULATION_RIGHTS_BASIS as BETTERGOV_POPULATION_RIGHTS_BASIS,
)
from .registry_data import (
    BETTERGOV_PSGC_ATTRIBUTION as BETTERGOV_PSGC_ATTRIBUTION,
)
from .registry_data import (
    BETTERGOV_PSGC_RIGHTS_BASIS as BETTERGOV_PSGC_RIGHTS_BASIS,
)
from .registry_data import (
    BETTERGOV_PSGC_URL as BETTERGOV_PSGC_URL,
)
from .registry_data import (
    BETTERGOV_STATISTICS_URL as BETTERGOV_STATISTICS_URL,
)
from .registry_data import (
    BIR_ATTRIBUTION as BIR_ATTRIBUTION,
)
from .registry_data import (
    BIR_RAO_URL as BIR_RAO_URL,
)
from .registry_data import (
    BIR_RIGHTS_BASIS as BIR_RIGHTS_BASIS,
)
from .registry_data import (
    BUCOR_ATTRIBUTION as BUCOR_ATTRIBUTION,
)
from .registry_data import (
    BUCOR_OPPF_URL as BUCOR_OPPF_URL,
)
from .registry_data import (
    BUCOR_RIGHTS_BASIS as BUCOR_RIGHTS_BASIS,
)
from .registry_data import (
    CAINTA_ATTRIBUTION as CAINTA_ATTRIBUTION,
)
from .registry_data import (
    CAINTA_HEALTH_URL as CAINTA_HEALTH_URL,
)
from .registry_data import (
    CAINTA_RIGHTS_BASIS as CAINTA_RIGHTS_BASIS,
)
from .registry_data import (
    CHED_HEIDA_ATTRIBUTION as CHED_HEIDA_ATTRIBUTION,
)
from .registry_data import (
    CHED_HEIDA_DIRECTORY_URL as CHED_HEIDA_DIRECTORY_URL,
)
from .registry_data import (
    CHED_HEIDA_RIGHTS_BASIS as CHED_HEIDA_RIGHTS_BASIS,
)
from .registry_data import (
    DEPED_BUKAS_ATTRIBUTION as DEPED_BUKAS_ATTRIBUTION,
)
from .registry_data import (
    DEPED_BUKAS_RIGHTS_BASIS as DEPED_BUKAS_RIGHTS_BASIS,
)
from .registry_data import (
    DEPED_EBEIS_RIGHTS_BASIS as DEPED_EBEIS_RIGHTS_BASIS,
)
from .registry_data import (
    DEPED_MAPAARALAN_ATTRIBUTION as DEPED_MAPAARALAN_ATTRIBUTION,
)
from .registry_data import (
    DEPED_MAPAARALAN_RIGHTS_BASIS as DEPED_MAPAARALAN_RIGHTS_BASIS,
)
from .registry_data import (
    DEPED_MASTERLIST_ATTRIBUTION as DEPED_MASTERLIST_ATTRIBUTION,
)
from .registry_data import (
    DEPED_MASTERLIST_DETAIL_ATTRIBUTION as DEPED_MASTERLIST_DETAIL_ATTRIBUTION,
)
from .registry_data import (
    DEPED_MASTERLIST_DETAIL_RIGHTS_BASIS as DEPED_MASTERLIST_DETAIL_RIGHTS_BASIS,
)
from .registry_data import (
    DEPED_MASTERLIST_RIGHTS_BASIS as DEPED_MASTERLIST_RIGHTS_BASIS,
)
from .registry_data import (
    DEPED_SHS_ARCGIS_ATTRIBUTION as DEPED_SHS_ARCGIS_ATTRIBUTION,
)
from .registry_data import (
    DEPED_SHS_ARCGIS_RIGHTS_BASIS as DEPED_SHS_ARCGIS_RIGHTS_BASIS,
)
from .registry_data import (
    DOE_LOEPP_ATTRIBUTION as DOE_LOEPP_ATTRIBUTION,
)
from .registry_data import (
    DOE_LOEPP_RIGHTS_BASIS as DOE_LOEPP_RIGHTS_BASIS,
)
from .registry_data import (
    DOH_NHFR_ATTRIBUTION as DOH_NHFR_ATTRIBUTION,
)
from .registry_data import (
    DOH_NHFR_RIGHTS_BASIS as DOH_NHFR_RIGHTS_BASIS,
)
from .registry_data import (
    DSWD_CRCF_ATTRIBUTION as DSWD_CRCF_ATTRIBUTION,
)
from .registry_data import (
    DSWD_CRCF_RIGHTS_BASIS as DSWD_CRCF_RIGHTS_BASIS,
)
from .registry_data import (
    DSWD_CRCF_URL as DSWD_CRCF_URL,
)
from .registry_data import (
    DTI_NEGOSYO_API_URL as DTI_NEGOSYO_API_URL,
)
from .registry_data import (
    DTI_NEGOSYO_ATTRIBUTION as DTI_NEGOSYO_ATTRIBUTION,
)
from .registry_data import (
    DTI_NEGOSYO_FINDER_URL as DTI_NEGOSYO_FINDER_URL,
)
from .registry_data import (
    DTI_NEGOSYO_RIGHTS_BASIS as DTI_NEGOSYO_RIGHTS_BASIS,
)
from .registry_data import (
    DTI_NEGOSYO_TERMS_URL as DTI_NEGOSYO_TERMS_URL,
)
from .registry_data import (
    EBEIS_MASTERLIST_URL as EBEIS_MASTERLIST_URL,
)
from .registry_data import (
    LRTA_ATTRIBUTION as LRTA_ATTRIBUTION,
)
from .registry_data import (
    LRTA_DISTANCE_URL as LRTA_DISTANCE_URL,
)
from .registry_data import (
    LRTA_RIGHTS_BASIS as LRTA_RIGHTS_BASIS,
)
from .registry_data import (
    MANDALUYONG_ATTRIBUTION as MANDALUYONG_ATTRIBUTION,
)
from .registry_data import (
    MANDALUYONG_DIRECTORY_URL as MANDALUYONG_DIRECTORY_URL,
)
from .registry_data import (
    MANDALUYONG_RIGHTS_BASIS as MANDALUYONG_RIGHTS_BASIS,
)
from .registry_data import (
    MRT3_ATTRIBUTION as MRT3_ATTRIBUTION,
)
from .registry_data import (
    MRT3_RIGHTS_BASIS as MRT3_RIGHTS_BASIS,
)
from .registry_data import (
    MRT3_STATIONS_URL as MRT3_STATIONS_URL,
)
from .registry_data import (
    NATIONAL_MUSEUM_ATTRIBUTION as NATIONAL_MUSEUM_ATTRIBUTION,
)
from .registry_data import (
    NATIONAL_MUSEUM_RIGHTS_BASIS as NATIONAL_MUSEUM_RIGHTS_BASIS,
)
from .registry_data import (
    NATIONAL_MUSEUM_URL as NATIONAL_MUSEUM_URL,
)
from .registry_data import (
    NBI_ATTRIBUTION as NBI_ATTRIBUTION,
)
from .registry_data import (
    NBI_OFFICES_URL as NBI_OFFICES_URL,
)
from .registry_data import (
    NBI_RIGHTS_BASIS as NBI_RIGHTS_BASIS,
)
from .registry_data import (
    NHA_ATTRIBUTION as NHA_ATTRIBUTION,
)
from .registry_data import (
    NHA_DOH_HF_URL as NHA_DOH_HF_URL,
)
from .registry_data import (
    NHA_LANDHOLDINGS_URL as NHA_LANDHOLDINGS_URL,
)
from .registry_data import (
    NHA_PROJECT_URL as NHA_PROJECT_URL,
)
from .registry_data import (
    NHA_RIGHTS_BASIS as NHA_RIGHTS_BASIS,
)
from .registry_data import (
    NLP_ATTRIBUTION as NLP_ATTRIBUTION,
)
from .registry_data import (
    NLP_LIBRARIES_URL as NLP_LIBRARIES_URL,
)
from .registry_data import (
    NLP_RIGHTS_BASIS as NLP_RIGHTS_BASIS,
)
from .registry_data import (
    NMIS_NARIS_ATTRIBUTION as NMIS_NARIS_ATTRIBUTION,
)
from .registry_data import (
    NMIS_NARIS_RIGHTS_BASIS as NMIS_NARIS_RIGHTS_BASIS,
)
from .registry_data import (
    NMIS_NARIS_URL as NMIS_NARIS_URL,
)
from .registry_data import (
    OFFICIAL_BLOCKED_BASIS as OFFICIAL_BLOCKED_BASIS,
)
from .registry_data import (
    OSM_ATTRIBUTION as OSM_ATTRIBUTION,
)
from .registry_data import (
    OSM_RIGHTS_BASIS as OSM_RIGHTS_BASIS,
)
from .registry_data import (
    PAGASA_AWS_ATTRIBUTION as PAGASA_AWS_ATTRIBUTION,
)
from .registry_data import (
    PAGASA_AWS_RIGHTS_BASIS as PAGASA_AWS_RIGHTS_BASIS,
)
from .registry_data import (
    PAGASA_AWS_URL as PAGASA_AWS_URL,
)
from .registry_data import (
    PASAY_ATTRIBUTION as PASAY_ATTRIBUTION,
)
from .registry_data import (
    PASAY_HEALTH_URL as PASAY_HEALTH_URL,
)
from .registry_data import (
    PASAY_RIGHTS_BASIS as PASAY_RIGHTS_BASIS,
)
from .registry_data import (
    PHILHEALTH_ATTRIBUTION as PHILHEALTH_ATTRIBUTION,
)

# Re-export the declared registry data so every existing import path stays valid.
from .registry_data import (
    PHILHEALTH_INDEX_URL as PHILHEALTH_INDEX_URL,
)
from .registry_data import (
    PHILHEALTH_OFFICE_ATTRIBUTION as PHILHEALTH_OFFICE_ATTRIBUTION,
)
from .registry_data import (
    PHILHEALTH_OFFICE_DIRECTORY_URL as PHILHEALTH_OFFICE_DIRECTORY_URL,
)
from .registry_data import (
    PHILHEALTH_OFFICE_RIGHTS_BASIS as PHILHEALTH_OFFICE_RIGHTS_BASIS,
)
from .registry_data import (
    PHILHEALTH_RIGHTS_BASIS as PHILHEALTH_RIGHTS_BASIS,
)
from .registry_data import (
    PHLPOST_RIGHTS_BASIS as PHLPOST_RIGHTS_BASIS,
)
from .registry_data import (
    PHLPOST_URL as PHLPOST_URL,
)
from .registry_data import (
    PPA_ATTRIBUTION as PPA_ATTRIBUTION,
)
from .registry_data import (
    PPA_PORT_LIST_URL as PPA_PORT_LIST_URL,
)
from .registry_data import (
    PPA_RIGHTS_BASIS as PPA_RIGHTS_BASIS,
)
from .registry_data import (
    PRC_ATTRIBUTION as PRC_ATTRIBUTION,
)
from .registry_data import (
    PRC_LOCATOR_URL as PRC_LOCATOR_URL,
)
from .registry_data import (
    PRC_RIGHTS_BASIS as PRC_RIGHTS_BASIS,
)
from .registry_data import (
    QUEZON_CITY_ATTRIBUTION as QUEZON_CITY_ATTRIBUTION,
)
from .registry_data import (
    QUEZON_CITY_DIRECTORY_URL as QUEZON_CITY_DIRECTORY_URL,
)
from .registry_data import (
    QUEZON_CITY_PLACES_ATTRIBUTION as QUEZON_CITY_PLACES_ATTRIBUTION,
)
from .registry_data import (
    QUEZON_CITY_PLACES_RIGHTS_BASIS as QUEZON_CITY_PLACES_RIGHTS_BASIS,
)
from .registry_data import (
    QUEZON_CITY_PLACES_URL as QUEZON_CITY_PLACES_URL,
)
from .registry_data import (
    QUEZON_CITY_RIGHTS_BASIS as QUEZON_CITY_RIGHTS_BASIS,
)
from .registry_data import (
    REAL_SOURCES as REAL_SOURCES,
)
from .registry_data import (
    SSS_ATTRIBUTION as SSS_ATTRIBUTION,
)
from .registry_data import (
    SSS_BRANCH_LOCATOR_URL as SSS_BRANCH_LOCATOR_URL,
)
from .registry_data import (
    SSS_RIGHTS_BASIS as SSS_RIGHTS_BASIS,
)
from .registry_data import (
    RealSource as RealSource,
)
from .registry_data import (
    source_spec as source_spec,
)


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
    "public_archived_zip",
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
