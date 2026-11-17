"""Backfill source-linked field claims without re-acquiring source files.

The ingestion pipeline writes an assertion for every field a source row
supplies. Older releases were ingested before that behaviour existed, but their
child rows already retain the exact ``source_record_id`` that supplied each
value. This module reconstructs only those exact claims: locations, functions,
services, roles, and school/health profile fields. It deliberately does not
guess which source supplied a facility-level field when several sources could
have done so.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from philfacilities_api.models import (
    AttributeAssertion,
    FacilityFunction,
    FacilityLocation,
    FacilityRole,
    FacilityService,
    HealthProfile,
    SchoolProfile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

BACKFILL_VERSION = "assertion-backfill-v1"

LOCATION_ATTRIBUTES = (
    "location.latitude",
    "location.longitude",
    "location.precision",
    "location.method",
    "location.address_text",
    "psgc_code",
)
FUNCTION_ATTRIBUTES = ("function_code",)
SERVICE_ATTRIBUTES = ("service_code",)
ROLE_ATTRIBUTES = ("role_type", "role_entity_name")
SCHOOL_ATTRIBUTES = (
    "school.sector",
    "school.school_management",
    "school.annex_status",
    "school.offers_es",
    "school.offers_jhs",
    "school.offers_shs",
    "deped_school_id",
)
HEALTH_ATTRIBUTES = (
    "health.facility_category",
    "health.service_capability_level",
    "health.bed_capacity",
    "doh_facility_id",
)
ALL_ATTRIBUTES = (
    *LOCATION_ATTRIBUTES,
    *FUNCTION_ATTRIBUTES,
    *SERVICE_ATTRIBUTES,
    *ROLE_ATTRIBUTES,
    *SCHOOL_ATTRIBUTES,
    *HEALTH_ATTRIBUTES,
)


@dataclass
class AssertionBackfillStats:
    examined: int = 0
    created: int = 0
    skipped_existing: int = 0
    by_attribute: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "created": self.created,
            "skipped_existing": self.skipped_existing,
            "by_attribute": dict(sorted(self.by_attribute.items())),
            "version": BACKFILL_VERSION,
        }


def _value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text.strip() or text.strip().lower() == "unknown":
        return None
    return text


def _existing_claim_keys(session: Session) -> set[tuple[uuid.UUID, uuid.UUID, str, str]]:
    rows = session.execute(
        select(
            AttributeAssertion.facility_id,
            AttributeAssertion.source_record_id,
            AttributeAssertion.attribute_name,
            AttributeAssertion.normalized_value,
        ).where(AttributeAssertion.attribute_name.in_(ALL_ATTRIBUTES))
    ).all()
    return {
        (facility_id, source_record_id, attribute, normalized_value or "")
        for facility_id, source_record_id, attribute, normalized_value in rows
    }


def _add(
    session: Session,
    stats: AssertionBackfillStats,
    existing: set[tuple[uuid.UUID, uuid.UUID, str, str]],
    *,
    facility_id: uuid.UUID,
    source_record_id: uuid.UUID,
    attribute: str,
    raw_value: Any,
    normalized_value: Any,
    source_field: str | None = None,
    review_status: str = "source_supplied",
) -> None:
    normalized = _value(normalized_value)
    if normalized is None:
        return
    stats.examined += 1
    key = (facility_id, source_record_id, attribute, normalized)
    if key in existing:
        stats.skipped_existing += 1
        return
    existing.add(key)
    session.add(
        AttributeAssertion(
            facility_id=facility_id,
            source_record_id=source_record_id,
            attribute_name=attribute,
            source_field=source_field or attribute,
            raw_value=None if raw_value is None else str(raw_value),
            normalized_value=normalized,
            transformation_version=BACKFILL_VERSION,
            review_status=review_status,
        )
    )
    stats.created += 1
    stats.by_attribute[attribute] += 1


def backfill_assertions(session: Session) -> AssertionBackfillStats:
    """Insert exact source-linked claims already represented by child rows.

    The operation is idempotent for the attributes it manages: an identical
    facility/source-record/attribute/value claim is not inserted twice.
    """

    stats = AssertionBackfillStats()
    existing = _existing_claim_keys(session)

    for row in session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.is_current.is_(True),
            FacilityLocation.source_record_id.is_not(None),
        )
    ):
        assert row.source_record_id is not None
        values = (
            ("location.latitude", row.latitude, row.latitude),
            ("location.longitude", row.longitude, row.longitude),
            ("location.precision", row.precision, row.precision),
            ("location.method", row.method, row.method),
            ("location.address_text", row.address_text, row.address_text),
            ("psgc_code", row.psgc_code, row.psgc_code),
        )
        for attribute, raw_value, normalized_value in values:
            _add(
                session,
                stats,
                existing,
                facility_id=row.facility_id,
                source_record_id=row.source_record_id,
                attribute=attribute,
                raw_value=raw_value,
                normalized_value=normalized_value,
            )

    for row in session.scalars(
        select(FacilityFunction).where(FacilityFunction.source_record_id.is_not(None))
    ):
        assert row.source_record_id is not None
        _add(
            session,
            stats,
            existing,
            facility_id=row.facility_id,
            source_record_id=row.source_record_id,
            attribute="function_code",
            raw_value=row.source_value or row.function_code,
            normalized_value=row.function_code,
            source_field="function_code",
        )

    for row in session.scalars(
        select(FacilityService).where(FacilityService.source_record_id.is_not(None))
    ):
        assert row.source_record_id is not None
        _add(
            session,
            stats,
            existing,
            facility_id=row.facility_id,
            source_record_id=row.source_record_id,
            attribute="service_code",
            raw_value=row.source_field or row.service_code,
            normalized_value=row.service_code,
            source_field="service_code",
        )

    for row in session.scalars(
        select(FacilityRole).where(FacilityRole.source_record_id.is_not(None))
    ):
        assert row.source_record_id is not None
        for attribute, value in (
            ("role_type", row.role_type),
            ("role_entity_name", row.entity_name),
        ):
            _add(
                session,
                stats,
                existing,
                facility_id=row.facility_id,
                source_record_id=row.source_record_id,
                attribute=attribute,
                raw_value=value,
                normalized_value=value,
                source_field=attribute,
            )

    for row in session.scalars(
        select(SchoolProfile).where(SchoolProfile.source_record_id.is_not(None))
    ):
        assert row.source_record_id is not None
        for attribute in (
            "sector",
            "school_management",
            "annex_status",
            "offers_es",
            "offers_jhs",
            "offers_shs",
            "deped_school_id",
        ):
            value = getattr(row, attribute)
            _add(
                session,
                stats,
                existing,
                facility_id=row.facility_id,
                source_record_id=row.source_record_id,
                attribute=(
                    "deped_school_id" if attribute == "deped_school_id" else f"school.{attribute}"
                ),
                raw_value=value,
                normalized_value=value,
                source_field=attribute,
            )

    for row in session.scalars(
        select(HealthProfile).where(HealthProfile.source_record_id.is_not(None))
    ):
        assert row.source_record_id is not None
        for attribute in (
            "facility_category",
            "service_capability_level",
            "bed_capacity",
            "doh_facility_id",
        ):
            value = getattr(row, attribute)
            _add(
                session,
                stats,
                existing,
                facility_id=row.facility_id,
                source_record_id=row.source_record_id,
                attribute=(
                    "doh_facility_id" if attribute == "doh_facility_id" else f"health.{attribute}"
                ),
                raw_value=value,
                normalized_value=value,
                source_field=attribute,
            )

    if stats.created:
        session.flush()
    return stats
