"""Validate the researched source-candidate inventory.

The candidate registry is deliberately separate from ``source.datasets``. A
candidate has not been acquired, schema-verified, rights-reviewed, or
published. Promoting one to a dataset remains an explicit ingestion decision.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REQUIRED_FIELDS = (
    "source_id",
    "custodian",
    "title",
    "urls",
    "evidence_state",
    "access_state",
    "rights_state",
    "coverage_scope",
    "priority",
    "next_action",
    "tracker_ids",
    "last_verified",
)

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "sources" / "source-candidates.json"


def load_source_candidates(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def validate_source_candidates(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["sources must be a non-empty list"]

    allowed = payload.get("allowed_states") or {}
    evidence_states = set(allowed.get("evidence") or ())
    access_states = set(allowed.get("access") or ())
    rights_states = set(allowed.get("rights") or ())
    coverage_states = set(allowed.get("coverage") or ())

    seen: set[str] = set()
    for index, source in enumerate(sources):
        label = source.get("source_id") or f"source[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label}: entry is not an object")
            continue
        for field in REQUIRED_FIELDS:
            if field not in source:
                errors.append(f"{label}: missing required field {field}")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{label}: source_id must be a non-empty string")
        elif source_id in seen:
            errors.append(f"{label}: duplicate source_id")
        else:
            seen.add(source_id)
        custodian = source.get("custodian")
        if not isinstance(custodian, str) or not custodian.strip():
            errors.append(f"{label}: custodian must be a non-empty string")
        urls = source.get("urls")
        if not isinstance(urls, list) or not urls:
            errors.append(f"{label}: urls must be a non-empty list")
        else:
            for url in urls:
                parsed = urlparse(str(url))
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    errors.append(f"{label}: invalid URL {url!r}")
        checks = (
            ("evidence_state", evidence_states),
            ("access_state", access_states),
            ("rights_state", rights_states),
            ("coverage_scope", coverage_states),
        )
        for field, allowed_values in checks:
            value = source.get(field)
            if allowed_values and value not in allowed_values:
                errors.append(f"{label}: {field}={value!r} is not an allowed state")
        tracker_ids = source.get("tracker_ids")
        if not isinstance(tracker_ids, list) or not all(
            isinstance(item, str) and item.strip() for item in tracker_ids
        ):
            errors.append(f"{label}: tracker_ids must be a list of non-empty strings")
    return errors


def summarize_source_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    sources = payload.get("sources") or []
    return {
        "total": len(sources),
        "by_evidence_state": dict(
            sorted(Counter(source.get("evidence_state") for source in sources).items())
        ),
        "by_access_state": dict(
            sorted(Counter(source.get("access_state") for source in sources).items())
        ),
        "by_rights_state": dict(
            sorted(Counter(source.get("rights_state") for source in sources).items())
        ),
        "by_coverage_scope": dict(
            sorted(Counter(source.get("coverage_scope") for source in sources).items())
        ),
        "by_priority": dict(sorted(Counter(source.get("priority") for source in sources).items())),
    }
