"""Release lifecycle: agencies, datasets, publication gates, issues, and reports."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from philfacilities_api.models import (
    Agency,
    Dataset,
    PublicationGate,
    QualityIssue,
    Release,
)
from philfacilities_api.rights import (
    PUBLICATION_APPROVED,
    PUBLICATION_BLOCKED,
    PUBLICATION_INTERNAL_ONLY,
    RIGHTS_REVIEW_REQUIRED,
    dataset_is_publishable,
    normalize_rights,
    rights_allow_public,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import IngestSettings
from ..contracts import ReleaseSpec, ValidationIssue
from ..sources.definitions import PUBLISHER_TYPE_BY_AGENCY
from .common import _json, _slug
from .stats import IngestStats


def ensure_source(session: Session, spec: ReleaseSpec) -> tuple[Agency, Dataset, PublicationGate]:
    agency = session.scalars(select(Agency).where(Agency.short_code == spec.agency_code)).first()
    if agency is None:
        agency = Agency(
            name=spec.agency_name,
            short_code=spec.agency_code,
            publisher_type=PUBLISHER_TYPE_BY_AGENCY.get(
                spec.agency_code,
                "government" if not spec.is_synthetic else "synthetic_fixture",
            ),
        )
        session.add(agency)
        session.flush()
    elif not spec.is_synthetic:
        # A real release must never leave the synthetic demo label on an agency
        # that now publishes official or rights-cleared records.
        if "(synthetic demo fixture)" in (agency.name or ""):
            agency.name = spec.agency_name
        agency.publisher_type = PUBLISHER_TYPE_BY_AGENCY.get(
            spec.agency_code, agency.publisher_type or "government"
        )
    rights = (
        spec.redistribution_status
        if spec.is_synthetic
        else normalize_rights(spec.redistribution_status)
    )
    requested_publication = spec.requested_publication_status or (
        PUBLICATION_APPROVED if rights_allow_public(rights) else PUBLICATION_BLOCKED
    )
    if spec.personal_data_status and "internal" in spec.personal_data_status.lower():
        requested_publication = PUBLICATION_INTERNAL_ONLY
    authority_level = (
        "synthetic"
        if spec.is_synthetic
        else spec.authority_level
        or (
            "community"
            if PUBLISHER_TYPE_BY_AGENCY.get(spec.agency_code) == "community"
            else "official"
        )
    )
    dataset = session.scalars(
        select(Dataset).where(Dataset.agency_id == agency.id, Dataset.slug == spec.dataset_slug)
    ).first()
    if dataset is None:
        dataset = Dataset(
            agency_id=agency.id,
            slug=spec.dataset_slug,
            name=spec.dataset_name,
            description=None,
            source_url=spec.source_url,
            access_method=spec.access_method,
            terms_url=spec.terms_url,
            license_identifier=spec.license_identifier,
            redistribution_status=rights,
            rights_basis=spec.rights_basis,
            attribution_text=spec.attribution_text,
            personal_data_status=spec.personal_data_status,
            publication_status=requested_publication,
            authority_level=authority_level,
            coverage_scope=spec.coverage_scope,
            coverage_note=spec.coverage_note,
            update_pattern=spec.update_pattern,
            is_public_source=True,
            is_synthetic=spec.is_synthetic,
        )
        session.add(dataset)
        session.flush()
    else:
        dataset.source_url = spec.source_url or dataset.source_url
        dataset.terms_url = spec.terms_url or dataset.terms_url
        if not dataset.is_synthetic:
            dataset.redistribution_status = rights
        dataset.is_synthetic = dataset.is_synthetic or spec.is_synthetic
        dataset.authority_level = "synthetic" if dataset.is_synthetic else authority_level
        if spec.license_identifier:
            dataset.license_identifier = spec.license_identifier
        if spec.rights_basis:
            dataset.rights_basis = spec.rights_basis
        if spec.attribution_text:
            dataset.attribution_text = spec.attribution_text
        if spec.personal_data_status:
            dataset.personal_data_status = spec.personal_data_status
        if spec.update_pattern:
            dataset.update_pattern = spec.update_pattern
        if spec.coverage_scope:
            dataset.coverage_scope = spec.coverage_scope
        if spec.coverage_note:
            dataset.coverage_note = spec.coverage_note
        if requested_publication in (PUBLICATION_BLOCKED, PUBLICATION_INTERNAL_ONLY):
            dataset.publication_status = requested_publication
    gate = session.scalars(
        select(PublicationGate).where(PublicationGate.dataset_id == dataset.id)
    ).first()
    if gate is None:
        if spec.is_synthetic:
            status = "synthetic_demo"
        elif requested_publication == PUBLICATION_INTERNAL_ONLY:
            status = PUBLICATION_INTERNAL_ONLY
        elif rights_allow_public(rights):
            status = PUBLICATION_APPROVED
        elif normalize_rights(rights) == RIGHTS_REVIEW_REQUIRED:
            status = "review_required"
        else:
            status = PUBLICATION_BLOCKED
        gate = PublicationGate(
            dataset_id=dataset.id,
            status=status,
            scope={"fields": ["facility", "location", "domain", "provenance"]}
            if spec.is_synthetic
            else None,
            reviewer=spec.rights_reviewer or ("automated-policy" if spec.is_synthetic else None),
            reviewed_at=(datetime.now(UTC) if spec.rights_reviewer or spec.is_synthetic else None),
            notes=(
                spec.rights_review_note
                or (
                    "Synthetic fixture data; not an official government release."
                    if spec.is_synthetic
                    else (
                        spec.rights_basis
                        or "Publication awaits source-terms review; records remain internal."
                    )
                )
            ),
        )
        session.add(gate)
        session.flush()
    elif spec.rights_reviewer:
        # A manual import or registry reconciliation records the operator who
        # accepted the rights decision. It does not silently change the gate's
        # publication state; the caller decides that separately.
        gate.reviewer = spec.rights_reviewer
        gate.reviewed_at = datetime.now(UTC)
        if spec.rights_review_note:
            gate.notes = spec.rights_review_note
    return agency, dataset, gate


def _dataset_is_public(dataset: Dataset, gate: PublicationGate) -> bool:
    return dataset_is_publishable(
        redistribution_status=dataset.redistribution_status,
        gate_status=gate.status,
        is_synthetic=dataset.is_synthetic,
        publication_status=dataset.publication_status,
    )


def _existing_release(session: Session, dataset_id: uuid.UUID, sha256: str) -> Release | None:
    return session.scalars(
        select(Release).where(Release.dataset_id == dataset_id, Release.sha256 == sha256)
    ).first()


def _record_issues(
    session: Session,
    *,
    issues: list[ValidationIssue],
    release: Release,
    record_by_row: dict[str, uuid.UUID],
    facility_id: uuid.UUID | None = None,
) -> None:
    for issue in issues:
        session.add(
            QualityIssue(
                facility_id=facility_id,
                source_record_id=record_by_row.get(issue.row_reference or ""),
                release_id=release.id,
                issue_code=issue.code,
                severity=issue.severity if issue.severity != "fatal" else "error",
                message=issue.message,
                details=issue.details,
                status="open",
            )
        )


def _resolve_open_issues(session: Session, release_id: uuid.UUID, issue_code: str) -> None:
    """Retire a transient issue once a later attempt for the same release succeeds."""

    session.execute(
        update(QualityIssue)
        .where(
            QualityIssue.release_id == release_id,
            QualityIssue.issue_code == issue_code,
            QualityIssue.status == "open",
        )
        .values(status="resolved", resolved_at=datetime.now(UTC))
    )


def _write_report(
    settings: IngestSettings,
    *,
    spec: ReleaseSpec,
    run_id: uuid.UUID,
    status: str,
    stats: IngestStats,
    issues: list[dict[str, Any]],
) -> tuple[str, str]:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{spec.dataset_slug}-{_slug(spec.release_label)}-{stamp}-{str(run_id)[:8]}"
    json_path = settings.report_dir / f"{base}.json"
    md_path = settings.report_dir / f"{base}.md"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "agency": spec.agency_code,
        "dataset": spec.dataset_slug,
        "release_label": spec.release_label,
        "source_url": spec.source_url,
        "source_published_at": _json(spec.source_published_at),
        "reference_period_start": _json(spec.reference_period_start),
        "reference_period_end": _json(spec.reference_period_end),
        "retrieved_at": _json(spec.retrieved_at or datetime.now(UTC)),
        "is_synthetic": spec.is_synthetic,
        "redistribution_status": spec.redistribution_status,
        "rights_basis": spec.rights_basis,
        "attribution_text": spec.attribution_text,
        "personal_data_status": spec.personal_data_status,
        "requested_publication_status": spec.requested_publication_status,
        "status": status,
        "stats": stats,
        "issues": issues,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = [
        f"# Ingestion report — {spec.agency_code} / {spec.dataset_slug}",
        "",
        f"- Release: `{spec.release_label}`",
        f"- Status: **{status}**",
        f"- Synthetic fixture: **{spec.is_synthetic}**",
        f"- Source URL: {spec.source_url or 'not supplied'}",
        f"- Retrieved: {payload['retrieved_at']}",
        f"- Reference period: {payload['reference_period_start']} → "
        f"{payload['reference_period_end']}",
        f"- Redistribution: `{spec.redistribution_status}`",
        "",
        "## Counts",
        "",
        "| Measure | Value |",
        "|---|---|",
    ]
    for key, value in stats.items():
        lines.append(
            f"| {key} | {json.dumps(value) if isinstance(value, (dict, list)) else value} |"
        )
    lines += ["", "## Issues", ""]
    if issues:
        lines.append("| Code | Severity | Message | Row |")
        lines.append("|---|---|---|---|")
        for issue in issues:
            lines.append(
                f"| {issue.get('code')} | {issue.get('severity')} | "
                f"{str(issue.get('message', '')).replace('|', '\\|')} | "
                f"{issue.get('row_reference') or ''} |"
            )
    else:
        lines.append("No validation issues were recorded.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)
