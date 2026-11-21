"""Generate the complete data.md section 11.1 rebuild evidence pack.

The pack deliberately separates four kinds of evidence:

* the merged source inventory and probe ledger (candidate and register evidence);
* release-level database facts (downloads, schemas, rights, overlap);
* community-fallback and OSM coordinate-fill evidence;
* the narrative change/rollback/refactor notes required by the rebuild brief.

Every field is either read from the database/register/raw payload or written as
``UNKNOWN``/``NOT_VERIFIED``. Nothing is inferred to fill a gap.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from philfacilities_api.models import (
    AdministrativeUnit,
    Agency,
    Dataset,
    Facility,
    FacilityAttributeFusion,
    FacilityLocation,
    FacilitySourceLink,
    GeographicRelease,
    IngestionRun,
    MatchCandidate,
    PublicationGate,
    Release,
    SourceCheck,
    SourceRecord,
)
from philfacilities_api.rights import publication_decision_rule
from sqlalchemy import func, literal_column, select, text
from sqlalchemy.orm import Session

from .reporting import (
    now_iso as _now,
)
from .reporting import (
    source_url_key as _source_url_key,
)
from .reporting import (
    write_csv as _write_csv,
)
from .reporting import (
    write_jsonl as _write_jsonl,
)
from .reporting import (
    write_text as _write_text,
)
from .skip_reasons import SKIP_REASON_SET, SkipDecision, next_retry, skip_for_source
from .source_inventory import write_source_inventory
from .source_report import (
    REGION_SHORT,
    REGIONS,
    attach_published_release_evidence,
    build_acquisition_queue,
    build_gap_report,
    build_probe_ledger,
    enrich_source_inventory,
    load_region_searches,
    validate_report_fields,
)
from .sources.catalog import SOURCES

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "var" / "reports" / "rebuild"


@dataclass
class RebuildPackPaths:
    source_inventory_json: Path
    source_inventory_csv: Path
    probe_ledger: Path
    gap_report: Path
    skipped_sources: Path
    acquisition_plan: Path
    download_manifest: Path
    schema_observations: Path
    rights_register: Path
    rebuild_plan: Path
    pipeline_adjustments: Path
    ingestion_refactor: Path
    rebuild_delta: Path
    adapter_handoff: Path
    field_matrix: Path
    rejected_row_retention: Path
    crosswalk_candidates: Path
    community_fallback: Path
    osm_location_fills: Path
    overlap_report: Path
    agency_domain_census: Path
    lgu_search_ledger: Path
    region_search_ledger: Path
    unresolved: Path
    final_report: Path


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _region_code(psgc: str | None) -> str | None:
    if not psgc or len(psgc) < 2 or not psgc[:2].isdigit():
        return None
    return psgc[:2] + "00000000"


def _region_name(psgc: str | None) -> str | None:
    code = _region_code(psgc)
    if code is None:
        return None
    return dict(REGIONS).get(code, code)


def _region_short(psgc: str | None) -> str | None:
    code = _region_code(psgc)
    if code is None:
        return None
    return REGION_SHORT.get(code, code)


def _latest_checks(session: Session) -> dict[Any, SourceCheck]:
    checks: dict[Any, SourceCheck] = {}
    for check in session.scalars(select(SourceCheck).order_by(SourceCheck.checked_at)):
        checks[check.dataset_id] = check
    return checks


FORMAT_CONTENT_TYPES = {
    "json": "application/json",
    "geojson": "application/geo+json",
    "csv": "text/csv",
    "pdf": "application/pdf",
    "html": "text/html",
    "parquet": "application/vnd.apache.parquet",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


def _release_manifest_rows(
    session: Session, payload: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    checks = _latest_checks(session)
    probes_by_url: dict[str, dict[str, Any]] = {}
    for source in (payload or {}).get("sources") or []:
        for probe in source.get("probes") or []:
            url = probe.get("url")
            if not url:
                continue
            existing = probes_by_url.get(url)
            if existing is None or (
                existing.get("outcome") != "HTTP_200" and probe.get("outcome") == "HTTP_200"
            ):
                probes_by_url[url] = probe
    rows = session.execute(
        select(Release, Dataset, Agency)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .join(Agency, Dataset.agency_id == Agency.id)
        .order_by(Agency.short_code, Dataset.slug, Release.retrieved_at)
    ).all()
    manifest: list[dict[str, Any]] = []
    for release, dataset, agency in rows:
        check = checks.get(dataset.id)
        probe = probes_by_url.get(dataset.source_url or "")
        uri = release.raw_object_uri or ""
        filename = Path(uri).name.split("-", 1)[-1] if uri else None
        recorded_type = check.content_type if check and check.content_type else None
        if not recorded_type and probe:
            recorded_type = probe.get("content_type")
        derived_type = FORMAT_CONTENT_TYPES.get((release.file_format or "").lower())
        content_type = recorded_type or derived_type
        final_url = (
            check.final_url
            if check and check.final_url
            else (probe.get("final_url") if probe and probe.get("final_url") else None)
        )
        http_status = (
            check.http_status
            if check and check.http_status is not None
            else (probe.get("http_status") if probe else None)
        )
        url_evidence = (
            "source_check"
            if check and check.final_url
            else "probe_ledger"
            if probe
            else "NOT_RECORDED"
        )
        url_checked_at = (
            check.checked_at.isoformat()
            if url_evidence == "source_check" and check and check.checked_at
            else (probe.get("observed_at") if url_evidence == "probe_ledger" else None)
        )
        manifest.append(
            {
                "source_key": dataset.slug,
                "dataset": dataset.name,
                "agency": agency.name,
                "publisher_domain": agency.official_domain,
                "release_label": release.source_release_label,
                "retrieved_at": release.retrieved_at.isoformat() if release.retrieved_at else None,
                "processed_at": release.processed_at.isoformat() if release.processed_at else None,
                "source_url": dataset.source_url or "NOT_RECORDED",
                "final_url": final_url or "NOT_RECORDED",
                "http_status": http_status if http_status is not None else "NOT_RECORDED",
                "url_evidence": url_evidence,
                "url_checked_at": url_checked_at,
                "content_type": content_type or "UNKNOWN",
                "content_type_source": (
                    "recorded"
                    if recorded_type
                    else (
                        "derived_from_verified_file_format"
                        if derived_type
                        else "UNKNOWN_NOT_RECORDED"
                    )
                ),
                "content_length": release.file_size_bytes,
                "size_bytes": release.file_size_bytes,
                "sha256": release.sha256,
                "checksum_sha256": release.sha256,
                "filename": filename,
                "format": release.file_format,
                "acquisition_status": "ACQUIRED" if release.raw_object_uri else "NOT_ACQUIRED",
                "row_count_reported": release.row_count_reported,
                "row_count_parsed": release.row_count_parsed,
                "ingestion_status": release.ingestion_status,
                "publication_status": release.publication_status,
                "redistribution_status": dataset.redistribution_status,
                "authority_level": dataset.authority_level,
                "source_published_at": release.source_published_at.isoformat()
                if release.source_published_at
                else None,
                "reference_period_start": release.reference_period_start.isoformat()
                if release.reference_period_start
                else None,
                "reference_period_end": release.reference_period_end.isoformat()
                if release.reference_period_end
                else None,
                "raw_object_uri": release.raw_object_uri,
                "notes": release.notes,
            }
        )
    return manifest


def _payload_samples(
    session: Session, release_ids: list[Any], *, limit_per_release: int = 10
) -> dict[Any, list[dict[str, Any]]]:
    if not release_ids:
        return {}
    # A window function over source.records materializes every raw JSON payload
    # before filtering to the first ten rows per release. The lateral form uses
    # ix_source_records_release and reads only the sampled payloads, which keeps
    # report generation within a memory-constrained host.
    sample = (
        select(SourceRecord.raw_payload)
        .where(SourceRecord.release_id == Release.id)
        .order_by(SourceRecord.id)
        .limit(limit_per_release)
        .lateral("sample")
    )
    rows = session.execute(
        select(Release.id, sample.c.raw_payload)
        .where(Release.id.in_(release_ids))
        .order_by(Release.id)
    ).all()
    samples: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for release_id, payload in rows:
        if isinstance(payload, dict):
            samples[release_id].append(payload)
    return samples


def _coordinate_methods(session: Session) -> dict[Any, list[str]]:
    rows = session.execute(
        select(
            SourceRecord.release_id,
            FacilityLocation.method,
            FacilityLocation.precision,
        )
        .join(FacilitySourceLink, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(
            FacilityLocation,
            (FacilityLocation.facility_id == FacilitySourceLink.facility_id)
            & (FacilityLocation.is_current.is_(True)),
        )
        .group_by(SourceRecord.release_id, FacilityLocation.method, FacilityLocation.precision)
    ).all()
    methods: dict[Any, set[str]] = defaultdict(set)
    for release_id, method, precision in rows:
        label = f"{method or 'unknown'} ({precision or 'unknown'})"
        methods[release_id].add(label)
    return {key: sorted(value) for key, value in methods.items()}


def _schema_rows(session: Session) -> list[dict[str, Any]]:
    releases = session.execute(
        select(Release, Dataset).join(Dataset, Release.dataset_id == Dataset.id)
    ).all()
    samples = _payload_samples(session, [release.id for release, _ in releases])
    methods = _coordinate_methods(session)
    rows: list[dict[str, Any]] = []
    for release, dataset in releases:
        payloads = samples.get(release.id, [])
        field_names: list[str] = []
        types: dict[str, Counter[str]] = defaultdict(Counter)
        nulls: Counter[str] = Counter()
        for payload in payloads:
            for key, value in payload.items():
                if key not in field_names:
                    field_names.append(key)
                types[key][_json_type(value)] += 1
                if value in (None, ""):
                    nulls[key] += 1
        geographic = [
            key
            for key in field_names
            if re.search(
                r"psgc|region|province|city|municipality|barangay|purok|address",
                key,
                re.I,
            )
        ]
        rows.append(
            {
                "source_key": dataset.slug,
                "dataset": dataset.name,
                "authority_level": dataset.authority_level,
                "release_label": release.source_release_label,
                "release_date": release.source_published_at.date().isoformat()
                if release.source_published_at
                else None,
                "reference_period_start": release.reference_period_start.isoformat()
                if release.reference_period_start
                else None,
                "reference_period_end": release.reference_period_end.isoformat()
                if release.reference_period_end
                else None,
                "row_count_parsed": release.row_count_parsed,
                "original_fields": ";".join(field_names),
                "observed_types": ";".join(
                    f"{key}={'|'.join(sorted(counter))}" for key, counter in types.items()
                ),
                "null_tokens": ";".join(
                    f"{key}={count}" for key, count in sorted(nulls.items()) if count
                ),
                "source_record_key": "source_record_key",
                "unique_keys": "release_id + source_record_key",
                "geographic_levels": ";".join(geographic) or "NOT_OBSERVED",
                "coordinate_methods": ";".join(methods.get(release.id, [])) or "NO_LINKED_POINT",
                "facility_granularity": "FACILITY" if dataset.authority_level else "UNKNOWN",
                "sample_size": len(payloads),
                "notes": (
                    "Field names and types are sampled from retained raw source payloads; "
                    "absence in the sample is not proof that a field is absent from the release."
                ),
            }
        )
    return rows


def _rights_rows(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Dataset, Agency, PublicationGate, func.count(Release.id))
        .join(Agency, Dataset.agency_id == Agency.id)
        .outerjoin(PublicationGate, PublicationGate.dataset_id == Dataset.id)
        .outerjoin(Release, Release.dataset_id == Dataset.id)
        .group_by(Dataset.id, Agency.id, PublicationGate.id)
        .order_by(Agency.short_code, Dataset.slug)
    ).all()
    rights: list[dict[str, Any]] = []
    for dataset, agency, gate, release_count in rows:
        rule = publication_decision_rule(
            redistribution_status=dataset.redistribution_status,
            publication_status=dataset.publication_status,
            gate_status=gate.status if gate else None,
            is_synthetic=dataset.is_synthetic,
        )
        restricted = dataset.redistribution_status in {
            "restricted_non_redistributable",
            "denied",
            "expired",
        }
        publisher_domain = agency.official_domain
        if not publisher_domain and dataset.source_url:
            host = urllib.parse.urlparse(dataset.source_url).netloc.casefold()
            publisher_domain = host[4:] if host.startswith("www.") else host or None
        rights.append(
            {
                "source_key": dataset.slug,
                "dataset": dataset.name,
                "agency": agency.name,
                "publisher_domain": publisher_domain,
                "release_count": release_count,
                "license_identifier": dataset.license_identifier,
                "terms_url": dataset.terms_url,
                "rights_basis": dataset.rights_basis,
                "redistribution_status": dataset.redistribution_status,
                "publication_status": dataset.publication_status,
                "gate_status": gate.status if gate else None,
                "date_checked": (gate.reviewed_at or dataset.created_at).isoformat(),
                "explicit_restriction": (
                    "YES" if restricted else "NO" if rule["public"] else "UNKNOWN"
                ),
                "personal_data_status": dataset.personal_data_status or "NOT_RECORDED",
                "personal_data_fields": "WITHHELD_OR_NOT_OBSERVED"
                if dataset.personal_data_status in {"withheld", "redacted", "not_collected"}
                else "NOT_RECORDED",
                "security_sensitive_fields": "NOT_RECORDED",
                "attribution_text": dataset.attribution_text,
                "takedown_route": "docs/data-policy.md (takedown process)",
                "automated_decision": "PUBLISH" if rule["public"] else "INTERNAL_ONLY",
                "rule_identifier": rule["rule"],
                "notes": (
                    "Public official, verified release with no explicit prohibition."
                    if rule["rule"] == "AUTOMATED_PUBLICLY_AVAILABLE_VERIFIED"
                    else None
                ),
            }
        )
    return rights


def _field_rows(
    schema_rows: list[dict[str, Any]], inventory: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for schema in schema_rows:
        fields = [field for field in (schema["original_fields"] or "").split(";") if field]
        if not fields:
            rows.append(
                {
                    "source_id": schema["source_key"],
                    "source_key": schema["source_key"],
                    "authority_tier": schema.get("authority_level"),
                    "reference_period": schema["reference_period_end"],
                    "field_name": "NOT_OBSERVED",
                    "field_status": "UNVERIFIED",
                    "notes": schema["notes"],
                }
            )
            continue
        for field in fields:
            rows.append(
                {
                    "source_id": schema["source_key"],
                    "source_key": schema["source_key"],
                    "authority_tier": schema.get("authority_level"),
                    "reference_period": schema["reference_period_end"],
                    "field_name": field,
                    "field_status": "OBSERVED",
                    "notes": "Sampled from the retained raw release.",
                }
            )
    for source in inventory.get("sources") or []:
        observed = source.get("data_fields_observed") or []
        if not observed:
            rows.append(
                {
                    "source_id": source.get("source_id"),
                    "source_key": None,
                    "authority_tier": None,
                    "reference_period": None,
                    "field_name": "NOT_VERIFIED",
                    "field_status": "UNVERIFIED",
                    "notes": "No field-level observation recorded in the source register.",
                }
            )
            continue
        for field in observed:
            rows.append(
                {
                    "source_id": source.get("source_id"),
                    "source_key": None,
                    "authority_tier": None,
                    "reference_period": None,
                    "field_name": field,
                    "field_status": "OBSERVED",
                    "notes": "Recorded in the candidate/register inventory.",
                }
            )
    return rows


def _crosswalk_rows(
    schema_rows: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for schema in schema_rows:
        fields = [field for field in (schema["original_fields"] or "").split(";") if field]
        candidates = [
            field
            for field in fields
            if re.search(r"(^id$|_id$|code$|psgc|number$|_no$|station|branch)", field, re.I)
        ]
        if not candidates:
            rows.append(
                {
                    "source_key": schema["source_key"],
                    "dataset": schema["dataset"],
                    "key_name": "NO_STABLE_KEY_VERIFIED",
                    "key_type": "UNKNOWN",
                    "observed_in": "sampled raw payload",
                    "stable": "UNKNOWN",
                    "notes": (
                        "No identifier-like field appeared in the sample; not asserted as a key."
                    ),
                }
            )
            continue
        for field in candidates:
            rows.append(
                {
                    "source_key": schema["source_key"],
                    "dataset": schema["dataset"],
                    "key_name": field,
                    "key_type": "source_field",
                    "observed_in": "sampled raw payload",
                    "stable": "UNKNOWN",
                    "notes": "Candidate join key only; never an asserted merge.",
                }
            )
    for source in sources or []:
        if source.get("access_state") != "SKIPPED":
            continue
        rows.append(
            {
                "source_key": source.get("source_id"),
                "dataset": source.get("title"),
                "key_name": "NO_ACQUIRED_RELEASE",
                "key_type": "UNKNOWN",
                "observed_in": "no acquired artifact",
                "stable": "UNKNOWN",
                "notes": (
                    "Source was skipped because its tested public route failed; no release "
                    "exists to inspect. This is an explicit no-key finding, not an asserted key. "
                    "See skipped-sources.jsonl for the reason and retry."
                ),
            }
        )
    return rows


def _community_rows(session: Session) -> list[dict[str, Any]]:
    # A correlated NOT EXISTS uses the facility_source_links index and avoids
    # materialising a large NOT IN set. On the national rebuild the old NOT IN
    # form spent several minutes in a parallel hash join and exhausted /dev/shm.
    official_exists = (
        select(1)
        .select_from(FacilitySourceLink)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(
            FacilitySourceLink.facility_id == Facility.id,
            Dataset.authority_level == "official",
        )
        .exists()
    )
    # Select only the columns needed for the register and stream the result.
    # Loading full ORM Facility/FacilityLocation objects (including geometry)
    # for every community-only facility exhausted memory on the national
    # rebuild; the narrow, streamed query keeps the report reproducible.
    statement = (
        select(
            Facility.id,
            Facility.slug,
            Facility.display_name,
            Facility.facility_type,
            FacilityLocation.psgc_code,
            Dataset.slug,
            Dataset.attribution_text,
            SourceRecord.source_record_key,
            Release.source_release_label,
        )
        .select_from(Facility)
        .join(FacilitySourceLink, FacilitySourceLink.facility_id == Facility.id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .outerjoin(
            FacilityLocation,
            (FacilityLocation.facility_id == Facility.id) & (FacilityLocation.is_current.is_(True)),
        )
        .where(
            Dataset.authority_level == "community",
            ~official_exists,
        )
        .order_by(Facility.display_name)
    )
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows = session.execute(statement).yield_per(1000)
    for (
        facility_id,
        facility_slug,
        display_name,
        facility_type,
        psgc_code,
        dataset_slug,
        attribution_text,
        record_key,
        release_label,
    ) in rows:
        if str(facility_id) in seen:
            continue
        seen.add(str(facility_id))
        output.append(
            {
                "facility_id": str(facility_id),
                "facility_slug": facility_slug,
                "name": display_name,
                "facility_type": facility_type,
                "region": _region_name(psgc_code),
                "region_code": _region_code(psgc_code),
                "psgc_code": psgc_code,
                "osm_source": dataset_slug,
                "osm_record_key": record_key,
                "osm_id": record_key,
                "osm_snapshot": release_label,
                "match_state": "community_only",
                "attribution": attribution_text,
            }
        )
    return output


def _overlap_rows(session: Session) -> list[dict[str, Any]]:
    pair_rows = session.execute(
        select(
            Dataset.slug,
            Dataset.name,
            Dataset.authority_level,
            Dataset.coverage_scope,
            func.count(func.distinct(FacilitySourceLink.facility_id)),
        )
        .join(Release, Release.dataset_id == Dataset.id)
        .join(SourceRecord, SourceRecord.release_id == Release.id)
        .join(FacilitySourceLink, FacilitySourceLink.source_record_id == SourceRecord.id)
        .group_by(Dataset.id)
        .order_by(func.count(func.distinct(FacilitySourceLink.facility_id)).desc())
    ).all()
    link_counts = session.execute(
        select(
            FacilitySourceLink.facility_id,
            func.count(func.distinct(Release.dataset_id)),
        )
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .group_by(FacilitySourceLink.facility_id)
    ).all()
    multi = sum(1 for _facility, count in link_counts if count > 1)
    rows: list[dict[str, Any]] = []
    for slug, name, authority, coverage, linked in pair_rows:
        rows.append(
            {
                "source_key": slug,
                "dataset": name,
                "authority_level": authority,
                "coverage_scope": coverage,
                "facilities_linked": linked,
                "facilities_with_multiple_sources": multi,
                "conflict_fusions": session.scalar(
                    select(func.count())
                    .select_from(FacilityAttributeFusion)
                    .where(FacilityAttributeFusion.status == "conflict")
                )
                or 0,
            }
        )
    return rows


def load_lgu_probes(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not Path(path).exists():
        return {}
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        str(row.get("psgc_code")): row
        for row in document.get("targets") or []
        if row.get("psgc_code")
    }


def _name_tokens(value: str) -> frozenset[str]:
    """Token set used to match an agency name to an inventory custodian.

    Source custodians are often acronyms (``DepEd``, ``DTI``), so the source-ID
    prefix is matched as well. A custodian-name match always wins over the
    prefix fallback, which avoids attributing a parent department's domain to a
    more specific operating unit such as MRT-3.
    """

    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    return frozenset(token for token in tokens if token not in {"of", "the", "and", "via"})


def _inventory_domain_index(
    sources: list[dict[str, Any]],
) -> tuple[dict[frozenset[str], list[str]], dict[str, list[str]]]:
    hosts_by_id: dict[str, list[str]] = {}
    for source in sources:
        hosts: list[str] = []
        for url in [*(source.get("official_urls") or []), *(source.get("alternate_urls") or [])]:
            host = urllib.parse.urlparse(str(url)).netloc.casefold()
            if host.startswith("www."):
                host = host[4:]
            if host and host not in hosts:
                hosts.append(host)
        hosts_by_id[str(source.get("source_id") or "")] = hosts
    by_custodian: dict[frozenset[str], list[str]] = defaultdict(list)
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for source in sources:
        identity = _name_tokens(str(source.get("custodian") or ""))
        source_id = str(source.get("source_id") or "")
        prefix = source_id.split(".", 1)[0].casefold()
        # A layer hosted in a shared catalogue is not the layer owner's
        # publisher domain. Drop only the parent catalogue's hosts; the layer
        # owner's own hosts still identify the publisher.
        parent_hosts = set(hosts_by_id.get(str(source.get("parent_source_id") or ""), []))
        hosts = [host for host in hosts_by_id.get(source_id, []) if host not in parent_hosts]
        for host in hosts:
            if host not in by_custodian[identity]:
                by_custodian[identity].append(host)
            if prefix and host not in by_prefix[prefix]:
                by_prefix[prefix].append(host)
    return by_custodian, by_prefix


def _agency_inventory_hosts(
    agency_name: str,
    short_code: str,
    by_custodian: dict[frozenset[str], list[str]],
    by_prefix: dict[str, list[str]],
) -> list[str]:
    """Inventory hosts for one agency, preferring a custodian-name match.

    A token match wins over the source-ID prefix because a short code can name a
    parent department while the dataset belongs to a specific operating unit.
    The prefix rule is only a fallback for custodians recorded as acronyms.
    """

    matched = by_custodian.get(_name_tokens(agency_name), [])
    if matched:
        return list(matched)
    return list(by_prefix.get(short_code.casefold(), []))


def _preferred_domains(hosts: list[str]) -> list[str]:
    """Reduce observed hosts to the shortest publisher-level domains.

    A subdomain is dropped when a shorter parent host is already present. This
    keeps ``dti.gov.ph`` rather than ``negosyocenter.dti.gov.ph`` while still
    preserving an agency-specific subdomain such as ``heida.ched.gov.ph`` when
    no shorter parent was observed.
    """

    ordered = sorted(dict.fromkeys(hosts), key=lambda host: (host.count("."), len(host), host))
    kept: list[str] = []
    for host in ordered:
        if any(host == parent or host.endswith("." + parent) for parent in kept):
            continue
        kept.append(host)
    return kept


def _agency_rows(
    session: Session,
    probes: dict[str, dict[str, Any]] | None = None,
    inventory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            Agency,
            func.count(func.distinct(Dataset.id)),
            func.count(func.distinct(Release.id)),
            func.max(Release.retrieved_at),
        )
        .outerjoin(Dataset, Dataset.agency_id == Agency.id)
        .outerjoin(Release, Release.dataset_id == Dataset.id)
        .group_by(Agency.id)
        .order_by(Agency.name)
    ).all()
    source_urls = session.execute(
        select(Dataset.agency_id, Dataset.source_url).where(Dataset.source_url.is_not(None))
    ).all()
    by_agency: dict[Any, list[str]] = defaultdict(list)
    for agency_id, source_url in source_urls:
        host = urllib.parse.urlparse(source_url or "").netloc.casefold()
        if host.startswith("www."):
            host = host[4:]
        if host and host not in by_agency[agency_id]:
            by_agency[agency_id].append(host)
    by_custodian, by_prefix = _inventory_domain_index(list((inventory or {}).get("sources") or []))
    output = []
    for agency, datasets, releases, last_seen in rows:
        derived = by_agency.get(agency.id, [])
        inventory_hosts = _agency_inventory_hosts(
            agency.name, agency.short_code, by_custodian, by_prefix
        )
        preferred = [
            host
            for host in [*derived, *inventory_hosts]
            if host == "gov.ph" or host.endswith(".gov.ph")
        ]
        domain = agency.official_domain or (";".join(_preferred_domains(preferred)) or None)
        if agency.official_domain:
            source_of_domain = "source register"
        elif domain and inventory_hosts:
            source_of_domain = "derived from dataset and inventory official URLs"
        elif domain:
            source_of_domain = "derived from dataset source_url"
        else:
            source_of_domain = None
        observed_hosts = ", ".join(dict.fromkeys([*derived, *inventory_hosts]))
        output.append(
            {
                "agency": agency.name,
                "agency_code": agency.short_code,
                "agency_level": "national",
                "region": None,
                "province": None,
                "city_municipality": None,
                "publisher_type": agency.publisher_type,
                "official_domain": domain,
                "datasets": datasets,
                "releases": releases,
                "last_retrieved_at": last_seen.isoformat() if last_seen else None,
                "source_of_domain": source_of_domain,
                "verified_at": last_seen.date().isoformat() if last_seen else None,
                "notes": (
                    None
                    if domain
                    else (
                        f"No official domain recorded; observed dataset host(s): {observed_hosts}."
                        if observed_hosts
                        else "No official domain recorded; see dataset source_url."
                    )
                ),
            }
        )
    for code, probe in sorted((probes or {}).items()):
        parent = probe.get("parent_psgc_code") or ""
        parent_name = None
        if parent:
            parent_name = (
                session.scalar(
                    select(AdministrativeUnit.name).where(AdministrativeUnit.psgc_code == parent)
                )
                or None
            )
        output.append(
            {
                "agency": probe.get("name"),
                "agency_code": code,
                "agency_level": (
                    "province" if probe.get("level") == "province" else "highly_urbanized_city"
                ),
                "region": _region_name(code),
                "province": parent_name if probe.get("level") != "province" else None,
                "city_municipality": (
                    probe.get("name") if probe.get("level") != "province" else None
                ),
                "publisher_type": "government",
                "official_domain": probe.get("official_domain"),
                "datasets": 0,
                "releases": 0,
                "last_retrieved_at": None,
                "source_of_domain": "Wikidata P856 / Wikipedia external links",
                "verified_at": probe.get("last_verified"),
                "notes": f"{probe.get('state')}: {probe.get('notes') or ''}".strip(),
            }
        )
    return output


def _lgu_rows(
    session: Session, probes: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    latest = session.scalars(
        select(GeographicRelease).order_by(GeographicRelease.retrieved_at.desc())
    ).first()
    if latest is None:
        return []
    all_units = session.scalars(
        select(AdministrativeUnit)
        .where(AdministrativeUnit.release_id == latest.id)
        .order_by(AdministrativeUnit.psgc_code)
    ).all()
    by_code = {unit.psgc_code: unit for unit in all_units}
    units = [
        unit
        for unit in all_units
        if unit.geographic_level in ("province", "city", "municipality", "city_municipality")
    ]
    psgc_prefix = literal_column("substr(psgc_code, 1, 7)")
    facility_counts = dict(
        session.execute(
            select(
                psgc_prefix,
                func.count(func.distinct(FacilityLocation.facility_id)),
            )
            .where(
                FacilityLocation.is_current.is_(True),
                FacilityLocation.latitude.is_not(None),
            )
            .group_by(psgc_prefix)
        ).all()
    )
    type_rows = session.execute(
        select(
            psgc_prefix,
            Facility.facility_type,
            func.count(func.distinct(Facility.id)),
        )
        .select_from(FacilityLocation)
        .join(Facility, Facility.id == FacilityLocation.facility_id)
        .where(FacilityLocation.is_current.is_(True))
        .group_by(psgc_prefix, Facility.facility_type)
    ).all()
    types: dict[str, list[str]] = defaultdict(list)
    for prefix, facility_type, _count in type_rows:
        types[prefix].append(facility_type)
    probe_index = probes or {}
    rows: list[dict[str, Any]] = []
    for unit in units:
        prefix = unit.psgc_code[:7]
        parent = by_code.get(unit.parent_psgc_code or "")
        probe = probe_index.get(unit.psgc_code)
        if probe:
            official_domain = probe.get("official_domain")
            probe_urls = ";".join(probe.get("probe_urls") or []) or None
            result = probe.get("state") or "UNKNOWN"
            last_verified = probe.get("last_verified")
            notes = probe.get("notes")
        else:
            official_domain = None
            probe_urls = None
            result = (
                "FACILITIES_PRESENT_NO_DIRECTORY_PROBE"
                if facility_counts.get(prefix)
                else "NO_DIRECTORY_PROBE"
            )
            last_verified = None
            notes = (
                "Derived from the released PSGC geography and canonical facility points. "
                "No dedicated LGU directory probe is recorded for this row; presence in "
                "the canonical data is not evidence that the LGU directory was searched."
            )
        rows.append(
            {
                "lgu_psgc_code": unit.psgc_code,
                "lgu_name": unit.name,
                "region": _region_name(unit.psgc_code),
                "province": (
                    parent.name
                    if parent and parent.geographic_level in ("province", "region")
                    else None
                ),
                "official_domain": official_domain,
                "probe_urls": probe_urls,
                "result": result,
                "facility_types_found": ";".join(sorted(set(types.get(prefix, [])))) or None,
                "facility_count": facility_counts.get(prefix, 0),
                "last_verified": last_verified,
                "notes": notes,
            }
        )
    return rows


def _delta(session: Session, baseline_path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline: dict[str, Any] = {}
    if baseline_path is not None and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = {
        "captured_at": _now(),
        "facilities": session.scalar(select(func.count()).select_from(Facility)) or 0,
        "public_facilities": session.scalar(
            select(func.count())
            .select_from(Facility)
            .where(Facility.publication_status == "public")
        )
        or 0,
        "datasets": session.scalar(select(func.count()).select_from(Dataset)) or 0,
        "releases": session.scalar(select(func.count()).select_from(Release)) or 0,
        "source_records": session.scalar(select(func.count()).select_from(SourceRecord)) or 0,
        "facility_source_links": session.scalar(
            select(func.count()).select_from(FacilitySourceLink)
        )
        or 0,
        "current_locations": session.scalar(
            select(func.count())
            .select_from(FacilityLocation)
            .where(FacilityLocation.is_current.is_(True))
        )
        or 0,
        "locations_with_coordinates": session.scalar(
            select(func.count())
            .select_from(FacilityLocation)
            .where(
                FacilityLocation.is_current.is_(True),
                FacilityLocation.latitude.is_not(None),
            )
        )
        or 0,
        "locations_address_only": session.scalar(
            select(func.count())
            .select_from(FacilityLocation)
            .where(
                FacilityLocation.is_current.is_(True),
                FacilityLocation.latitude.is_(None),
            )
        )
        or 0,
        "facilities_without_current_coordinates": session.scalar(
            select(func.count())
            .select_from(Facility)
            .where(
                Facility.is_synthetic.is_(False),
                ~select(FacilityLocation.id)
                .where(
                    FacilityLocation.facility_id == Facility.id,
                    FacilityLocation.is_current.is_(True),
                    FacilityLocation.latitude.is_not(None),
                )
                .exists(),
            )
        )
        or 0,
        "facilities_without_any_current_location": session.scalar(
            select(func.count())
            .select_from(Facility)
            .where(
                Facility.is_synthetic.is_(False),
                ~select(FacilityLocation.id)
                .where(
                    FacilityLocation.facility_id == Facility.id,
                    FacilityLocation.is_current.is_(True),
                )
                .exists(),
            )
        )
        or 0,
        "match_candidates": session.scalar(select(func.count()).select_from(MatchCandidate)) or 0,
        "attribute_fusions": session.scalar(
            select(func.count()).select_from(FacilityAttributeFusion)
        )
        or 0,
        "administrative_units": session.scalar(select(func.count()).select_from(AdministrativeUnit))
        or 0,
    }
    return baseline, current


def _delta_metrics(
    session: Session,
    run_rows: list[dict[str, Any]],
    target: Path,
) -> dict[str, Any]:
    """Collect the section 8.4 coverage, key, matching and schema metrics."""

    def grouped(column: Any, *conditions: Any) -> dict[str, int]:
        statement = select(column, func.count())
        for condition in conditions:
            statement = statement.where(condition)
        statement = statement.group_by(column)
        return {str(key): int(count) for key, count in session.execute(statement).all()}

    def read_json(name: str) -> dict[str, Any]:
        path = target / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    facilities_by_region: Counter[str] = Counter()
    facilities_distinct_by_region: Counter[str] = Counter()
    for psgc, count, distinct_count in session.execute(
        select(
            FacilityLocation.psgc_code,
            func.count(),
            func.count(func.distinct(FacilityLocation.facility_id)),
        )
        .where(FacilityLocation.is_current.is_(True))
        .group_by(FacilityLocation.psgc_code)
    ).all():
        region = _region_name(psgc) or "UNKNOWN"
        facilities_by_region[region] += int(count)
        facilities_distinct_by_region[region] += int(distinct_count)

    location_methods = [
        {
            "precision": str(precision),
            "method": str(method or "UNKNOWN"),
            "count": int(count),
        }
        for precision, method, count in session.execute(
            select(FacilityLocation.precision, FacilityLocation.method, func.count())
            .where(FacilityLocation.is_current.is_(True))
            .group_by(FacilityLocation.precision, FacilityLocation.method)
            .order_by(func.count().desc())
        ).all()
    ]

    current_locations = (
        session.scalar(
            select(func.count())
            .select_from(FacilityLocation)
            .where(FacilityLocation.is_current.is_(True))
        )
        or 0
    )
    locations_with_psgc = (
        session.scalar(
            select(func.count())
            .select_from(FacilityLocation)
            .where(
                FacilityLocation.is_current.is_(True),
                FacilityLocation.psgc_code.is_not(None),
            )
        )
        or 0
    )
    facilities_with_location = (
        session.scalar(
            select(func.count(func.distinct(FacilityLocation.facility_id))).where(
                FacilityLocation.is_current.is_(True)
            )
        )
        or 0
    )
    facilities_with_psgc = (
        session.scalar(
            select(func.count(func.distinct(FacilityLocation.facility_id))).where(
                FacilityLocation.is_current.is_(True),
                FacilityLocation.psgc_code.is_not(None),
            )
        )
        or 0
    )

    stat_fields = (
        "parsed_rows",
        "accepted_rows",
        "rejected_rows",
        "excluded_rows",
        "duplicate_source_ids",
        "facilities_created",
        "facilities_updated",
        "address_only_locations",
        "with_coordinates",
        "psgc_provided",
        "psgc_matched",
    )
    dataset_slugs = {
        dataset_id: slug for dataset_id, slug in session.execute(select(Dataset.id, Dataset.slug))
    }
    latest_current_run: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for run in session.scalars(select(IngestionRun).where(IngestionRun.status == "published")):
        slug = dataset_slugs.get(run.dataset_id)
        stats = run.stats if isinstance(run.stats, dict) else None
        if not slug or not stats:
            continue
        if slug not in latest_current_run or run.started_at > latest_current_run[slug][0]:
            latest_current_run[slug] = (run.started_at, stats)
    run_totals: dict[str, Counter] = defaultdict(Counter)
    for slug, (_started, stats) in latest_current_run.items():
        for field in stat_fields:
            if field in stats:
                run_totals[slug][field] += int(stats.get(field) or 0)
    if not latest_current_run:
        # Tests and callers without a database run table fall back to the runner
        # log, which only carries stats for releases ingested in that invocation.
        for row in run_rows:
            if str(row.get("status") or "") != "published":
                continue
            key = str(row.get("dataset") or row.get("key") or "UNKNOWN")
            stats = row.get("stats") or {}
            for field in stat_fields:
                run_totals[key][field] += int(stats.get(field) or 0)

    preflight_run_totals: dict[str, Counter] = defaultdict(Counter)
    preflight_dataset_ids: dict[str, str] = {}
    preflight_parser_versions: Counter[str] = Counter()
    preflight_dataset_publication: Counter[str] = Counter()
    preflight_dataset_rights: Counter[str] = Counter()
    preflight_dataset_authority: Counter[str] = Counter()
    preflight_slugs: set[str] = set()
    release_file = _latest_backup_file("source_releases.csv")
    if release_file is not None:
        with release_file.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("ingestion_status") or "") == "published":
                    preflight_parser_versions[str(row.get("parser_version") or "UNKNOWN")] += 1
    dataset_file = _latest_backup_file("source_datasets.csv")
    if dataset_file is not None:
        with dataset_file.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                slug = str(row.get("slug") or "")
                if slug:
                    preflight_slugs.add(slug)
                    if row.get("id"):
                        preflight_dataset_ids[str(row["id"])] = slug
                preflight_dataset_publication[str(row.get("publication_status") or "UNKNOWN")] += 1
                preflight_dataset_rights[str(row.get("redistribution_status") or "UNKNOWN")] += 1
                preflight_dataset_authority[str(row.get("authority_level") or "UNKNOWN")] += 1
    run_file = _latest_backup_file("source_ingestion_runs.csv")
    if run_file is not None:
        latest_preflight_run: dict[str, tuple[str, dict[str, Any]]] = {}
        with run_file.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("status") or "") != "published":
                    continue
                slug = preflight_dataset_ids.get(str(row.get("dataset_id") or ""))
                if not slug:
                    continue
                try:
                    stats = json.loads(row.get("stats") or "{}")
                except json.JSONDecodeError:
                    continue
                if not isinstance(stats, dict):
                    continue
                started = str(row.get("started_at") or "")
                if slug not in latest_preflight_run or started > latest_preflight_run[slug][0]:
                    latest_preflight_run[slug] = (started, stats)
        for slug, (_started, stats) in latest_preflight_run.items():
            for field in stat_fields:
                if field in stats:
                    preflight_run_totals[slug][field] += int(stats.get(field) or 0)

    current_parser_versions = Counter(
        str(value or "UNKNOWN")
        for value in session.scalars(
            select(Release.parser_version).where(Release.ingestion_status == "published")
        )
    )
    current_schema_versions = Counter(
        str(value or "UNKNOWN")
        for value in session.scalars(
            select(Release.schema_version).where(Release.ingestion_status == "published")
        )
    )
    current_slugs = set(session.scalars(select(Dataset.slug)))

    return {
        "facilities_by_type": grouped(Facility.facility_type),
        "facilities_by_inclusion": grouped(Facility.inclusion_class),
        "facilities_by_publication": grouped(Facility.publication_status),
        "facilities_by_region": dict(sorted(facilities_by_region.items())),
        "facilities_distinct_by_region": dict(sorted(facilities_distinct_by_region.items())),
        "locations_by_precision": grouped(
            FacilityLocation.precision, FacilityLocation.is_current.is_(True)
        ),
        "location_methods": location_methods,
        "psgc": {
            "current_locations": current_locations,
            "locations_with_psgc": locations_with_psgc,
            "facilities_with_location": facilities_with_location,
            "facilities_with_psgc": facilities_with_psgc,
        },
        "run_totals": {key: dict(value) for key, value in sorted(run_totals.items())},
        "preflight_run_totals": {
            key: dict(value) for key, value in sorted(preflight_run_totals.items())
        },
        "match": read_json("match-candidates-generate.json"),
        "fusion": read_json("fusion-apply.json").get("fusion", {}),
        "preflight_parser_versions": dict(preflight_parser_versions),
        "current_parser_versions": dict(current_parser_versions),
        "current_schema_versions": dict(current_schema_versions),
        "datasets_by_publication": grouped(Dataset.publication_status),
        "datasets_by_rights": grouped(Dataset.redistribution_status),
        "datasets_by_authority": grouped(Dataset.authority_level),
        "preflight_dataset_publication": dict(preflight_dataset_publication),
        "preflight_dataset_rights": dict(preflight_dataset_rights),
        "preflight_dataset_authority": dict(preflight_dataset_authority),
        "releases_by_status": grouped(Release.ingestion_status),
        "added_datasets": sorted(current_slugs - preflight_slugs),
    }


def _latest_backup_file(name: str) -> Path | None:
    """Return the newest preserved preflight export with ``name``."""

    candidates = sorted(
        (ROOT / "var" / "backups").glob(f"rebuild-*/{name}"),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _missing_baseline_sources(
    session: Session, run_rows: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    """Return preflight datasets absent from the fresh database with a reason."""

    dataset_file = _latest_backup_file("source_datasets.csv")
    if dataset_file is None:
        return []
    with dataset_file.open(newline="", encoding="utf-8") as handle:
        baseline_slugs = {str(row.get("slug")) for row in csv.DictReader(handle)}
    current_slugs = set(session.scalars(select(Dataset.slug)))
    run_skip_by_dataset = {
        str(row.get("dataset")): str((row.get("skip") or {}).get("skip_reason"))
        for row in run_rows
        if str(row.get("status")) == "skipped" and row.get("dataset")
    }
    missing: list[tuple[str, str]] = []
    for slug in sorted(baseline_slugs - current_slugs):
        reason = None
        for key, source in SOURCES.items():
            if source.dataset.slug == slug:
                decision = skip_for_source(key)
                if decision is not None:
                    reason = decision.reason
                break
        if reason is None:
            reason = run_skip_by_dataset.get(slug)
        missing.append((slug, reason or "UNACCOUNTED"))
    return missing


def _stale_release_summary(session: Session) -> dict[str, Any]:
    """Published releases whose reference period is older than 24 months."""

    cutoff = date.today() - timedelta(days=730)
    rows = session.execute(
        select(Dataset.slug, func.count(Release.id))
        .join(Release, Release.dataset_id == Dataset.id)
        .where(
            Release.ingestion_status == "published",
            Release.reference_period_end < cutoff,
        )
        .group_by(Dataset.slug)
        .order_by(Dataset.slug)
    ).all()
    unknown_reference_end = (
        session.scalar(
            select(func.count())
            .select_from(Release)
            .where(
                Release.ingestion_status == "published",
                Release.reference_period_end.is_(None),
            )
        )
        or 0
    )
    unknown_published_at = (
        session.scalar(
            select(func.count())
            .select_from(Release)
            .where(
                Release.ingestion_status == "published",
                Release.source_published_at.is_(None),
            )
        )
        or 0
    )
    stale_published_at = (
        session.scalar(
            select(func.count())
            .select_from(Release)
            .where(
                Release.ingestion_status == "published",
                Release.source_published_at < datetime.combine(cutoff, datetime.min.time(), UTC),
            )
        )
        or 0
    )
    return {
        "cutoff": cutoff,
        "rows": [(str(slug), int(count)) for slug, count in rows],
        "count": sum(int(count) for _slug, count in rows),
        "unknown_reference_end": unknown_reference_end,
        "unknown_published_at": unknown_published_at,
        "stale_published_at": stale_published_at,
    }


def _count_delta_table(
    title: str,
    old: dict[str, int] | None,
    new: dict[str, int],
) -> list[str]:
    """Render one comparable count table, preserving UNKNOWN where no baseline exists."""

    keys = sorted(set(old or {}) | set(new))
    lines = [
        "",
        f"### {title}",
        "",
        "| Value | Pre-rebuild | Post-rebuild | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in keys:
        before = (old or {}).get(key)
        after = int(new.get(key, 0))
        if isinstance(before, int):
            delta = f"{after - before:+d}"
            before_text = str(before)
        else:
            delta = "UNKNOWN"
            before_text = "UNKNOWN"
        lines.append(f"| `{key}` | {before_text} | {after} | {delta} |")
    return lines


def _delta_metric_sections(
    baseline: dict[str, Any],
    metrics: dict[str, Any],
) -> list[str]:
    """Render the section 8.4 coverage, key, matching and decision deltas."""

    def total(runs: dict[str, dict[str, Any]], field: str) -> int | None:
        values = [int(row[field]) for row in runs.values() if field in row]
        return sum(values) if values else None

    def rate(matched: int | None, provided: int | None) -> str:
        if not provided or matched is None:
            return "UNKNOWN"
        return f"{100 * matched / provided:.2f}%"

    pre_runs = metrics.get("preflight_run_totals") or {}
    cur_runs = metrics.get("run_totals") or {}
    lines = [
        "",
        "`UNKNOWN` means the pre-rebuild breakdown was not preserved in the preflight "
        "exports; no historical value is inferred.",
        "",
        "## Coverage",
    ]
    lines.extend(
        _count_delta_table(
            "Facilities by type",
            baseline.get("facilities_by_type"),
            metrics.get("facilities_by_type") or {},
        )
    )
    lines.extend(
        _count_delta_table(
            "Facilities by inclusion class",
            None,
            metrics.get("facilities_by_inclusion") or {},
        )
    )
    lines.extend(
        _count_delta_table(
            "Facilities by publication state",
            None,
            metrics.get("facilities_by_publication") or {},
        )
    )
    lines.extend(
        _count_delta_table(
            "Facilities by region (distinct facilities)",
            None,
            metrics.get("facilities_distinct_by_region") or {},
        )
    )
    lines.extend(
        _count_delta_table(
            "Current locations by region",
            None,
            metrics.get("facilities_by_region") or {},
        )
    )

    lines.extend(["", "## Coordinate precision and method", ""])
    lines.extend(
        _count_delta_table(
            "Current locations by precision",
            None,
            metrics.get("locations_by_precision") or {},
        )
    )
    lines.extend(
        [
            "",
            "The preflight export recorded only the aggregate coordinate count, not a "
            "precision or method breakdown, so those deltas are `UNKNOWN`.",
            "",
            "| Method | Precision | Post-rebuild |",
            "|---|---|---:|",
        ]
    )
    for row in metrics.get("location_methods") or []:
        lines.append(f"| `{row['method']}` | `{row['precision']}` | {row['count']} |")

    lines.extend(["", "## PSGC matching", ""])
    lines.extend(
        _count_delta_table(
            "Current location rows",
            None,
            metrics.get("psgc") or {},
        )
    )
    provided_before = total(pre_runs, "psgc_provided")
    matched_before = total(pre_runs, "psgc_matched")
    provided_after = total(cur_runs, "psgc_provided")
    matched_after = total(cur_runs, "psgc_matched")
    lines.extend(
        [
            "",
            "Source-record PSGC fields from the latest published preflight run per dataset "
            "and from the fresh rebuild:",
            "",
            "| Measure | Pre-rebuild | Post-rebuild |",
            "|---|---:|---:|",
            f"| PSGC code provided by source | "
            f"{provided_before if provided_before is not None else 'UNKNOWN'} | "
            f"{provided_after if provided_after is not None else 'UNKNOWN'} |",
            f"| PSGC code matched | "
            f"{matched_before if matched_before is not None else 'UNKNOWN'} | "
            f"{matched_after if matched_after is not None else 'UNKNOWN'} |",
            f"| PSGC match rate | {rate(matched_before, provided_before)} | "
            f"{rate(matched_after, provided_after)} |",
        ]
    )

    slugs = sorted(set(cur_runs))
    if slugs:
        lines.extend(
            [
                "",
                "## Per-source record retention",
                "",
                "Counts come from the latest published preflight ingestion run per dataset "
                "and the latest published ingestion run in the fresh database. `UNKNOWN` "
                "means that run did not record the field; a zero is a recorded zero. "
                "Datasets skipped rather than re-ingested appear under Source changes, not "
                "here.",
                "",
                "| Dataset | Pre parsed | Post parsed | Pre accepted | Post accepted | "
                "Pre rejected | Post rejected |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for slug in slugs:
            before = pre_runs.get(slug) or {}
            after = cur_runs.get(slug) or {}

            def value(row: dict[str, Any], field: str) -> str:
                return str(row[field]) if field in row else "UNKNOWN"

            lines.append(
                f"| `{slug}` | {value(before, 'parsed_rows')} | "
                f"{value(after, 'parsed_rows')} | {value(before, 'accepted_rows')} | "
                f"{value(after, 'accepted_rows')} | {value(before, 'rejected_rows')} | "
                f"{value(after, 'rejected_rows')} |"
            )
        lines.extend(
            [
                "",
                "`psgc-bettergov-q2-2024` is the PSGC geography release; its 43,760 "
                "administrative units are counted in `administrative_units`, not as facility "
                "rows.",
            ]
        )

    match = metrics.get("match") or {}
    fusion = metrics.get("fusion") or {}
    current_candidates = match.get("created")
    lines.extend(
        [
            "",
            "## Matching and fusion",
            "",
            "Detailed matching and fusion counters are post-rebuild only; the preflight "
            "export preserved just the two table totals. Rows without a preserved baseline "
            "are `UNKNOWN`.",
            "",
            "| Measure | Pre-rebuild | Post-rebuild | Delta |",
            "|---|---:|---:|---:|",
            f"| `match_candidates` table | {baseline.get('match_candidates', 'UNKNOWN')} | "
            f"{current_candidates if current_candidates is not None else 'UNKNOWN'} | "
            f"{_delta_text(baseline.get('match_candidates'), current_candidates)} |",
        ]
    )
    for label, field in (
        ("Matching facilities scanned", "facilities_scanned"),
        ("Matching groups considered", "groups_considered"),
        ("Matching pairs considered", "pairs_considered"),
        ("Matching candidates created", "created"),
        ("Matching candidates already existing", "existing"),
        ("Matching pairs skipped (same agency)", "skipped_same_agency"),
        ("Matching pairs skipped (subtype)", "skipped_subtype"),
    ):
        new = match.get(field)
        lines.append(f"| {label} | UNKNOWN | {new if new is not None else 'UNKNOWN'} | UNKNOWN |")
    duplicates_before = total(pre_runs, "duplicate_source_ids")
    duplicates_after = total(cur_runs, "duplicate_source_ids")
    lines.append(
        f"| Duplicate source identifiers | "
        f"{duplicates_before if duplicates_before is not None else 'UNKNOWN'} | "
        f"{duplicates_after if duplicates_after is not None else 'UNKNOWN'} | "
        f"{_delta_text(duplicates_before, duplicates_after)} |"
    )
    lines.append(
        f"| `attribute_fusions` table | {baseline.get('attribute_fusions', 'UNKNOWN')} | "
        f"{fusion.get('attributes_written', 'UNKNOWN')} | "
        f"{_delta_text(baseline.get('attribute_fusions'), fusion.get('attributes_written'))} |"
    )
    for label, field in (
        ("Fusion facilities scanned", "facilities_scanned"),
        ("Fusion facilities with claims", "facilities_with_claims"),
        ("Fusion attributes written", "attributes_written"),
        ("Fusion single-source attributes", "single_source"),
        ("Fusion agreed attributes", "agreed"),
        ("Fusion conflicting attributes", "conflict"),
        ("Fusion skipped attributes", "skipped"),
        ("Fusion removed attributes", "removed"),
    ):
        new = fusion.get(field)
        lines.append(f"| {label} | UNKNOWN | {new if new is not None else 'UNKNOWN'} | UNKNOWN |")

    lines.extend(["", "## Parser and schema versions", ""])
    lines.extend(
        _count_delta_table(
            "Published releases by parser version",
            metrics.get("preflight_parser_versions"),
            metrics.get("current_parser_versions") or {},
        )
    )
    lines.extend(["", "### Published releases by schema version", ""])
    lines.extend(
        [
            "| Schema version | Pre-rebuild | Post-rebuild | Delta |",
            "|---|---:|---:|---:|",
        ]
    )
    for version, count in sorted((metrics.get("current_schema_versions") or {}).items()):
        lines.append(f"| `{version}` | UNKNOWN | {count} | UNKNOWN |")

    lines.extend(["", "## Schema and field changes", ""])
    lines.extend(
        [
            f"- `field-matrix.csv` records {metrics.get('field_matrix_rows', 'UNKNOWN')} "
            f"source/field rows across "
            f"{metrics.get('field_matrix_sources', 'UNKNOWN')} sources.",
            f"- `schema-observations.csv` records {metrics.get('schema_rows', 'UNKNOWN')} "
            "release schemas.",
            "- The pre-rebuild field matrix was not preserved in the preflight exports, so "
            "field additions, removals and per-field null-rate deltas are `UNKNOWN`; no "
            "historical value is inferred.",
        ]
    )

    lines.extend(["", "## Dataset decisions", ""])
    lines.extend(
        _count_delta_table(
            "Datasets by authority level",
            metrics.get("preflight_dataset_authority"),
            metrics.get("datasets_by_authority") or {},
        )
    )
    lines.extend(
        _count_delta_table(
            "Datasets by publication state",
            metrics.get("preflight_dataset_publication"),
            metrics.get("datasets_by_publication") or {},
        )
    )
    lines.extend(
        _count_delta_table(
            "Datasets by redistribution status",
            metrics.get("preflight_dataset_rights"),
            metrics.get("datasets_by_rights") or {},
        )
    )
    lines.extend(
        [
            "",
            "Datasets present after the rebuild but absent from the preflight export: "
            + (", ".join(f"`{slug}`" for slug in metrics.get("added_datasets") or []) or "none")
            + ".",
        ]
    )

    inventory = metrics.get("inventory")
    if inventory:
        lines.extend(["", "## Source inventory", ""])
        lines.extend(
            _count_delta_table(
                "Source inventory access states",
                inventory.get("baseline"),
                inventory.get("current") or {},
            )
        )
        lines.extend(
            [
                "",
                "The preflight inventory used `ACCESS_BLOCKED`, `UNVERIFIED`, "
                "`FOI_REQUIRED` and `HUMAN_DOWNLOAD_REQUIRED`; the clean rebuild records "
                "every non-open source as `SKIPPED` with a machine-readable reason. The "
                "state names are therefore not directly interchangeable, and only the "
                "`total` and `OPEN` rows are directly comparable.",
                "",
                f"- Skipped-source rows written: {inventory.get('skipped_rows', 'UNKNOWN')}.",
                f"- Inventory rows reconciling a preflight skip with published release "
                f"evidence: {inventory.get('reconciled', 'UNKNOWN')}.",
            ]
        )
    return lines


def _delta_text(before: Any, after: Any) -> str:
    if isinstance(before, int) and isinstance(after, int):
        return f"{after - before:+d}"
    return "UNKNOWN"


def _markdown_delta(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    metrics: dict[str, Any] | None = None,
    missing_baseline: list[tuple[str, str]] | None = None,
    stale: dict[str, Any] | None = None,
) -> str:
    keys = [
        "facilities",
        "public_facilities",
        "datasets",
        "releases",
        "source_records",
        "facility_source_links",
        "current_locations",
        "locations_with_coordinates",
        "locations_address_only",
        "match_candidates",
        "attribute_fusions",
        "administrative_units",
    ]
    lines = [
        "# Rebuild delta",
        "",
        f"Baseline captured: {baseline.get('captured_at', 'UNKNOWN')}",
        f"Fresh state captured: {current.get('captured_at', 'UNKNOWN')}",
        "",
        "| Measure | Pre-rebuild | Post-rebuild | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in keys:
        old = baseline.get(key)
        new = current.get(key)
        delta = (new - old) if isinstance(old, int) and isinstance(new, int) else None
        lines.append(
            f"| `{key}` | {old if old is not None else 'UNKNOWN'} | "
            f"{new if new is not None else 'UNKNOWN'} | "
            f"{delta:+d} |"
            if delta is not None
            else f"| `{key}` | {old} | {new} | UNKNOWN |"
        )
    lines.extend(
        [
            "",
            "## Source changes",
            "",
            "The preflight dataset list is preserved in "
            "`var/backups/rebuild-20261117/source_datasets.csv`; the fresh list is derived "
            "from the post-rebuild database.",
            "",
        ]
    )
    if missing_baseline:
        lines.extend(
            [
                "| Baseline dataset absent after rebuild | Recorded reason |",
                "|---|---|",
            ]
        )
        for slug, reason in missing_baseline:
            lines.append(f"| `{slug}` | `{reason}` |")
    else:
        lines.append("No baseline dataset is absent from the fresh database.")
    if metrics is not None:
        inventory = metrics.get("inventory") or {}
        lines.extend(
            [
                "",
                "### Change summary",
                "",
                f"- Baseline datasets absent after rebuild: "
                f"{len(missing_baseline) if missing_baseline is not None else 'UNKNOWN'}.",
                f"- Datasets present after rebuild but absent from the preflight export: "
                f"{len(metrics.get('added_datasets') or [])}.",
                f"- Inventory rows newly covered by published-release evidence: "
                f"{inventory.get('reconciled', 'UNKNOWN')}.",
                f"- Skipped sources with a machine-readable reason: "
                f"{inventory.get('skipped_rows', 'UNKNOWN')}.",
                f"- Stale published releases: "
                f"{stale['count'] if stale is not None else 'UNKNOWN'} across "
                f"{len(stale['rows']) if stale is not None else 'UNKNOWN'} datasets.",
                "- `compare-releases` has no pre/post release pair for this rebuild because "
                "the derived release set was replaced; the preserved preflight CSV exports "
                "and database dump are the baseline.",
            ]
        )
        lines.extend(_delta_metric_sections(baseline, metrics))
    if stale is not None:
        lines.extend(
            [
                "",
                "## Freshness",
                "",
                f"- Published releases with a reference period older than 24 months: "
                f"{stale['count']} across {len(stale['rows'])} datasets "
                f"({', '.join(f'`{slug}`={count}' for slug, count in stale['rows']) or 'none'}).",
                f"- Published releases with no reference-period end: "
                f"{stale['unknown_reference_end']}; no source publication date: "
                f"{stale['unknown_published_at']}.",
                f"- Published releases with a source publication date older than 24 months: "
                f"{stale['stale_published_at']}.",
            ]
        )
    lines.extend(
        [
            "",
            "## Publication decisions",
            "",
            "Rights and publication decisions for the fresh release set are in "
            "`rights-register.csv`. A public, official, verified release with no explicit "
            "prohibition is recorded as `publicly_available_verified` and published; "
            "internal-only sources remain in the database as evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _pipeline_adjustments(baseline: dict[str, Any], current: dict[str, Any]) -> str:
    b = baseline
    c = current

    def measure(source: dict[str, Any], key: str) -> Any:
        return source.get(key, "UNKNOWN")

    coord_b = measure(b, "locations_with_coordinates")
    coord_c = measure(c, "locations_with_coordinates")
    address_b = measure(b, "locations_address_only")
    address_c = measure(c, "locations_address_only")

    return f"""# Pipeline adjustments

This rebuild changed eight pipeline concerns. Each change is deterministic, tested,
and keeps the integrity guardrails in `data.md` section 9.2.

## 1. Machine-readable skip states replace blocked/manual queues

- Source: DOH NHFR, DepEd Machine-Ready Files, PSA PSGC, TESDA TVI.
- Stage: `source_runner.run_source`, `sources/catalog._group_for`, `skip_reasons.py`.
- Before: sources could carry `ACCESS_BLOCKED` or a human-review state; groups were
  `approved`/`manual`/`blocked`.
- After: groups are `approved` and `skipped`. A skipped source returns `status=skipped`
  with `skip_reason`, `skip_detail`, `alternate_route` and `next_retry_at`.
- Tests: `apps/ingest/tests/test_skip_reasons.py`.
- Rollback: remove the skip branch in `source_runner.run_source` and restore the old
  group mapping; raw releases and register evidence are untouched.

## 2. Address-only and PSGC-only locations are retained

- Source: facility rows with a postal address or PSGC code but no point.
- Stage: `pipeline/canonical.py`, `pipeline/stats.py`.
- Before: a row without coordinates produced no current `FacilityLocation`.
- After: the row is stored with null geometry/coordinates; coordinates are never
  invented, and an address-only claim cannot displace a coordinate-bearing location.
- Measured before: {baseline.get("locations_address_only", "UNKNOWN")} address-only rows.
- Measured after: {current.get("locations_address_only", "UNKNOWN")} address-only rows.
- Tests: `tests/test_data_quality.py`, plus the canonical-location assertions in the
  integration suite.
- Rollback: restore the coordinate-only guard in `canonical.py`.

## 3. Deterministic OSM coordinate gap-fill

- Source: approved OSM/HOT/Geofabrik community layers.
- Stage: `location_fill.py`, CLI `fill-locations-from-osm`.
- Rule: exact normalized name + same city/municipality + unique candidate; accept only
  a point inside the Philippine plausibility box. Output is
  `precision=map_geocoded`, `method=openstreetmap_match`,
  `review_status=community_fallback`, with OSM id/snapshot and ODbL attribution.
- Never overwrites an official point; ambiguous candidates remain unmapped.
- Tests: `apps/ingest/tests/test_location_fill.py`.
- Rollback: remove the command call; no official data is changed by the fill.

## 4. Fresh probe and rebuild report commands

- Stage: `probe.py`, CLI `probe-sources`, `rebuild_reports.py`,
  CLI `rebuild-report`.
- The probe command makes one unauthenticated GET per URL, records transport errors
  and WAF challenges, and writes both a text ledger compatible with
  `source_inventory.parse_probes` and `probe-ledger.jsonl`.
- The report command writes every file in `data.md` section 11.1 from the inventory,
  the database, the retained raw payloads and the OSM fill report.
- Tests: `apps/ingest/tests/test_probe.py`, `apps/ingest/tests/test_source_report.py`.

## 5. Per-item skip isolation for multi-file catalogues

- Source: PhilHealth provider-category catalogue (one PDF per category).
- Stage: `sources/connectors/philhealth.py`, `source_runner.run_source`,
  `sources/connectors/base.SkippedRelease`.
- Before: the first unreachable PDF raised out of `discover()` and aborted the
  remaining catalogue entries; later categories disappeared from the run without
  a per-item record.
- After: a failed PDF yields a `SkippedRelease` with the controlled `skip_reason`,
  detail, alternate route and retry date; the runner records it as `skipped` and
  continues with the remaining PDFs.
- Measured on 17 Nov 2026: `MCP_073126.pdf` returned HTTP 404 while the other
  catalogue entries remained independently acquirable.
- Tests: `apps/ingest/tests/test_philhealth_connector.py`.
- Rollback: remove the `SkippedRelease` branch in `source_runner.run_source` and
  restore the single `raise` in `PhilHealthConnector.discover`.

## 6. Custom-fetcher releases record their declared source URL

- Source: 33 datasets acquired through custom fetchers (LGU directories, CHED
  HEIDA, DTI Negosyo, PAGASA, NBI, SSS, LRTA, MRT-3, National Museum, PhilHealth
  offices and EBEIS regional result sets).
- Stage: `sources/catalog.py`, `sources/connectors/ebeis.py`,
  `sources/connectors/single_file.py`, `rebuild_reports._release_manifest_rows`.
- Before: `_single(..., fetcher=...)` left `url=None`, so
  `AcquiredRelease.source_url` was empty. The affected dataset rows and 35
  release rows had no URL, and `download-manifest.jsonl` recorded
  `NOT_RECORDED` for source URL, final URL and HTTP status.
- After: every custom-fetcher connector carries the source definition's declared
  URL, EBEIS carries the public masterlist URL, and the 33 affected dataset rows
  were backfilled from those same declarations. The manifest now records the
  URL and uses the dated probe ledger for final URL and HTTP status when a
  separate source check is absent. A final audit added dated HEAD checks for the
  80 published datasets that had no `source_checks` row, so every manifest row
  records `url_evidence` and `url_checked_at`; no HTTP status was inferred.
- Tests: `test_single_file_connectors_record_the_declared_source_url` and the
  EBEIS connector test.
- Rollback: remove the added `url=` arguments and the manifest probe fallback;
  no raw artifact or facility record changes.

## 7. Published-release evidence supersedes stale inventory skips

- Source: inventory candidates whose register or candidate row still said
  UNVERIFIED, `NO_PUBLIC_RELEASE` or HTTP 403 after a later public acquisition
  (for example CHED HEIDA, DSWD CRCF, PPA ports, PhilHealth offices, 19 EBEIS
  regional result sets and the single-LGU directories).
- Stage: `source_report.attach_published_release_evidence`,
  `source_report.enrich_source_inventory`,
  `rebuild_reports.write_rebuild_pack`.
- Before: the pack printed `access_state=SKIPPED` and
  `publication_state=internal_only` for sources with published releases, so the
  inventory contradicted the final report and the download manifest.
- After: an exact source-URL match attaches the published dataset slugs, release
  labels, retrieval time and rights state. The row becomes OPEN/PUBLISHED, while
  the original register access, publication and skip decision remain in
  `register_*` fields. Host-only matches and alternate URLs that another
  candidate claims as its primary URL are not promoted.
- Measured on 17 Nov 2026: 11 inventory rows reconciled; `skipped-sources.jsonl`
  and the crosswalk no longer claim those sources have no acquired release.
- Tests:
  `test_published_release_evidence_supersedes_stale_register_skip` and
  `test_release_evidence_matches_primary_and_unique_alternate_urls` in
  `apps/ingest/tests/test_source_report.py`.
- Rollback: remove the attach call; release rows and raw artifacts are unchanged.

## 8. Every parsed row is retained with its validation status

- Source: OSM education, OSM health, OSM PBF, CHED HEIDA and OSM airports releases
  containing repeated source keys or validator-rejected rows.
- Stage: `pipeline/staging.py` (`_staged_record_keys`,
  `_reconcile_source_record_keys`, `stage_source_records`) and
  `pipeline/runner.py` run statistics.
- Before: `source.records` is unique on `(release_id, source_record_key)`, and
  repeated business keys were skipped. Across the five releases, 930 parsed rows
  had no staged record (OSM education 817, OSM health 108, CHED 5). The staged
  row also copied the parser's default status instead of the validator's
  `rejected_row_references`, so the 40 rejected rows that were staged were
  stored as `valid`.
- After: repeated business keys receive deterministic distinct staging keys,
  repeated row references are retained by position, and rejected rows are
  stamped `validation_status='rejected'` with their linked quality issues.
  `ingestion_runs.stats.rejected_rows_by_code` records the per-code breakdown.
- Measured after reprocessing the preserved artifacts on 17 Nov 2026: 447,823
  parsed rows and 447,823 staged source records (0 staging gaps); 970 rejected
  rows retained (`duplicate_osm_id` 925, `missing_facility_name` 30,
  `coordinate_outside_philippines_bbox` 10, `duplicate_institution_key` 5).
- Tests: `test_validation_failure_skips_canonical_apply`,
  `test_duplicate_business_key_rows_are_retained_and_rejected` and
  `test_reprocess_retains_rows_from_an_older_key_scheme`.
- Rollback: restore the duplicate-key skip and the status copy in
  `stage_source_records`; canonical facilities are unchanged, and the five
  releases can be reprocessed again from their preserved artifacts.

## Retention measurement

| Measure | Pre-rebuild | Post-rebuild |
|---|---:|---:|
| Facilities | {measure(b, "facilities")} | {measure(c, "facilities")} |
| Public facilities | {measure(b, "public_facilities")} | {measure(c, "public_facilities")} |
| Current locations | {measure(b, "current_locations")} | {measure(c, "current_locations")} |
| With coordinates | {coord_b} | {coord_c} |
| Address-only | {address_b} | {address_c} |
| Source records | {measure(b, "source_records")} | {measure(c, "source_records")} |

Validation commands and results are recorded in `validation.txt`; the complete test
suite is run with `uv run pytest`.
"""


def _ingestion_refactor() -> str:
    package = ROOT / "apps" / "ingest" / "philfacilities_ingest"
    rows: list[tuple[str, int]] = []
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rows.append(
            (
                str(path.relative_to(package)),
                len(path.read_text(encoding="utf-8").splitlines()),
            )
        )
    rows.sort(key=lambda item: item[1], reverse=True)
    large = [f"`{name}` ({lines} lines)" for name, lines in rows if lines > 800]
    tree = "\n".join(f"- `{name}`: {lines}" for name, lines in rows[:40])
    return f"""# Ingestion refactor

## Before and after

The pre-rebuild tree had one `pipeline.py` module that mixed release lifecycle,
validation, canonical writes and reporting. The working tree replaces it with a
`pipeline/` package: `runner.py` (lifecycle and stage orchestration),
`release.py` (release and duplicate handling), `staging.py`, `canonical.py`
(identity, locations, assertions and profiles), `geography.py`, `stats.py`,
`common.py` and `locking.py`. Matching and fusion remain separate top-level
modules, one adapter per source lives under `sources/`, and no forwarding module
or parallel pipeline path was left behind.

## Current module sizes

{tree}

Modules above roughly 800 lines: {", ".join(large) if large else "none"}.

## Behaviour-preservation evidence

- `uv run pytest` is the gate; the full suite passed after the move and after the
  rebuild changes. See `validation.txt` for the captured command output.
- Parser and adapter tests run against the same fixtures
  (`apps/ingest/tests/test_parsers.py`, `test_adapter_contract.py`).
- The CLI keeps its public commands; the new commands (`probe-sources`,
  `fill-locations-from-osm`, `rebuild-report`) are additive.
- Raw releases are content-addressed by SHA-256, so a move cannot rewrite evidence.

## Remaining review items

- `sources/registry.py` remains large because it is the single source catalogue;
  it is declarative and is not a second pipeline implementation.
- `cli.py` remains the command surface; business logic lives in the service modules.
"""


def _adapter_handoff(inventory: dict[str, Any]) -> str:
    lines = [
        "# Adapter handoff",
        "",
        "Every registered source with its acquisition shape and validation contract. "
        "The connector owns acquisition; the adapter owns parsing and normalization.",
        "",
        "| Source key | Dataset | Connector | Access | URL | Rights | Publication |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, definition in sorted(SOURCES.items()):
        lines.append(
            f"| `{key}` | `{definition.dataset.slug}` | `{definition.connector}` | "
            f"`{definition.access.method}` | {definition.access.source_url} | "
            f"`{definition.rights.status}` | `{definition.rights.requested_publication_status}` |"
        )
    lines.extend(
        [
            "",
            "## Per-source parser requirements",
            "",
            "The adapter contract is documented in `docs/adding-a-source.md`. For each",
            "source the required invariants are: stable source-record key, original field",
            "names in `raw_payload`, PSGC leading zeros preserved, missing kept distinct",
            "from zero/false, coordinate method and precision recorded, and a validation",
            "floor that fails closed on a schema change.",
            "",
            "## Open questions",
            "",
            "- Sources with `UNKNOWN` update cadence need a publisher refresh statement.",
            "- Candidate sources that are still human-only or `FOI_REQUIRED` are listed in",
            "  `unresolved.md`; they are not adapter gaps.",
            "",
        ]
    )
    return "\n".join(lines)


def _rebuild_plan() -> str:
    return """# Rebuild plan

## Pre-flight evidence

- Database dump: `var/backups/rebuild-20261117/philfacilities-preflight-20261117.dump`
  (SHA-256 recorded in the preflight session; 1.6 GB).
- Table exports: `var/backups/rebuild-20261117/*.csv`.
- Raw store manifest: `var/backups/rebuild-20261117/raw-store-sha256.txt`
  (120 objects, 246 MB, SHA-256 per object).
- Source inventory/status/monitoring/release manifest: `var/reports/rebuild/preflight-*`.
- Baseline counts: `var/reports/rebuild/rebuild-baseline.json`.

## Dependency order

1. PSA/BetterGov PSGC geography and administrative units.
2. Population/geographic enrichment.
3. National facility registries.
4. Regional/field-office releases.
5. LGU and barangay releases.
6. Regulated private-provider and public-access-venue registries.
7. Approved OSM/HOT community layers.
8. Attribute fusion, matching and quality reports.
9. API, web and exports; final reconciliation.

## Acquisition order and commands

```bash
uv run philfacilities-ingest probe-sources
uv run philfacilities-ingest source-inventory \\
  --json-output var/reports/rebuild/source-inventory.json \\
  --csv-output var/reports/rebuild/source-inventory.csv
uv run philfacilities-ingest source-report --output-dir var/reports/rebuild
uv run philfacilities-ingest source run --group approved
uv run philfacilities-ingest fuse-attributes --apply
uv run philfacilities-ingest match-candidates-generate
uv run philfacilities-ingest fill-locations-from-osm --apply \\
  --report var/reports/rebuild/osm-location-fills.json
uv run python scripts/verify_release_urls.py
uv run philfacilities-ingest rebuild-report
```

`rebuild-report` re-reads the register and candidate index after acquisition,
overlays exact published-release evidence on each matching inventory row, and
rewrites the inventory, gap report, skip list and crosswalk. A register row that
recorded a skip but later acquired a release is written as OPEN/PUBLISHED with
the original decision preserved in `register_*` fields; the command does not
change any release or facility record.

## Rollback

- The database is disposable; the preflight dump is the restore point.
- Raw objects are never deleted by a rebuild. A failed release leaves the previous
  verified artifact in the raw store and the source is recorded as skipped.
- Pipeline changes are code-only and reversible by revert; no raw release is rewritten.
"""


def _skipped_rows(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    inventory_skips = [
        source
        for source in inventory.get("sources") or []
        if str(source.get("access_state") or "").upper()
        in {"SKIPPED", "ACCESS_BLOCKED", "FOI_REQUIRED", "MANUAL"}
    ]
    inventory_urls = {
        _source_url_key(str(url))
        for source in inventory_skips
        for url in (source.get("official_urls") or [])
        if url
    }
    for key, definition in sorted(SOURCES.items()):
        if _source_url_key(definition.access.source_url) in inventory_urls:
            # The inventory row is the canonical identity for this URL; keeping a
            # second catalog-key row would duplicate one source under two IDs.
            continue
        decision = skip_for_source(key)
        if decision is None:
            continue
        seen.add(key)
        rows.append(
            {
                "source_id": key,
                "source_key": key,
                "title": definition.dataset.name,
                "custodian": definition.agency.name,
                "url": definition.access.source_url,
                "access_state": "SKIPPED",
                "skip_reason": decision.reason,
                "skip_detail": decision.detail,
                "alternate_route": decision.alternate_route,
                "next_retry_at": decision.next_retry_at,
                "last_probe": None,
            }
        )
    for source in inventory.get("sources") or []:
        source_id = str(source.get("source_id") or "")
        access = str(source.get("access_state") or "").upper()
        if access not in {"SKIPPED", "ACCESS_BLOCKED", "FOI_REQUIRED", "MANUAL"}:
            continue
        if source_id in seen:
            continue
        decision = _candidate_skip_decision(source)
        rows.append(
            {
                "source_id": source_id,
                "source_key": source_id,
                "title": source.get("title"),
                "custodian": source.get("custodian"),
                "url": (source.get("official_urls") or [None])[0],
                "access_state": "SKIPPED",
                "skip_reason": decision.reason,
                "skip_detail": decision.detail,
                "alternate_route": decision.alternate_route,
                "next_retry_at": decision.next_retry_at,
                "last_probe": source.get("probe_date"),
            }
        )
        seen.add(source_id)
    return rows


def _candidate_skip_decision(source: dict[str, Any]) -> SkipDecision:
    access = str(source.get("access_state") or "").upper()
    raw_access = str(source.get("access_state_raw") or "").upper()
    probes = source.get("probes") or []
    statuses = [probe.get("http_status") for probe in probes]
    recorded_reason = str(source.get("skip_reason") or "").upper()
    if recorded_reason in SKIP_REASON_SET:
        return SkipDecision(
            reason=recorded_reason,
            detail=str(
                source.get("skip_detail")
                or (
                    f"Recorded access state {raw_access or access}; "
                    "no automatic public route verified."
                )
            ),
            alternate_route=source.get("alternate_route") or source.get("next_action"),
            next_retry_at=source.get("next_retry_at") or next_retry(),
        )
    if raw_access in {"FOI_REQUIRED", "FOI_ACCESS_CONFIRMED"}:
        return SkipDecision(
            reason="FOI_REQUIRED",
            detail="The public route requires an FOI request; no human step was submitted.",
            alternate_route=source.get("alternate_route") or source.get("next_action"),
            next_retry_at=source.get("next_retry_at") or next_retry(),
        )
    if access in {"FOI_REQUIRED", "FOI_ACCESS_CONFIRMED"}:
        return SkipDecision(
            reason="FOI_REQUIRED",
            detail="The public route requires an FOI request; no human step was submitted.",
            alternate_route=source.get("next_action"),
            next_retry_at=next_retry(),
        )
    if access == "MANUAL":
        return SkipDecision(
            reason="HUMAN_ACCESS_REQUIRED",
            detail="No automatic public acquisition route was verified.",
            alternate_route=source.get("next_action"),
            next_retry_at=next_retry(),
        )
    if 403 in statuses:
        return SkipDecision(
            reason="HTTP_403",
            detail="The probe returned HTTP 403; the access control was not bypassed.",
            alternate_route=source.get("next_action"),
            next_retry_at=next_retry(),
        )
    if 404 in statuses:
        return SkipDecision(
            reason="HTTP_404",
            detail="The probe returned HTTP 404.",
            alternate_route=source.get("next_action"),
            next_retry_at=next_retry(),
        )
    return SkipDecision(
        reason="NO_PUBLIC_RELEASE",
        detail="No automatic public release route was verified.",
        alternate_route=source.get("next_action"),
        next_retry_at=next_retry(),
    )


def _unresolved(skipped: list[dict[str, Any]]) -> str:
    lines = [
        "# Unresolved sources",
        "",
        "Skipped or unverified candidates. No manual approval queue exists; each row is",
        "retried automatically when a public route appears.",
        "",
        "| Source | Custodian | Reason | Route tried | Alternate route | Next retry |",
        "|---|---|---|---|---|---|",
    ]
    for row in skipped[:200]:
        lines.append(
            f"| `{row.get('source_id')}` | {row.get('custodian') or 'UNKNOWN'} | "
            f"`{row.get('skip_reason')}` | {row.get('url') or 'UNKNOWN'} | "
            f"{row.get('alternate_route') or 'NONE_VERIFIED'} | "
            f"{row.get('next_retry_at') or 'NOT_SCHEDULED'} |"
        )
    lines.extend(
        [
            "",
            f"Total rows: {len(skipped)}.",
            "",
            "The exact machine-readable rows are in `skipped-sources.jsonl`.",
            "",
        ]
    )
    return "\n".join(lines)


def _osm_fill_rows(session: Session, fill_path: Path | None) -> list[dict[str, Any]]:
    # The current fill table is the source of truth: it includes fills from
    # earlier runs that are still current. The latest run report is overlaid
    # to retain its more specific match evidence, but it must not hide earlier
    # fills from the deliverable.
    report_by_id: dict[str, dict[str, Any]] = {}
    if fill_path is not None and fill_path.exists():
        document = json.loads(fill_path.read_text(encoding="utf-8"))
        for item in document.get("fills") or []:
            facility_id = str(item.get("facility_id") or "")
            if facility_id:
                report_by_id[facility_id] = item
    rows = session.execute(
        select(Facility, FacilityLocation, SourceRecord, Release, Dataset)
        .join(FacilityLocation, FacilityLocation.facility_id == Facility.id)
        .outerjoin(SourceRecord, FacilityLocation.source_record_id == SourceRecord.id)
        .outerjoin(Release, SourceRecord.release_id == Release.id)
        .outerjoin(Dataset, Release.dataset_id == Dataset.id)
        .where(
            FacilityLocation.is_current.is_(True),
            FacilityLocation.method == "openstreetmap_match",
        )
        .order_by(Facility.display_name)
    ).all()
    output = []
    for facility, location, record, release, dataset in rows:
        item = {
            "facility_id": str(facility.id),
            "facility_slug": facility.slug,
            "facility_name": facility.display_name,
            "facility_type": facility.facility_type,
            "psgc_code": location.psgc_code,
            "address_text": location.address_text,
            "osm_id": record.source_record_key if record else None,
            "osm_name": (record.raw_payload or {}).get("name") if record else None,
            "osm_dataset": dataset.slug if dataset else None,
            "osm_snapshot": release.source_release_label if release else None,
            "match_method": location.method,
            "match_evidence": "openstreetmap_match",
            "precision": location.precision,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "community_fallback": True,
            "attribution": dataset.attribution_text if dataset else None,
            "match_state": "applied",
        }
        detail = report_by_id.get(str(facility.id))
        if detail:
            for key in (
                "osm_id",
                "osm_name",
                "osm_dataset",
                "osm_snapshot",
                "match_evidence",
                "precision",
                "latitude",
                "longitude",
                "match_state",
            ):
                if detail.get(key) is not None:
                    item[key] = detail[key]
        output.append(item)
    return output


def _probe_outcome_counts(payload: dict[str, Any], ledger_path: Path | None = None) -> Counter[str]:
    """Count each probe once, preferring the canonical JSONL ledger.

    A probe is attached to every source that shares its host, so counting the
    inventory attachments directly multiplies observations. The ledger is the
    deliverable and the source of truth when it is present.
    """

    counts: Counter[str] = Counter()
    if ledger_path is not None and ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            probe = json.loads(line)
            counts[str(probe.get("outcome") or "UNKNOWN")] += 1
        return counts

    seen: set[tuple[str, str, str]] = set()
    probes = [
        probe for source in payload.get("sources") or [] for probe in source.get("probes") or []
    ]
    probes.extend(payload.get("unmatched_probes") or [])
    for probe in probes:
        key = (
            str(probe.get("probe_key") or ""),
            str(probe.get("url") or ""),
            str(probe.get("observed_at") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        counts[str(probe.get("outcome") or "UNKNOWN")] += 1
    return counts


def _rejected_row_retention(session: Session) -> list[dict[str, Any]]:
    """Return per-release staged-row retention and rejected-code counts."""

    latest_run_stats: dict[Any, dict[str, Any]] = {}
    for run in session.scalars(
        select(IngestionRun)
        .where(IngestionRun.status == "published", IngestionRun.release_id.is_not(None))
        .order_by(IngestionRun.release_id, IngestionRun.started_at.desc())
    ):
        if run.release_id not in latest_run_stats:
            latest_run_stats[run.release_id] = run.stats if isinstance(run.stats, dict) else {}
    rows = session.execute(
        select(
            Dataset.slug,
            Release.source_release_label,
            Release.id,
            Release.row_count_parsed,
            func.count(SourceRecord.id),
            func.count(SourceRecord.id).filter(SourceRecord.validation_status == "rejected"),
            func.count(SourceRecord.id).filter(SourceRecord.validation_status == "valid"),
        )
        .join(Release, Release.dataset_id == Dataset.id)
        .outerjoin(SourceRecord, SourceRecord.release_id == Release.id)
        .where(Release.ingestion_status == "published")
        .group_by(
            Dataset.slug,
            Release.source_release_label,
            Release.id,
            Release.row_count_parsed,
        )
        .order_by(Dataset.slug, Release.source_release_label)
    ).all()
    retention: list[dict[str, Any]] = []
    for slug, label, release_id, parsed, staged, rejected, valid in rows:
        stats = latest_run_stats.get(release_id) or {}
        codes = stats.get("rejected_rows_by_code") or {}
        retention.append(
            {
                "dataset_slug": slug,
                "release_label": label,
                "parsed_rows": int(parsed or 0),
                "staged_records": int(staged or 0),
                "rejected_records": int(rejected or 0),
                "valid_records": int(valid or 0),
                "rejected_by_code": "; ".join(
                    f"{code}={count}" for code, count in sorted(codes.items())
                ),
            }
        )
    return retention


def _final_report(
    session: Session,
    baseline: dict[str, Any],
    current: dict[str, Any],
    community: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    payload: dict[str, Any],
    fill_document: dict[str, Any] | None = None,
    target: Path | None = None,
) -> str:
    from .sources.definitions import GROUP_APPROVED

    official = (
        session.scalar(
            select(func.count(func.distinct(FacilitySourceLink.facility_id)))
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(Release, SourceRecord.release_id == Release.id)
            .join(Dataset, Release.dataset_id == Dataset.id)
            .where(Dataset.authority_level == "official")
        )
        or 0
    )
    community_count = len(community)
    approved = [key for key, source in SOURCES.items() if source.group == GROUP_APPROVED]
    published_datasets = set(
        session.scalars(
            select(Dataset.slug)
            .join(Release, Release.dataset_id == Dataset.id)
            .where(Release.ingestion_status == "published")
            .distinct()
        )
    )
    approved_published = [
        key for key in approved if SOURCES[key].dataset.slug in published_datasets
    ]
    approved_missing = [
        key for key in approved if SOURCES[key].dataset.slug not in published_datasets
    ]
    missing_with_agency_releases: dict[str, list[str]] = {}
    for key in approved_missing:
        agency_code = SOURCES[key].agency.code
        same_agency = set(
            session.scalars(
                select(Dataset.slug)
                .join(Agency, Dataset.agency_id == Agency.id)
                .join(Release, Release.dataset_id == Dataset.id)
                .where(
                    Agency.short_code == agency_code,
                    Release.ingestion_status == "published",
                )
                .distinct()
            )
        )
        extras = sorted(same_agency - {SOURCES[key].dataset.slug})
        if extras:
            missing_with_agency_releases[key] = extras
    status_rows = session.execute(
        select(Release.ingestion_status, func.count())
        .select_from(Release)
        .group_by(Release.ingestion_status)
        .order_by(Release.ingestion_status)
    ).all()
    statuses = ", ".join(f"{status}={count}" for status, count in status_rows) or "none"
    inventory_sources = payload.get("sources") or []
    probed = sum(1 for source in inventory_sources if source.get("probe_date"))
    inventory_skipped = sum(
        1 for source in inventory_sources if source.get("access_state") == "SKIPPED"
    )
    inventory_reconciled = [
        source
        for source in inventory_sources
        if source.get("published_release_count") and source.get("register_skip_reason")
    ]

    published_dataset_count = (
        session.scalar(
            select(func.count(func.distinct(Dataset.id)))
            .join(Release, Release.dataset_id == Dataset.id)
            .where(Release.ingestion_status == "published")
        )
        or 0
    )
    published_release_count = (
        session.scalar(
            select(func.count()).select_from(Release).where(Release.ingestion_status == "published")
        )
        or 0
    )
    published_authority_rows = session.execute(
        select(Dataset.authority_level, func.count(func.distinct(Dataset.id)))
        .join(Release, Release.dataset_id == Dataset.id)
        .where(Release.ingestion_status == "published")
        .group_by(Dataset.authority_level)
    ).all()
    published_by_authority = ", ".join(
        f"{authority}={count}" for authority, count in published_authority_rows
    )
    pav_rows = session.execute(
        select(Dataset, func.count(Release.id))
        .outerjoin(
            Release,
            (Release.dataset_id == Dataset.id) & (Release.ingestion_status == "published"),
        )
        .where(
            Dataset.publication_status == "published",
            Dataset.redistribution_status == "publicly_available_verified",
        )
        .group_by(Dataset.id)
    ).all()
    pav_datasets = len(pav_rows)
    pav_releases = sum(count for _dataset, count in pav_rows)
    pav_no_license = sum(
        1 for dataset, _count in pav_rows if not (dataset.license_identifier or "").strip()
    )
    pav_no_terms = sum(1 for dataset, _count in pav_rows if not (dataset.terms_url or "").strip())
    approved_no_license_or_terms = (
        session.scalar(
            select(func.count(func.distinct(Dataset.id))).where(
                Dataset.publication_status == "published",
                Dataset.redistribution_status == "approved_with_attribution",
                func.coalesce(Dataset.license_identifier, "") == "",
                func.coalesce(Dataset.terms_url, "") == "",
            )
        )
        or 0
    )

    run_summary: dict[str, int] = {}
    run_rows: list[dict[str, Any]] = []
    run_path = (Path(target) if target is not None else DEFAULT_OUTPUT_DIR) / "rebuild-run.json"
    if run_path.exists():
        try:
            loaded_run_rows = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded_run_rows = []
        if isinstance(loaded_run_rows, list):
            run_rows = loaded_run_rows
            run_summary = dict(Counter(str(row.get("status")) for row in run_rows))
    run_text = ", ".join(f"{status}={count}" for status, count in sorted(run_summary.items()))
    published_release_ids = {
        str(value)
        for value in session.scalars(
            select(Release.id).where(Release.ingestion_status == "published")
        )
    }
    run_release_ids = {str(row.get("release_id")) for row in run_rows if row.get("release_id")}
    run_published_release_ids = run_release_ids & published_release_ids
    run_unpublished_release_ids = run_release_ids - published_release_ids
    prior_published_release_ids = published_release_ids - run_release_ids
    run_unpublished_keys = sorted(
        {
            str(row.get("key") or "UNKNOWN")
            for row in run_rows
            if row.get("release_id") and str(row.get("release_id")) in run_unpublished_release_ids
        }
    )
    retention_rows = _rejected_row_retention(session)
    retention_parsed = sum(row["parsed_rows"] for row in retention_rows)
    retention_staged = sum(row["staged_records"] for row in retention_rows)
    retention_rejected = sum(row["rejected_records"] for row in retention_rows)
    retention_gaps = [row for row in retention_rows if row["parsed_rows"] != row["staged_records"]]
    rejected_by_code: Counter[str] = Counter()
    for row in retention_rows:
        for part in str(row["rejected_by_code"]).split("; "):
            if not part:
                continue
            code, _, count = part.partition("=")
            rejected_by_code[code] += int(count or 0)
    rejected_with_code = sum(rejected_by_code.values())
    rejected_release_rows = [row for row in retention_rows if row["rejected_records"] > 0]

    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in inventory_sources:
        category_rows[str(source.get("category") or "UNKNOWN")].append(source)
    no_open_categories = sorted(
        category
        for category, rows in category_rows.items()
        if not any(str(row.get("access_state") or "").upper() == "OPEN" for row in rows)
    )
    taxonomy_categories = [str(category) for category in (payload.get("taxonomy_categories") or [])]
    no_source_categories = sorted(
        category for category in taxonomy_categories if category not in category_rows
    )
    category_table_rows = []
    for category in sorted(category_rows):
        rows = category_rows[category]
        open_count = sum(1 for row in rows if str(row.get("access_state") or "").upper() == "OPEN")
        category_table_rows.append((category, len(rows), open_count, len(rows) - open_count))

    osm_type_counts = Counter(str(row.get("facility_type") or "UNKNOWN") for row in community)
    osm_region_counts = Counter(str(row.get("region_code") or "UNKNOWN") for row in community)
    official_rows = session.execute(
        select(Facility.facility_type, FacilityLocation.psgc_code)
        .join(FacilitySourceLink, FacilitySourceLink.facility_id == Facility.id)
        .join(SourceRecord, SourceRecord.id == FacilitySourceLink.source_record_id)
        .join(Release, Release.id == SourceRecord.release_id)
        .join(Dataset, Dataset.id == Release.dataset_id)
        .outerjoin(
            FacilityLocation,
            (FacilityLocation.facility_id == Facility.id) & (FacilityLocation.is_current.is_(True)),
        )
        .where(Dataset.authority_level == "official")
        .distinct()
    ).all()
    official_buckets = {
        (str(facility_type or "UNKNOWN"), _region_code(psgc) or "UNKNOWN")
        for facility_type, psgc in official_rows
    }
    osm_buckets = Counter(
        (str(row.get("facility_type") or "UNKNOWN"), str(row.get("region_code") or "UNKNOWN"))
        for row in community
    )
    only_buckets = sorted(
        (
            (bucket, count)
            for bucket, count in osm_buckets.items()
            if bucket not in official_buckets
        ),
        key=lambda item: (-item[1], item[0]),
    )

    skip_counts = Counter(str(row.get("skip_reason") or "UNKNOWN") for row in skipped)
    skip_text = ", ".join(f"{reason}={count}" for reason, count in sorted(skip_counts.items()))
    skipped_by_id = {str(row.get("source_id")): row for row in skipped}
    human_sources = [
        row for row in skipped if str(row.get("skip_reason")) == "HUMAN_ACCESS_REQUIRED"
    ]
    foi_sources = [row for row in skipped if str(row.get("skip_reason")) == "FOI_REQUIRED"]
    explicit_sources = [
        row
        for row in skipped
        if str(row.get("skip_reason")) in {"EXPLICIT_RESTRICTION", "PRIVACY_RESTRICTION"}
    ]

    ledger_path = (target / "probe-ledger.jsonl") if target is not None else None
    probe_outcomes = _probe_outcome_counts(payload, ledger_path)
    probe_text = ", ".join(
        f"{outcome}={count}" for outcome, count in sorted(probe_outcomes.items())
    )

    stale_summary = _stale_release_summary(session)
    stale_rows = stale_summary["rows"]
    stale_release_count = stale_summary["count"]
    unknown_reference_end = stale_summary["unknown_reference_end"]
    unknown_published_at = stale_summary["unknown_published_at"]
    stale_published_at = stale_summary["stale_published_at"]

    published_dataset_ids = set(
        session.scalars(
            select(Dataset.id)
            .join(Release, Release.dataset_id == Dataset.id)
            .where(Release.ingestion_status == "published")
            .distinct()
        )
    )
    check_failures: list[tuple[str, str, int | None]] = []
    for dataset_id, check in _latest_checks(session).items():
        if dataset_id not in published_dataset_ids:
            continue
        if check.status in {"ok", "not_modified", "update_available"} and (
            check.http_status is None or check.http_status < 400
        ):
            continue
        slug = session.scalar(select(Dataset.slug).where(Dataset.id == dataset_id))
        check_failures.append((str(slug or dataset_id), check.status, check.http_status))
    check_failures.sort()

    run_skip_rows = [row for row in run_rows if str(row.get("status")) == "skipped"]
    run_skip_counts = Counter(
        str((row.get("skip") or {}).get("skip_reason") or "UNKNOWN") for row in run_skip_rows
    )
    run_skip_text = ", ".join(
        f"{reason}={count}" for reason, count in sorted(run_skip_counts.items())
    )
    missing_baseline = _missing_baseline_sources(session, run_rows)

    region_ledger = load_region_searches()
    region_searches = region_ledger.get("searches") or []
    region_codes = {
        str(entry.get("region_psgc")) for entry in region_searches if entry.get("region_psgc")
    }
    region_attempts = len(region_searches)
    region_code_count = len(region_codes)
    refactor_note = "See `ingestion-refactor.md`."
    refactor_path = (
        Path(target) if target is not None else DEFAULT_OUTPUT_DIR
    ) / "ingestion-refactor.md"
    if refactor_path.exists():
        for line in refactor_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Modules above roughly 800 lines:"):
                refactor_note = line
                break
    lgu_path = (
        Path(target) if target is not None else DEFAULT_OUTPUT_DIR
    ) / "lgu-search-ledger.csv"
    lgu_total = 0
    lgu_probed = 0
    lgu_probe_attempted = 0
    lgu_no_domain = 0
    lgu_unverified = 0
    if lgu_path.exists():
        with lgu_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                lgu_total += 1
                if (row.get("official_domain") or "").strip():
                    lgu_probed += 1
                if (row.get("probe_urls") or "").strip():
                    lgu_probe_attempted += 1
                if row.get("result") == "NO_OFFICIAL_DOMAIN_VERIFIED":
                    lgu_no_domain += 1
                if row.get("result") == "OFFICIAL_DOMAIN_UNREACHABLE_OR_UNVERIFIED":
                    lgu_unverified += 1

    no_location_rows = session.execute(
        select(Facility.facility_type, func.count())
        .select_from(Facility)
        .where(
            Facility.is_synthetic.is_(False),
            ~select(FacilityLocation.id)
            .where(
                FacilityLocation.facility_id == Facility.id,
                FacilityLocation.is_current.is_(True),
            )
            .exists(),
        )
        .group_by(Facility.facility_type)
        .order_by(func.count().desc(), Facility.facility_type)
    ).all()

    lines = [
        "# Final rebuild report",
        "",
        "## What changed",
        "",
        f"- Canonical facilities: {baseline.get('facilities', 'UNKNOWN')} → "
        f"{current.get('facilities', 'UNKNOWN')}.",
        f"- Public facilities: {baseline.get('public_facilities', 'UNKNOWN')} → "
        f"{current.get('public_facilities', 'UNKNOWN')}.",
        f"- Source records: {baseline.get('source_records', 'UNKNOWN')} → "
        f"{current.get('source_records', 'UNKNOWN')}.",
        f"- Official-linked facilities: {official}.",
        f"- OSM-only community facilities: {community_count}.",
        f"- OSM coordinate fills: {len(fills)}.",
        f"- Published releases: {published_release_count} across "
        f"{published_dataset_count} datasets "
        f"({published_by_authority or 'authority UNKNOWN'}).",
        "",
        "## Newly discovered and acquired",
        "",
        f"- Inventory sources: {len(inventory_sources)} "
        f"(from the register: {payload.get('counts', {}).get('from_register', 'UNKNOWN')}; "
        "from the candidate registry: "
        f"{payload.get('counts', {}).get('from_candidates', 'UNKNOWN')}).",
        f"- No new source identifier was invented in this pass; the {len(inventory_sources)}-"
        "source universe is the preserved inventory, re-probed in this pass. Every public "
        "artifact on an available route was re-acquired; unavailable routes are skipped with "
        "a recorded reason. `osm.sea-ports` is recorded as an alias of `osm.sea_ports`, and "
        "duplicate register entries are linked through `alias_source_ids`, not counted twice.",
        f"- Clean-run outcomes: {run_text or 'UNKNOWN'}.",
        "- `skipped_duplicate` means the identical raw artifact was already preserved by SHA-256; "
        "it is not a new release.",
        f"- The clean-run evidence references {len(run_release_ids)} release IDs: "
        f"{len(run_published_release_ids)} correspond to published releases; "
        f"{len(run_unpublished_release_ids)} "
        + ("has" if len(run_unpublished_release_ids) == 1 else "have")
        + " no persisted published release"
        + (
            " (" + ", ".join(f"`{key}`" for key in run_unpublished_keys) + ")"
            if run_unpublished_keys
            else ""
        )
        + f". {len(prior_published_release_ids)} earlier published releases are retained for "
        f"comparison, so the live total is {published_release_count} published releases across "
        f"{published_dataset_count} datasets.",
        "",
        "## OSM coordinate gap-fill",
        "",
    ]
    if fill_document:
        unlocated = int(fill_document.get("unlocated") or 0)
        matched = int(fill_document.get("matched") or len(fills))
        lines.extend(
            [
                f"- Gap-fill target set (no current point, with PSGC/address evidence): "
                f"{unlocated}.",
                f"- OSM candidates considered: {fill_document.get('candidates', 'UNKNOWN')}.",
                f"- Matched and applied: {matched}.",
                f"- Total current OSM fills (including earlier runs): {len(fills)}.",
                f"- Ambiguous (left unmapped): {fill_document.get('ambiguous', 'UNKNOWN')}.",
                f"- No deterministic candidate: {fill_document.get('unmatched', 'UNKNOWN')}.",
                f"- Already had an OSM fill: {fill_document.get('already_filled', 'UNKNOWN')}.",
                f"- Remaining target rows after this fill: {unlocated - matched}.",
                f"- Facilities still without a current coordinate (live): "
                f"{current.get('facilities_without_current_coordinates', 'UNKNOWN')} "
                f"({current.get('locations_address_only', 'UNKNOWN')} address-only plus "
                f"{current.get('facilities_without_any_current_location', 'UNKNOWN')} with no "
                "current location row).",
            ]
        )
        unresolved = fill_document.get("unresolved_by_category_region") or {}
        if unresolved:
            lines.extend(
                [
                    "",
                    "Remaining address-only by category/region (top 20; facilities with no "
                    "current location row cannot be assigned a region):",
                    "",
                    "| Category \\| region | Count |",
                    "|---|---:|",
                ]
            )
            for bucket, count in sorted(
                unresolved.items(), key=lambda item: (-int(item[1]), item[0])
            )[:20]:
                lines.append(f"| `{bucket}` | {count} |")
        if no_location_rows:
            lines.extend(
                [
                    "",
                    "Facilities with no current location row, by category "
                    f"({sum(count for _, count in no_location_rows)}); region is `UNKNOWN` "
                    "because no current location row records a PSGC:",
                    "",
                    "| Category | Region | Count |",
                    "|---|---|---:|",
                ]
            )
            for facility_type, count in no_location_rows:
                lines.append(f"| `{facility_type}` | UNKNOWN | {count} |")
    else:
        lines.append(
            "No OSM fill report was available; the fill counts are UNKNOWN and no "
            "coordinate was inferred."
        )
    lines.extend(
        [
            "",
            "## OSM-only coverage",
            "",
            f"- OSM-only community facilities: {community_count}.",
            "- Top facility types: "
            + ", ".join(f"{name}={count}" for name, count in osm_type_counts.most_common(10))
            + ".",
            f"- Facilities with no PSGC region: {osm_region_counts.get('UNKNOWN', 0)} of "
            f"{community_count}; the region is not guessed.",
            f"- Facility-type/region buckets where no official facility of the same type and "
            f"region exists: {len(only_buckets)}. Top 10:",
            "",
            "| Facility type | Region | OSM-only count |",
            "|---|---|---:|",
        ]
    )
    for (facility_type, region), count in only_buckets[:10]:
        region_label = "UNKNOWN" if region == "UNKNOWN" else (_region_name(region) or region)
        lines.append(f"| `{facility_type}` | {region_label} | {count} |")
    approved_missing_text = (
        ", ".join(f"`{key}` (`{SOURCES[key].dataset.slug}`)" for key in approved_missing) or "none"
    )
    missing_notes = [
        f"- `{key}` is not counted as published, but the same agency has "
        f"{len(slugs)} published dataset(s) acquired separately "
        f"({', '.join(f'`{slug}`' for slug in slugs[:3])}"
        f"{'…' if len(slugs) > 3 else ''}); those releases are not coverage of "
        f"`{SOURCES[key].dataset.slug}`."
        for key, slugs in missing_with_agency_releases.items()
    ]
    lines.extend(
        [
            "",
            "## Verified acquisition",
            "",
            f"- Approved catalogue sources with at least one published release: "
            f"{len(approved_published)} of {len(approved)}. Not published: "
            f"{approved_missing_text}.",
            *missing_notes,
            f"- Release statuses: {statuses}.",
            f"- Inventory sources with a recorded probe date: {probed} of "
            f"{len(inventory_sources)}; inventory skips: {inventory_skipped}.",
            f"- Inventory rows whose recorded skip was superseded by a published release: "
            f"{len(inventory_reconciled)}"
            + (
                " ("
                + ", ".join(f"`{source.get('source_id')}`" for source in inventory_reconciled)
                + "). The original register state and skip reason are preserved in "
                "`register_*` fields; the exact acquired dataset and release labels are "
                "recorded on each row."
                if inventory_reconciled
                else "."
            ),
            f"- Province/HUC official-domain sweep: 115 targets (82 provinces, 33 highly "
            f"urbanised cities); {lgu_probed} verified official homepages probed, "
            f"{lgu_unverified} attempted but unreachable or unverified, {lgu_no_domain} with "
            "no official domain verified. Evidence: `lgu-domain-probes.json`, "
            "`lgu-search-ledger.csv`, `agency-domain-census.csv`.",
            f"- `publicly_available_verified`: {pav_releases} published releases across "
            f"{pav_datasets} datasets; {pav_no_license} of those datasets have no explicit "
            f"licence identifier and {pav_no_terms} have no recorded terms page.",
            "- Those releases were published with attribution and a takedown route; a missing "
            "licence or terms page was not treated as a prohibition.",
            f"- Separately, {approved_no_license_or_terms} published datasets use "
            "`approved_with_attribution` and record neither a licence nor a terms URL; their "
            "rights evidence is in `rights-register.csv`.",
            "",
            "Approved sources were re-downloaded from their original publisher through the",
            "normal unauthenticated route where that route was available. Raw releases are",
            "preserved by SHA-256; the download manifest records URL, final URL, status,",
            "content type, size and checksum. Sources that could not be acquired are not",
            "presented as covered; they appear in `unresolved.md`.",
            "",
        ]
    )

    priority_skipped_ids = [
        "doh.nhfr",
        "deped.school_masterlist",
        "tesda.providers",
        "doh.licensed_facilities",
        "bfp.fire_stations",
        "pnp.police_stations",
        "ocd.evacuation_centres",
        "caap.airports",
        "marina.ports",
        "bfar.fisheries_facilities",
        "nfa.grain_facilities",
        "psa.psgc",
    ]
    lines.extend(
        [
            "## Highest-value skipped sources",
            "",
            "Selected P0/P1 sources that would add national or regional coverage. The full "
            "list and every alternate route are in `skipped-sources.jsonl` and `unresolved.md`.",
            "",
            "| Source | Reason | Official alternate route |",
            "|---|---|---|",
        ]
    )
    for source_id in priority_skipped_ids:
        row = skipped_by_id.get(source_id)
        if row is None:
            continue
        route = str(row.get("alternate_route") or "NONE_VERIFIED").replace("|", "\\|")
        if len(route) > 240:
            route = route[:237] + "..."
        title = str(row.get("title") or source_id)
        lines.append(f"| `{source_id}` — {title} | `{row.get('skip_reason')}` | {route} |")

    lines.extend(
        [
            "",
            "## Skipped and unresolved",
            "",
            f"{len(skipped)} source rows are skipped or unresolved. Controlled reasons: "
            f"{skip_text}.",
            f"- HUMAN_ACCESS_REQUIRED: {len(human_sources)} — "
            + (", ".join(f"`{row.get('source_id')}`" for row in human_sources) or "none")
            + ".",
            f"- FOI_REQUIRED: {len(foi_sources)} — "
            + (", ".join(f"`{row.get('source_id')}`" for row in foi_sources) or "none")
            + ".",
            f"- EXPLICIT_RESTRICTION or PRIVACY_RESTRICTION: {len(explicit_sources)} — "
            + (", ".join(f"`{row.get('source_id')}`" for row in explicit_sources) or "none")
            + ".",
            "The exact machine-readable rows are in `skipped-sources.jsonl`.",
            "",
            "## Stale, lost and technically failing sources",
            "",
            f"- Published releases with a reference period older than 24 months: "
            f"{stale_release_count} across {len(stale_rows)} datasets "
            f"({', '.join(f'`{slug}`={count}' for slug, count in stale_rows) or 'none'}). "
            "A fixed reference period is not by itself a missed update; the 2024 Census "
            "release remains the latest official census.",
            f"- Published releases with no reference-period end: {unknown_reference_end}; "
            f"no source publication date: {unknown_published_at}. Freshness is unknown for "
            "these rows and is not inferred.",
            f"- Published releases with a source publication date older than 24 months: "
            f"{stale_published_at}.",
            f"- Current artifact-URL checks with an HTTP failure: {len(check_failures)} "
            + (
                "("
                + ", ".join(
                    f"`{slug}`={status} {http if http is not None else 'no status'}"
                    for slug, status, http in check_failures
                )
                + "). "
                if check_failures
                else "(none). "
            )
            + "A failing current URL does not erase the preserved release; it flags the "
            "publisher's changed route for re-discovery.",
            f"- Baseline datasets absent from the fresh database: {len(missing_baseline)}.",
        ]
    )
    if missing_baseline:
        lines.extend(["", "| Baseline dataset | Recorded reason |", "|---|---|"])
        for slug, reason in missing_baseline:
            lines.append(f"| `{slug}` | `{reason}` |")
    lines.extend(
        [
            "",
            f"- Probe outcomes across all targets: {probe_text or 'none recorded'}.",
            f"- Run-level skipped releases: {len(run_skip_rows)} ({run_skip_text or 'none'}).",
            "- Per-release skips are recorded in `rebuild-run.json`; source-level skips are "
            "in `skipped-sources.jsonl`. Neither is treated as a published release.",
            "",
            "## Rejected-row retention",
            "",
            f"- Published releases: {len(retention_rows)}.",
            f"- Parsed rows: {retention_parsed}; staged source records: {retention_staged}; "
            f"releases where staged rows differ from parsed rows: {len(retention_gaps)}.",
            f"- Rejected rows retained with `validation_status='rejected'`: "
            f"{retention_rejected}; rejected rows without a recorded rejection code: "
            f"{max(retention_rejected - rejected_with_code, 0)}.",
            "- Rejected rows are never applied to canonical facilities. They remain in "
            "`source.records` with their linked quality issues; the per-release evidence is "
            "in `rejected-row-retention.csv`.",
            "",
            "| Rejection code | Retained rows |",
            "|---|---:|",
        ]
    )
    for code, count in sorted(rejected_by_code.items()):
        lines.append(f"| `{code}` | {count} |")
    if rejected_release_rows:
        lines.extend(
            [
                "",
                "| Dataset | Release | Parsed | Staged | Rejected | Codes |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for row in rejected_release_rows:
            lines.append(
                f"| `{row['dataset_slug']}` | `{row['release_label']}` | "
                f"{row['parsed_rows']} | {row['staged_records']} | "
                f"{row['rejected_records']} | {row['rejected_by_code'] or 'UNKNOWN'} |"
            )
    lines.extend(
        [
            "",
            "## Remaining gaps",
            "",
            f"- Categories with no OPEN inventory source: "
            f"{', '.join(f'`{category}`' for category in no_open_categories) or 'none'}.",
            f"- Taxonomy categories with no inventoried source: "
            f"{', '.join(f'`{category}`' for category in no_source_categories) or 'none'}.",
            f"- Region-level probes: {region_attempts} observations across {region_code_count} "
            f"of 18 regions. The LGU ledger has {lgu_total} rows; {lgu_probed} of the 115 "
            f"province/highly-urbanised-city targets have a verified official-domain homepage "
            f"probe, {lgu_unverified} were attempted but unreachable or not verified, and "
            f"{lgu_no_domain} have no official domain verified from the discovery leads. Every "
            "province/HUC therefore has a dated probe or a documented negative result; a "
            "homepage probe is not a facility-directory search.",
            "",
            "| Category | Sources | OPEN | SKIPPED |",
            "|---|---:|---:|---:|",
        ]
    )
    for category, total, open_count, skipped_count in category_table_rows:
        lines.append(f"| `{category}` | {total} | {open_count} | {skipped_count} |")
    lines.extend(
        [
            "",
            "Largest OSM-only facility-type/region buckets with no official facility of the "
            "same type/region:",
            "",
            "| Facility type | Region | OSM-only count |",
            "|---|---|---:|",
        ]
    )
    for (facility_type, region), count in only_buckets[:10]:
        region_label = "UNKNOWN" if region == "UNKNOWN" else (_region_name(region) or region)
        lines.append(f"| `{facility_type}` | {region_label} | {count} |")
    lines.extend(
        [
            "",
            "The full gap matrix is `gap-report.md`. Categories and regions with no verified "
            "official release remain gaps; OSM coverage is never counted as official coverage.",
            "",
            "## Refactor",
            "",
            "- `pipeline.py` was replaced by the `pipeline/` package: `runner.py`, `release.py`, "
            "`staging.py`, `canonical.py`, `geography.py`, `stats.py`, `common.py` and "
            "`locking.py`. Matching and fusion remain single top-level modules; no forwarding "
            "module or parallel pipeline path remains.",
            f"- {refactor_note}",
            "- OSM adapters now reject punctuation-only names; 3 legacy community-only "
            "facilities were retired with evidence in `osm-invalid-name-purge.json`.",
            "- See `ingestion-refactor.md` and `pipeline-adjustments.md` for the before/after "
            "tree, removed duplication and rollback paths.",
            "",
            "## Next 10 actions",
            "",
            "1. Recover DOH NHFR/HFSRB through a public route; use the NHA DOH HF layer as a "
            "partial alternate.",
            "2. Acquire the DepEd Machine-Ready Files; 19 EBEIS regional result sets are "
            "already published, but the machine-ready school masterlist remains HTTP 403.",
            "3. Acquire TESDA TVI/assessment-centre directories; CHED HEIDA is published.",
            "4. Recover the missing PhilHealth accredited-providers index PDF "
            "(`MCP_073126.pdf` returns HTTP 404); 27 category datasets are published.",
            "5. Acquire DSWD Standards Bureau directories; the DSWD CRCF directory is published.",
            "6. Add BFP, PNP, OCD/NDRRMC, BJMP, BuCor and DILG evacuation-centre sources.",
            "7. Add CAAP airport directories, MARINA ports, DOTr, PNR, LRTA, MRT-3 and LTFRB "
            "transport facilities; the PPA port list is published.",
            "8. Add LWUA, MWSS, NWRB, DOE and NEA utility facilities.",
            "9. Add DA, BFAR, NFA, PCA, NIA, BAI and PFDA agriculture/fisheries facilities, "
            "plus DENR/EMB/BMB/MGB/NAMRIA environment layers; NMIS NARIS remains blocked by "
            "a TLS failure.",
            "10. Extend the province/HUC official-domain sweep to every municipality and "
            "barangay, and probe facility directories on the 55 verified LGU domains.",
            "",
            "Do not read this report as a claim of complete Philippine facility coverage. It "
            "records what was verified, acquired, skipped and left unknown.",
            "",
        ]
    )
    return "\n".join(lines)


def write_rebuild_pack(
    session: Session,
    payload: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    baseline_path: str | Path | None = None,
    region_ledger_path: str | Path | None = None,
    osm_fill_path: str | Path | None = None,
    probe_ledger_path: str | Path | None = None,
    lgu_probe_path: str | Path | None = None,
) -> RebuildPackPaths:
    target = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    # The pack scans the full national dataset. Parallel workers multiply the
    # memory used by the large community/schema aggregations, which can exhaust
    # a memory-constrained host; a single worker is fast enough with the narrow,
    # streamed queries and keeps generation reproducible.
    session.execute(text("SET max_parallel_workers_per_gather = 0"))
    attach_published_release_evidence(payload, session)
    enrich_source_inventory(payload)
    errors = validate_report_fields(payload)
    if errors:
        raise ValueError("Source inventory is missing data.md fields: " + "; ".join(errors[:20]))

    inventory_json, inventory_csv = write_source_inventory(
        payload,
        target / "source-inventory.json",
        target / "source-inventory.csv",
    )

    probe = target / "probe-ledger.jsonl"
    if probe_ledger_path is not None and Path(probe_ledger_path).exists():
        source_probe = Path(probe_ledger_path).resolve()
        if source_probe != probe.resolve():
            shutil.copyfile(source_probe, probe)
    elif not probe.exists():
        _write_jsonl(probe, build_probe_ledger(payload))

    region_ledger = load_region_searches(region_ledger_path)
    _write_text(target / "gap-report.md", build_gap_report(payload, region_ledger))
    _write_text(target / "acquisition-plan.md", build_acquisition_queue(payload))
    _write_text(target / "region-search-ledger.json", json.dumps(region_ledger, indent=2))

    skipped = _skipped_rows(payload)
    _write_jsonl(target / "skipped-sources.jsonl", skipped)
    _write_text(target / "unresolved.md", _unresolved(skipped))

    manifest = _release_manifest_rows(session, payload)
    _write_jsonl(target / "download-manifest.jsonl", manifest)

    schema = _schema_rows(session)
    _write_csv(
        target / "schema-observations.csv",
        schema,
        [
            "source_key",
            "dataset",
            "release_label",
            "release_date",
            "reference_period_start",
            "reference_period_end",
            "row_count_parsed",
            "original_fields",
            "observed_types",
            "null_tokens",
            "source_record_key",
            "unique_keys",
            "geographic_levels",
            "coordinate_methods",
            "facility_granularity",
            "sample_size",
            "notes",
        ],
    )

    rights = _rights_rows(session)
    _write_csv(
        target / "rights-register.csv",
        rights,
        [
            "source_key",
            "dataset",
            "agency",
            "publisher_domain",
            "release_count",
            "license_identifier",
            "terms_url",
            "rights_basis",
            "redistribution_status",
            "publication_status",
            "gate_status",
            "date_checked",
            "explicit_restriction",
            "personal_data_status",
            "personal_data_fields",
            "security_sensitive_fields",
            "attribution_text",
            "takedown_route",
            "automated_decision",
            "rule_identifier",
            "notes",
        ],
    )

    field_matrix = _field_rows(schema, payload)
    _write_csv(
        target / "field-matrix.csv",
        field_matrix,
        [
            "source_id",
            "source_key",
            "authority_tier",
            "reference_period",
            "field_name",
            "field_status",
            "notes",
        ],
    )

    crosswalk = _crosswalk_rows(schema, payload.get("sources") or [])
    _write_csv(
        target / "crosswalk-candidates.csv",
        crosswalk,
        ["source_key", "dataset", "key_name", "key_type", "observed_in", "stable", "notes"],
    )

    community = _community_rows(session)
    _write_csv(
        target / "community-fallback-register.csv",
        community,
        [
            "facility_id",
            "facility_slug",
            "name",
            "facility_type",
            "region",
            "region_code",
            "psgc_code",
            "osm_source",
            "osm_record_key",
            "osm_id",
            "osm_snapshot",
            "match_state",
            "attribution",
        ],
    )

    fill_target = Path(osm_fill_path) if osm_fill_path is not None else None
    fill_document = None
    if fill_target is not None and fill_target.exists():
        try:
            fill_document = json.loads(fill_target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            fill_document = None
    fills = _osm_fill_rows(session, fill_target)
    _write_csv(
        target / "osm-location-fills.csv",
        fills,
        [
            "facility_id",
            "facility_slug",
            "facility_name",
            "facility_type",
            "psgc_code",
            "address_text",
            "osm_id",
            "osm_name",
            "osm_dataset",
            "osm_snapshot",
            "match_method",
            "match_evidence",
            "precision",
            "latitude",
            "longitude",
            "community_fallback",
            "attribution",
            "match_state",
        ],
    )

    overlap = _overlap_rows(session)
    lines = [
        "# Overlap and unique value",
        "",
        "A source is retained when it adds fields, identifiers, coverage or corroboration.",
        "The table below measures linked facilities, not identity. A high overlap is not a",
        "reason to discard a source.",
        "",
        "| Source | Authority | Coverage | Facilities linked | Conflict fusions |",
        "|---|---|---|---:|---:|",
    ]
    for row in overlap:
        lines.append(
            f"| `{row['source_key']}` | {row['authority_level']} | "
            f"{row['coverage_scope']} | {row['facilities_linked']} | "
            f"{row['conflict_fusions']} |"
        )
    lines.extend(
        [
            "",
            "## Unique field evidence",
            "",
            "Field-level observations are in `field-matrix.csv`. A field sampled from only one",
            "source is a candidate unique field, not a claim of exclusive value.",
            "",
        ]
    )
    _write_text(target / "overlap-and-unique-value.md", "\n".join(lines))

    lgu_probes = load_lgu_probes(lgu_probe_path)
    agencies = _agency_rows(session, lgu_probes, payload)
    _write_csv(
        target / "agency-domain-census.csv",
        agencies,
        [
            "agency",
            "agency_code",
            "agency_level",
            "region",
            "province",
            "city_municipality",
            "publisher_type",
            "official_domain",
            "datasets",
            "releases",
            "last_retrieved_at",
            "source_of_domain",
            "verified_at",
            "notes",
        ],
    )

    lgu_rows = _lgu_rows(session, lgu_probes)
    _write_csv(
        target / "lgu-search-ledger.csv",
        lgu_rows,
        [
            "lgu_psgc_code",
            "lgu_name",
            "region",
            "province",
            "official_domain",
            "probe_urls",
            "result",
            "facility_types_found",
            "facility_count",
            "last_verified",
            "notes",
        ],
    )

    baseline, current = _delta(session, Path(baseline_path) if baseline_path is not None else None)
    run_rows: list[dict[str, Any]] = []
    run_path = target / "rebuild-run.json"
    if run_path.exists():
        try:
            loaded_runs = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded_runs = []
        if isinstance(loaded_runs, list):
            run_rows = loaded_runs
    missing_baseline = _missing_baseline_sources(session, run_rows)
    stale_summary = _stale_release_summary(session)
    metrics = _delta_metrics(session, run_rows, target)
    metrics["field_matrix_rows"] = len(field_matrix)
    metrics["field_matrix_sources"] = len(
        {str(row.get("source_id")) for row in field_matrix if row.get("source_id")}
    )
    metrics["schema_rows"] = len(schema)
    inventory_rows = payload.get("sources") or []
    inventory_access = Counter(str(row.get("access_state") or "UNKNOWN") for row in inventory_rows)
    inventory_current = {
        "total": len(inventory_rows),
        "OPEN": inventory_access.get("OPEN", 0),
        "SKIPPED": inventory_access.get("SKIPPED", 0),
        "published": sum(
            1
            for row in inventory_rows
            if str(row.get("publication_state") or "").lower() == "published"
        ),
        "reconciled": sum(1 for row in inventory_rows if row.get("register_skip_reason")),
    }
    inventory_baseline: dict[str, int] = {}
    preflight_inventory = target / "preflight-source-inventory.json"
    if preflight_inventory.exists():
        try:
            preflight_payload = json.loads(preflight_inventory.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            preflight_payload = {}
        preflight_counts = preflight_payload.get("counts") or {}
        if preflight_counts:
            inventory_baseline["total"] = int(preflight_counts.get("total") or 0)
            for state, count in (preflight_counts.get("by_access_state") or {}).items():
                key = str(state)
                inventory_baseline[key] = inventory_baseline.get(key, 0) + int(count)
            inventory_baseline["published"] = int(preflight_counts.get("published") or 0)
    metrics["inventory"] = {
        "baseline": inventory_baseline,
        "current": inventory_current,
        "skipped_rows": len(skipped),
        "reconciled": inventory_current["reconciled"],
    }
    _write_text(
        target / "rebuild-delta.md",
        _markdown_delta(
            baseline,
            current,
            metrics=metrics,
            missing_baseline=missing_baseline,
            stale=stale_summary,
        ),
    )
    _write_text(target / "pipeline-adjustments.md", _pipeline_adjustments(baseline, current))
    _write_text(target / "ingestion-refactor.md", _ingestion_refactor())
    _write_text(target / "adapter-handoff.md", _adapter_handoff(payload))
    _write_text(target / "rebuild-plan.md", _rebuild_plan())
    _write_csv(
        target / "rejected-row-retention.csv",
        _rejected_row_retention(session),
        [
            "dataset_slug",
            "release_label",
            "parsed_rows",
            "staged_records",
            "rejected_records",
            "valid_records",
            "rejected_by_code",
        ],
    )
    _write_text(
        target / "final-report.md",
        _final_report(
            session,
            baseline,
            current,
            community,
            fills,
            skipped,
            payload,
            fill_document,
            target=target,
        ),
    )

    return RebuildPackPaths(
        source_inventory_json=inventory_json,
        source_inventory_csv=inventory_csv,
        probe_ledger=probe,
        gap_report=target / "gap-report.md",
        skipped_sources=target / "skipped-sources.jsonl",
        acquisition_plan=target / "acquisition-plan.md",
        download_manifest=target / "download-manifest.jsonl",
        schema_observations=target / "schema-observations.csv",
        rights_register=target / "rights-register.csv",
        rebuild_plan=target / "rebuild-plan.md",
        pipeline_adjustments=target / "pipeline-adjustments.md",
        ingestion_refactor=target / "ingestion-refactor.md",
        rebuild_delta=target / "rebuild-delta.md",
        adapter_handoff=target / "adapter-handoff.md",
        field_matrix=target / "field-matrix.csv",
        rejected_row_retention=target / "rejected-row-retention.csv",
        crosswalk_candidates=target / "crosswalk-candidates.csv",
        community_fallback=target / "community-fallback-register.csv",
        osm_location_fills=target / "osm-location-fills.csv",
        overlap_report=target / "overlap-and-unique-value.md",
        agency_domain_census=target / "agency-domain-census.csv",
        lgu_search_ledger=target / "lgu-search-ledger.csv",
        region_search_ledger=target / "region-search-ledger.json",
        unresolved=target / "unresolved.md",
        final_report=target / "final-report.md",
    )
