"""Recurring, read-only probes for sources that are not registered datasets.

Discovery probes do not create datasets, accept terms, or download bulk files. They
record what an official endpoint returned so the source register can be reviewed on a
schedule. A blocked or changed page remains a blocker; it is never bypassed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .acquisition import AcquisitionError, HttpAcquirer, classify_response

DISCOVERY_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class DiscoveryTarget:
    key: str
    agency: str
    dataset: str
    url: str
    note: str


DISCOVERY_TARGETS: tuple[DiscoveryTarget, ...] = (
    DiscoveryTarget(
        key="doh-hfsrb",
        agency="Department of Health — HFSRB",
        dataset="Licensed health facilities",
        url="https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/",
        note="Licensing semantics and reuse terms are not established.",
    ),
    DiscoveryTarget(
        key="psa-classification-api",
        agency="Philippine Statistics Authority",
        dataset="PSGC classification API",
        url="https://classification.psa.gov.ph/psgc",
        note="Data collections may require a token; no token was requested.",
    ),
    DiscoveryTarget(
        key="tesda-assessment-centers",
        agency="Technical Education and Skills Development Authority",
        dataset="Assessment centers",
        url="https://www.tesda.gov.ph/AssessmentCenters",
        note="Provider-level export and reuse terms are not verified.",
    ),
    DiscoveryTarget(
        key="hazardhunter",
        agency="GeoRisk Philippines",
        dataset="HazardHunterPH",
        url="https://hazardhunter.georisk.gov.ph/",
        note="No hazard layer or reuse permission has been acquired.",
    ),
    DiscoveryTarget(
        key="georisk",
        agency="GeoRisk Philippines",
        dataset="GeoAnalytics data and methods",
        url="https://georisk.gov.ph/geoanalytics/data-and-methods",
        note="No layer acquired; TLS failures are recorded, never bypassed.",
    ),
    DiscoveryTarget(
        key="phivolcs",
        agency="PHIVOLCS",
        dataset="Hazard maps portal",
        url="https://maps.phivolcs.dost.gov.ph/",
        note="No layer or reuse permission has been acquired.",
    ),
    DiscoveryTarget(
        key="pagasa-climgrid",
        agency="PAGASA",
        dataset="Climgrid / CliMap",
        url="https://climgridph.pagasa.dost.gov.ph/climapv2/",
        note="No climate layer or reuse permission has been acquired.",
    ),
    DiscoveryTarget(
        key="denr-mgb",
        agency="DENR — Mines and Geosciences Bureau",
        dataset="Geohazard maps",
        url="https://mgb.gov.ph/",
        note="No geohazard layer or reuse permission has been acquired.",
    ),
    DiscoveryTarget(
        key="open-data-ph",
        agency="Open Data Philippines",
        dataset="Dataset catalogue",
        url="https://data.gov.ph/",
        note="A catalogue listing does not establish reuse rights.",
    ),
    DiscoveryTarget(
        key="dilg",
        agency="Department of the Interior and Local Government",
        dataset="LGU facilities",
        url="https://www.dilg.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="bfp",
        agency="Bureau of Fire Protection",
        dataset="Fire stations",
        url="https://bfp.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="pnp",
        agency="Philippine National Police",
        dataset="Police stations",
        url="https://pnp.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="bjmp",
        agency="Bureau of Jail Management and Penology",
        dataset="Jails and detention facilities",
        url="https://bjmp.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="bucor",
        agency="Bureau of Corrections",
        dataset="Correctional institutions",
        url="https://bucor.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="dswd",
        agency="Department of Social Welfare and Development",
        dataset="Residential care and service facilities",
        url="https://www.dswd.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="dpwh",
        agency="Department of Public Works and Highways",
        dataset="Public infrastructure",
        url="https://www.dpwh.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="denr",
        agency="Department of Environment and Natural Resources",
        dataset="Protected areas and environmental facilities",
        url="https://www.denr.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="namria",
        agency="National Mapping and Resource Information Authority",
        dataset="Geographic and cartographic data",
        url="https://www.namria.gov.ph/",
        note="No verified bulk data or reuse permission.",
    ),
    DiscoveryTarget(
        key="nha",
        agency="National Housing Authority",
        dataset="Public housing projects",
        url="https://nha.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="nlp",
        agency="National Library of the Philippines",
        dataset="Public libraries",
        url="https://web.nlp.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="ncca",
        agency="National Commission for Culture and the Arts",
        dataset="Cultural facilities",
        url="https://ncca.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="lwua",
        agency="Local Water Utilities Administration",
        dataset="Water districts and service areas",
        url="https://lwua.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="mwss",
        agency="Metropolitan Waterworks and Sewerage System",
        dataset="Water service infrastructure",
        url="https://mwss.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="dotr",
        agency="Department of Transportation",
        dataset="Transport terminals and facilities",
        url="https://dotr.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
    DiscoveryTarget(
        key="dict",
        agency="Department of Information and Communications Technology",
        dataset="Public digital-service and connectivity facilities",
        url="https://dict.gov.ph/",
        note="No verified facility export or reuse permission.",
    ),
)


def _probe(
    target: DiscoveryTarget,
    acquirer: HttpAcquirer,
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    base: dict[str, Any] = {
        **asdict(target),
        "checked_at": checked_at,
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "status": "request_failed",
        "blocker_page": False,
        "error": None,
    }
    try:
        result = acquirer.fetch(target.url, max_bytes=2 * 1024 * 1024)
    except AcquisitionError as exc:
        base["error"] = str(exc)
        return base

    status = classify_response(result)
    base.update(
        {
            "http_status": result.status_code,
            "final_url": result.final_url,
            "content_type": result.content_type,
            "status": status,
            "blocker_page": status == "access_blocked",
        }
    )
    return base


def probe_discovery_targets(
    targets: Iterable[DiscoveryTarget] | None = None,
    *,
    acquirer: HttpAcquirer | None = None,
) -> list[dict[str, Any]]:
    """Probe discovery targets without mutating the source register."""

    selected = list(targets) if targets is not None else list(DISCOVERY_TARGETS)
    own_client = acquirer is None
    client = acquirer or HttpAcquirer(
        timeout_seconds=DISCOVERY_TIMEOUT_SECONDS,
        retries=1,
    )
    try:
        return [_probe(target, client) for target in selected]
    finally:
        if own_client:
            client.close()
