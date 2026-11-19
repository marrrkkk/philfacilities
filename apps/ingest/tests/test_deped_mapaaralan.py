"""Parser and normalization tests for the OSMPH MaPaaralan school points."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from philfacilities_ingest.contracts import LocationData, ReleaseSpec, SchoolData
from philfacilities_ingest.sources.deped_mapaaralan import DepEdMapaaralanAdapter
from sqlalchemy import func, select

HEADER = (
    "@id",
    "name",
    "short_name",
    "old_name",
    "date_started",
    "population:pupils:2012",
    "population:pupils:2015",
    "isced:level",
    "addr:region",
    "addr:province",
    "addr:town",
    "addr:city",
    "addr:borough",
    "addr:housenumber",
    "addr:street",
    "addr:street:corner",
    "addr:neighbourhood",
    "addr:village",
    "addr:hamlet",
    "operator",
    "latitude",
    "longitude",
    "hrslph100m",
    "priority",
)


def _spec(content: bytes) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code="deped",
        agency_name="Department of Education",
        dataset_slug="deped-mapaaralan-school-locations",
        dataset_name="DepEd MaPaaralan school locations — OSMPH 2019 release",
        release_label="DEPED-MAPAARALAN-TEST",
        filename="deped-mapaaralan-2019-osmph.tsv",
        content=content,
    )


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "@id": "134837",
        "name": "Taungoh Elementary School",
        "addr:region": "Autonomous Region in Muslim Mindanao",
        "addr:province": "Tawi-tawi",
        "addr:town": "Sibutu",
        "addr:city": "",
        "operator": "East Sibutu II District of Tawi-Tawi Schools Division",
        "latitude": "4.706311",
        "longitude": "119.492008",
        "hrslph100m": "true",
        "priority": "medium",
    }
    row.update(overrides)
    return row


def _tsv(rows: list[dict[str, str]]) -> bytes:
    lines = ["\t".join(HEADER)]
    for row in rows:
        lines.append("\t".join(row.get(column, "") for column in HEADER))
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_parse_and_normalize_is_link_only_point_enrichment() -> None:
    adapter = DepEdMapaaralanAdapter(_spec(b"unused"))
    parsed = adapter.parse(_spec(_tsv([_row()])))
    validation = adapter.validate(parsed)
    assert validation.accepted_rows == 1
    assert validation.rejected_rows == 0
    assert not validation.failed

    candidates = adapter.normalize(parsed)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_entity_id == "134837"
    assert candidate.display_name == "Taungoh Elementary School"
    assert candidate.enrichment_only is True
    assert candidate.link_only is True
    assert candidate.facility_type == "school"
    assert candidate.ownership == "unknown"
    assert candidate.ownership_type == "UNKNOWN"
    assert candidate.record_status == "unknown"
    assert candidate.location.latitude == 4.706311
    assert candidate.location.longitude == 119.492008
    assert candidate.location.precision == "map_geocoded"
    assert candidate.location.method == "deped_mapaaralan_2019_osmph"
    assert candidate.location.psgc_code is None
    assert candidate.location.address_text is None
    assert candidate.school is not None
    assert candidate.school.deped_school_id == "134837"
    assert candidate.school.sector is None
    assert candidate.school.school_management is None
    assert candidate.school.enrollment == []


def test_duplicate_id_keeps_first_point_and_rejects_second() -> None:
    rows = [
        _row(),
        _row(name="Taungoh ES duplicate", latitude="4.706400"),
        _row(**{"@id": "134836", "name": "Tandu Banak Central ES"}),
    ]
    adapter = DepEdMapaaralanAdapter(_spec(b"unused"))
    parsed = adapter.parse(_spec(_tsv(rows)))
    validation = adapter.validate(parsed)
    assert validation.accepted_rows == 2
    assert validation.rejected_rows == 1
    assert validation.rejected_row_references == {"deped-mapaaralan:134837:3"}
    summary = next(issue for issue in validation.issues if issue.code == "mapaaralan_rejections")
    assert summary.details["duplicates"] == 1
    candidates = adapter.normalize(parsed)
    kept = [
        candidate
        for candidate in candidates
        if candidate.row_reference not in validation.rejected_row_references
    ]
    assert [candidate.source_entity_id for candidate in kept] == ["134837", "134836"]


def test_invalid_rows_are_rejected_with_reasons() -> None:
    rows = [
        _row(**{"@id": "12345"}),
        _row(**{"@id": "134838", "name": ""}),
        _row(**{"@id": "134839", "latitude": "", "longitude": ""}),
        _row(**{"@id": "134840", "latitude": "0.0", "longitude": "0.0"}),
    ]
    adapter = DepEdMapaaralanAdapter(_spec(b"unused"))
    parsed = adapter.parse(_spec(_tsv(rows)))
    validation = adapter.validate(parsed)
    assert validation.accepted_rows == 0
    assert validation.rejected_rows == 4
    assert validation.failed is True
    summary = next(issue for issue in validation.issues if issue.code == "mapaaralan_rejections")
    assert summary.details["missing_points"] == 2
    assert summary.details["outside_philippines_bbox"] == 1
    assert adapter.normalize(parsed) == []


def test_missing_required_column_is_rejected() -> None:
    content = b"@id\tname\tlatitude\n134837\tTaungoh ES\t4.7\n"
    adapter = DepEdMapaaralanAdapter(_spec(b"unused"))
    try:
        adapter.parse(_spec(content))
    except ValueError as exc:
        assert "longitude" in str(exc)
    else:
        raise AssertionError("a table without a longitude column must not parse")


def test_empty_table_is_rejected() -> None:
    adapter = DepEdMapaaralanAdapter(_spec(b"unused"))
    try:
        adapter.parse(_spec(b"@id\tname\tlatitude\tlongitude\n"))
    except ValueError as exc:
        assert "no school rows" in str(exc)
    else:
        raise AssertionError("an empty MaPaaralan table must not parse")


def _candidate(
    entity_id: str = "134837",
    *,
    latitude: float = 4.706311,
    longitude: float = 119.492008,
):
    from philfacilities_ingest.contracts import FacilityCandidate

    return FacilityCandidate(
        source_record_key=f"{entity_id}-2",
        source_entity_id=entity_id,
        row_reference=f"deped-mapaaralan:{entity_id}:2",
        display_name="Taungoh Elementary School",
        facility_type="school",
        facility_subtype=None,
        ownership="unknown",
        ownership_type="UNKNOWN",
        operator_type="UNKNOWN",
        record_status="unknown",
        location=LocationData(
            latitude=latitude,
            longitude=longitude,
            precision="map_geocoded",
            method="deped_mapaaralan_2019_osmph",
            review_status="source_supplied",
        ),
        school=SchoolData(deped_school_id=entity_id),
        enrichment_only=True,
        link_only=True,
    )


def _source_rows(session, suffix: str):
    from philfacilities_api.models import (
        Agency,
        Dataset,
        PublicationGate,
        Release,
        SourceRecord,
    )

    agency = Agency(name=f"DepEd test {suffix}", short_code=f"deped-{suffix}")
    session.add(agency)
    session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=f"deped-mapaaralan-{suffix}",
        name="DepEd MaPaaralan test",
        publication_status="public",
        redistribution_status="publicly_available_verified",
        authority_level="community",
    )
    session.add(dataset)
    session.flush()
    gate = PublicationGate(dataset_id=dataset.id, status="approved")
    session.add(gate)
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"MAP-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="processing",
        publication_status="public",
        terms_review_status="approved_with_attribution",
    )
    session.add(release)
    session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key="134837-2",
        raw_payload={"@id": "134837", "name": "Taungoh Elementary School"},
        raw_record_hash=uuid.uuid4().hex * 2,
        validation_status="valid",
    )
    session.add(record)
    session.flush()
    return agency, dataset, gate, release, record


@pytest.mark.integration
def test_unmatched_link_only_row_never_creates_a_facility(db_session) -> None:
    from philfacilities_api.models import Facility, QualityIssue
    from philfacilities_ingest.pipeline.canonical import _apply_candidate
    from philfacilities_ingest.pipeline.stats import IngestStats

    suffix = uuid.uuid4().hex[:10]
    agency, dataset, gate, release, record = _source_rows(db_session, suffix)
    before = db_session.scalar(select(func.count()).select_from(Facility))
    stats = IngestStats()
    result = _apply_candidate(
        db_session,
        candidate=_candidate("999999"),
        release=release,
        record=record,
        agency=agency,
        dataset=dataset,
        gate=gate,
        parser_version="deped-mapaaralan-1.0.0",
        stats=stats,
    )
    db_session.flush()
    assert result is None
    assert db_session.scalar(select(func.count()).select_from(Facility)) == before
    assert stats["unresolved"] == 1
    issue = db_session.scalars(
        select(QualityIssue).where(
            QualityIssue.source_record_id == record.id,
            QualityIssue.issue_code == "unmatched_link_only_row",
        )
    ).one()
    assert issue.details["source_entity_id"] == "999999"


@pytest.mark.integration
def test_coordinate_only_link_fills_missing_point_and_keeps_address(db_session) -> None:
    from philfacilities_api.models import (
        Dataset,
        Facility,
        FacilityLocation,
        FacilitySourceLink,
        Release,
        SchoolProfile,
        SourceRecord,
    )
    from philfacilities_ingest.pipeline.canonical import _apply_candidate
    from philfacilities_ingest.pipeline.stats import IngestStats

    suffix = uuid.uuid4().hex[:10]
    agency, dataset, gate, release, record = _source_rows(db_session, suffix)
    existing_dataset = Dataset(
        agency_id=agency.id,
        slug=f"deped-ebeis-{suffix}",
        name="DepEd EBEIS test",
        publication_status="public",
        redistribution_status="publicly_available_verified",
        authority_level="official",
    )
    db_session.add(existing_dataset)
    db_session.flush()
    existing_release = Release(
        dataset_id=existing_dataset.id,
        source_release_label=f"EBEIS-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="public",
        terms_review_status="approved_with_attribution",
    )
    db_session.add(existing_release)
    db_session.flush()
    existing_record = SourceRecord(
        release_id=existing_release.id,
        source_record_key="134837",
        raw_payload={"School ID": "134837"},
        raw_record_hash=uuid.uuid4().hex * 2,
        validation_status="valid",
    )
    db_session.add(existing_record)
    db_session.flush()
    facility = Facility(
        slug=f"taungoh-{suffix}",
        display_name="Taungoh ES",
        official_name="Taungoh ES",
        facility_type="school",
        ownership="unknown",
        record_status="active_in_registry",
        publication_status="public",
        is_synthetic=False,
    )
    db_session.add(facility)
    db_session.flush()
    db_session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=existing_record.id,
            source_entity_id="134837",
            match_method="new_canonical_record",
            match_status="automatic_high_confidence",
            match_confidence=1,
        )
    )
    db_session.add(
        SchoolProfile(
            facility_id=facility.id,
            deped_school_id="134837",
            source_record_id=existing_record.id,
        )
    )
    db_session.add(
        FacilityLocation(
            facility_id=facility.id,
            address_text="Brgy. Tandu Banak, Sibutu, Tawi-Tawi",
            precision="unknown",
            review_status="source_supplied",
            is_current=True,
        )
    )
    db_session.flush()

    stats = IngestStats()
    result = _apply_candidate(
        db_session,
        candidate=_candidate(),
        release=release,
        record=record,
        agency=agency,
        dataset=dataset,
        gate=gate,
        parser_version="deped-mapaaralan-1.0.0",
        stats=stats,
    )
    db_session.flush()
    assert result is not None
    assert result.id == facility.id
    assert stats["with_coordinates"] == 1

    current = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(True),
        )
    ).one()
    assert float(current.latitude) == pytest.approx(4.706311)
    assert float(current.longitude) == pytest.approx(119.492008)
    assert current.precision == "map_geocoded"
    assert current.method == "deped_mapaaralan_2019_osmph"
    assert current.address_text == "Brgy. Tandu Banak, Sibutu, Tawi-Tawi"
    assert current.source_record_id == record.id

    history = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(False),
        )
    ).all()
    assert len(history) == 1
    assert history[0].address_text == "Brgy. Tandu Banak, Sibutu, Tawi-Tawi"
