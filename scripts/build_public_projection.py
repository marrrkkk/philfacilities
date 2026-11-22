#!/usr/bin/env python3
"""Build the public-only read model that the hosted API serves.

The authoritative database keeps every release, assertion, internal record and
raw payload. This script makes a *derived* copy on a scratch database, filters
it down to what the public API may serve, and writes a custom-format dump plus
a JSON manifest. Heroku never runs ingestion and never receives provenance.

The copy is intentionally small enough for `heroku-postgresql:essential-0`
(1 GB including indexes). It contains public facilities, current locations,
profiles, global lookups, and a slim source-evidence layer so detail pages and
the publication gate keep working. Assertions, fusions, change history, raw
payloads and internal rows stay in the authoritative database.

Usage:
    uv run python scripts/build_public_projection.py \
      --source-url postgresql+psycopg://user:pass@host:5432/philfacilities
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRATCH_DB = "philfacilities_public_projection_test"
DEFAULT_OUTPUT_DIR = ROOT / "var" / "publish"
MANIFEST_VERSION = 1

# Copy order respects foreign keys: lookups, releases, records, then facilities,
# then child/provenance rows that reference them.
TABLE_ORDER: tuple[str, ...] = (
    "source.agencies",
    "source.datasets",
    "source.releases",
    "source.ingestion_runs",
    "source.source_checks",
    "quality.publication_gates",
    "geo.geographic_releases",
    "geo.administrative_units",
    "geo.geography_crosswalk",
    "geo.osm_admin_boundaries",
    "source.records",
    "stats.population_observations",
    "core.facilities",
    "source.facility_source_links",
    "core.facility_slug_aliases",
    "core.facility_locations",
    "core.facility_functions",
    "core.facility_roles",
    "core.facility_services",
    "core.facility_contacts",
    "core.facility_relationships",
    "school.profiles",
    "school.resource_observations",
    "health.profiles",
    "health.accreditations",
    "health.licenses",
    "utility.profiles",
)

# Tables whose rows belong to one facility. Only public facilities are copied.
FACILITY_CHILD_TABLES: frozenset[str] = frozenset(
    {
        "core.facility_slug_aliases",
        "core.facility_locations",
        "core.facility_functions",
        "core.facility_roles",
        "core.facility_services",
        "core.facility_contacts",
        "school.profiles",
        "school.resource_observations",
        "health.profiles",
        "health.accreditations",
        "health.licenses",
        "utility.profiles",
    }
)

# Indexes/constraints the API does not need in a read-only projection. Dropping
# them keeps the dump comfortably below the 1 GB hosted quota.
PROJECTION_INDEXES_TO_DROP: tuple[str, ...] = (
    "source.ix_source_records_source_key_trgm",
    "source.uq_records_release_source_key",
    "source.ix_source_records_release",
    "source.ix_links_source_entity",
    "source.uq_links_facility_source_record",
    "core.idx_facility_locations_geom",
)

# Tables deliberately absent from the read model. Their data stays authoritative.
OMITTED_TABLES: tuple[str, ...] = (
    "core.attribute_assertions",
    "core.facility_attribute_fusions",
    "source.release_facility_snapshots",
    "history.facility_change_events",
    "quality.issues",
    "quality.match_candidates",
)

# (table, facility foreign key or None for global rows) for record references.
RECORD_REFERENCE_TABLES: tuple[tuple[str, str | None], ...] = (
    ("source.facility_source_links", "facility_id"),
    ("core.facility_locations", "facility_id"),
    ("core.facility_functions", "facility_id"),
    ("core.facility_roles", "facility_id"),
    ("core.facility_services", "facility_id"),
    ("core.facility_contacts", "facility_id"),
    ("core.facility_relationships", "subject_facility_id"),
    ("school.profiles", "facility_id"),
    ("school.resource_observations", "facility_id"),
    ("health.profiles", "facility_id"),
    ("health.accreditations", "facility_id"),
    ("health.licenses", "facility_id"),
    ("utility.profiles", "facility_id"),
    ("stats.population_observations", None),
)


@dataclass(frozen=True)
class CopyResult:
    table: str
    rows: int


def normalise_database_url(url: str) -> str:
    """Return a libpq/psycopg URL, dropping SQLAlchemy driver suffixes."""

    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )


def admin_database_url(url: str) -> str:
    """Point at the `postgres` maintenance database on the same server."""

    base = normalise_database_url(url)
    head, _, _ = base.rpartition("/")
    return f"{head}/postgres"


def scratch_database_url(url: str, scratch_db: str) -> str:
    """Point at the scratch database on the same server as the source."""

    base = normalise_database_url(url)
    head, _, _ = base.rpartition("/")
    return f"{head}/{scratch_db}"


def table_columns(conn: psycopg.Connection, table: str) -> list[str]:
    schema, name = table.split(".", 1)
    rows = conn.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position""",
        (schema, name),
    ).fetchall()
    return [row[0] for row in rows]


def select_expression(table: str, column: str) -> str:
    """Return the SELECT expression for one target column.

    Read-only projections keep the schema but do not need raw payloads or link
    evidence. Nulling those columns saves hundreds of megabytes without
    changing any public API response.
    """

    if table == "source.records" and column == "raw_payload":
        return "'{}'::jsonb"
    if table == "source.facility_source_links" and column in {
        "source_entity_id",
        "evidence",
    }:
        return "NULL"
    return f'src."{column}"'


def record_reference_query(select_list: str) -> str:
    """Build the set-based SELECT for slim source records.

    A single UNION + hash join replaces a dozen correlated EXISTS clauses,
    which took over 20 minutes at national scale. Only records referenced by
    public facilities or global population rows are kept.
    """

    references: list[str] = []
    for table, facility_column in RECORD_REFERENCE_TABLES:
        if facility_column:
            references.append(
                f"SELECT x.source_record_id AS id FROM {table} x "
                f"JOIN public_facilities f ON f.id = x.{facility_column} "
                "WHERE x.source_record_id IS NOT NULL"
            )
        else:
            references.append(
                f"SELECT source_record_id AS id FROM {table} WHERE source_record_id IS NOT NULL"
            )
    return (
        "WITH public_facilities AS ("
        "SELECT id FROM core.facilities WHERE publication_status = 'public'"
        "), referenced AS ("
        + " UNION ".join(references)
        + ") SELECT "
        + select_list
        + " FROM source.records src JOIN referenced r ON r.id = src.id"
    )


def table_filter(table: str) -> str | None:
    """Return the authoritative-DB predicate that selects public rows."""

    if table == "core.facilities":
        return "src.publication_status = 'public'"
    if table == "source.facility_source_links":
        return (
            "EXISTS (SELECT 1 FROM core.facilities f "
            "WHERE f.id = src.facility_id AND f.publication_status = 'public')"
        )
    if table == "core.facility_locations":
        return (
            "src.is_current IS TRUE AND EXISTS (SELECT 1 FROM core.facilities f "
            "WHERE f.id = src.facility_id AND f.publication_status = 'public')"
        )
    if table == "core.facility_relationships":
        return (
            "EXISTS (SELECT 1 FROM core.facilities f "
            "WHERE f.id = src.subject_facility_id AND f.publication_status = 'public')"
        )
    if table in FACILITY_CHILD_TABLES:
        return (
            "EXISTS (SELECT 1 FROM core.facilities f "
            "WHERE f.id = src.facility_id AND f.publication_status = 'public')"
        )
    return None


def copy_table(
    source: psycopg.Connection,
    target: psycopg.Connection,
    table: str,
    *,
    columns: list[str] | None = None,
    where: str | None = None,
) -> int:
    """Stream one table with COPY and return the number of rows written."""

    cols = columns or table_columns(source, table)
    quoted = ", ".join(f'"{column}"' for column in cols)
    select_list = ", ".join(f'{select_expression(table, c)} AS "{c}"' for c in cols)
    if table == "source.records":
        query = record_reference_query(select_list)
    else:
        query = f"SELECT {select_list} FROM {table} src"
        if where:
            query = f"{query} WHERE {where}"
    written = 0
    with (
        source.cursor().copy(f"COPY ({query}) TO STDOUT") as reader,
        target.cursor().copy(f"COPY {table} ({quoted}) FROM STDIN") as writer,
    ):
        for row in reader.rows():
            writer.write_row(row)
            written += 1
    target.commit()
    return written


def copy_public_rows(source: psycopg.Connection, target: psycopg.Connection) -> list[CopyResult]:
    """Copy every table in the projection, applying the public filter."""

    results: list[CopyResult] = []
    for table in TABLE_ORDER:
        rows = copy_table(source, target, table, where=table_filter(table))
        results.append(CopyResult(table=table, rows=rows))
    return results


def trim_projection_indexes(conn: psycopg.Connection) -> None:
    """Drop indexes and constraints the read-only projection does not need."""

    for name in PROJECTION_INDEXES_TO_DROP:
        schema, _, object_name = name.partition(".")
        with conn.cursor() as cur:
            cur.execute(
                """SELECT conrelid::regclass::text FROM pg_constraint
                   WHERE connamespace = %s::regnamespace AND conname = %s""",
                (schema, object_name),
            )
            constraint = cur.fetchone()
            if constraint:
                cur.execute(f"ALTER TABLE {constraint[0]} DROP CONSTRAINT {object_name}")
            else:
                cur.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()


def refresh_coverage(conn: psycopg.Connection) -> None:
    """Pre-compute the materialised view behind GET /v1/fields."""

    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW stats.api_field_coverage")
    conn.commit()


def vacuum_projection(conn: psycopg.Connection) -> None:
    """Compact and analyse every application table in the projection."""

    tables = [
        row[0]
        for row in conn.execute(
            """SELECT table_schema || '.' || table_name FROM information_schema.tables
               WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'tiger', 'topology')
                 AND table_type = 'BASE TABLE'"""
        ).fetchall()
    ]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"VACUUM (FULL, ANALYZE) {table}")


def build_manifest(
    *,
    source_db: str,
    revision: str,
    dump_path: Path,
    counts: dict[str, int],
    by_category: dict[str, int],
    postgres_version: str,
) -> dict:
    """Create the manifest that the deploy workflow verifies before loading."""

    digest = hashlib.sha256()
    with dump_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "format_version": MANIFEST_VERSION,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_database": source_db,
        "source_revision": revision,
        "dump_file": dump_path.name,
        "sha256": digest.hexdigest(),
        "bytes": dump_path.stat().st_size,
        "postgres_version": postgres_version,
        "counts": counts,
        "by_category": by_category,
    }


def _database_name(url: str) -> str:
    base = normalise_database_url(url)
    return base.rpartition("/")[2].split("?", 1)[0]


def _run_migrations(scratch_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = scratch_url.replace("postgresql://", "postgresql+psycopg://", 1)
    subprocess.run(
        ["uv", "run", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
    )


def _dump_command(scratch_db: str) -> list[str]:
    # Include `history` (and every other schema created by migrations) even
    # though the projection copies no rows into it. pg_restore --clean then
    # drops and recreates these empty tables in dependency order; otherwise a
    # stale FK such as history.facility_change_events -> core.facilities blocks
    # dropping the primary key on an already-provisioned hosted database.
    schemas = [
        "source",
        "core",
        "school",
        "health",
        "utility",
        "geo",
        "stats",
        "quality",
        "history",
    ]
    common: list[str] = []
    for schema in schemas:
        common.extend(["--schema", schema])
    common.extend(["--format=custom", "--no-owner", "--no-privileges", "-d", scratch_db])
    pg_dump = shutil.which("pg_dump")
    if pg_dump:
        return [pg_dump, "-h", "localhost", "-p", "54329", "-U", "philfacilities", *common]
    return [
        "docker",
        "compose",
        "-f",
        "infra/compose.yaml",
        "exec",
        "-T",
        "db",
        "pg_dump",
        "-U",
        "philfacilities",
        *common,
    ]


def _write_dump(scratch_db: str, dump_path: Path) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = "philfacilities"  # local development database only
    command = _dump_command(scratch_db)
    with dump_path.open("wb") as handle:
        subprocess.run(command, cwd=ROOT, env=env, check=True, stdout=handle)


def build_projection(
    source_url: str,
    *,
    scratch_db: str = DEFAULT_SCRATCH_DB,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    skip_dump: bool = False,
) -> dict:
    """Create the scratch projection, dump it, and return the manifest."""

    if not scratch_db.endswith("_test"):
        raise ValueError("scratch database must end in _test")

    source_url = normalise_database_url(source_url)
    admin_url = admin_database_url(source_url)
    scratch_url = scratch_database_url(source_url, scratch_db)

    with psycopg.connect(admin_url, autocommit=True, connect_timeout=15) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {scratch_db}")
        admin.execute(f"CREATE DATABASE {scratch_db} TEMPLATE template_postgis")

    _run_migrations(scratch_url)

    with psycopg.connect(source_url) as source, psycopg.connect(scratch_url) as target:
        revision = source.execute(
            "SELECT coalesce(max(version_num), 'none') FROM alembic_version"
        ).fetchone()[0]
        results = copy_public_rows(source, target)
        trim_projection_indexes(target)
        refresh_coverage(target)
        target.autocommit = True
        try:
            vacuum_projection(target)
        finally:
            target.autocommit = False
        counts = {result.table: result.rows for result in results}
        by_category = dict(
            target.execute(
                """SELECT facility_type, count(*) FROM core.facilities
                   GROUP BY facility_type ORDER BY facility_type"""
            ).fetchall()
        )
        postgres_version = target.execute("SHOW server_version").fetchone()[0]

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dump_path = output_dir / f"public-{stamp}.dump"
    if not skip_dump:
        _write_dump(scratch_db, dump_path)

    manifest = build_manifest(
        source_db=_database_name(source_url),
        revision=revision,
        dump_path=dump_path,
        counts=counts,
        by_category=by_category,
        postgres_version=postgres_version,
    )
    manifest_path = dump_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url",
        default=os.environ.get("PHILFACILITIES_DATABASE_URL", ""),
        help="Authoritative database URL (or PHILFACILITIES_DATABASE_URL).",
    )
    parser.add_argument("--scratch-db", default=DEFAULT_SCRATCH_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-dump", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.source_url:
        parser.error("provide --source-url or PHILFACILITIES_DATABASE_URL")

    manifest = build_projection(
        args.source_url,
        scratch_db=args.scratch_db,
        output_dir=args.output_dir,
        skip_dump=args.skip_dump,
    )
    print(f"facilities: {manifest['counts']['core.facilities']:,}")
    print(f"records: {manifest['counts']['source.records']:,}")
    print(f"links: {manifest['counts']['source.facility_source_links']:,}")
    print(f"dump: {manifest['dump_file']} ({manifest['bytes'] / 1024 / 1024:.0f} MB)")
    print(f"sha256: {manifest['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
