"""Synthetic, clearly-labelled OpenAPI examples.

These values are fabricated for documentation only. They must never resemble a
real facility identity; see the testing guide's synthetic-data rule. The examples
deliberately include nulls and empty collections so consumers see the missing-
data convention documented in the data dictionary.
"""

from __future__ import annotations

FACILITY_ID = "00000000-0000-4000-8000-000000000001"
SOURCE_RECORD_ID = "00000000-0000-4000-8000-000000000002"
UPDATED_AT = "2026-11-21T09:00:00Z"

SUMMARY_EXAMPLE = {
    "id": FACILITY_ID,
    "slug": "synthetic-example-library",
    "display_name": "Synthetic Example Library",
    "facility_type": "library",
    "facility_subtype": None,
    "facility_kind": "facility",
    "inclusion_class": "DISCOVERY_CANDIDATE",
    "ownership": "unknown",
    "ownership_type": "UNKNOWN",
    "operator_type": "UNKNOWN",
    "public_access_class": "UNKNOWN",
    "record_status": "active",
    "publication_status": "public",
    "is_synthetic": True,
    "functions": [],
    "location": {
        "latitude": 14.6,
        "longitude": 120.98,
        "precision": "map_geocoded",
        "method": None,
        "address_text": "1 Synthetic Road, Example City",
        "postal_code": None,
        "psgc_code": "9901000001",
        "review_status": "source_supplied",
    },
    "geography": {
        "psgc_code": "9901000001",
        "region_name": "Synthetic Region (demo)",
        "province_name": "Synthetic Province (demo)",
        "municipality_name": "Example City (demo)",
    },
    "source_count": 1,
    "source_refs": [
        {
            "agency_code": "SYN",
            "dataset_slug": "synthetic-example-directory",
            "source_record_id": "SYN-EXAMPLE-0001",
        }
    ],
    "updated_at": UPDATED_AT,
}

DETAIL_EXAMPLE = {
    **SUMMARY_EXAMPLE,
    "official_name": None,
    "access_conditions": None,
    "school": None,
    "health": None,
    "utility": None,
    "accreditations": [],
    "contacts": [],
    "function_details": [],
    "services": [],
    "roles": [],
    "relationships": [],
    "sources": [
        {
            "id": SOURCE_RECORD_ID,
            "agency": "Synthetic Agency (demo)",
            "agency_code": "SYN",
            "dataset": "Synthetic Example Directory (demo)",
            "dataset_slug": "synthetic-example-directory",
            "release_id": "00000000-0000-4000-8000-000000000003",
            "release_label": "SYNTHETIC-DEMO-2026-11-21",
            "source_record_id": "SYN-EXAMPLE-0001",
            "source_record_uuid": SOURCE_RECORD_ID,
            "retrieved_at": UPDATED_AT,
            "match_method": "source_key",
            "match_status": "single_source",
            "match_confidence": 1.0,
            "is_synthetic": True,
        }
    ],
    "quality": {
        "identity_status": "source_linked",
        "location_precision": "map_geocoded",
        "warnings": [
            {
                "code": "approximate_coordinate",
                "severity": "info",
                "message": "This point is geocoded, not a verified building location.",
            }
        ],
        "source_count": 1,
    },
    "created_at": UPDATED_AT,
}

COMPACT_EXAMPLE = {
    "id": FACILITY_ID,
    "name": "Synthetic Example Library",
    "slug": "synthetic-example-library",
    "display_name": "Synthetic Example Library",
    "facility_type": "library",
    "facility_subtype": None,
    "inclusion_class": "DISCOVERY_CANDIDATE",
    "ownership": "unknown",
    "location": {
        "latitude": 14.6,
        "longitude": 120.98,
        "precision": "map_geocoded",
        "address_text": "1 Synthetic Road, Example City",
        "psgc_code": "9901000001",
    },
    "geography": {
        "psgc_code": "9901000001",
        "region_name": "Synthetic Region (demo)",
        "province_name": "Synthetic Province (demo)",
        "municipality_name": "Example City (demo)",
    },
    "source_refs": SUMMARY_EXAMPLE["source_refs"],
    "updated_at": UPDATED_AT,
}

MAP_POINT_EXAMPLE = {
    "id": FACILITY_ID,
    "slug": "synthetic-example-library",
    "name": "Synthetic Example Library",
    "facility_type": "library",
    "inclusion_class": "DISCOVERY_CANDIDATE",
    "precision": "map_geocoded",
    "latitude": 14.6,
    "longitude": 120.98,
}

FIELD_COVERAGE_EXAMPLE = {
    "as_of": UPDATED_AT,
    "version": "1.3",
    "fields": [
        {
            "field": "relationships[]",
            "scope": "detail",
            "populated": 0,
            "total": 229274,
            "fill_ratio": 0.0,
            "semantics": "[] means no publication-cleared rows exist for this collection.",
        },
        {
            "field": "location.postal_code",
            "scope": "summary",
            "populated": 27924,
            "total": 227911,
            "fill_ratio": 0.1225,
            "semantics": "null means no value supplied or established.",
        },
    ],
    "caveats": ["Counts are derived from public facilities using the API publication gate."],
}

ERROR_EXAMPLES = {
    "400": {
        "code": "invalid_bbox",
        "message": "bbox must be min_lon,min_lat,max_lon,max_lat.",
        "details": None,
        "request_id": "synthetic-request-id",
    },
    "404": {
        "code": "facility_not_found",
        "message": "No published facility exists with that ID.",
        "details": None,
        "request_id": "synthetic-request-id",
    },
    "422": {
        "code": "validation_error",
        "message": "One or more query parameters are invalid.",
        "details": [],
        "request_id": "synthetic-request-id",
    },
    "429": {
        "code": "rate_limit_exceeded",
        "message": "Too many requests. Retry after the current window.",
        "details": {"limit": 120, "window_seconds": 60},
        "request_id": "synthetic-request-id",
    },
    "500": {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
        "details": None,
        "request_id": "synthetic-request-id",
    },
}

SCHEMA_EXAMPLES = {
    "FacilitySummary": [SUMMARY_EXAMPLE],
    "FacilityDetail": [DETAIL_EXAMPLE],
    "FacilityCompact": [COMPACT_EXAMPLE],
    "FacilityMapPoint": [MAP_POINT_EXAMPLE],
    "FieldCoverageResponse": [FIELD_COVERAGE_EXAMPLE],
    "ErrorBody": list(ERROR_EXAMPLES.values()),
}
