"""Shared primitives for the generated report writers.

Report generators in this package and in ``scripts/`` all need the same small
set of deterministic helpers: timestamp formatting, CSV/JSONL/text writers,
source-URL normalization for artifact-to-register matching, and Markdown table
formatting.  Keeping them here means report outputs stay identical while the
individual generators own only their domain-specific row construction.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def now_iso() -> str:
    """Return the current UTC time in the format used by generated reports."""

    return datetime.now(UTC).isoformat()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def source_url_key(url: str | None) -> str:
    """Normalize a source URL for exact artifact-to-register matching."""

    if not url:
        return ""
    parsed = urlparse(str(url).strip())
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    return f"{host}{parsed.path.rstrip('/')}".casefold()


def format_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, datetime):
        return value.isoformat()
    text_value = str(value).replace("\n", " ").strip()
    return text_value.replace("|", "\\|")


def markdown_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(format_value(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(path: Path, title: str, generated_at: str, intro: str, body: str) -> None:
    path.write_text(
        f"# {title}\n\n"
        f"**Generated:** {generated_at}  \n"
        f"**Source of truth:** the configured PhilFacilities PostgreSQL database.  \n\n"
        f"{intro}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
