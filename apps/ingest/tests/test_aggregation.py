"""General evidence aggregation across facility types."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from philfacilities_api.models import (
    AdministrativeUnit,
    Agency,
    Dataset,
    Facility,
    FacilityLocation,
    FacilitySourceLink,
    GeographicRelease,
    MatchCandidate,
    Release,
    SchoolProfile,
    SourceRecord,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def test_city_alias_resolves_city_segment_not_ambiguous_province() -> None:
    from philfacilities_ingest.aggregation import _AdminIndex, _city_aliases, _city_from_address

    assert _city_aliases("City of Lucena") >= {"lucena", "lucena city"}
    admin = _AdminIndex(
        city_alias_to_codes={
            "lucena": {"0431200000"},
            "lucena city": {"0431200000"},
            "quezon": {"1381300000"},
            "san pablo city": {"0403424000"},
            "san isidro": {"0203129000", "0304925000"},
        },
        city_names={"0431200000": "City of Lucena"},
        barangay_names={"0431200017": "Gulang-gulang"},
        administrative_tokens={"lucena", "quezon", "city"},
    )
    assert _city_from_address("Lucena City, Quezon", admin) == "0431200000"
    assert (
        _city_from_address("Diversion Road, Brgy. Gulang-gulang, Lucena City", admin)
        == "0431200000"
    )
    assert _city_from_address("Lucena, Quezon", admin) == "0431200000"
    assert _city_from_address("Brgy. San Isidro, San Pablo City, Laguna", admin) == "0403424000"
    assert _city_from_address("San Isidro, Laguna", admin) is None


def _geography(session) -> None:
    suffix = uuid.uuid4().hex[:10]
    release = GeographicRelease(
        release_label=f"aggregation-test-{suffix}",
        retrieved_at=datetime.now(UTC),
        is_synthetic=False,
    )
    session.add(release)
    session.flush()
    session.add_all(
        [
            AdministrativeUnit(
                release_id=release.id,
                psgc_code="0400000000",
                name="Region IV-A (CALABARZON)",
                geographic_level="region",
            ),
            AdministrativeUnit(
                release_id=release.id,
                psgc_code="0431200000",
                name="City of Lucena",
                geographic_level="municipality",
                parent_psgc_code="0400000000",
            ),
            AdministrativeUnit(
                release_id=release.id,
                psgc_code="0431200017",
                name="Gulang-gulang",
                geographic_level="barangay",
                parent_psgc_code="0431200000",
            ),
            AdministrativeUnit(
                release_id=release.id,
                psgc_code="0403425000",
                name="City of San Pedro",
                geographic_level="municipality",
                parent_psgc_code="0400000000",
            ),
            AdministrativeUnit(
                release_id=release.id,
                psgc_code="0403425024",
                name="San Antonio",
                geographic_level="barangay",
                parent_psgc_code="0403425000",
            ),
        ]
    )
    session.flush()


def _source_facility(
    session,
    *,
    name: str,
    agency_code: str,
    authority_level: str,
    facility_type: str = "school",
    subtype: str = "OTHER_SCHOOL",
    address: str,
    latitude=None,
    longitude=None,
    psgc_code=None,
    deped_school_id: str | None = None,
    dataset_slug: str | None = None,
    raw_payload: dict | None = None,
) -> tuple[Facility, MatchCandidate | None]:
    suffix = uuid.uuid4().hex[:10]
    agency = Agency(
        name=f"Aggregation test {agency_code} {suffix}", short_code=f"{agency_code}-{suffix}"
    )
    session.add(agency)
    session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug=dataset_slug or f"aggregation-test-{agency_code.lower()}-{suffix}",
        name=f"Aggregation test {agency_code}",
        publication_status="public",
        redistribution_status="publicly_available_verified",
        authority_level=authority_level,
        coverage_scope="selected_lgu",
    )
    session.add(dataset)
    session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label=f"AGG-{suffix}",
        retrieved_at=datetime.now(UTC),
        sha256=uuid.uuid4().hex * 2,
        ingestion_status="published",
        publication_status="public",
        terms_review_status="approved_with_attribution",
    )
    session.add(release)
    session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key=f"{agency_code}:{suffix}",
        raw_payload={"name": name, "address": address, **(raw_payload or {})},
        raw_record_hash=uuid.uuid4().hex * 2,
        validation_status="valid",
    )
    session.add(record)
    session.flush()
    facility = Facility(
        slug=f"aggregation-{agency_code.lower()}-{suffix}",
        display_name=name,
        official_name=name,
        facility_type=facility_type,
        facility_subtype=subtype,
        ownership="unknown",
        record_status="active_in_registry",
        publication_status="public",
        is_synthetic=False,
    )
    session.add(facility)
    session.flush()
    session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=record.id,
            source_entity_id=f"{agency_code}:{suffix}",
            match_method="new_canonical_record",
            match_status="automatic_high_confidence",
            match_confidence=1,
        )
    )
    session.add(
        FacilityLocation(
            facility_id=facility.id,
            latitude=latitude,
            longitude=longitude,
            psgc_code=psgc_code,
            precision="map_geocoded" if latitude is not None else "unknown",
            address_text=address,
            review_status="source_supplied",
            is_current=True,
        )
    )
    if deped_school_id is not None:
        session.add(
            SchoolProfile(
                facility_id=facility.id,
                deped_school_id=deped_school_id,
                source_record_id=record.id,
            )
        )
    session.flush()
    return facility, None


def _st_anne_facilities(session):
    _geography(session)
    deped, _ = _source_facility(
        session,
        name="St. Anne College Lucena, Inc.",
        agency_code="deped",
        authority_level="official",
        subtype="OTHER_SCHOOL",
        address="Diversion Road, Brgy. Gulang-gulang, Lucena City",
        deped_school_id="403263",
    )
    ched, _ = _source_facility(
        session,
        name="St. Anne College Lucena",
        agency_code="ched",
        authority_level="official",
        subtype="HIGHER_EDUCATION_INSTITUTION",
        address="Lucena City, Quezon",
        psgc_code="0400000000",
    )
    osm, _ = _source_facility(
        session,
        name="Saint Anne College Lucena",
        agency_code="osm",
        authority_level="community",
        subtype="college",
        address="Lucena",
        latitude=13.961715,
        longitude=121.612162,
        psgc_code="0431200017",
    )
    return deped, ched, osm


def test_st_anne_sources_aggregate_into_one_school_with_osm_location(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        deped, ched, osm = _st_anne_facilities(db_session)
        dry_run = consolidate_facilities(db_session, dry_run=True)
        assert dry_run["clusters_accepted"] == 1
        assert dry_run["would_merge"] == 2
        db_session.rollback()

        deped, ched, osm = _st_anne_facilities(db_session)
        stats = consolidate_facilities(db_session, dry_run=False)
        db_session.flush()

        assert stats["clusters_accepted"] == 1
        assert stats["merged"] == 2
        assert ched.record_status == "merged"
        assert osm.record_status == "merged"
        assert deped.record_status == "active_in_registry"
        assert deped.publication_status == "public"

        current = db_session.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id == deped.id,
                FacilityLocation.is_current.is_(True),
            )
        ).one()
        assert current.latitude is not None
        assert current.longitude is not None
        assert current.psgc_code == "0431200017"
        assert float(current.latitude) == pytest.approx(13.961715)
        assert float(current.longitude) == pytest.approx(121.612162)

        candidates = db_session.scalars(
            select(MatchCandidate).where(
                MatchCandidate.candidate_facility_id == deped.id,
                MatchCandidate.match_method == "facility_identity_evidence_v1",
            )
        ).all()
        assert len(candidates) == 2
        assert all(candidate.match_status == "merged" for candidate in candidates)
        assert all(
            candidate.reviewer == "system:facility-identity-evidence" for candidate in candidates
        )

        # Undoing the OSM merge moves the point back and restores the previous
        # address-only current location on the survivor.
        from philfacilities_ingest.matching import undo_match_merge

        osm_candidate = next(
            candidate for candidate in candidates if candidate.source_facility_id == osm.id
        )
        undo_match_merge(db_session, osm_candidate.id, reviewer="reviewer-1")
        db_session.flush()
        restored_current = db_session.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id == deped.id,
                FacilityLocation.is_current.is_(True),
            )
        ).one()
        assert restored_current.address_text == ("Diversion Road, Brgy. Gulang-gulang, Lucena City")
        assert restored_current.latitude is None
        assert osm.record_status == "active_in_registry"
    finally:
        db_session.rollback()


def test_health_facility_sources_merge_on_barangay_and_promote_the_point(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        doh, _ = _source_facility(
            db_session,
            name="Lucena City Health Office",
            agency_code="doh",
            authority_level="official",
            facility_type="health_facility",
            subtype="HEALTH_CENTER",
            address="Brgy. Gulang-gulang, Lucena City",
            psgc_code="0431200017",
        )
        osm, _ = _source_facility(
            db_session,
            name="Lucena City Health Office",
            agency_code="osm",
            authority_level="community",
            facility_type="health_facility",
            subtype="HEALTH_CENTER",
            address="Lucena",
            latitude=13.961715,
            longitude=121.612162,
            psgc_code="0431200017",
        )
        stats = consolidate_facilities(db_session, dry_run=False)
        db_session.flush()

        assert stats["clusters_accepted"] == 1
        assert stats["merged"] == 1
        assert doh.record_status == "active_in_registry"
        assert doh.publication_status == "public"
        assert osm.record_status == "merged"

        current = db_session.scalars(
            select(FacilityLocation).where(
                FacilityLocation.facility_id == doh.id,
                FacilityLocation.is_current.is_(True),
            )
        ).one()
        assert current.latitude is not None
        assert float(current.latitude) == pytest.approx(13.961715)
        assert current.psgc_code == "0431200017"

        candidate = db_session.scalars(
            select(MatchCandidate).where(
                MatchCandidate.candidate_facility_id == doh.id,
                MatchCandidate.match_method == "facility_identity_evidence_v1",
            )
        ).one()
        assert candidate.match_status == "merged"
        assert candidate.resolution["active"] is True
    finally:
        db_session.rollback()


def test_same_school_in_different_assigned_cities_merges_on_close_points(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        osm, _ = _source_facility(
            db_session,
            name="Camantero Elementary School",
            agency_code="osm",
            authority_level="community",
            address="Silay",
            latitude=10.730906,
            longitude=123.086718,
            psgc_code="1804528000",
        )
        deped, _ = _source_facility(
            db_session,
            name="Camantero Elementary School",
            agency_code="deped",
            authority_level="official",
            address="HDA CAMANTERO 1",
            latitude=10.730879,
            longitude=123.086797,
            psgc_code="1804526000",
            deped_school_id="117812",
        )
        stats = consolidate_facilities(db_session, dry_run=False)
        db_session.flush()

        assert stats["clusters_accepted"] == 1
        assert stats["merged"] == 1
        assert deped.record_status == "active_in_registry"
        assert osm.record_status == "merged"
    finally:
        db_session.rollback()


def test_hospital_name_with_reordered_connector_merges(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        osm, _ = _source_facility(
            db_session,
            name="Perpetual Succor Maternity Hospital",
            agency_code="osm",
            authority_level="community",
            facility_type="health_facility",
            subtype="HOSPITAL",
            address="Florentino Cayco Street",
            latitude=14.608100,
            longitude=120.992330,
            psgc_code="1380606000",
        )
        doh, _ = _source_facility(
            db_session,
            name="PERPETUAL SUCCOR HOSPITAL AND MATERNITY INC.",
            agency_code="doh",
            authority_level="official",
            facility_type="health_facility",
            subtype="HOSPITAL",
            address=(
                "BARANGAY 457, CITY OF MANILA, NCR, FIRST DISTRICT "
                "(Not a Province), NATIONAL CAPITAL REGION (NCR)"
            ),
            latitude=14.608177,
            longitude=120.992337,
            psgc_code="1380606063",
        )
        stats = consolidate_facilities(db_session, dry_run=False)
        db_session.flush()

        assert stats["clusters_accepted"] == 1
        assert stats["merged"] == 1
        assert doh.record_status == "active_in_registry"
        assert osm.record_status == "merged"
    finally:
        db_session.rollback()


def test_cross_type_co_located_match_creates_pending_not_merge(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        hospital, _ = _source_facility(
            db_session,
            name="Quezon Medical Center",
            agency_code="doh",
            authority_level="official",
            facility_type="health_facility",
            subtype="HOSPITAL",
            address="Brgy. Gulang-gulang, Lucena City",
            latitude=13.961715,
            longitude=121.612162,
            psgc_code="0431200017",
        )
        shelter, _ = _source_facility(
            db_session,
            name="Quezon Medical Center",
            agency_code="osm",
            authority_level="community",
            facility_type="social_welfare_facility",
            subtype="SHELTER",
            address="Lucena City",
            latitude=13.962057,
            longitude=121.612214,
            psgc_code="0431200017",
        )
        stats = consolidate_facilities(db_session, dry_run=False)
        db_session.flush()

        assert stats["would_merge"] == 0
        assert stats["merged"] == 0
        assert stats["clusters_accepted"] == 0
        assert stats["pending_created"] == 1
        assert hospital.record_status == "active_in_registry"
        assert shelter.record_status == "active_in_registry"

        candidate = db_session.scalars(
            select(MatchCandidate).where(
                MatchCandidate.match_method == "facility_identity_evidence_v1",
            )
        ).one()
        assert candidate.match_status == "pending"
        assert candidate.source_facility_id == shelter.id
        assert candidate.candidate_facility_id == hospital.id
        assert candidate.evidence["cross_type"] is True
        assert candidate.evidence["source_facility_type"] == "social_welfare_facility"
        assert candidate.evidence["candidate_facility_type"] == "health_facility"
    finally:
        db_session.rollback()


def test_same_name_different_branches_are_not_auto_merged(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        _source_facility(
            db_session,
            name="Mercury Drug",
            agency_code="directory",
            authority_level="unknown",
            facility_type="pharmacy",
            subtype="PHARMACY",
            address="123 Rizal Avenue, Lucena City",
            latitude=13.960000,
            longitude=121.610000,
            psgc_code="0431200017",
        )
        _source_facility(
            db_session,
            name="Mercury Drug",
            agency_code="osm",
            authority_level="community",
            facility_type="pharmacy",
            subtype="PHARMACY",
            address="456 M.L. Quezon Avenue, Lucena City",
            latitude=13.975000,
            longitude=121.625000,
            psgc_code="0431200017",
        )
        stats = consolidate_facilities(db_session, dry_run=True)
        assert stats["auto_pairs"] == 0
        assert stats["would_merge"] == 0
        assert stats["clusters_accepted"] == 0
    finally:
        db_session.rollback()


def test_city_only_name_match_without_location_bridge_is_not_merged(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        # Both rows are exact-name matches in the same city, and one is
        # official, but neither address nor coordinates distinguishes one
        # branch from another. City-level agreement alone must not merge them.
        _source_facility(
            db_session,
            name="Mercury Drug",
            agency_code="directory",
            authority_level="official",
            facility_type="pharmacy",
            subtype="PHARMACY",
            address="Lucena City",
            psgc_code="0431200000",
        )
        _source_facility(
            db_session,
            name="Mercury Drug",
            agency_code="osm",
            authority_level="community",
            facility_type="pharmacy",
            subtype="PHARMACY",
            address="Lucena City",
            psgc_code="0431200000",
        )
        stats = consolidate_facilities(db_session, dry_run=True)
        assert stats["auto_pairs"] == 1
        assert stats["clusters_rejected"] == 1
        assert stats["would_merge"] == 0
    finally:
        db_session.rollback()


def test_structured_admin_resolves_duplicate_city_names_and_city_suffix() -> None:
    from philfacilities_ingest.aggregation import (
        _AdminIndex,
        _resolve_barangay_code,
        _resolve_city_code,
    )

    admin = _AdminIndex(
        city_alias_to_codes={
            "calamba": {"0403405000", "1004204000"},
            "san isidro": {"0304925000", "0403426000"},
            "bacolod": {"1003501000", "1830200000"},
        },
        city_names={
            "0403405000": "City of Calamba",
            "1004204000": "Calamba",
            "0304925000": "San Isidro",
            "0403426000": "San Isidro",
            "1003501000": "Bacolod",
            "1830200000": "City of Bacolod",
        },
        barangay_names={"0431200017": "Gulang-gulang"},
        administrative_tokens=set(),
        city_alias_to_parent_alias_codes={
            ("san isidro", "nueva ecija"): {"0304925000"},
            ("san isidro", "laguna"): {"0403426000"},
        },
        barangay_alias_to_parent_codes={
            ("bgy no 18 san quirino poblacion", "0102812000"): {"0102812059"},
        },
    )
    assert (
        _resolve_city_code(admin, municipality="CITY OF CALAMBA", division="Calamba City")
        == "0403405000"
    )
    assert (
        _resolve_city_code(
            admin, municipality="BACOLOD CITY (Capital)", division="Negros Occidental"
        )
        == "1830200000"
    )
    assert (
        _resolve_city_code(admin, municipality="SAN ISIDRO", division="Nueva Ecija") == "0304925000"
    )
    assert _resolve_city_code(admin, municipality="SAN ISIDRO", division="Laguna") == "0403426000"
    assert _resolve_city_code(admin, municipality="SAN ISIDRO") is None
    assert (
        _resolve_barangay_code(admin, "BRY. NO. 18, SAN QUIRINO (POB.)", "0102812000")
        == "0102812059"
    )


def test_deped_structured_admin_derives_barangay_and_merges_with_osm(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        deped, _ = _source_facility(
            db_session,
            name="Tugonan Elementary School",
            agency_code="deped",
            authority_level="official",
            address="Purok 2",
            deped_school_id="123456",
            dataset_slug="deped-masterlist-sy2020-2021-detail",
            raw_payload={
                "municipality": "LUCENA CITY (Capital)",
                "division": "Lucena City",
                "region": "Region IV-A",
                "barangay": "GULANG-GULANG",
            },
        )
        _osm, _ = _source_facility(
            db_session,
            name="Tugonan Elementary School",
            agency_code="osm",
            authority_level="community",
            address="Gulang-gulang",
            latitude=13.961715,
            longitude=121.612162,
            psgc_code="0431200017",
        )
        stats = consolidate_facilities(db_session, dry_run=True)
        assert stats["clusters_accepted"] == 1
        assert stats["would_merge"] == 1
        example = stats["examples"][0]
        assert example["same_city"] is True
        assert example["same_barangay"] is True
        assert example["location_reason"] == "same_barangay"
        assert deped.record_status == "active_in_registry"
    finally:
        db_session.rollback()


def test_ambiguous_same_name_branch_cluster_stays_pending(db_session) -> None:
    from philfacilities_ingest.aggregation import consolidate_facilities

    try:
        _geography(db_session)
        # An official directory row could refer to either branch. The two OSM
        # points are too far apart to be the same place, so the complete cluster
        # test must reject the automatic merge instead of picking one.
        college, _ = _source_facility(
            db_session,
            name="St. Louis Anne Colleges",
            agency_code="ched",
            authority_level="official",
            address="San Pedro City, Laguna",
            psgc_code="0403425000",
        )
        _source_facility(
            db_session,
            name="St. Louis Anne Colleges",
            agency_code="osm",
            authority_level="community",
            address="San Pedro",
            latitude=14.355288,
            longitude=121.052537,
            psgc_code="0403425024",
        )
        _source_facility(
            db_session,
            name="St. Louis Anne Colleges",
            agency_code="osm2",
            authority_level="community",
            address="San Pedro",
            latitude=14.344069,
            longitude=121.038822,
            psgc_code="0403425024",
        )
        stats = consolidate_facilities(db_session, dry_run=True)
        assert stats["would_merge"] == 0
        assert stats["clusters_accepted"] == 0
        assert stats["clusters_rejected"] == 1
        assert college.record_status == "active_in_registry"
    finally:
        db_session.rollback()
