"""Ownership-inclusive registry semantics exposed through the public API."""

from __future__ import annotations

import pytest
from philfacilities_api.taxonomy import (
    DISCOVERY_CANDIDATE,
    GOVERNMENT_FACILITY,
    PRIVATE_PUBLIC_SERVICE_PROVIDER,
    PUBLIC_INCLUSION_CLASSES,
    derive_inclusion_class,
    ownership_type_from_legacy,
)

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
    # The demo release is the only source in the test database; it carries no
    # national-coverage claim.
    assert all(
        row["coverage_scope"] != "NATIONAL_OFFICIAL_INVENTORY" for row in source_rows.values()
    )


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
