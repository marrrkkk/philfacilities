from __future__ import annotations

import csv
import html
import io
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dateutil import parser as date_parser


class RequiredColumnsError(ValueError):
    """Raised when a source file no longer matches its documented schema."""


def normalise_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalise_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    # Spreadsheet and HTML exports frequently double-encode ``&`` as
    # ``&amp;``. Decode it for the canonical candidate while the preserved raw
    # payload keeps the original source bytes.
    text = html.unescape(str(value).replace("\u00a0", " ")).strip()
    return text or None


def has_usable_name(value: Any) -> bool:
    """Return True when a label contains at least one letter or digit.

    OpenStreetMap occasionally stores punctuation-only placeholders such as
    ``.`` or ``=`` in the ``name`` tag.  Those are not facility names and must
    not become community facilities.  The check is Unicode-aware so legitimate
    names written in non-Latin scripts are retained.
    """

    text = clean_text(value)
    if text is None:
        return False
    return re.search(r"[^\W_]", text, flags=re.UNICODE) is not None


def parse_int(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


TRUE_VALUES = {"true", "yes", "y", "1", "offered", "offer"}
FALSE_VALUES = {"false", "no", "n", "0", "not offered", "not_offered"}


def parse_bool(value: Any) -> bool | None:
    text = clean_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    return None


def parse_date(value: Any) -> date | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return date_parser.parse(text, dayfirst=False, fuzzy=False).date()
    except (ValueError, OverflowError):
        return None


def jsonify(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def read_csv_rows(content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RequiredColumnsError("Could not decode CSV using supported encodings.")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [normalise_header(name) for name in (reader.fieldnames or [])]
    rows = []
    for raw in reader:
        rows.append({normalise_header(key): value for key, value in raw.items()})
    return headers, rows


def require_columns(headers: list[str], required: set[str], source: str) -> None:
    missing = required - set(headers)
    if missing:
        raise RequiredColumnsError(
            f"{source}: schema drift detected; missing required columns: {sorted(missing)}"
        )


def require_any_columns(headers: list[str], aliases: list[str], source: str) -> None:
    """Require at least one header from each alias list.

    Source exports rename columns between releases; accepting documented aliases
    avoids false schema-drift failures while still rejecting genuinely missing
    fields.
    """
    if not set(aliases) & set(headers):
        raise RequiredColumnsError(
            f"{source}: schema drift detected; none of the accepted columns "
            f"{sorted(aliases)} is present"
        )


def require_column_groups(headers: list[str], groups: list[list[str]], source: str) -> None:
    for aliases in groups:
        require_any_columns(headers, aliases, source)


def first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def normalise_ownership(value: Any) -> str:
    text = (clean_text(value) or "").lower()
    if any(token in text for token in ("public", "government", "govt", "national", "lgu")):
        return "government"
    if any(token in text for token in ("private", "non-profit", "nonprofit", "religious")):
        return "private"
    return "unknown"
