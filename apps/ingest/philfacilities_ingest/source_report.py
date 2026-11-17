"""data.md deliverables derived from the merged source inventory.

The source inventory answers *what candidates exist*. This module emits the
remaining research outputs required by ``data.md``:

* ``probe-ledger.jsonl`` — one line per tested URL, including every block;
* ``gap-report.md`` — taxonomy category by region matrix with positive and
  negative findings;
* ``blocked-register.md`` — blocked sources, the reason, the official alternate
  route and the authorization a human must obtain;
* ``acquisition-queue.md`` — candidates ranked by coverage, observed record
  count, access, rights clarity and public-interest priority.

Nothing here invents a source, a record count or a permission. A source with no
probe is reported as ``NOT_PROBED``; a source with no observed count keeps
``null``. The reports are derived from the inventory plus an optional region
search ledger produced by real probes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from philfacilities_api.rights import (
    PUBLICATION_INTERNAL_ONLY,
    PUBLICATION_PUBLISHED,
    RIGHTS_APPROVED_ATTRIBUTION,
    RIGHTS_APPROVED_PUBLIC,
    RIGHTS_DENIED,
    RIGHTS_EXPIRED,
    RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
    RIGHTS_RESTRICTED,
    RIGHTS_REVIEW_REQUIRED,
    RIGHTS_UNKNOWN,
)

from .source_inventory import REQUIRED_OUTPUT_FIELDS, summarize_source_inventory

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "var" / "reports"
DEFAULT_REGION_LEDGER = ROOT / "data" / "sources" / "region-search-ledger.json"

# The 18 regions in the current PSGC release used by the platform. data.md's
# "17 regions" predates the 2024 Negros Island Region reinstatement; the
# inventory follows the released geography rather than dropping a real region.
REGIONS: tuple[tuple[str, str], ...] = (
    ("0100000000", "Region I (Ilocos Region)"),
    ("0200000000", "Region II (Cagayan Valley)"),
    ("0300000000", "Region III (Central Luzon)"),
    ("0400000000", "Region IV-A (CALABARZON)"),
    ("0500000000", "Region V (Bicol Region)"),
    ("0600000000", "Region VI (Western Visayas)"),
    ("0700000000", "Region VII (Central Visayas)"),
    ("0800000000", "Region VIII (Eastern Visayas)"),
    ("0900000000", "Region IX (Zamboanga Peninsula)"),
    ("1000000000", "Region X (Northern Mindanao)"),
    ("1100000000", "Region XI (Davao Region)"),
    ("1200000000", "Region XII (SOCCSKSARGEN)"),
    ("1300000000", "National Capital Region (NCR)"),
    ("1400000000", "Cordillera Administrative Region (CAR)"),
    ("1600000000", "Region XIII (Caraga)"),
    ("1700000000", "MIMAROPA Region"),
    ("1800000000", "Negros Island Region (NIR)"),
    ("1900000000", "Bangsamoro Autonomous Region In Muslim Mindanao (BARMM)"),
)

REGION_SHORT = {
    "0100000000": "I",
    "0200000000": "II",
    "0300000000": "III",
    "0400000000": "IV-A",
    "0500000000": "V",
    "0600000000": "VI",
    "0700000000": "VII",
    "0800000000": "VIII",
    "0900000000": "IX",
    "1000000000": "X",
    "1100000000": "XI",
    "1200000000": "XII",
    "1300000000": "NCR",
    "1400000000": "CAR",
    "1600000000": "XIII",
    "1700000000": "MIMAROPA",
    "1800000000": "NIR",
    "1900000000": "BARMM",
}

# Sources whose own publication states a region. An empty tuple means the
# source is national or its region is not stated; the report never guesses.
SOURCE_REGIONS: dict[str, tuple[str, ...]] = {
    "lgu.quezon_city_directories": ("1300000000",),
    "lgu.quezon_city_places": ("1300000000",),
    "lgu.mandaluyong_barangay_directory": ("1300000000",),
    "lgu.pasay_health_centers": ("1300000000",),
    "lgu.cainta_health_centers": ("0400000000",),
}

# Official alternate routes verified in this project or stated by the source
# owner. A route is not a substitute dataset; it is the next authorized place to
# look. ``None`` means no official alternate was verified.
OFFICIAL_ALTERNATES: dict[str, tuple[dict[str, str], ...]] = {
    "doh.nhfr": (
        {
            "title": "NHA GeoServer WFS — DOH HF layer",
            "url": (
                "https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0"
                "&request=GetFeature&typeName=NHA_PH:DOH%20HF&outputFormat=application/json"
            ),
            "note": (
                "Public NHA GeoServer layer tagged 'DOH HF'. 31,016 features observed "
                "on 16 November 2026 with a DOH facility code, type, ownership, PSGC "
                "labels and coordinates; a partial alternate route, not the complete NHFR."
            ),
        },
        {
            "title": "PhilHealth accredited-provider categories",
            "url": "https://www.philhealth.gov.ph/partners/providers/facilities/accredited/",
            "note": (
                "26 provider-category releases already published. Accreditation is "
                "benefit-package-specific and is not a DOH licence or registry record."
            ),
        },
    ),
    "doh.licensed_facilities": (
        {
            "title": "NHA GeoServer WFS — DOH HF layer",
            "url": (
                "https://maps.nha.gov.ph/geoserver/NHA_PH/ows?service=WFS&version=1.0.0"
                "&request=GetFeature&typeName=NHA_PH:DOH%20HF&outputFormat=application/json"
            ),
            "note": "Partial facility layer, not a licensing register.",
        },
    ),
    "psa.psgc": (
        {
            "title": "BetterGov Classification API (PSGC Q2 2024 mirror)",
            "url": "https://statistics.bettergov.ph/api/classification/psgc",
            "note": (
                "43,760 published geographic units. A labelled supplementary snapshot, "
                "not the latest official PSA release."
            ),
        },
    ),
    "deped.school_masterlist": (
        {
            "title": "DepEd EBEIS masterlist result sets (all regions)",
            "url": "https://ebeis.deped.gov.ph/beis/reports_info/masterlist",
            "note": (
                "Public paginated result form covers 19 region groups (18 regions plus "
                "PSO). All region result sets are published with institution-level "
                "fields; school-head names are withheld from normalized records."
            ),
        },
        {
            "title": "DepEd Regional Office VIII public site",
            "url": "https://region8.deped.gov.ph/",
            "note": "Reached HTTP 200 on 16 Nov 2026; regional pages are not a national bulk file.",
        },
        {
            "title": "DepEd Caraga public site",
            "url": "https://caraga.deped.gov.ph/",
            "note": "Reached HTTP 200 on 16 Nov 2026; regional pages are not a national bulk file.",
        },
    ),
    "tesda.providers": (
        {
            "title": "Philippine Geoportal — TESDA TVET providers (NCR), 2022-02-10",
            "url": "https://geoportal.gov.ph/",
            "note": (
                "Catalogue marks download true but the bulk route needs a human form; "
                "no layer-level licence was found. Not acquired."
            ),
        },
    ),
    "dilg.barangay_masterlist": (
        {
            "title": "PSA PSGC geographic universe (via BetterGov mirror)",
            "url": "https://statistics.bettergov.ph/api/classification/psgc",
            "note": (
                "Provides barangay codes and names, not barangay-hall facilities. "
                "Useful as the geography universe, not as a facility register."
            ),
        },
    ),
    "dilg.barangay_halls": (
        {
            "title": "LGU published barangay directories",
            "url": "https://mandaluyong.gov.ph/government/barangays/",
            "note": (
                "Verified example: Mandaluyong published 27 barangay office records. "
                "Coverage is single-LGU; no national hall masterlist was supplied."
            ),
        },
    ),
    "bfp.fire_stations": (
        {
            "title": "FOI release — BFP logistical report (August 2025)",
            "url": "https://www.foi.gov.ph/agencies/bfp/list-of-all-fire-stations/",
            "note": (
                "FOI response links a public Drive folder. A human must review the "
                "attachment scope and terms; no bypass was attempted."
            ),
        },
        {
            "title": "DILG DRRM-PULSE participating-LGU map",
            "url": "https://drrm.ncr.dilg.gov.ph/map",
            "note": (
                "Participating-LGU map categories include fire stations. Feed returned "
                "one command-centre feature in prior inspection; not a bulk register."
            ),
        },
    ),
    "caap.airports": (
        {
            "title": "Philippine Geoportal — National Airport / Airport Control Station",
            "url": "https://geoportal.gov.ph/",
            "note": (
                "Catalogue layers exist but no date, schema, feature count or reuse "
                "terms; download flag false. Not acquired."
            ),
        },
    ),
    "dswd.standards_directories": (
        {
            "title": "DSWD Centers and Residential Care Facilities directory",
            "url": "https://www.dswd.gov.ph/crcf/",
            "note": "76 DSWD-operated CRCFs published; not the Standards Bureau accredited lists.",
        },
    ),
    "dilg.drrm_pulse": (
        {
            "title": "DILG Subaybayan — evacuation-centre project list",
            "url": "https://subaybayan.dilg.gov.ph/",
            "note": (
                "Project records, not operating facilities. Prior inspection returned "
                "HTTP 403; no bypass attempted."
            ),
        },
    ),
    "open_data_philippines": (
        {
            "title": "Open Data Philippines (data.gov.ph)",
            "url": "https://data.gov.ph/",
            "note": (
                "HTTP 200 single-page catalogue shell. The CKAN-style API paths return "
                "the same HTML shell, so no machine-readable catalogue endpoint was "
                "verified."
            ),
        },
    ),
    "emb.air_quality_stations": (
        {
            "title": "EMB regional real-time air monitoring pages",
            "url": "https://ncr.emb.gov.ph/realtimeairmonitoring/",
            "note": "Regional pages exist; station data and reuse terms were not verified.",
        },
    ),
    "lwua.water_districts": (
        {
            "title": "LWUA public site",
            "url": "https://lwua.gov.ph/",
            "note": "HTTP 403 on 16 Nov 2026; no official alternate register verified.",
        },
    ),
    "bmb.protected_areas": (
        {
            "title": "DENR-BMB official site",
            "url": "https://bmb.gov.ph/",
            "note": (
                "Official publisher route to monitor for a public protected-area "
                "download; PAIS is contextual geography, not a facility register."
            ),
        },
    ),
    "dswd.crcf": (
        {
            "title": "DSWD Standards Bureau dated directories",
            "url": "https://standards.dswd.gov.ph/directories-3/",
            "note": (
                "Official dated CRCF and LGU-accredited directory route; no bulk "
                "download was verified from the main CRCF page."
            ),
        },
        {
            "title": "DSWD e-services directory",
            "url": "https://eodb.dswd.gov.ph/directory/",
            "note": "Official public directory route; no bulk download verified.",
        },
    ),
    "marina.ports": (
        {
            "title": "MARINA official site",
            "url": "https://marina.gov.ph/",
            "note": (
                "Official publisher route. The /ports/ path returned HTTP 404; "
                "monitor the site for a published port/terminal registry."
            ),
        },
    ),
    "ppa.ports": (
        {
            "title": "PPA official site",
            "url": "https://ppa.com.ph/",
            "note": (
                "Official publisher route for the port list and revised statistics "
                "manual; the 15 November 2026 PDF artifact remains the release of record."
            ),
        },
    ),
    "nmis.meat_establishments": (
        {
            "title": "NMIS official site",
            "url": "https://www.nmis.gov.ph/",
            "note": (
                "Official publisher route; NARIS currently fails TLS. The dated "
                "4 November 2025 slaughterhouse list is the preserved release."
            ),
        },
        {
            "title": "NMIS dated accredited-establishment list",
            "url": "https://www.nmis.gov.ph/images/pdf/accredited_list/2025/sh20251104.pdf",
            "note": "Dated public PDF used for the 357 published establishment records.",
        },
    ),
}

GOCC_PREFIXES = (
    "ppa",
    "philhealth",
    "sss",
    "nia",
    "lwua",
    "mwss",
    "nwrb",
    "nea",
    "nha",
    "lrta",
    "pnr",
    "caap",
    "marina",
    "pagasa",
    "phivolcs",
    "nfa",
    "pca",
    "bai",
    "pfda",
    "namria",
    "bettergov",
)

BULK_EXTENSIONS = {
    ".pdf": "PDF",
    ".csv": "CSV",
    ".xlsx": "XLSX",
    ".xls": "XLSX",
    ".json": "JSON",
    ".geojson": "GeoJSON",
    ".zip": "ZIP",
    ".shp": "SHP",
    ".parquet": "PARQUET",
}

BLOCKED_ACCESS_STATES = {
    "ACCESS_BLOCKED",
    "FOI_REQUIRED",
    "HUMAN_DOWNLOAD_REQUIRED",
    "AGREEMENT_REQUIRED",
}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _url_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    for extension in BULK_EXTENSIONS:
        if path.endswith(extension):
            return BULK_EXTENSIONS[extension]
    return ""


def _derive_format(source: dict[str, Any]) -> str:
    probes = _as_list(source.get("probes"))
    for probe in sorted(probes, key=lambda item: _as_text(item.get("observed_at")), reverse=True):
        content_type = _as_text(probe.get("content_type")).lower()
        if "json" in content_type:
            return "JSON"
        if "xml" in content_type:
            return "XML"
        if "pdf" in content_type:
            return "PDF"
        if "csv" in content_type:
            return "CSV"
        if "spreadsheet" in content_type or "excel" in content_type:
            return "XLSX"
        if "html" in content_type:
            return "HTML"
    for url in _as_list(source.get("urls")):
        extension = _url_extension(str(url))
        if extension:
            return extension
    evidence = _as_text(source.get("evidence_state")).upper()
    if evidence in {"DISCOVERY_ONLY", "CATALOGUE_CANDIDATE"}:
        return "UNKNOWN"
    if "GIS" in _as_text(source.get("category")).upper():
        return "UNKNOWN"
    return "HTML"


def _derive_access_method(source: dict[str, Any]) -> str:
    access = _as_text(source.get("access_state")).upper()
    urls = " ".join(_as_text(url) for url in _as_list(source.get("urls")))
    if "foi.gov.ph" in urls or access == "FOI_REQUIRED":
        return "FOI"
    if access == "AGREEMENT_REQUIRED":
        return "AGREEMENT"
    if access == "HUMAN_DOWNLOAD_REQUIRED":
        return "HUMAN_DOWNLOAD"
    if "geoserver" in urls.lower() or "service=wfs" in urls.lower():
        return "GIS_LAYER"
    if "/api" in urls.lower() or _derive_format(source) in {"JSON", "API"}:
        return "API"
    for url in _as_list(source.get("urls")):
        if _url_extension(str(url)) in {"PDF", "CSV", "XLSX", "ZIP", "SHP", "GeoJSON"}:
            return "BULK_FILE"
    evidence = _as_text(source.get("evidence_state")).upper()
    if evidence in {"DIRECTORY_CONTENT_VERIFIED", "DIRECTORY_EXAMPLE_VERIFIED"}:
        return "HTML_DIRECTORY"
    if evidence in {"DISCOVERY_ONLY", "CATALOGUE_CANDIDATE"}:
        return "SEARCH_ONLY"
    return "UNKNOWN"


def _derive_agency_level(source: dict[str, Any]) -> str:
    source_id = _as_text(source.get("source_id")).lower()
    custodian = _as_text(source.get("custodian")).lower()
    if source_id.startswith(("lgu.", "quezon-city", "mandaluyong", "pasay", "cainta")):
        return "LGU"
    if any(token in custodian for token in ("city government", "municipal", "provincial")):
        return "LGU"
    if "regional office" in custodian or "region" in custodian:
        return "REGIONAL"
    prefix = source_id.split(".", 1)[0]
    if prefix in GOCC_PREFIXES:
        return "GOCC"
    return "NATIONAL"


def _derive_geographic_scope(source: dict[str, Any]) -> str:
    coverage = _as_text(source.get("coverage_scope")).upper()
    if coverage in {"NATIONAL_OFFICIAL_INVENTORY", "NATIONAL_PARTIAL"}:
        return "NATIONAL"
    if coverage == "REGIONAL":
        return "REGIONAL"
    if coverage in {"PARTICIPATING_LGUS", "SELECTED_LGUS", "SINGLE_LGU"}:
        return "LGU"
    if coverage == "DIRECTORY_SUBSET":
        return "DIRECTORY_SUBSET"
    if coverage == "DISCOVERY_LAYER":
        return "UNKNOWN"
    return "UNKNOWN"


def _probe_summary(source: dict[str, Any]) -> tuple[str, str | None, str]:
    probes = _as_list(source.get("probes"))
    if not probes:
        return "NOT_PROBED", None, "No live probe is recorded for this candidate."
    ordered = sorted(probes, key=lambda item: _as_text(item.get("observed_at")))
    latest = ordered[-1]
    outcomes = [f"{item.get('probe_key') or 'probe'}={item.get('outcome')}" for item in probes]
    status = _as_text(latest.get("outcome")) or "UNKNOWN"
    observed = _as_text(latest.get("observed_at")) or None
    note = "; ".join(outcomes)
    if latest.get("error"):
        note = f"{note}; error={latest['error']}"
    return status, observed, note


def _description(source: dict[str, Any]) -> str:
    parts = [
        _as_text(source.get("title")),
        _as_text(source.get("notes")),
    ]
    text = " — ".join(part for part in parts if part)
    return text[:2000]


def _ownership_semantics(source: dict[str, Any]) -> str:
    category = _as_text(source.get("category"))
    source_id = _as_text(source.get("source_id")).lower()
    if (
        "private" in _as_text(source.get("title")).lower()
        or "private" in _as_text(source.get("notes")).lower()
    ):
        return "MIXED_OR_PRIVATE_PROVIDERS"
    if category in {"HEALTH", "EDUCATION", "SOCIAL_WELFARE"}:
        return "MIXED_GOVERNMENT_AND_PRIVATE_PROVIDERS"
    if source_id.startswith(("lgu.", "quezon-city", "mandaluyong", "pasay", "cainta")):
        return "LGU_GOVERNMENT_FACILITIES"
    return "GOVERNMENT_FACILITIES_OR_UNKNOWN"


def _record_count(source: dict[str, Any]) -> int | None:
    value = source.get("record_count_observed")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    return None


def _publisher_identity(source: dict[str, Any]) -> tuple[str, str, str, str | None]:
    source_id = _as_text(source.get("source_id")).lower()
    custodian = _as_text(source.get("custodian"))
    title = _as_text(source.get("title")).lower()
    combined = f"{source_id} {custodian.casefold()} {title}"
    official_urls = _as_list(source.get("official_urls")) or _as_list(source.get("urls"))
    domain = None
    if official_urls:
        parsed = urlparse(str(official_urls[0]))
        domain = parsed.netloc.casefold() or None
        if domain and domain.startswith("www."):
            domain = domain[4:]

    if "openstreetmap" in combined or source_id.startswith("osm"):
        return custodian or "OpenStreetMap contributors", "community", "COMMUNITY_FALLBACK", domain
    if "bettergov" in combined:
        return custodian or "BetterGov.PH", "non_government_mirror", "OFFICIAL_MIRROR", domain
    if "accredited_providers" in source_id or "provider-category" in title:
        return custodian or "PhilHealth", "government_regulator", "REGULATOR_ACCREDITOR", domain
    return custodian or "UNKNOWN", "government", "OFFICIAL_CUSTODIAN", domain


def _source_url_key(url: str | None) -> str:
    """Normalize a source URL for exact artifact-to-register matching."""

    if not url:
        return ""
    parsed = urlparse(str(url).strip())
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    return f"{host}{parsed.path.rstrip('/')}".casefold()


def attach_published_release_evidence(payload: dict[str, Any], session: Any) -> list[str]:
    """Attach exact published-release evidence to matching inventory candidates.

    The register records what was known when a candidate was researched. A later
    public acquisition can make an ``UNVERIFIED`` or ``ACCESS_BLOCKED`` row stale.
    This function matches an acquired dataset URL to the candidate's primary URL
    (or to a unique alternate URL that no other candidate claims as primary) and
    records the published dataset/release facts on the row. It does not promote
    anything on its own; :func:`enrich_source_inventory` applies the observed
    state while preserving the register value in ``register_*`` fields.
    """

    from philfacilities_api.models import Agency, Dataset, Release
    from sqlalchemy import select

    rows = session.execute(
        select(Release, Dataset, Agency)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .where(Release.ingestion_status == "published")
        .order_by(Release.retrieved_at)
    ).all()
    evidence: dict[str, dict[str, Any]] = {}
    for release, dataset, agency in rows:
        key = _source_url_key(dataset.source_url)
        if not key:
            continue
        entry = evidence.setdefault(
            key,
            {
                "source_url": dataset.source_url,
                "dataset_slugs": set(),
                "release_labels": [],
                "release_count": 0,
                "latest_retrieved_at": None,
                "dataset_publication_states": set(),
                "rights_states": set(),
                "agency_codes": set(),
            },
        )
        entry["dataset_slugs"].add(dataset.slug)
        entry["release_labels"].append(release.source_release_label)
        entry["release_count"] += 1
        entry["latest_retrieved_at"] = (
            release.retrieved_at.isoformat()
            if release.retrieved_at
            else entry["latest_retrieved_at"]
        )
        entry["dataset_publication_states"].add(dataset.publication_status)
        entry["rights_states"].add(dataset.redistribution_status)
        entry["agency_codes"].add(agency.short_code)

    sources = payload.get("sources") or []
    primary_keys = {
        _source_url_key((source.get("official_urls") or source.get("urls") or [None])[0])
        for source in sources
    }
    annotated: list[str] = []
    for source in sources:
        urls = source.get("official_urls") or source.get("urls") or []
        if not urls:
            continue
        match_key = _source_url_key(urls[0])
        if match_key not in evidence:
            alternates = {
                _source_url_key(url)
                for url in urls[1:]
                if _source_url_key(url) in evidence and _source_url_key(url) not in primary_keys
            }
            match_key = alternates.pop() if len(alternates) == 1 else ""
        entry = evidence.get(match_key)
        if entry is None:
            continue
        source["published_release_count"] = entry["release_count"]
        source["published_dataset_slugs"] = sorted(entry["dataset_slugs"])
        source["published_release_labels"] = sorted(entry["release_labels"])
        source["published_latest_retrieved_at"] = entry["latest_retrieved_at"]
        source["published_dataset_publication_states"] = sorted(entry["dataset_publication_states"])
        source["published_rights_states"] = sorted(entry["rights_states"])
        source["published_agency_codes"] = sorted(entry["agency_codes"])
        source["acquisition_evidence"] = "published_release_exact_source_url"
        annotated.append(str(source.get("source_id")))
    return annotated


def enrich_source_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    """Add the data.md output fields without changing preserved evidence."""

    from philfacilities_api.rights import (
        ALL_RIGHTS,
        PUBLICATION_APPROVED,
        PUBLICATION_BLOCKED,
        PUBLICATION_INTERNAL_ONLY,
        PUBLICATION_PUBLISHED,
        PUBLICATION_QUARANTINED,
        RIGHTS_APPROVED_ATTRIBUTION,
        RIGHTS_APPROVED_PUBLIC,
        RIGHTS_DENIED,
        RIGHTS_EXPIRED,
        RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        RIGHTS_RESTRICTED,
        RIGHTS_REVIEW_REQUIRED,
        RIGHTS_UNKNOWN,
    )

    from .skip_reasons import (
        SKIP_REASON_SET,
        from_access_state,
        from_error,
        from_http_status,
        skip_for_source,
    )

    rights_aliases = {
        "UNKNOWN": RIGHTS_UNKNOWN,
        "REVIEW_REQUIRED": RIGHTS_REVIEW_REQUIRED,
        "APPROVED_PUBLIC_REDISTRIBUTION": RIGHTS_APPROVED_PUBLIC,
        "APPROVED_WITH_ATTRIBUTION": RIGHTS_APPROVED_ATTRIBUTION,
        "PUBLICLY_AVAILABLE_VERIFIED": RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        # The research register used PUBLISHED for a source whose records were
        # already published under the platform's public-availability rule. Keep
        # the raw value and normalize it to the controlled rights state.
        "PUBLISHED": RIGHTS_PUBLICLY_AVAILABLE_VERIFIED,
        "RESTRICTED": RIGHTS_RESTRICTED,
        "RESTRICTED_NON_REDISTRIBUTABLE": RIGHTS_RESTRICTED,
        "DENIED": RIGHTS_DENIED,
        "EXPIRED": RIGHTS_EXPIRED,
    }
    publication_aliases = {
        "PUBLISHED": PUBLICATION_PUBLISHED,
        "INTERNAL_ONLY": PUBLICATION_INTERNAL_ONLY,
        "APPROVED": PUBLICATION_APPROVED,
        "QUARANTINED": PUBLICATION_QUARANTINED,
        "BLOCKED": PUBLICATION_BLOCKED,
        "NOT_PUBLISHED": PUBLICATION_INTERNAL_ONLY,
    }
    skipped_access_states = {
        "ACCESS_BLOCKED",
        "UNVERIFIED",
        "FOI_REQUIRED",
        "FOI_ACCESS_CONFIRMED",
        "HUMAN_DOWNLOAD_REQUIRED",
        "HUMAN_ACCESS_REQUIRED",
        "AGREEMENT_REQUIRED",
        "RESTRICTED",
        "EXPLICIT_RESTRICTION",
    }

    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source.setdefault("official_urls", list(_as_list(source.get("urls"))))
        source.setdefault("alternate_urls", [])
        if not source["alternate_urls"]:
            alternates = [
                item.get("url")
                for item in OFFICIAL_ALTERNATES.get(source.get("source_id"), ())
                if item.get("url")
            ]
            source["alternate_urls"] = list(dict.fromkeys(alternates))
        source.setdefault("description", _description(source))
        source.setdefault("agency_level", _derive_agency_level(source))
        source.setdefault("access_method", _derive_access_method(source))
        source.setdefault("format", _derive_format(source))
        source.setdefault("geographic_scope", _derive_geographic_scope(source))
        source.setdefault(
            "publication_state",
            "PUBLISHED"
            if _as_text(source.get("evidence_state")).upper() == "PUBLISHED"
            else "NOT_PUBLISHED",
        )
        probe_status, probe_date, probe_notes = _probe_summary(source)
        source.setdefault("probe_status", probe_status)
        source.setdefault("probe_date", probe_date)
        source.setdefault("probe_notes", probe_notes)
        source.setdefault("data_fields_observed", [])
        source.setdefault("record_count_observed", _record_count(source))
        source.setdefault("ownership_semantics", _ownership_semantics(source))
        source.setdefault("notes", _as_text(source.get("notes")))
        publisher, publisher_type, officiality_tier, publisher_domain = _publisher_identity(source)
        source.setdefault("publisher", publisher)
        source.setdefault("publisher_type", publisher_type)
        source.setdefault("publisher_domain", publisher_domain)
        source.setdefault("officiality_tier", officiality_tier)
        source.setdefault(
            "authority_level",
            "community" if officiality_tier == "COMMUNITY_FALLBACK" else "official",
        )

        # Preserve the register/candidate state as evidence, but expose only the
        # data.md controlled access vocabulary (OPEN/SKIPPED) in the core field.
        # Enrichment must be idempotent: callers may enrich a payload before
        # writing reports and the writer may validate it again.
        already_classified = "access_state_raw" in source and _as_text(
            source.get("access_state")
        ) in {"OPEN", "SKIPPED"}
        source.setdefault("access_state_raw", _as_text(source.get("access_state")) or "UNKNOWN")
        source.setdefault("rights_state_raw", _as_text(source.get("rights_state")) or "UNKNOWN")
        source.setdefault(
            "publication_state_raw", _as_text(source.get("publication_state")) or "UNKNOWN"
        )

        rights_value = rights_aliases.get(
            source["rights_state_raw"].upper(), source["rights_state_raw"].lower()
        )
        source["rights_state"] = rights_value if rights_value in ALL_RIGHTS else RIGHTS_UNKNOWN
        publication_value = publication_aliases.get(
            source["publication_state_raw"].upper(),
            source["publication_state_raw"].lower(),
        )
        source["publication_state"] = (
            publication_value
            if publication_value
            in {
                PUBLICATION_BLOCKED,
                PUBLICATION_INTERNAL_ONLY,
                PUBLICATION_QUARANTINED,
                PUBLICATION_APPROVED,
                PUBLICATION_PUBLISHED,
            }
            else PUBLICATION_INTERNAL_ONLY
        )

        if not already_classified:
            legacy_access = source["access_state_raw"].upper()
            probe_upper = _as_text(probe_status).upper()
            alternate = (
                (source.get("alternate_urls") or [None])[0]
                or _as_text(source.get("next_action"))
                or None
            )
            decision = skip_for_source(_as_text(source.get("source_id")))
            if decision is None and source["publication_state"] != PUBLICATION_PUBLISHED:
                if legacy_access in skipped_access_states:
                    decision = from_access_state(
                        legacy_access,
                        detail=(f"Recorded access state {legacy_access}; probe={probe_status}."),
                        alternate_route=alternate,
                        probe_status=probe_status,
                    )
                elif "403" in probe_upper:
                    decision = from_http_status(
                        403,
                        detail=f"Probe outcome {probe_status}.",
                        alternate_route=alternate,
                        challenge="WAF" in probe_upper,
                    )
                elif "404" in probe_upper:
                    decision = from_http_status(
                        404,
                        detail=f"Probe outcome {probe_status}.",
                        alternate_route=alternate,
                    )
                elif "TRANSPORT_ERROR" in probe_upper or "FAILURE" in probe_upper:
                    decision = from_error(
                        _as_text(source.get("probe_notes")) or probe_status,
                        alternate_route=alternate,
                    )

            if decision is not None:
                source["access_state"] = "SKIPPED"
                source.update(decision.as_dict())
                source["challenge_detected"] = decision.reason in {
                    "WAF_CHALLENGE",
                    "HTTP_403",
                }
            else:
                source["access_state"] = "OPEN"
                source["skip_reason"] = None
                source["skip_detail"] = None
                source["alternate_route"] = None
                source["next_retry_at"] = None
                source["challenge_detected"] = False
        # A later public acquisition can supersede a stale register decision.
        # Apply the exact published-release evidence after the automatic skip
        # decision, and keep the register values in register_* fields. This runs
        # on every enrichment pass so repeated report generation is idempotent.
        published_release_count = source.get("published_release_count") or 0
        if isinstance(published_release_count, int) and published_release_count > 0:
            source.setdefault("register_access_state", source.get("access_state_raw"))
            source.setdefault("register_publication_state", source.get("publication_state_raw"))
            if source.get("skip_reason"):
                source.setdefault("register_skip_reason", source.get("skip_reason"))
                source.setdefault("register_skip_detail", source.get("skip_detail"))
                source.setdefault("register_alternate_route", source.get("alternate_route"))
                source.setdefault("register_next_retry_at", source.get("next_retry_at"))
            source["access_state"] = "OPEN"
            source["publication_state"] = PUBLICATION_PUBLISHED
            source["skip_reason"] = None
            source["skip_detail"] = None
            source["alternate_route"] = None
            source["next_retry_at"] = None
            source["challenge_detected"] = False
            rights_states = source.get("published_rights_states") or []
            if len(rights_states) == 1 and rights_states[0] in ALL_RIGHTS:
                source["rights_state"] = rights_states[0]
            source["publication_evidence"] = "published_release_exact_source_url"
        # A public source whose register evidence already records published
        # records is published under publicly_available_verified. This is applied
        # only after the automated skip decision, so it can never promote an
        # inaccessible source, and it runs on every enrichment pass.
        if source["access_state"] == "OPEN" and source["rights_state_raw"].upper() == "PUBLISHED":
            source["rights_state"] = RIGHTS_PUBLICLY_AVAILABLE_VERIFIED
            source["publication_state"] = PUBLICATION_PUBLISHED
        source.setdefault("robots_allowed", None)

        if source["access_state"] == "SKIPPED" and source["skip_reason"] not in SKIP_REASON_SET:
            raise ValueError(
                f"{source.get('source_id')}: invalid skip reason {source['skip_reason']!r}"
            )
    # The summary is written beside the normalized rows. Recompute it after
    # enrichment so the JSON summary cannot expose the legacy access/rights
    # vocabularies that were preserved only in the ``*_raw`` evidence fields.
    payload["counts"] = summarize_source_inventory(payload)
    return payload


def validate_report_fields(payload: dict[str, Any]) -> list[str]:
    """Return data.md schema violations for an enriched inventory."""

    from philfacilities_api.rights import (
        ALL_RIGHTS,
        PUBLICATION_APPROVED,
        PUBLICATION_BLOCKED,
        PUBLICATION_QUARANTINED,
    )

    from .skip_reasons import SKIP_REASON_SET

    errors: list[str] = []
    publication_states = {
        PUBLICATION_APPROVED,
        PUBLICATION_BLOCKED,
        PUBLICATION_INTERNAL_ONLY,
        PUBLICATION_PUBLISHED,
        PUBLICATION_QUARANTINED,
    }
    for index, source in enumerate(payload.get("sources") or []):
        label = source.get("source_id") or f"source[{index}]"
        for field in REQUIRED_OUTPUT_FIELDS:
            if field not in source:
                errors.append(f"{label}: missing required output field {field}")
        if not _as_list(source.get("official_urls")):
            errors.append(f"{label}: official_urls must be non-empty")
        for field in ("publisher", "publisher_type", "officiality_tier", "authority_level"):
            if not _as_text(source.get(field)):
                errors.append(f"{label}: {field} must be non-empty")
        if not isinstance(source.get("alternate_urls"), list):
            errors.append(f"{label}: alternate_urls must be a list")
        if not isinstance(source.get("data_fields_observed"), list):
            errors.append(f"{label}: data_fields_observed must be a list")
        count = source.get("record_count_observed")
        if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
            errors.append(f"{label}: record_count_observed must be an integer or null")
        for field in ("probe_date",):
            value = source.get(field)
            if value is not None:
                try:
                    date.fromisoformat(str(value))
                except ValueError:
                    errors.append(f"{label}: {field} must be an ISO date or null")
        access = _as_text(source.get("access_state"))
        if access not in {"OPEN", "SKIPPED"}:
            errors.append(f"{label}: access_state must be OPEN or SKIPPED, got {access!r}")
        if access == "SKIPPED":
            if source.get("skip_reason") not in SKIP_REASON_SET:
                errors.append(f"{label}: skipped source has no controlled skip_reason")
            for field in ("skip_detail", "alternate_route", "next_retry_at"):
                if not _as_text(source.get(field)).strip():
                    errors.append(f"{label}: skipped source is missing {field}")
        rights = _as_text(source.get("rights_state"))
        if rights not in ALL_RIGHTS:
            errors.append(f"{label}: rights_state is not a controlled value: {rights!r}")
        publication = _as_text(source.get("publication_state"))
        if publication not in publication_states:
            errors.append(f"{label}: publication_state is not a controlled value: {publication!r}")
    return errors


def build_probe_ledger(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every probe, including probes not matched to a source."""

    ledger: list[dict[str, Any]] = []
    for source in payload.get("sources") or []:
        for probe in _as_list(source.get("probes")):
            ledger.append(
                {
                    "source_id": source.get("source_id"),
                    "custodian": source.get("custodian"),
                    "category": source.get("category"),
                    **probe,
                }
            )
    for probe in payload.get("unmatched_probes") or []:
        ledger.append(
            {
                "source_id": None,
                "custodian": None,
                "category": None,
                **probe,
            }
        )
    ledger.sort(
        key=lambda item: (
            _as_text(item.get("observed_at")),
            _as_text(item.get("source_id")),
            _as_text(item.get("url")),
        )
    )
    return ledger


def load_region_searches(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_REGION_LEDGER
    if not target.exists():
        return {"version": 1, "as_of": None, "searches": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _region_searches_by_code(region_ledger: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in region_ledger.get("searches") or []:
        code = _as_text(entry.get("region_psgc"))
        if code:
            grouped.setdefault(code, []).append(entry)
    return grouped


def _source_regions(source: dict[str, Any]) -> set[str]:
    source_id = _as_text(source.get("source_id"))
    explicit = SOURCE_REGIONS.get(source_id)
    if explicit is not None:
        return set(explicit)
    # A national source covers every region; an unknown subnational one is not
    # placed anywhere by guesswork.
    if _derive_geographic_scope(source) == "NATIONAL":
        return {code for code, _name in REGIONS}
    return set()


def _category_matrix(
    payload: dict[str, Any], region_searches: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, str]]:
    categories = list(payload.get("taxonomy_categories") or [])
    matrix: dict[str, dict[str, str]] = {category: {} for category in categories}
    for category in categories:
        sources = [
            source for source in payload.get("sources") or [] if source.get("category") == category
        ]
        for code, _name in REGIONS:
            has_national = False
            has_regional = False
            has_lgu = False
            for source in sources:
                regions = _source_regions(source)
                if code not in regions:
                    continue
                scope = _derive_geographic_scope(source)
                if scope == "NATIONAL":
                    has_national = True
                elif scope == "REGIONAL":
                    has_regional = True
                elif scope == "LGU":
                    has_lgu = True
            if has_national:
                matrix[category][code] = "N"
            elif has_lgu:
                matrix[category][code] = "L"
            elif has_regional:
                matrix[category][code] = "R"
            elif region_searches.get(code):
                matrix[category][code] = "S"
            else:
                matrix[category][code] = "."
    return matrix


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def build_gap_report(
    payload: dict[str, Any],
    region_ledger: dict[str, Any] | None = None,
) -> str:
    region_ledger = region_ledger or load_region_searches()
    searches = _region_searches_by_code(region_ledger)
    matrix = _category_matrix(payload, searches)
    categories = list(payload.get("taxonomy_categories") or [])
    sources = list(payload.get("sources") or [])

    lines = [
        "# Source gap report",
        "",
        f"**As of:** {payload.get('as_of') or 'UNKNOWN'}",
        f"**Inventory rows:** {len(sources)}",
        f"**Taxonomy categories:** {len(categories)}",
        "",
        "This report records positive and negative source findings. It does not claim that a "
        "category or region has no facility data: an `S` cell means a region-level search was "
        "attempted and no category-specific source was verified in this pass.",
        "",
        "## Matrix legend",
        "",
        "- `N` — a national source is inventoried for the category (coverage may be partial).",
        "- `R` — a regional source is inventoried for the category.",
        "- `L` — an LGU/single-area source is inventoried for the category.",
        "- `S` — a real region-level search was attempted; no category-specific source verified.",
        "- `.` — no source and no recorded region search for this pass.",
        "",
        "## Category by region matrix",
        "",
    ]
    headers = ["Category"] + [REGION_SHORT[code] for code, _name in REGIONS]
    rows = []
    for category in categories:
        rows.append([category] + [matrix[category][code] for code, _name in REGIONS])
    lines.extend(_markdown_table(headers, rows))
    lines.extend(
        [
            "",
            "National sources apply to every region as a matter of scope, not proof that the "
            "source contains a record for that region. LGU sources are placed only where the "
            "source itself states the area.",
            "",
            "## Category findings",
            "",
        ]
    )
    for category in categories:
        category_sources = [s for s in sources if s.get("category") == category]
        national = [s for s in category_sources if _derive_geographic_scope(s) == "NATIONAL"]
        subnational = [s for s in category_sources if _derive_geographic_scope(s) != "NATIONAL"]
        published = [
            s
            for s in category_sources
            if s.get("publication_state") in {PUBLICATION_PUBLISHED, PUBLICATION_INTERNAL_ONLY}
        ]
        lines.append(f"### {category}")
        lines.append("")
        lines.append(
            f"- Sources inventoried: **{len(category_sources)}** "
            f"({len(national)} national, {len(subnational)} subnational/unknown)."
        )
        lines.append(
            f"- Sources with a recorded publication or internal-only release: **{len(published)}**."
        )
        if category_sources:
            lines.append(
                "- Candidates: "
                + ", ".join(
                    f"`{s.get('source_id')}` ({s.get('access_state')})"
                    for s in category_sources[:20]
                )
                + (" …" if len(category_sources) > 20 else "")
            )
        else:
            lines.append("- **Negative finding:** no candidate is inventoried for this category.")
        lines.append("")

    lines.extend(["## Region searches", ""])
    region_rows = []
    for code, name in REGIONS:
        entries = searches.get(code, [])
        if not entries:
            region_rows.append([name, "0", "NOT_SEARCHED", "—"])
            continue
        outcomes = "; ".join(
            f"{entry.get('url')} → {entry.get('http_status') or entry.get('outcome') or 'ERROR'}"
            for entry in entries
        )
        positive = any(
            str(entry.get("outcome") or "").startswith("HTTP_2") or entry.get("http_status") == 200
            for entry in entries
        )
        region_rows.append(
            [
                name,
                str(len(entries)),
                "POSITIVE_OR_PARTIAL" if positive else "NEGATIVE",
                outcomes[:500],
            ]
        )
    lines.extend(_markdown_table(["Region", "Attempts", "Result", "Evidence"], region_rows))
    lines.extend(
        [
            "",
            "## Remaining unknowns",
            "",
            "- The inventory is not a census of all Philippine facility sources. A category can "
            "have a national source whose coverage is partial, stale, or restricted.",
            "- Region cells describe source scope and search attempts, not record counts "
            "per region.",
            "- No cell proves the absence of a dataset; an agency may hold data that is "
            "not published.",
            "- Record counts are `null` unless a retained release or a directly observed "
            "count is recorded.",
            "",
        ]
    )
    return "\n".join(lines)


def build_blocked_register(payload: dict[str, Any]) -> str:
    blocked = []
    for source in payload.get("sources") or []:
        access = _as_text(source.get("access_state")).upper()
        probe_status = _as_text(source.get("probe_status")).upper()
        if access not in BLOCKED_ACCESS_STATES and not any(
            token in probe_status for token in ("HTTP_403", "TRANSPORT_ERROR", "HTTP_404")
        ):
            continue
        if source.get("publication_state") == PUBLICATION_PUBLISHED:
            continue
        blocked.append(source)

    lines = [
        "# Blocked and gated sources",
        "",
        f"**As of:** {payload.get('as_of') or 'UNKNOWN'}",
        "",
        "A block is recorded, not bypassed. No Cloudflare/WAF challenge, CAPTCHA, login, "
        "download form, paywall or robots refusal was circumvented in this pass.",
        "",
    ]
    if not blocked:
        lines.append("No blocked or gated source is recorded in the current inventory.")
        lines.append("")
        return "\n".join(lines)

    for source in sorted(blocked, key=lambda item: _as_text(item.get("source_id"))):
        source_id = _as_text(source.get("source_id"))
        lines.append(f"## `{source_id}` — {source.get('custodian')}")
        lines.append("")
        lines.append(f"- **Category:** {source.get('category')}")
        lines.append(f"- **Access state:** {source.get('access_state')}")
        lines.append(f"- **Rights state:** {source.get('rights_state')}")
        lines.append(f"- **Evidence state:** {source.get('evidence_state')}")
        lines.append(
            f"- **Probe:** {source.get('probe_status')} on {source.get('probe_date') or 'UNKNOWN'}"
        )
        if source.get("probe_notes"):
            lines.append(f"- **Probe notes:** {source.get('probe_notes')}")
        lines.append(f"- **Official URLs:** {', '.join(_as_list(source.get('official_urls')))}")
        alternates = OFFICIAL_ALTERNATES.get(source_id, ())
        if alternates:
            lines.append("- **Official alternate routes:**")
            for alternate in alternates:
                lines.append(
                    f"  - [{alternate['title']}]({alternate['url']}) — {alternate['note']}"
                )
        else:
            lines.append("- **Official alternate routes:** none verified in this pass.")
        if source.get("access_state") == "FOI_REQUIRED":
            lines.append(
                "- **Authorization needed:** a human must submit or review the FOI request and "
                "the response conditions before ingestion."
            )
        elif source.get("access_state") == "AGREEMENT_REQUIRED":
            lines.append(
                "- **Authorization needed:** a responsible officer must review and sign the "
                "data-use agreement; no agreement was accepted by an agent."
            )
        elif source.get("access_state") == "HUMAN_DOWNLOAD_REQUIRED":
            lines.append(
                "- **Authorization needed:** a human must complete the publisher's download "
                "form/terms flow and preserve the exact release."
            )
        else:
            lines.append(
                "- **Authorization needed:** none identified for a public retry; a human must "
                "confirm the publisher's terms before acquisition."
            )
        lines.append(f"- **Next action:** {source.get('next_action')}")
        lines.append("")
    return "\n".join(lines)


COVERAGE_SCORE = {
    "NATIONAL_OFFICIAL_INVENTORY": 5.0,
    "NATIONAL_PARTIAL": 4.0,
    "REGIONAL": 3.5,
    "PARTICIPATING_LGUS": 3.0,
    "SELECTED_LGUS": 2.5,
    "SINGLE_LGU": 2.0,
    "DIRECTORY_SUBSET": 2.0,
    "DISCOVERY_LAYER": 0.5,
    "UNKNOWN_COVERAGE": 0.0,
}
ACCESS_SCORE = {
    "OPEN": 3.0,
    "HUMAN_DOWNLOAD_REQUIRED": 2.0,
    "FOI_REQUIRED": 1.5,
    "AGREEMENT_REQUIRED": 1.0,
    "ACCESS_BLOCKED": 0.5,
    "UNVERIFIED": 0.5,
}
RIGHTS_SCORE = {
    RIGHTS_APPROVED_PUBLIC: 3.0,
    RIGHTS_APPROVED_ATTRIBUTION: 3.0,
    RIGHTS_PUBLICLY_AVAILABLE_VERIFIED: 2.5,
    RIGHTS_REVIEW_REQUIRED: 1.0,
    RIGHTS_UNKNOWN: 0.5,
    RIGHTS_RESTRICTED: 0.0,
    RIGHTS_DENIED: 0.0,
    RIGHTS_EXPIRED: 0.0,
}
PRIORITY_SCORE = {"P0": 3.0, "P1": 2.0, "P2": 1.0, None: 0.0}


def _queue_score(source: dict[str, Any]) -> float:
    coverage = COVERAGE_SCORE.get(_as_text(source.get("coverage_scope")), 0.0)
    access = ACCESS_SCORE.get(_as_text(source.get("access_state")), 0.0)
    rights = RIGHTS_SCORE.get(_as_text(source.get("rights_state")).lower(), 0.0)
    priority = PRIORITY_SCORE.get(source.get("priority"), 0.0)
    count = _record_count(source)
    count_score = min(3.0, math.log10(count + 1) / 2) if count else 0.5
    return round(coverage + access + rights + priority + count_score, 3)


def build_acquisition_queue(payload: dict[str, Any]) -> str:
    candidates = [
        source
        for source in payload.get("sources") or []
        if source.get("publication_state") != PUBLICATION_PUBLISHED
    ]
    ranked = sorted(
        candidates,
        key=lambda source: (-_queue_score(source), _as_text(source.get("source_id"))),
    )
    lines = [
        "# Acquisition queue",
        "",
        f"**As of:** {payload.get('as_of') or 'UNKNOWN'}",
        "",
        "Ranked by coverage scope, observed record count (when known), access state, rights "
        "clarity and recorded priority. A high score is an invitation to verify, not a "
        "publication decision. `record_count_observed = null` means no count was observed.",
        "",
        "## Immediate wins — bulk, API or GIS routes",
        "",
    ]
    immediate = [
        source
        for source in ranked
        if source.get("access_method") in {"API", "BULK_FILE", "GIS_LAYER"}
        and source.get("access_state") in {"OPEN", "UNVERIFIED"}
    ][:15]
    if immediate:
        for source in immediate:
            lines.append(
                f"- `{source.get('source_id')}` — {source.get('title')} "
                f"({source.get('access_method')}, {source.get('coverage_scope')}, "
                f"rights={source.get('rights_state')}). {source.get('next_action')}"
            )
    else:
        lines.append("No open bulk/API/GIS route is currently recorded.")
    lines.extend(["", "## Ranked queue", ""])
    headers = [
        "Rank",
        "Source",
        "Category",
        "Scope",
        "Access",
        "Rights",
        "Count",
        "Score",
        "Next action",
    ]
    rows = []
    for index, source in enumerate(ranked, start=1):
        rows.append(
            [
                str(index),
                f"`{source.get('source_id')}`",
                str(source.get("category")),
                str(source.get("coverage_scope")),
                str(source.get("access_state")),
                str(source.get("rights_state")),
                "null" if _record_count(source) is None else str(_record_count(source)),
                f"{_queue_score(source):.2f}",
                _as_text(source.get("next_action"))[:220],
            ]
        )
    lines.extend(_markdown_table(headers, rows))
    lines.extend(
        [
            "",
            "## Coverage honesty",
            "",
            "- Government, private-provider and public-access-venue semantics stay separate in "
            "the `ownership_semantics` field; a mixed source is not a government census.",
            "- Facility, site, building, unit, project, asset and polygon are distinct in the "
            "register notes; a project list is not a facility list.",
            "- Personal, security-sensitive and critical-infrastructure fields are flagged for "
            "review before publication.",
            "",
        ]
    )
    return "\n".join(lines)


@dataclass
class SourceReportPaths:
    probe_ledger: Path
    gap_report: Path
    acquisition_plan: Path


def write_source_reports(
    payload: dict[str, Any],
    output_dir: str | Path | None = None,
    region_ledger_path: str | Path | None = None,
) -> SourceReportPaths:
    target = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    enrich_source_inventory(payload)
    errors = validate_report_fields(payload)
    if errors:
        raise ValueError("Source inventory is missing data.md fields: " + "; ".join(errors[:20]))

    probe_path = target / "probe-ledger.jsonl"
    # A fresh probe ledger is the richer evidence and must not be replaced by the
    # flatter inventory-derived ledger. Only seed it when no probe has run yet.
    if not probe_path.exists():
        ledger = build_probe_ledger(payload)
        with probe_path.open("w", encoding="utf-8") as handle:
            for entry in ledger:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    region_ledger = load_region_searches(region_ledger_path)
    gap_path = target / "gap-report.md"
    gap_path.write_text(build_gap_report(payload, region_ledger), encoding="utf-8")

    plan_path = target / "acquisition-plan.md"
    plan_path.write_text(build_acquisition_queue(payload), encoding="utf-8")

    return SourceReportPaths(
        probe_ledger=probe_path,
        gap_report=gap_path,
        acquisition_plan=plan_path,
    )
