"""Helpers for data that may be opened in spreadsheet software."""

from __future__ import annotations

from decimal import Decimal


def sanitize_csv_cell(value: object) -> str:
    """Neutralize spreadsheet formula prefixes while preserving the text.

    CSV is plain text, but spreadsheet applications may evaluate a cell that
    starts with ``=``, ``+``, ``-``, or ``@``. Prefixing an apostrophe keeps the
    original text visible without turning source-controlled text into a formula.
    Numeric values are left alone so negative coordinates remain numbers.
    """

    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal, bool)):
        return str(value)
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
