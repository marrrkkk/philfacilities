#!/usr/bin/env python3
"""Fail when a relative Markdown link points at a missing local path."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".next",
    ".venv",
    "node_modules",
    "playwright-report",
    "test-results",
    "var",
}
LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def main() -> int:
    checked = 0
    missing: list[tuple[Path, str]] = []

    for path in sorted(ROOT.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        for match in LINK.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            checked += 1
            if not (path.parent / target).exists():
                missing.append((path.relative_to(ROOT), target))

    print(f"checked {checked} local links")
    if missing:
        for source, target in missing:
            print(f"MISSING {source}: {target}")
        return 1
    print("all local markdown links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
