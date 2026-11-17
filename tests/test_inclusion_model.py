"""Ownership-inclusive registry semantics exposed through the public API."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from philfacilities_api.taxonomy import (
    DISCOVERY_CANDIDATE,
    GOVERNMENT_FACILITY,
    PRIVATE_PUBLIC_SERVICE_PROVIDER,
    PUBLIC_INCLUSION_CLASSES,
    derive_inclusion_class,
    ownership_type_from_legacy,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _items(client, path: str, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_unknown_ownership_is_never_guessed_as_government() -> None:
    assert derive_inclusion_class("government") == GOVERNMENT_FACILITY
    assert derive_inclusion_class("private") == PRIVATE_PUBLIC_SERVICE_PROVIDER
    assert derive_inclusion_class("unknown") == DISCOVERY_CANDIDATE
    assert derive_inclusion_class(None) == DISCOVERY_CANDIDATE
    assert ownership_type_from_legacy("government") == "GOVERNMENT_UNSPECIFIED"
    assert ownership_type_from_legacy("private") == "PRIVATE_UNSPECIFIED"
    assert ownership_type_from_legacy(None) == "UNKNOWN"


def test_statistics_report_inclusion_classes_separately(client):
    stats = _items(client, "/v1/statistics")
    assert set(stats["by_inclusion_class"]) <= set(PUBLIC_INCLUSION_CLASSES)
    assert sum(stats["by_inclusion_class"].values()) == stats["published_facilities"]
    assert sum(stats["by_ownership_type"].values()) == stats["published_facilities"]
    assert sum(stats["by_category"].values()) == stats["published_facilities"]

    # A private provider must never be counted as a government facility.
    assert stats["by_inclusion_class"].get(PRIVATE_PUBLIC_SERVICE_PROVIDER, 0) > 0
    private = _items(
        client, "/v1/facilities", inclusion_class=PRIVATE_PUBLIC_SERVICE_PROVIDER, limit=100
    )
    assert private["total"] == stats["by_inclusion_class"][PRIVATE_PUBLIC_SERVICE_PROVIDER]
    assert all(
        item["inclusion_class"] == PRIVATE_PUBLIC_SERVICE_PROVIDER for item in private["items"]
    )
    assert all(item["ownership"] == "private" for item in private["items"])


def test_inclusion_and_access_filters_are_consistent(client):
    government = _items(client, "/v1/facilities", inclusion_class=GOVERNMENT_FACILITY, limit=100)
    assert government["total"] > 0
    assert {item["inclusion_class"] for item in government["items"]} == {GOVERNMENT_FACILITY}

    venues = _items(client, "/v1/facilities", inclusion_class="PUBLIC_ACCESS_VENUE", limit=100)
    assert venues["total"] == 0

    private_typed = _items(
        client, "/v1/facilities", ownership_type="PRIVATE_UNSPECIFIED", limit=100
    )
    assert private_typed["total"] > 0
    assert {item["ownership_type"] for item in private_typed["items"]} == {"PRIVATE_UNSPECIFIED"}

    health = _items(client, "/v1/health-facilities", facility_kind="facility", limit=100)
    assert health["total"] > 0
    assert {item["facility_kind"] for item in health["items"]} == {"facility"}

    free = _items(client, "/v1/facilities", public_access_class="PUBLIC_FREE", limit=100)
    assert free["total"] == 0


def test_facility_detail_exposes_functions_and_new_fields(client):
    item = _items(client, "/v1/facilities", limit=1)["items"][0]
    detail = _items(client, f"/v1/facilities/{item['id']}")
    assert detail["inclusion_class"] == item["inclusion_class"]
    assert detail["ownership_type"] == item["ownership_type"]
    assert detail["facility_kind"] == item["facility_kind"]
    assert "public_access_class" in detail
    assert isinstance(detail["functions"], list)
    assert isinstance(detail["services"], list)
    assert isinstance(detail["roles"], list)
    assert isinstance(detail["relationships"], list)


def test_coverage_reports_source_scope_and_class_counts(client):
    coverage = _items(client, "/v1/coverage")
    assert coverage["registry_records"] >= coverage["published_records"]

    class_rows = {row["key"]: row for row in coverage["by_inclusion_class"]}
    assert set(class_rows) <= set(PUBLIC_INCLUSION_CLASSES)
    published = coverage["published_records"]
    assert sum(row["facility_count"] for row in class_rows.values()) == published

    stats = _items(client, "/v1/statistics")
    assert (
        sum(row["with_coordinates"] for row in coverage["by_inclusion_class"])
        == stats["with_coordinates"]
    )

    lgu_rows = coverage["by_lgu_coverage"]
    assert lgu_rows
    assert {row["state"] for row in lgu_rows} <= {
        "NATIONAL",
        "REGIONAL",
        "PARTICIPATING_LGUS",
        "SELECTED_LGUS",
        "UNKNOWN",
    }
    assert sum(row["source_count"] for row in lgu_rows) == len(coverage["source_coverage"])
    assert all(row["label"] for row in lgu_rows)

    source_rows = {row["dataset_slug"]: row for row in coverage["source_coverage"]}
    assert source_rows
    for row in source_rows.values():
        assert row["coverage_scope"]
        assert row["publication_status"] in {
            "published",
            "approved",
            "internal_only",
            "blocked",
            "review_required",
            "quarantined",
            "synthetic_demo",
        }
        assert row["rights_status"]
        assert row["freshness_days"] is None or row["freshness_days"] >= 0
        assert row["is_stale"] is None or isinstance(row["is_stale"], bool)
    # The demo release is the only source in the test database; it carries no
    # national-coverage claim.
    assert all(
        row["coverage_scope"] != "NATIONAL_OFFICIAL_INVENTORY" for row in source_rows.values()
    )


def test_coverage_reports_subtype_and_freshness_metrics(client):
    coverage = _items(client, "/v1/coverage")
    published = coverage["published_records"]
    subtype_rows = coverage["by_subtype"]
    assert subtype_rows
    assert sum(row["facility_count"] for row in subtype_rows) == published
    assert sum(row["with_coordinates"] for row in subtype_rows) <= published
    assert coverage["coverage_stale_after_days"] > 0
    assert coverage["stale_source_count"] == sum(
        1 for row in coverage["source_coverage"] if row["is_stale"] is True
    )
    for row in subtype_rows:
        assert row["category"]
        assert row["subtype"]
        assert row["with_coordinates"] <= row["facility_count"]


def test_facility_assertions_expose_field_level_provenance(client):
    items = _items(client, "/v1/facilities", limit=50)["items"]
    selected = None
    claims = []
    for item in items:
        candidate_claims = _items(client, f"/v1/facilities/{item['id']}/assertions")
        if candidate_claims:
            selected = item
            claims = candidate_claims
            break
    assert selected is not None, "No published facility exposes field-level assertions."
    assert claims
    assert any(claim["attribute"] == "display_name" for claim in claims)
    for claim in claims:
        assert claim["attribute"]
        assert claim["source"]["release_label"]
        assert claim["source"]["source_record_id"]
        assert claim["source"]["rights_status"]
        assert claim["source"]["publication_status"] in {"approved", "published"}

    filtered = _items(
        client,
        f"/v1/facilities/{selected['id']}/assertions",
        attribute="display_name",
    )
    assert filtered
    assert {claim["attribute"] for claim in filtered} == {"display_name"}


def test_internal_source_assertions_never_leak_through_a_public_facility(db_session):
    from philfacilities_api.models import (
        Agency,
        AttributeAssertion,
        Dataset,
        Facility,
        FacilitySourceLink,
        Release,
        SourceRecord,
    )
    from philfacilities_api.services import load_attribute_assertions

    facility = db_session.scalars(
        select(Facility).where(Facility.publication_status == "public").limit(1)
    ).one()
    agency = Agency(name="Internal assertion test agency", short_code="internal-assert-test")
    db_session.add(agency)
    db_session.flush()
    dataset = Dataset(
        agency_id=agency.id,
        slug="internal-assert-test",
        name="Internal assertion test dataset",
        redistribution_status="review_required",
        publication_status="internal_only",
        is_public_source=False,
    )
    db_session.add(dataset)
    db_session.flush()
    release = Release(
        dataset_id=dataset.id,
        source_release_label="INTERNAL-ASSERT-TEST",
        retrieved_at=datetime.now(UTC),
        sha256="1" * 64,
        file_format="json",
        file_size_bytes=2,
        ingestion_status="published",
        terms_review_status="review_required",
        publication_status="blocked",
        parser_version="test",
    )
    db_session.add(release)
    db_session.flush()
    record = SourceRecord(
        release_id=release.id,
        source_record_key="internal-assert-record",
        row_number_or_page="1",
        raw_payload={"secret_claim": "do-not-publish"},
        raw_record_hash="0" * 64,
        validation_status="valid",
    )
    db_session.add(record)
    db_session.flush()
    db_session.add(
        FacilitySourceLink(
            facility_id=facility.id,
            source_record_id=record.id,
            source_entity_id="internal-assert-record",
            match_method="test",
            match_confidence=1,
            match_status="automatic_high_confidence",
            evidence={},
        )
    )
    db_session.add(
        AttributeAssertion(
            facility_id=facility.id,
            source_record_id=record.id,
            attribute_name="secret_claim",
            source_field="secret_claim",
            raw_value="do-not-publish",
            normalized_value="do-not-publish",
            transformation_version="test",
        )
    )
    try:
        db_session.flush()
        visible = load_attribute_assertions(db_session, facility.id, limit=1000)
        assert all(claim.attribute != "secret_claim" for claim in visible)
    finally:
        db_session.rollback()


def test_map_query_applies_inclusion_class_filter(client):
    mapped = _items(client, "/v1/facilities", has_coordinates="true", limit=1)["items"]
    assert mapped
    latitude = mapped[0]["location"]["latitude"]
    longitude = mapped[0]["location"]["longitude"]
    bbox = f"{longitude - 0.05},{latitude - 0.05},{longitude + 0.05},{latitude + 0.05}"

    response = client.get(
        "/v1/facilities/within",
        params={
            "bbox": bbox,
            "inclusion_class": PRIVATE_PUBLIC_SERVICE_PROVIDER,
            "limit": 500,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"]
    assert {item["inclusion_class"] for item in payload["items"]} == {
        PRIVATE_PUBLIC_SERVICE_PROVIDER
    }
