"""Declarative field-coverage definitions shared by the API and the DX audit.

This module is the single place that maps a public schema path to the canonical
tables behind it. The endpoint ``GET /v1/fields`` and ``scripts/api_dx_audit.py``
both derive their counts from these definitions, so they cannot drift apart.
It is an implementation detail, not a second public vocabulary: taxonomy codes
still come from ``taxonomy.py`` and ``/v1/taxonomy``.

Counts are set-based. Scalar fields share one grouped scan, and every child
collection shares one query whose CTE materialises the publication-cleared
source-record set once. A correlated gate per child row measured ~48 s on
229k facilities; this form avoids it without a materialized view.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, func, literal, or_, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ..models import (
    Dataset,
    Facility,
    FacilityContact,
    FacilityFunction,
    FacilityLocation,
    FacilityRelationship,
    FacilityRole,
    FacilityService,
    FacilitySourceLink,
    HealthAccreditation,
    HealthProfile,
    Release,
    ResourceObservation,
    SchoolProfile,
    SourceRecord,
    UtilityProfile,
)
from ..publication import public_dataset_release_condition
from .filters import public_facility_index_filter
from .search import utcnow

CoverageScope = str
ChildRowsFactory = Callable[[Any], Select]

# The null-vs-empty rule documented in the data dictionary and surfaced on every
# FieldCoverageEntry. It is deliberately explicit so a client cannot mistake an
# empty, publication-cleared collection for "the facility has none".
NULL_SEMANTICS = "null means no value supplied or established; it is not zero, false, or closed"
COLLECTION_SEMANTICS = (
    "[] means no publication-cleared rows exist for this collection; "
    "it does not assert that the facility has none"
)
PRECISION_SEMANTICS = (
    "coordinate precision is kept with every point; centroids are not building pins"
)


def _public_gate() -> list[ColumnElement[bool]]:
    return list(public_facility_index_filter())


def _filled(column: Any, *, unknown: str | None = None) -> Callable[[], ColumnElement[bool]]:
    def build() -> ColumnElement[bool]:
        conditions = [column.is_not(None)]
        if unknown is not None:
            conditions.append(column != unknown)
        conditions.append(column != "")
        result = conditions[0]
        for condition in conditions[1:]:
            result = result & condition
        return result

    return build


def _public_source_ids() -> Select:
    """Ids of source records cleared by the shared publication gate."""

    return (
        select(SourceRecord.id.label("id"))
        .select_from(SourceRecord)
        .join(Release, SourceRecord.release_id == Release.id)
        .join(Dataset, Release.dataset_id == Dataset.id)
        .where(public_dataset_release_condition())
    )


def _gated_child_rows(model: Any, records: Any, *conditions: ColumnElement[bool]) -> Select:
    """Facility ids with a publication-cleared child row.

    A hash join against the one shared source-record set is far cheaper than a
    correlated publication gate per child row. A NULL source record is a legacy
    canonical value and stays visible, matching ``public_source_record_condition``.
    """

    record_id = model.source_record_id
    return (
        select(model.facility_id.label("facility_id"))
        .select_from(model)
        .outerjoin(records, records.c.id == record_id)
        .where(
            or_(record_id.is_(None), records.c.id.is_not(None)),
            *conditions,
        )
        .distinct()
    )


def _child_ids(model: Any, *conditions: ColumnElement[bool]) -> ChildRowsFactory:
    return lambda records: _gated_child_rows(model, records, *conditions)


def _profile_ids(model: Any, column: Any) -> ChildRowsFactory:
    return _child_ids(model, column.is_not(None), column != "")


def _location_ids(column: Any) -> ChildRowsFactory:
    return _child_ids(
        FacilityLocation,
        FacilityLocation.is_current.is_(True),
        column.is_not(None),
        column != "",
    )


def _relationship_side(column: Any, records: Any) -> Select:
    record_id = FacilityRelationship.source_record_id
    return (
        select(column.label("facility_id"))
        .select_from(FacilityRelationship)
        .outerjoin(records, records.c.id == record_id)
        .where(or_(record_id.is_(None), records.c.id.is_not(None)))
        .distinct()
    )


def _relationship_ids() -> ChildRowsFactory:
    return lambda records: _relationship_side(
        FacilityRelationship.subject_facility_id, records
    ).union_all(_relationship_side(FacilityRelationship.object_facility_id, records))


@dataclass(frozen=True)
class FieldDefinition:
    path: str
    scope: CoverageScope
    semantics: str
    type_scope: str | None = None
    require_current_location: bool = False
    scalar: Callable[[], ColumnElement[bool]] | None = None
    child: ChildRowsFactory | None = None

    def eligible_conditions(self) -> list[ColumnElement[bool]]:
        conditions = _public_gate()
        if self.type_scope:
            conditions.append(Facility.facility_type == self.type_scope)
        return conditions

    def _public_set(self):
        base = select(
            Facility.id.label("facility_id"), Facility.facility_type.label("category")
        ).where(*self.eligible_conditions())
        if self.require_current_location:
            ids = (
                select(FacilityLocation.facility_id.label("facility_id"))
                .where(FacilityLocation.is_current.is_(True))
                .distinct()
                .subquery("eligible_locations")
            )
            base = base.join(ids, ids.c.facility_id == Facility.id)
        return base.subquery("public_facilities")

    def count(self, session: Session) -> dict[str, Any]:
        """Standalone count for one field (also used by ad-hoc audits)."""

        public = self._public_set()
        if self.child is not None:
            records = _public_source_ids().cte("coverage_public_records")
            populated = self.child(records).subquery("populated_facilities")
            rows = session.execute(
                select(
                    public.c.category.label("category"),
                    func.count().label("total"),
                    func.count(populated.c.facility_id).label("populated"),
                )
                .select_from(
                    public.outerjoin(populated, populated.c.facility_id == public.c.facility_id)
                )
                .group_by(public.c.category)
            ).all()
        elif self.scalar is not None:
            predicate = self.scalar()
            rows = session.execute(
                select(
                    Facility.facility_type.label("category"),
                    func.count().label("total"),
                    func.count().filter(predicate).label("populated"),
                )
                .select_from(Facility)
                .where(*self.eligible_conditions())
                .group_by(Facility.facility_type)
            ).all()
        else:  # pragma: no cover - guarded by construction in FIELDS
            raise ValueError(f"Field {self.path} has no counting rule")
        return _shape(self.path, self.scope, self.semantics, rows)


def _shape(path: str, scope: str, semantics: str, rows) -> dict[str, Any]:
    by_category = {row.category: {"total": row.total, "populated": row.populated} for row in rows}
    total = sum(row["total"] for row in by_category.values())
    populated = sum(row["populated"] for row in by_category.values())
    entry = {
        "field": path,
        "scope": scope,
        "populated": populated,
        "total": total,
        "fill_ratio": round(populated / total, 6) if total else 0.0,
        "semantics": semantics,
        "by_category": by_category,
    }
    return entry


def _batched_scalar_counts(session: Session, definitions: list[FieldDefinition]) -> dict[str, dict]:
    """Count every unscoped scalar field in a single grouped scan."""

    if not definitions:
        return {}
    columns = [
        func.count().filter(definition.scalar()).label(definition.path)  # type: ignore[misc]
        for definition in definitions
    ]
    rows = session.execute(
        select(Facility.facility_type.label("category"), func.count().label("total"), *columns)
        .select_from(Facility)
        .where(*_public_gate())
        .group_by(Facility.facility_type)
    ).all()
    result: dict[str, dict] = {definition.path: {} for definition in definitions}
    for row in rows:
        for definition in definitions:
            result[definition.path][row.category] = {
                "total": row.total,
                "populated": row._mapping[definition.path],
            }
    return result


def _batched_child_counts(session: Session, definitions: list[FieldDefinition]) -> dict[str, dict]:
    """Count all child collections in one query with one shared gate CTE."""

    if not definitions:
        return {}
    records = _public_source_ids().cte("coverage_public_records")
    current_ids = (
        select(FacilityLocation.facility_id.label("facility_id"))
        .where(FacilityLocation.is_current.is_(True))
        .distinct()
        .subquery("coverage_current_locations")
    )
    denominator_rows = session.execute(
        select(
            Facility.facility_type.label("category"),
            func.count().label("total"),
            func.count()
            .filter(Facility.id.in_(select(current_ids.c.facility_id)))
            .label("with_location"),
        )
        .select_from(Facility)
        .where(*_public_gate())
        .group_by(Facility.facility_type)
    ).all()
    denominators = {
        row.category: {"total": row.total, "with_location": row.with_location}
        for row in denominator_rows
    }

    parts = []
    for index, definition in enumerate(definitions):
        child = definition.child(records).subquery(f"coverage_child_{index}")  # type: ignore[misc]
        parts.append(
            select(
                literal(definition.path).label("field"),
                literal(definition.type_scope or "").label("type_scope"),
                child.c.facility_id.label("facility_id"),
            ).select_from(child)
        )
    populated_fields = union_all(*parts).subquery("coverage_populated_fields")
    numerator_rows = session.execute(
        select(
            populated_fields.c.field.label("field"),
            Facility.facility_type.label("category"),
            func.count(func.distinct(Facility.id)).label("populated"),
        )
        .select_from(
            populated_fields.join(
                Facility,
                and_conditions(
                    Facility.id == populated_fields.c.facility_id,
                    or_(
                        populated_fields.c.type_scope == "",
                        Facility.facility_type == populated_fields.c.type_scope,
                    ),
                ),
            )
        )
        .where(*_public_gate())
        .group_by(populated_fields.c.field, Facility.facility_type)
    ).all()
    numerators = {(row.field, row.category): row.populated for row in numerator_rows}

    result: dict[str, dict] = {}
    for definition in definitions:
        by_category: dict[str, dict] = {}
        for category, counts in denominators.items():
            if definition.type_scope and category != definition.type_scope:
                continue
            eligible = (
                counts["with_location"] if definition.require_current_location else counts["total"]
            )
            by_category[category] = {
                "total": eligible,
                "populated": min(numerators.get((definition.path, category), 0), eligible),
            }
        result[definition.path] = by_category
    return result


def and_conditions(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    result = conditions[0]
    for condition in conditions[1:]:
        result = result & condition
    return result


FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition(
        "display_name", "summary", NULL_SEMANTICS, scalar=_filled(Facility.display_name)
    ),
    FieldDefinition(
        "facility_subtype", "summary", NULL_SEMANTICS, scalar=_filled(Facility.facility_subtype)
    ),
    FieldDefinition(
        "ownership_type",
        "summary",
        "UNKNOWN means the source did not establish an owner type",
        scalar=_filled(Facility.ownership_type, unknown="UNKNOWN"),
    ),
    FieldDefinition(
        "operator_type",
        "summary",
        "UNKNOWN means the source did not establish an operator type",
        scalar=_filled(Facility.operator_type, unknown="UNKNOWN"),
    ),
    FieldDefinition(
        "public_access_class",
        "summary",
        "UNKNOWN means the source did not establish conditions of entry",
        scalar=_filled(Facility.public_access_class, unknown="UNKNOWN"),
    ),
    FieldDefinition(
        "functions[]", "summary", COLLECTION_SEMANTICS, child=_child_ids(FacilityFunction)
    ),
    FieldDefinition(
        "location.postal_code",
        "summary",
        NULL_SEMANTICS + "; denominator is facilities with a current location",
        require_current_location=True,
        child=_location_ids(FacilityLocation.postal_code),
    ),
    FieldDefinition(
        "location.precision",
        "summary",
        PRECISION_SEMANTICS,
        require_current_location=True,
        child=_child_ids(
            FacilityLocation,
            FacilityLocation.is_current.is_(True),
            FacilityLocation.precision != "unknown",
        ),
    ),
    FieldDefinition(
        "official_name", "detail", NULL_SEMANTICS, scalar=_filled(Facility.official_name)
    ),
    FieldDefinition(
        "access_conditions",
        "detail",
        NULL_SEMANTICS + "; null never implies unrestricted access",
        scalar=_filled(Facility.access_conditions),
    ),
    FieldDefinition(
        "contacts[]", "detail", COLLECTION_SEMANTICS, child=_child_ids(FacilityContact)
    ),
    FieldDefinition(
        "services[]", "detail", COLLECTION_SEMANTICS, child=_child_ids(FacilityService)
    ),
    FieldDefinition("roles[]", "detail", COLLECTION_SEMANTICS, child=_child_ids(FacilityRole)),
    FieldDefinition("relationships[]", "detail", COLLECTION_SEMANTICS, child=_relationship_ids()),
    FieldDefinition(
        "function_details[]",
        "detail",
        COLLECTION_SEMANTICS + "; duplicates functions[] on a summary",
        child=_child_ids(FacilityFunction),
    ),
    FieldDefinition(
        "sources[]",
        "detail",
        COLLECTION_SEMANTICS + "; synthetic records keep their labelled source evidence",
        child=_child_ids(FacilitySourceLink),
    ),
    FieldDefinition(
        "school.sector",
        "profile_school",
        NULL_SEMANTICS + "; denominator is public schools",
        type_scope="school",
        child=_profile_ids(SchoolProfile, SchoolProfile.sector),
    ),
    FieldDefinition(
        "school.school_management",
        "profile_school",
        NULL_SEMANTICS + "; denominator is public schools",
        type_scope="school",
        child=_profile_ids(SchoolProfile, SchoolProfile.school_management),
    ),
    FieldDefinition(
        "school.division",
        "profile_school",
        NULL_SEMANTICS + "; denominator is public schools",
        type_scope="school",
        child=_profile_ids(SchoolProfile, SchoolProfile.division),
    ),
    FieldDefinition(
        "school.district",
        "profile_school",
        NULL_SEMANTICS + "; denominator is public schools",
        type_scope="school",
        child=_profile_ids(SchoolProfile, SchoolProfile.district),
    ),
    FieldDefinition(
        "school.resources[]",
        "profile_school",
        COLLECTION_SEMANTICS + "; denominator is public schools",
        type_scope="school",
        child=_child_ids(ResourceObservation),
    ),
    FieldDefinition(
        "health.licensing_status",
        "profile_health",
        NULL_SEMANTICS + "; denominator is public health facilities; not operational status",
        type_scope="health_facility",
        child=_profile_ids(HealthProfile, HealthProfile.licensing_status),
    ),
    FieldDefinition(
        "health.accreditations[]",
        "profile_health",
        COLLECTION_SEMANTICS
        + "; denominator is public health facilities; accreditation is not current operation",
        type_scope="health_facility",
        child=_child_ids(HealthAccreditation),
    ),
    FieldDefinition(
        "utility.resource_type",
        "profile_utility",
        NULL_SEMANTICS + "; denominator is public utility facilities",
        type_scope="utility_facility",
        child=_profile_ids(UtilityProfile, UtilityProfile.resource_type),
    ),
)

# The definition version is about this mapping, not a data release. Bump it when
# a field path, scope, or counting rule changes so cached clients can invalidate.
FIELD_COVERAGE_VERSION = "1.3"

COVERAGE_CAVEATS = (
    "Counts are computed at request time over public facilities using the same "
    "publication gate as the directory list (core.facilities.publication_status = 'public').",
    "Denominators are scope-specific: profile fields count only their facility type, "
    "and location fields count only facilities with a current location.",
    "publication_status and is_synthetic are constant across public responses and are "
    "deliberately omitted from this field list.",
    "Low fill means a fact is rarely established by a rights-cleared source, not that "
    "the underlying field is useless; missing values are preserved in the data model.",
)


_COVERAGE_CACHE: dict[tuple, dict[str, Any]] = {}


def collect_field_coverage(session: Session, *, by_category: bool = False) -> dict[str, Any]:
    """Compute coverage for every declared field with two batched queries.

    The payload is cached in-process under the latest public edit time. A
    publication changes that timestamp and invalidates the entry; until then an
    ETag request is served from memory instead of re-scanning the national
    dataset. This is the on-demand computation option from the DX plan; the
    documented fallback is a refresh-after-publication materialized view.
    """

    as_of = session.scalar(
        select(func.max(Facility.updated_at)).where(*public_facility_index_filter())
    )
    cache_key = (as_of, by_category, FIELD_COVERAGE_VERSION)
    cached = _COVERAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    scalar_definitions = [definition for definition in FIELDS if definition.scalar is not None]
    child_definitions = [definition for definition in FIELDS if definition.child is not None]
    scalar_counts = _batched_scalar_counts(session, scalar_definitions)
    child_counts = _batched_child_counts(session, child_definitions)

    entries = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for definition in FIELDS:
        by_cat = scalar_counts.get(definition.path) or child_counts.get(definition.path) or {}
        total = sum(value["total"] for value in by_cat.values())
        populated = sum(value["populated"] for value in by_cat.values())
        counts = {
            "field": definition.path,
            "scope": definition.scope,
            "populated": populated,
            "total": total,
            "fill_ratio": round(populated / total, 6) if total else 0.0,
            "semantics": definition.semantics,
        }
        entries.append(counts)
        if by_category:
            for category, pair in by_cat.items():
                grouped.setdefault(category, []).append(
                    {
                        **counts,
                        "populated": pair["populated"],
                        "total": pair["total"],
                        "fill_ratio": (
                            round(pair["populated"] / pair["total"], 6) if pair["total"] else 0.0
                        ),
                    }
                )
    payload: dict[str, Any] = {
        "as_of": as_of or utcnow(),
        "version": FIELD_COVERAGE_VERSION,
        "fields": entries,
        "caveats": list(COVERAGE_CAVEATS),
    }
    if by_category:
        payload["by_category"] = grouped
    _COVERAGE_CACHE.clear()
    _COVERAGE_CACHE[cache_key] = payload
    return payload
