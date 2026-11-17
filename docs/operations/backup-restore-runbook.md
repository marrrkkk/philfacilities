# Database backup and restore runbook

**Status:** Local Compose procedure implemented and verified on 15 November 2026 against the 15 November 2026 real-data snapshot (88,824 facilities; 235,049 source records; 47 releases). Restore verification passed 15/15 checks. Production schedule, off-host retention, encryption, and point-in-time recovery are **not** configured. This runbook describes the tested local procedure and the steps a production operator must complete before launch.

Related: [Operations](../operations.md).

## 1. Scope and guarantees

| Item | Current state |
|---|---|
| Database | PostgreSQL 17.5 with PostGIS 3.5, custom-format `pg_dump` |
| Backup contents | All application schemas (`source`, `core`, `geo`, `school`, `health`, `stats`, `quality`, `history`), data, indexes, constraints, and PostGIS extension objects. Includes 92,422 canonical facilities (61,806 public, 30,616 non-public), non-public DepEd EBEIS rows, and retained source provenance |
| Backup tooling | `scripts/db_backup.sh` through the Compose `db` service |
| Restore verification | `scripts/db_restore_verify.sh` restores into a throwaway `*_test` database and compares against a source manifest |
| Tested restore | 15 checks passed on 15 November 2026 at real-data scale (see [evidence](evidence/2026-11-15-backup-restore/real-scale/philfacilities-20261115T083554Z.dump.restore-report.txt)); the earlier demo-scale run is retained in [2026-11-14 evidence](evidence/2026-11-14-backup-restore/restore-report.txt) |
| Off-host copy | Not implemented |
| Encryption at rest/in transit | Not implemented by these scripts; rely on the storage platform and TLS |
| Schedule/retention | Not configured; requirements in section 7 |
| Point-in-time recovery | Not configured; provider-level WAL archiving/PITR decision is pending |
| Object storage backups | Not implemented; raw-source objects need separate versioning/retention |

These scripts use `--no-owner --no-privileges`. The dump does not contain role passwords or ownership grants. A restore target must already have the required roles, extensions, and PostGIS image.

## 2. Why a manifest and a scratch restore

A dump that exits successfully can still be unusable. The procedure therefore:

1. writes a custom-format archive;
2. validates the archive with `pg_restore --list`;
3. records the SHA-256 checksum, byte size, archive entry count, PostgreSQL/PostGIS versions, Alembic revision, schema/table counts, and key row counts;
4. restores the archive into a separate database with `pg_restore --exit-on-error`;
5. compares the restored database to the manifest;
6. drops the scratch database unless explicitly told to keep it.

This proves the backup can be read and restored. It does **not** prove production recovery time or data freshness.

## 3. Prerequisites

- Docker with Compose, and the `db` service running (`docker compose -f infra/compose.yaml up -d db`).
- The database credentials configured for the Compose service. Defaults: database `philfacilities`, user `philfacilities`.
- Free disk space at least twice the dump size for restore verification.
- A target PostgreSQL major version compatible with the dump. Use the same `postgis/postgis:17-3.5` image for the tested path.

The host does not need `pg_dump`, `pg_restore`, or `psql`; all commands run inside the database container.

> **WSL/Docker note:** if Docker requires a separate config directory in your environment, prefix commands with `DOCKER_CONFIG=/tmp/opencode/docker-config` or export it for the session. This is environment-specific and not required by the scripts themselves.

## 4. Create a backup

```bash
scripts/db_backup.sh
```

`just backup-db` runs the same command where `just` is installed.

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `PHILFACILITIES_COMPOSE_FILE` | `infra/compose.yaml` | Compose file that defines the database service |
| `PHILFACILITIES_DB_SERVICE` | `db` | Compose service name |
| `PHILFACILITIES_DB_NAME` | `philfacilities` | Source database |
| `PHILFACILITIES_DB_USER` | `philfacilities` | Database user |
| `PHILFACILITIES_BACKUP_DIR` | `var/backups` | Output directory |
| `PHILFACILITIES_BACKUP_TIMESTAMP` | current UTC time | Deterministic filename for scheduled/manual runs |

Outputs:

```text
var/backups/philfacilities-<timestamp>.dump
var/backups/philfacilities-<timestamp>.dump.sha256
var/backups/philfacilities-<timestamp>.dump.toc.txt
var/backups/philfacilities-<timestamp>.dump.manifest.txt
```

The script fails if the archive has zero entries, if any required manifest value is empty, or if `pg_dump` fails. A partial file is removed on failure. File permissions are restricted with `umask 077`.

Example manifest from the 14 November 2026 test run, when the database still held the small synthetic demo set. Current real-data dump counts will be much larger; use the generated manifest, not these historic figures, for verification:

```text
format_version=1
created_at=2026-11-14T15:26:17Z
source_database=philfacilities
dump_file=philfacilities-20261114T152614Z.dump
bytes=108974
sha256=92e185d828c7793d340e2fad13097769b6927f1cd7bfff66adb87bdb82cdd3fd
toc_entries=171
postgres_version=17.5(Debian17.5-1.pgdg110+1)
postgis_version=3.5 USE_GEOS=1 USE_PROJ=1 USE_STATS=1
alembic_revision=0002_match_candidates
schemas=7
tables=22
facilities=22
source_records=58
releases=5
geographic_releases=1
administrative_units=30
facility_locations=15
locations_with_geom=15
locations_srid_4326=15
```

## 5. Verify a restore

Verify the newest dump in the backup directory:

```bash
scripts/db_restore_verify.sh
```

Verify a specific dump:

```bash
scripts/db_restore_verify.sh var/backups/philfacilities-20261114T152614Z.dump
```

`just restore-verify` or `just restore-verify var/backups/<file>.dump` runs the same commands where `just` is installed.

Safety rules:

- The scratch database name **must end in `_test`**; the script refuses anything else.
- Verification creates and drops `philfacilities_restore_test` by default. Override with `PHILFACILITIES_RESTORE_DB`.
- Set `PHILFACILITIES_KEEP_RESTORE_DB=1` to retain the restored database for inspection. Drop it manually afterwards.
- The checksum is verified before any database is created. A tampered or truncated archive fails immediately.
- `pg_restore --exit-on-error` means any SQL error fails the verification instead of producing a partially restored database silently.

The report is written beside the dump as `<dump>.restore-report.txt`. It records each expected/actual pair and never includes credentials.

Tested result on 14 November 2026:

```text
result=pass
check.pg_restore=PASS
check.postgres_version=PASS
check.postgis_version=PASS
check.schemas=PASS expected=7 actual=7
check.tables=PASS expected=22 actual=22
check.alembic_revision=PASS expected=0002_match_candidates actual=0002_match_candidates
check.facilities=PASS expected=22 actual=22
check.source_records=PASS expected=58 actual=58
check.releases=PASS expected=5 actual=5
check.geographic_releases=PASS expected=1 actual=1
check.administrative_units=PASS expected=30 actual=30
check.facility_locations=PASS expected=15 actual=15
check.locations_with_geom=PASS expected=15 actual=15
check.locations_srid_4326=PASS expected=15 actual=15
check.postgis_extension=PASS
```

A negative test appended bytes to a copy of the dump. The script exited with status 1 and recorded `check.sha256=FAIL` without creating a database. This confirms the integrity gate works.

## 6. Restore to a new production database

Do not restore over a live database in place. Use a new database and switch the application connection only after validation.

1. **Freeze writes.** Stop ingestion jobs and put the API into maintenance/read-only mode, or stop it, so no writes are lost after the dump timestamp.
2. **Create a fresh target database** with the same PostgreSQL major version and PostGIS extension available.
3. **Verify the archive checksum** against the stored `.sha256` and manifest before restoring.
4. **Restore with explicit failure handling:**

   ```bash
   pg_restore --exit-on-error --no-owner --no-privileges \
     --dbname="$TARGET_DATABASE_URL" /path/to/philfacilities-<timestamp>.dump
   ```

   Run this from a host/container with matching `pg_restore` 17.x and network access to the target. The Compose helper is only appropriate when the target is that container.

5. **Validate the restored database:**
   - `alembic_version` matches the manifest;
   - schema/table counts match;
   - facility, source-record, release, geography, and location counts match;
   - `select postgis_version();` returns a compatible version;
   - all non-null geometries have SRID 4326;
   - a sample facility detail and `/v1/statistics` response match expectations.
6. **Run the application smoke tests** against the new database: health check, directory search, facility profile, map bbox query, and source catalogue.
7. **Switch the connection string** and restart the API/ingest services.
8. **Record the restore**: operator, timestamp, dump checksum, target database, validation output, and any data-loss window.
9. **Resume ingestion/writes** only after the smoke tests pass.

If validation fails, keep the old database serving traffic and investigate. Do not delete the previous database until the new one has been accepted and a fresh backup exists.

## 7. Production schedule and retention requirements

These are requirements to implement, not current automation:

- **RPO:** at most 24 hours for the database until a business requirement sets a tighter target. Daily full backups are the minimum; PITR/WAL archiving should be evaluated for a public production service.
- **RTO:** target at most 4 hours for a database restore, measured during a restore exercise. The current local restore has not been timed against production-sized data.
- **Schedule:** daily automated backup at a low-traffic UTC window; retain at least 30 daily backups and 12 monthly backups, subject to storage cost and any source-agreement retention limits.
- **Off-host:** copy dumps and manifests to encrypted object storage in a separate failure domain. A backup on the same volume as the database is not a backup.
- **Integrity:** run checksum verification on every copy and a restore verification at least monthly and after every schema migration.
- **Access:** restrict backup storage to operations roles; log downloads and restores. Dumps may contain non-public source data and must follow the same rights restrictions as the database.
- **Object storage:** enable versioning or immutable retention for raw source files where terms permit, and record checksums alongside objects.
- **Monitoring:** alert on backup job failure, missing daily backup, checksum mismatch, restore-verification failure, and backup age exceeding the RPO.
- **Ownership:** name a database operator and an escalation path before launch. This is currently unassigned.

## 8. Known limitations

- No scheduled job, retention policy, off-host replication, or alerting is configured.
- No PITR/WAL archiving; the maximum loss window is the time since the last successful dump.
- The scratch restore runs on the same database server, so it does not test host or volume loss.
- The scripts target the Compose service. A managed PostgreSQL provider needs equivalent `pg_dump`/`pg_restore` commands, provider backup verification, and network/TLS configuration.
- The manifest checks row counts and spatial metadata, not full row-level equality. A production acceptance test should add application-level checks and, where feasible, row-level checksums.
- Backups contain public facility data plus private raw source rows, including DepEd EBEIS school-head names. Backups and raw source objects must follow the same rights and access restrictions as the source systems; they are not public artifacts.
- The restore exercise used the 15 November 2026 snapshot. Dump size, restore time, and disk requirements for the current 92,422-facility database still need re-measurement.
- Restore time and storage growth have not been measured at production scale.

## 9. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `pg_restore: error: could not execute query ... extension "postgis"` | Target image/database lacks PostGIS | Use a `postgis/postgis` image or install the extension before restore |
| `server version mismatch` | `pg_restore` major version older than dump | Use matching PostgreSQL client tools |
| `database ... does not exist` | Scratch DB creation failed or wrong service | Check Compose service health and `PHILFACILITIES_DB_SERVICE` |
| Checksum mismatch | Truncated/corrupted/tampered dump | Discard it and restore from another verified copy |
| Counts differ | Restore partially applied or source changed during backup | Re-run with writes frozen; inspect the report's failing checks |
| Permission errors on dump | User lacks read access to tables/sequences | Grant required access or run as the database owner |

## 10. Evidence

The tested manifest and restore report are stored under [`docs/operations/evidence/2026-11-14-backup-restore/`](evidence/2026-11-14-backup-restore/). The dump itself is intentionally not committed because `var/` is ignored and backups may contain non-public data.
