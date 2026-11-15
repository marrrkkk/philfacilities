#!/usr/bin/env bash
#
# Restore a PhilFacilities custom-format dump into a throwaway database and verify
# that the restored PostGIS schema/data matches the source manifest produced by
# scripts/db_backup.sh. The scratch database is dropped on exit unless
# PHILFACILITIES_KEEP_RESTORE_DB=1 is set.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PHILFACILITIES_COMPOSE_FILE:-${ROOT_DIR}/infra/compose.yaml}"
DB_SERVICE="${PHILFACILITIES_DB_SERVICE:-db}"
DB_USER="${PHILFACILITIES_DB_USER:-philfacilities}"
BACKUP_DIR="${PHILFACILITIES_BACKUP_DIR:-${ROOT_DIR}/var/backups}"
SCRATCH_DB="${PHILFACILITIES_RESTORE_DB:-philfacilities_restore_test}"
KEEP_DB="${PHILFACILITIES_KEEP_RESTORE_DB:-0}"

DUMP_FILE="${1:-}"
if [[ -z "${DUMP_FILE}" ]]; then
  DUMP_FILE="$(find "${BACKUP_DIR}" -maxdepth 1 -name '*.dump' -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr | awk 'NR==1 {sub(/^[^ ]+ /, ""); print}')"
fi
if [[ -z "${DUMP_FILE}" || ! -f "${DUMP_FILE}" ]]; then
  echo "Usage: $0 [path/to/backup.dump]" >&2
  echo "No dump found in ${BACKUP_DIR}." >&2
  exit 1
fi
DUMP_FILE="$(cd "$(dirname "${DUMP_FILE}")" && pwd)/$(basename "${DUMP_FILE}")"
MANIFEST_FILE="${DUMP_FILE}.manifest.txt"
REPORT_FILE="${DUMP_FILE}.restore-report.txt"

if [[ ! -f "${MANIFEST_FILE}" ]]; then
  echo "Restore verification failed: manifest not found: ${MANIFEST_FILE}" >&2
  exit 1
fi
if [[ "${SCRATCH_DB}" != *_test ]]; then
  echo "Refusing restore: scratch database must end in _test (got ${SCRATCH_DB})." >&2
  exit 1
fi

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

manifest_value() {
  local key="$1"
  awk -F= -v key="${key}" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "${MANIFEST_FILE}"
}

psql_scratch_value() {
  compose exec -T "${DB_SERVICE}" psql \
    -U "${DB_USER}" -d "${SCRATCH_DB}" -v ON_ERROR_STOP=1 -Atc "$1"
}

count_scratch_rows() {
  psql_scratch_value "select count(*) from $1;" | tr -d '[:space:]'
}

RESULT="pass"
CHECKS=""
record_check() {
  local key="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    CHECKS+="check.${key}=PASS expected=${expected} actual=${actual}"$'\n'
  else
    RESULT="fail"
    CHECKS+="check.${key}=FAIL expected=${expected} actual=${actual}"$'\n'
  fi
}

cleanup() {
  if [[ "${KEEP_DB}" != "1" ]]; then
    compose exec -T "${DB_SERVICE}" dropdb -U "${DB_USER}" --if-exists "${SCRATCH_DB}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

write_report() {
  {
    echo "PhilFacilities restore verification"
    echo "result=${RESULT}"
    echo "verified_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "dump_file=$(basename "${DUMP_FILE}")"
    echo "manifest_file=$(basename "${MANIFEST_FILE}")"
    echo "sha256=$(manifest_value sha256)"
    echo "source_database=$(manifest_value source_database)"
    echo "restore_database=${SCRATCH_DB}"
    echo "kept_for_inspection=${KEEP_DB}"
    printf '%s' "${CHECKS}"
  } >"${REPORT_FILE}"
}

# Verify the archive checksum before touching the database.
EXPECTED_SHA="$(manifest_value sha256)"
ACTUAL_SHA="$(sha256sum "${DUMP_FILE}" | awk '{print $1}')"
if [[ -z "${EXPECTED_SHA}" || "${EXPECTED_SHA}" != "${ACTUAL_SHA}" ]]; then
  CHECKS+="check.sha256=FAIL expected=${EXPECTED_SHA:-missing} actual=${ACTUAL_SHA}"$'\n'
  RESULT="fail"
  write_report
  echo "Restore verification failed: checksum mismatch. Report: ${REPORT_FILE}" >&2
  exit 1
fi

echo "→ Recreating scratch database ${SCRATCH_DB}"
compose exec -T "${DB_SERVICE}" dropdb -U "${DB_USER}" --if-exists "${SCRATCH_DB}" >/dev/null
compose exec -T "${DB_SERVICE}" createdb -U "${DB_USER}" "${SCRATCH_DB}"

echo "→ Restoring $(basename "${DUMP_FILE}")"
if ! compose exec -T "${DB_SERVICE}" pg_restore \
  -U "${DB_USER}" -d "${SCRATCH_DB}" \
  --no-owner --no-privileges --exit-on-error <"${DUMP_FILE}"; then
  CHECKS+="check.pg_restore=FAIL"$'\n'
  RESULT="fail"
  write_report
  echo "Restore verification failed: pg_restore returned an error. Report: ${REPORT_FILE}" >&2
  exit 1
fi
CHECKS+="check.pg_restore=PASS"$'\n'

check_scalar() {
  local key="$1" sql="$2"
  local expected actual
  expected="$(manifest_value "${key}" | tr -d '[:space:]')"
  actual="$(psql_scratch_value "${sql}" | tr -d '[:space:]')"
  record_check "${key}" "${expected}" "${actual}"
}

check_scalar postgres_version "show server_version;"
check_scalar postgis_version "select postgis_version();"
check_scalar schemas "select count(*) from information_schema.schemata where schema_name in ('source','core','geo','school','health','quality','history');"
check_scalar tables "select count(*) from pg_tables where schemaname in ('source','core','geo','school','health','quality','history');"
check_scalar alembic_revision "select coalesce(max(version_num), 'none') from alembic_version;"
check_scalar facilities "select count(*) from core.facilities;"
check_scalar source_records "select count(*) from source.records;"
check_scalar releases "select count(*) from source.releases;"
check_scalar geographic_releases "select count(*) from geo.geographic_releases;"
check_scalar administrative_units "select count(*) from geo.administrative_units;"
check_scalar facility_locations "select count(*) from core.facility_locations;"
check_scalar locations_with_geom "select count(*) from core.facility_locations where geom is not null;"
check_scalar locations_srid_4326 "select count(*) from core.facility_locations where geom is not null and ST_SRID(geom) = 4326;"

POSTGIS_VERSION="$(psql_scratch_value 'select postgis_version();' | tr -d '\n')"
if [[ -z "${POSTGIS_VERSION}" ]]; then
  CHECKS+="check.postgis_extension=FAIL postgis_version is empty"$'\n'
  RESULT="fail"
else
  CHECKS+="check.postgis_extension=PASS version=${POSTGIS_VERSION}"$'\n'
fi

write_report

if [[ "${RESULT}" != "pass" ]]; then
  echo "Restore verification FAILED. Report: ${REPORT_FILE}" >&2
  grep '=FAIL' "${REPORT_FILE}" >&2 || true
  exit 1
fi

echo "Restore verification passed."
echo "report=${REPORT_FILE}"
echo "restore_database=${SCRATCH_DB}"
grep -c '=PASS' "${REPORT_FILE}" | awk '{print "passed_checks=" $1}'
