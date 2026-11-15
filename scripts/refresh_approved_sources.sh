#!/usr/bin/env bash
# Refresh only sources whose rights evidence permits public redistribution.
#
# The loaders are idempotent: an unchanged checksum is skipped, a changed file is
# retained as a new immutable release, and validation failures never replace the
# previously published release. Blocked sources are intentionally not refreshed.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Refreshing rights-cleared geography, population, PhilHealth, and OSM sources."
uv run philfacilities-ingest load-psgc-bettergov
uv run philfacilities-ingest load-population
uv run philfacilities-ingest load-philhealth
uv run philfacilities-ingest load-osm --domain health
uv run philfacilities-ingest load-osm --domain education
uv run philfacilities-ingest status
