"""Assertion backfill reconstructs only exact source-linked child claims."""

from __future__ import annotations

from decimal import Decimal

import pytest
from philfacilities_api.models import (
    AttributeAssertion,
    Facility,
    FacilityLocation,
    SourceRecord,
)
from philfacilities_ingest.assertions import BACKFILL_VERSION, backfill_assertions
from sqlalchemy import select

pytestmark = pytest.mark.integration


def test_backfill_assertions_reconstructs_source_linked_location_claims(db_session) -> None:
    record = db_session.scalars(select(SourceRecord).limit(1)).one()
    facility = db_session.scalars(select(Facility).limit(1)).one()
    # The test database enforces one current location per facility. Retire the
    # existing row inside this transaction; the rollback restores it.
    for current in db_session.scalars(
        select(FacilityLocation).where(
            FacilityLocation.facility_id == facility.id,
            FacilityLocation.is_current.is_(True),
        )
    ).all():
        current.is_current = False
    db_session.flush()
    location = FacilityLocation(
        facility_id=facility.id,
        source_record_id=record.id,
        latitude=Decimal("14.599512"),
        longitude=Decimal("120.984222"),
        precision="source_gps",
        method="assertion-backfill-test",
        address_text="Synthetic backfill test address",
        is_current=True,
    )
    db_session.add(location)
    db_session.flush()

    try:
        stats = backfill_assertions(db_session)
        db_session.flush()
        claims = db_session.scalars(
            select(AttributeAssertion).where(
                AttributeAssertion.facility_id == facility.id,
                AttributeAssertion.source_record_id == record.id,
                AttributeAssertion.transformation_version == BACKFILL_VERSION,
            )
        ).all()
        attributes = {claim.attribute_name for claim in claims}
        assert {
            "location.latitude",
            "location.longitude",
            "location.method",
            "location.address_text",
        } <= attributes
        assert stats.created >= 4
        assert stats.by_attribute["location.latitude"] >= 1
    finally:
        db_session.rollback()
