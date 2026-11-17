# PhilFacilities developer commands.
# `just` is optional: every recipe maps to a plain command shown in README.md.

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

db_port := env("PHILFACILITIES_DB_PORT", "54329")
test_db_port := env("PHILFACILITIES_TEST_DB_PORT", "54330")
database_url := env("PHILFACILITIES_DATABASE_URL", "postgresql+psycopg://philfacilities:philfacilities@localhost:" + db_port + "/philfacilities")
test_database_url := env("PHILFACILITIES_TEST_DATABASE_URL", "postgresql+psycopg://philfacilities:philfacilities@localhost:" + test_db_port + "/philfacilities_test")

default:
    @just --list

install:
    uv sync --all-packages
    pnpm install --frozen-lockfile

setup: install db-up migrate
    @echo "Local dependencies and PostgreSQL/PostGIS are ready. Run 'uv run philfacilities-ingest source run --group approved' to load the rights-cleared real data."

format:
    uv run ruff format .

db-up:
    docker compose -f infra/compose.yaml up -d db

db-test-up:
    docker compose -f infra/compose.yaml --profile test up -d test-db

db-down:
    docker compose -f infra/compose.yaml --profile test down

migrate:
    DATABASE_URL="{{database_url}}" uv run alembic -c apps/api/alembic.ini upgrade head

db-migrate: migrate

fixtures:
    uv run philfacilities-ingest generate-fixtures

demo:
    uv run philfacilities-ingest demo load --reset

demo-status:
    uv run philfacilities-ingest status

backup-db:
    scripts/db_backup.sh

restore-verify *args:
    scripts/db_restore_verify.sh {{args}}

smoke:
    scripts/smoke_check.sh

benchmark-api *args:
    uv run python scripts/api_benchmark.py {{args}}

api:
    PHILFACILITIES_DATABASE_URL="{{database_url}}" uv run uvicorn philfacilities_api.main:app --host 127.0.0.1 --port 8010 --reload

web:
    pnpm --filter @philfacilities/web dev

test:
    uv run pytest

test-db:
    PHILFACILITIES_TEST_DATABASE_URL="{{test_database_url}}" uv run pytest

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    pnpm lint

typecheck:
    pnpm typecheck

build:
    pnpm build

e2e:
    pnpm --filter @philfacilities/web test:e2e

typegen: openapi-export
    pnpm typegen

openapi-export:
    uv run python -c "import json; from pathlib import Path; from philfacilities_api.main import app; Path('packages/api-client/openapi.json').write_text(json.dumps(app.openapi(), indent=2) + '\n')"

check: lint typecheck
    uv run pytest
    pnpm build
    uv run python scripts/check_markdown_links.py
