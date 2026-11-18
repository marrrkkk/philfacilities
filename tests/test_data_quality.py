"""Data-integrity checks over the seeded canonical database."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

pytestmark = [pytest.mark.integration, pytest.mark.data_quality]


def test_every_published_facility_has_provenance_and_one_current_location(db_session):
    from philfacilities_api.models import (
        Dataset,
        Facility,
        FacilityLocation,
        FacilitySourceLink,
        Release,
        SourceRecord,
    )

    facilities = db_session.scalars(select(Facility)).all()
    assert len(facilities) == 22
    assert all(facility.publication_status == "public" for facility in facilities)
    assert all(facility.is_synthetic for facility in facilities)

    for facility in facilities:
        links = db_session.scalars(
            select(FacilitySourceLink).where(FacilitySourceLink.facility_id == facility.id)
        ).all()
        assert links, f"{facility.slug} has no source evidence"
        assert all(link.match_status == "automatic_high_confidence" for link in links)
        assert all(float(link.match_confidence) == 1.0 for link in links)
        assert all(link.source_entity_id for link in links)

        locations = db_session.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id == facility.id,
                FacilityLocation.is_current.is_(True),
            )
        ).all()
        # A facility may legitimately have no location yet; missing is not a fabricated point.
        assert len(locations) <= 1
        for location in locations:
            if location.latitude is None or location.longitude is None:
                assert location.geom is None

    orphan_records = db_session.scalar(
        select(func.count())
        .select_from(SourceRecord)
        .outerjoin(Release, SourceRecord.release_id == Release.id)
        .where(Release.id.is_(None))
    )
    assert orphan_records == 0

    non_synthetic_links = db_session.scalar(
        select(func.count())
        .select_from(FacilitySourceLink)
        .join(SourceRecord, FacilitySourceLink.source_record_id == SourceRecord.id)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(Dataset.is_synthetic.is_(False))
    )
    assert non_synthetic_links == 0


def test_every_change_event_carries_source_evidence(db_session):
    from philfacilities_api.models import FacilityChangeEvent

    events = db_session.scalars(select(FacilityChangeEvent)).all()
    assert events
    assert all(event.source_record_id is not None for event in events)


def test_only_one_current_location_per_facility_is_enforced(db_session):
    from philfacilities_api.models import FacilityLocation
    from sqlalchemy.exc import IntegrityError

    existing = db_session.scalars(
        select(FacilityLocation).where(FacilityLocation.is_current.is_(True))
    ).first()
    assert existing is not None

    duplicate = FacilityLocation(
        facility_id=existing.facility_id,
        precision="unknown",
        method="test_duplicate",
        review_status="source_supplied",
        is_current=True,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_release_checksums_match_deterministic_fixture_bytes(db_session):
    from philfacilities_api.models import Dataset, GeographicRelease, Release
    from philfacilities_ingest.cli import demo_specs

    specs = {spec.dataset_slug: spec for _name, spec, _adapter in demo_specs()}
    releases = db_session.scalars(select(Release)).all()
    assert len(releases) == 5
    for release in releases:
        dataset = db_session.get(Dataset, release.dataset_id)
        spec = specs[dataset.slug]
        expected = hashlib.sha256(spec.content).hexdigest()
        assert release.sha256 == expected
        assert release.row_count_parsed is not None and release.row_count_parsed > 0
        assert release.parser_version
        assert release.raw_object_uri
        assert release.terms_review_status == "synthetic_demo"

    geo = db_session.scalars(select(GeographicRelease)).one()
    expected_geo = hashlib.sha256(specs["demo-psgc"].content).hexdigest()
    assert geo.sha256 == expected_geo
    assert geo.release_label == "SYNTHETIC-DEMO-2026-Q3"


def test_missing_values_remain_unknown_not_zero(db_session):
    from philfacilities_api.models import Facility, FacilityLocation, HealthProfile

    facilities = db_session.scalars(select(Facility)).all()
    current_locations = {
        location.facility_id: location
        for location in db_session.scalars(
            select(FacilityLocation).where(FacilityLocation.is_current.is_(True))
        ).all()
    }
    facilities_without_point = [
        facility
        for facility in facilities
        if facility.id not in current_locations
        or current_locations[facility.id].latitude is None
        or current_locations[facility.id].longitude is None
    ]
    # Seven facilities have no source point. Under data.md §9.1 their PSGC/address
    # evidence is still persisted as a location row with a null geometry rather
    # than discarded, so absence of a point is measured on coordinates.
    assert len(facilities_without_point) == 7
    for facility in facilities_without_point:
        location = current_locations[facility.id]
        assert location.geom is None
        assert location.psgc_code or location.address_text or location.postal_code

    # An absent location is not represented as the valid Gulf of Guinea point (0, 0).
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(FacilityLocation)
            .where(FacilityLocation.latitude == 0, FacilityLocation.longitude == 0)
        )
        == 0
    )

    unknown_precision = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.precision == "unknown",
            FacilityLocation.latitude.is_not(None),
            FacilityLocation.longitude.is_not(None),
        )
    ).all()
    assert unknown_precision
    # Coordinates exist but the source never claimed a precision; keep the method and do not
    # promote them to a precise pin.
    assert all(location.method for location in unknown_precision)
    assert all(location.precision == "unknown" for location in unknown_precision)

    address_only = db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.is_current.is_(True),
            FacilityLocation.latitude.is_(None),
            FacilityLocation.longitude.is_(None),
        )
    ).all()
    # Address/PSGC-only claims are retained without inventing a coordinate or method.
    assert address_only
    assert all(location.geom is None for location in address_only)
    assert all(
        location.psgc_code or location.address_text or location.postal_code
        for location in address_only
    )

    # The synthetic demo supplies a detail type but no licensing status. A
    # missing licence is retained as null, never fabricated as "Without License".
    profiles = db_session.scalars(select(HealthProfile)).all()
    assert profiles
    with_doh_id = [profile for profile in profiles if profile.doh_facility_id]
    assert with_doh_id
    assert all(profile.facility_type_detail for profile in with_doh_id)
    assert all(profile.licensing_status is None for profile in profiles)


def test_quality_issues_are_explainable_and_reference_a_release(db_session):
    from philfacilities_api.models import QualityIssue

    issues = db_session.scalars(select(QualityIssue)).all()
    assert issues
    assert all(issue.issue_code for issue in issues)
    assert all(issue.message for issue in issues)
    assert all(issue.release_id for issue in issues)
    assert all(issue.severity in {"info", "warning", "error"} for issue in issues)
    assert all(issue.status == "open" for issue in issues)


def test_dataset_registry_records_rights_and_publication_gate(db_session):
    from philfacilities_api.models import Dataset, PublicationGate

    datasets = db_session.scalars(select(Dataset).order_by(Dataset.slug)).all()
    assert len(datasets) == 6
    for dataset in datasets:
        assert dataset.is_synthetic is True
        assert dataset.redistribution_status == "not_applicable"
        assert dataset.terms_url is None
        assert "Synthetic" in (dataset.license_identifier or "")
        gate = db_session.scalars(
            select(PublicationGate).where(PublicationGate.dataset_id == dataset.id)
        ).one()
        assert gate.status == "synthetic_demo"
        assert gate.reviewer == "automated-policy"
        assert gate.reviewed_at is not None
