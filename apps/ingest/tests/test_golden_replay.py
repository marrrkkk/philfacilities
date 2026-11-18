"""Golden replay of the synthetic demo dataset against the live test database.

The fixture is deterministic. Reloading it from scratch must reproduce the same
canonical facilities, source records, assertions, links, releases, and
publication state. UUIDs and timestamps are deliberately excluded: the golden
contract is the published data, not database identity.

The same test asserts that every facility run recorded stage timings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = Path(__file__).with_name("golden")

FACILITY_FIELDS = (
    "slug",
    "display_name",
    "official_name",
    "facility_type",
    "facility_subtype",
    "facility_kind",
    "ownership",
    "ownership_type",
    "operator_type",
    "public_access_class",
    "access_conditions",
    "record_status",
    "inclusion_class",
    "publication_status",
    "is_synthetic",
)


def _snapshot(session) -> dict:
    from philfacilities_api.models import (
        AttributeAssertion,
        Dataset,
        Facility,
        FacilityLocation,
        FacilitySourceLink,
        IngestionRun,
        QualityIssue,
        Release,
        SourceRecord,
    )

    facilities = session.scalars(select(Facility).order_by(Facility.slug)).all()
    facility_rows = [
        {field: getattr(facility, field) for field in FACILITY_FIELDS} for facility in facilities
    ]

    locations = session.execute(
        select(Facility.slug, FacilityLocation)
        .join(FacilityLocation, FacilityLocation.facility_id == Facility.id)
        .where(FacilityLocation.is_current.is_(True))
        .order_by(Facility.slug)
    ).all()
    location_rows = [
        {
            "facility": slug,
            "latitude": float(location.latitude) if location.latitude is not None else None,
            "longitude": float(location.longitude) if location.longitude is not None else None,
            "precision": location.precision,
            "method": location.method,
            "address_text": location.address_text,
            "psgc_code": location.psgc_code,
        }
        for slug, location in locations
    ]

    records = session.execute(
        select(
            Release.source_release_label,
            SourceRecord.source_record_key,
            SourceRecord.raw_record_hash,
            SourceRecord.validation_status,
        )
        .join(SourceRecord, SourceRecord.release_id == Release.id)
        .order_by(Release.source_release_label, SourceRecord.source_record_key)
    ).all()
    record_rows = [list(row) for row in records]

    links = session.execute(
        select(
            Facility.slug,
            Release.source_release_label,
            SourceRecord.source_record_key,
            FacilitySourceLink.match_method,
            FacilitySourceLink.match_status,
        )
        .select_from(FacilitySourceLink)
        .join(Facility, FacilitySourceLink.facility_id == Facility.id)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .order_by(Facility.slug, Release.source_release_label, SourceRecord.source_record_key)
    ).all()
    link_rows = [list(row) for row in links]

    releases = session.execute(
        select(
            Dataset.slug,
            Release.source_release_label,
            Release.ingestion_status,
            Release.publication_status,
            Release.row_count_parsed,
        )
        .join(Release, Release.dataset_id == Dataset.id)
        .order_by(Dataset.slug, Release.source_release_label)
    ).all()
    release_rows = [list(row) for row in releases]

    datasets = session.execute(
        select(
            Dataset.slug,
            Dataset.publication_status,
            Dataset.redistribution_status,
            Dataset.is_synthetic,
        ).order_by(Dataset.slug)
    ).all()
    dataset_rows = [list(row) for row in datasets]

    assertion_counts = dict(
        session.execute(
            select(AttributeAssertion.attribute_name, func.count())
            .group_by(AttributeAssertion.attribute_name)
            .order_by(AttributeAssertion.attribute_name)
        ).all()
    )
    issue_counts = dict(
        session.execute(
            select(QualityIssue.issue_code, func.count())
            .group_by(QualityIssue.issue_code)
            .order_by(QualityIssue.issue_code)
        ).all()
    )

    payload = {
        "facilities": facility_rows,
        "locations": location_rows,
        "records": record_rows,
        "links": link_rows,
        "releases": release_rows,
        "datasets": dataset_rows,
        "assertions": assertion_counts,
        "issues": issue_counts,
    }
    payload["counts"] = {
        "facilities": len(facility_rows),
        "locations": len(location_rows),
        "records": len(record_rows),
        "links": len(link_rows),
        "assertions": sum(assertion_counts.values()),
    }
    payload["canonical_hash"] = hashlib.sha256(
        json.dumps(
            {
                "facilities": facility_rows,
                "locations": location_rows,
                "records": record_rows,
                "links": link_rows,
                "releases": release_rows,
                "datasets": dataset_rows,
                "assertions": assertion_counts,
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    payload["runs"] = [
        run
        for run in session.scalars(select(IngestionRun).order_by(IngestionRun.started_at)).all()
        if run.stats
    ]
    return payload


def _assert_stage_timings(runs) -> None:
    # Geography releases use the same typed stats container but do not run the
    # facility parse/apply stages, so they carry an empty timings map. Only runs
    # that actually recorded stage timings are facility runs.
    facility_runs = [run for run in runs if (run.stats or {}).get("timings_ms")]
    assert len(facility_runs) >= 5, f"only {len(facility_runs)} timed runs found"

    required = {
        "parse_ms",
        "validate_ms",
        "normalize_ms",
        "stage_records_ms",
        "apply_candidates_ms",
        "report_ms",
    }
    for run in facility_runs:
        stats = run.stats
        assert stats["total_ms"] > 0
        assert stats["rows_per_second"] is None or stats["rows_per_second"] > 0
        missing = required - set(stats["timings_ms"])
        assert not missing, f"run {run.id} is missing stage timings {sorted(missing)}"
        assert all(value >= 0 for value in stats["timings_ms"].values())


def test_demo_replay_is_golden_and_records_stage_timings(db_session) -> None:
    from philfacilities_ingest.cli import load_demo

    load_demo(reset=True)
    db_session.expire_all()
    first = _snapshot(db_session)

    load_demo(reset=True)
    db_session.expire_all()
    second = _snapshot(db_session)

    assert first["counts"] == second["counts"], (
        f"golden replay counts changed: {first['counts']} -> {second['counts']}"
    )
    for section in (
        "facilities",
        "locations",
        "records",
        "links",
        "releases",
        "datasets",
        "assertions",
        "issues",
    ):
        if first[section] != second[section]:
            detail = ""
            if section == "links":
                difference = set(map(tuple, first[section])) ^ set(map(tuple, second[section]))
                detail = f" symmetric difference: {difference}"
            raise AssertionError(f"golden replay changed {section!r}.{detail}")
    assert first["canonical_hash"] == second["canonical_hash"]

    _assert_stage_timings(second["runs"])


PRESERVED_EBEIS_GLOB = "var/raw/deped/deped-ebeis-masterlist-ncr/DEPED-EBEIS-NCR-2026-11-16/*.html"


def _preserved_ebeis_spec():
    """Build a release spec for the newest preserved NCR EBEIS page.

    The raw artifacts live in the gitignored private raw store, so the test is
    skipped on a checkout without them. The golden file stores only counts,
    parser identity, and a hash; no school or personnel data is committed.
    """

    from philfacilities_ingest.sources.registry import REAL_SOURCES, source_spec

    matches = sorted(REPO_ROOT.glob(PRESERVED_EBEIS_GLOB))
    if not matches:
        pytest.skip("preserved EBEIS NCR artifact is not available")
    path = matches[-1]
    return path, source_spec(
        REAL_SOURCES["deped-ebeis"],
        release_label="GOLDEN-PRESERVED-EBEIS-NCR",
        filename=path.name,
        content=path.read_bytes(),
        retrieved_at=datetime(2026, 11, 16, tzinfo=UTC),
        enqueue_cross_source_matches=False,
        notes="Read-only golden replay of a preserved EBEIS masterlist page.",
    )


def _preserved_parse_fingerprint(spec) -> dict:
    """Hash every parsed row and normalized candidate, in stable order."""

    from philfacilities_ingest.sources.deped_ebeis import DepEdEBEISAdapter

    adapter = DepEdEBEISAdapter(spec)
    parsed = adapter.parse(spec)
    validation = adapter.validate(parsed)
    candidates = adapter.normalize(parsed)
    payload = {
        "parser_version": parsed.parser_version,
        "schema_version": parsed.schema_version,
        "rows": [
            {
                "key": row.source_record_key,
                "row_reference": row.row_reference,
                "raw": row.raw_payload,
                "normalized": row.normalized_payload,
            }
            for row in sorted(parsed.rows, key=lambda row: row.source_record_key)
        ],
        # `enrichment_only` is a pipeline directive, not source-derived data.
        # Excluding it keeps this fingerprint about what the EBEIS page says.
        "candidates": [
            {key: value for key, value in asdict(candidate).items() if key != "enrichment_only"}
            for candidate in sorted(candidates, key=lambda item: item.source_record_key)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return {
        "parser_version": parsed.parser_version,
        "schema_version": parsed.schema_version,
        "parsed_rows": len(parsed.rows),
        "accepted_rows": validation.accepted_rows,
        "rejected_rows": validation.rejected_rows,
        "candidates": len(candidates),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def test_preserved_ebeis_artifact_replays_to_its_golden_fingerprint() -> None:
    """A preserved real source page must replay byte-identically.

    This is the Phase 0 golden replay over preserved raw artifacts. It is a
    read-only parse/validate/normalize replay: canonical counts are covered by
    the synthetic demo replay against the database.
    """

    path, spec = _preserved_ebeis_spec()
    golden_path = GOLDEN_DIR / "preserved-ebeis-ncr.json"
    assert golden_path.exists(), f"missing golden fingerprint {golden_path}"
    golden = json.loads(golden_path.read_text())

    first = _preserved_parse_fingerprint(spec)
    second = _preserved_parse_fingerprint(spec)

    assert first == second, "preserved EBEIS replay is not deterministic"
    for field in (
        "parser_version",
        "schema_version",
        "parsed_rows",
        "accepted_rows",
        "rejected_rows",
        "candidates",
        "sha256",
    ):
        assert first[field] == golden[field], (
            f"golden fingerprint changed for {path.name}: {field} "
            f"{golden[field]!r} -> {first[field]!r}"
        )
