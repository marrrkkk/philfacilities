#!/usr/bin/env bash
#
# External smoke check for a running PhilFacilities API and web app. Suitable for
# a cron job, uptime monitor, or post-deploy verification. It checks liveness,
# database reachability, the public statistics endpoint, and the web homepage.
set -euo pipefail

API_BASE_URL="${PHILFACILITIES_API_BASE_URL:-http://127.0.0.1:8010}"
WEB_BASE_URL="${PHILFACILITIES_WEB_BASE_URL:-http://127.0.0.1:3000}"
TIMEOUT_SECONDS="${PHILFACILITIES_SMOKE_TIMEOUT_SECONDS:-30}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

curl_json() {
  curl --fail --silent --show-error --max-time "${TIMEOUT_SECONDS}" "$1"
}

health="$(curl_json "${API_BASE_URL}/healthz")" || fail "API health endpoint is unreachable"
python3 - "${health}" <<'PY' || fail "API health response is degraded or malformed"
import json
import sys

body = json.loads(sys.argv[1])
if body.get("status") != "ok":
    raise SystemExit(f"status={body.get('status')!r}")
if body.get("database") != "ok":
    raise SystemExit(f"database={body.get('database')!r}")
print(f"api=ok version={body.get('version', 'unknown')} environment={body.get('environment', 'unknown')}")
PY

stats="$(curl_json "${API_BASE_URL}/v1/statistics")" || fail "statistics endpoint is unreachable"
published="$(python3 - "${stats}" <<'PY'
import json
import sys

body = json.loads(sys.argv[1])
value = body.get("published_facilities")
if not isinstance(value, int):
    raise SystemExit("published_facilities is missing or not an integer")
print(value)
PY
)" || fail "statistics response is malformed"

web_code="$(curl --silent --show-error --max-time "${TIMEOUT_SECONDS}" \
  --output /dev/null --write-out '%{http_code}' "${WEB_BASE_URL}/")" \
  || fail "web homepage is unreachable"
if [[ "${web_code}" != "200" ]]; then
  fail "web homepage returned HTTP ${web_code}"
fi

echo "web=ok status=${web_code}"
echo "statistics=ok published_facilities=${published}"
echo "SMOKE CHECK PASSED"
