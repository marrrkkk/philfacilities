"""Build a versioned manifest of the published PhilFacilities data release.

The manifest describes the exact source releases that back the public registry,
their counts and rights state, and the datasets that remain excluded. It is a
release artifact, not a new source of truth: every value is read from the
database and every included dataset/release is already publication-approved.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from philfacilities_api.models import (
    Agency,
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    IngestionRun,
    Release,
    SourceRecord,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MANIFEST_VERSION = "1.0"
SCHEMA_VERSION = "1.0"


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _latest_run(session: Session, release_id: Any) -> IngestionRun | None:
    return session.scalars(
        select(IngestionRun)
        .where(IngestionRun.release_id == release_id)
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    ).first()


def _record_counts(session: Session, release_id: Any) -> tuple[int, int]:
    facility_count = (
        session.scalar(
            select(func.count(func.distinct(FacilitySourceLink.facility_id)))
            .select_from(FacilitySourceLink)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .where(SourceRecord.release_id == release_id)
        )
        or 0
    )
    coordinate_count = (
        session.scalar(
            select(func.count(func.distinct(FacilitySourceLink.facility_id)))
            .select_from(FacilitySourceLink)
            .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
            .join(Facility, FacilitySourceLink.facility_id == Facility.id)
            .join(
                FacilityLocation,
                (FacilityLocation.facility_id == Facility.id)
                & (FacilityLocation.is_current.is_(True)),
            )
            .where(
                SourceRecord.release_id == release_id,
                FacilityLocation.latitude.is_not(None),
                FacilityLocation.longitude.is_not(None),
            )
        )
        or 0
    )
    return facility_count, coordinate_count


def build_release_manifest(
    session: Session,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a deterministic manifest of published datasets and releases."""

    generated_at = generated_at or datetime.now(UTC)
    dataset_rows = session.execute(
        select(Dataset, Agency)
        .join(Agency, Dataset.agency_id == Agency.id)
        .order_by(Agency.short_code, Dataset.slug)
    ).all()

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []

    for dataset, agency in dataset_rows:
        releases = session.scalars(
            select(Release)
            .where(Release.dataset_id == dataset.id)
            .order_by(Release.retrieved_at.desc(), Release.created_at.desc())
        ).all()
        published_release = next(
            (release for release in releases if release.publication_status == "published"),
            None,
        )
        if dataset.publication_status != "published" or published_release is None:
            excluded.append(
                {
                    "dataset_slug": dataset.slug,
                    "dataset_name": dataset.name,
                    "agency_code": agency.short_code,
                    "publication_status": dataset.publication_status,
                    "rights_status": dataset.redistribution_status,
                    "coverage_scope": dataset.coverage_scope or "UNKNOWN_COVERAGE",
                    "reason": (
                        dataset.coverage_note
                        or dataset.rights_basis
                        or "No publication-approved source release is available."
                    ),
                    "latest_release_label": releases[0].source_release_label if releases else None,
                }
            )
            continue

        release = published_release
        facility_count, coordinate_count = _record_counts(session, release.id)
        run = _latest_run(session, release.id)
        run_stats = run.stats if run and run.stats else {}
        included.append(
            {
                "dataset_slug": dataset.slug,
                "dataset_name": dataset.name,
                "agency_code": agency.short_code,
                "agency_name": agency.name,
                "source_url": dataset.source_url,
                "source_release": release.source_release_label,
                "source_published_at": release.source_published_at,
                "reference_period_start": release.reference_period_start,
                "reference_period_end": release.reference_period_end,
                "retrieved_at": release.retrieved_at,
                "published_at": release.processed_at,
                "rights_status": dataset.redistribution_status,
                "publication_status": dataset.publication_status,
                "coverage_scope": dataset.coverage_scope or "UNKNOWN_COVERAGE",
                "coverage_note": dataset.coverage_note,
                "attribution_text": dataset.attribution_text,
                "personal_data_status": dataset.personal_data_status,
                "is_synthetic": dataset.is_synthetic,
                "sha256": release.sha256,
                "raw_object_uri": release.raw_object_uri,
                "row_count_reported": release.row_count_reported,
                "row_count_parsed": release.row_count_parsed,
                "accepted_rows": run_stats.get("accepted_rows"),
                "rejected_rows": run_stats.get("rejected_rows"),
                "linked_facilities": facility_count,
                "with_coordinates": coordinate_count,
                "parser_version": release.parser_version,
            }
        )
        if dataset.coverage_scope and dataset.coverage_scope != "NATIONAL_OFFICIAL_INVENTORY":
            coverage_gaps.append(
                {
                    "dataset_slug": dataset.slug,
                    "coverage_scope": dataset.coverage_scope,
                    "coverage_note": dataset.coverage_note,
                }
            )

    published_facilities = (
        session.scalar(
            select(func.count())
            .select_from(Facility)
            .where(Facility.publication_status == "public")
        )
        or 0
    )
    synthetic_facilities = (
        session.scalar(
            select(func.count())
            .select_from(Facility)
            .where(Facility.publication_status == "public", Facility.is_synthetic.is_(True))
        )
        or 0
    )
    by_inclusion = dict(
        session.execute(
            select(Facility.inclusion_class, func.count())
            .where(Facility.publication_status == "public")
            .group_by(Facility.inclusion_class)
        ).all()
    )
    by_category = dict(
        session.execute(
            select(Facility.facility_type, func.count())
            .where(Facility.publication_status == "public")
            .group_by(Facility.facility_type)
        ).all()
    )
    by_ownership = dict(
        session.execute(
            select(Facility.ownership_type, func.count())
            .where(Facility.publication_status == "public")
            .group_by(Facility.ownership_type)
        ).all()
    )

    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "datasets": included,
        "excluded_datasets": excluded,
        "known_coverage_gaps": coverage_gaps,
        "totals": {
            "datasets_included": len(included),
            "datasets_excluded": len(excluded),
            "published_facilities": published_facilities,
            "synthetic_published_facilities": synthetic_facilities,
            "by_inclusion_class": by_inclusion,
            "by_category": by_category,
            "by_ownership_type": by_ownership,
        },
        "caveats": [
            (
                "The manifest lists only publication-approved source releases. "
                "Excluded datasets are retained internally and are not public data."
            ),
            (
                "Source coverage scope describes the source, not proof of national "
                "completeness. Missing records do not prove a facility does not exist."
            ),
            (
                "Synthetic demo rows are labelled here and in every facility record; "
                "the production database contains zero synthetic facilities."
            ),
        ],
    }
    manifest["checksum"] = _checksum(manifest)
    return manifest


def render_release_notes(manifest: dict[str, Any]) -> str:
    """Render public release notes from a release manifest."""

    totals = manifest["totals"]
    lines = [
        "# PhilFacilities data release notes",
        "",
        f"Generated: {manifest['generated_at']}",
        f"Manifest checksum: `{manifest['checksum']}`",
        "",
        "## Coverage at a glance",
        "",
        f"- Published facilities: **{totals['published_facilities']:,}**",
        f"- Datasets included: **{totals['datasets_included']}**",
        f"- Datasets excluded from publication: **{totals['datasets_excluded']}**",
        f"- Synthetic published facilities: **{totals['synthetic_published_facilities']:,}**",
        "",
        "| Inclusion class | Published facilities |",
        "|---|---:|",
    ]
    for key, value in sorted(totals.get("by_inclusion_class", {}).items()):
        lines.append(f"| {key} | {value:,} |")
    lines.extend(
        [
            "",
            "| Category | Published facilities |",
            "|---|---:|",
        ]
    )
    for key, value in sorted(totals.get("by_category", {}).items()):
        lines.append(f"| {key} | {value:,} |")
    lines.extend(
        [
            "",
            "## Included source releases",
            "",
            (
                "| Dataset | Publisher | Source release | Coverage | Rows parsed | "
                "Linked facilities | Coordinates | Rights |"
            ),
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for item in manifest["datasets"]:
        lines.append(
            "| {dataset} | {agency} | {release} | {coverage} | {rows} | {facilities} | "
            "{coordinates} | {rights} |".format(
                dataset=item["dataset_slug"],
                agency=item["agency_name"],
                release=item["source_release"],
                coverage=item["coverage_scope"],
                rows=item["row_count_parsed"] if item["row_count_parsed"] is not None else "—",
                facilities=item["linked_facilities"],
                coordinates=item["with_coordinates"],
                rights=item["rights_status"],
            )
        )
    lines.extend(["", "## Known coverage gaps", ""])
    if manifest["known_coverage_gaps"]:
        for gap in manifest["known_coverage_gaps"]:
            note = f" — {gap['coverage_note']}" if gap.get("coverage_note") else ""
            lines.append(f"- `{gap['dataset_slug']}`: {gap['coverage_scope']}{note}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Excluded or not yet publishable", ""])
    if manifest["excluded_datasets"]:
        for item in manifest["excluded_datasets"]:
            lines.append(
                f"- `{item['dataset_slug']}` ({item['publication_status']}): {item['reason']}"
            )
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Caveats", ""])
    lines.extend(f"- {caveat}" for caveat in manifest["caveats"])
    lines.append("")
    return "\n".join(lines)


def write_release_manifest(
    session: Session,
    output: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    manifest = build_release_manifest(session, generated_at=generated_at)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return manifest
