#!/usr/bin/env python3
"""Generate the required source, acquisition, schema, quality, and rights reports.

Every value in the generated files is read from the configured PhilFacilities
database. Missing values are reported as ``NULL`` or ``not recorded``; nothing is
estimated or filled in. The generated Markdown is an operational snapshot, not a
legal opinion.

Usage:
    uv run python scripts/generate_data_reports.py
    uv run python scripts/generate_data_reports.py --output-dir var/reports
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from philfacilities_ingest.config import get_settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

DEFAULT_OUTPUT_DIR = Path("var/reports")


def format_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, datetime):
        return value.isoformat()
    text_value = str(value).replace("\n", " ").strip()
    return text_value.replace("|", "\\|")


def markdown_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(format_value(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(path: Path, title: str, generated_at: str, intro: str, body: str) -> None:
    path.write_text(
        f"# {title}\n\n"
        f"**Generated:** {generated_at}  \n"
        f"**Source of truth:** the configured PhilFacilities PostgreSQL database.  \n\n"
        f"{intro}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def dataset_rows(connection: Connection) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            """
            SELECT
                a.short_code AS agency_code,
                a.name AS agency_name,
                d.slug,
                d.name,
                d.source_url,
                d.access_method,
                d.terms_url,
                d.license_identifier,
                d.redistribution_status,
                d.rights_basis,
                d.attribution_text,
                d.personal_data_status,
                d.publication_status,
                d.update_pattern,
                d.schema_version,
                d.is_synthetic,
                (SELECT count(*) FROM source.releases r WHERE r.dataset_id = d.id)
                    AS release_count,
                (SELECT max(r.retrieved_at) FROM source.releases r WHERE r.dataset_id = d.id)
                    AS last_retrieved_at,
                (
                    SELECT count(*)
                    FROM source.records sr
                    JOIN source.releases r ON r.id = sr.release_id
                    WHERE r.dataset_id = d.id
                ) AS source_record_count,
                (
                    SELECT count(DISTINCT fsl.facility_id)
                    FROM source.facility_source_links fsl
                    JOIN source.records sr ON sr.id = fsl.source_record_id
                    JOIN source.releases r ON r.id = sr.release_id
                    WHERE r.dataset_id = d.id
                ) AS linked_facility_count,
                (
                    SELECT count(*)
                    FROM stats.population_observations po
                    JOIN source.releases pr ON pr.id = po.release_id
                    WHERE pr.dataset_id = d.id
                ) AS population_observation_count,
                sc.checked_at AS last_checked_at,
                sc.status AS last_check_status,
                sc.http_status AS last_check_http_status,
                sc.message AS last_check_message,
                lr.source_release_label AS latest_release_label,
                lr.ingestion_status AS latest_release_ingestion_status,
                lr.publication_status AS latest_release_publication_status,
                lr.notes AS latest_release_notes
            FROM source.datasets d
            JOIN source.agencies a ON a.id = d.agency_id
            LEFT JOIN LATERAL (
                SELECT checked_at, status, http_status, message
                FROM source.source_checks
                WHERE dataset_id = d.id
                ORDER BY checked_at DESC
                LIMIT 1
            ) sc ON true
            LEFT JOIN LATERAL (
                SELECT source_release_label, ingestion_status, publication_status, notes
                FROM source.releases
                WHERE dataset_id = d.id
                ORDER BY retrieved_at DESC
                LIMIT 1
            ) lr ON true
            ORDER BY a.short_code, d.slug
            """
        )
    )
    return [dict(row._mapping) for row in result]


def release_rows(connection: Connection) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            """
            SELECT
                r.id,
                a.short_code AS agency_code,
                d.slug,
                d.name AS dataset_name,
                r.source_release_label,
                r.source_published_at,
                r.reference_period_start,
                r.reference_period_end,
                r.retrieved_at,
                r.processed_at,
                r.raw_object_uri,
                r.sha256,
                r.file_format,
                r.file_size_bytes,
                r.row_count_reported,
                r.row_count_parsed,
                r.ingestion_status,
                r.terms_review_status,
                r.publication_status,
                r.parser_version,
                r.notes,
                (SELECT count(*) FROM source.records sr WHERE sr.release_id = r.id)
                    AS source_record_count
            FROM source.releases r
            JOIN source.datasets d ON d.id = r.dataset_id
            JOIN source.agencies a ON a.id = d.agency_id
            ORDER BY a.short_code, d.slug, r.retrieved_at DESC
            """
        )
    )
    return [dict(row._mapping) for row in result]


def latest_run_stats(connection: Connection) -> dict[str, dict[str, Any]]:
    result = connection.execute(
        text(
            """
            SELECT DISTINCT ON (ir.release_id)
                ir.release_id::text AS release_id,
                ir.status,
                ir.started_at,
                ir.finished_at,
                ir.stats,
                ir.report_path,
                ir.error_summary
            FROM source.ingestion_runs ir
            WHERE ir.release_id IS NOT NULL
            ORDER BY ir.release_id, ir.started_at DESC
            """
        )
    )
    return {row.release_id: dict(row._mapping) for row in result}


def geographic_release_rows(connection: Connection) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            """
            SELECT gr.release_label,
                   gr.reference_date,
                   gr.retrieved_at,
                   gr.sha256,
                   gr.raw_object_uri,
                   gr.source_url,
                   gr.is_synthetic,
                   count(au.id) AS units
            FROM geo.geographic_releases gr
            LEFT JOIN geo.administrative_units au ON au.release_id = gr.id
            GROUP BY gr.id
            ORDER BY gr.reference_date DESC NULLS LAST, gr.release_label
            """
        )
    )
    return [dict(row._mapping) for row in result]


def build_source_directory(connection: Connection, generated_at: str) -> str:
    rows = dataset_rows(connection)
    table = markdown_table(
        [
            "Agency",
            "Dataset",
            "Official URL",
            "Access",
            "Update",
            "Rights",
            "Publication",
            "Personal data",
            "Releases",
            "Source records",
            "Population observations",
            "Facilities linked",
            "Last check",
        ],
        (
            [
                row["agency_code"],
                row["slug"],
                row["source_url"],
                row["access_method"],
                row["update_pattern"],
                row["redistribution_status"],
                row["publication_status"],
                row["personal_data_status"],
                row["release_count"],
                row["source_record_count"],
                row["population_observation_count"],
                row["linked_facility_count"],
                (
                    f"{row['last_check_status']} ({row['last_check_http_status']}) "
                    f"at {row['last_checked_at']}"
                    if row["last_check_status"]
                    else "not checked"
                ),
            ]
            for row in rows
        ),
    )
    blocked = [row for row in rows if row["publication_status"] in {"blocked", "internal_only"}]
    blocked_table = markdown_table(
        ["Dataset", "Status", "Reason / latest check"],
        (
            [
                row["slug"],
                row["publication_status"],
                (
                    row["latest_release_notes"]
                    or (
                        row["last_check_message"]
                        if row["last_check_status"] not in (None, "ok", "not_modified")
                        else None
                    )
                    or row["rights_basis"]
                    or "not recorded"
                ),
            ]
            for row in blocked
        ),
    )
    discovery_only = [
        (
            "DOH HFSRB licensed health facilities",
            "https://hfsrb.doh.gov.ph/list-of-licensed-health-facilities/",
            "HTTP 403 Cloudflare challenge; no file or agreement acquired",
            "blocked; no verified public release or agreement-based publication decision",
        ),
        (
            "PSA classification API",
            "https://classification.psa.gov.ph/psgc",
            "`/regions` HTTP 200; data collections require a token that was not obtained",
            "blocked; no token requested or bypassed",
        ),
        (
            "TESDA Assessment Centers",
            "https://www.tesda.gov.ph/AssessmentCenters",
            "not independently acquired",
            "blocked; no verified public release and no agreement-based decision",
        ),
        (
            "HazardHunterPH",
            "https://hazardhunter.georisk.gov.ph/",
            "HTTP 200 HTML; no hazard layer requested",
            "blocked; no hazard layer acquired",
        ),
        (
            "GeoRiskPH",
            "https://georisk.gov.ph/",
            "TLS certificate verification failure from the probe host",
            "blocked; no layer acquired and TLS was not bypassed",
        ),
        (
            "PHIVOLCS",
            "https://www.phivolcs.dost.gov.ph/",
            "main site HTTP 200; maps portal TLS failure",
            "blocked; no layer acquired",
        ),
        (
            "PAGASA / Climgrid",
            "https://www.pagasa.dost.gov.ph/",
            "HTTP 200 HTML; no climate layer requested",
            "blocked; no layer acquired",
        ),
        (
            "DENR-MGB",
            "https://mgb.gov.ph/",
            "HTTP 403 WAF/challenge",
            "blocked; no geohazard layer acquired",
        ),
        (
            "Open Data Philippines",
            "https://data.gov.ph/",
            "HTTP 200 single-page app; public API search returned 404",
            "blocked; no dataset from this catalogue was registered or published",
        ),
    ]
    discovery_table = markdown_table(
        ["Source", "Official URL", "Access result", "Rights / publication"],
        discovery_only,
    )
    geographic_releases = geographic_release_rows(connection)
    geographic_table = markdown_table(
        [
            "Geographic release",
            "Reference date",
            "Retrieved",
            "Units",
            "Synthetic",
            "SHA-256",
            "Raw object",
        ],
        (
            [
                row["release_label"],
                row["reference_date"],
                row["retrieved_at"],
                row["units"],
                row["is_synthetic"],
                row["sha256"],
                row["raw_object_uri"],
            ]
            for row in geographic_releases
        ),
    )
    return (
        "This directory lists every dataset registered in the platform and the "
        "discovery-only sources that were probed but not registered. A listed row is not "
        "evidence that a dataset is accessible, current, complete, or legally publishable.\n\n"
        "**Snapshot note:** this report is generated from the configured database. "
        "Publication decisions, source releases, and canonical facility flags can move at "
        "different times. The governing policy is\n"
        "[docs/data-policy.md](../../docs/data-policy.md); where this snapshot conflicts "
        "with the current database or registry, the database and registry control.\n\n"
        "## Registered sources\n\n"
        f"{table}\n\n"
        "## Versioned geographic releases\n\n"
        "PSGC releases are stored separately from facility datasets so codes keep "
        "their leading zeros and previous releases remain addressable.\n\n"
        f"{geographic_table}\n\n"
        "## Non-public sources\n\n"
        "The following registered datasets are deliberately blocked or internal-only. "
        "They must not be exposed by the public API until the recorded gate changes.\n\n"
        f"{blocked_table}\n\n"
        "## Discovery-only sources (not registered as datasets)\n\n"
        "These sources were probed during source discovery, but no dataset row, "
        "release, file, or field schema was registered. They are listed so the directory "
        "is complete; none is available to the public API.\n\n"
        f"{discovery_table}\n\n"
        "## Reading this directory\n\n"
        "- `approved_with_attribution`, `approved_public_redistribution`, and "
        "`publicly_available_verified` are public-compatible rights states; publication "
        "still requires an approved or published release.\n"
        "- `publicly_available_verified` means the exact release is verified and publicly "
        "available, no explicit prohibition was found, and only reviewed non-personal "
        "fields are published with provenance, attribution, and takedown-on-notice.\n"
        "- `review_required` and `blocked` sources remain unavailable to the public API.\n"
        "- `internal_only` releases may be retained for validation but are excluded from "
        "public endpoints and downloads.\n"
        "- Reachability checks record what an endpoint returned at a point in time; they "
        "do not by themselves establish a rights decision.\n"
        "- Original field names, types, and missing-value statistics are in report 03. "
        "Per-source coverage, acquisition procedure, and evidence notes are in "
        "`docs/sources.md`.\n"
        "- The `Update` column is the recorded expected cadence, not evidence that a "
        "hosted scheduled run exists.\n"
    )


def build_acquisition_report(connection: Connection, generated_at: str) -> str:
    releases = release_rows(connection)
    runs = latest_run_stats(connection)
    table = markdown_table(
        [
            "Dataset",
            "Release",
            "Published",
            "Reference period",
            "Retrieved",
            "Format",
            "Size (bytes)",
            "SHA-256",
            "Rows parsed",
            "Ingestion",
            "Publication",
            "Raw object",
        ],
        (
            [
                row["slug"],
                row["source_release_label"],
                row["source_published_at"],
                (
                    f"{row['reference_period_start']} to {row['reference_period_end']}"
                    if row["reference_period_start"] or row["reference_period_end"]
                    else None
                ),
                row["retrieved_at"],
                row["file_format"],
                row["file_size_bytes"],
                row["sha256"],
                row["row_count_parsed"],
                row["ingestion_status"],
                row["publication_status"],
                row["raw_object_uri"],
            ]
            for row in releases
        ),
    )
    check_rows = connection.execute(
        text(
            """
            SELECT a.short_code, d.slug, sc.checked_at, sc.status, sc.http_status,
                   sc.url, sc.message
            FROM source.source_checks sc
            JOIN source.datasets d ON d.id = sc.dataset_id
            JOIN source.agencies a ON a.id = d.agency_id
            WHERE sc.status NOT IN ('ok', 'not_modified')
            ORDER BY sc.checked_at DESC
            LIMIT 50
            """
        )
    ).all()
    checks = markdown_table(
        ["Agency", "Dataset", "Checked", "Status", "HTTP", "URL", "Message"],
        (
            [
                row.short_code,
                row.slug,
                row.checked_at,
                row.status,
                row.http_status,
                row.url,
                row.message,
            ]
            for row in check_rows
        ),
    )
    run_table = markdown_table(
        [
            "Dataset",
            "Release",
            "Run status",
            "Parsed",
            "Accepted",
            "Rejected",
            "With coordinates",
            "PSGC provided",
            "PSGC matched",
            "Candidate matches",
            "Error",
        ],
        (
            [
                row["slug"],
                row["source_release_label"],
                runs[str(row["id"])]["status"] if str(row["id"]) in runs else "not recorded",
                (runs[str(row["id"])]["stats"] or {}).get("parsed_rows")
                if str(row["id"]) in runs
                else None,
                (runs[str(row["id"])]["stats"] or {}).get("accepted_rows")
                if str(row["id"]) in runs
                else None,
                (runs[str(row["id"])]["stats"] or {}).get("rejected_rows")
                if str(row["id"]) in runs
                else None,
                (runs[str(row["id"])]["stats"] or {}).get("with_coordinates")
                if str(row["id"]) in runs
                else None,
                (runs[str(row["id"])]["stats"] or {}).get("psgc_provided")
                if str(row["id"]) in runs
                else None,
                (runs[str(row["id"])]["stats"] or {}).get("psgc_matched")
                if str(row["id"]) in runs
                else None,
                (runs[str(row["id"])]["stats"] or {}).get("candidate_matches")
                if str(row["id"]) in runs
                else None,
                runs[str(row["id"])]["error_summary"] if str(row["id"]) in runs else None,
            ]
            for row in releases
        ),
    )
    return (
        "This report records actual acquired releases and their immutable file identity. "
        "A release is retained even when its ingestion failed or its publication is "
        "blocked. Per-source access procedures, success evidence, and recovery steps are "
        "in report 06 and `docs/sources.md`.\n\n"
        "## Acquired releases\n\n"
        f"{table}\n\n"
        "## Latest ingestion run per release\n\n"
        f"{run_table}\n\n"
        "## Recorded access failures and blockers\n\n"
        "The following checks record access failures, broken links, and blockers "
        "(`not_modified` responses are healthy and are excluded). They are not releases "
        "and must not be treated as acquired data.\n\n"
        f"{checks or '_No access failures or blockers recorded._'}\n\n"
        "## Preservation\n\n"
        "Per-release statistics are also written to `var/reports/` by the ingestion "
        "pipeline. Original files remain under `var/raw/` by default (or the configured "
        "S3-compatible store); `raw_object_uri` above identifies the preserved copy. A "
        "new source file produces a new release; existing releases are not overwritten.\n"
    )


def build_schema_report(connection: Connection, generated_at: str) -> str:
    datasets = connection.execute(
        text(
            """
            SELECT d.id, d.slug, d.schema_version,
                   (SELECT count(*) FROM source.records sr
                    JOIN source.releases r ON r.id = sr.release_id
                    WHERE r.dataset_id = d.id) AS record_count
            FROM source.datasets d
            ORDER BY d.slug
            """
        )
    ).all()
    sections: list[str] = []
    for dataset in datasets:
        if not dataset.record_count:
            if dataset.slug == "philhealth-emcb-ante":
                sections.append(
                    "### `philhealth-emcb-ante`\n\n"
                    "No source records are currently stored; the release is withdrawn and "
                    "blocked. The retained PDF's provider pages were observed with columns "
                    "`NAME OF HEALTH FACILITY`, `CAT`, `TEL_NO`, `EMAIL`, `STREET`, and "
                    "`MUNICIPALITY`; pages 121-240 carry the aligned `EXPIRE DATE` and `SEC` "
                    "annex. The corrected parser reads 3,221 provider rows. See reports 02 "
                    "and 04 for the withdrawal record.\n"
                )
            else:
                sections.append(
                    f"### `{dataset.slug}`\n\nNo source records are stored for this dataset, "
                    "so no original schema can be reported.\n"
                )
            continue
        key_rows = connection.execute(
            text(
                """
                SELECT e.key,
                       count(*) AS present,
                       count(*) FILTER (
                           WHERE e.value = 'null'::jsonb OR e.value = '""'::jsonb
                       ) AS null_or_blank,
                       string_agg(DISTINCT jsonb_typeof(e.value), ', ') AS json_types,
                       min(e.value #>> '{}') AS sample_value
                FROM source.records sr
                JOIN source.releases r ON r.id = sr.release_id,
                LATERAL jsonb_each(sr.raw_payload) AS e(key, value)
                WHERE r.dataset_id = :dataset_id
                GROUP BY e.key
                ORDER BY present DESC, e.key
                """
            ),
            {"dataset_id": dataset.id},
        ).all()
        unique_keys = connection.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT sr.source_record_key) AS distinct_keys,
                       count(*) FILTER (
                           WHERE sr.source_record_key IS NULL OR btrim(sr.source_record_key) = ''
                       ) AS blank_keys
                FROM source.records sr
                JOIN source.releases r ON r.id = sr.release_id
                WHERE r.dataset_id = :dataset_id
                """
            ),
            {"dataset_id": dataset.id},
        ).one()
        table = markdown_table(
            ["Original key", "Present", "Missing", "Null/blank", "JSON types", "Sample value"],
            (
                [
                    row.key,
                    row.present,
                    dataset.record_count - row.present,
                    row.null_or_blank,
                    row.json_types,
                    row.sample_value,
                ]
                for row in key_rows
            ),
        )
        sections.append(
            f"### `{dataset.slug}`\n\n"
            f"- Declared schema version: `{dataset.schema_version or 'not recorded'}`\n"
            f"- Stored source records: {dataset.record_count}\n"
            f"- Distinct source-record keys: {unique_keys.distinct_keys}\n"
            f"- Duplicate source-record keys: "
            f"{dataset.record_count - unique_keys.distinct_keys}\n"
            f"- Blank source-record keys: {unique_keys.blank_keys}\n\n"
            f"{table}\n"
        )
    mapping_table = markdown_table(
        ["Source family", "Original field / key", "Normalized destination", "Rule / caveat"],
        [
            (
                "PhilHealth provider PDFs",
                "Provider-name column (e.g. `NAME OF HEALTH FACILITY`)",
                "`core.facilities.display_name`, `core.facilities.official_name`",
                "Trimmed for display; the original string remains in `source.records.raw_payload`.",
            ),
            (
                "PhilHealth provider PDFs",
                "Provider category column (e.g. `CAT`)",
                "`core.facilities.facility_subtype`, `health.profiles.facility_category`, "
                "`health.accreditations.accreditation_category`",
                "Benefit-package category, not an operational or licensed status.",
            ),
            (
                "PhilHealth provider PDFs",
                "Contact/address columns where present (`TEL_NO`, `EMAIL`, `STREET`, "
                "`MUNICIPALITY`)",
                "`health.accreditations.telephone`, `.email`, `.street_address`, "
                "`.municipality`; `core.facility_locations.address_text`",
                "Address text is retained; no coordinates are inferred from it.",
            ),
            (
                "PhilHealth provider PDFs",
                "`EXPIRE DATE`",
                "`health.accreditations.valid_until`",
                "Parsed only when the column/value exists; otherwise null.",
            ),
            (
                "PhilHealth provider PDFs",
                "`SEC`",
                "`health.accreditations.sector_code`",
                "Null when the annex/column is absent.",
            ),
            (
                "DepEd EBEIS result pages",
                "`School ID`",
                "`source.records.source_record_key`, `source.records.source_entity_id`, "
                "`school.profiles.deped_school_id`",
                "Leading zeros are preserved; the row key also carries the result-page table row.",
            ),
            (
                "DepEd EBEIS result pages",
                "`School Name`",
                "`core.facilities.display_name`, `core.facilities.official_name`",
                "Original name retained; no cross-source rename is inferred.",
            ),
            (
                "DepEd EBEIS result pages",
                "`School Type`",
                "`core.facilities.facility_subtype`",
                "Stored as reported; school type is not a licensing status.",
            ),
            (
                "DepEd EBEIS result pages",
                "`Address`",
                "`core.facility_locations.address_text`",
                "No coordinates are inferred from the address.",
            ),
            (
                "DepEd EBEIS result pages",
                "`Head / Position`",
                "No normalized field; retained in the private raw record only",
                "Personal data; never published. School-head names are withheld even though "
                "the source release is approved for institution-level publication.",
            ),
            (
                "HOT/OSM GeoParquet",
                "`id`",
                "`source.records.source_record_key`, `source.records.source_entity_id`",
                "Entity key is prefixed `osm:`.",
            ),
            (
                "HOT/OSM GeoParquet",
                "`name` / `name_en`",
                "`core.facilities.display_name`, `core.facilities.official_name`",
                "Unnamed features are rejected rather than invented.",
            ),
            (
                "HOT/OSM GeoParquet",
                "`healthcare` / `amenity` / `building`",
                "`core.facilities.facility_subtype`",
                "Domain-specific choice; the raw tags remain in the source record.",
            ),
            (
                "HOT/OSM GeoParquet",
                "`addr_full` / `addr_city`",
                "`core.facility_locations.address_text`",
                "No address geocoding is performed.",
            ),
            (
                "HOT/OSM GeoParquet",
                "Feature bbox centre",
                "`core.facility_locations.latitude`, `.longitude`",
                "Always `precision=map_geocoded`, "
                "`method=openstreetmap_bbox_center`; never promoted to a precise pin.",
            ),
            (
                "HOT/OSM GeoParquet",
                "`operator_type`",
                "`core.facilities.ownership`",
                "`unknown` when absent; registry presence does not imply operation.",
            ),
            (
                "PSA 2024 Census via BetterGov",
                "`codes[0]`",
                "`stats.population_observations.psgc_code`",
                "PSGC code as text; leading zeros preserved.",
            ),
            (
                "PSA 2024 Census via BetterGov",
                "`codes[1]`",
                "`stats.population_observations.indicator_code`",
                "PSA parameter code; the label is stored separately.",
            ),
            (
                "PSA 2024 Census via BetterGov",
                "`labels[0]` / `labels[1]`",
                "`stats.population_observations.geographic_name` / `.indicator_label`",
                "Original labels retained with leading dots stripped for display only.",
            ),
            (
                "PSA 2024 Census via BetterGov",
                "`value`",
                "`stats.population_observations.value`",
                "Null is preserved; a missing value is never converted to zero.",
            ),
            (
                "BetterGov PSGC mirror",
                "`code`, `area_name`, `geographic_level`",
                "`geo.administrative_units.psgc_code`, `.name`, `.geographic_level`",
                "Versioned per geographic release; leading zeros preserved.",
            ),
            (
                "BetterGov PSGC mirror",
                "`correspondence_code`, `old_name`, `city_class`, "
                "`income_classification`, `urban_rural`, `island_region`",
                "`geo.administrative_units` fields of the same names",
                "Retained as published; previous geographic releases remain addressable.",
            ),
        ],
    )
    return (
        "The tables below describe the original top-level keys actually stored in "
        "`source.records.raw_payload`. They are not an agency-published data dictionary. "
        "Normalization mappings are implemented in the source adapters under "
        "`apps/ingest/philfacilities_ingest/sources/` and are versioned per release.\n\n"
        "Nested objects are reported as a JSON type rather than flattened. Counts are "
        "measured over every stored record for the dataset. No acquired real dataset is "
        "a spreadsheet, so original sheet names are not applicable to the stored data; "
        "the DepEd workbook adapter is unused because no Machine-Ready File was acquired. "
        "Container formats and file identities are in report 02.\n\n"
        "## Normalized field mapping\n\n"
        f"{mapping_table}\n\n"
        "## Per-dataset original schema\n\n" + "\n".join(sections)
    )


def build_quality_report(connection: Connection, generated_at: str) -> str:
    facility_counts = connection.execute(
        text(
            """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE is_synthetic) AS synthetic,
                   count(*) FILTER (WHERE publication_status = 'public') AS public,
                   count(*) FILTER (WHERE publication_status <> 'public') AS non_public
            FROM core.facilities
            """
        )
    ).one()
    by_type = connection.execute(
        text(
            """
            SELECT facility_type, count(*) AS facilities
            FROM core.facilities
            GROUP BY facility_type
            ORDER BY facilities DESC, facility_type
            """
        )
    ).all()
    precision = connection.execute(
        text(
            """
            SELECT fl.precision, count(DISTINCT fl.facility_id) AS facilities
            FROM core.facility_locations fl
            WHERE fl.is_current
            GROUP BY fl.precision
            ORDER BY facilities DESC, fl.precision
            """
        )
    ).all()
    location_counts = connection.execute(
        text(
            """
            SELECT count(*) AS facilities,
                   count(*) FILTER (
                       WHERE EXISTS (
                           SELECT 1 FROM core.facility_locations fl
                           WHERE fl.facility_id = f.id AND fl.is_current
                             AND fl.geom IS NOT NULL
                       )
                   ) AS with_coordinates,
                   count(*) FILTER (
                       WHERE NOT EXISTS (
                           SELECT 1 FROM core.facility_locations fl
                           WHERE fl.facility_id = f.id AND fl.is_current
                       )
                   ) AS without_location,
                   count(*) FILTER (
                       WHERE EXISTS (
                           SELECT 1 FROM core.facility_locations fl
                           WHERE fl.facility_id = f.id AND fl.is_current
                             AND fl.psgc_code IS NULL
                       )
                   ) AS without_psgc
            FROM core.facilities f
            """
        )
    ).one()
    issues = connection.execute(
        text(
            """
            SELECT issue_code, severity, status, count(*) AS issues
            FROM quality.issues
            GROUP BY issue_code, severity, status
            ORDER BY issues DESC, issue_code
            """
        )
    ).all()
    matches = connection.execute(
        text(
            """
            SELECT match_status, count(*) AS candidates
            FROM quality.match_candidates
            GROUP BY match_status
            ORDER BY match_status
            """
        )
    ).all()
    link_counts = connection.execute(
        text(
            """
            SELECT count(*) AS links,
                   count(DISTINCT source_record_id) AS linked_records,
                   count(DISTINCT facility_id) AS linked_facilities,
                   count(*) FILTER (
                       WHERE match_method = 'new_canonical_record'
                   ) AS automatic_new,
                   count(*) FILTER (
                       WHERE match_method = 'exact_agency_id'
                   ) AS exact_agency
            FROM source.facility_source_links
            """
        )
    ).one()
    facility_record_counts = connection.execute(
        text(
            """
            SELECT count(*) AS records,
                   count(*) FILTER (
                       WHERE NOT EXISTS (
                           SELECT 1 FROM source.facility_source_links l
                           WHERE l.source_record_id = sr.id
                       )
                   ) AS unlinked
            FROM source.records sr
            JOIN source.releases r ON r.id = sr.release_id
            JOIN source.datasets d ON d.id = r.dataset_id
            WHERE d.slug <> 'psa-census-2024-population'
            """
        )
    ).one()
    cross_source = connection.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM (
                    SELECT l.facility_id
                    FROM source.facility_source_links l
                    JOIN source.records sr ON sr.id = l.source_record_id
                    JOIN source.releases r ON r.id = sr.release_id
                    GROUP BY l.facility_id
                    HAVING count(DISTINCT r.dataset_id) > 1
                ) multi_dataset) AS multi_dataset_facilities,
                (SELECT count(*) FROM (
                    SELECT l.facility_id
                    FROM source.facility_source_links l
                    JOIN source.records sr ON sr.id = l.source_record_id
                    JOIN source.releases r ON r.id = sr.release_id
                    JOIN source.datasets d ON d.id = r.dataset_id
                    GROUP BY l.facility_id
                    HAVING count(DISTINCT d.agency_id) > 1
                ) multi_agency) AS multi_agency_facilities,
                (SELECT count(*) FROM quality.match_candidates
                 WHERE match_status = 'pending') AS pending_candidates
            """
        )
    ).one()
    population_totals = connection.execute(
        text(
            """
            SELECT count(*) AS observations,
                   count(DISTINCT psgc_code) AS psgc_codes,
                   count(*) FILTER (WHERE value IS NULL) AS null_values,
                   count(*) FILTER (WHERE value = 0) AS zero_values,
                   count(DISTINCT release_id) AS releases,
                   count(*) FILTER (
                       WHERE release_id IN (
                           SELECT r.id
                           FROM source.releases r
                           JOIN source.datasets d ON d.id = r.dataset_id
                           WHERE d.publication_status IN ('approved', 'published')
                             AND r.publication_status IN ('approved', 'published')
                       )
                   ) AS public_observations
            FROM stats.population_observations
            """
        )
    ).one()
    population_levels = connection.execute(
        text(
            """
            SELECT geographic_level, count(*) AS observations,
                   count(DISTINCT psgc_code) AS psgc_codes
            FROM stats.population_observations
            GROUP BY geographic_level
            ORDER BY observations DESC, geographic_level
            """
        )
    ).all()
    population_indicators = connection.execute(
        text(
            """
            SELECT indicator_label, unit, count(*) AS observations,
                   count(*) FILTER (WHERE value IS NULL) AS null_values
            FROM stats.population_observations
            GROUP BY indicator_label, unit
            ORDER BY observations DESC, indicator_label
            """
        )
    ).all()
    population_duplicates = connection.execute(
        text(
            """
            SELECT count(*) AS duplicate_keys
            FROM (
                SELECT release_id, source_record_key
                FROM stats.population_observations
                GROUP BY release_id, source_record_key
                HAVING count(*) > 1
            ) duplicates
            """
        )
    ).scalar_one()
    reconciliation = connection.execute(
        text(
            """
            SELECT d.slug, r.source_release_label,
                   r.row_count_reported, r.row_count_parsed,
                   (SELECT count(*) FROM source.records sr WHERE sr.release_id = r.id)
                       AS stored_records,
                   (SELECT count(*) FROM source.records sr
                    JOIN source.facility_source_links fsl ON fsl.source_record_id = sr.id
                    WHERE sr.release_id = r.id) AS linked_records,
                   (SELECT count(*) FROM source.records sr
                    WHERE sr.release_id = r.id
                      AND NOT EXISTS (
                          SELECT 1 FROM source.facility_source_links fsl
                          WHERE fsl.source_record_id = sr.id
                      )) AS unlinked_records,
                   (SELECT count(*) FROM quality.issues qi
                    WHERE qi.release_id = r.id AND qi.issue_code = 'psgc_unmatched')
                       AS psgc_unmatched,
                   (SELECT count(*) FROM quality.issues qi
                    WHERE qi.release_id = r.id AND qi.issue_code = 'location_missing')
                       AS location_missing,
                   (SELECT count(*) FROM quality.issues qi
                    WHERE qi.release_id = r.id
                      AND qi.issue_code = 'coordinate_outside_philippines_bbox')
                       AS invalid_coordinates,
                   (SELECT count(*) FROM quality.issues qi
                    WHERE qi.release_id = r.id AND qi.issue_code = 'duplicate_source_row')
                       AS duplicate_source_rows
            FROM source.releases r
            JOIN source.datasets d ON d.id = r.dataset_id
            ORDER BY d.slug, r.retrieved_at DESC
            """
        )
    ).all()
    conflict_rows = connection.execute(
        text(
            """
            SELECT attribute_name, count(*) AS facilities
            FROM (
                SELECT facility_id, attribute_name, count(DISTINCT normalized_value) AS values
                FROM core.attribute_assertions
                WHERE normalized_value IS NOT NULL
                GROUP BY facility_id, attribute_name
                HAVING count(DISTINCT normalized_value) > 1
            ) conflicts
            GROUP BY attribute_name
            ORDER BY facilities DESC, attribute_name
            """
        )
    ).all()
    run_stats = connection.execute(
        text(
            """
            SELECT d.slug, r.source_release_label,
                   (ir.stats ->> 'input_rows')::bigint AS input_rows,
                   (ir.stats ->> 'parsed_rows')::bigint AS parsed_rows,
                   (ir.stats ->> 'accepted_rows')::bigint AS accepted_rows,
                   (ir.stats ->> 'rejected_rows')::bigint AS rejected_rows,
                   (ir.stats ->> 'duplicate_source_ids')::bigint AS duplicate_source_ids,
                   (ir.stats ->> 'with_coordinates')::bigint AS with_coordinates,
                   (ir.stats ->> 'psgc_provided')::bigint AS psgc_provided,
                   (ir.stats ->> 'psgc_matched')::bigint AS psgc_matched,
                   (ir.stats ->> 'candidate_matches')::bigint AS candidate_matches,
                   ir.status, ir.error_summary
            FROM source.ingestion_runs ir
            JOIN source.datasets d ON d.id = ir.dataset_id
            JOIN source.releases r ON r.id = ir.release_id
            WHERE ir.id IN (
                SELECT DISTINCT ON (release_id) id
                FROM source.ingestion_runs
                WHERE release_id IS NOT NULL
                ORDER BY release_id, started_at DESC
            )
            ORDER BY d.slug
            """
        )
    ).all()
    stats_table = markdown_table(
        [
            "Dataset",
            "Release",
            "Input",
            "Parsed",
            "Accepted",
            "Rejected",
            "Duplicate IDs",
            "With coords",
            "PSGC provided",
            "PSGC matched",
            "Match candidates",
            "Run status",
            "Error",
        ],
        (
            [
                row.slug,
                row.source_release_label,
                row.input_rows,
                row.parsed_rows,
                row.accepted_rows,
                row.rejected_rows,
                row.duplicate_source_ids,
                row.with_coordinates,
                row.psgc_provided,
                row.psgc_matched,
                row.candidate_matches,
                row.status,
                row.error_summary,
            ]
            for row in run_stats
        ),
    )
    facility_table = markdown_table(
        ["Total", "Synthetic", "Public", "Non-public"],
        [
            [
                facility_counts.total,
                facility_counts.synthetic,
                facility_counts.public,
                facility_counts.non_public,
            ]
        ],
    )
    type_table = markdown_table(
        ["Facility type", "Facilities"],
        [[row.facility_type, row.facilities] for row in by_type],
    )
    location_table = markdown_table(
        [
            "Facilities",
            "With coordinates",
            "Without any current location",
            "With a current location but no PSGC",
        ],
        [
            [
                location_counts.facilities,
                location_counts.with_coordinates,
                location_counts.without_location,
                location_counts.without_psgc,
            ]
        ],
    )
    precision_table = markdown_table(
        ["Precision", "Facilities"],
        [[row.precision, row.facilities] for row in precision],
    )
    match_table = markdown_table(
        ["Candidate status", "Candidates"],
        [[row.match_status, row.candidates] for row in matches],
    )
    identity_table = markdown_table(
        ["Measure", "Count"],
        [
            ["Facility-domain source records", facility_record_counts.records],
            ["Records linked to a canonical facility", link_counts.linked_records],
            ["Records without a canonical link", facility_record_counts.unlinked],
            ["Facilities with at least one source link", link_counts.linked_facilities],
            ["Facilities linked from more than one dataset", cross_source.multi_dataset_facilities],
            ["Facilities linked from more than one agency", cross_source.multi_agency_facilities],
            ["Links created as new canonical records", link_counts.automatic_new],
            ["Links matched by exact agency identifier", link_counts.exact_agency],
            ["Pending / ambiguous match candidates", cross_source.pending_candidates],
        ],
    )
    population_table = markdown_table(
        [
            "Observations",
            "PSGC codes",
            "Releases",
            "Null values",
            "Zero values",
            "Public observations",
            "Duplicate source keys",
        ],
        [
            [
                population_totals.observations,
                population_totals.psgc_codes,
                population_totals.releases,
                population_totals.null_values,
                population_totals.zero_values,
                population_totals.public_observations,
                population_duplicates,
            ]
        ],
    )
    population_level_table = markdown_table(
        ["Geographic level", "Observations", "PSGC codes"],
        [[row.geographic_level, row.observations, row.psgc_codes] for row in population_levels],
    )
    population_indicator_table = markdown_table(
        ["Indicator", "Unit", "Observations", "Null values"],
        [
            [row.indicator_label, row.unit, row.observations, row.null_values]
            for row in population_indicators
        ],
    )
    issue_table = markdown_table(
        ["Issue code", "Severity", "Status", "Count"],
        [[row.issue_code, row.severity, row.status, row.issues] for row in issues],
    )
    reconciliation_table = markdown_table(
        [
            "Dataset",
            "Release",
            "Reported rows",
            "Parsed rows",
            "Stored records",
            "Linked records",
            "Unlinked records",
            "Unmatched PSGC",
            "Missing location",
            "Invalid coordinates",
            "Duplicate source rows",
        ],
        (
            [
                row.slug,
                row.source_release_label,
                row.row_count_reported,
                row.row_count_parsed,
                row.stored_records,
                row.linked_records,
                row.unlinked_records,
                row.psgc_unmatched,
                row.location_missing,
                row.invalid_coordinates,
                row.duplicate_source_rows,
            ]
            for row in reconciliation
        ),
    )
    conflict_table = markdown_table(
        ["Attribute", "Facilities with conflicting source values"],
        [[row.attribute_name, row.facilities] for row in conflict_rows],
    )
    return (
        "This snapshot reports measured counts from the current database. A zero value "
        "means the source reported or the pipeline recorded zero; a missing value means "
        "the measure was not recorded and is not an implied zero.\n\n"
        "## Facility counts\n\n"
        f"{facility_table}\n\n"
        "### By facility type\n\n"
        f"{type_table}\n\n"
        "## Location and geography quality\n\n"
        f"{location_table}\n\n"
        "### Current coordinate precision\n\n"
        f"{precision_table}\n\n"
        "## Identity and cross-source matching\n\n"
        "A linked record is matched to a canonical facility by an exact agency "
        "identifier (OSM feature id, DepEd School ID, or PhilHealth name+municipality "
        "key). Name-only fuzzy merges are not automatic. A facility linked from more "
        "than one dataset has not necessarily been matched across agencies; the "
        "multi-agency count measures that separately.\n\n"
        f"{identity_table}\n\n"
        "### Match-review queue\n\n"
        f"{match_table if matches else '_No match candidates recorded._'}\n\n"
        "## Population statistics\n\n"
        "Population and household counts are stored separately from facility records. "
        "They are never merged into a facility attribute and a null source value is not "
        "converted to zero.\n\n"
        f"{population_table}\n\n"
        "### Observations by geographic level\n\n"
        f"{population_level_table}\n\n"
        "### Observations by indicator\n\n"
        f"{population_indicator_table}\n\n"
        "The source's 2024 Census tables include 42 Manila city-district rows whose labels "
        "do not carry one of PSA's dotted hierarchy prefixes; they are stored with "
        "`geographic_level = unknown` rather than guessed to be a province, city, or "
        "barangay.\n\n"
        "## Recorded quality issues\n\n"
        f"{issue_table}\n\n"
        "## Source-to-database reconciliation\n\n"
        "Reported rows are the source's own count where recorded; parsed and stored "
        "counts are measured in this database. Unlinked records have no canonical "
        "facility link (for example, a rejected or unresolved row). These are not "
        "silently treated as valid facilities.\n\n"
        f"{reconciliation_table}\n\n"
        "## Conflicting source attributes\n\n"
        "Counts facilities whose stored field-level assertions disagree across sources. "
        "Conflict detection is informational; no value is auto-merged.\n\n"
        f"{conflict_table or '_No conflicting normalized assertions recorded._'}\n\n"
        "## Per-release ingestion statistics\n\n"
        f"{stats_table}\n\n"
        "## Interpretation limits\n\n"
        "- Missing coordinates are retained as missing. No coordinates were fabricated to "
        "fill the map.\n"
        "- OSM coordinates are bounding-box centres and are labelled `map_geocoded`, not "
        "verified facility points.\n"
        "- A mapped or registered facility does not prove that it is currently open.\n"
        "- PSGC match counts describe code matching, not boundary or address verification.\n"
    )


def build_rights_report(connection: Connection, generated_at: str) -> str:
    datasets = dataset_rows(connection)
    dataset_table = markdown_table(
        [
            "Dataset",
            "Rights status",
            "Publication status",
            "Basis / terms",
            "Attribution",
            "Personal data",
        ],
        (
            [
                row["slug"],
                row["redistribution_status"],
                row["publication_status"],
                row["rights_basis"] or row["terms_url"] or "not recorded",
                row["attribution_text"],
                row["personal_data_status"],
            ]
            for row in datasets
        ),
    )
    releases = release_rows(connection)
    release_table = markdown_table(
        ["Dataset", "Release", "Terms review", "Publication"],
        (
            [
                row["slug"],
                row["source_release_label"],
                row["terms_review_status"],
                row["publication_status"],
            ]
            for row in releases
        ),
    )
    exposure = connection.execute(
        text(
            """
            SELECT d.slug,
                   count(DISTINCT f.id) FILTER (WHERE f.publication_status = 'public')
                       AS public_facilities,
                   count(DISTINCT f.id) FILTER (WHERE f.publication_status <> 'public')
                       AS non_public_facilities
            FROM source.datasets d
            LEFT JOIN source.releases r ON r.dataset_id = d.id
            LEFT JOIN source.records sr ON sr.release_id = r.id
            LEFT JOIN source.facility_source_links fsl ON fsl.source_record_id = sr.id
            LEFT JOIN core.facilities f ON f.id = fsl.facility_id
            GROUP BY d.slug
            ORDER BY public_facilities DESC, d.slug
            """
        )
    ).all()
    exposure_table = markdown_table(
        ["Dataset", "Public facilities", "Non-public facilities"],
        [[row.slug, row.public_facilities, row.non_public_facilities] for row in exposure],
    )
    return (
        "**This is an evidence register, not a legal opinion.** No source has a completed "
        "formal legal review. Rights states record the terms and source evidence collected "
        "and the technical gate applied by the platform. Publication decisions follow "
        "`docs/data-policy.md`.\n\n"
        "**Snapshot note:** this report is generated from the configured database. A source "
        "registry or release decision and the canonical facility publication flag can move "
        "at different times; a re-ingestion or field-level review is required before every "
        "surface reflects the same state. For example, the current DepEd EBEIS release is "
        "published for institution-level fields, while its canonical facility rows remain "
        "`internal`.\n\n"
        "## Dataset-level rights and publication gates\n\n"
        f"{dataset_table}\n\n"
        "## Release-level gates\n\n"
        f"{release_table}\n\n"
        "## Public exposure by dataset\n\n"
        f"{exposure_table}\n\n"
        "## Enforced rules\n\n"
        "- A facility is public only when its cached publication flag is `public` **and** "
        "it links through a source record and release to a dataset whose redistribution "
        "status is public-compatible and whose release is approved or published.\n"
        "- `restricted_non_redistributable`, `review_required`, `unknown`, `denied`, and "
        "`expired` sources are excluded, even if their records are stored.\n"
        "- `publicly_available_verified` is public-compatible when the exact release is "
        "verified, publicly available, and not subject to an explicit prohibition, and only "
        "reviewed institutional fields are published with provenance, attribution, and "
        "takedown-on-notice.\n"
        "- DepEd EBEIS contains school-head names. The current source release is published "
        "for institution-level fields with those names withheld; canonical facility rows "
        "remain `internal` until field-level mapping and privacy review.\n"
        "- PHLPost publishes 1,272 factual locator facilities under a recorded product "
        "decision; an earlier review-required release is retained internally.\n"
        "- CHED HEIDA is published under `publicly_available_verified` for institutional "
        "fields only; contact details and institutional-head names are discarded and 123 "
        "unknown/CHED-supervised rows remain internal.\n"
        "- Official PSA PSGC, official DepEd Machine-Ready Files, DOH NHFR/HFSRB, TESDA, and "
        "DILG DRRM-PULSE are not published because no verified public release, broader "
        "validated export, or agreement-based publication decision exists.\n"
        "- OSM-derived records carry ODbL attribution and are labelled non-official.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    generated_at = datetime.now(UTC).isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with engine.connect() as connection:
        reports = {
            "01-source-directory.md": (
                "01 — Complete Government Data Source Directory",
                "Every registered dataset and every discovery-only source that was probed.",
                build_source_directory(connection, generated_at),
            ),
            "02-acquisition-report.md": (
                "02 — Acquisition Report",
                "Actual retained releases, checksums, counts, formats, and access failures.",
                build_acquisition_report(connection, generated_at),
            ),
            "03-schema-report.md": (
                "03 — Schema Report",
                "Original stored keys, types, presence, and missing-value counts by dataset.",
                build_schema_report(connection, generated_at),
            ),
            "04-data-quality-report.md": (
                "04 — Data Quality Report",
                "Accepted, rejected, missing, duplicate, geographic, coordinate, "
                "and identity measures.",
                build_quality_report(connection, generated_at),
            ),
            "05-source-rights-report.md": (
                "05 — Source Rights and Publication Report",
                "Recorded rights states and the technical publication gate per dataset "
                "and release.",
                build_rights_report(connection, generated_at),
            ),
        }
        for filename, (title, intro, body) in reports.items():
            write_report(args.output_dir / filename, title, generated_at, intro, body)
            print(f"wrote {args.output_dir / filename}")

    engine.dispose()


if __name__ == "__main__":
    main()
