"""Shared pytest configuration.

Integration tests run against a dedicated PostgreSQL/PostGIS test database. They are
skipped when the database is unavailable, so parser/unit tests remain runnable without
Docker. The test schema is destroyed and rebuilt on each session to keep counts and
provenance assertions deterministic.

Safety rail: the database name must end in ``_test``. Point
``PHILFACILITIES_TEST_DATABASE_URL`` at a throwaway database only.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parent
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://philfacilities:philfacilities@localhost:54330/philfacilities_test"
)
TEST_DATABASE_URL = os.environ.get("PHILFACILITIES_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)

_database_name = urlparse(TEST_DATABASE_URL.replace("+psycopg", "")).path.lstrip("/")
if not _database_name.endswith("_test"):
    raise RuntimeError(
        "Refusing to run destructive integration fixtures: the test database name must "
        f"end with '_test' (got {_database_name!r})."
    )

# These must be set before any application module reads its cached settings.
os.environ["PHILFACILITIES_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["PHILFACILITIES_ENV"] = "test"
os.environ["PHILFACILITIES_RATE_LIMIT_PER_MINUTE"] = "100000"
_test_artifacts = Path(tempfile.mkdtemp(prefix="philfacilities-tests-"))
os.environ["PHILFACILITIES_RAW_STORE"] = str(_test_artifacts / "raw")
os.environ["PHILFACILITIES_REPORT_DIR"] = str(_test_artifacts / "reports")

SCHEMAS = (
    "source",
    "core",
    "geo",
    "school",
    "health",
    "utility",
    "quality",
    "history",
    "stats",
)


def _reset_schema(database_url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            for schema in SCHEMAS:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def seeded_database() -> str:
    """Rebuild the test schema and load the deterministic synthetic demo dataset."""

    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(TEST_DATABASE_URL, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:  # pragma: no cover - environment-dependent skip
        pytest.skip(
            "PostGIS test database is unavailable. Start it with "
            "`docker compose -f infra/compose.yaml --profile test up -d test-db`. "
            f"({type(exc).__name__}: {exc})"
        )

    from alembic import command
    from alembic.config import Config

    _reset_schema(TEST_DATABASE_URL)
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")

    from philfacilities_ingest.cli import load_demo

    load_demo(reset=True)
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def client(seeded_database: str):
    from fastapi.testclient import TestClient
    from philfacilities_api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(seeded_database: str):
    from philfacilities_api.db import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="session")
def openapi_client():
    """A client that only needs the app object, not a live database."""

    from fastapi.testclient import TestClient
    from philfacilities_api.main import app

    with TestClient(app) as test_client:
        yield test_client
