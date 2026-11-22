#!/usr/bin/env bash
#
# Package the latest public projection as a GitHub release asset and ask the
# publish-heroku workflow to install it. The dump is built locally by
# scripts/build_public_projection.py; only the finished read model leaves this
# machine. Requires `gh auth login` with release and workflow permissions.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PUBLISH_DIR="${PHILFACILITIES_PUBLISH_DIR:-${ROOT_DIR}/var/publish}"
RELEASE_TAG="${1:-public-$(date -u +%Y%m%dT%H%M%SZ)}"
WORKFLOW="publish-heroku.yml"

DUMP_FILE="$(find "${PUBLISH_DIR}" -maxdepth 1 -name 'public-*.dump' -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr | awk 'NR==1 {sub(/^[^ ]+ /, ""); print}')"
if [[ -z "${DUMP_FILE}" || ! -f "${DUMP_FILE}" ]]; then
  echo "No public projection dump found in ${PUBLISH_DIR}." >&2
  echo "Run: uv run python scripts/build_public_projection.py" >&2
  exit 1
fi
MANIFEST_FILE="${DUMP_FILE%.dump}.manifest.json"
if [[ ! -f "${MANIFEST_FILE}" ]]; then
  echo "Manifest not found: ${MANIFEST_FILE}" >&2
  exit 1
fi

FACILITIES="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["core.facilities"])' "${MANIFEST_FILE}")"
SHA256="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "${MANIFEST_FILE}")"
NOTES_FILE="$(mktemp)"
trap 'rm -f "${NOTES_FILE}"' EXIT
cat >"${NOTES_FILE}" <<EOF
Public-only read model for the hosted API.

- public facilities: ${FACILITIES}
- dump sha256: ${SHA256}

Built by \`scripts/build_public_projection.py\`. Installed by
\`.github/workflows/${WORKFLOW}\`. Assertions, raw payloads and internal rows
remain in the authoritative database.
EOF

if gh release view "${RELEASE_TAG}" >/dev/null 2>&1; then
  echo "→ Uploading assets to existing release ${RELEASE_TAG}"
  gh release upload "${RELEASE_TAG}" "${DUMP_FILE}" "${MANIFEST_FILE}" --clobber
else
  echo "→ Creating release ${RELEASE_TAG}"
  gh release create "${RELEASE_TAG}" "${DUMP_FILE}" "${MANIFEST_FILE}" \
    --title "${RELEASE_TAG}" --notes-file "${NOTES_FILE}"
fi

echo "→ Triggering ${WORKFLOW}"
gh workflow run "${WORKFLOW}" --field "release_tag=${RELEASE_TAG}"

echo "Published projection ${RELEASE_TAG}."
echo "Release: $(gh release view "${RELEASE_TAG}" --json url --jq .url)"
echo "Deploy: https://github.com/$(gh repo view --json nameWithOwner --jq .nameWithOwner)/actions"
