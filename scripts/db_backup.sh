#!/usr/bin/env bash
#
# Create a portable custom-format PostgreSQL/PostGIS dump plus a checksum and
# source manifest. The manifest is consumed by scripts/db_restore_verify.sh.
#
# Defaults target the local Docker Compose database. Override the PHILFACILITIES_DB_*
# variables (and PHILFACILITIES_COMPOSE_FILE) when using another Compose service.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PHILFACILITIES_COMPOSE_FILE:-${ROOT_DIR}/infra/compose.yaml}"
DB_SERVICE="${PHILFACILITIES_DB_SERVICE:-db}"
DB_NAME="${PHILFACILITIES_DB_NAME:-philfacilities}"
DB_USER="${PHILFACILITIES_DB_USER:-philfacilities}"
BACKUP_DIR="${PHILFACILITIES_BACKUP_DIR:-${ROOT_DIR}/var/backups}"
TIMESTAMP="${PHILFACILITIES_BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

psql_value() {
  compose exec -T "${DB_SERVICE}" psql \
    -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -Atc "$1"
}

count_rows() {
  psql_value "select count(*) from $1;" | tr -d '[:space:]'
}

require_value() {
  local key="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    echo "Backup failed: ${key} was empty." >&2
    exit 1
  fi
  printf '%s=%s\n' "${key}" "${value}"
}

mkdir -p "${BACKUP_DIR}"
umask 077

DUMP_FILE="${BACKUP_DIR}/philfacilities-${TIMESTAMP}.dump"
MANIFEST_FILE="${DUMP_FILE}.manifest.txt"
TOC_FILE="${DUMP_FILE}.toc.txt"
PARTIAL_FILE="${DUMP_FILE}.partial"

cleanup() {
  rm -f "${PARTIAL_FILE}"
}
trap cleanup EXIT

echo "→ Dumping ${DB_NAME} from Compose service ${DB_SERVICE}"
compose exec -T "${DB_SERVICE}" pg_dump \
  -U "${DB_USER}" -d "${DB_NAME}" \
  --format=custom --no-owner --no-privileges >"${PARTIAL_FILE}"
mv "${PARTIAL_FILE}" "${DUMP_FILE}"

echo "→ Verifying the dump archive and writing its table of contents"
compose exec -T "${DB_SERVICE}" pg_restore --list <"${DUMP_FILE}" >"${TOC_FILE}"
TOC_ENTRIES="$(grep -cve '^;' "${TOC_FILE}" || true)"
if [[ "${TOC_ENTRIES}" -eq 0 ]]; then
  echo "Backup failed: pg_restore --list found no archive entries." >&2
  exit 1
fi

SHA256="$(sha256sum "${DUMP_FILE}" | awk '{print $1}')"
BYTES="$(stat -c '%s' "${DUMP_FILE}")"
printf '%s  %s\n' "${SHA256}" "$(basename "${DUMP_FILE}")" >"${DUMP_FILE}.sha256"

{
  require_value format_version "1"
  require_value created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  require_value source_database "${DB_NAME}"
  require_value dump_file "$(basename "${DUMP_FILE}")"
  require_value bytes "${BYTES}"
  require_value sha256 "${SHA256}"
  require_value toc_entries "${TOC_ENTRIES}"
  require_value postgres_version "$(psql_value 'show server_version;' | tr -d '[:space:]')"
  require_value postgis_version "$(psql_value 'select postgis_version();' | tr -d '\n')"
  require_value alembic_revision "$(psql_value "select coalesce(max(version_num), 'none') from alembic_version;" | tr -d '[:space:]')"
  require_value schemas "$(psql_value "select count(*) from information_schema.schemata where schema_name in ('source','core','geo','school','health','quality','history');" | tr -d '[:space:]')"
  require_value tables "$(psql_value "select count(*) from pg_tables where schemaname in ('source','core','geo','school','health','quality','history');" | tr -d '[:space:]')"
  require_value facilities "$(count_rows core.facilities)"
  require_value source_records "$(count_rows source.records)"
  require_value releases "$(count_rows source.releases)"
  require_value geographic_releases "$(count_rows geo.geographic_releases)"
  require_value administrative_units "$(count_rows geo.administrative_units)"
  require_value facility_locations "$(count_rows core.facility_locations)"
  require_value locations_with_geom "$(psql_value 'select count(*) from core.facility_locations where geom is not null;' | tr -d '[:space:]')"
  require_value locations_srid_4326 "$(psql_value 'select count(*) from core.facility_locations where geom is not null and ST_SRID(geom) = 4326;' | tr -d '[:space:]')"
} >"${MANIFEST_FILE}"

echo "Backup complete."
echo "dump=${DUMP_FILE}"
echo "manifest=${MANIFEST_FILE}"
echo "sha256=${SHA256}"
echo "bytes=${BYTES}"
echo "toc_entries=${TOC_ENTRIES}"
