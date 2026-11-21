"""Refresh-after-publication materialized view for field coverage.

The query in ``field_coverage.collect_field_coverage`` is correct but too slow
to run on a cold cache at national scale (~27-31 s on 229k records). This module
projects the *same declarative definitions* into a PostgreSQL materialized view
so ``GET /v1/fields`` becomes a cheap indexed read. The view definition is
generated from ``FIELDS`` at migration time; a contract/integration test
reconciles its rows with the on-demand counts so the projection cannot drift.

Rollback: migration 0026 owns the view and its unique index; downgrading drops
both. The endpoint falls back to on-demand computation when the view is absent
(e.g. on a database that has not run the migration), so the change is reversible.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from .field_coverage import (
    FIELD_COVERAGE_VERSION,
    FIELDS,
    FieldDefinition,
    _public_source_ids,
    utcnow,
)

MV_NAME = "stats.api_field_coverage"
MV_INDEX = "ux_api_field_coverage_field_category"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _eligibility_sql(definition: FieldDefinition) -> str:
    conditions = ["core.facilities.publication_status = 'public'"]
    if definition.type_scope:
        conditions.append(f"core.facilities.facility_type = {_sql_literal(definition.type_scope)}")
    if definition.require_current_location:
        conditions.append(
            "EXISTS (SELECT 1 FROM core.facility_locations "
            "WHERE core.facility_locations.facility_id = core.facilities.id "
            "AND core.facility_locations.is_current)"
        )
    return " AND ".join(conditions)


def _populated_sql(definition: FieldDefinition) -> str:
    if definition.scalar is not None:
        return str(definition.scalar().compile(compile_kwargs={"literal_binds": True}))
    if definition.child is not None:
        # Compile the same child query the on-demand path uses. Correlate the
        # resulting distinct-id set to the facility row being projected.
        source_ids = _public_source_ids()
        rows = definition.child(source_ids.subquery("mv_public_records"))
        compiled = str(rows.compile(compile_kwargs={"literal_binds": True}))
        return (
            "EXISTS (SELECT 1 FROM (" + compiled + ") AS mv_hit "
            "WHERE mv_hit.facility_id = core.facilities.id)"
        )
    raise ValueError(f"Field {definition.path} has no counting rule")


def build_definition_sql(fields: tuple[FieldDefinition, ...] = FIELDS) -> str:
    """Return the CREATE MATERIALIZED VIEW body from the declarative mapping."""

    branches = []
    for definition in fields:
        branches.append(
            "    SELECT "
            f"{_sql_literal(definition.path)}::text AS field, "
            f"{_sql_literal(definition.scope)}::text AS scope, "
            "core.facilities.facility_type::text AS category, "
            "1::bigint AS eligible, "
            f"CASE WHEN {_populated_sql(definition)} THEN 1::bigint ELSE 0::bigint END "
            "AS populated\n"
            "    FROM core.facilities\n"
            f"    WHERE {_eligibility_sql(definition)}"
        )
    return (
        "CREATE MATERIALIZED VIEW " + MV_NAME + " AS\n"
        "WITH coverage_field_rows AS (\n" + "\n    UNION ALL\n".join(branches) + "\n)\n"
        "SELECT field, scope, category,\n"
        "       SUM(eligible)::bigint AS total,\n"
        "       SUM(populated)::bigint AS populated,\n"
        "       now() AS refreshed_at\n"
        "FROM coverage_field_rows\n"
        "GROUP BY field, scope, category\n"
        "WITH NO DATA"
    )


def create_index_sql() -> str:
    """A unique index makes REFRESH MATERIALIZED VIEW CONCURRENTLY possible."""

    return f"CREATE UNIQUE INDEX {MV_INDEX} ON {MV_NAME} (field, category)"


def refresh_coverage_mv(session: Session, *, concurrent: bool = True) -> None:
    """Refresh the projection. Call after a publication commit.

    CONCURRENTLY cannot run inside a transaction block, so use a short-lived
    AUTOCOMMIT connection rather than the caller's session.
    """

    keyword = (
        "REFRESH MATERIALIZED VIEW CONCURRENTLY" if concurrent else "REFRESH MATERIALIZED VIEW"
    )
    bind = session.get_bind()
    with bind.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
        connection.execute(text(f"{keyword} {MV_NAME}"))


def coverage_mv_fresh(session: Session) -> bool:
    """True when the projection was refreshed after the last public edit."""

    row = session.execute(
        text(
            "SELECT (SELECT max(refreshed_at) FROM " + MV_NAME + ") AS refreshed, "
            "(SELECT max(updated_at) FROM core.facilities "
            "WHERE publication_status = 'public') AS updated"
        )
    ).one()
    refreshed: datetime | None = row.refreshed
    updated: datetime | None = row.updated
    return refreshed is not None and (updated is None or refreshed >= updated)


def read_coverage_mv(session: Session, *, by_category: bool = False) -> dict:
    """Read the projection into the same public response shape as the endpoint."""

    rows = session.execute(
        text(
            "SELECT field, scope, category, total, populated, refreshed_at "
            f"FROM {MV_NAME} ORDER BY field, category"
        )
    ).all()
    definitions = {definition.path: definition for definition in FIELDS}
    grouped: dict[str, list[dict]] = {}
    as_of: datetime | None = None
    # A field with no eligible facilities produces no MV rows. Publish a zero
    # entry anyway so the response shape always matches the declarative mapping.
    by_path = {
        definition.path: {
            "field": definition.path,
            "scope": definition.scope,
            "populated": 0,
            "total": 0,
            "fill_ratio": 0.0,
            "semantics": definition.semantics,
        }
        for definition in FIELDS
    }
    for row in rows:
        as_of = row.refreshed_at if as_of is None else max(as_of, row.refreshed_at)
        entry = by_path.setdefault(
            row.field,
            {
                "field": row.field,
                "scope": row.scope,
                "populated": 0,
                "total": 0,
                "fill_ratio": 0.0,
                "semantics": definitions[row.field].semantics if row.field in definitions else "",
            },
        )
        entry["populated"] += row.populated
        entry["total"] += row.total
    entries = list(by_path.values())
    for entry in entries:
        entry["fill_ratio"] = (
            round(entry["populated"] / entry["total"], 6) if entry["total"] else 0.0
        )
    if by_category:
        for row in rows:
            base = {k: v for k, v in by_path[row.field].items()}
            grouped.setdefault(row.category, []).append(
                {
                    **base,
                    "populated": row.populated,
                    "total": row.total,
                    "fill_ratio": round(row.populated / row.total, 6) if row.total else 0.0,
                }
            )
    payload = {
        # An empty view (fresh deployment, no public facilities) has no row to
        # source the timestamp from. Keep the declared datetime shape.
        "as_of": as_of or utcnow(),
        # The version describes the field definitions, not the storage path.
        # Both the view and the on-demand fallback must report the same value.
        "version": FIELD_COVERAGE_VERSION,
        "fields": entries,
        "caveats": [
            "Counts come from a materialized view refreshed after publication; "
            "the publication gate is applied in the view definition.",
            "Scope denominators are explicit: profile fields count only their "
            "facility type and location fields only current locations.",
            "Missing values stay missing; [] means no publication-cleared rows.",
        ],
    }
    if by_category:
        payload["by_category"] = grouped
    return payload
