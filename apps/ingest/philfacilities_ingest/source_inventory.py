"""Build the master inventory of researched source candidates.

The register in ``expand/docs/03-SOURCE-REGISTER.md`` is the evidence narrative,
``expand/source-candidates.json`` is the curator-reviewed normalized index, and
the probe ledgers under ``docs/operations/evidence`` record live reachability.
This module merges those three views into one validated JSON/CSV inventory.

An inventory row is still a *candidate*, not an acquired dataset. Acquisition,
schema verification, rights review, release checksums and publication remain
separate steps. The merged inventory deliberately keeps negative evidence
(HTTP 403, DNS failure, TLS failure, robots disallow) instead of hiding it.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTER_PATH = ROOT / "expand" / "docs" / "03-SOURCE-REGISTER.md"
DEFAULT_CANDIDATES_PATH = ROOT / "expand" / "source-candidates.json"
DEFAULT_PROBES_PATH = (
    ROOT
    / "docs"
    / "operations"
    / "evidence"
    / "2026-11-16-category-source-search"
    / "probes-2026-11-16.txt"
)
DEFAULT_JSON_OUTPUT = ROOT / "expand" / "data" / "source-inventory.json"
DEFAULT_CSV_OUTPUT = ROOT / "expand" / "data" / "source-inventory.csv"

# Matches the taxonomy in expand/docs/02-FACILITY-TAXONOMY.md §3.
TAXONOMY_CATEGORIES = (
    "GOV_ADMIN",
    "COMMUNITY",
    "EDUCATION",
    "HEALTH",
    "EMERGENCY_DRM",
    "SOCIAL_WELFARE",
    "SPORTS_RECREATION",
    "PUBLIC_SPACE",
    "CULTURE_KNOWLEDGE",
    "PUBLIC_COMMERCE",
    "UTILITIES_SANITATION",
    "TRANSPORT",
    "ENVIRONMENT_AGRI",
    "HOUSING_SETTLEMENT",
    "JUSTICE_CORRECTIONS",
    "OTHER_QUALIFYING",
)

REQUIRED_FIELDS = (
    "source_id",
    "custodian",
    "title",
    "category",
    "urls",
    "evidence_state",
    "access_state",
    "rights_state",
    "coverage_scope",
    "priority",
    "next_action",
    "tracker_ids",
    "last_verified",
    "provenance",
)

EVIDENCE_RANK = {
    "DISCOVERED": 0,
    "DISCOVERY_ONLY": 0,
    "CATALOGUE_CANDIDATE": 1,
    "OFFICIAL_LAW_VERIFIED": 1,
    "PUBLIC_FEED_INSPECTED_NOT_USABLE": 2,
    "OFFICIAL_PORTAL_VERIFIED": 2,
    "DIRECTORY_EXAMPLE_VERIFIED": 3,
    "DIRECTORY_CONTENT_VERIFIED": 4,
    "RECORDS_OBSERVED": 4,
    "FILE_DOCUMENT_VERIFIED": 5,
    "FOI_ACCESS_CONFIRMED": 5,
    "FOI_LIMITATION_CONFIRMED": 5,
    "ACQUIRED": 6,
    "SCHEMA_VERIFIED": 7,
    "PUBLISHED": 8,
}

EVIDENCE_LABELS = {
    "ACQUIRED AND PUBLISHED": "PUBLISHED",
    "PUBLISHED": "PUBLISHED",
    "ACQUIRED": "ACQUIRED",
    "SCHEMA VERIFIED": "SCHEMA_VERIFIED",
    "FILE/DOCUMENT VERIFIED": "FILE_DOCUMENT_VERIFIED",
    "DIRECTORY CONTENT VERIFIED": "DIRECTORY_CONTENT_VERIFIED",
    "DIRECTORY EXAMPLE VERIFIED": "DIRECTORY_EXAMPLE_VERIFIED",
    "OFFICIAL PORTAL VERIFIED": "OFFICIAL_PORTAL_VERIFIED",
    "OFFICIAL LAW VERIFIED": "OFFICIAL_LAW_VERIFIED",
    "FOI ACCESS CONFIRMED": "FOI_ACCESS_CONFIRMED",
    "FOI LIMITATION CONFIRMED": "FOI_LIMITATION_CONFIRMED",
    "FOI LIMITATION": "FOI_LIMITATION_CONFIRMED",
    "CATALOGUE CANDIDATE": "CATALOGUE_CANDIDATE",
    "PUBLIC FEED INSPECTED — NOT USABLE": "PUBLIC_FEED_INSPECTED_NOT_USABLE",
    "PUBLIC FEED INSPECTED - NOT USABLE": "PUBLIC_FEED_INSPECTED_NOT_USABLE",
    "DISCOVERY ONLY": "DISCOVERY_ONLY",
    "OFFICIAL MAP/PORTAL DISCOVERED": "DISCOVERED",
    "DISCOVERY/CATALOGUE TARGET": "CATALOGUE_CANDIDATE",
}

# Prefix rules are a fallback for sources that are not yet in the candidate
# registry. Explicit overrides below win.
CATEGORY_PREFIXES = (
    ("deped", "EDUCATION"),
    ("ched", "EDUCATION"),
    ("tesda", "EDUCATION"),
    ("doh", "HEALTH"),
    ("philhealth", "HEALTH"),
    ("dswd", "SOCIAL_WELFARE"),
    ("eccd", "SOCIAL_WELFARE"),
    ("nlp", "CULTURE_KNOWLEDGE"),
    ("nationalmuseum", "CULTURE_KNOWLEDGE"),
    ("ncca", "CULTURE_KNOWLEDGE"),
    ("nhcp", "CULTURE_KNOWLEDGE"),
    ("dilg", "COMMUNITY"),
    ("lgu", "COMMUNITY"),
    ("dpwh", "GOV_ADMIN"),
    ("bfp", "EMERGENCY_DRM"),
    ("pnp", "EMERGENCY_DRM"),
    ("ocd", "EMERGENCY_DRM"),
    ("drrm", "EMERGENCY_DRM"),
    ("bjmp", "JUSTICE_CORRECTIONS"),
    ("bucor", "JUSTICE_CORRECTIONS"),
    ("doj", "JUSTICE_CORRECTIONS"),
    ("judiciary", "JUSTICE_CORRECTIONS"),
    ("bir", "GOV_ADMIN"),
    ("dti", "GOV_ADMIN"),
    ("phlpost", "GOV_ADMIN"),
    ("prc", "GOV_ADMIN"),
    ("sss", "GOV_ADMIN"),
    ("nbi", "GOV_ADMIN"),
    ("govph", "GOV_ADMIN"),
    ("ppa", "TRANSPORT"),
    ("caap", "TRANSPORT"),
    ("marina", "TRANSPORT"),
    ("dotr", "TRANSPORT"),
    ("pnr", "TRANSPORT"),
    ("lrta", "TRANSPORT"),
    ("pcg", "TRANSPORT"),
    ("nmis", "PUBLIC_COMMERCE"),
    ("pfda", "ENVIRONMENT_AGRI"),
    ("da", "ENVIRONMENT_AGRI"),
    ("bfar", "ENVIRONMENT_AGRI"),
    ("nfa", "ENVIRONMENT_AGRI"),
    ("pca", "ENVIRONMENT_AGRI"),
    ("nia", "ENVIRONMENT_AGRI"),
    ("bai", "ENVIRONMENT_AGRI"),
    ("nha", "HOUSING_SETTLEMENT"),
    ("shfc", "HOUSING_SETTLEMENT"),
    ("dhsud", "HOUSING_SETTLEMENT"),
    ("pagasa", "ENVIRONMENT_AGRI"),
    ("emb", "ENVIRONMENT_AGRI"),
    ("bmb", "ENVIRONMENT_AGRI"),
    ("denr_mgb", "ENVIRONMENT_AGRI"),
    ("lwua", "UTILITIES_SANITATION"),
    ("mwss", "UTILITIES_SANITATION"),
    ("nwrb", "UTILITIES_SANITATION"),
    ("doe", "UTILITIES_SANITATION"),
    ("nea", "UTILITIES_SANITATION"),
    ("geoportal", "OTHER_QUALIFYING"),
    ("phivolcs", "OTHER_QUALIFYING"),
    ("psa", "OTHER_QUALIFYING"),
    ("open_data_philippines", "OTHER_QUALIFYING"),
    ("bettergov", "OTHER_QUALIFYING"),
)

CATEGORY_OVERRIDES = {
    "dilg.drrm_pulse": "EMERGENCY_DRM",
    "dilg.evacuation_ncr_foi": "EMERGENCY_DRM",
    "dilg.subaybayan_evacuation_projects": "EMERGENCY_DRM",
    "dilg.subaybayan_lime20": "EMERGENCY_DRM",
    "dilg.public_markets": "PUBLIC_COMMERCE",
    "dilg.barangay_halls": "GOV_ADMIN",
    "dilg.barangay_masterlist": "GOV_ADMIN",
    "lgu.quezon_city_places": "PUBLIC_SPACE",
    "lgu.market_and_abattoir_directories": "PUBLIC_COMMERCE",
    "lgu.cainta_health_centers": "HEALTH",
    "lgu.pasay_health_centers": "HEALTH",
    "lgu.mandaluyong_barangay_directory": "GOV_ADMIN",
    "dpwh.infrastructure_projects": "GOV_ADMIN",
    "dpwh.transparency_projects": "GOV_ADMIN",
    "dti.shared_service_facilities": "OTHER_QUALIFYING",
    "nmis.meat_establishments": "PUBLIC_COMMERCE",
    "pfda.fish_ports": "ENVIRONMENT_AGRI",
    "emb.air_quality_stations": "ENVIRONMENT_AGRI",
    "bmb.protected_areas": "ENVIRONMENT_AGRI",
    "geoportal.facility_layers": "OTHER_QUALIFYING",
    "open_data_philippines": "OTHER_QUALIFYING",
}

CUSTODIAN_FALLBACKS = {
    "dpwh.transparency_projects": "DPWH",
    "dilg.subaybayan_lime20": "DILG",
    "open_data_philippines": "Open Data Philippines / DICT",
    "bettergov.open_data": "BetterGov",
    "psa.psgc": "Philippine Statistics Authority",
    "psa.openstat": "Philippine Statistics Authority",
    "bettergov.statistics": "BetterGov",
    "dilg.barangay_masterlist": "DILG",
}

MONTH_PATTERN = (
    r"January|February|March|April|May|June|July|August|September|October|"
    r"November|December"
)

SECTION_RE = re.compile(r"^#\s+(?P<letter>[A-M])\.\s+(?P<title>.+?)\s*$")
ROW_RE = re.compile(
    r"^\|\s*`(?P<source_id>[a-z0-9][a-z0-9_.-]*)`\s*"
    r"(?:[\u2014\u2013-]\s*(?P<custodian>[^|]*?))?\s*\|"
)
LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
PRIORITY_RE = re.compile(r"\b(P[012])\b")
TRACKER_RE = re.compile(r"\b(AF\d+-\d+)\b")
DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})\s+(\d{{4}})\b")
BASELINE_RE = re.compile(rf"Research baseline:\*\*\s*(\d{{1,2}})\s+({MONTH_PATTERN})\s+(\d{{4}})")
PROBE_LINE_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\t(?P<url>https?://[^\t]+)\t(?P<rest>.*)$")
PROBE_STATUS_RE = re.compile(
    r"^(?P<status>\d{3})\t(?P<content_type>[^\t]*)\t(?P<final_url>https?://[^\t]*)\t(?P<size>\d+)\s*$"
)

MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


@dataclass
class RegisterRow:
    source_id: str
    custodian: str
    title: str
    urls: list[str]
    section: str
    cells: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class ProbeObservation:
    probe_key: str
    url: str
    observed_at: str
    status_code: int | None = None
    content_type: str | None = None
    final_url: str | None = None
    size_bytes: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_key": self.probe_key,
            "observed_at": self.observed_at,
            "url": self.url,
            "http_status": self.status_code,
            "content_type": self.content_type,
            "final_url": self.final_url,
            "size_bytes": self.size_bytes,
            "error": self.error,
            "outcome": _probe_outcome(self),
        }


def _probe_outcome(probe: ProbeObservation) -> str:
    if probe.status_code == 403:
        return "HTTP_403"
    if probe.status_code in (None, 0):
        return "TRANSPORT_ERROR"
    if probe.status_code == 200:
        return "HTTP_200"
    return f"HTTP_{probe.status_code}"


def _normalise_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _clean_markdown(text: str) -> str:
    text = LINK_RE.sub(lambda match: match.group("label"), text)
    text = BACKTICK_RE.sub(lambda match: match.group(1), text)
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip(" .;|")


def _parse_long_date(day: str, month: str, year: str) -> str:
    return date(int(year), MONTHS[month], int(day)).isoformat()


def _register_baseline(text: str) -> str:
    match = BASELINE_RE.search(text)
    if match:
        return _parse_long_date(*match.groups())
    return date.today().isoformat()


def _latest_date(text: str, fallback: str) -> str:
    dates = [_parse_long_date(*match.groups()) for match in DATE_RE.finditer(text)]
    return max(dates) if dates else fallback


def parse_register(path: str | Path | None = None) -> tuple[list[RegisterRow], str]:
    target = Path(path) if path is not None else DEFAULT_REGISTER_PATH
    text = target.read_text(encoding="utf-8")
    baseline = _register_baseline(text)
    rows: list[RegisterRow] = []
    section: str | None = None
    for line in text.splitlines():
        section_match = SECTION_RE.match(line)
        if section_match:
            section = f"{section_match.group('letter')}. {section_match.group('title')}"
            continue
        if section is None or not line.startswith("|"):
            continue
        row_match = ROW_RE.match(line)
        if not row_match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        source_id = row_match.group("source_id")
        custodian = (row_match.group("custodian") or "").strip()
        custodian = CUSTODIAN_FALLBACKS.get(source_id, custodian)
        if not custodian:
            custodian = source_id.split(".", 1)[0].replace("_", " ").title()
        links = [
            {"label": _clean_markdown(match.group("label")), "url": match.group("url")}
            for match in LINK_RE.finditer(line)
        ]
        title = links[0]["label"] if links else _clean_markdown(cells[1] if len(cells) > 1 else "")
        if not title:
            title = source_id
        rows.append(
            RegisterRow(
                source_id=source_id,
                custodian=custodian,
                title=title,
                urls=list(dict.fromkeys(link["url"] for link in links)),
                section=section,
                cells=cells,
                text=" ".join(cells),
            )
        )
    return rows, baseline


def _evidence_state(text: str, cells: list[str] | None = None) -> str:
    upper = text.upper()
    found: list[str] = []
    # Evidence labels in the register are normally backticked. Restricting the
    # first pass to backticked spans avoids treating prose such as "previously
    # published government data" as a release of this source.
    for span in BACKTICK_RE.findall(text):
        state = EVIDENCE_LABELS.get(span.strip().upper())
        if state:
            found.append(state)
    if not found:
        # A few rows spell the label without backticks. Only strong multi-word
        # phrases are accepted; a bare "published" is never evidence.
        for label, state in EVIDENCE_LABELS.items():
            if label in {"PUBLISHED", "ACQUIRED"}:
                continue
            if label in upper:
                found.append(state)
    if not found:
        return "DISCOVERED"
    return max(found, key=lambda state: EVIDENCE_RANK.get(state, 0))


def _publication_state(text: str, evidence_state: str) -> str:
    upper = text.upper()
    if evidence_state != "PUBLISHED":
        return "NOT_PUBLISHED"
    if "INTERNAL" in upper:
        return "INTERNAL_ONLY"
    return "PUBLISHED"


def _access_state(text: str, evidence_state: str) -> str:
    upper = text.upper()
    if (
        "ACCESS BLOCKED" in upper
        or "ACCESS_BLOCKED" in upper
        or "RETURNED 403" in upper
        or "RETURNED HTTP 403" in upper
    ):
        return "ACCESS_BLOCKED"
    if "WAF" in upper or "CLOUDFLARE" in upper:
        return "ACCESS_BLOCKED"
    if "RESTRICTED TO SOME CLIENTS" in upper or "KADENCE SECURITY" in upper:
        return "ACCESS_BLOCKED"
    if "HUMAN DOWNLOAD" in upper:
        return "HUMAN_DOWNLOAD_REQUIRED"
    if "FOI ACCESS CONFIRMED" in upper or "FOI REQUIRED" in upper:
        return "FOI_REQUIRED"
    if "FOI LIMITATION" in upper or "FOI RESPONSE" in upper:
        return "FOI_REQUIRED"
    if "AGREEMENT REQUIRED" in upper or "SIGNED DATA RELEASE" in upper:
        return "AGREEMENT_REQUIRED"
    if "RETURNED HTTP 200" in upper or "RETURNED 200" in upper:
        return "OPEN"
    if evidence_state in {"PUBLISHED", "ACQUIRED"}:
        return "OPEN"
    return "UNVERIFIED"


def _rights_state(text: str, evidence_state: str) -> str:
    upper = text.upper()
    if "RESTRICTED" in upper:
        return "RESTRICTED"
    if "DATA RELEASE AND USE AGREEMENT" in upper or "AGREEMENT REQUIRED" in upper:
        return "AGREEMENT_REQUIRED"
    if "COPYRIGHT" in upper or "ALL RIGHTS RESERVED" in upper:
        return "REVIEW_REQUIRED"
    if evidence_state == "PUBLISHED":
        return "PUBLICLY_AVAILABLE_VERIFIED"
    if "RIGHTS" in upper and "REVIEW" in upper:
        return "REVIEW_REQUIRED"
    return "UNKNOWN"


def _coverage_scope(text: str) -> str:
    upper = text.upper()
    if "COVERAGE IS " in upper and " ONLY" in upper:
        return "SINGLE_LGU"
    if "SINGLE LGU" in upper or "SINGLE-LGU" in upper:
        return "SINGLE_LGU"
    if "PARTICIPATING LGU" in upper:
        return "PARTICIPATING_LGUS"
    if "SELECTED LGU" in upper or "SELECTED-LGU" in upper:
        return "SELECTED_LGUS"
    if "DIRECTORY SUBSET" in upper or "NOT A COMPLETE" in upper or "NOT ALL" in upper:
        return "DIRECTORY_SUBSET"
    if "CATALOGUE" in upper or " CANDIDATE LAYER" in upper or "LAYER" in upper:
        return "DISCOVERY_LAYER"
    if "NCR SCOPE" in upper or "REGIONAL" in upper:
        return "REGIONAL"
    if "NATIONAL" in upper:
        return "NATIONAL_PARTIAL"
    return "UNKNOWN_COVERAGE"


def _priority(text: str) -> str | None:
    match = PRIORITY_RE.search(text)
    if not match:
        return None
    value = match.group(1)
    # The register writes "P0/P1" when a source spans two priorities; the first
    # value is the recorded priority and the full text remains in next_action.
    return value


def _normalise_priority(value: Any) -> str | None:
    if value is None:
        return None
    match = PRIORITY_RE.search(str(value))
    return match.group(1) if match else None


def _next_action(cells: list[str], text: str, section: str | None = None) -> str:
    # Sections G/H use the fourth column for "what it is not"/limitations and
    # the last column only for a priority, so the last cell is not a next action.
    if section and section[0] in {"G", "H"} and len(cells) >= 4:
        return _clean_markdown(cells[3])
    if len(cells) >= 5 and cells[-1]:
        return _clean_markdown(cells[-1])
    if cells:
        return _clean_markdown(cells[-1])
    return _clean_markdown(text)


def _category_for(source_id: str) -> str:
    if source_id in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[source_id]
    for prefix, category in CATEGORY_PREFIXES:
        if source_id == prefix or source_id.startswith(f"{prefix}."):
            return category
    return "OTHER_QUALIFYING"


def _row_to_source(row: RegisterRow, baseline: str) -> dict[str, Any]:
    evidence = _evidence_state(row.text, row.cells)
    return {
        "source_id": row.source_id,
        "custodian": row.custodian,
        "title": row.title,
        "category": _category_for(row.source_id),
        "urls": row.urls,
        "evidence_state": evidence,
        "access_state": _access_state(row.text, evidence),
        "rights_state": _rights_state(row.text, evidence),
        "coverage_scope": _coverage_scope(row.text),
        "priority": _priority(row.text),
        "next_action": _next_action(row.cells, row.text, row.section),
        "tracker_ids": sorted(set(TRACKER_RE.findall(row.text))),
        "last_verified": _latest_date(row.text, baseline),
        "publication_state": _publication_state(row.text, evidence),
        "register_section": row.section,
        "provenance": {
            "register": True,
            "candidates": False,
            "probe": False,
        },
        "probes": [],
    }


def load_source_candidates(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_CANDIDATES_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _default_probe_date(path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if match:
        return match.group(1)
    return date.today().isoformat()


def parse_probes(path: str | Path | None = None) -> list[ProbeObservation]:
    target = Path(path) if path is not None else DEFAULT_PROBES_PATH
    if not target.exists():
        return []
    observed_at = _default_probe_date(target)
    lines = target.read_text(encoding="utf-8").splitlines()
    probes: list[ProbeObservation] = []
    index = 0
    while index < len(lines):
        match = PROBE_LINE_RE.match(lines[index])
        if not match:
            index += 1
            continue
        probe = ProbeObservation(
            probe_key=match.group("key"),
            url=match.group("url"),
            observed_at=observed_at,
        )
        rest = match.group("rest").strip()
        status = PROBE_STATUS_RE.match(rest)
        if status:
            _apply_probe_status(probe, status)
        else:
            if rest.startswith("curl:"):
                probe.error = rest
            cursor = index + 1
            while cursor < len(lines):
                status = PROBE_STATUS_RE.match(lines[cursor])
                if status:
                    _apply_probe_status(probe, status)
                    index = cursor
                    break
                if PROBE_LINE_RE.match(lines[cursor]):
                    index = cursor - 1
                    break
                if probe.error is None and lines[cursor].strip():
                    probe.error = lines[cursor].strip()
                cursor += 1
            else:
                index = cursor
        probes.append(probe)
        index += 1
    return probes


def _apply_probe_status(probe: ProbeObservation, match: re.Match[str]) -> None:
    probe.status_code = int(match.group("status"))
    probe.content_type = match.group("content_type") or None
    probe.final_url = match.group("final_url") or None
    probe.size_bytes = int(match.group("size"))


def _merge_candidate(source: dict[str, Any], candidate: dict[str, Any]) -> None:
    for name in (
        "custodian",
        "title",
        "evidence_state",
        "access_state",
        "rights_state",
        "coverage_scope",
        "priority",
        "next_action",
        "last_verified",
    ):
        value = candidate.get(name)
        if value not in (None, ""):
            source[name] = value
    if candidate.get("urls"):
        source["urls"] = list(dict.fromkeys([*source["urls"], *candidate["urls"]]))
    source["priority"] = _normalise_priority(source.get("priority"))
    if candidate.get("tracker_ids"):
        source["tracker_ids"] = sorted(set([*source["tracker_ids"], *candidate["tracker_ids"]]))
    if candidate.get("notes"):
        source["notes"] = candidate["notes"]
    source["publication_state"] = _publication_state(
        f"{source.get('notes') or ''} {source.get('next_action') or ''}",
        source["evidence_state"],
    )
    source["provenance"]["candidates"] = True


def _attach_probes(
    sources: list[dict[str, Any]], probes: list[ProbeObservation]
) -> list[dict[str, Any]]:
    host_index: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        for url in source["urls"]:
            host = _normalise_host(url)
            if host:
                host_index.setdefault(host, []).append(source)
    unmatched: list[ProbeObservation] = []
    seen: set[tuple[str, str]] = set()
    for probe in probes:
        hosts = {_normalise_host(probe.url)}
        if probe.final_url:
            hosts.add(_normalise_host(probe.final_url))
        matched = False
        for host in hosts:
            for source in host_index.get(host, []):
                key = (source["source_id"], probe.url)
                if key in seen:
                    continue
                seen.add(key)
                source["probes"].append(probe.as_dict())
                source["provenance"]["probe"] = True
                source["last_verified"] = max(source["last_verified"], probe.observed_at)
                matched = True
        if not matched:
            unmatched.append(probe)
    for source in sources:
        outcomes = {probe["outcome"] for probe in source["probes"]}
        if not outcomes:
            continue
        if (
            "HTTP_403" in outcomes
            and source["access_state"] in {"UNVERIFIED", "OPEN"}
            and source.get("publication_state") != "PUBLISHED"
        ):
            source["access_state"] = "ACCESS_BLOCKED"
        source["observed_access_state"] = (
            "ACCESS_BLOCKED"
            if outcomes & {"HTTP_403", "TRANSPORT_ERROR"}
            else "OPEN"
            if outcomes == {"HTTP_200"}
            else "MIXED"
        )
    return unmatched


def _probe_only_record(probe: ProbeObservation) -> dict[str, Any]:
    return probe.as_dict()


def build_source_inventory(
    register_path: str | Path | None = None,
    candidates_path: str | Path | None = None,
    probes_path: str | Path | None = None,
) -> dict[str, Any]:
    rows, baseline = parse_register(register_path)
    candidate_payload = load_source_candidates(candidates_path)
    sources = [_row_to_source(row, baseline) for row in rows]
    by_id = {source["source_id"]: source for source in sources}

    for candidate in candidate_payload.get("sources", []):
        source_id = candidate.get("source_id")
        if not source_id:
            continue
        if source_id in by_id:
            _merge_candidate(by_id[source_id], candidate)
            continue
        source = {
            "source_id": source_id,
            "custodian": candidate.get("custodian") or source_id,
            "title": candidate.get("title") or source_id,
            "category": _category_for(source_id),
            "urls": list(candidate.get("urls") or []),
            "evidence_state": candidate.get("evidence_state") or "DISCOVERED",
            "access_state": candidate.get("access_state") or "UNVERIFIED",
            "rights_state": candidate.get("rights_state") or "UNKNOWN",
            "coverage_scope": candidate.get("coverage_scope") or "UNKNOWN_COVERAGE",
            "priority": _normalise_priority(candidate.get("priority")),
            "next_action": candidate.get("next_action") or "",
            "tracker_ids": sorted(set(candidate.get("tracker_ids") or [])),
            "last_verified": candidate.get("last_verified") or baseline,
            "publication_state": (
                "PUBLISHED" if candidate.get("evidence_state") == "PUBLISHED" else "NOT_PUBLISHED"
            ),
            "register_section": None,
            "provenance": {"register": False, "candidates": True, "probe": False},
            "probes": [],
        }
        if candidate.get("notes"):
            source["notes"] = candidate["notes"]
        sources.append(source)
        by_id[source_id] = source

    probes = parse_probes(probes_path)
    unmatched = _attach_probes(sources, probes)
    sources.sort(key=lambda source: source["source_id"])

    payload: dict[str, Any] = {
        "version": 1,
        "as_of": max(
            [baseline, candidate_payload.get("as_of", baseline)]
            + [probe.observed_at for probe in probes]
        ),
        "description": (
            "Merged inventory of researched source candidates from the register, the "
            "normalized candidate registry, and live probe ledgers. Presence is not "
            "acquisition, schema verification, rights approval, or a publication decision."
        ),
        "allowed_states": candidate_payload.get("allowed_states", {}),
        "taxonomy_categories": list(TAXONOMY_CATEGORIES),
        "counts": {},
        "sources": sources,
        "unmatched_probes": [_probe_only_record(probe) for probe in unmatched],
    }
    payload["counts"] = summarize_source_inventory(payload)
    return payload


def validate_source_inventory(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["sources must be a non-empty list"]

    allowed = payload.get("allowed_states") or {}
    states = {
        "evidence_state": set(allowed.get("evidence") or EVIDENCE_RANK),
        "access_state": set(allowed.get("access") or ()),
        "rights_state": set(allowed.get("rights") or ()),
        "coverage_scope": set(allowed.get("coverage") or ()),
    }
    categories = set(payload.get("taxonomy_categories") or TAXONOMY_CATEGORIES)
    seen: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"source[{index}]: entry is not an object")
            continue
        label = source.get("source_id") or f"source[{index}]"
        for required in REQUIRED_FIELDS:
            if required not in source:
                errors.append(f"{label}: missing required field {required}")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{label}: source_id must be a non-empty string")
        elif source_id in seen:
            errors.append(f"{label}: duplicate source_id")
        else:
            seen.add(source_id)
        custodian = source.get("custodian")
        if not isinstance(custodian, str) or not custodian.strip():
            errors.append(f"{label}: custodian must be a non-empty string")
        title = source.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{label}: title must be a non-empty string")
        if source.get("category") not in categories:
            errors.append(f"{label}: category={source.get('category')!r} is not in the taxonomy")
        urls = source.get("urls")
        if not isinstance(urls, list) or not urls:
            errors.append(f"{label}: urls must be a non-empty list")
        else:
            for url in urls:
                parsed = urlparse(str(url))
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    errors.append(f"{label}: invalid URL {url!r}")
        for state_field, allowed_values in states.items():
            value = source.get(state_field)
            if allowed_values and value not in allowed_values:
                errors.append(f"{label}: {state_field}={value!r} is not an allowed state")
        priority = source.get("priority")
        if priority not in (None, "P0", "P1", "P2"):
            errors.append(f"{label}: priority={priority!r} must be P0, P1, P2 or null")
        tracker_ids = source.get("tracker_ids")
        if not isinstance(tracker_ids, list) or not all(
            isinstance(item, str) and item.strip() for item in tracker_ids
        ):
            errors.append(f"{label}: tracker_ids must be a list of non-empty strings")
        try:
            date.fromisoformat(str(source.get("last_verified")))
        except ValueError:
            errors.append(f"{label}: last_verified must be an ISO date")
        provenance = source.get("provenance")
        if not isinstance(provenance, dict) or not all(
            isinstance(provenance.get(key), bool) for key in ("register", "candidates", "probe")
        ):
            errors.append(f"{label}: provenance must carry boolean register/candidates/probe flags")
        if not isinstance(source.get("probes"), list):
            errors.append(f"{label}: probes must be a list")
        section = source.get("register_section")
        if section is not None and not isinstance(section, str):
            errors.append(f"{label}: register_section must be a string or null")
    return errors


def summarize_source_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    sources = payload.get("sources") or []

    def counts(field: str) -> dict[str, int]:
        values = Counter(
            "UNASSIGNED" if source.get(field) is None else str(source.get(field))
            for source in sources
        )
        return dict(sorted(values.items()))

    return {
        "total": len(sources),
        "from_register": sum(1 for source in sources if source["provenance"]["register"]),
        "from_candidates": sum(1 for source in sources if source["provenance"]["candidates"]),
        "probed": sum(1 for source in sources if source["provenance"]["probe"]),
        "unmatched_probes": len(payload.get("unmatched_probes") or []),
        "published": sum(1 for source in sources if source.get("publication_state") == "PUBLISHED"),
        "internal_only": sum(
            1 for source in sources if source.get("publication_state") == "INTERNAL_ONLY"
        ),
        "by_category": counts("category"),
        "by_evidence_state": counts("evidence_state"),
        "by_access_state": counts("access_state"),
        "by_rights_state": counts("rights_state"),
        "by_coverage_scope": counts("coverage_scope"),
        "by_priority": counts("priority"),
    }


CSV_FIELDS = (
    "source_id",
    "category",
    "custodian",
    "title",
    "evidence_state",
    "access_state",
    "rights_state",
    "coverage_scope",
    "priority",
    "publication_state",
    "primary_url",
    "url_count",
    "register_section",
    "provenance",
    "probe_outcomes",
    "last_verified",
    "tracker_ids",
    "next_action",
)


def write_source_inventory(
    payload: dict[str, Any],
    json_path: str | Path | None = None,
    csv_path: str | Path | None = None,
) -> tuple[Path, Path]:
    json_target = Path(json_path) if json_path is not None else DEFAULT_JSON_OUTPUT
    csv_target = Path(csv_path) if csv_path is not None else DEFAULT_CSV_OUTPUT
    json_target.parent.mkdir(parents=True, exist_ok=True)
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with csv_target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for source in payload["sources"]:
            writer.writerow(
                {
                    "source_id": source["source_id"],
                    "category": source["category"],
                    "custodian": source["custodian"],
                    "title": source["title"],
                    "evidence_state": source["evidence_state"],
                    "access_state": source["access_state"],
                    "rights_state": source["rights_state"],
                    "coverage_scope": source["coverage_scope"],
                    "priority": source.get("priority") or "",
                    "publication_state": source.get("publication_state") or "",
                    "primary_url": source["urls"][0] if source["urls"] else "",
                    "url_count": len(source["urls"]),
                    "register_section": source.get("register_section") or "",
                    "provenance": "+".join(
                        key for key, value in source["provenance"].items() if value
                    ),
                    "probe_outcomes": ";".join(
                        f"{probe['probe_key']}={probe['outcome']}"
                        for probe in source.get("probes") or []
                    ),
                    "last_verified": source["last_verified"],
                    "tracker_ids": ";".join(source.get("tracker_ids") or []),
                    "next_action": source.get("next_action") or "",
                }
            )
    return json_target, csv_target
