"""Tests for the test harness and CI contract themselves.

A green build is only meaningful if integration tests really ran. These tests
lock in the two guards that make that true: ``--require-integration`` turns a
missing PostGIS database into a failure, and the CI workflow actually passes
that flag to pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nobody@127.0.0.1:1/unreachable_test"
INTEGRATION_TEST = "tests/test_api_integration.py::test_statistics_and_facility_inventory_agree"


def _run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PHILFACILITIES_TEST_DATABASE_URL"] = UNREACHABLE_DATABASE_URL
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-q",
            INTEGRATION_TEST,
            *args,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_missing_test_database_skips_by_default() -> None:
    """Without the flag, a missing database remains a local skip."""

    result = _run_pytest()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout


def test_require_integration_fails_when_test_database_unavailable() -> None:
    """With the flag, a missing database fails instead of skipping."""

    result = _run_pytest("--require-integration")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "ERROR tests/test_api_integration.py" in output
    assert "PostGIS test database is unavailable" in output


def test_require_integration_rejects_a_run_with_no_integration_tests() -> None:
    """A filter that deselects every integration test is also a hard failure."""

    result = _run_pytest("--require-integration", "-k", "definitely_not_a_test_name")
    assert result.returncode != 0
    assert "No integration tests were selected" in result.stdout + result.stderr


def test_ci_workflow_enforces_integration_and_required_jobs() -> None:
    """Guard against deleting the integration gate or a required check."""

    config = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = config["jobs"]

    required = {"quality", "python-tests", "web", "e2e"}
    assert required <= set(jobs)
    assert set(jobs["ci-ok"]["needs"]) == required

    for name in required:
        assert "timeout-minutes" in jobs[name], f"{name} has no timeout"
        assert jobs[name].get("continue-on-error") is not True, f"{name} may fail silently"

    matrix = jobs["python-tests"]["strategy"]["matrix"]["python-version"]
    assert set(matrix) == {"3.12", "3.14"}

    commands = [step.get("run", "") for job in jobs.values() for step in job.get("steps", [])]
    assert any("--require-integration" in command for command in commands)


@pytest.mark.parametrize("marker", ["integration", "contract", "data_quality"])
def test_pytest_markers_are_declared(marker: str) -> None:
    """Markers used by the suite must be registered to avoid silent typos."""

    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{marker}:' in config
